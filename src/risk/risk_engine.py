"""
Portfolio-Level Risk Engine.

Provides pre-trade risk checks and position sizing rules that operate on
the *portfolio* as a whole.  This is intentionally separate from the
per-trade stop-loss / take-profit configuration in ``src.utils.config.RiskConfig``
which is wired into BacktestEngine's broker/execution layer.

DESIGN PRINCIPLE
----------------
  - All checks are *read-only advisory* -- the risk engine never executes
    orders or mutates portfolio state.
  - The caller (portfolio backtester, research runner) acts on the
    RiskDecision returned by ``PortfolioRiskManager.check_entry()``.
  - Regime-aware risk throttling is optional: when a ``regime_label`` is
    supplied that matches a high-risk regime, the engine can reduce the
    allowed position fraction.

PORTFOLIO RISK RULES (configurable, all documented)
----------------------------------------------------
  max_risk_per_trade_pct    : Maximum fraction of portfolio equity to risk
                              on a single trade (default 0.01 = 1%).
                              Controls the relationship between stop-loss
                              distance and position size.

  max_portfolio_exposure_pct: Maximum fraction of portfolio equity that may
                              be deployed simultaneously (default 0.20 = 20%).
                              Prevents over-concentration.

  max_drawdown_pct          : Kill-switch: if current portfolio drawdown
                              exceeds this, all new entries are blocked
                              (default 0.15 = 15%).

  max_concurrent_positions  : Hard limit on open positions across the
                              portfolio (default 10).

REGIME-AWARE THROTTLING (optional)
------------------------------------
  When regime_risk_overrides is provided, entering a high-risk regime
  reduces max_portfolio_exposure_pct and/or max_concurrent_positions:

    {
      "bearish_volatile": {"max_portfolio_exposure_pct": 0.10,
                           "max_concurrent_positions":   5},
      "risk_off":         {"max_portfolio_exposure_pct": 0.00,
                           "max_concurrent_positions":   0},
    }

  "risk_off" with max_concurrent_positions=0 means no new positions.

POSITION SIZING (PositionSizer)
--------------------------------
  PositionSizer answers: "How many shares/units given a capital allocation
  and a price?"

    position_size_pct: fraction of allocated capital to deploy per position
                       (default 0.95 = 95%, leaves 5% as buffer for fees).

  ``size_position(capital, price)`` returns the quantity (shares) to buy.

VALIDATION FUNCTION (non-class)
---------------------------------
  ``validate_portfolio_risk(equity_curve, config)`` runs post-hoc risk
  checks on an existing equity curve and returns a list of violation
  strings.  Used for research reporting.

PUBLIC API
----------
  PortfolioRiskConfig   Configuration dataclass (Pydantic model).
  PositionSizer         Quantity calculator.
  RiskDecision          Result of a pre-trade risk check.
  PortfolioRiskManager  Main risk management class.
  validate_portfolio_risk()  Post-hoc equity curve validation.
  generate_risk_report()     Markdown research report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    from pydantic import BaseModel, Field, field_validator
    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False
    BaseModel = object  # type: ignore[assignment,misc]

from src.utils.logger import setup_logger

logger = setup_logger("risk_engine")

# ---------------------------------------------------------------------------
# High-risk composite regimes (used for default regime throttling)
# ---------------------------------------------------------------------------
_HIGH_RISK_REGIMES: frozenset[str] = frozenset({
    "bearish_volatile",
    "risk_off",
})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

if _PYDANTIC_AVAILABLE:
    class PortfolioRiskConfig(BaseModel):
        """Portfolio-level risk management configuration.

        All thresholds are expressed as fractions (not percentages).
        Example: max_risk_per_trade_pct=0.01 means 1% per trade.

        Note: This is distinct from ``src.utils.config.RiskConfig`` which
        handles per-trade stop-loss, take-profit, and trailing-stop for
        BacktestEngine's broker layer.
        """

        # Per-trade risk limit
        max_risk_per_trade_pct: float = Field(
            default=0.01, gt=0, le=1.0,
            description="Max fraction of portfolio equity risked per trade (default 1%).",
        )

        # Portfolio exposure cap
        max_portfolio_exposure_pct: float = Field(
            default=0.20, gt=0, le=1.0,
            description="Max fraction of equity deployed simultaneously (default 20%).",
        )

        # Drawdown kill-switch
        max_drawdown_pct: float = Field(
            default=0.15, gt=0, le=1.0,
            description="Block all new entries if portfolio drawdown exceeds this (default 15%).",
        )

        # Concurrent positions hard cap
        max_concurrent_positions: int = Field(
            default=10, gt=0,
            description="Maximum number of simultaneously open positions (default 10).",
        )

        # Regime-aware throttle overrides
        regime_risk_overrides: dict[str, dict[str, Any]] = Field(
            default_factory=dict,
            description=(
                "Optional per-regime overrides for risk parameters. "
                "Keys are composite regime labels (e.g. 'risk_off'). "
                "Values are dicts with any subset of the risk config fields."
            ),
        )

else:
    # Fallback pure-Python dataclass (no Pydantic)
    @dataclass
    class PortfolioRiskConfig:  # type: ignore[no-redef]
        max_risk_per_trade_pct: float = 0.01
        max_portfolio_exposure_pct: float = 0.20
        max_drawdown_pct: float = 0.15
        max_concurrent_positions: int = 10
        regime_risk_overrides: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Position sizer
# ---------------------------------------------------------------------------

@dataclass
class PositionSizer:
    """Compute position quantity from allocated capital and entry price.

    Parameters
    ----------
    position_size_pct : float
        Fraction of allocated capital to deploy per entry (default 0.95 = 95%).
        The remaining 5% acts as a buffer to absorb fee and slippage rounding.
    """

    position_size_pct: float = 0.95

    def size_position(self, capital: float, price: float) -> float:
        """Return the number of units to buy.

        Parameters
        ----------
        capital : float
            Capital allocated to this position (e.g. initial_capital / max_positions).
        price : float
            Entry price per unit.

        Returns
        -------
        float
            Quantity (fractional units allowed for research purposes).
            Returns 0.0 when price <= 0 or capital <= 0.
        """
        if price <= 0.0 or capital <= 0.0:
            return 0.0

        pct = max(0.0, min(1.0, self.position_size_pct))
        return (capital * pct) / price

    def max_capital_for_risk(
        self,
        portfolio_equity: float,
        stop_loss_pct: float,
        max_risk_pct: float = 0.01,
    ) -> float:
        """Return the maximum capital to deploy given a stop-loss distance.

        Ensures that hitting the stop-loss costs at most ``max_risk_pct`` of
        portfolio equity.

        max_capital = (portfolio_equity * max_risk_pct) / stop_loss_pct

        Parameters
        ----------
        portfolio_equity : float
            Current total portfolio value.
        stop_loss_pct : float
            Distance from entry to stop-loss as a fraction (e.g. 0.02 = 2%).
        max_risk_pct : float
            Maximum acceptable portfolio equity at risk (default 0.01 = 1%).

        Returns
        -------
        float
            Maximum deployment capital (Rs / $).  Returns 0 when inputs are
            invalid (stop_loss_pct <= 0 or portfolio_equity <= 0).
        """
        if stop_loss_pct <= 0.0 or portfolio_equity <= 0.0:
            return 0.0
        return (portfolio_equity * max_risk_pct) / stop_loss_pct


# ---------------------------------------------------------------------------
# Risk decision
# ---------------------------------------------------------------------------

@dataclass
class RiskDecision:
    """Result of a pre-trade risk check.

    Attributes
    ----------
    allowed : bool
        True when all risk rules pass and the entry is permitted.
    blocked_reason : str
        Human-readable explanation when ``allowed`` is False.
    effective_max_exposure_pct : float
        The exposure cap in effect after any regime override.
    effective_max_positions : int
        The position cap in effect after any regime override.
    regime_throttled : bool
        True when regime-aware overrides reduced any limit.
    """

    allowed: bool
    blocked_reason: str = ""
    effective_max_exposure_pct: float = 0.20
    effective_max_positions: int = 10
    regime_throttled: bool = False


# ---------------------------------------------------------------------------
# Portfolio Risk Manager
# ---------------------------------------------------------------------------

class PortfolioRiskManager:
    """Main portfolio risk management class.

    Runs pre-trade checks and exposure monitoring for research simulations.

    Parameters
    ----------
    config : PortfolioRiskConfig
        Risk configuration.  All thresholds are expressed as fractions.
    """

    def __init__(self, config: Optional[PortfolioRiskConfig] = None) -> None:
        self.config = config or PortfolioRiskConfig()
        self._sizer = PositionSizer()

    # ------------------------------------------------------------------
    # Pre-trade check (entry gate)
    # ------------------------------------------------------------------

    def check_entry(
        self,
        portfolio_equity: float,
        current_drawdown_pct: float,
        open_positions_count: int,
        deployed_capital: float,
        regime_label: Optional[str] = None,
    ) -> RiskDecision:
        """Evaluate whether a new position entry is permitted.

        Parameters
        ----------
        portfolio_equity : float
            Current total portfolio value (cash + market value of positions).
        current_drawdown_pct : float
            Current drawdown from peak as a fraction (0.05 = 5%).
        open_positions_count : int
            Number of positions currently open.
        deployed_capital : float
            Sum of current open position entry values (capital in play).
        regime_label : str, optional
            Composite regime string (e.g. 'risk_off').  Used for optional
            regime-aware override lookups.

        Returns
        -------
        RiskDecision
            Allowed if all checks pass; blocked with reason otherwise.
        """
        cfg = self.config

        # --- Resolve effective limits (apply regime overrides if any) ---
        effective_exposure = cfg.max_portfolio_exposure_pct
        effective_positions = cfg.max_concurrent_positions
        regime_throttled = False

        if regime_label and cfg.regime_risk_overrides:
            override = cfg.regime_risk_overrides.get(regime_label, {})
            if override:
                regime_throttled = True
                effective_exposure = float(
                    override.get("max_portfolio_exposure_pct", effective_exposure)
                )
                effective_positions = int(
                    override.get("max_concurrent_positions", effective_positions)
                )
                logger.debug(
                    f"Regime override applied for '{regime_label}': "
                    f"exposure={effective_exposure:.0%}, "
                    f"positions={effective_positions}"
                )

        base_kwargs = dict(
            effective_max_exposure_pct=effective_exposure,
            effective_max_positions=effective_positions,
            regime_throttled=regime_throttled,
        )

        # --- Rule 1: Drawdown kill-switch ---
        if current_drawdown_pct > cfg.max_drawdown_pct:
            reason = (
                f"Drawdown kill-switch triggered: current drawdown "
                f"{current_drawdown_pct:.2%} > limit {cfg.max_drawdown_pct:.2%}."
            )
            logger.info(f"RiskEngine BLOCKED: {reason}")
            return RiskDecision(allowed=False, blocked_reason=reason, **base_kwargs)

        # --- Rule 2: Maximum concurrent positions ---
        if open_positions_count >= effective_positions:
            reason = (
                f"Max concurrent positions reached: {open_positions_count} open "
                f">= limit {effective_positions}."
            )
            logger.debug(f"RiskEngine BLOCKED: {reason}")
            return RiskDecision(allowed=False, blocked_reason=reason, **base_kwargs)

        # --- Rule 3: Maximum portfolio exposure ---
        if portfolio_equity > 0.0:
            current_exposure = deployed_capital / portfolio_equity
            if current_exposure >= effective_exposure:
                reason = (
                    f"Portfolio exposure cap: current {current_exposure:.2%} "
                    f">= limit {effective_exposure:.2%}."
                )
                logger.debug(f"RiskEngine BLOCKED: {reason}")
                return RiskDecision(allowed=False, blocked_reason=reason, **base_kwargs)

        return RiskDecision(allowed=True, **base_kwargs)

    # ------------------------------------------------------------------
    # Position sizing helper (delegates to PositionSizer)
    # ------------------------------------------------------------------

    def compute_position_size(
        self,
        capital: float,
        price: float,
        portfolio_equity: float,
        stop_loss_pct: Optional[float] = None,
    ) -> float:
        """Compute position size subject to risk limits.

        Uses the smaller of:
          a) capital * position_size_pct / price  (straight allocation)
          b) risk-based sizing from stop_loss distance (when stop_loss_pct given)

        Parameters
        ----------
        capital : float
            Capital allocated to this position slot.
        price : float
            Entry price.
        portfolio_equity : float
            Total portfolio equity (for risk-based sizing).
        stop_loss_pct : float, optional
            Stop-loss distance as a fraction (e.g. 0.02 = 2%).

        Returns
        -------
        float
            Recommended position quantity.
        """
        straight_qty = self._sizer.size_position(capital, price)

        if stop_loss_pct is not None and stop_loss_pct > 0.0:
            max_cap_risk = self._sizer.max_capital_for_risk(
                portfolio_equity=portfolio_equity,
                stop_loss_pct=stop_loss_pct,
                max_risk_pct=self.config.max_risk_per_trade_pct,
            )
            risk_qty = max_cap_risk / price if price > 0.0 else 0.0
            return min(straight_qty, risk_qty)

        return straight_qty

    # ------------------------------------------------------------------
    # Drawdown tracker
    # ------------------------------------------------------------------

    @staticmethod
    def compute_drawdown(equity_series: pd.Series) -> tuple[float, float]:
        """Compute current and maximum drawdown from an equity series.

        Parameters
        ----------
        equity_series : pd.Series
            Portfolio equity time series.

        Returns
        -------
        tuple[float, float]
            (current_drawdown_pct, max_drawdown_pct) as fractions.
        """
        if equity_series.empty or len(equity_series) < 2:
            return 0.0, 0.0

        peak = equity_series.cummax()
        drawdown_pct = (peak - equity_series) / peak.replace(0.0, float("nan"))
        drawdown_pct = drawdown_pct.fillna(0.0)

        current_dd = float(drawdown_pct.iloc[-1])
        max_dd = float(drawdown_pct.max())
        return current_dd, max_dd


# ---------------------------------------------------------------------------
# Post-hoc validation
# ---------------------------------------------------------------------------

def validate_portfolio_risk(
    equity_curve: pd.DataFrame,
    config: Optional[PortfolioRiskConfig] = None,
) -> list[str]:
    """Run post-hoc risk validation against an equity curve.

    Checks the equity curve for violations of the configured risk rules.
    Returns a list of violation strings (empty when all checks pass).

    Parameters
    ----------
    equity_curve : pd.DataFrame
        Portfolio equity curve (must contain ``portfolio_equity`` column).
    config : PortfolioRiskConfig, optional
        Risk configuration.  Uses default config when None.

    Returns
    -------
    list[str]
        List of human-readable violation descriptions.  Empty if clean.
    """
    cfg = config or PortfolioRiskConfig()
    violations: list[str] = []

    if equity_curve.empty:
        violations.append("Equity curve is empty; cannot validate risk rules.")
        return violations

    eq_col = "portfolio_equity" if "portfolio_equity" in equity_curve.columns else "equity"
    if eq_col not in equity_curve.columns:
        violations.append(
            f"Cannot validate: equity column '{eq_col}' not found in equity_curve."
        )
        return violations

    eq = equity_curve[eq_col].dropna()
    if eq.empty:
        violations.append("Equity series has no valid (non-NaN) values.")
        return violations

    # -- Check max drawdown --
    _, max_dd = PortfolioRiskManager.compute_drawdown(eq)
    if max_dd > cfg.max_drawdown_pct:
        violations.append(
            f"Max drawdown violation: {max_dd:.2%} exceeded limit {cfg.max_drawdown_pct:.2%}."
        )

    # -- Check for negative equity (bankruptcy) --
    if (eq < 0).any():
        violations.append(
            "Portfolio equity went negative (bankruptcy) during the backtest."
        )

    # -- Return-on-risk sanity: total return vs expected risk exposure --
    if len(eq) >= 2:
        total_return = eq.iloc[-1] / eq.iloc[0] - 1.0
        if total_return < -cfg.max_drawdown_pct:
            violations.append(
                f"Total return {total_return:.2%} is worse than max_drawdown_pct "
                f"limit {cfg.max_drawdown_pct:.2%} -- unusual; review backtest."
            )

    return violations


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_risk_report(
    config: PortfolioRiskConfig,
    validation_violations: list[str],
    equity_curve: Optional[pd.DataFrame] = None,
    output_path: Optional[str | Path] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Generate and save the risk engine validation markdown report.

    Parameters
    ----------
    config : PortfolioRiskConfig
        The risk configuration that was applied.
    validation_violations : list[str]
        Output of :func:`validate_portfolio_risk`.
    equity_curve : pd.DataFrame, optional
        Portfolio equity curve for drawdown display.
    output_path : str or Path, optional
        Where to write the markdown file.  Defaults to
        ``research/risk_engine_validation.md``.
    metadata : dict, optional
        Extra context to embed (symbols, strategies, interval, etc.).

    Returns
    -------
    str
        Full markdown content of the report.
    """
    output_path = (
        Path(output_path)
        if output_path
        else Path("research") / "risk_engine_validation.md"
    )
    metadata = dict(metadata) if metadata else {}

    lines = _build_risk_report_lines(config, validation_violations, equity_curve, metadata)
    content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Risk engine validation report written to {output_path}")

    return content


# ---------------------------------------------------------------------------
# Report helpers (ASCII-only for Windows cp1252 compatibility)
# ---------------------------------------------------------------------------

def _fmt_val(v: Any) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, int):
        return str(v)
    return str(v)


def _pct(v: float) -> str:
    return f"{v * 100.0:.2f}%"


def _build_risk_report_lines(
    config: PortfolioRiskConfig,
    violations: list[str],
    equity_curve: Optional[pd.DataFrame],
    metadata: dict[str, Any],
) -> list[str]:
    """Assemble all markdown sections for the risk engine validation report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        "# Risk Engine Validation Report",
        "",
        "## Run Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
    ]
    for key, val in metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Risk Configuration Applied",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        f"| Max Risk Per Trade | {_pct(config.max_risk_per_trade_pct)} |",
        f"| Max Portfolio Exposure | {_pct(config.max_portfolio_exposure_pct)} |",
        f"| Max Drawdown (kill-switch) | {_pct(config.max_drawdown_pct)} |",
        f"| Max Concurrent Positions | {config.max_concurrent_positions} |",
    ]

    # Regime overrides table
    overrides = getattr(config, "regime_risk_overrides", {})
    if overrides:
        lines += [
            "",
            "### Regime-Aware Overrides",
            "",
            "| Regime | Max Exposure | Max Positions |",
            "| --- | --- | --- |",
        ]
        for regime, ov in sorted(overrides.items()):
            exp = _pct(float(ov.get("max_portfolio_exposure_pct", config.max_portfolio_exposure_pct)))
            pos = str(int(ov.get("max_concurrent_positions", config.max_concurrent_positions)))
            lines.append(f"| {regime} | {exp} | {pos} |")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Validation result
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Validation Results",
        "",
    ]
    if not violations:
        lines += [
            "> **PASS** - All risk rules satisfied; no violations detected.",
            "",
        ]
    else:
        lines += [
            f"> **{len(violations)} VIOLATION(S) DETECTED**",
            "",
        ]
        for i, v in enumerate(violations, 1):
            lines.append(f"{i}. {v}")
        lines.append("")

    lines += ["---"]

    # ------------------------------------------------------------------
    # Equity curve drawdown snippet
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Drawdown Summary",
        "",
    ]
    if equity_curve is not None and not equity_curve.empty:
        eq_col = "portfolio_equity" if "portfolio_equity" in equity_curve.columns else "equity"
        if eq_col in equity_curve.columns:
            eq = equity_curve[eq_col].dropna()
            if len(eq) >= 2:
                _, max_dd = PortfolioRiskManager.compute_drawdown(eq)
                current_dd, _ = PortfolioRiskManager.compute_drawdown(eq)
                status = "OK" if max_dd <= config.max_drawdown_pct else "VIOLATION"
                lines += [
                    f"| Metric | Value |",
                    f"| --- | --- |",
                    f"| Max Drawdown (actual) | **{_pct(max_dd)}** |",
                    f"| Max Drawdown (limit) | {_pct(config.max_drawdown_pct)} |",
                    f"| Status | {status} |",
                    "",
                ]
            else:
                lines.append("_Insufficient equity data for drawdown computation._")
        else:
            lines.append("_No equity column found in equity_curve._")
    else:
        lines.append("_No equity curve provided._")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Rule definitions
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Risk Rule Definitions",
        "",
        "| Rule | Description |",
        "| --- | --- |",
        "| max_risk_per_trade_pct | Max portfolio equity risked per trade "
        "(stop-loss distance x position size). |",
        "| max_portfolio_exposure_pct | Max fraction of equity deployed "
        "simultaneously across all open positions. |",
        "| max_drawdown_pct | Drawdown kill-switch: block all new entries "
        "when portfolio drawdown exceeds this threshold. |",
        "| max_concurrent_positions | Hard cap on simultaneously open "
        "positions regardless of exposure fraction. |",
        "",
        "---",
        "",
        "## Caveats",
        "",
        "- Risk engine checks are advisory and do not guarantee "
        "loss prevention in live trading.",
        "- Drawdown kill-switch is evaluated at the start of each "
        "simulated period; intra-bar drawdown is not tracked.",
        "- Regime-aware throttling requires regime detection to be "
        "active (--regime-analysis or --include-regime).",
        "- These thresholds are conservative research defaults; "
        "production trading risk management requires live order "
        "routing, real-time monitoring, and regulatory compliance.",
        "- No live trading. This output must not be used for real capital deployment.",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with "
        "`--enable-risk-management` enabled._",
    ]

    return lines
