"""
Dashboard API layer for the backtesting engine.

Provides a clean adapter that transforms BacktestEngine and
MultiAssetBacktester results into JSON-serializable payloads
for consumption by a future AI dashboard / UI frontend.

Design constraints:
- No web server, no Streamlit, no Flask, no WebSockets yet.
- Pure Python adapter: DataFrames → dicts/lists, Timestamps → strings.
- Works with both single-asset and multi-asset result shapes.
- Gracefully returns empty structures when data is missing.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("dashboard_api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_timestamp(value: Any) -> str:
    """Convert a timestamp-like value to an ISO-8601 string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return str(value)


def _safe_float(value: Any) -> Optional[float]:
    """Convert to float, handling NaN / inf gracefully."""
    if value is None:
        return None
    try:
        f = float(value)
        if f != f:              # NaN
            return None
        if f == float("inf") or f == float("-inf"):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of JSON-safe dicts.

    Timestamps are converted to ISO-8601 strings.
    NaN / inf values become None.
    """
    if df is None or df.empty:
        return []

    records = []
    # Reset index to expose the index column as a regular column
    working = df.reset_index() if df.index.name else df

    for _, row in working.iterrows():
        record: dict[str, Any] = {}
        for col in working.columns:
            val = row[col]
            if isinstance(val, (datetime, pd.Timestamp)):
                record[col] = _safe_timestamp(val)
            elif isinstance(val, float):
                record[col] = _safe_float(val)
            elif isinstance(val, (int, bool, str)):
                record[col] = val
            else:
                record[col] = str(val) if val is not None else None
        records.append(record)

    return records


def _safe_dict(d: Any) -> dict[str, Any]:
    """Ensure a dict is JSON-safe (NaN → None, timestamps → str)."""
    if not isinstance(d, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (datetime, pd.Timestamp)):
            out[k] = _safe_timestamp(v)
        elif isinstance(v, float):
            out[k] = _safe_float(v)
        elif isinstance(v, dict):
            out[k] = _safe_dict(v)
        elif isinstance(v, pd.DataFrame):
            out[k] = _dataframe_to_records(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# DashboardAPI — main adapter class
# ---------------------------------------------------------------------------

class DashboardAPI:
    """Adapter that presents backtest results as JSON-serializable payloads.

    Accepts either:
    - single-asset results from ``BacktestEngine.get_results()``
    - multi-asset results from ``MultiAssetBacktester.run()``

    and exposes uniform accessor methods that always return plain
    Python objects (dicts, lists, strings, numbers).

    Example — single-asset::

        engine = BacktestEngine(config, strategy)
        engine.run(data_handler)
        api = DashboardAPI(engine.get_results())
        api.get_equity_curve()

    Example — multi-asset::

        backtester = MultiAssetBacktester(...)
        results = backtester.run()
        api = DashboardAPI(results)
        api.get_portfolio_stats()
    """

    def __init__(self, results: dict[str, Any]) -> None:
        self._raw = results or {}
        self._is_multi = self._detect_multi_asset()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def _detect_multi_asset(self) -> bool:
        """Return True if the payload looks like multi-asset output."""
        return "symbol_results" in self._raw or "portfolio_metrics" in self._raw

    @property
    def is_multi_asset(self) -> bool:
        return self._is_multi

    # ------------------------------------------------------------------
    # Single-asset accessors
    # ------------------------------------------------------------------

    def get_equity_curve(self) -> list[dict[str, Any]]:
        """Return the equity curve as a list of records.

        Works for both single-asset (``equity_curve`` key) and
        multi-asset (``portfolio_equity_curve`` key).
        """
        if self._is_multi:
            df = self._raw.get("portfolio_equity_curve")
        else:
            df = self._raw.get("equity_curve")

        if isinstance(df, pd.DataFrame):
            return _dataframe_to_records(df)
        return []

    def get_trade_log(self) -> list[dict[str, Any]]:
        """Return the trade log as a list of records."""
        if self._is_multi:
            df = self._raw.get("portfolio_trade_log")
        else:
            df = self._raw.get("trade_log")

        if isinstance(df, pd.DataFrame):
            return _dataframe_to_records(df)
        return []

    def get_strategy_metrics(self) -> dict[str, Any]:
        """Return the strategy-level performance metrics.

        For single-asset, returns the ``metrics`` dict directly.
        For multi-asset, returns the aggregated ``portfolio_metrics``.
        """
        if self._is_multi:
            return _safe_dict(self._raw.get("portfolio_metrics", {}))

        return _safe_dict(self._raw.get("metrics", {}))

    # ------------------------------------------------------------------
    # Multi-asset specific accessors
    # ------------------------------------------------------------------

    def get_portfolio_stats(self) -> dict[str, Any]:
        """Return portfolio-level aggregate statistics.

        Returns ``portfolio_metrics`` for multi-asset, or wraps
        ``metrics`` for single-asset so the caller always gets a dict.
        """
        if self._is_multi:
            return _safe_dict(self._raw.get("portfolio_metrics", {}))
        return _safe_dict(self._raw.get("metrics", {}))

    def get_symbol_metrics(self) -> dict[str, dict[str, Any]]:
        """Return per-symbol metrics (multi-asset only).

        Returns:
            ``{ "RELIANCE.NS": { ... }, "TCS.NS": { ... } }``
            Empty dict for single-asset payloads.
        """
        symbol_results = self._raw.get("symbol_results", {})
        if not symbol_results:
            return {}

        out: dict[str, dict[str, Any]] = {}
        for symbol, result in symbol_results.items():
            # MultiAssetRunResult dataclass has a .metrics dict
            metrics = getattr(result, "metrics", None)
            if metrics is None and isinstance(result, dict):
                metrics = result.get("metrics", {})
            out[symbol] = _safe_dict(metrics or {})
        return out

    def get_correlation_matrix(self) -> list[dict[str, Any]]:
        """Return the correlation matrix as records (multi-asset only).

        Each record is one row, e.g.
        ``{"index": "RELIANCE.NS", "RELIANCE.NS": 1.0, "TCS.NS": 0.75}``.
        Returns empty list for single-asset payloads.
        """
        df = self._raw.get("correlation_matrix")
        if isinstance(df, pd.DataFrame) and not df.empty:
            return _dataframe_to_records(df)
        return []

    # ------------------------------------------------------------------
    # Full snapshot
    # ------------------------------------------------------------------

    def get_full_snapshot(self) -> dict[str, Any]:
        """Return the complete dashboard payload as one dict.

        Useful for serializing a full state dump to JSON.
        """
        return {
            "is_multi_asset": self._is_multi,
            "equity_curve": self.get_equity_curve(),
            "trade_log": self.get_trade_log(),
            "strategy_metrics": self.get_strategy_metrics(),
            "portfolio_stats": self.get_portfolio_stats(),
            "symbol_metrics": self.get_symbol_metrics(),
            "correlation_matrix": self.get_correlation_matrix(),
        }


# ---------------------------------------------------------------------------
# RealtimeDashboard — in-memory placeholder
# ---------------------------------------------------------------------------

class RealtimeDashboard:
    """Placeholder for future real-time dashboard streaming.

    No network layer yet. Stores updates in an in-memory deque
    and supports basic subscribe/push/get patterns so a future
    WebSocket or SSE transport can be plugged in without
    redesigning the interface.
    """

    def __init__(self, max_updates: int = 1000) -> None:
        self._updates: deque[dict[str, Any]] = deque(maxlen=max_updates)
        self._subscribers: dict[str, list[dict[str, Any]]] = {}

    def push_update(self, data: dict[str, Any]) -> None:
        """Push a new update into the queue.

        Args:
            data: Arbitrary JSON-serializable dict.
                  Should include a ``"strategy_id"`` key for routing.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": _safe_dict(data),
        }
        self._updates.append(entry)

        # Route to subscribers
        strategy_id = data.get("strategy_id")
        if strategy_id and strategy_id in self._subscribers:
            self._subscribers[strategy_id].append(entry)

    def subscribe(self, strategy_id: str) -> None:
        """Register interest in updates for a given strategy.

        Args:
            strategy_id: Identifier for the strategy to follow.
        """
        if strategy_id not in self._subscribers:
            self._subscribers[strategy_id] = []
            logger.info(f"Subscribed to strategy: {strategy_id}")

    def get_latest_updates(
        self, count: int = 10, strategy_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Retrieve the most recent updates.

        Args:
            count: Max number of updates to return.
            strategy_id: If set, filter to this strategy only.

        Returns:
            List of update dicts, newest first.
        """
        if strategy_id and strategy_id in self._subscribers:
            source = self._subscribers[strategy_id]
        else:
            source = list(self._updates)

        return list(reversed(source[-count:]))

    def clear(self) -> None:
        """Clear all stored updates and subscriptions."""
        self._updates.clear()
        self._subscribers.clear()


# ---------------------------------------------------------------------------
# Export helper
# ---------------------------------------------------------------------------

def save_dashboard_payload(
    api: DashboardAPI,
    filepath: str | Path,
) -> Path:
    """Export a full dashboard snapshot to a JSON file.

    Args:
        api: A DashboardAPI instance.
        filepath: Destination path.

    Returns:
        Path to the written file.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = api.get_full_snapshot()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    logger.info(f"Dashboard payload saved to {path}")
    return path
