"""
Macro provider normalization helpers.

This module normalizes provider payloads into a stable internal shape used by
the macro analysis module. It is data-only and safe in offline environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd


_MACRO_STALE_DAYS = 21


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        clean = value.strip().replace(",", "")
        if not clean:
            return None
        value = clean
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(out):
        return None
    return out


def _to_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        ts = pd.Timestamp(value)
    except Exception:  # noqa: BLE001
        return None
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


@dataclass(frozen=True)
class MacroIndicatorPoint:
    indicator: str
    value: float
    timestamp: pd.Timestamp
    country: str
    source: str


@dataclass(frozen=True)
class MacroEvent:
    event_name: str
    event_time: pd.Timestamp
    country: str
    importance: str = "medium"
    category: str = ""
    policy_related: bool = False
    source: str = "none"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MacroDataBundle:
    indicators: dict[str, list[MacroIndicatorPoint]] = field(default_factory=dict)
    events: list[MacroEvent] = field(default_factory=list)
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def latest(self, indicator: str) -> MacroIndicatorPoint | None:
        rows = self.indicators.get(indicator, [])
        if not rows:
            return None
        return max(rows, key=lambda row: row.timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicators": {
                key: [
                    {
                        "indicator": row.indicator,
                        "value": row.value,
                        "timestamp": row.timestamp.isoformat(),
                        "country": row.country,
                        "source": row.source,
                    }
                    for row in rows
                ]
                for key, rows in self.indicators.items()
            },
            "events": [
                {
                    "event_name": event.event_name,
                    "event_time": event.event_time.isoformat(),
                    "country": event.country,
                    "importance": event.importance,
                    "category": event.category,
                    "policy_related": event.policy_related,
                    "source": event.source,
                    "metadata": dict(event.metadata),
                }
                for event in self.events
            ],
            "provider_metadata": dict(self.provider_metadata),
        }


def _normalize_indicator_points(
    indicator: str,
    value: Any,
    *,
    country: str,
    provider_name: str,
) -> list[MacroIndicatorPoint]:
    rows: list[MacroIndicatorPoint] = []

    def _append_point(raw_value: Any, raw_ts: Any) -> None:
        val = _to_float(raw_value)
        ts = _to_timestamp(raw_ts) or _now_utc()
        if val is None:
            return
        rows.append(
            MacroIndicatorPoint(
                indicator=indicator,
                value=val,
                timestamp=ts,
                country=country,
                source=provider_name,
            )
        )

    if isinstance(value, Mapping):
        if isinstance(value.get("series"), list):
            for row in value.get("series", []):
                if isinstance(row, Mapping):
                    _append_point(row.get("value"), row.get("timestamp") or row.get("date"))
        else:
            _append_point(value.get("value"), value.get("timestamp") or value.get("date"))
    elif isinstance(value, list):
        for row in value:
            if isinstance(row, Mapping):
                _append_point(row.get("value"), row.get("timestamp") or row.get("date"))
            else:
                _append_point(row, _now_utc())
    else:
        _append_point(value, _now_utc())

    return rows


def _normalize_events(
    rows: list[Any],
    *,
    country: str,
    provider_name: str,
) -> list[MacroEvent]:
    events: list[MacroEvent] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or row.get("event") or row.get("title") or "").strip()
        if not name:
            continue
        event_time = _to_timestamp(row.get("timestamp") or row.get("date") or row.get("time"))
        if event_time is None:
            continue
        importance = str(row.get("importance") or row.get("impact") or "medium").strip().lower()
        category = str(row.get("category") or row.get("type") or "").strip().lower()
        policy_related = bool(
            row.get("policy_related")
            or "policy" in name.lower()
            or "central bank" in name.lower()
            or "rate" in name.lower()
            or category in {"policy", "rates"}
        )
        events.append(
            MacroEvent(
                event_name=name,
                event_time=event_time,
                country=str(row.get("country") or country).strip().upper() or country,
                importance=importance,
                category=category,
                policy_related=policy_related,
                source=provider_name,
                metadata={k: v for k, v in row.items() if k not in {"name", "event", "title", "timestamp", "date", "time"}},
            )
        )
    return events


def normalize_macro_payload(
    provider_name: str,
    payload: Mapping[str, Any] | None,
    *,
    default_country: str = "US",
) -> MacroDataBundle:
    clean_provider = str(provider_name or "none").strip().lower() or "none"
    country = str(default_country).strip().upper() or "US"
    fetched_at = _now_utc()

    if payload is None:
        return MacroDataBundle(
            indicators={},
            events=[],
            provider_metadata={
                "provider": clean_provider,
                "configured": clean_provider != "none",
                "available": False,
                "degraded": True,
                "reason": "no_payload",
            },
        )

    indicators_root = payload.get("indicators")
    if not isinstance(indicators_root, Mapping):
        indicators_root = payload

    indicator_aliases: dict[str, tuple[str, ...]] = {
        "cpi": ("cpi", "inflation", "consumer_price_index"),
        "ppi": ("ppi", "producer_price_index"),
        "gdp": ("gdp", "gross_domestic_product"),
        "unemployment": ("unemployment", "unemployment_rate", "jobless_rate"),
        "payrolls": ("payrolls", "nonfarm_payrolls", "nfp"),
        "policy_rate": ("policy_rate", "fed_funds", "repo_rate", "interest_rate"),
        "treasury_2y": ("treasury_2y", "us02y", "yield_2y"),
        "treasury_10y": ("treasury_10y", "us10y", "yield_10y"),
    }

    normalized_indicators: dict[str, list[MacroIndicatorPoint]] = {}
    for indicator, aliases in indicator_aliases.items():
        raw_value = None
        for key in aliases:
            if key in indicators_root:
                raw_value = indicators_root.get(key)
                break
        if raw_value is None:
            continue
        rows = _normalize_indicator_points(
            indicator,
            raw_value,
            country=country,
            provider_name=clean_provider,
        )
        if rows:
            normalized_indicators[indicator] = rows

    events_raw = payload.get("events")
    if not isinstance(events_raw, list):
        events_raw = payload.get("calendar")
    if not isinstance(events_raw, list):
        events_raw = payload.get("economic_calendar")
    if not isinstance(events_raw, list):
        events_raw = []
    events = _normalize_events(events_raw, country=country, provider_name=clean_provider)

    latest_timestamps = [
        max(rows, key=lambda row: row.timestamp).timestamp
        for rows in normalized_indicators.values()
        if rows
    ]
    as_of = max(latest_timestamps) if latest_timestamps else None
    stale = bool(as_of is not None and (fetched_at - as_of).days > _MACRO_STALE_DAYS)
    degraded = len(normalized_indicators) < 2

    return MacroDataBundle(
        indicators=normalized_indicators,
        events=events,
        provider_metadata={
            "provider": clean_provider,
            "configured": clean_provider != "none",
            "available": bool(normalized_indicators or events),
            "degraded": degraded,
            "stale": stale,
            "country": country,
            "indicator_count": len(normalized_indicators),
            "event_count": len(events),
            "as_of": as_of.isoformat() if as_of is not None else None,
            "fetched_at": fetched_at.isoformat(),
        },
    )
