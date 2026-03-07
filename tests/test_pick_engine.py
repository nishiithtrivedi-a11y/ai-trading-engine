from __future__ import annotations

import pandas as pd

from src.decision.config import DecisionConfig, DecisionThresholdsConfig, RegimePolicyConfig
from src.decision.models import DecisionHorizon
from src.decision.pick_engine import PickEngine
from src.monitoring.models import MonitoringRunResult, RegimeAssessment, RegimeState, RelativeStrengthSnapshot
from src.scanners.models import Opportunity, OpportunityClass, ScanResult


def _opportunity(
    symbol: str,
    classification: OpportunityClass,
    score: float,
    entry: float = 100.0,
    stop: float = 98.0,
    target: float = 104.0,
) -> Opportunity:
    return Opportunity(
        symbol=symbol,
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-07 14:00:00", tz="UTC"),
        classification=classification,
        entry_price=entry,
        stop_loss=stop,
        target_price=target,
        score=score,
        reasons=["actionable_buy_signal"],
        metadata={"sector": "IT"},
    )


def test_pick_engine_happy_path_with_monitoring_context() -> None:
    scan = ScanResult(
        opportunities=[
            _opportunity("RELIANCE.NS", OpportunityClass.INTRADAY, 82.0),
            _opportunity("TCS.NS", OpportunityClass.SWING, 78.0),
            _opportunity("INFY.NS", OpportunityClass.POSITIONAL, 55.0),
        ]
    )
    monitoring = MonitoringRunResult(
        scan_result=scan,
        regime_assessment=RegimeAssessment(regime=RegimeState.BULLISH),
        relative_strength=[
            RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.2, rank=1),
            RelativeStrengthSnapshot(symbol="TCS.NS", score=0.15, rank=2),
        ],
    )
    cfg = DecisionConfig(
        thresholds=DecisionThresholdsConfig(
            min_score_by_horizon={
                DecisionHorizon.INTRADAY: 60.0,
                DecisionHorizon.SWING: 65.0,
                DecisionHorizon.POSITIONAL: 70.0,
            }
        )
    )

    result = PickEngine(decision_config=cfg).run(monitoring_result=monitoring)

    assert len(result.top_intraday) == 1
    assert len(result.top_swing) == 1
    assert len(result.top_positional) == 0
    assert any(r.symbol == "INFY.NS" for r in result.rejected_opportunities)


def test_pick_engine_regime_block_rejects_candidate() -> None:
    scan = ScanResult(opportunities=[_opportunity("TCS.NS", OpportunityClass.SWING, 80.0)])
    monitoring = MonitoringRunResult(
        scan_result=scan,
        regime_assessment=RegimeAssessment(regime=RegimeState.BEARISH),
    )
    cfg = DecisionConfig(
        regime_policy=RegimePolicyConfig(
            allowed_regimes_by_horizon={
                DecisionHorizon.INTRADAY: {RegimeState.BULLISH},
                DecisionHorizon.SWING: {RegimeState.BULLISH},
                DecisionHorizon.POSITIONAL: {RegimeState.BULLISH},
            },
            hard_block_on_mismatch=True,
        )
    )

    result = PickEngine(decision_config=cfg).run(monitoring_result=monitoring)
    assert len(result.selected_picks) == 0
    assert any("regime_blocked" in r.to_dict()["rejection_reasons"] for r in result.rejected_opportunities)


def test_pick_engine_graceful_without_monitoring_context() -> None:
    scan = ScanResult(opportunities=[_opportunity("SBIN.NS", OpportunityClass.SWING, 79.0)])
    result = PickEngine().run(scan_result=scan)

    assert len(result.selected_picks) == 1
    assert result.selected_picks[0].symbol == "SBIN.NS"
