from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.market_intelligence.config import MarketIntelligenceConfig
from src.market_intelligence.market_state_engine import MarketStateEngine


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
            "volume": [1000 + i * 5 for i in range(len(closes))],
        }
    )
    df.to_csv(path, index=False)


def test_market_state_engine_happy_path(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_symbol_csv(data_dir, "NIFTY50.NS", [100 + i * 0.3 for i in range(180)])
    _write_symbol_csv(data_dir, "RELIANCE.NS", [100 + i * 0.7 for i in range(180)])
    _write_symbol_csv(data_dir, "TCS.NS", [100 + i * 0.5 for i in range(180)])
    _write_symbol_csv(data_dir, "INFY.NS", [100 + i * 0.4 for i in range(180)])

    cfg = MarketIntelligenceConfig(provider_name="csv", data_dir=str(data_dir))
    engine = MarketStateEngine()

    result = engine.run(
        symbols=["RELIANCE.NS", "TCS.NS", "INFY.NS"],
        sector_symbol_map={"Energy": ["RELIANCE.NS"], "IT": ["TCS.NS", "INFY.NS"]},
        config=cfg,
        benchmark_symbol="NIFTY50.NS",
    )

    assert result.breadth_snapshot is not None
    assert result.market_state is not None
    assert result.volatility_snapshot is not None
    assert len(result.sector_rotation) == 2
    assert len(result.volume_analysis) >= 1


def test_market_state_engine_graceful_missing_benchmark(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_symbol_csv(data_dir, "RELIANCE.NS", [100 + i * 0.7 for i in range(180)])
    _write_symbol_csv(data_dir, "TCS.NS", [100 + i * 0.5 for i in range(180)])

    cfg = MarketIntelligenceConfig(provider_name="csv", data_dir=str(data_dir))
    result = MarketStateEngine().run(
        symbols=["RELIANCE.NS", "TCS.NS"],
        sector_symbol_map={"Energy": ["RELIANCE.NS"], "IT": ["TCS.NS"]},
        config=cfg,
        benchmark_symbol="MISSINGBENCH.NS",
    )

    assert result.market_state is not None
    assert any("benchmark data unavailable" in w for w in result.warnings)
