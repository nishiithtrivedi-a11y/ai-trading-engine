"""
Regime-aware historical research validation.

Provides three public functions:

  analyze_by_regime(results_df)         -> pd.DataFrame
      Aggregate backtest metrics grouped by (regime_label, strategy).

  rank_strategies_by_regime(agg_df)    -> dict[str, pd.DataFrame]
      Rank strategies within each regime by risk-adjusted performance.

  generate_regime_report(results_df, …) -> str
      Build and optionally save a markdown research report.

SCOPE OF regime_label
---------------------
When called from the NIFTY 50 research runner with --regime-analysis, the
regime_label in each result row is the CompositeRegime value detected from
*that symbol's own historical OHLCV data* at the end of the backtest window.

This is NOT a bar-by-bar regime signal and NOT the current market regime.
It is a snapshot of the dominant market condition in the symbol's recent
history at the point the data was loaded, giving a best-effort labelling of
"what kind of market this symbol was in during the test period."

WIN RATE DEFINITION
-------------------
Two complementary metrics are reported:

  mean_win_rate         — average of each run's *trade-level* win rate
                          (num_winners / num_trades per backtest run).
                          Comes directly from the backtest engine; precise.

  positive_return_rate  — fraction of (symbol, strategy) backtest *runs*
                          that produced a positive total_return_pct.
                          Useful when num_trades is very small (1-2 trades).

RANKING METHODOLOGY
-------------------
Within each regime, strategies are sorted by:
  1. mean_sharpe     descending  (risk-adjusted return — primary)
  2. mean_return     descending  (raw return — secondary)
  3. mean_drawdown   descending  (max_drawdown_pct is stored as a negative
                                  fraction; descending = closest to 0 =
                                  least bad; tertiary)

A higher rank indicates better historical performance in that regime.
Strategies absent from a regime's rows are omitted from that regime's table.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Recognised CompositeRegime values (informational; not enforced in logic)
_ALL_COMPOSITE_REGIMES: frozenset[str] = frozenset({
    "bullish_trending",
    "bullish_sideways",
    "bearish_trending",
    "bearish_volatile",
    "rangebound",
    "risk_off",
    "unknown",
})

# Minimum columns required by every public function
_REQUIRED_COLS: frozenset[str] = frozenset({"regime_label", "strategy"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_by_regime(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate backtest performance metrics grouped by (regime_label, strategy).

    Parameters
    ----------
    results_df : pd.DataFrame
        Result rows from the research runner.  Must contain at minimum:
        ``regime_label`` and ``strategy``.  Performance metrics are
        aggregated only when their columns are present; missing metric columns
        are silently ignored so the function degrades gracefully.

    Returns
    -------
    pd.DataFrame
        One row per (regime_label, strategy) pair with aggregated metrics.
        Always present: regime_label, strategy, symbol_count, run_count.
        Additional columns depend on which metric columns are in results_df.

    Raises
    ------
    TypeError
        If ``results_df`` is not a DataFrame.
    ValueError
        If required columns are missing or no rows have a valid regime_label.
    """
    _validate_input(results_df)

    df = results_df[results_df["regime_label"].notna()].copy()
    if df.empty:
        raise ValueError(
            "No rows with a valid regime_label found in results_df. "
            "Ensure --include-regime or --regime-analysis was active and "
            "at least one symbol's regime was successfully detected."
        )

    # ------------------------------------------------------------------
    # Build named aggregation kwargs dynamically from available columns
    # ------------------------------------------------------------------
    agg_kwargs: dict[str, Any] = {
        "symbol_count": pd.NamedAgg(column="symbol", aggfunc="nunique"),
        "run_count":    pd.NamedAgg(column="symbol",  aggfunc="count"),
    }

    if "sharpe_ratio" in df.columns:
        agg_kwargs["mean_sharpe"]   = pd.NamedAgg(column="sharpe_ratio", aggfunc="mean")
        agg_kwargs["median_sharpe"] = pd.NamedAgg(column="sharpe_ratio", aggfunc="median")

    if "total_return_pct" in df.columns:
        agg_kwargs["mean_return"]   = pd.NamedAgg(column="total_return_pct", aggfunc="mean")
        agg_kwargs["median_return"] = pd.NamedAgg(column="total_return_pct", aggfunc="median")

    if "max_drawdown_pct" in df.columns:
        agg_kwargs["mean_drawdown"] = pd.NamedAgg(column="max_drawdown_pct", aggfunc="mean")

    if "win_rate" in df.columns:
        agg_kwargs["mean_win_rate"] = pd.NamedAgg(column="win_rate", aggfunc="mean")

    if "num_trades" in df.columns:
        agg_kwargs["total_trades"] = pd.NamedAgg(
            column="num_trades",
            aggfunc=lambda s: int(s.fillna(0).sum()),
        )

    agg = df.groupby(["regime_label", "strategy"]).agg(**agg_kwargs).reset_index()

    # ------------------------------------------------------------------
    # Positive-return rate — computed separately (requires a lambda)
    # ------------------------------------------------------------------
    if "total_return_pct" in df.columns:
        pos_rate = (
            df.groupby(["regime_label", "strategy"])["total_return_pct"]
            .apply(lambda x: float((x > 0).sum()) / max(float(len(x)), 1.0))
            .rename("positive_return_rate")
            .reset_index()
        )
        agg = agg.merge(pos_rate, on=["regime_label", "strategy"], how="left")

    # Round all floats for readability
    float_cols = list(agg.select_dtypes("float").columns)
    agg[float_cols] = agg[float_cols].round(4)

    return agg


def rank_strategies_by_regime(agg_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Rank strategies within each regime by risk-adjusted performance.

    Ranking order (see module docstring for full methodology):
      1. mean_sharpe     descending
      2. mean_return     descending
      3. mean_drawdown   descending  (closest to 0 = least bad = best)

    Parameters
    ----------
    agg_df : pd.DataFrame
        Output of :func:`analyze_by_regime`.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys are regime_label strings.  Values are DataFrames sorted by rank
        with a 1-based RangeIndex named ``"rank"``.
    """
    if "regime_label" not in agg_df.columns or "strategy" not in agg_df.columns:
        raise ValueError(
            "agg_df must contain 'regime_label' and 'strategy' columns. "
            "Pass the output of analyze_by_regime()."
        )

    # Build sort specification from whichever ranking columns exist
    sort_cols: list[str] = []
    sort_asc: list[bool] = []
    for col, ascending in [
        ("mean_sharpe",   False),  # higher Sharpe = better
        ("mean_return",   False),  # higher return = better
        ("mean_drawdown", False),  # stored as negative fraction; -0.05 > -0.25 -> desc
    ]:
        if col in agg_df.columns:
            sort_cols.append(col)
            sort_asc.append(ascending)

    ranked: dict[str, pd.DataFrame] = {}
    for regime in sorted(agg_df["regime_label"].unique()):
        sub = agg_df[agg_df["regime_label"] == regime].copy()
        if sort_cols:
            sub = sub.sort_values(sort_cols, ascending=sort_asc)
        sub = sub.reset_index(drop=True)
        sub.index = sub.index + 1   # 1-based rank
        sub.index.name = "rank"
        ranked[regime] = sub

    return ranked


def generate_regime_report(
    results_df: pd.DataFrame,
    output_path: Optional[str | Path] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """
    Generate and optionally save a markdown research report.

    Parameters
    ----------
    results_df : pd.DataFrame
        Result rows from the research runner (must have regime_label column).
    output_path : str or Path, optional
        Where to save the markdown file.  Parent directories are created if
        needed.  Defaults to ``research/regime_validation.md`` relative to CWD.
    metadata : dict, optional
        Extra context to embed in the report header (provider, interval, etc.).

    Returns
    -------
    str
        The full markdown content of the report.  The file is also written
        to ``output_path`` as a side-effect.
    """
    if not isinstance(results_df, pd.DataFrame):
        raise TypeError(f"results_df must be a pandas DataFrame; got {type(results_df)}")
    output_path = Path(output_path) if output_path else Path("research") / "regime_validation.md"
    metadata = dict(metadata) if metadata else {}

    try:
        # _validate_input raises ValueError for missing required columns (e.g. regime_label
        # absent because --regime-analysis was not used).  Catching it here produces a
        # graceful minimal report rather than an unhandled exception.
        _validate_input(results_df)
        agg_df = analyze_by_regime(results_df)
        ranked = rank_strategies_by_regime(agg_df)
    except ValueError as exc:
        lines = _minimal_report_lines(metadata, str(exc))
        content = "\n".join(lines)
        _write_report(content, output_path)
        return content

    lines = _build_report_lines(results_df, agg_df, ranked, metadata)
    content = "\n".join(lines)
    _write_report(content, output_path)
    return content


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _validate_input(results_df: pd.DataFrame) -> None:
    if not isinstance(results_df, pd.DataFrame):
        raise TypeError(f"results_df must be a pandas DataFrame; got {type(results_df)}")
    missing = _REQUIRED_COLS - set(results_df.columns)
    if missing:
        raise ValueError(
            f"results_df is missing required columns: {sorted(missing)}. "
            "Ensure --regime-analysis (or --include-regime) was active during the run."
        )


def _write_report(content: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _df_to_md(df: pd.DataFrame, with_index: bool = False) -> str:
    """Convert a DataFrame to a Markdown table string."""
    if df.empty:
        return "_No data._"

    def _fmt(v: Any) -> str:
        if v is None or (isinstance(v, float) and v != v):
            return "N/A"
        if isinstance(v, float):
            return f"{v:.4f}"
        if isinstance(v, int):
            return str(v)
        return str(v)

    if with_index:
        col_names = [df.index.name or "rank"] + list(df.columns)
        rows_data = [
            [idx] + list(row)
            for idx, row in zip(df.index, df.itertuples(index=False, name=None))
        ]
    else:
        col_names = list(df.columns)
        rows_data = [list(row) for row in df.itertuples(index=False, name=None)]

    header = "| " + " | ".join(str(c) for c in col_names) + " |"
    sep    = "| " + " | ".join("---" for _ in col_names) + " |"
    rows   = ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in rows_data]
    return "\n".join([header, sep] + rows)


def _regime_interpretation(regime: str, ranked_strategies: list[str]) -> str:
    """Return a one-line research interpretation for a regime."""
    top = ranked_strategies[0] if ranked_strategies else "N/A"
    hints: dict[str, str] = {
        "bullish_trending": (
            "Trend-following strategies (SMA, Breakout) tend to perform best "
            "as sustained momentum rewards directional exposure."
        ),
        "bullish_sideways": (
            "Breakout and mean-reversion can both work; breakouts near "
            "resistance levels are higher-probability."
        ),
        "bearish_trending": (
            "Long-only strategies face structural headwinds; capital "
            "preservation and reduced exposure are advisable."
        ),
        "bearish_volatile": (
            "Elevated drawdowns expected across all strategies; "
            "minimal new long positions and tight stops recommended."
        ),
        "rangebound": (
            "Mean-reversion strategies (RSI) tend to outperform trend-following "
            "as price oscillates within support/resistance bounds."
        ),
        "risk_off": (
            "All strategies face significant headwinds; the empirical data "
            "typically supports cash preservation over new exposure."
        ),
        "unknown": (
            "Regime was unclear during the test period; interpret results "
            "with caution as conditions were ambiguous."
        ),
    }
    base = hints.get(regime, "Regime not recognised; interpret results carefully.")
    return f"Top-ranked: **{top}**. {base}"


def _build_report_lines(
    results_df: pd.DataFrame,
    agg_df: pd.DataFrame,
    ranked: dict[str, pd.DataFrame],
    metadata: dict[str, Any],
) -> list[str]:
    """Assemble all sections of the markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_regimes = int(agg_df["regime_label"].nunique()) if not agg_df.empty else 0
    lines: list[str] = []

    # ------------------------------------------------------------------
    # Header / metadata
    # ------------------------------------------------------------------
    lines += [
        "# Regime-Aware Historical Research Validation",
        "",
        "## Run Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
    ]
    for key, val in metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")

    n_total  = len(results_df)
    n_regime = int(results_df["regime_label"].notna().sum())
    n_sym    = results_df["symbol"].nunique() if "symbol" in results_df.columns else "N/A"
    n_strat  = results_df["strategy"].nunique() if "strategy" in results_df.columns else "N/A"

    lines += [
        f"| Total result rows | {n_total} |",
        f"| Rows with regime label | {n_regime} |",
        f"| Distinct symbols | {n_sym} |",
        f"| Distinct strategies | {n_strat} |",
        f"| Distinct regimes observed | {n_regimes} |",
        "",
        "---",
    ]

    # ------------------------------------------------------------------
    # Regime distribution
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Regime Distribution",
        "",
        "> Counts of how many (symbol, strategy) backtest runs fell into each regime.",
        "> regime_label = composite regime detected from each symbol's own OHLCV data.",
        "",
    ]
    valid_df = results_df[results_df["regime_label"].notna()]
    if valid_df.empty:
        lines.append("_No rows with regime labels found._")
    else:
        dist = (
            valid_df
            .groupby("regime_label")
            .agg(
                symbol_count=("symbol", "nunique"),
                run_count=("symbol", "count"),
            )
            .reset_index()
            .sort_values("run_count", ascending=False)
        )
        lines.append(_df_to_md(dist))
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Performance by regime and strategy
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Performance by Regime and Strategy",
        "",
        "> Aggregated backtest metrics grouped by (regime_label, strategy).",
        "> WIN RATE: trade-level (num_winners / num_trades per run), then averaged.",
        "> POSITIVE RETURN RATE: fraction of runs where total_return_pct > 0.",
        "",
    ]
    display_cols = [c for c in [
        "regime_label", "strategy", "run_count",
        "mean_sharpe", "median_sharpe",
        "mean_return", "median_return",
        "mean_drawdown", "mean_win_rate",
        "positive_return_rate", "total_trades",
    ] if c in agg_df.columns]

    sorted_agg = agg_df[display_cols].sort_values(
        ["regime_label", "mean_sharpe"] if "mean_sharpe" in agg_df.columns
        else ["regime_label"],
        ascending=[True, False] if "mean_sharpe" in agg_df.columns else [True],
    )
    lines.append(_df_to_md(sorted_agg))
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Best strategies per regime
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Best Strategies Per Regime",
        "",
        "> Ranking: mean Sharpe (1st), mean return (2nd), mean drawdown (3rd, less negative = better).",
        "> All columns are averaged over backtest runs in that regime.",
        "",
    ]
    rank_display_base = [
        "strategy", "run_count",
        "mean_sharpe", "mean_return", "mean_drawdown",
        "positive_return_rate",
    ]
    for regime, df_rank in sorted(ranked.items()):
        strategy_names = df_rank["strategy"].tolist() if "strategy" in df_rank.columns else []
        interp = _regime_interpretation(regime, strategy_names)
        rank_cols = [c for c in rank_display_base if c in df_rank.columns]
        lines += [
            f"### Regime: {regime}",
            "",
            _df_to_md(df_rank[rank_cols], with_index=True),
            "",
            f"> {interp}",
            "",
        ]
    lines.append("---")

    # ------------------------------------------------------------------
    # Summary conclusions
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Summary Conclusions",
        "",
        "Key findings from this regime-aware historical analysis:",
        "",
    ]
    for regime, df_rank in sorted(ranked.items()):
        if df_rank.empty:
            continue
        top_strat  = df_rank.iloc[0]["strategy"] if "strategy" in df_rank.columns else "N/A"
        run_count  = int(df_rank["run_count"].sum()) if "run_count" in df_rank.columns else 0
        sharpe_str = (
            f"{df_rank.iloc[0]['mean_sharpe']:.4f}"
            if "mean_sharpe" in df_rank.columns else "N/A"
        )
        lines.append(
            f"- **{regime}** ({run_count} runs): "
            f"top strategy = **{top_strat}** (mean Sharpe = {sharpe_str})"
        )

    lines += [
        "",
        f"> Analysis covers {n_sym} symbols and {n_strat} strategies "
        f"across {n_regimes} distinct regime{'s' if n_regimes != 1 else ''}. "
        "Results reflect historical backtests only and must not be used for live trading.",
        "",
        "---",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with `--regime-analysis` enabled._",
    ]
    return lines


def _minimal_report_lines(metadata: dict[str, Any], error_msg: str) -> list[str]:
    """Return a short report when regime analysis could not be completed."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        "# Regime-Aware Historical Research Validation",
        "",
        f"**Generated:** {now}  ",
        "",
        "## Status: Incomplete",
        "",
        f"> Regime analysis could not be completed: {error_msg}",
        "",
        "Possible causes:",
        "- No symbols were processed successfully",
        "- Regime detection failed for all symbols (insufficient data bars?)",
        "- `regime_label` column was missing from result rows",
        "",
        "Re-run with `--symbols-limit 5 --include-regime --regime-analysis` "
        "to generate a full report.",
    ]
