"""
Regime-Driven Strategy Selection Policy.

Converts historical regime research into a deterministic policy layer that
answers, for each detected market regime:

  - Which strategy is *preferred* (best historical risk-adjusted return)?
  - Which strategies are *allowed* (acceptable performance threshold)?
  - Which strategies are *suppressed* (materially underperforming)?
  - Should trading occur at all in this regime?

PUBLIC API
----------
  RegimePolicyEntry      Immutable policy record for one regime.
  RegimePolicy           Container for all per-regime entries; JSON-serialisable.
  RegimePolicyBuilder    Builds a RegimePolicy from analyze_by_regime() output.
  RegimePolicyDecision   Lightweight runtime result from select_for_regime().
  select_for_regime()    Runtime hook: given a detected regime + available
                         strategies, return a RegimePolicyDecision.

POLICY CONSTRUCTION THRESHOLDS (all documented and configurable)
----------------------------------------------------------------
  MIN_RUN_COUNT            = 3      Minimum backtest runs for a strategy to be
                                    considered.  Strategies with fewer samples
                                    are treated as insufficient data and excluded
                                    from allowed/preferred lists.

  SHARPE_PREFERRED_MIN     = 0.0    Preferred strategy must have mean_sharpe >= 0
                                    (break-even risk-adjusted return or better).

  SHARPE_ALLOWED_MIN       = -0.25  Allowed strategies must have mean_sharpe >=
                                    -0.25.  Strategies between -0.25 and 0 are
                                    tolerated but not preferred.

  SHARPE_SUPPRESSED_BELOW  = -0.5   Strategies with mean_sharpe < -0.5 are
                                    flagged as suppressed (materially bad).

  POS_RETURN_RATE_MIN      = 0.25   Allowed strategies must show a positive
                                    total-return in at least 25% of runs.

  NO_TRADE_SHARPE_MAX      = -0.25  If ALL eligible strategies have mean_sharpe
                                    below this, set should_trade = False.

  NO_TRADE_POS_RATE_MAX    = 0.35   If ALL eligible strategies also have
                                    positive_return_rate below this, the
                                    no-trade condition is confirmed.

  RISK_OFF_AUTO_NO_TRADE   = True   risk_off regime always produces should_trade
                                    = False unless at least one strategy
                                    independently clears SHARPE_PREFERRED_MIN
                                    and MIN_RUN_COUNT.

RANKING METHODOLOGY
-------------------
Within each regime, strategies are sorted identically to analyze_by_regime():
  1. mean_sharpe     descending  (risk-adjusted primary)
  2. mean_return     descending  (raw return secondary)
  3. mean_drawdown   descending  (stored as negative fraction;
                                  closer to 0 = smaller drawdown = better)

Ties at the same float value are broken by strategy name alphabetically to
ensure fully deterministic output regardless of input row order.

LIMITATIONS (documented caveats)
---------------------------------
  - Policy is derived from historical backtests; past regime performance
    does not guarantee future results.
  - Thresholds are conservative and intentionally simple for v1.
  - Sample sizes from a typical 5-20 symbol research run are small; treat
    policy decisions as directional guidance, not statistical certainty.
  - No machine learning; all rules are explicit and auditable.
  - Not wired into live order execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Module-level threshold constants  (all documented in module docstring)
# ---------------------------------------------------------------------------

MIN_RUN_COUNT: int          = 3
SHARPE_PREFERRED_MIN: float = 0.0
SHARPE_ALLOWED_MIN: float   = -0.25
SHARPE_SUPPRESSED_BELOW: float = -0.5
POS_RETURN_RATE_MIN: float  = 0.25
NO_TRADE_SHARPE_MAX: float  = -0.25
NO_TRADE_POS_RATE_MAX: float = 0.35
RISK_OFF_AUTO_NO_TRADE: bool = True


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RegimePolicyEntry:
    """
    Immutable policy record for one market regime.

    Fields
    ------
    regime_label       : str
        CompositeRegime value string (e.g. ``"bullish_trending"``).
    preferred_strategy : str or None
        Top-ranked strategy that cleared all quality thresholds.  None when
        no strategy meets the preferred bar.
    ranked_strategies  : list[str]
        All strategies observed in this regime, sorted best-to-worst by
        (mean_sharpe DESC, mean_return DESC, mean_drawdown DESC).
    allowed_strategies : list[str]
        Strategies that passed both run-count and performance thresholds.
    suppressed_strategies : list[str]
        Strategies present in this regime but materially underperforming.
    should_trade       : bool
        False when trading in this regime is inadvisable based on all
        strategies' historical performance.
    rationale          : str
        Human-readable explanation of the policy decision.
    source_metrics     : dict[str, Any]
        Snapshot of the aggregated metrics that drove this entry.
    """
    regime_label: str
    preferred_strategy: Optional[str]
    ranked_strategies: list[str]
    allowed_strategies: list[str]
    suppressed_strategies: list[str]
    should_trade: bool
    rationale: str
    source_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_label":           self.regime_label,
            "preferred_strategy":     self.preferred_strategy,
            "ranked_strategies":      list(self.ranked_strategies),
            "allowed_strategies":     list(self.allowed_strategies),
            "suppressed_strategies":  list(self.suppressed_strategies),
            "should_trade":           self.should_trade,
            "rationale":              self.rationale,
            "source_metrics":         dict(self.source_metrics),
        }


@dataclass
class RegimePolicy:
    """
    Container for the full set of per-regime policy entries.

    Attributes
    ----------
    entries : dict[str, RegimePolicyEntry]
        Keyed by regime_label string; alphabetically ordered.
    generated_at : str
        ISO-format timestamp of when the policy was built.
    source_description : str
        Free-text description of the data that drove the policy.
    metadata : dict[str, Any]
        Arbitrary extra context (symbols_tested, strategies, etc.).
    """
    entries: dict[str, RegimePolicyEntry] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    source_description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, regime_label: str) -> Optional[RegimePolicyEntry]:
        """Return the policy entry for a regime, or None if not found."""
        return self.entries.get(regime_label)

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, regime_label: str) -> bool:
        return regime_label in self.entries

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at":       self.generated_at,
            "source_description": self.source_description,
            "metadata":           dict(self.metadata),
            "thresholds": {
                "MIN_RUN_COUNT":           MIN_RUN_COUNT,
                "SHARPE_PREFERRED_MIN":    SHARPE_PREFERRED_MIN,
                "SHARPE_ALLOWED_MIN":      SHARPE_ALLOWED_MIN,
                "SHARPE_SUPPRESSED_BELOW": SHARPE_SUPPRESSED_BELOW,
                "POS_RETURN_RATE_MIN":     POS_RETURN_RATE_MIN,
                "NO_TRADE_SHARPE_MAX":     NO_TRADE_SHARPE_MAX,
                "NO_TRADE_POS_RATE_MAX":   NO_TRADE_POS_RATE_MAX,
                "RISK_OFF_AUTO_NO_TRADE":  RISK_OFF_AUTO_NO_TRADE,
            },
            "regimes": {
                label: entry.to_dict()
                for label, entry in sorted(self.entries.items())
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise the policy to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimePolicy":
        """Reconstruct a RegimePolicy from a dict (e.g. loaded from JSON)."""
        entries: dict[str, RegimePolicyEntry] = {}
        for label, raw in data.get("regimes", {}).items():
            entries[label] = RegimePolicyEntry(
                regime_label=raw["regime_label"],
                preferred_strategy=raw.get("preferred_strategy"),
                ranked_strategies=list(raw.get("ranked_strategies", [])),
                allowed_strategies=list(raw.get("allowed_strategies", [])),
                suppressed_strategies=list(raw.get("suppressed_strategies", [])),
                should_trade=bool(raw.get("should_trade", True)),
                rationale=str(raw.get("rationale", "")),
                source_metrics=dict(raw.get("source_metrics", {})),
            )
        return cls(
            entries=entries,
            generated_at=data.get("generated_at", ""),
            source_description=data.get("source_description", ""),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def load_json(cls, path: str | Path) -> "RegimePolicy":
        """Load a RegimePolicy from a JSON file written by save_json()."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Regime policy file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save_json(self, path: str | Path) -> Path:
        """Write the policy to a JSON file.  Parent directories are created."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


@dataclass
class RegimePolicyDecision:
    """
    Lightweight result returned by :func:`select_for_regime`.

    Intended for use at research or paper-trading runtime when a regime
    snapshot is available and the engine needs to select a strategy.

    Attributes
    ----------
    detected_regime    : str
        The CompositeRegime value string from the live/research snapshot.
    preferred_strategy : str or None
        Best historical strategy for this regime, or None.
    allowed_strategies : list[str]
        Strategies that passed quality thresholds AND are available.
    should_trade       : bool
        False when trading is inadvisable in this regime.
    explanation        : str
        Human-readable rationale string for logging / reporting.
    policy_found       : bool
        True when a matching RegimePolicyEntry was found; False means the
        decision was produced from a fallback (no historical data).
    """
    detected_regime: str
    preferred_strategy: Optional[str]
    allowed_strategies: list[str]
    should_trade: bool
    explanation: str
    policy_found: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_regime":    self.detected_regime,
            "preferred_strategy": self.preferred_strategy,
            "allowed_strategies": list(self.allowed_strategies),
            "should_trade":       self.should_trade,
            "explanation":        self.explanation,
            "policy_found":       self.policy_found,
        }


# ---------------------------------------------------------------------------
# Policy builder
# ---------------------------------------------------------------------------

class RegimePolicyBuilder:
    """
    Build a RegimePolicy from the aggregated regime analysis DataFrame.

    Parameters
    ----------
    min_run_count : int
        Minimum backtest-run count for a strategy to be considered.
        Default: ``MIN_RUN_COUNT`` (3).
    sharpe_preferred_min : float
        mean_sharpe threshold for a strategy to be *preferred*.
        Default: ``SHARPE_PREFERRED_MIN`` (0.0).
    sharpe_allowed_min : float
        mean_sharpe threshold for a strategy to be *allowed*.
        Default: ``SHARPE_ALLOWED_MIN`` (-0.25).
    sharpe_suppressed_below : float
        mean_sharpe below which a strategy is *suppressed*.
        Default: ``SHARPE_SUPPRESSED_BELOW`` (-0.5).
    pos_return_rate_min : float
        positive_return_rate threshold for *allowed* strategies.
        Default: ``POS_RETURN_RATE_MIN`` (0.25).
    no_trade_sharpe_max : float
        If ALL strategies have mean_sharpe below this, should_trade = False.
        Default: ``NO_TRADE_SHARPE_MAX`` (-0.25).
    no_trade_pos_rate_max : float
        Secondary condition for no-trade (all pos_return_rate below this).
        Default: ``NO_TRADE_POS_RATE_MAX`` (0.35).
    risk_off_auto_no_trade : bool
        If True, risk_off regime automatically sets should_trade = False
        unless at least one strategy clears sharpe_preferred_min and
        min_run_count.  Default: ``RISK_OFF_AUTO_NO_TRADE`` (True).
    """

    def __init__(
        self,
        *,
        min_run_count: int             = MIN_RUN_COUNT,
        sharpe_preferred_min: float    = SHARPE_PREFERRED_MIN,
        sharpe_allowed_min: float      = SHARPE_ALLOWED_MIN,
        sharpe_suppressed_below: float = SHARPE_SUPPRESSED_BELOW,
        pos_return_rate_min: float     = POS_RETURN_RATE_MIN,
        no_trade_sharpe_max: float     = NO_TRADE_SHARPE_MAX,
        no_trade_pos_rate_max: float   = NO_TRADE_POS_RATE_MAX,
        risk_off_auto_no_trade: bool   = RISK_OFF_AUTO_NO_TRADE,
    ) -> None:
        self._min_run_count            = int(min_run_count)
        self._sharpe_preferred_min     = float(sharpe_preferred_min)
        self._sharpe_allowed_min       = float(sharpe_allowed_min)
        self._sharpe_suppressed_below  = float(sharpe_suppressed_below)
        self._pos_return_rate_min      = float(pos_return_rate_min)
        self._no_trade_sharpe_max      = float(no_trade_sharpe_max)
        self._no_trade_pos_rate_max    = float(no_trade_pos_rate_max)
        self._risk_off_auto_no_trade   = bool(risk_off_auto_no_trade)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def build(
        self,
        agg_df: pd.DataFrame,
        *,
        source_description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> RegimePolicy:
        """
        Build and return a :class:`RegimePolicy` from aggregated data.

        Parameters
        ----------
        agg_df : pd.DataFrame
            Output of :func:`src.research.regime_analysis.analyze_by_regime`.
            Must contain ``regime_label`` and ``strategy`` columns.
        source_description : str
            Free-text description embedded in the policy artifact.
        metadata : dict, optional
            Extra context (symbols_tested, interval, etc.).

        Returns
        -------
        RegimePolicy
            Fully populated policy with one entry per regime observed.

        Raises
        ------
        TypeError
            If ``agg_df`` is not a DataFrame.
        ValueError
            If required columns are missing.
        """
        self._validate_agg_df(agg_df)

        entries: dict[str, RegimePolicyEntry] = {}
        for regime_label in sorted(agg_df["regime_label"].unique()):
            regime_df = agg_df[agg_df["regime_label"] == regime_label].copy()
            entry = self._build_entry(regime_label, regime_df)
            entries[regime_label] = entry

        return RegimePolicy(
            entries=entries,
            generated_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            source_description=source_description or "Built by RegimePolicyBuilder",
            metadata=dict(metadata) if metadata else {},
        )

    # ------------------------------------------------------------------
    # Private: entry construction
    # ------------------------------------------------------------------

    def _build_entry(self, regime_label: str, regime_df: pd.DataFrame) -> RegimePolicyEntry:
        """Build one RegimePolicyEntry for a single regime."""
        # Sort rows deterministically (same methodology as rank_strategies_by_regime)
        regime_df = self._sort_strategies(regime_df)

        # Collect per-strategy records for analysis
        records = self._extract_records(regime_df)

        # Determine ranked list (all strategies, best-first)
        ranked_strategies = [r["strategy"] for r in records]

        # Eligible records: only those with sufficient sample size
        eligible = [r for r in records if r["run_count"] >= self._min_run_count]

        # ------------------------------------------------------------------
        # Allowed strategies
        # ------------------------------------------------------------------
        allowed_strategies = [
            r["strategy"] for r in eligible
            if r["mean_sharpe"] >= self._sharpe_allowed_min
            and r["pos_return_rate"] >= self._pos_return_rate_min
        ]

        # ------------------------------------------------------------------
        # Suppressed strategies (eligible but materially underperforming)
        # ------------------------------------------------------------------
        suppressed_strategies = [
            r["strategy"] for r in eligible
            if r["mean_sharpe"] < self._sharpe_suppressed_below
        ]

        # ------------------------------------------------------------------
        # Preferred strategy (top eligible that clears preferred threshold)
        # ------------------------------------------------------------------
        preferred_strategy: Optional[str] = None
        for r in eligible:
            if r["mean_sharpe"] >= self._sharpe_preferred_min:
                preferred_strategy = r["strategy"]
                break  # already sorted best-first

        # ------------------------------------------------------------------
        # No-trade determination
        # ------------------------------------------------------------------
        should_trade, rationale = self._determine_should_trade(
            regime_label=regime_label,
            eligible=eligible,
            allowed_strategies=allowed_strategies,
            preferred_strategy=preferred_strategy,
            ranked_strategies=ranked_strategies,
        )

        # ------------------------------------------------------------------
        # Source metrics snapshot (for auditability)
        # ------------------------------------------------------------------
        source_metrics: dict[str, Any] = {}
        for r in records:
            source_metrics[r["strategy"]] = {
                k: v for k, v in r.items() if k != "strategy"
            }

        return RegimePolicyEntry(
            regime_label=regime_label,
            preferred_strategy=preferred_strategy,
            ranked_strategies=ranked_strategies,
            allowed_strategies=allowed_strategies,
            suppressed_strategies=suppressed_strategies,
            should_trade=should_trade,
            rationale=rationale,
            source_metrics=source_metrics,
        )

    def _determine_should_trade(
        self,
        *,
        regime_label: str,
        eligible: list[dict[str, Any]],
        allowed_strategies: list[str],
        preferred_strategy: Optional[str],
        ranked_strategies: list[str],
    ) -> tuple[bool, str]:
        """Return (should_trade, rationale) for this regime."""

        # Case 1: No eligible records at all (insufficient data)
        if not eligible:
            return (
                True,
                f"No strategies had >= {self._min_run_count} runs in {regime_label!r}; "
                f"trading not blocked but policy has insufficient data to guide selection.",
            )

        # Case 2: risk_off auto no-trade
        if self._risk_off_auto_no_trade and regime_label == "risk_off":
            if preferred_strategy is None:
                return (
                    False,
                    f"risk_off regime: all strategies have mean_sharpe < "
                    f"{self._sharpe_preferred_min:.2f}; trading suppressed. "
                    f"Ranked: {', '.join(ranked_strategies) or 'none'}.",
                )
            # A strategy did clear the preferred threshold — allow it
            return (
                True,
                f"risk_off regime but {preferred_strategy!r} cleared "
                f"mean_sharpe >= {self._sharpe_preferred_min:.2f}; "
                f"trading conditionally allowed with {preferred_strategy!r} only.",
            )

        # Case 3: Universal no-trade — all eligible strategies are clearly bad
        all_sharpe_bad = all(
            r["mean_sharpe"] < self._no_trade_sharpe_max for r in eligible
        )
        all_pos_rate_bad = all(
            r["pos_return_rate"] < self._no_trade_pos_rate_max for r in eligible
        )
        if all_sharpe_bad and all_pos_rate_bad:
            worst_sharpe = min(r["mean_sharpe"] for r in eligible)
            return (
                False,
                f"{regime_label!r}: all {len(eligible)} eligible strategies have "
                f"mean_sharpe < {self._no_trade_sharpe_max:.2f} (worst: {worst_sharpe:.4f}) "
                f"and positive_return_rate < {self._no_trade_pos_rate_max:.2f}; "
                f"trading suppressed.",
            )

        # Case 4: At least some strategies allowed
        if allowed_strategies:
            pref_txt = (
                f"preferred = {preferred_strategy!r}"
                if preferred_strategy
                else "no preferred strategy meets quality threshold"
            )
            return (
                True,
                f"{regime_label!r}: {len(allowed_strategies)} of {len(eligible)} "
                f"eligible strategies are allowed; {pref_txt}.",
            )

        # Case 5: No strategy passes allowed threshold but not all are clearly bad
        return (
            True,
            f"{regime_label!r}: no strategy fully clears allowed thresholds "
            f"(sharpe >= {self._sharpe_allowed_min:.2f} and "
            f"positive_return_rate >= {self._pos_return_rate_min:.2f}); "
            f"trading not blocked but proceed with caution.",
        )

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_strategies(regime_df: pd.DataFrame) -> pd.DataFrame:
        """Sort strategies: mean_sharpe DESC, mean_return DESC, mean_drawdown DESC,
        then strategy name ASC for deterministic tie-breaking."""
        sort_cols: list[str] = []
        sort_asc:  list[bool] = []
        for col, ascending in [
            ("mean_sharpe",   False),
            ("mean_return",   False),
            ("mean_drawdown", False),
            ("strategy",      True),   # alphabetical tie-break
        ]:
            if col in regime_df.columns:
                sort_cols.append(col)
                sort_asc.append(ascending)

        if sort_cols:
            regime_df = regime_df.sort_values(sort_cols, ascending=sort_asc)
        return regime_df.reset_index(drop=True)

    @staticmethod
    def _extract_records(regime_df: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Convert each strategy row into a normalised dict with safe defaults.

        All numeric fields default to NaN-safe fallbacks so downstream logic
        does not need to guard against missing columns.
        """
        records: list[dict[str, Any]] = []
        for _, row in regime_df.iterrows():
            run_count   = int(row.get("run_count", 0) or 0)
            mean_sharpe = float(row.get("mean_sharpe", float("-inf")) or float("-inf"))
            mean_return = float(row.get("mean_return", float("-inf")) or float("-inf"))
            mean_drawdown = float(row.get("mean_drawdown", 0.0) or 0.0)
            pos_return_rate = float(row.get("positive_return_rate", 0.0) or 0.0)
            median_sharpe   = float(row.get("median_sharpe", float("-inf")) or float("-inf"))
            total_trades    = int(row.get("total_trades", 0) or 0)
            mean_win_rate   = float(row.get("mean_win_rate", float("nan")) or float("nan"))
            records.append({
                "strategy":         str(row["strategy"]),
                "run_count":        run_count,
                "mean_sharpe":      mean_sharpe,
                "mean_return":      mean_return,
                "mean_drawdown":    mean_drawdown,
                "pos_return_rate":  pos_return_rate,
                "median_sharpe":    median_sharpe,
                "total_trades":     total_trades,
                "mean_win_rate":    mean_win_rate,
            })
        return records

    @staticmethod
    def _validate_agg_df(agg_df: pd.DataFrame) -> None:
        if not isinstance(agg_df, pd.DataFrame):
            raise TypeError(
                f"agg_df must be a pandas DataFrame; got {type(agg_df)}. "
                "Pass the output of analyze_by_regime()."
            )
        required = {"regime_label", "strategy"}
        missing = required - set(agg_df.columns)
        if missing:
            raise ValueError(
                f"agg_df is missing required columns: {sorted(missing)}. "
                "Pass the output of analyze_by_regime()."
            )


# ---------------------------------------------------------------------------
# Runtime hook
# ---------------------------------------------------------------------------

def select_for_regime(
    regime_label: str,
    available_strategies: list[str],
    policy: RegimePolicy,
) -> RegimePolicyDecision:
    """
    Given a detected regime and a list of available strategies, return a
    :class:`RegimePolicyDecision` from the pre-built policy.

    This is a lightweight, stateless runtime lookup.  It does not re-run
    any analysis; it merely intersects the policy's allowed/preferred lists
    with the caller's available strategies.

    Parameters
    ----------
    regime_label : str
        CompositeRegime value string (e.g. ``"bullish_trending"``).
    available_strategies : list[str]
        Strategy short names available to the caller
        (e.g. ``["sma", "rsi", "breakout"]``).
    policy : RegimePolicy
        Pre-built policy from :class:`RegimePolicyBuilder`.

    Returns
    -------
    RegimePolicyDecision
        Always returns a decision object; never raises for unknown regimes
        (uses a conservative fallback instead).
    """
    if not isinstance(policy, RegimePolicy):
        raise TypeError(f"policy must be a RegimePolicy; got {type(policy)}")

    available_set = set(available_strategies)
    entry = policy.get(regime_label)

    if entry is None:
        # No historical data for this regime — conservative fallback
        return RegimePolicyDecision(
            detected_regime=regime_label,
            preferred_strategy=None,
            allowed_strategies=sorted(available_set),
            should_trade=True,
            explanation=(
                f"No policy entry for regime {regime_label!r}; "
                f"returning all available strategies with no preference."
            ),
            policy_found=False,
        )

    # Intersect policy lists with what the caller actually has
    allowed = [s for s in entry.allowed_strategies if s in available_set]
    preferred = entry.preferred_strategy if entry.preferred_strategy in available_set else None

    # If policy says no-trade, honour that regardless of available strategies
    if not entry.should_trade:
        return RegimePolicyDecision(
            detected_regime=regime_label,
            preferred_strategy=None,
            allowed_strategies=[],
            should_trade=False,
            explanation=entry.rationale,
            policy_found=True,
        )

    # Build explanation
    if preferred:
        explanation = (
            f"Regime {regime_label!r}: preferred = {preferred!r}; "
            f"allowed = {allowed}. {entry.rationale}"
        )
    elif allowed:
        explanation = (
            f"Regime {regime_label!r}: no preferred strategy available; "
            f"allowed = {allowed}. {entry.rationale}"
        )
    else:
        explanation = (
            f"Regime {regime_label!r}: no preferred or allowed strategy "
            f"from {sorted(available_set)} found in policy. "
            f"Policy allowed = {entry.allowed_strategies}. "
            "Proceeding without regime guidance."
        )

    return RegimePolicyDecision(
        detected_regime=regime_label,
        preferred_strategy=preferred,
        allowed_strategies=allowed,
        should_trade=entry.should_trade,
        explanation=explanation,
        policy_found=True,
    )


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_policy_report(
    policy: RegimePolicy,
    output_path: Optional[str | Path] = None,
) -> str:
    """
    Generate a human-readable markdown summary of the policy.

    Parameters
    ----------
    policy : RegimePolicy
        Built by :class:`RegimePolicyBuilder`.
    output_path : str or Path, optional
        Where to save the markdown.  Defaults to
        ``research/regime_policy.md``.

    Returns
    -------
    str
        Markdown content (also written to ``output_path`` as side-effect).
    """
    if not isinstance(policy, RegimePolicy):
        raise TypeError(f"policy must be a RegimePolicy; got {type(policy)}")

    output_path = (
        Path(output_path) if output_path else Path("research") / "regime_policy.md"
    )

    lines = _build_policy_report_lines(policy)
    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content


# ---------------------------------------------------------------------------
# Private: report helpers
# ---------------------------------------------------------------------------

def _build_policy_report_lines(policy: RegimePolicy) -> list[str]:
    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        "# Regime-Driven Strategy Selection Policy",
        "",
        "## Policy Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
        f"| Policy timestamp | {policy.generated_at} |",
        f"| Source | {policy.source_description or 'N/A'} |",
    ]
    for key, val in policy.metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")
    lines += [
        f"| Regimes covered | {len(policy.entries)} |",
        "",
        "---",
    ]

    # ------------------------------------------------------------------
    # Threshold documentation
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Policy Thresholds",
        "",
        "> All thresholds are deterministic and fully auditable.",
        "",
        "| Threshold | Value | Meaning |",
        "| --- | --- | --- |",
        f"| MIN_RUN_COUNT | {MIN_RUN_COUNT} | Min backtest runs to consider a strategy |",
        f"| SHARPE_PREFERRED_MIN | {SHARPE_PREFERRED_MIN:.2f} | Preferred strategy min mean Sharpe |",
        f"| SHARPE_ALLOWED_MIN | {SHARPE_ALLOWED_MIN:.2f} | Allowed strategy min mean Sharpe |",
        f"| SHARPE_SUPPRESSED_BELOW | {SHARPE_SUPPRESSED_BELOW:.2f} | Strategies below this are suppressed |",
        f"| POS_RETURN_RATE_MIN | {POS_RETURN_RATE_MIN:.2f} | Min fraction of runs with positive return |",
        f"| NO_TRADE_SHARPE_MAX | {NO_TRADE_SHARPE_MAX:.2f} | If ALL strategies below this: no-trade candidate |",
        f"| NO_TRADE_POS_RATE_MAX | {NO_TRADE_POS_RATE_MAX:.2f} | Secondary no-trade condition |",
        f"| RISK_OFF_AUTO_NO_TRADE | {RISK_OFF_AUTO_NO_TRADE} | risk_off always no-trade unless preferred strategy exists |",
        "",
        "---",
    ]

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Summary Table",
        "",
        "| Regime | Preferred | Allowed | Suppressed | Trade? |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label, entry in sorted(policy.entries.items()):
        pref  = entry.preferred_strategy or "none"
        allow = ", ".join(entry.allowed_strategies) if entry.allowed_strategies else "none"
        supp  = ", ".join(entry.suppressed_strategies) if entry.suppressed_strategies else "none"
        trade = "YES" if entry.should_trade else "NO"
        lines.append(f"| {label} | {pref} | {allow} | {supp} | {trade} |")
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Per-regime detail
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Per-Regime Policy Detail",
        "",
    ]
    for label, entry in sorted(policy.entries.items()):
        trade_str = "YES - trading allowed" if entry.should_trade else "NO - trading suppressed"
        lines += [
            f"### {label}",
            "",
            f"- **Trade?** {trade_str}",
            f"- **Preferred strategy:** {entry.preferred_strategy or 'none'}",
            f"- **Allowed strategies:** {', '.join(entry.allowed_strategies) or 'none'}",
            f"- **Suppressed strategies:** {', '.join(entry.suppressed_strategies) or 'none'}",
            f"- **All ranked:** {' > '.join(entry.ranked_strategies) or 'none'}",
            f"- **Rationale:** {entry.rationale}",
        ]
        # Source metrics mini-table
        if entry.source_metrics:
            lines += [
                "",
                "  | Strategy | run_count | mean_sharpe | mean_return | pos_return_rate |",
                "  | --- | --- | --- | --- | --- |",
            ]
            for strat in entry.ranked_strategies:
                m = entry.source_metrics.get(strat, {})
                rc  = m.get("run_count", "N/A")
                ms  = f"{m['mean_sharpe']:.4f}"  if isinstance(m.get("mean_sharpe"),  float) else "N/A"
                mr  = f"{m['mean_return']:.4f}"  if isinstance(m.get("mean_return"),  float) else "N/A"
                prr = f"{m['pos_return_rate']:.4f}" if isinstance(m.get("pos_return_rate"), float) else "N/A"
                lines.append(f"  | {strat} | {rc} | {ms} | {mr} | {prr} |")
        lines += ["", ""]

    lines += ["---", ""]

    # ------------------------------------------------------------------
    # Caveats
    # ------------------------------------------------------------------
    lines += [
        "## Notes and Caveats",
        "",
        "- Policy is derived from historical backtests; past performance does not "
        "guarantee future results.",
        "- Sample sizes from a typical research run are small; treat decisions as "
        "directional guidance, not statistical certainty.",
        "- All rules are explicit, deterministic, and threshold-based (no machine learning).",
        "- This policy is not wired into live order execution.",
        "- Re-run with more symbols (`--symbols-limit 20+`) for more robust estimates.",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with "
        "`--regime-analysis --build-regime-policy` enabled._",
    ]
    return lines
