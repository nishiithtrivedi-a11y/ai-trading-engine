from __future__ import annotations

import pandas as pd

from src.analysis.fundamental.module import FundamentalAnalysisModule


def _sample_price_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1_000_000, 1_100_000, 1_200_000],
        },
        index=pd.date_range("2026-01-01", periods=3, freq="D", name="timestamp"),
    )


def test_fundamental_module_builds_factor_outputs() -> None:
    module = FundamentalAnalysisModule()
    features = module.build_features(
        _sample_price_data(),
        {
            "symbol": "RELIANCE.NS",
            "fundamentals_provider": "fmp",
            "fundamental_payload": {
                "marketCap": 200000000000,
                "PERatio": 18.0,
                "priceToBookRatio": 2.4,
                "debtToEquity": 0.35,
                "returnOnEquity": 0.2,
                "returnOnAssets": 0.08,
                "revenueGrowthTTM": 0.15,
                "earningsGrowthTTM": 0.12,
                "freeCashFlowYield": 4.2,
                "operatingMargin": 0.24,
                "nextEarningsDate": "2026-04-01T10:00:00Z",
            },
        },
    )

    assert features["fundamental_available"] == 1.0
    assert features["fundamental_degraded"] == 0.0
    assert 0.0 <= float(features["factor_value"]) <= 1.0
    assert 0.0 <= float(features["factor_quality"]) <= 1.0
    assert 0.0 <= float(features["factor_growth"]) <= 1.0
    assert "event_risk_earnings_within_7d" in features


def test_fundamental_module_handles_missing_fields_gracefully() -> None:
    module = FundamentalAnalysisModule()
    features = module.build_features(
        _sample_price_data(),
        {
            "symbol": "INFY.NS",
            "fundamentals_provider": "none",
            "fundamental_payload": None,
        },
    )

    assert features["fundamental_degraded"] == 1.0
    assert features["fundamental_provider"] == "none"
    assert features["factor_value"] is None
    assert features["event_risk_earnings_within_7d"] == 0.0


def test_fundamental_module_health_ok() -> None:
    health = FundamentalAnalysisModule().health_check()
    assert health["status"] == "ok"
