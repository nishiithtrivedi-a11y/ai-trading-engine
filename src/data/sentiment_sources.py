"""
Sentiment/news normalization helpers.

Provider payloads are normalized into a common structure while preserving the
difference between provider-supplied sentiment and lightweight derived signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import pandas as pd


_SENTIMENT_STALE_HOURS = 24


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


def _normalize_tickers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [chunk.strip().upper() for chunk in value.replace(";", ",").split(",")]
        return [item for item in parts if item]
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return []


@dataclass(frozen=True)
class NewsItem:
    headline: str
    published_at: pd.Timestamp
    source: str
    sentiment_score: float | None = None
    provider_sentiment: bool = False
    summary: str = ""
    url: str = ""
    tickers: list[str] = field(default_factory=list)
    category: str = ""
    relevance: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SentimentDataBundle:
    ticker_news: list[NewsItem] = field(default_factory=list)
    market_news: list[NewsItem] = field(default_factory=list)
    macro_news: list[NewsItem] = field(default_factory=list)
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def all_news(self) -> list[NewsItem]:
        return [*self.ticker_news, *self.market_news, *self.macro_news]

    def to_dict(self) -> dict[str, Any]:
        def _serialize(rows: list[NewsItem]) -> list[dict[str, Any]]:
            return [
                {
                    "headline": row.headline,
                    "published_at": row.published_at.isoformat(),
                    "source": row.source,
                    "sentiment_score": row.sentiment_score,
                    "provider_sentiment": row.provider_sentiment,
                    "summary": row.summary,
                    "url": row.url,
                    "tickers": list(row.tickers),
                    "category": row.category,
                    "relevance": row.relevance,
                    "metadata": dict(row.metadata),
                }
                for row in rows
            ]

        return {
            "ticker_news": _serialize(self.ticker_news),
            "market_news": _serialize(self.market_news),
            "macro_news": _serialize(self.macro_news),
            "provider_metadata": dict(self.provider_metadata),
        }


def _build_news_item(
    row: Mapping[str, Any],
    *,
    provider_name: str,
) -> NewsItem | None:
    headline = str(row.get("headline") or row.get("title") or "").strip()
    if not headline:
        return None
    published_at = _to_timestamp(
        row.get("published_at")
        or row.get("publishedAt")
        or row.get("time_published")
        or row.get("datetime")
        or row.get("date")
    )
    if published_at is None:
        return None

    raw_sentiment = (
        row.get("sentiment_score")
        or row.get("sentiment")
        or row.get("overall_sentiment_score")
        or row.get("sentimentScore")
    )
    sentiment_score = _to_float(raw_sentiment)
    provider_sentiment = sentiment_score is not None

    relevance = _to_float(row.get("relevance") or row.get("relevance_score"))
    category = str(row.get("category") or row.get("topic") or "").strip().lower()
    source = str(row.get("source") or row.get("publisher") or provider_name).strip()

    return NewsItem(
        headline=headline,
        published_at=published_at,
        source=source,
        sentiment_score=sentiment_score,
        provider_sentiment=provider_sentiment,
        summary=str(row.get("summary") or row.get("description") or "").strip(),
        url=str(row.get("url") or row.get("link") or "").strip(),
        tickers=_normalize_tickers(row.get("tickers") or row.get("symbols") or row.get("ticker")),
        category=category,
        relevance=relevance,
        metadata={k: v for k, v in row.items() if k not in {"headline", "title", "summary", "description", "url", "link"}},
    )


def normalize_sentiment_payload(
    provider_name: str,
    payload: Mapping[str, Any] | None,
    *,
    symbol: Optional[str] = None,
) -> SentimentDataBundle:
    clean_provider = str(provider_name or "none").strip().lower() or "none"
    clean_symbol = str(symbol).strip().upper() if symbol else ""
    fetched_at = _now_utc()

    if payload is None:
        return SentimentDataBundle(
            ticker_news=[],
            market_news=[],
            macro_news=[],
            provider_metadata={
                "provider": clean_provider,
                "configured": clean_provider != "none",
                "available": False,
                "degraded": True,
                "reason": "no_payload",
            },
        )

    ticker_rows = payload.get("ticker_news")
    market_rows = payload.get("market_news")
    macro_rows = payload.get("macro_news")
    generic_rows = payload.get("news") or payload.get("articles") or []

    if not isinstance(ticker_rows, list):
        ticker_rows = []
    if not isinstance(market_rows, list):
        market_rows = []
    if not isinstance(macro_rows, list):
        macro_rows = []
    if not isinstance(generic_rows, list):
        generic_rows = []

    ticker_news: list[NewsItem] = []
    market_news: list[NewsItem] = []
    macro_news: list[NewsItem] = []

    for row in ticker_rows:
        if isinstance(row, Mapping):
            item = _build_news_item(row, provider_name=clean_provider)
            if item is not None:
                ticker_news.append(item)

    for row in market_rows:
        if isinstance(row, Mapping):
            item = _build_news_item(row, provider_name=clean_provider)
            if item is not None:
                market_news.append(item)

    for row in macro_rows:
        if isinstance(row, Mapping):
            item = _build_news_item(row, provider_name=clean_provider)
            if item is not None:
                macro_news.append(item)

    if generic_rows:
        for row in generic_rows:
            if not isinstance(row, Mapping):
                continue
            item = _build_news_item(row, provider_name=clean_provider)
            if item is None:
                continue
            category = item.category
            if clean_symbol and clean_symbol in item.tickers:
                ticker_news.append(item)
            elif category in {"macro", "economy", "policy", "central_bank"}:
                macro_news.append(item)
            else:
                market_news.append(item)

    all_news = [*ticker_news, *market_news, *macro_news]
    latest_ts = max((row.published_at for row in all_news), default=None)
    stale = bool(
        latest_ts is not None
        and (fetched_at - latest_ts).total_seconds() > (_SENTIMENT_STALE_HOURS * 3600)
    )
    provider_sentiment_rows = sum(1 for row in all_news if row.provider_sentiment)
    degraded = len(all_news) == 0

    return SentimentDataBundle(
        ticker_news=ticker_news,
        market_news=market_news,
        macro_news=macro_news,
        provider_metadata={
            "provider": clean_provider,
            "configured": clean_provider != "none",
            "available": bool(all_news),
            "degraded": degraded,
            "stale": stale,
            "news_count": len(all_news),
            "ticker_news_count": len(ticker_news),
            "market_news_count": len(market_news),
            "macro_news_count": len(macro_news),
            "provider_sentiment_count": provider_sentiment_rows,
            "latest_news_at": latest_ts.isoformat() if latest_ts is not None else None,
            "fetched_at": fetched_at.isoformat(),
        },
    )
