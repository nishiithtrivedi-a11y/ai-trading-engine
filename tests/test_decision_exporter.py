from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.decision.config import DecisionExportConfig
from src.decision.exporter import DecisionExporter
from src.decision.models import (
    ConvictionBreakdown,
    DecisionHorizon,
    PickRunResult,
    RankedPick,
    RejectedOpportunity,
    RejectionReason,
    TradePlan,
)


def _pick(symbol: str, horizon: DecisionHorizon, score: float) -> RankedPick:
    plan = TradePlan(
        symbol=symbol,
        timeframe="1D",
        strategy_name="S1",
        entry_price=100.0,
        stop_loss=99.0,
        target_price=103.0,
        risk_reward=3.0,
        horizon=horizon,
    )
    breakdown = ConvictionBreakdown(
        scanner_score=score,
        setup_quality=score,
        risk_reward=score,
        regime_compatibility=score,
        relative_strength=score,
        liquidity=score,
        freshness=score,
        final_score=score,
    )
    return RankedPick(
        trade_plan=plan,
        conviction_score=score,
        conviction_breakdown=breakdown,
        scanner_score=score,
    )


def test_decision_exporter_writes_all_outputs(tmp_path: Path) -> None:
    result = PickRunResult(
        generated_at=pd.Timestamp("2026-03-07 15:00:00", tz="UTC"),
        selected_picks=[
            _pick("RELIANCE.NS", DecisionHorizon.INTRADAY, 85.0),
            _pick("TCS.NS", DecisionHorizon.SWING, 82.0),
        ],
        top_intraday=[_pick("RELIANCE.NS", DecisionHorizon.INTRADAY, 85.0)],
        top_swing=[_pick("TCS.NS", DecisionHorizon.SWING, 82.0)],
        top_positional=[],
        rejected_opportunities=[
            RejectedOpportunity(
                symbol="INFY.NS",
                timeframe="1D",
                strategy_name="S1",
                horizon=DecisionHorizon.POSITIONAL,
                scanner_score=50.0,
                rejection_reasons=[RejectionReason.BELOW_MIN_SCORE],
            )
        ],
    )
    cfg = DecisionExportConfig(output_dir=str(tmp_path / "decision"))

    outputs = DecisionExporter().export_all(result, cfg)

    assert "intraday_csv" in outputs
    assert "summary_json" in outputs
    for path in outputs.values():
        assert Path(path).exists()

    summary = json.loads((Path(cfg.output_dir) / cfg.summary_json_filename).read_text(encoding="utf-8"))
    assert summary["summary"]["selected_total"] == 2


def test_decision_exporter_handles_empty_result(tmp_path: Path) -> None:
    result = PickRunResult()
    cfg = DecisionExportConfig(output_dir=str(tmp_path / "decision_empty"))
    outputs = DecisionExporter().export_all(result, cfg)

    assert (Path(cfg.output_dir) / cfg.manifest_json_filename).exists()
    assert len(outputs) >= 2
