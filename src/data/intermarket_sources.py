"""
Intermarket data normalization helpers.

Intermarket context is usually derived from existing market/macro feeds rather
than one dedicated API. This module keeps the derived shape explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _to_series(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        return pd.to_numeric(value, errors="coerce").dropna()
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series(dtype="float64")
        return pd.to_numeric(value.iloc[:, 0], errors="coerce").dropna()
    if isinstance(value, list):
        return pd.to_numeric(pd.Series(value), errors="coerce").dropna()
    return pd.Series(dtype="float64")


@dataclass
class IntermarketDataBundle:
    series: dict[str, pd.Series] = field(default_factory=dict)
    scalars: dict[str, float] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": {
                key: [float(v) for v in values.tolist()]
                for key, values in self.series.items()
            },
            "scalars": dict(self.scalars),
            "provider_metadata": dict(self.provider_metadata),
        }


def normalize_intermarket_payload(
    provider_name: str,
    payload: Mapping[str, Any] | None,
) -> IntermarketDataBundle:
    clean_provider = str(provider_name or "derived").strip().lower() or "derived"
    fetched_at = _now_utc()

    if payload is None:
        return IntermarketDataBundle(
            series={},
            scalars={},
            provider_metadata={
                "provider": clean_provider,
                "configured": clean_provider not in {"", "none"},
                "available": False,
                "degraded": True,
                "reason": "no_payload",
            },
        )

    root_series = payload.get("series")
    if not isinstance(root_series, Mapping):
        root_series = {}

    known_series_names = (
        "asset_returns",
        "benchmark_returns",
        "sector_returns",
        "rates_returns",
        "usd_returns",
        "commodity_returns",
        "inr_returns",
    )
    normalized_series: dict[str, pd.Series] = {}

    for name in known_series_names:
        if name in payload:
            series = _to_series(payload.get(name))
            if not series.empty:
                normalized_series[name] = series
        if name in root_series:
            series = _to_series(root_series.get(name))
            if not series.empty:
                normalized_series[name] = series

    scalars_raw = payload.get("scalars")
    if not isinstance(scalars_raw, Mapping):
        scalars_raw = payload.get("signals")
    if not isinstance(scalars_raw, Mapping):
        scalars_raw = {}

    scalars: dict[str, float] = {}
    for key, value in scalars_raw.items():
        try:
            scalars[str(key)] = float(value)
        except (TypeError, ValueError):
            continue

    degraded = len(normalized_series) < 2
    latest_points = []
    for row in normalized_series.values():
        if len(row) > 0:
            latest_points.append(pd.Timestamp(row.index[-1]) if not isinstance(row.index, pd.RangeIndex) else fetched_at)
    latest_ts = max(latest_points) if latest_points else fetched_at

    return IntermarketDataBundle(
        series=normalized_series,
        scalars=scalars,
        provider_metadata={
            "provider": clean_provider,
            "configured": clean_provider not in {"", "none"},
            "available": bool(normalized_series or scalars),
            "degraded": degraded,
            "series_count": len(normalized_series),
            "scalar_count": len(scalars),
            "latest_point_at": latest_ts.isoformat(),
            "fetched_at": fetched_at.isoformat(),
        },
    )
