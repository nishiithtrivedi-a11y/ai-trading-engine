"""
Portfolio-Level Backtesting.

Runs multiple (symbol, strategy) combinations under a single shared-capital
framework.  Unlike MultiAssetBacktester (which allocates capital independently
per symbol), this module:

  * Respects a ``max_positions`` hard limit on concurrent positions.
  * Selects a strategy *per symbol* (different symbols may use different
    strategies).
  * Optionally integrates the RegimePolicy to drive per-symbol strategy
    selection -- the policy decides which strategy fits the detected regime
    for each symbol.
  * Computes portfolio-level turnover in addition to the standard equity /
    drawdown / Sharpe metrics.
  * Exports research/portfolio_backtest.md and CSV artefacts.

CAPITAL ALLOCATION
------------------
  Default behavior:
    per_symbol_capital = initial_capital / num_active_symbols

  Optional conservative reserve mode:
    per_symbol_capital = initial_capital / max_positions

  Each active symbol runs a full backtest with ``per_symbol_capital`` as its
  initial capital.  The portfolio equity curve is the sum of all per-symbol
  equity curves (aligned on their common date index, forward-filled for gaps).

STRATEGY SELECTION (per symbol)
--------------------------------
  Priority 1: RegimePolicy (when provided)
    -- detect the composite regime from the symbol's OHLCV data.
    -- call select_for_regime(); use its ``preferred`` strategy if available
       and found in strategy_registry.
  Priority 2: Fallback -- the first key in strategy_registry (lexicographic
    sort so the choice is deterministic).

MAX POSITIONS
-------------
  When the number of symbols exceeds max_positions, only the first
  ``max_positions`` symbols (alphabetical order) are backtested.  Remaining
  symbols are skipped and noted in the report.

TURNOVER
--------
  Turnover = sum(entry_value per round-trip trade) / initial_capital.
  A value of 2.0 means the portfolio turned over twice (200%) during the
  test period.

NO LOOKAHEAD
------------
  Regime detection uses only the data available to each symbol's own
  DataHandler.  No future data crosses into the strategy selection step.

PUBLIC API
----------
  PortfolioPosition        Open-position snapshot (dataclass).
  PortfolioTradeRecord     Closed-trade record (dataclass).
  PortfolioBacktestResult  Full result container (dataclass).
  PortfolioBacktester      Main backtesting class.
  generate_portfolio_report(result, output_path, metadata) -> str
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.utils.config import BacktestConfig
from src.utils.logger import setup_logger

logger = setup_logger("portfolio_backtester")

# ---------------------------------------------------------------------------
# Lazy imports (optional dependencies)
# ---------------------------------------------------------------------------

def _load_regime_engine():
    """Lazy-load MarketRegimeEngine to keep the module importable without it."""
    from src.market_intelligence.regime_engine import MarketRegimeEngine  # noqa: F401
    return MarketRegimeEngine


def _load_select_for_regime():
    from src.decision.regime_policy import select_for_regime  # noqa: F401
    return select_for_regime


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PortfolioPosition:
    """Snapshot of one open position within the portfolio simulation."""

    symbol: str
    strategy_name: str
    entry_timestamp: pd.Timestamp
    entry_price: float
    quantity: float
    allocated_capital: float


@dataclass
class PortfolioTradeRecord:
    """Closed-trade record enriched with symbol and strategy context."""

    symbol: str
    strategy_name: str
    entry_timestamp: Any  # pd.Timestamp or str
    exit_timestamp: Any
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    bars_held: int
    fees: float = 0.0
    exit_reason: str = ""


@dataclass
class PortfolioBacktestResult:
    """Complete result of a portfolio-level backtest run."""

    # Capital summary
    initial_capital: float
    final_value: float
    portfolio_return: float          # absolute Rs
    portfolio_return_pct: float      # fractional (0.12 = 12%)

    # Risk/return metrics
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    annualized_return: float

    # Trade statistics
    num_trades: int
    win_rate: float
    profit_factor: float
    turnover: float                  # total entry value / initial_capital

    # Configuration echo
    num_symbols_active: int
    num_symbols_skipped: int
    max_positions: int
    per_symbol_capital: float
    reserve_full_capacity: bool = False
    strategy_selection: dict[str, str] = field(default_factory=dict)  # symbol -> strategy

    # Per-symbol drill-down
    symbol_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Time series
    portfolio_equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    trade_log: pd.DataFrame = field(default_factory=pd.DataFrame)


# ---------------------------------------------------------------------------
# Main backtester class
# ---------------------------------------------------------------------------

class PortfolioBacktester:
    """
    Portfolio-level backtester with shared capital and optional regime policy.

    Parameters
    ----------
    base_config : BacktestConfig
        Base backtest configuration.  ``initial_capital`` is the *total*
        portfolio capital; per-symbol capital is derived from ``max_positions``.
    strategy_registry : dict[str, dict]
        Mapping of strategy short name -> {"class": StrategyClass, "params": {...}}.
        Keys must include at least one entry.
    symbol_to_data : dict[str, DataHandler]
        OHLCV data per symbol.
    max_positions : int
        Maximum concurrent open positions.  Controls capital allocation and
        limits the number of symbols backtested.
    reserve_full_capacity : bool
        When True, per-symbol capital remains ``initial_capital / max_positions``
        even if fewer symbols are active. When False (default), capital is
        allocated across actual active symbols only.
    regime_policy : optional
        A ``RegimePolicy`` instance (from ``src.decision.regime_policy``).
        When provided, each symbol's regime is detected and the policy selects
        the preferred strategy.  Falls back to lexicographic first strategy if
        the regime has no policy entry.
    output_dir : str
        Directory for CSV artefacts.
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        strategy_registry: dict[str, dict[str, Any]],
        symbol_to_data: dict[str, DataHandler],
        max_positions: int = 10,
        regime_policy: Optional[Any] = None,
        output_dir: str = "output/portfolio",
        reserve_full_capacity: bool = False,
    ) -> None:
        if not strategy_registry:
            raise ValueError("strategy_registry cannot be empty.")
        if not symbol_to_data:
            raise ValueError("symbol_to_data cannot be empty.")
        if max_positions < 1:
            raise ValueError("max_positions must be >= 1.")

        self.base_config = base_config
        self.strategy_registry = strategy_registry
        self.symbol_to_data = symbol_to_data
        self.max_positions = max_positions
        self.regime_policy = regime_policy
        self.output_dir = Path(output_dir)
        self.reserve_full_capacity = bool(reserve_full_capacity)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Computed after run()
        self._result: Optional[PortfolioBacktestResult] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> PortfolioBacktestResult:
        """Execute the portfolio backtest.

        Returns
        -------
        PortfolioBacktestResult
            Full portfolio-level result with equity curve and trade log.
        """
        logger.info(
            f"Starting portfolio backtest: {len(self.symbol_to_data)} symbols, "
            f"max_positions={self.max_positions}"
        )

        # Select active symbols (alphabetical for determinism; limit to max_positions)
        all_symbols = sorted(self.symbol_to_data.keys())
        active_symbols = all_symbols[: self.max_positions]
        skipped_symbols = all_symbols[self.max_positions:]

        if skipped_symbols:
            logger.info(
                f"Skipping {len(skipped_symbols)} symbol(s) due to max_positions limit: "
                f"{skipped_symbols}"
            )

        num_active = len(active_symbols)
        allocation_slots = self.max_positions if self.reserve_full_capacity else max(1, num_active)
        per_symbol_capital = float(self.base_config.initial_capital) / allocation_slots

        logger.info(
            f"Active symbols: {num_active}, per-symbol capital: {per_symbol_capital:,.2f}, "
            f"reserve_full_capacity={self.reserve_full_capacity}"
        )

        # Per-symbol results
        symbol_results: dict[str, dict[str, Any]] = {}
        strategy_selection: dict[str, str] = {}
        equity_frames: list[pd.DataFrame] = []
        trade_frames: list[pd.DataFrame] = []

        for symbol in active_symbols:
            data_handler = self.symbol_to_data[symbol]

            # Select strategy
            strategy_name = self._select_strategy_for_symbol(symbol, data_handler)
            strategy_selection[symbol] = strategy_name
            logger.info(f"  {symbol}: strategy={strategy_name}")

            # Run backtest
            run_result = self._run_symbol_backtest(
                symbol=symbol,
                strategy_name=strategy_name,
                capital=per_symbol_capital,
                data_handler=data_handler,
            )

            symbol_results[symbol] = run_result

            # Collect equity curve
            eq = run_result.get("equity_curve", pd.DataFrame())
            if not eq.empty and "equity" in eq.columns:
                eq_copy = eq[["equity"]].rename(columns={"equity": symbol})
                equity_frames.append(eq_copy)

            # Collect trade log
            tl = run_result.get("trade_log", pd.DataFrame())
            if not tl.empty:
                tl = tl.copy()
                tl["symbol"] = symbol
                tl["strategy"] = strategy_name
                trade_frames.append(tl)

        # Aggregate
        portfolio_equity_curve = self._aggregate_equity_curves(
            equity_frames=equity_frames,
            initial_capital=float(self.base_config.initial_capital),
        )
        trade_log = self._aggregate_trade_logs(trade_frames)

        # Portfolio metrics
        metrics = self._compute_portfolio_metrics(
            equity_curve=portfolio_equity_curve,
            trade_log=trade_log,
            initial_capital=float(self.base_config.initial_capital),
        )
        turnover = self._compute_turnover(
            trade_log=trade_log,
            initial_capital=float(self.base_config.initial_capital),
        )

        self._result = PortfolioBacktestResult(
            initial_capital=float(self.base_config.initial_capital),
            final_value=metrics.get("final_value", float(self.base_config.initial_capital)),
            portfolio_return=metrics.get("portfolio_return", 0.0),
            portfolio_return_pct=metrics.get("portfolio_return_pct", 0.0),
            max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
            sortino_ratio=metrics.get("sortino_ratio", 0.0),
            annualized_return=metrics.get("annualized_return", 0.0),
            num_trades=metrics.get("num_trades", 0),
            win_rate=metrics.get("win_rate", 0.0),
            profit_factor=metrics.get("profit_factor", 0.0),
            turnover=turnover,
            num_symbols_active=num_active,
            num_symbols_skipped=len(skipped_symbols),
            max_positions=self.max_positions,
            reserve_full_capacity=self.reserve_full_capacity,
            per_symbol_capital=per_symbol_capital,
            strategy_selection=strategy_selection,
            symbol_results=symbol_results,
            portfolio_equity_curve=portfolio_equity_curve,
            trade_log=trade_log,
        )

        # Export CSV artefacts
        self._export_outputs(self._result)

        logger.info(
            f"Portfolio backtest complete. "
            f"Return: {metrics.get('portfolio_return_pct', 0):.2%}, "
            f"Sharpe: {metrics.get('sharpe_ratio', 0):.4f}, "
            f"MaxDD: {metrics.get('max_drawdown_pct', 0):.2%}"
        )

        return self._result

    # ------------------------------------------------------------------
    # B1: Accept pre-computed per-symbol engine results (avoids re-running)
    # ------------------------------------------------------------------

    def run_from_engine_results(
        self,
        precomputed: dict[str, dict[str, Any]],
    ) -> PortfolioBacktestResult:
        """Build a portfolio result from already-computed per-symbol backtests.

        This method mirrors ``run()`` but skips the per-symbol backtest step,
        consuming ``equity_curve`` and ``trade_log`` DataFrames that were
        produced by the runner's main loop.  Calling this instead of ``run()``
        eliminates the duplicate backtest work when the runner already has
        results available.

        Parameters
        ----------
        precomputed:
            Mapping of symbol -> engine results dict.  Each value must have at
            least the keys returned by ``BacktestEngine.get_results()``:
            ``"metrics"``, ``"equity_curve"`` (DataFrame), ``"trade_log"``
            (DataFrame).  Symbols missing from ``precomputed`` are treated as
            failed and skipped.

        Returns
        -------
        PortfolioBacktestResult
            Identical schema to ``run()`` — all downstream consumers work
            unchanged.
        """
        logger.info(
            f"Portfolio backtest (pre-computed): {len(precomputed)} symbols provided, "
            f"max_positions={self.max_positions}"
        )

        all_symbols = sorted(self.symbol_to_data.keys())
        active_symbols = all_symbols[: self.max_positions]
        skipped_symbols = all_symbols[self.max_positions :]

        if skipped_symbols:
            logger.info(
                f"Skipping {len(skipped_symbols)} symbol(s) due to max_positions limit: "
                f"{skipped_symbols}"
            )

        num_active = len(active_symbols)
        allocation_slots = self.max_positions if self.reserve_full_capacity else max(1, num_active)
        per_symbol_capital = float(self.base_config.initial_capital) / allocation_slots

        symbol_results: dict[str, dict[str, Any]] = {}
        strategy_selection: dict[str, str] = {}
        equity_frames: list[pd.DataFrame] = []
        trade_frames: list[pd.DataFrame] = []

        for symbol in active_symbols:
            data_handler = self.symbol_to_data[symbol]

            # Determine strategy name (same logic as run())
            strategy_name = self._select_strategy_for_symbol(symbol, data_handler)
            strategy_selection[symbol] = strategy_name
            logger.info(f"  {symbol}: strategy={strategy_name} (pre-computed)")

            # Use the pre-computed result when available; fall back to re-running.
            if symbol in precomputed and precomputed[symbol]:
                run_result = precomputed[symbol]
                logger.debug(f"  {symbol}: using pre-computed engine results")
            else:
                logger.warning(
                    f"  {symbol}: no pre-computed result — falling back to live backtest"
                )
                run_result = self._run_symbol_backtest(
                    symbol=symbol,
                    strategy_name=strategy_name,
                    capital=per_symbol_capital,
                    data_handler=data_handler,
                )

            symbol_results[symbol] = run_result

            eq = run_result.get("equity_curve", pd.DataFrame())
            if not eq.empty and "equity" in eq.columns:
                eq_copy = eq[["equity"]].rename(columns={"equity": symbol})
                equity_frames.append(eq_copy)

            tl = run_result.get("trade_log", pd.DataFrame())
            if not tl.empty:
                tl = tl.copy()
                tl["symbol"] = symbol
                tl["strategy"] = strategy_name
                trade_frames.append(tl)

        portfolio_equity_curve = self._aggregate_equity_curves(
            equity_frames=equity_frames,
            initial_capital=float(self.base_config.initial_capital),
        )
        trade_log = self._aggregate_trade_logs(trade_frames)

        metrics = self._compute_portfolio_metrics(
            equity_curve=portfolio_equity_curve,
            trade_log=trade_log,
            initial_capital=float(self.base_config.initial_capital),
        )
        turnover = self._compute_turnover(
            trade_log=trade_log,
            initial_capital=float(self.base_config.initial_capital),
        )

        self._result = PortfolioBacktestResult(
            initial_capital=float(self.base_config.initial_capital),
            final_value=metrics.get("final_value", float(self.base_config.initial_capital)),
            portfolio_return=metrics.get("portfolio_return", 0.0),
            portfolio_return_pct=metrics.get("portfolio_return_pct", 0.0),
            max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
            sortino_ratio=metrics.get("sortino_ratio", 0.0),
            annualized_return=metrics.get("annualized_return", 0.0),
            num_trades=metrics.get("num_trades", 0),
            win_rate=metrics.get("win_rate", 0.0),
            profit_factor=metrics.get("profit_factor", 0.0),
            turnover=turnover,
            num_symbols_active=num_active,
            num_symbols_skipped=len(skipped_symbols),
            max_positions=self.max_positions,
            reserve_full_capacity=self.reserve_full_capacity,
            per_symbol_capital=per_symbol_capital,
            strategy_selection=strategy_selection,
            symbol_results=symbol_results,
            portfolio_equity_curve=portfolio_equity_curve,
            trade_log=trade_log,
        )

        self._export_outputs(self._result)

        logger.info(
            f"Portfolio backtest (pre-computed) complete. "
            f"Return: {metrics.get('portfolio_return_pct', 0):.2%}, "
            f"Sharpe: {metrics.get('sharpe_ratio', 0):.4f}, "
            f"MaxDD: {metrics.get('max_drawdown_pct', 0):.2%}"
        )

        return self._result

    # ------------------------------------------------------------------
    # Strategy selection
    # ------------------------------------------------------------------

    def _select_strategy_for_symbol(
        self,
        symbol: str,
        data_handler: DataHandler,
    ) -> str:
        """Return the strategy name to use for this symbol.

        Priority:
          1. RegimePolicy (if provided) + regime detected from symbol's data.
          2. Lexicographic first key in strategy_registry (deterministic fallback).
        """
        fallback = sorted(self.strategy_registry.keys())[0]

        if self.regime_policy is None:
            return fallback

        # Detect regime
        regime_label = self._detect_symbol_regime(data_handler)
        if regime_label is None:
            return fallback

        # Apply policy
        try:
            select_for_regime = _load_select_for_regime()
            decision = select_for_regime(
                regime_label=regime_label,
                available_strategies=list(self.strategy_registry.keys()),
                policy=self.regime_policy,
            )
            if (
                decision is not None
                and decision.preferred_strategy
                and decision.preferred_strategy in self.strategy_registry
                and decision.should_trade
            ):
                return decision.preferred_strategy
        except Exception as exc:
            logger.warning(
                f"Regime policy lookup failed for {symbol}: {exc}. "
                f"Using fallback strategy '{fallback}'."
            )

        return fallback

    def _detect_symbol_regime(self, data_handler: DataHandler) -> Optional[str]:
        """Detect composite regime from the symbol's OHLCV data.

        Returns the composite regime string (e.g. 'bullish_trending') or None
        if detection fails or data is insufficient.
        """
        try:
            MarketRegimeEngine = _load_regime_engine()
            engine = MarketRegimeEngine()
            snapshot = engine.detect(data_handler.data, symbol="portfolio_symbol")
            regime_val = snapshot.composite_regime.value
            return str(regime_val)
        except Exception as exc:
            logger.debug(f"Regime detection failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Single-symbol backtest runner
    # ------------------------------------------------------------------

    def _run_symbol_backtest(
        self,
        symbol: str,
        strategy_name: str,
        capital: float,
        data_handler: DataHandler,
    ) -> dict[str, Any]:
        """Run a single-symbol backtest and return the raw results dict.

        Uses the existing BacktestEngine unchanged.  Capital is set to the
        per-symbol allocation.

        Returns
        -------
        dict with keys: metrics, equity_curve, trade_log, buy_hold
        """
        reg = self.strategy_registry.get(strategy_name)
        if reg is None:
            logger.warning(
                f"Strategy '{strategy_name}' not in registry for {symbol}. "
                f"Using first available."
            )
            strategy_name = sorted(self.strategy_registry.keys())[0]
            reg = self.strategy_registry[strategy_name]

        config = _clone_config(self.base_config)
        config.initial_capital = capital

        strategy_cls = reg["class"]
        params = reg.get("params", {})

        # Update strategy params in config
        merged_params = dict(config.strategy_params)
        merged_params.update(params)
        config.strategy_params = merged_params

        strategy_instance = strategy_cls()

        try:
            engine = BacktestEngine(config=config, strategy=strategy_instance)
            engine.run(data_handler=copy.deepcopy(data_handler))
            return engine.get_results()
        except Exception as exc:
            logger.error(f"Backtest failed for {symbol}/{strategy_name}: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def _aggregate_equity_curves(
        self,
        equity_frames: list[pd.DataFrame],
        initial_capital: float,
    ) -> pd.DataFrame:
        """Sum per-symbol equity curves into a portfolio equity curve."""
        if not equity_frames:
            return pd.DataFrame()

        combined = pd.concat(equity_frames, axis=1).sort_index()
        combined = combined.ffill().bfill()

        symbol_cols = list(combined.columns)
        combined["portfolio_equity"] = combined[symbol_cols].sum(axis=1)

        combined["portfolio_return_pct"] = (
            combined["portfolio_equity"] / initial_capital - 1.0
        )

        combined["portfolio_peak"] = combined["portfolio_equity"].cummax()
        combined["portfolio_drawdown"] = (
            combined["portfolio_peak"] - combined["portfolio_equity"]
        )
        # Avoid divide-by-zero on peak
        peak_safe = combined["portfolio_peak"].replace(0.0, pd.NA)
        combined["portfolio_drawdown_pct"] = (
            combined["portfolio_drawdown"] / peak_safe
        )

        return combined

    def _aggregate_trade_logs(
        self,
        trade_frames: list[pd.DataFrame],
    ) -> pd.DataFrame:
        """Concatenate per-symbol trade logs into one sorted log."""
        if not trade_frames:
            return pd.DataFrame()

        df = pd.concat(trade_frames, ignore_index=True)

        sort_col = "exit_timestamp" if "exit_timestamp" in df.columns else None
        if sort_col is not None:
            df = df.sort_values(by=sort_col).reset_index(drop=True)

        return df

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _compute_portfolio_metrics(
        self,
        equity_curve: pd.DataFrame,
        trade_log: pd.DataFrame,
        initial_capital: float,
    ) -> dict[str, Any]:
        """Compute portfolio-level performance metrics."""
        if equity_curve.empty or "portfolio_equity" not in equity_curve.columns:
            return {
                "final_value": initial_capital,
                "portfolio_return": 0.0,
                "portfolio_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "annualized_return": 0.0,
                "num_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
            }

        eq = equity_curve["portfolio_equity"]
        final_value = float(eq.iloc[-1])
        total_return = final_value - initial_capital
        total_return_pct = total_return / initial_capital if initial_capital > 0 else 0.0

        max_drawdown_pct = (
            float(equity_curve["portfolio_drawdown_pct"].max())
            if "portfolio_drawdown_pct" in equity_curve.columns
            else 0.0
        )
        if pd.isna(max_drawdown_pct):
            max_drawdown_pct = 0.0

        # Annualized return
        num_periods = len(eq)
        trading_days_per_year = float(
            getattr(self.base_config, "trading_days_per_year", 252)
        )
        if num_periods > 1 and total_return_pct > -1.0:
            annualized_return = (1.0 + total_return_pct) ** (
                trading_days_per_year / num_periods
            ) - 1.0
        else:
            annualized_return = 0.0

        # Sharpe ratio
        sharpe_ratio = self._compute_sharpe(eq, trading_days_per_year)
        sortino_ratio = self._compute_sortino(eq, trading_days_per_year)

        # Trade statistics
        num_trades = len(trade_log) if not trade_log.empty else 0
        win_rate = 0.0
        profit_factor = 0.0

        if not trade_log.empty and "net_pnl" in trade_log.columns:
            winners = trade_log[trade_log["net_pnl"] > 0]
            losers = trade_log[trade_log["net_pnl"] < 0]
            win_rate = (
                len(winners) / len(trade_log) if len(trade_log) > 0 else 0.0
            )
            gross_profit = float(winners["net_pnl"].sum()) if not winners.empty else 0.0
            gross_loss = abs(float(losers["net_pnl"].sum())) if not losers.empty else 0.0
            profit_factor = (
                gross_profit / gross_loss if gross_loss > 0 else float("inf")
            )

        return {
            "final_value": final_value,
            "portfolio_return": total_return,
            "portfolio_return_pct": total_return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "annualized_return": annualized_return,
            "num_trades": num_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
        }

    @staticmethod
    def _compute_sharpe(
        equity: pd.Series,
        trading_days_per_year: float = 252.0,
        risk_free_rate: float = 0.0,
    ) -> float:
        """Annualised Sharpe ratio from equity series."""
        if len(equity) < 2:
            return 0.0
        returns = equity.pct_change().dropna()
        std = returns.std()
        if std == 0.0 or pd.isna(std):
            return 0.0
        daily_rf = risk_free_rate / trading_days_per_year
        excess = returns - daily_rf
        return float((excess.mean() / excess.std()) * np.sqrt(trading_days_per_year))

    @staticmethod
    def _compute_sortino(
        equity: pd.Series,
        trading_days_per_year: float = 252.0,
        risk_free_rate: float = 0.0,
    ) -> float:
        """Annualised Sortino ratio (downside-only volatility) from equity series."""
        if len(equity) < 2:
            return 0.0
        returns = equity.pct_change().dropna()
        daily_rf = risk_free_rate / trading_days_per_year
        excess = returns - daily_rf
        downside = excess[excess < 0]
        if len(downside) == 0:
            return float("inf") if excess.mean() > 0 else 0.0
        ds_std = downside.std()
        if ds_std == 0.0 or pd.isna(ds_std):
            return 0.0
        return float((excess.mean() / ds_std) * np.sqrt(trading_days_per_year))

    @staticmethod
    def _compute_turnover(
        trade_log: pd.DataFrame,
        initial_capital: float,
    ) -> float:
        """Compute portfolio turnover.

        Turnover = sum of entry values (quantity * entry_price) / initial_capital.

        A value of 1.0 means the entire portfolio was turned over once.
        """
        if trade_log.empty or initial_capital <= 0:
            return 0.0

        if "entry_price" in trade_log.columns and "quantity" in trade_log.columns:
            entry_values = (
                trade_log["entry_price"].fillna(0.0) *
                trade_log["quantity"].fillna(0.0)
            )
            total_entry_value = float(entry_values.sum())
            return total_entry_value / initial_capital

        return 0.0

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_outputs(self, result: PortfolioBacktestResult) -> None:
        """Write CSV artefacts to output_dir."""
        if not result.portfolio_equity_curve.empty:
            result.portfolio_equity_curve.to_csv(
                self.output_dir / "portfolio_equity_curve.csv"
            )
            logger.info(f"Exported portfolio equity curve to {self.output_dir}")

        if not result.trade_log.empty:
            result.trade_log.to_csv(
                self.output_dir / "portfolio_trades.csv",
                index=False,
            )
            logger.info(f"Exported {len(result.trade_log)} trades to {self.output_dir}")

        # Per-symbol summary
        rows = []
        for symbol, sym_result in result.symbol_results.items():
            m = sym_result.get("metrics", {})
            row = {
                "symbol": symbol,
                "strategy": result.strategy_selection.get(symbol, "unknown"),
            }
            row.update(m)
            rows.append(row)

        if rows:
            pd.DataFrame(rows).to_csv(
                self.output_dir / "portfolio_symbol_summary.csv",
                index=False,
            )


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_portfolio_report(
    result: PortfolioBacktestResult,
    output_path: Optional[str | Path] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Generate and save the portfolio backtest markdown report.

    Parameters
    ----------
    result : PortfolioBacktestResult
        Output of ``PortfolioBacktester.run()``.
    output_path : str or Path, optional
        Where to write the markdown file.  Defaults to
        ``research/portfolio_backtest.md``.
    metadata : dict, optional
        Extra run context (provider, interval, date range, etc.).

    Returns
    -------
    str
        Full markdown content of the report.
    """
    output_path = (
        Path(output_path)
        if output_path
        else Path("research") / "portfolio_backtest.md"
    )
    metadata = dict(metadata) if metadata else {}

    lines = _build_portfolio_report_lines(result, metadata)
    content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Portfolio backtest report written to {output_path}")

    return content


# ---------------------------------------------------------------------------
# Report helpers (ASCII-only for Windows cp1252 compatibility)
# ---------------------------------------------------------------------------

def _fmt_val(v: Any) -> str:
    """Format a value for markdown table cells."""
    if v is None or (isinstance(v, float) and v != v):
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, int):
        return str(v)
    return str(v)


def _df_to_md(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a Markdown table string."""
    if df.empty:
        return "_No data._"

    col_names = list(df.columns)
    header = "| " + " | ".join(str(c) for c in col_names) + " |"
    sep = "| " + " | ".join("---" for _ in col_names) + " |"
    rows = [
        "| " + " | ".join(_fmt_val(v) for v in row) + " |"
        for row in df.itertuples(index=False, name=None)
    ]
    return "\n".join([header, sep] + rows)


def _pct(v: float) -> str:
    """Format a fraction as a percentage string."""
    return f"{v * 100.0:.2f}%"


def _build_portfolio_report_lines(
    result: PortfolioBacktestResult,
    metadata: dict[str, Any],
) -> list[str]:
    """Assemble all markdown sections for the portfolio backtest report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        "# Portfolio-Level Backtest Report",
        "",
        "## Run Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
        f"| Initial Capital | {result.initial_capital:,.2f} |",
        f"| Max Positions | {result.max_positions} |",
        f"| Reserve Full Capacity | {result.reserve_full_capacity} |",
        f"| Per-Symbol Capital | {result.per_symbol_capital:,.2f} |",
        f"| Active Symbols | {result.num_symbols_active} |",
        f"| Skipped Symbols (>max_positions) | {result.num_symbols_skipped} |",
    ]
    for key, val in metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Portfolio performance
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Portfolio Performance",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Initial Capital | {result.initial_capital:,.2f} |",
        f"| Final Value | {result.final_value:,.2f} |",
        f"| Total Return | **{_pct(result.portfolio_return_pct)}** |",
        f"| Annualized Return | {_pct(result.annualized_return)} |",
        f"| Max Drawdown | {_pct(result.max_drawdown_pct)} |",
        f"| Sharpe Ratio | {result.sharpe_ratio:.4f} |",
        f"| Sortino Ratio | {result.sortino_ratio:.4f} |",
        f"| Total Trades | {result.num_trades} |",
        f"| Win Rate | {_pct(result.win_rate)} |",
        f"| Profit Factor | {result.profit_factor:.4f} |",
        f"| Turnover | {result.turnover:.4f}x |",
        "",
        "---",
    ]

    # ------------------------------------------------------------------
    # Strategy selection
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Strategy Selection Per Symbol",
        "",
        "> Strategy assigned to each symbol (via regime policy if available,",
        "> else lexicographic fallback from strategy_registry).",
        "",
    ]
    if result.strategy_selection:
        sel_rows = [
            {"symbol": sym, "strategy": strat}
            for sym, strat in sorted(result.strategy_selection.items())
        ]
        lines.append(_df_to_md(pd.DataFrame(sel_rows)))
    else:
        lines.append("_No strategy selection data._")
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Per-symbol drill-down
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Per-Symbol Results",
        "",
        "> Each row is one symbol's independent backtest run.",
        "",
    ]
    sym_rows = []
    for symbol in sorted(result.symbol_results.keys()):
        m = result.symbol_results[symbol].get("metrics", {})
        sym_rows.append({
            "symbol": symbol,
            "strategy": result.strategy_selection.get(symbol, "N/A"),
            "final_value": round(m.get("final_value", 0.0), 2),
            "total_return_pct": round(m.get("total_return_pct", 0.0) * 100, 2),
            "sharpe_ratio": round(m.get("sharpe_ratio", 0.0), 4),
            "max_drawdown_pct": round(m.get("max_drawdown_pct", 0.0) * 100, 2),
            "num_trades": m.get("num_trades", 0),
            "win_rate": round(m.get("win_rate", 0.0) * 100, 2),
        })

    if sym_rows:
        df_sym = pd.DataFrame(sym_rows)
        lines.append(_df_to_md(df_sym))
    else:
        lines.append("_No per-symbol data._")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Equity curve snippet (first / last 5 rows)
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Equity Curve (snapshot)",
        "",
        "> Full curve exported to output/portfolio/portfolio_equity_curve.csv",
        "",
    ]
    eq = result.portfolio_equity_curve
    if not eq.empty and "portfolio_equity" in eq.columns:
        snapshot = eq[["portfolio_equity", "portfolio_return_pct"]].round(4)
        n = len(snapshot)
        if n > 10:
            snap = pd.concat([snapshot.head(5), snapshot.tail(5)])
            lines.append(f"_Showing first 5 and last 5 of {n} rows._")
            lines.append("")
        else:
            snap = snapshot
        lines.append(_df_to_md(snap.reset_index()))
    else:
        lines.append("_No equity curve data._")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Conclusions
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Key Conclusions",
        "",
        f"- **Portfolio return: {_pct(result.portfolio_return_pct)}** "
        f"({result.num_symbols_active} symbols, {result.num_trades} trades).",
        f"- Max drawdown: {_pct(result.max_drawdown_pct)}; "
        f"Sharpe: {result.sharpe_ratio:.4f}.",
        f"- Capital deployed: {result.per_symbol_capital:,.2f} per position "
        f"(equal-weight, {result.max_positions} max positions, "
        f"reserve_full_capacity={result.reserve_full_capacity}).",
        f"- Portfolio turnover: {result.turnover:.2f}x over the test period.",
    ]
    if result.num_symbols_skipped > 0:
        lines.append(
            f"- {result.num_symbols_skipped} symbol(s) skipped due to "
            f"max_positions={result.max_positions} limit."
        )

    lines += [
        "",
        "---",
        "",
        "## Caveats",
        "",
        "- Each symbol is backtested independently; intra-day cross-symbol "
        "capital constraints are not modelled.",
        "- Equal-weight allocation within max_positions; risk-parity or "
        "momentum-weighted sizing not implemented.",
        "- Regime policy (when used) selects strategy from historical "
        "regime-performance data; past relationships may not persist.",
        "- No live trading. Results must not be used for real capital deployment.",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with "
        "`--portfolio-backtest` enabled._",
    ]

    return lines


# ---------------------------------------------------------------------------
# Config clone utility (mirrors multi_asset_backtester.py)
# ---------------------------------------------------------------------------

def _clone_config(config: BacktestConfig) -> BacktestConfig:
    if hasattr(config, "model_copy"):
        return config.model_copy(deep=True)
    if hasattr(config, "copy"):
        try:
            return config.copy(deep=True)
        except TypeError:
            return config.copy()
    return copy.deepcopy(config)
