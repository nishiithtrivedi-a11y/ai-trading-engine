from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderFactory
from src.monitoring.config import RelativeStrengthConfig
from src.monitoring.sector_strength import SectorStrengthAnalyzer
from src.scanners.data_gateway import DataGateway


def _factory_for_csv() -> ProviderFactory:
    cfg = DataProvidersConfig(
        default_provider="csv",
        providers={"csv": ProviderEntry(enabled=True), "indian_csv": ProviderEntry(enabled=True)},
    )
    return ProviderFactory(cfg)


def _write_symbol_csv(data_dir: Path, symbol: str, closes: list[float]) -> None:
    stem = symbol.replace(".NS", "")
    path = data_dir / f"{stem}_1D.csv"
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": [v * 1.01 for v in closes],
            "low": [v * 0.99 for v in closes],
            "close": closes,
            "volume": [1000 + i * 3 for i in range(len(closes))],
        }
    )
    df.to_csv(path, index=False)


def test_relative_strength_ranking_with_benchmark(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    benchmark = [100 + i * 0.25 for i in range(220)]
    strong = [100 + i * 0.8 for i in range(220)]
    weak = [100 + i * 0.1 for i in range(220)]

    _write_symbol_csv(data_dir, "NIFTY50.NS", benchmark)
    _write_symbol_csv(data_dir, "RELIANCE.NS", strong)
    _write_symbol_csv(data_dir, "TCS.NS", weak)

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )
    cfg = RelativeStrengthConfig(
        benchmark_symbol="NIFTY50.NS",
        lookback_windows=[20, 60, 120],
        lookback_weights={20: 0.5, 60: 0.3, 120: 0.2},
        top_n=10,
    )

    analyzer = SectorStrengthAnalyzer()
    rows, sectors = analyzer.analyze(
        symbols=["RELIANCE.NS", "TCS.NS"],
        data_gateway=gateway,
        config=cfg,
    )

    assert len(rows) == 2
    assert rows[0].symbol == "RELIANCE.NS"
    assert rows[0].score > rows[1].score
    assert sectors == []


def test_relative_strength_missing_benchmark_graceful(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_symbol_csv(data_dir, "INFY.NS", [100 + i * 0.5 for i in range(220)])

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )
    cfg = RelativeStrengthConfig(
        benchmark_symbol="MISSINGBENCH.NS",
        allow_missing_benchmark=True,
    )

    rows, _ = SectorStrengthAnalyzer().analyze(
        symbols=["INFY.NS"],
        data_gateway=gateway,
        config=cfg,
    )
    assert len(rows) == 1
    assert rows[0].benchmark_symbol is None


def test_sector_strength_aggregation(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_symbol_csv(data_dir, "NIFTY50.NS", [100 + i * 0.2 for i in range(220)])
    _write_symbol_csv(data_dir, "RELIANCE.NS", [100 + i * 0.8 for i in range(220)])
    _write_symbol_csv(data_dir, "ONGC.NS", [100 + i * 0.6 for i in range(220)])
    _write_symbol_csv(data_dir, "INFY.NS", [100 + i * 0.3 for i in range(220)])

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )
    cfg = RelativeStrengthConfig(benchmark_symbol="NIFTY50.NS")

    rows, sectors = SectorStrengthAnalyzer().analyze(
        symbols=["RELIANCE.NS", "ONGC.NS", "INFY.NS"],
        data_gateway=gateway,
        config=cfg,
        sector_map={
            "RELIANCE.NS": "Energy",
            "ONGC.NS": "Energy",
            "INFY.NS": "IT",
        },
    )

    assert len(rows) == 3
    assert len(sectors) == 2
    assert sectors[0].rank == 1
    assert sectors[0].sector in {"Energy", "IT"}
