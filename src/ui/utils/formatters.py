"""
Display formatting utilities for the Streamlit dashboard.

Converts raw data values into human-readable display strings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import pandas as pd


def fmt_pct(value: Any, decimals: int = 2) -> str:
    """Format a decimal ratio as a percentage string.

    0.1234 -> "12.34%"
    None   -> "N/A"
    """
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


def fmt_pct_already(value: Any, decimals: int = 2) -> str:
    """Format a value that is already in percentage form.

    12.34  -> "12.34%"
    None   -> "N/A"
    """
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


def fmt_currency(value: Any, symbol: str = "", decimals: int = 0) -> str:
    """Format a number as currency.

    100000 -> "1,00,000" (Indian) or "$100,000"
    """
    if value is None:
        return "N/A"
    try:
        v = float(value)
        formatted = f"{v:,.{decimals}f}"
        return f"{symbol}{formatted}" if symbol else formatted
    except (TypeError, ValueError):
        return "N/A"


def fmt_number(value: Any, decimals: int = 2) -> str:
    """Format a plain number."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
        if v == int(v) and decimals == 0:
            return f"{int(v):,}"
        return f"{v:,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def fmt_ratio(value: Any, decimals: int = 2) -> str:
    """Format a ratio like Sharpe, Sortino, risk/reward."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def fmt_signal(signal: Any) -> str:
    """Format a trading signal for display."""
    if signal is None:
        return "-"
    s = str(signal).upper()
    return s


def fmt_horizon(horizon: Any) -> str:
    """Format a trade horizon classification."""
    if horizon is None:
        return "-"
    return str(horizon).replace("_", " ").title()


def fmt_severity(severity: Any) -> str:
    """Format an alert severity for display."""
    if severity is None:
        return "-"
    return str(severity).replace("_", " ").title()


def fmt_timestamp(value: Any) -> str:
    """Format a timestamp for display (shorter form)."""
    if value is None:
        return "N/A"
    try:
        ts = pd.Timestamp(value)
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)[:19]


def fmt_date(value: Any) -> str:
    """Format a date for display."""
    if value is None:
        return "N/A"
    try:
        ts = pd.Timestamp(value)
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def fmt_bool(value: Any) -> str:
    """Format a boolean for display."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def color_pnl(value: Any) -> str:
    """Return a color name based on PnL sign (for conditional formatting)."""
    if value is None:
        return "gray"
    try:
        v = float(value)
        if v > 0:
            return "green"
        elif v < 0:
            return "red"
        return "gray"
    except (TypeError, ValueError):
        return "gray"


def color_score(score: Any, thresholds: tuple = (40, 60, 80)) -> str:
    """Return color based on score thresholds.

    < 40: red, 40-60: orange, 60-80: blue, 80+: green
    """
    if score is None:
        return "gray"
    try:
        s = float(score)
        if s < thresholds[0]:
            return "red"
        elif s < thresholds[1]:
            return "orange"
        elif s < thresholds[2]:
            return "blue"
        return "green"
    except (TypeError, ValueError):
        return "gray"


def metrics_to_display_dict(
    metrics: Dict[str, Any],
    keys: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Convert a raw metrics dict into formatted display values.

    If keys is provided, only includes those keys. Otherwise includes all.
    """
    formatters = {
        "total_return_pct": fmt_pct,
        "annualized_return": fmt_pct,
        "cagr": fmt_pct,
        "max_drawdown_pct": fmt_pct,
        "win_rate": fmt_pct,
        "exposure_pct": fmt_pct,
        "sharpe_ratio": fmt_ratio,
        "sortino_ratio": fmt_ratio,
        "profit_factor": fmt_ratio,
        "expectancy": lambda v: fmt_currency(v, decimals=2),
        "final_value": lambda v: fmt_currency(v, decimals=0),
        "initial_capital": lambda v: fmt_currency(v, decimals=0),
        "total_fees": lambda v: fmt_currency(v, decimals=2),
        "num_trades": lambda v: fmt_number(v, decimals=0),
        "num_winners": lambda v: fmt_number(v, decimals=0),
        "num_losers": lambda v: fmt_number(v, decimals=0),
        "avg_bars_held": lambda v: fmt_number(v, decimals=1),
    }

    selected = keys or list(metrics.keys())
    result = {}
    for key in selected:
        if key not in metrics:
            continue
        val = metrics[key]
        formatter = formatters.get(key)
        if formatter:
            result[key] = formatter(val)
        elif isinstance(val, float):
            result[key] = fmt_number(val)
        else:
            result[key] = str(val) if val is not None else "N/A"
    return result


def clean_column_name(col: str) -> str:
    """Convert snake_case column names to Title Case for display."""
    return col.replace("_", " ").title()


def style_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply display-friendly column renames to a DataFrame copy."""
    renamed = {}
    for col in df.columns:
        renamed[col] = clean_column_name(col)
    return df.rename(columns=renamed)
