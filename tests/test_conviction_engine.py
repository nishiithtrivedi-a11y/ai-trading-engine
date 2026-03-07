from __future__ import annotations

import pandas as pd

from src.decision.config import ConvictionWeightsConfig, DecisionConfig
from src.decision.conviction_engine import ConvictionEngine
from src.decision.models import DecisionHorizon, RegimeFilterResult, TradePlan
from src.monitoring.models import RelativeStrengthSnapshot
from src.scanners.models import Opportunity, OpportunityClass


def _opportunity() -> Opportunity:
    return Opportunity(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-07 10:00:00", tz="UTC"),
        classification=OpportunityClass.POSITIONAL,
        entry_price=2500.0,
        stop_loss=2450.0,
        target_price=2600.0,
        score=80.0,
        score_liquidity=0.7,
        score_freshness=0.6,
    )


def _plan(rr: float) -> TradePlan:
    entry = 100.0
    stop = 99.0
    target = entry + rr * (entry - stop)
    return TradePlan(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        entry_price=entry,
        stop_loss=stop,
        target_price=target,
        risk_reward=rr,
        horizon=DecisionHorizon.POSITIONAL,
    )


def test_conviction_score_bounded() -> None:
    engine = ConvictionEngine()
    cfg = DecisionConfig()

    breakdown = engine.score(
        opportunity=_opportunity(),
        trade_plan=_plan(2.0),
        config=cfg,
        regime_result=RegimeFilterResult(allowed=True, penalty=0.0),
        relative_strength=RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.1),
    )

    assert 0.0 <= breakdown.final_score <= 100.0


def test_higher_rr_improves_score_when_rr_weight_dominant() -> None:
    cfg = DecisionConfig(
        conviction_weights=ConvictionWeightsConfig(weights={"risk_reward": 1.0})
    )
    engine = ConvictionEngine()
    opp = _opportunity()

    low = engine.score(opp, _plan(1.0), cfg).final_score
    high = engine.score(opp, _plan(2.5), cfg).final_score

    assert high > low


def test_regime_penalty_reduces_score() -> None:
    cfg = DecisionConfig()
    engine = ConvictionEngine()
    opp = _opportunity()
    plan = _plan(2.0)

    neutral = engine.score(
        opportunity=opp,
        trade_plan=plan,
        config=cfg,
        regime_result=RegimeFilterResult(allowed=True, penalty=0.0),
    ).final_score
    penalized = engine.score(
        opportunity=opp,
        trade_plan=plan,
        config=cfg,
        regime_result=RegimeFilterResult(allowed=True, penalty=40.0),
    ).final_score

    assert penalized < neutral


def test_missing_optional_context_is_graceful() -> None:
    cfg = DecisionConfig()
    engine = ConvictionEngine()
    breakdown = engine.score(
        opportunity=_opportunity(),
        trade_plan=_plan(1.8),
        config=cfg,
        regime_result=None,
        relative_strength=None,
    )
    assert 0.0 <= breakdown.final_score <= 100.0
    assert "regime_context_missing_neutral" in breakdown.notes
