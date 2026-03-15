"""
Relative Strength / Top-Stock Selection.

Computes multi-factor relative strength scores for a universe of symbols
and ranks them so a portfolio layer can select the strongest names.

METRICS (per symbol, computed over a rolling lookback window)
-------------------------------------------------------------
  momentum_return        : Total return over the lookback period
                           (close[-1] / close[0] - 1).  Primary signal.

  trend_slope            : Normalised linear-regression slope of close prices.
                           Positive = upward trend; negative = downward.
                           Normalised by mean close so it is comparable across
                           different price levels.

  relative_return        : Excess return vs a benchmark series.
                           = momentum_return - benchmark_momentum_return.
                           Zero when no benchmark is provided.

  vol_adjusted_return    : Momentum return / annualised daily-return std-dev.
                           Rewards consistent gains with low volatility.
                           Zero when volatility is zero.

  rolling_strength_score : Composite score (z-score average of the four
                           metrics above).  Normalised across all symbols so
                           ranking is meaningful relative to the universe.

NO LOOKAHEAD
------------
  Each metric uses only the LAST `lookback` bars of each symbol's OHLCV
  DataFrame.  The function never peeks beyond the data provided by the caller.

PUBLIC API
----------
  RelativeStrengthRecord          Per-symbol result (dataclass).
  compute_relative_strength()     Compute metrics for all symbols.
  rank_symbols_by_strength()      Sort DataFrame by rolling_strength_score.
  select_top_symbols()            Return top-N symbol list.
  generate_relative_strength_report()  Write markdown report.

USAGE EXAMPLE
-------------
  from src.market_intelligence.relative_strength import (
      compute_relative_strength, select_top_symbols,
  )
  rs_df = compute_relative_strength(symbol_to_ohlcv, lookback=90)
  top5  = select_top_symbols(rs_df, n=5)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("relative_strength")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRED_COL = "close"          # only column required from OHLCV DataFrames
_METRIC_COLS = (                 # columns used in composite z-score
    "momentum_return",
    "trend_slope",
    "relative_return",
    "vol_adjusted_return",
)
_TRADING_DAYS_PER_YEAR: float = 252.0


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class RelativeStrengthRecord:
    """Per-symbol relative strength metrics."""

    symbol: str
    momentum_return: float       # total return over lookback window
    trend_slope: float           # normalised linear-regression slope
    relative_return: float       # excess return vs benchmark (0 if no benchmark)
    vol_adjusted_return: float   # return / annualised volatility
    rolling_strength_score: float  # composite z-score across four metrics
    lookback_bars: int           # actual number of bars used


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_relative_strength(
    symbol_to_ohlcv: dict[str, pd.DataFrame],
    lookback: int = 90,
    benchmark_series: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Compute relative strength metrics for every symbol in the universe.

    Parameters
    ----------
    symbol_to_ohlcv : dict[str, pd.DataFrame]
        Mapping of symbol -> OHLCV DataFrame.  Each DataFrame must have a
        ``close`` column and a DatetimeIndex (or any sortable index).
        Additional OHLC/volume columns are ignored.
    lookback : int
        Number of *bars* to use for each metric (default 90).  The most
        recent ``lookback`` rows of each DataFrame are used.  If a symbol
        has fewer rows than ``lookback``, all available rows are used and
        ``lookback_bars`` reflects the actual count.
    benchmark_series : pd.Series, optional
        Close-price series for a benchmark instrument (e.g. NIFTY 50 index).
        The series is re-indexed to each symbol's lookback window using
        forward-fill.  When None, ``relative_return`` is set to 0.0 for all
        symbols.

    Returns
    -------
    pd.DataFrame
        One row per symbol with columns:
        ``symbol, momentum_return, trend_slope, relative_return,
        vol_adjusted_return, rolling_strength_score, lookback_bars``.
        Sorted by ``rolling_strength_score`` descending.
        Returns an empty DataFrame when ``symbol_to_ohlcv`` is empty or all
        symbols fail processing.

    Notes
    -----
    * The composite ``rolling_strength_score`` is the mean of the per-metric
      z-scores across the universe.  When only one symbol is present,
      z-scores are all zero and the score is 0.
    * Symbols that cannot be processed (missing close column, fewer than 2
      bars) are silently skipped and excluded from the output.
    """
    if not symbol_to_ohlcv:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    for symbol, df in symbol_to_ohlcv.items():
        row = _compute_symbol_metrics(symbol, df, lookback, benchmark_series)
        if row is not None:
            rows.append(row)

    if not rows:
        logger.warning("compute_relative_strength: no symbols produced valid metrics.")
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result = _add_composite_score(result)
    result = result.sort_values("rolling_strength_score", ascending=False).reset_index(drop=True)

    # Round for readability
    float_cols = result.select_dtypes("float").columns.tolist()
    result[float_cols] = result[float_cols].round(6)

    logger.info(
        f"compute_relative_strength: {len(result)} symbols ranked, "
        f"lookback={lookback} bars."
    )
    return result


def rank_symbols_by_strength(rs_df: pd.DataFrame) -> pd.DataFrame:
    """Sort a relative strength DataFrame by score (descending).

    Parameters
    ----------
    rs_df : pd.DataFrame
        Output of :func:`compute_relative_strength`.

    Returns
    -------
    pd.DataFrame
        Re-sorted copy.  If ``rolling_strength_score`` is absent, returns
        the DataFrame unchanged.
    """
    if rs_df.empty:
        return rs_df

    if "rolling_strength_score" not in rs_df.columns:
        logger.warning(
            "rank_symbols_by_strength: 'rolling_strength_score' column missing. "
            "Returning input unchanged."
        )
        return rs_df

    return (
        rs_df.sort_values("rolling_strength_score", ascending=False)
        .reset_index(drop=True)
    )


def select_top_symbols(
    rs_df: pd.DataFrame,
    n: int = 5,
) -> list[str]:
    """Return the top-N symbol names by rolling_strength_score.

    Parameters
    ----------
    rs_df : pd.DataFrame
        Output of :func:`compute_relative_strength` or
        :func:`rank_symbols_by_strength`.
    n : int
        Number of top symbols to return (default 5).  If the DataFrame has
        fewer rows than ``n``, all available symbols are returned.

    Returns
    -------
    list[str]
        Symbol names, strongest first.  Empty list when ``rs_df`` is empty
        or ``"symbol"`` column is absent.
    """
    if rs_df.empty or "symbol" not in rs_df.columns:
        return []

    n = max(1, int(n))
    ranked = rank_symbols_by_strength(rs_df)
    return ranked["symbol"].head(n).tolist()


def generate_relative_strength_report(
    rs_df: pd.DataFrame,
    output_path: Optional[str | Path] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Generate and save the relative strength markdown report.

    Parameters
    ----------
    rs_df : pd.DataFrame
        Output of :func:`compute_relative_strength`.
    output_path : str or Path, optional
        Where to write the markdown file.  Defaults to
        ``research/relative_strength_analysis.md``.
    metadata : dict, optional
        Extra context to embed (interval, lookback, benchmark symbol, etc.).

    Returns
    -------
    str
        Full markdown content of the report.
    """
    output_path = (
        Path(output_path)
        if output_path
        else Path("research") / "relative_strength_analysis.md"
    )
    metadata = dict(metadata) if metadata else {}

    lines = _build_rs_report_lines(rs_df, metadata)
    content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Relative strength report written to {output_path}")

    return content


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _compute_symbol_metrics(
    symbol: str,
    df: pd.DataFrame,
    lookback: int,
    benchmark_series: Optional[pd.Series],
) -> Optional[dict[str, Any]]:
    """Compute metrics for one symbol.  Returns None on failure."""
    if df is None or df.empty:
        return None

    if _REQUIRED_COL not in df.columns:
        logger.debug(f"{symbol}: missing 'close' column; skipped.")
        return None

    # Use most recent `lookback` bars
    slice_df = df.tail(lookback) if len(df) >= lookback else df.copy()
    close = slice_df[_REQUIRED_COL].dropna()

    if len(close) < 2:
        logger.debug(f"{symbol}: fewer than 2 close prices after dropna; skipped.")
        return None

    # ------------------------------------------------------------------
    # 1. Momentum return
    # ------------------------------------------------------------------
    momentum_return = float(close.iloc[-1]) / float(close.iloc[0]) - 1.0

    # ------------------------------------------------------------------
    # 2. Trend slope (normalised linear regression slope of close)
    # ------------------------------------------------------------------
    x = np.arange(len(close), dtype=float)
    try:
        coeffs = np.polyfit(x, close.values.astype(float), 1)
        slope = float(coeffs[0])
    except (np.linalg.LinAlgError, ValueError):
        slope = 0.0

    mean_price = float(close.mean())
    trend_slope = slope / mean_price if mean_price > 0 else 0.0

    # ------------------------------------------------------------------
    # 3. Relative return vs benchmark
    # ------------------------------------------------------------------
    relative_return = 0.0
    if benchmark_series is not None:
        try:
            bm = benchmark_series.reindex(close.index).ffill().bfill().dropna()
            if len(bm) >= 2:
                bm_return = float(bm.iloc[-1]) / float(bm.iloc[0]) - 1.0
                relative_return = momentum_return - bm_return
        except Exception as exc:
            logger.debug(f"{symbol}: benchmark alignment failed: {exc}")

    # ------------------------------------------------------------------
    # 4. Volatility-adjusted return
    # ------------------------------------------------------------------
    daily_returns = close.pct_change().dropna()
    if len(daily_returns) >= 2:
        daily_std = float(daily_returns.std())
        ann_vol = daily_std * float(np.sqrt(_TRADING_DAYS_PER_YEAR))
    else:
        ann_vol = 0.0

    vol_adjusted_return = momentum_return / ann_vol if ann_vol > 0.0 else 0.0

    return {
        "symbol":               symbol,
        "momentum_return":      momentum_return,
        "trend_slope":          trend_slope,
        "relative_return":      relative_return,
        "vol_adjusted_return":  vol_adjusted_return,
        "rolling_strength_score": 0.0,   # placeholder; filled by _add_composite_score
        "lookback_bars":        int(len(close)),
    }


def _add_composite_score(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the composite rolling_strength_score via z-score averaging.

    Each of the four metric columns is z-scored across all symbols.
    The composite score is the mean of those z-scores.  When only one
    symbol is present all z-scores are 0 (well-defined but uninformative).
    """
    metric_cols = [c for c in _METRIC_COLS if c in df.columns]

    if len(df) < 2:
        # Single row: z-scores undefined -> set to 0
        df["rolling_strength_score"] = 0.0
        return df

    z_frames: list[pd.Series] = []
    for col in metric_cols:
        col_std = df[col].std()
        if col_std > 0.0:
            z = (df[col] - df[col].mean()) / col_std
        else:
            z = pd.Series(0.0, index=df.index)
        z_frames.append(z)

    if z_frames:
        df["rolling_strength_score"] = pd.concat(z_frames, axis=1).mean(axis=1)
    else:
        df["rolling_strength_score"] = 0.0

    return df


# ---------------------------------------------------------------------------
# Report helpers (ASCII-only for Windows cp1252 compatibility)
# ---------------------------------------------------------------------------

def _fmt_val(v: Any) -> str:
    """Format a value for a markdown table cell."""
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
    sep    = "| " + " | ".join("---" for _ in col_names) + " |"
    rows   = [
        "| " + " | ".join(_fmt_val(v) for v in row) + " |"
        for row in df.itertuples(index=False, name=None)
    ]
    return "\n".join([header, sep] + rows)


def _build_rs_report_lines(
    rs_df: pd.DataFrame,
    metadata: dict[str, Any],
) -> list[str]:
    """Assemble all markdown sections for the relative strength report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_symbols = len(rs_df) if not rs_df.empty else 0

    lines: list[str] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        "# Relative Strength Analysis",
        "",
        "## Run Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
        f"| Symbols Analysed | {n_symbols} |",
    ]
    for key, val in metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Full ranked table
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Ranked Symbols by Relative Strength",
        "",
        "> Sorted by **rolling_strength_score** (composite z-score, higher = stronger).",
        "> Benchmark is included in relative_return when provided; 0 otherwise.",
        "",
    ]

    if not rs_df.empty:
        display_cols = [c for c in [
            "symbol", "rolling_strength_score",
            "momentum_return", "trend_slope",
            "relative_return", "vol_adjusted_return",
            "lookback_bars",
        ] if c in rs_df.columns]
        lines.append(_df_to_md(rs_df[display_cols]))
    else:
        lines.append("_No results._")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Top 10 spotlight
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Top 10 Strongest Symbols",
        "",
        "> These names scored highest on the composite relative strength metric.",
        "> Suitable as candidates for the portfolio long-list.",
        "",
    ]
    if not rs_df.empty and "symbol" in rs_df.columns:
        top10_syms = rs_df.head(10)["symbol"].tolist()
        for rank, sym in enumerate(top10_syms, 1):
            row = rs_df[rs_df["symbol"] == sym].iloc[0]
            score = _fmt_val(row.get("rolling_strength_score", float("nan")))
            mom = _fmt_val(row.get("momentum_return", float("nan")))
            lines.append(f"{rank}. **{sym}** (score={score}, momentum={mom})")
    else:
        lines.append("_No data._")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Metric definitions
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Metric Definitions",
        "",
        "| Metric | Definition |",
        "| --- | --- |",
        "| momentum_return | close[-1] / close[0] - 1 over the lookback window |",
        "| trend_slope | Normalised linear-regression slope (slope / mean_price) |",
        "| relative_return | momentum_return - benchmark_momentum_return |",
        "| vol_adjusted_return | momentum_return / annualised_daily_std |",
        "| rolling_strength_score | Mean z-score across the four metrics above |",
        "",
        "---",
        "",
        "## Caveats",
        "",
        "- Relative strength is a backward-looking momentum metric; "
        "past performance does not guarantee future results.",
        "- A single lookback window is used per run; different lookbacks "
        "may produce different rankings.",
        "- Volatility-adjusted return is undefined when daily returns have "
        "zero variance; those symbols receive vol_adjusted_return = 0.",
        "- Relative return is 0 when no benchmark is provided.",
        "- No live trading. This output must not be used for real capital deployment.",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with "
        "`--top-n-symbols` enabled._",
    ]

    return lines
