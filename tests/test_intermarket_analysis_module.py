from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.intermarket.module import IntermarketAnalysisModule


def _asset_df() -> pd.DataFrame:
    close = np.linspace(100, 110, 30)
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 0.5,
            "low": close - 0.8,
            "close": close,
            "volume": np.linspace(1000, 1200, 30),
        },
        index=pd.date_range("2026-01-01", periods=30, freq="D", name="timestamp"),
    )


def test_intermarket_module_builds_correlation_features() -> None:
    module = IntermarketAnalysisModule()
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    series = pd.Series(np.linspace(0.001, 0.02, 30), index=idx)
    features = module.build_features(
        _asset_df(),
        {
            "intermarket_provider": "derived",
            "intermarket_payload": {
                "series": {
                    "benchmark_returns": series,
                    "sector_returns": series * 0.9,
                    "rates_returns": series * -0.6,
                    "usd_returns": series * 0.2,
                    "commodity_returns": series * -0.2,
                }
            },
        },
    )

    assert features["intermarket_available"] == 1.0
    assert features["intermarket_corr_asset_benchmark"] is not None
    assert features["intermarket_confirmation_flag"] in {0.0, 1.0}
    assert features["intermarket_coverage"] >= 2.0


def test_intermarket_module_handles_sparse_payload() -> None:
    module = IntermarketAnalysisModule()
    features = module.build_features(
        _asset_df(),
        {"intermarket_provider": "derived", "intermarket_payload": {"series": {"benchmark_returns": [0.01]}}},
    )
    assert features["intermarket_degraded"] == 1.0
    assert features["intermarket_coverage"] == 0.0


def test_intermarket_module_health_ok() -> None:
    health = IntermarketAnalysisModule().health_check()
    assert health["status"] == "ok"
