"""
Macro analysis module.

Produces explainable macro context features from normalized indicator/event
payloads. Missing data paths stay explicit and non-breaking.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analysis.base import BaseAnalysisModule
from src.data.macro_sources import MacroDataBundle, normalize_macro_payload


def _mean(values: list[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return float(sum(valid) / len(valid))


def _slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    x = list(range(len(values)))
    x_mean = sum(x) / len(x)
    y_mean = sum(values) / len(values)
    denom = sum((item - x_mean) ** 2 for item in x)
    if denom <= 0:
        return None
    numer = sum((item - x_mean) * (value - y_mean) for item, value in zip(x, values))
    return float(numer / denom)


class MacroAnalysisModule(BaseAnalysisModule):
    """Macro regime/context module: inflation/growth/rates/events/risk-on overlay."""

    name: str = "macro"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return True

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        bundle = self._resolve_bundle(context)
        metadata = dict(bundle.provider_metadata)
        features: dict[str, Any] = {
            "macro_available": 1.0 if metadata.get("available") else 0.0,
            "macro_degraded": 1.0 if metadata.get("degraded") else 0.0,
            "macro_stale": 1.0 if metadata.get("stale") else 0.0,
            "macro_provider": metadata.get("provider", "none"),
            "macro_indicator_count": float(metadata.get("indicator_count", 0) or 0),
            "macro_event_count": float(metadata.get("event_count", 0) or 0),
        }

        latest = {
            "cpi": self._latest_value(bundle, "cpi"),
            "ppi": self._latest_value(bundle, "ppi"),
            "gdp": self._latest_value(bundle, "gdp"),
            "unemployment": self._latest_value(bundle, "unemployment"),
            "payrolls": self._latest_value(bundle, "payrolls"),
            "policy_rate": self._latest_value(bundle, "policy_rate"),
            "treasury_2y": self._latest_value(bundle, "treasury_2y"),
            "treasury_10y": self._latest_value(bundle, "treasury_10y"),
        }
        features.update({f"macro_{key}": value for key, value in latest.items()})

        cpi_series = self._series_values(bundle, "cpi")
        gdp_series = self._series_values(bundle, "gdp")
        unemployment_series = self._series_values(bundle, "unemployment")

        inflation_slope = _slope(cpi_series[-4:]) if cpi_series else None
        growth_slope = _slope(gdp_series[-4:]) if gdp_series else None
        unemployment_slope = _slope(unemployment_series[-4:]) if unemployment_series else None

        inflation_trend = 0.0
        if inflation_slope is not None:
            inflation_trend = 1.0 if inflation_slope > 0 else -1.0

        growth_trend = 0.0
        if growth_slope is not None:
            growth_trend = 1.0 if growth_slope > 0 else -1.0
        elif unemployment_slope is not None:
            growth_trend = -1.0 if unemployment_slope > 0 else 1.0

        rate_pressure = _mean(
            [
                latest.get("policy_rate"),
                latest.get("cpi"),
                latest.get("treasury_2y"),
            ]
        )
        if rate_pressure is not None:
            rate_pressure = float(max(min(rate_pressure / 10.0, 2.0), -2.0))

        yield_spread = None
        if latest.get("treasury_10y") is not None and latest.get("treasury_2y") is not None:
            yield_spread = float(latest["treasury_10y"] - latest["treasury_2y"])

        features["macro_inflation_trend"] = inflation_trend
        features["macro_growth_trend"] = growth_trend
        features["macro_rate_pressure"] = rate_pressure
        features["macro_yield_curve_spread"] = yield_spread
        features["macro_yield_curve_inversion"] = 1.0 if yield_spread is not None and yield_spread < 0 else 0.0

        macro_regime = "neutral"
        risk_on_overlay = 0.0
        if inflation_trend > 0 and growth_trend <= 0:
            macro_regime = "stagflation_risk"
            risk_on_overlay = -1.0
        elif growth_trend > 0 and inflation_trend <= 0:
            macro_regime = "growth_supportive"
            risk_on_overlay = 1.0
        elif inflation_trend > 0 and (rate_pressure is not None and rate_pressure > 0.8):
            macro_regime = "tightening_risk"
            risk_on_overlay = -1.0

        features["macro_regime"] = macro_regime
        features["macro_risk_on_overlay"] = risk_on_overlay

        next_event_hours, high_impact_hours, policy_event_hours = self._event_risk(bundle)
        features["macro_next_event_hours"] = next_event_hours
        features["event_risk_macro_within_24h"] = 1.0 if next_event_hours is not None and next_event_hours <= 24 else 0.0
        features["event_risk_macro_within_6h"] = 1.0 if next_event_hours is not None and next_event_hours <= 6 else 0.0
        features["event_risk_high_impact_within_24h"] = (
            1.0 if high_impact_hours is not None and high_impact_hours <= 24 else 0.0
        )
        features["macro_blackout_window"] = (
            1.0 if policy_event_hours is not None and policy_event_hours <= 12 else 0.0
        )

        latest_ts = self._latest_timestamp(bundle)
        if latest_ts is not None:
            freshness_hours = max(0.0, float((pd.Timestamp.now(tz="UTC") - latest_ts).total_seconds() / 3600.0))
            features["macro_freshness_hours"] = freshness_hours
        else:
            features["macro_freshness_hours"] = None

        return features

    @staticmethod
    def _resolve_bundle(context: dict) -> MacroDataBundle:
        existing = context.get("macro_data")
        if isinstance(existing, MacroDataBundle):
            return existing

        provider = str(
            context.get("macro_provider")
            or context.get("analysis_provider_selection", {}).get("macro", "none")
        ).strip().lower() or "none"
        payload = context.get("macro_payload")
        if payload is None and isinstance(existing, dict):
            payload = existing
        country = str(context.get("country") or context.get("region") or "US").strip().upper()
        return normalize_macro_payload(provider, payload, default_country=country)

    @staticmethod
    def _series_values(bundle: MacroDataBundle, indicator: str) -> list[float]:
        rows = bundle.indicators.get(indicator, [])
        ordered = sorted(rows, key=lambda row: row.timestamp)
        return [float(row.value) for row in ordered]

    @staticmethod
    def _latest_value(bundle: MacroDataBundle, indicator: str) -> float | None:
        row = bundle.latest(indicator)
        if row is None:
            return None
        return float(row.value)

    @staticmethod
    def _latest_timestamp(bundle: MacroDataBundle) -> pd.Timestamp | None:
        timestamps = [
            row.timestamp
            for rows in bundle.indicators.values()
            for row in rows
        ]
        if not timestamps:
            return None
        return max(timestamps)

    @staticmethod
    def _event_risk(bundle: MacroDataBundle) -> tuple[float | None, float | None, float | None]:
        now = pd.Timestamp.now(tz="UTC")
        upcoming = [event for event in bundle.events if event.event_time >= now]
        if not upcoming:
            return None, None, None

        def _hours_to(event_time: pd.Timestamp) -> float:
            return max(0.0, float((event_time - now).total_seconds() / 3600.0))

        next_event_hours = min(_hours_to(event.event_time) for event in upcoming)

        high_impact_events = [
            event
            for event in upcoming
            if event.importance in {"high", "critical"}
        ]
        high_impact_hours = (
            min(_hours_to(event.event_time) for event in high_impact_events)
            if high_impact_events
            else None
        )

        policy_events = [event for event in upcoming if event.policy_related]
        policy_event_hours = (
            min(_hours_to(event.event_time) for event in policy_events)
            if policy_events
            else None
        )
        return next_event_hours, high_impact_hours, policy_event_hours

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Macro context module with regime, trend, and event-risk outputs.",
        }
