from __future__ import annotations

import pandas as pd
import pytest

from src.decision.trade_plan_builder import TradePlanBuilder, TradePlanBuilderError
from src.scanners.models import Opportunity, OpportunityClass


def _opportunity(classification: OpportunityClass = OpportunityClass.SWING) -> Opportunity:
    return Opportunity(
        symbol="TCS.NS",
        timeframe="1h",
        strategy_name="RSIReversionStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-07 11:00:00", tz="UTC"),
        classification=classification,
        entry_price=4100.0,
        stop_loss=4040.0,
        target_price=4220.0,
        score=76.0,
        reasons=["actionable_buy_signal"],
        score_signal=0.8,
        score_rr=0.7,
        score_trend=0.6,
        score_liquidity=0.5,
        score_freshness=0.9,
        metadata={"sector": "IT"},
    )


def test_build_trade_plan_maps_horizon_and_policy() -> None:
    plan = TradePlanBuilder().build(_opportunity(OpportunityClass.INTRADAY))
    assert plan.horizon.value == "intraday"
    assert plan.max_hold_policy == "same_day_exit"
    assert plan.risk_reward > 0


def test_build_trade_plan_preserves_notes_and_metadata() -> None:
    plan = TradePlanBuilder().build(_opportunity(), additional_notes=["decision_layer_note"])
    assert "actionable_buy_signal" in plan.notes
    assert "decision_layer_note" in plan.notes
    assert plan.metadata["scanner_score"] == pytest.approx(76.0)
    assert plan.metadata["sector"] == "IT"


def test_invalid_long_setup_raises() -> None:
    bad = _opportunity()
    bad.stop_loss = bad.entry_price  # invalid long setup
    with pytest.raises(TradePlanBuilderError):
        TradePlanBuilder().build(bad)
