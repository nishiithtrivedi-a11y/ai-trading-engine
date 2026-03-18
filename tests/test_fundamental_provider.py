from __future__ import annotations

import pandas as pd

from src.data.fundamental_sources import normalize_fundamental_payload


def test_normalize_fundamental_payload_maps_key_metrics() -> None:
    payload = {
        "name": "Reliance Industries",
        "sector": "Energy",
        "industry": "Integrated Oil & Gas",
        "marketCap": "200000000000",
        "epsTTM": "95.2",
        "PERatio": "22.5",
        "priceToBookRatio": "3.4",
        "debtToEquity": "0.45",
        "returnOnEquity": "0.18",
        "revenueGrowthTTM": "0.12",
        "earningsGrowthTTM": "0.08",
        "freeCashFlow": "12000000000",
        "dividendYield": "0.9",
        "nextEarningsDate": "2026-04-20T12:00:00Z",
    }

    bundle = normalize_fundamental_payload("alphavantage", "RELIANCE.NS", payload)
    snapshot = bundle.snapshot

    assert snapshot.symbol == "RELIANCE.NS"
    assert snapshot.company_name == "Reliance Industries"
    assert snapshot.sector == "Energy"
    assert snapshot.market_cap == 200000000000.0
    assert snapshot.pe == 22.5
    assert snapshot.debt_to_equity == 0.45
    assert snapshot.roe == 0.18
    assert snapshot.revenue_growth == 0.12
    assert snapshot.earnings_growth == 0.08
    assert snapshot.fcf_yield is not None
    assert snapshot.field_sources["fcf_yield"] in {"provider", "derived"}
    assert len(bundle.events) == 1
    assert bundle.events[0].event_type == "earnings"


def test_normalize_fundamental_payload_handles_missing_payload() -> None:
    bundle = normalize_fundamental_payload("none", "INFY.NS", None)
    snapshot = bundle.snapshot

    assert snapshot.symbol == "INFY.NS"
    assert snapshot.degraded is True
    assert bundle.provider_metadata["available"] is False
    assert bundle.provider_metadata["reason"] == "no_payload"


def test_normalize_fundamental_payload_uses_supplied_as_of_for_staleness() -> None:
    old_as_of = pd.Timestamp("2025-01-01T00:00:00Z")
    payload = {
        "name": "Old Co",
        "marketCap": "1000",
        "EPS": "1.0",
    }
    bundle = normalize_fundamental_payload(
        "fmp",
        "OLD.NS",
        payload,
        as_of=old_as_of,
    )
    assert bundle.snapshot.stale is True
