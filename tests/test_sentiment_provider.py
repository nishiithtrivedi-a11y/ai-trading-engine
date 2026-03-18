from __future__ import annotations

import pandas as pd

from src.data.sentiment_sources import normalize_sentiment_payload


def test_normalize_sentiment_payload_preserves_provider_scores() -> None:
    payload = {
        "news": [
            {
                "headline": "RELIANCE beats estimates on strong growth",
                "date": "2026-03-10T08:00:00Z",
                "tickers": ["RELIANCE.NS"],
                "sentiment_score": 0.7,
                "source": "Wire",
            },
            {
                "headline": "Markets steady before policy meeting",
                "date": "2026-03-10T09:00:00Z",
                "sentiment_score": 0.1,
            },
        ]
    }
    bundle = normalize_sentiment_payload("finnhub", payload, symbol="RELIANCE.NS")

    assert len(bundle.ticker_news) == 1
    assert len(bundle.market_news) == 1
    assert bundle.ticker_news[0].provider_sentiment is True
    assert bundle.provider_metadata["provider_sentiment_count"] == 2


def test_normalize_sentiment_payload_no_news_mode() -> None:
    bundle = normalize_sentiment_payload("none", None, symbol="INFY.NS")
    assert bundle.provider_metadata["available"] is False
    assert bundle.provider_metadata["degraded"] is True


def test_normalize_sentiment_payload_stale_detection() -> None:
    payload = {
        "news": [
            {
                "headline": "Old headline",
                "date": "2024-01-01T00:00:00Z",
            }
        ]
    }
    bundle = normalize_sentiment_payload("eodhd", payload)
    assert bundle.provider_metadata["stale"] is True
