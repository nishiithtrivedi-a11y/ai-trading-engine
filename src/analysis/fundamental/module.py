"""
Fundamental analysis module.

Computes explainable factor-style outputs from normalized fundamental payloads.
The module remains safe when no provider data is available by returning explicit
availability/degraded flags instead of raising.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analysis.base import BaseAnalysisModule
from src.data.fundamental_sources import (
    FundamentalDataBundle,
    normalize_fundamental_payload,
)


def _pct_to_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    val = float(value)
    if abs(val) > 1.0 and abs(val) <= 100.0:
        return val / 100.0
    return val


def _score_from_range(
    value: float | None,
    *,
    lower: float,
    upper: float,
    invert: bool = False,
) -> float | None:
    if value is None:
        return None
    if upper <= lower:
        return None
    clipped = min(max(float(value), lower), upper)
    score = (clipped - lower) / (upper - lower)
    if invert:
        score = 1.0 - score
    return float(min(max(score, 0.0), 1.0))


def _mean(values: list[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return float(sum(valid) / len(valid))


class FundamentalAnalysisModule(BaseAnalysisModule):
    """Fundamental factor module: value, quality, growth, leverage, event risk."""

    name: str = "fundamental"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return str(instrument_type).strip().lower() in {
            "",
            "equity",
            "stock",
            "etf",
            "index",
        }

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        symbol = self._extract_symbol(context)
        bundle = self._resolve_bundle(symbol=symbol, context=context)
        snapshot = bundle.snapshot

        features: dict[str, Any] = {
            "fundamental_available": 0.0 if snapshot.degraded and snapshot.market_cap is None else 1.0,
            "fundamental_degraded": 1.0 if snapshot.degraded else 0.0,
            "fundamental_stale": 1.0 if snapshot.stale else 0.0,
            "fundamental_provider": snapshot.provider,
            "fundamental_field_coverage": (
                float(
                    sum(1 for value in [
                        snapshot.market_cap,
                        snapshot.eps,
                        snapshot.pe,
                        snapshot.pb,
                        snapshot.debt_to_equity,
                        snapshot.roe,
                        snapshot.roa,
                        snapshot.revenue_growth,
                        snapshot.earnings_growth,
                        snapshot.fcf_yield,
                    ] if value is not None)
                )
                / 10.0
            ),
        }

        # Raw normalized metrics
        features.update(
            {
                "market_cap": snapshot.market_cap,
                "shares_outstanding": snapshot.shares_outstanding,
                "eps": snapshot.eps,
                "pe": snapshot.pe,
                "pb": snapshot.pb,
                "debt_to_equity": snapshot.debt_to_equity,
                "roe": snapshot.roe,
                "roa": snapshot.roa,
                "revenue_growth": snapshot.revenue_growth,
                "earnings_growth": snapshot.earnings_growth,
                "free_cash_flow": snapshot.free_cash_flow,
                "fcf_yield": snapshot.fcf_yield,
                "operating_margin": snapshot.operating_margin,
                "net_margin": snapshot.net_margin,
                "gross_margin": snapshot.gross_margin,
                "dividend_yield": snapshot.dividend_yield,
            }
        )

        # Factor outputs (0..1), explainable and additive.
        value_score = _mean(
            [
                _score_from_range(snapshot.pe, lower=5.0, upper=40.0, invert=True),
                _score_from_range(snapshot.pb, lower=0.5, upper=8.0, invert=True),
                _score_from_range(snapshot.fcf_yield, lower=0.0, upper=10.0),
                _score_from_range(snapshot.dividend_yield, lower=0.0, upper=8.0),
            ]
        )
        quality_score = _mean(
            [
                _score_from_range(_pct_to_ratio(snapshot.roe), lower=0.0, upper=0.3),
                _score_from_range(_pct_to_ratio(snapshot.roa), lower=0.0, upper=0.15),
                _score_from_range(_pct_to_ratio(snapshot.net_margin), lower=-0.1, upper=0.4),
                _score_from_range(snapshot.debt_to_equity, lower=0.0, upper=3.0, invert=True),
            ]
        )
        growth_score = _mean(
            [
                _score_from_range(_pct_to_ratio(snapshot.revenue_growth), lower=-0.2, upper=0.4),
                _score_from_range(_pct_to_ratio(snapshot.earnings_growth), lower=-0.4, upper=0.6),
            ]
        )
        leverage_score = _score_from_range(snapshot.debt_to_equity, lower=0.0, upper=3.0, invert=True)
        profitability_score = _mean(
            [
                _score_from_range(_pct_to_ratio(snapshot.gross_margin), lower=0.0, upper=0.7),
                _score_from_range(_pct_to_ratio(snapshot.operating_margin), lower=-0.1, upper=0.4),
                _score_from_range(_pct_to_ratio(snapshot.net_margin), lower=-0.1, upper=0.35),
            ]
        )
        cash_flow_quality = _mean(
            [
                _score_from_range(snapshot.fcf_yield, lower=-2.0, upper=10.0),
                1.0 if (snapshot.free_cash_flow is not None and snapshot.free_cash_flow > 0) else 0.0,
            ]
        )

        features["factor_value"] = value_score
        features["factor_quality"] = quality_score
        features["factor_growth"] = growth_score
        features["factor_leverage"] = leverage_score
        features["factor_profitability"] = profitability_score
        features["factor_cash_flow_quality"] = cash_flow_quality

        event_days = self._days_to_earnings(bundle)
        features["event_earnings_days"] = float(event_days) if event_days is not None else None
        features["event_risk_earnings_within_7d"] = 1.0 if event_days is not None and event_days <= 7 else 0.0
        features["event_risk_earnings_within_3d"] = 1.0 if event_days is not None and event_days <= 3 else 0.0

        if snapshot.as_of is not None:
            freshness_days = max(0.0, float((snapshot.fetched_at - snapshot.as_of).total_seconds() / 86400.0))
            features["fundamental_freshness_days"] = freshness_days
        else:
            features["fundamental_freshness_days"] = None

        return features

    @staticmethod
    def _extract_symbol(context: dict) -> str:
        if "symbol" in context and str(context["symbol"]).strip():
            return str(context["symbol"]).strip().upper()
        signal = context.get("signal")
        if signal is not None and hasattr(signal, "symbol"):
            return str(signal.symbol).strip().upper()
        return "UNKNOWN"

    @staticmethod
    def _resolve_bundle(symbol: str, context: dict) -> FundamentalDataBundle:
        existing = context.get("fundamental_data")
        if isinstance(existing, FundamentalDataBundle):
            return existing

        provider = str(
            context.get("fundamentals_provider")
            or context.get("fundamental_provider")
            or context.get("analysis_provider_selection", {}).get("fundamentals", "none")
        ).strip().lower() or "none"
        payload = context.get("fundamental_payload")
        if payload is None and isinstance(existing, dict):
            payload = existing
        return normalize_fundamental_payload(provider, symbol, payload)

    @staticmethod
    def _days_to_earnings(bundle: FundamentalDataBundle) -> int | None:
        if not bundle.events:
            return None
        earnings_events = [event for event in bundle.events if event.event_type == "earnings"]
        if not earnings_events:
            return None
        event = min(earnings_events, key=lambda row: row.event_time)
        if event.days_to_event is not None:
            return int(event.days_to_event)
        delta = event.event_time - pd.Timestamp.now(tz="UTC")
        if delta.total_seconds() < 0:
            return None
        return int(delta.total_seconds() // 86400)

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Fundamental factor module with value/quality/growth/event-risk outputs.",
        }
