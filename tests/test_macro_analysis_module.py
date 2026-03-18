from __future__ import annotations

import pandas as pd

from src.analysis.macro.module import MacroAnalysisModule


def _data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.0],
            "volume": [1000, 1100, 1200],
        },
        index=pd.date_range("2026-03-01", periods=3, freq="D", name="timestamp"),
    )


def test_macro_module_outputs_regime_and_event_risk() -> None:
    module = MacroAnalysisModule()
    features = module.build_features(
        _data(),
        {
            "macro_provider": "alphavantage",
            "macro_payload": {
                "indicators": {
                    "cpi": [
                        {"date": "2025-12-01", "value": 2.8},
                        {"date": "2026-01-01", "value": 3.0},
                        {"date": "2026-02-01", "value": 3.2},
                    ],
                    "gdp": [
                        {"date": "2025-09-01", "value": 2.0},
                        {"date": "2025-12-01", "value": 2.2},
                        {"date": "2026-03-01", "value": 2.4},
                    ],
                    "policy_rate": {"date": "2026-03-01", "value": 5.25},
                    "treasury_2y": {"date": "2026-03-01", "value": 4.7},
                    "treasury_10y": {"date": "2026-03-01", "value": 4.3},
                },
                "events": [
                    {
                        "name": "FOMC Rate Decision",
                        "date": (pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=8)).isoformat(),
                        "importance": "high",
                    }
                ],
            },
        },
    )

    assert features["macro_available"] == 1.0
    assert features["macro_regime"] in {"neutral", "stagflation_risk", "growth_supportive", "tightening_risk"}
    assert features["event_risk_macro_within_24h"] == 1.0
    assert features["macro_blackout_window"] == 1.0


def test_macro_module_handles_missing_payload() -> None:
    module = MacroAnalysisModule()
    features = module.build_features(_data(), {"macro_provider": "none", "macro_payload": None})

    assert features["macro_available"] == 0.0
    assert features["macro_degraded"] == 1.0
    assert features["macro_event_count"] == 0.0


def test_macro_module_health_ok() -> None:
    health = MacroAnalysisModule().health_check()
    assert health["status"] == "ok"
