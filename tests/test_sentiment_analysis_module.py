from __future__ import annotations

import pandas as pd

from src.analysis.sentiment.module import SentimentAnalysisModule


def _price_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100, 101],
            "high": [101, 102],
            "low": [99, 100],
            "close": [100.5, 101.3],
            "volume": [1000, 1200],
        },
        index=pd.date_range("2026-03-01", periods=2, freq="D", name="timestamp"),
    )


def test_sentiment_module_uses_provider_scores_when_available() -> None:
    module = SentimentAnalysisModule()
    features = module.build_features(
        _price_data(),
        {
            "symbol": "RELIANCE.NS",
            "sentiment_provider": "finnhub",
            "sentiment_payload": {
                "ticker_news": [
                    {
                        "headline": "RELIANCE beats estimates",
                        "date": "2026-03-10T09:00:00Z",
                        "sentiment_score": 0.8,
                        "tickers": ["RELIANCE.NS"],
                    }
                ],
                "market_news": [
                    {
                        "headline": "Broad market cautious ahead of policy rate decision",
                        "date": "2026-03-10T10:00:00Z",
                        "sentiment_score": -0.2,
                    }
                ],
            },
        },
    )

    assert features["sentiment_available"] == 1.0
    assert features["sentiment_provider_score_used"] == 1.0
    assert features["sentiment_ticker"] == 0.8
    assert features["event_risk_news_flow"] in {0.0, 1.0}


def test_sentiment_module_fallback_derives_score_from_headlines() -> None:
    module = SentimentAnalysisModule()
    features = module.build_features(
        _price_data(),
        {
            "symbol": "INFY.NS",
            "sentiment_provider": "none",
            "analysis_provider_settings": {"allow_derived_sentiment_fallback": True},
            "sentiment_payload": {
                "ticker_news": [
                    {"headline": "INFY upgrade after strong growth outlook", "date": "2026-03-10T09:00:00Z"},
                    {"headline": "INFY faces lawsuit warning", "date": "2026-03-10T10:00:00Z"},
                ]
            },
        },
    )

    assert features["sentiment_provider_score_used"] == 0.0
    assert features["sentiment_derived_score_used"] == 1.0
    assert features["sentiment_ticker"] is not None


def test_sentiment_module_no_news_mode_safe() -> None:
    module = SentimentAnalysisModule()
    features = module.build_features(_price_data(), {"sentiment_provider": "none", "sentiment_payload": None})
    assert features["sentiment_available"] == 0.0
    assert features["news_count_total"] == 0.0


def test_sentiment_module_health_ok() -> None:
    health = SentimentAnalysisModule().health_check()
    assert health["status"] == "ok"
