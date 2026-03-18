from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.registry import AnalysisRegistry
from src.config.analysis_profiles import AnalysisProfileLoader
from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderFactory
from src.scanners.config import ScannerConfig, StrategyScanSpec
from src.scanners.data_gateway import DataGateway
from src.scanners.engine import StockScannerEngine
from src.strategies.base_strategy import BaseStrategy, Signal


class _AlwaysBuyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.BUY


def _write_symbol_csv(data_dir: Path, symbol: str, suffix: str = "1D") -> None:
    stem = symbol.replace(".NS", "")
    path = data_dir / f"{stem}_{suffix}.csv"
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=120, freq="D"),
            "open": [100 + i * 0.2 for i in range(120)],
            "high": [101 + i * 0.2 for i in range(120)],
            "low": [99 + i * 0.2 for i in range(120)],
            "close": [100.5 + i * 0.2 for i in range(120)],
            "volume": [1000 + i * 2 for i in range(120)],
        }
    )
    df.to_csv(path, index=False)


def _factory_for_csv() -> ProviderFactory:
    return ProviderFactory(
        DataProvidersConfig(
            default_provider="csv",
            providers={
                "csv": ProviderEntry(enabled=True),
                "indian_csv": ProviderEntry(enabled=True),
            },
        )
    )


def test_phase4_profile_expected_module_sets() -> None:
    loader = AnalysisProfileLoader()
    profiles = loader.load()

    assert {"technical", "quant"}.issubset(set(profiles["intraday_equity"].enabled))
    assert {"technical", "quant", "fundamental", "sentiment"}.issubset(
        set(profiles["swing_equity"].enabled)
    )
    assert {"macro", "intermarket", "technical"}.issubset(set(profiles["macro_swing"].enabled))
    assert {"technical", "quant", "options", "sentiment"}.issubset(
        set(profiles["index_options"].enabled)
    )
    assert {"technical", "quant", "futures", "macro", "intermarket"}.issubset(
        set(profiles["commodity_futures"].enabled)
    )
    assert {"technical", "quant", "futures", "macro", "intermarket"}.issubset(
        set(profiles["inr_currency_derivatives"].enabled)
    )


def test_analysis_profile_application_keeps_backward_compatible_defaults() -> None:
    registry = AnalysisRegistry.create_default()
    loader = AnalysisProfileLoader()
    loader.apply_profile_by_name("default", registry)
    enabled = {module.name for module in registry.enabled_modules()}
    assert enabled == {"technical", "quant"}


def test_scanner_additive_phase4_analysis_context_attachment(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    symbol = "RELIANCE.NS"
    _write_symbol_csv(data_dir, symbol)

    universe_file = tmp_path / "universe.csv"
    pd.DataFrame({"symbol": [symbol]}).to_csv(universe_file, index=False)

    scanner_cfg = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_file),
        provider_name="csv",
        data_dir=str(data_dir),
        strategy_specs=[StrategyScanSpec(strategy_class=_AlwaysBuyStrategy, timeframes=["1D"])],
        enable_analysis_features=True,
        analysis_profile="swing_equity",
        analysis_context={
            "fundamentals_provider": "fmp",
            "fundamental_payload": {
                "marketCap": 100000000000,
                "PERatio": 18.0,
                "priceToBookRatio": 2.0,
                "debtToEquity": 0.4,
                "returnOnEquity": 0.2,
                "revenueGrowthTTM": 0.11,
            },
            "sentiment_provider": "finnhub",
            "sentiment_payload": {
                "ticker_news": [
                    {
                        "headline": "RELIANCE beats estimates",
                        "date": "2026-03-10T10:00:00Z",
                        "sentiment_score": 0.6,
                    }
                ]
            },
        },
    )

    engine = StockScannerEngine(
        scanner_config=scanner_cfg,
        data_gateway=DataGateway(
            provider_name="csv",
            data_dir=str(data_dir),
            provider_factory=_factory_for_csv(),
        ),
    )
    result = engine.run(export=False)
    assert len(result.opportunities) == 1

    components = result.opportunities[0].metadata["score_components"]
    assert "analysis_features" in components
    assert components["analysis_features"]["fundamental"] != {}
    assert components["analysis_features"]["sentiment"] != {}
    assert "fundamental_summary" in components
    assert "event_risk_flags" in components
