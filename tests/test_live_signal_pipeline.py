from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.live import LiveSignalPipeline, LiveSignalPipelineConfig
from src.strategies.breakout import BreakoutStrategy


def _write_symbol_csv(path: Path, *, base: float, slope: float, breakout_boost: float = 0.0) -> None:
    rows = []
    start = pd.Timestamp("2025-01-01")
    for i in range(40):
        close = base + slope * i
        if i == 39:
            close += breakout_boost
        rows.append(
            {
                "timestamp": (start + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": close - 0.6,
                "high": close + 0.8,
                "low": close - 0.9,
                "close": close,
                "volume": 100000 + i * 100,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _strategy_registry() -> dict[str, dict]:
    return {
        "breakout": {
            "class": BreakoutStrategy,
            "params": {"entry_period": 20, "exit_period": 10},
        }
    }


def test_live_pipeline_safe_default_disabled(tmp_path: Path) -> None:
    cfg = LiveSignalPipelineConfig(
        enabled=False,
        provider_name="indian_csv",
        symbols=["RELIANCE.NS"],
        output_dir=str(tmp_path / "out"),
    )
    pipeline = LiveSignalPipeline(config=cfg, strategy_registry=_strategy_registry())

    report = pipeline.run()

    assert report.enabled is False
    assert report.decisions == []
    assert report.exports == {}
    assert any("disabled" in w.lower() for w in report.warnings)


def test_live_pipeline_generates_signals_and_artifacts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    _write_symbol_csv(data_dir / "RELIANCE_1D.csv", base=100.0, slope=0.4, breakout_boost=4.0)
    _write_symbol_csv(data_dir / "TCS_1D.csv", base=150.0, slope=0.2, breakout_boost=3.5)

    cfg = LiveSignalPipelineConfig(
        enabled=True,
        provider_name="indian_csv",
        symbols=["RELIANCE.NS", "TCS.NS"],
        interval="day",
        lookback_bars=30,
        output_dir=str(tmp_path / "live_signals"),
        paper_handoff=True,
        data_dir=str(data_dir),
    )

    pipeline = LiveSignalPipeline(config=cfg, strategy_registry=_strategy_registry())
    report = pipeline.run()

    assert len(report.market_snapshots) == 2
    assert len(report.regime_snapshots) == 2
    assert len(report.decisions) == 2
    assert len(report.actionable_signals) >= 1
    first_actionable = report.actionable_signals[0]
    assert "estimated_deployed_capital" in first_actionable.metadata
    assert "estimated_open_positions" in first_actionable.metadata
    assert "signals" in report.exports
    assert "watchlist" in report.exports
    assert "regime_snapshot" in report.exports
    assert "session_state" in report.exports
    assert "session_summary" in report.exports
    assert "paper_handoff" in report.exports
    assert "artifacts_meta" in report.exports

    for path in report.exports.values():
        assert Path(path).exists()

    state_payload = json.loads(Path(report.exports["session_state"]).read_text(encoding="utf-8"))
    assert state_payload["schema_version"] == "v1"
    assert state_payload["source"] == "live.session_signal_report"

    meta_payload = json.loads(Path(report.exports["artifacts_meta"]).read_text(encoding="utf-8"))
    assert meta_payload["schema_version"] == "v1"
    assert meta_payload["source"] == "live.market_session_store"
    assert "signals" in meta_payload["artifacts"]

    summary_path = Path(report.exports["session_summary"])
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "No live broker orders were placed" in summary_text


def test_live_pipeline_applies_relative_strength_top_n(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    _write_symbol_csv(data_dir / "RELIANCE_1D.csv", base=100.0, slope=0.8, breakout_boost=5.0)
    _write_symbol_csv(data_dir / "TCS_1D.csv", base=200.0, slope=0.05, breakout_boost=1.0)

    cfg = LiveSignalPipelineConfig(
        enabled=True,
        provider_name="indian_csv",
        symbols=["RELIANCE.NS", "TCS.NS"],
        top_n_symbols=1,
        lookback_bars=30,
        output_dir=str(tmp_path / "rs_topn"),
        data_dir=str(data_dir),
    )

    pipeline = LiveSignalPipeline(config=cfg, strategy_registry=_strategy_registry())
    report = pipeline.run()

    assert report.watchlist_state is not None
    assert len(report.watchlist_state.loaded_symbols) == 2
    assert len(report.watchlist_state.ranked_symbols) == 1
    assert len(report.decisions) == 1


def test_live_pipeline_risk_precheck_can_reject(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    _write_symbol_csv(data_dir / "RELIANCE_1D.csv", base=100.0, slope=0.6, breakout_boost=4.0)

    cfg = LiveSignalPipelineConfig(
        enabled=True,
        provider_name="indian_csv",
        symbols=["RELIANCE.NS"],
        interval="day",
        lookback_bars=30,
        output_dir=str(tmp_path / "risk_reject"),
        data_dir=str(data_dir),
        risk_context_open_positions_count=10,
    )

    pipeline = LiveSignalPipeline(config=cfg, strategy_registry=_strategy_registry())
    report = pipeline.run()

    assert len(report.actionable_signals) == 0
    assert len(report.risk_rejections) == 1
    assert report.risk_rejections[0].risk_allowed is False


def test_live_pipeline_keeps_execution_inert_metadata(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_symbol_csv(data_dir / "RELIANCE_1D.csv", base=100.0, slope=0.6, breakout_boost=4.0)

    cfg = LiveSignalPipelineConfig(
        enabled=True,
        provider_name="indian_csv",
        symbols=["RELIANCE.NS"],
        output_dir=str(tmp_path / "safe_meta"),
        data_dir=str(data_dir),
    )

    pipeline = LiveSignalPipeline(config=cfg, strategy_registry=_strategy_registry())
    report = pipeline.run()

    assert report.metadata.get("execution_mode") == "none"
    assert report.metadata.get("safety") == "no_live_orders"


def test_live_pipeline_rejects_provider_without_historical_capability(tmp_path: Path) -> None:
    cfg = LiveSignalPipelineConfig(
        enabled=True,
        provider_name="upstox",
        symbols=["RELIANCE.NS"],
        output_dir=str(tmp_path / "unsupported_provider"),
    )

    pipeline = LiveSignalPipeline(config=cfg, strategy_registry=_strategy_registry())
    report = pipeline.run()

    assert report.decisions == []
    assert report.market_snapshots == []
    assert any("historical_data" in error for error in report.errors)
