from __future__ import annotations

import pandas as pd
import pytest

from src.decision.models import (
    ConvictionBreakdown,
    DecisionHorizon,
    PickRunResult,
    RankedPick,
    RejectedOpportunity,
    RejectionReason,
    TradePlan,
)


def _trade_plan() -> TradePlan:
    return TradePlan(
        symbol="reliance.ns",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        entry_price=2500.0,
        stop_loss=2450.0,
        target_price=2600.0,
        risk_reward=2.0,
        horizon=DecisionHorizon.POSITIONAL,
        setup_tags=["trend_following"],
    )


def _breakdown(final_score: float = 82.0) -> ConvictionBreakdown:
    return ConvictionBreakdown(
        scanner_score=80.0,
        setup_quality=78.0,
        risk_reward=85.0,
        regime_compatibility=75.0,
        relative_strength=70.0,
        liquidity=65.0,
        freshness=60.0,
        final_score=final_score,
    )


def test_trade_plan_validation_and_to_dict() -> None:
    plan = _trade_plan()
    payload = plan.to_dict()
    assert plan.symbol == "RELIANCE.NS"
    assert payload["horizon"] == "positional"
    assert payload["risk_reward"] == pytest.approx(2.0)


def test_trade_plan_invalid_long_setup_raises() -> None:
    with pytest.raises(ValueError):
        TradePlan(
            symbol="TCS.NS",
            timeframe="1D",
            strategy_name="RSIReversionStrategy",
            entry_price=100.0,
            stop_loss=101.0,
            target_price=110.0,
            risk_reward=1.5,
            horizon=DecisionHorizon.SWING,
        )


def test_conviction_breakdown_bounds() -> None:
    with pytest.raises(ValueError):
        ConvictionBreakdown(
            scanner_score=101.0,
            setup_quality=70.0,
            risk_reward=70.0,
            regime_compatibility=70.0,
            relative_strength=70.0,
            liquidity=70.0,
            freshness=70.0,
            final_score=70.0,
        )


def test_ranked_pick_serialization() -> None:
    pick = RankedPick(
        trade_plan=_trade_plan(),
        conviction_score=82.0,
        conviction_breakdown=_breakdown(),
        scanner_score=79.0,
        priority_rank=1,
        horizon_rank=1,
        reasons=["regime_aligned", "high_rr"],
    )
    payload = pick.to_dict()
    assert payload["symbol"] == "RELIANCE.NS"
    assert payload["conviction_score"] == pytest.approx(82.0)
    assert payload["horizon"] == "positional"
    assert payload["priority_rank"] == 1


def test_rejected_opportunity_to_dict() -> None:
    rejected = RejectedOpportunity(
        symbol="infy.ns",
        timeframe="1D",
        strategy_name="Dummy",
        horizon=DecisionHorizon.SWING,
        scanner_score=58.0,
        rejection_reasons=[RejectionReason.BELOW_MIN_SCORE, RejectionReason.BELOW_MIN_RR],
        notes=["score below configured threshold"],
    )
    payload = rejected.to_dict()
    assert payload["symbol"] == "INFY.NS"
    assert "below_min_score" in payload["rejection_reasons"]


def test_pick_run_result_summary_shape() -> None:
    pick = RankedPick(
        trade_plan=_trade_plan(),
        conviction_score=82.0,
        conviction_breakdown=_breakdown(),
        scanner_score=79.0,
    )
    rejected = RejectedOpportunity(
        symbol="TCS.NS",
        timeframe="1D",
        strategy_name="Dummy",
        horizon=DecisionHorizon.SWING,
        scanner_score=52.0,
        rejection_reasons=[RejectionReason.BELOW_MIN_SCORE],
    )
    result = PickRunResult(
        generated_at=pd.Timestamp("2026-03-07 14:00:00", tz="UTC"),
        selected_picks=[pick],
        top_positional=[pick],
        rejected_opportunities=[rejected],
    )
    payload = result.to_dict()
    assert payload["summary"]["selected_total"] == 1
    assert payload["summary"]["rejected_total"] == 1
