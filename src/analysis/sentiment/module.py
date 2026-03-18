"""
Sentiment analysis module.

Computes lightweight sentiment/news features with a strict distinction between
provider-supplied sentiment and derived fallback values.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.analysis.base import BaseAnalysisModule
from src.data.sentiment_sources import NewsItem, SentimentDataBundle, normalize_sentiment_payload


_POSITIVE_TOKENS = {
    "beat",
    "upgrade",
    "surge",
    "record",
    "growth",
    "strong",
    "bullish",
    "outperform",
}
_NEGATIVE_TOKENS = {
    "miss",
    "downgrade",
    "fall",
    "lawsuit",
    "probe",
    "weak",
    "bearish",
    "warning",
    "fraud",
}
_EVENT_TOKENS = {
    "earnings",
    "results",
    "policy",
    "rate",
    "cpi",
    "inflation",
    "payroll",
    "fomc",
    "rbi",
}


class SentimentAnalysisModule(BaseAnalysisModule):
    """Sentiment/news module with provider and derived fallback support."""

    name: str = "sentiment"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return True

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        symbol = self._extract_symbol(context)
        bundle = self._resolve_bundle(symbol=symbol, context=context)
        metadata = dict(bundle.provider_metadata)

        allow_derived = bool(
            context.get("analysis_provider_settings", {}).get("allow_derived_sentiment_fallback", True)
        )

        features: dict[str, Any] = {
            "sentiment_available": 1.0 if metadata.get("available") else 0.0,
            "sentiment_degraded": 1.0 if metadata.get("degraded") else 0.0,
            "sentiment_stale": 1.0 if metadata.get("stale") else 0.0,
            "sentiment_provider": metadata.get("provider", "none"),
            "news_count_total": float(metadata.get("news_count", 0) or 0),
            "news_count_ticker": float(metadata.get("ticker_news_count", 0) or 0),
            "news_count_market": float(metadata.get("market_news_count", 0) or 0),
            "news_count_macro": float(metadata.get("macro_news_count", 0) or 0),
        }

        ticker_sentiment, ticker_provider_used = self._aggregate_sentiment(
            bundle.ticker_news,
            allow_derived=allow_derived,
        )
        market_sentiment, market_provider_used = self._aggregate_sentiment(
            bundle.market_news,
            allow_derived=allow_derived,
        )
        macro_sentiment, macro_provider_used = self._aggregate_sentiment(
            bundle.macro_news,
            allow_derived=allow_derived,
        )

        features["sentiment_ticker"] = ticker_sentiment
        features["sentiment_market"] = market_sentiment
        features["sentiment_macro"] = macro_sentiment
        features["sentiment_provider_score_used"] = 1.0 if any(
            [ticker_provider_used, market_provider_used, macro_provider_used]
        ) else 0.0
        features["sentiment_derived_score_used"] = 1.0 if (
            allow_derived and not features["sentiment_provider_score_used"]
        ) else 0.0

        now = pd.Timestamp.now(tz="UTC")
        all_news = bundle.all_news()
        recent_6h = [item for item in all_news if (now - item.published_at).total_seconds() <= 6 * 3600]
        recent_24h = [item for item in all_news if (now - item.published_at).total_seconds() <= 24 * 3600]

        features["news_intensity_6h"] = float(len(recent_6h))
        features["news_intensity_24h"] = float(len(recent_24h))
        features["news_intensity_72h"] = float(
            len([item for item in all_news if (now - item.published_at).total_seconds() <= 72 * 3600])
        )

        event_hits = sum(self._headline_event_hit(item.headline) for item in recent_24h)
        features["event_risk_news_flow"] = 1.0 if event_hits > 0 else 0.0
        features["event_risk_news_flow_high"] = 1.0 if event_hits >= 3 else 0.0

        overnight_window = [
            item
            for item in all_news
            if item.published_at.hour >= 18 or item.published_at.hour <= 8
        ]
        overnight_sentiment, _ = self._aggregate_sentiment(overnight_window, allow_derived=allow_derived)
        features["overnight_news_caution"] = 1.0 if overnight_sentiment is not None and overnight_sentiment < -0.2 else 0.0

        latest_news_at = self._latest_news_timestamp(all_news)
        if latest_news_at is not None:
            freshness_hours = max(0.0, float((now - latest_news_at).total_seconds() / 3600.0))
            features["sentiment_freshness_hours"] = freshness_hours
        else:
            features["sentiment_freshness_hours"] = None

        return features

    @staticmethod
    def _extract_symbol(context: dict) -> str:
        if "symbol" in context and str(context["symbol"]).strip():
            return str(context["symbol"]).strip().upper()
        signal = context.get("signal")
        if signal is not None and hasattr(signal, "symbol"):
            return str(signal.symbol).strip().upper()
        return ""

    @staticmethod
    def _resolve_bundle(symbol: str, context: dict) -> SentimentDataBundle:
        existing = context.get("sentiment_data")
        if isinstance(existing, SentimentDataBundle):
            return existing

        provider = str(
            context.get("sentiment_provider")
            or context.get("analysis_provider_selection", {}).get("sentiment", "none")
        ).strip().lower() or "none"
        payload = context.get("sentiment_payload")
        if payload is None and isinstance(existing, dict):
            payload = existing
        return normalize_sentiment_payload(provider, payload, symbol=symbol)

    @staticmethod
    def _headline_event_hit(headline: str) -> int:
        tokens = {token.strip(".,:;!?()[]{}\"'").lower() for token in str(headline).split()}
        return 1 if tokens & _EVENT_TOKENS else 0

    @staticmethod
    def _derived_score_from_headline(headline: str) -> float:
        tokens = {token.strip(".,:;!?()[]{}\"'").lower() for token in str(headline).split()}
        pos_hits = len(tokens & _POSITIVE_TOKENS)
        neg_hits = len(tokens & _NEGATIVE_TOKENS)
        score = (pos_hits - neg_hits) / max(1.0, float(pos_hits + neg_hits))
        return float(max(min(score, 1.0), -1.0))

    def _aggregate_sentiment(
        self,
        rows: list[NewsItem],
        *,
        allow_derived: bool,
    ) -> tuple[float | None, bool]:
        if not rows:
            return None, False

        provider_scores = [
            float(row.sentiment_score)
            for row in rows
            if row.provider_sentiment and row.sentiment_score is not None
        ]
        if provider_scores:
            return float(sum(provider_scores) / len(provider_scores)), True

        if not allow_derived:
            return None, False

        derived_scores = [self._derived_score_from_headline(row.headline) for row in rows]
        if not derived_scores:
            return None, False
        return float(sum(derived_scores) / len(derived_scores)), False

    @staticmethod
    def _latest_news_timestamp(rows: list[NewsItem]) -> pd.Timestamp | None:
        if not rows:
            return None
        return max(row.published_at for row in rows)

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Sentiment/news module with provider + derived fallback support.",
        }
