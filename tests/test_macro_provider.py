from __future__ import annotations

from src.data.macro_sources import normalize_macro_payload


def test_normalize_macro_payload_builds_indicators_and_events() -> None:
    payload = {
        "indicators": {
            "cpi": [
                {"date": "2026-01-01", "value": 3.1},
                {"date": "2026-02-01", "value": 3.3},
            ],
            "gdp": [{"date": "2025-12-31", "value": 2.4}],
            "policy_rate": {"date": "2026-02-15", "value": 5.25},
            "treasury_2y": {"date": "2026-02-15", "value": 4.7},
            "treasury_10y": {"date": "2026-02-15", "value": 4.2},
        },
        "events": [
            {"name": "FOMC Rate Decision", "date": "2026-03-20T18:00:00Z", "importance": "high"},
            {"name": "CPI Release", "date": "2026-03-12T12:30:00Z", "importance": "medium"},
        ],
    }

    bundle = normalize_macro_payload("alphavantage", payload, default_country="US")
    assert "cpi" in bundle.indicators
    assert len(bundle.indicators["cpi"]) == 2
    assert bundle.latest("policy_rate") is not None
    assert len(bundle.events) == 2
    assert bundle.events[0].country == "US"


def test_normalize_macro_payload_handles_partial_data() -> None:
    payload = {"indicators": {"cpi": [{"date": "2026-01-01", "value": 3.2}]}}
    bundle = normalize_macro_payload("fmp", payload)
    assert bundle.provider_metadata["indicator_count"] == 1
    assert bundle.provider_metadata["degraded"] is True


def test_normalize_macro_payload_none_is_degraded() -> None:
    bundle = normalize_macro_payload("none", None)
    assert bundle.provider_metadata["available"] is False
    assert bundle.provider_metadata["degraded"] is True
