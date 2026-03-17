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


# ---------------------------------------------------------------------------
# Additional tests added in regression-hardening pass
# ---------------------------------------------------------------------------

def test_stop_above_entry_raises() -> None:
    bad = _opportunity()
    bad.stop_loss = bad.entry_price + 50.0  # stop above entry
    with pytest.raises(TradePlanBuilderError, match="stop must be below entry"):
        TradePlanBuilder().build(bad)


def test_target_at_entry_raises() -> None:
    bad = _opportunity()
    bad.target_price = bad.entry_price  # no reward
    with pytest.raises(TradePlanBuilderError, match="target must be above entry"):
        TradePlanBuilder().build(bad)


def test_target_below_entry_raises() -> None:
    bad = _opportunity()
    bad.target_price = bad.entry_price - 10.0
    with pytest.raises(TradePlanBuilderError):
        TradePlanBuilder().build(bad)


def test_swing_horizon_and_policy() -> None:
    plan = TradePlanBuilder().build(_opportunity(OpportunityClass.SWING))
    assert plan.horizon.value == "swing"
    assert "multi_day" in plan.max_hold_policy


def test_positional_horizon_and_policy() -> None:
    plan = TradePlanBuilder().build(_opportunity(OpportunityClass.POSITIONAL))
    assert plan.horizon.value == "positional"
    assert "multi_week" in plan.max_hold_policy


def test_risk_reward_computed_correctly() -> None:
    opp = _opportunity()
    entry, stop, target = 4100.0, 4040.0, 4220.0
    opp.entry_price = entry
    opp.stop_loss = stop
    opp.target_price = target
    expected_rr = (target - entry) / (entry - stop)  # 120 / 60 = 2.0

    plan = TradePlanBuilder().build(opp)
    assert plan.risk_reward == pytest.approx(expected_rr)


def test_setup_tags_include_strategy_timeframe_horizon() -> None:
    plan = TradePlanBuilder().build(_opportunity(OpportunityClass.INTRADAY))
    assert "RSIReversionStrategy" in plan.setup_tags
    assert "1h" in plan.setup_tags
    assert "intraday" in plan.setup_tags


def test_score_sub_fields_in_metadata() -> None:
    plan = TradePlanBuilder().build(_opportunity())
    assert plan.metadata["score_signal"] == pytest.approx(0.8)
    assert plan.metadata["score_rr"] == pytest.approx(0.7)
    assert plan.metadata["score_trend"] == pytest.approx(0.6)
    assert plan.metadata["score_liquidity"] == pytest.approx(0.5)
    assert plan.metadata["score_freshness"] == pytest.approx(0.9)


def test_additional_notes_without_opportunity_reasons() -> None:
    opp = _opportunity()
    opp.reasons = []
    plan = TradePlanBuilder().build(opp, additional_notes=["custom_note"])
    assert "custom_note" in plan.notes
    assert len(plan.notes) == 1


def test_opportunity_metadata_merged_into_plan() -> None:
    plan = TradePlanBuilder().build(_opportunity())
    assert plan.metadata["sector"] == "IT"
