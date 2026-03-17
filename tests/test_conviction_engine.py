from __future__ import annotations

import pandas as pd
import pytest

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


# ---------------------------------------------------------------------------
# Additional tests added in regression-hardening pass
# ---------------------------------------------------------------------------

def test_zero_rr_plan_rejected_at_construction() -> None:
    """TradePlan itself refuses rr=0 (target == entry for long-side plans)."""
    with pytest.raises(ValueError):
        _plan(0.0)


def test_negative_rr_plan_rejected_at_construction() -> None:
    """TradePlan itself refuses rr<0 (target below entry for long-side plans)."""
    with pytest.raises(ValueError):
        _plan(-1.0)


def test_score_rr_present_overrides_fallback_setup_quality() -> None:
    """When opportunity.score_rr is set, setup_quality must use it, not rr_score."""
    cfg = DecisionConfig(
        conviction_weights=ConvictionWeightsConfig(weights={"setup_quality": 1.0})
    )
    engine = ConvictionEngine()
    opp_with_score_rr = _opportunity()
    opp_with_score_rr.score_rr = 0.9   # 90/100 setup quality

    opp_without_score_rr = _opportunity()
    opp_without_score_rr.score_rr = None

    plan = _plan(1.0)  # rr=1.0 → rr_score = 1.0/3.0*100 ≈ 33.3

    with_score_rr = engine.score(opp_with_score_rr, plan, cfg)
    without_score_rr = engine.score(opp_without_score_rr, plan, cfg)

    # With score_rr=0.9 → setup_quality=90; without → setup_quality ≈ 33.3
    assert with_score_rr.setup_quality == pytest.approx(90.0)
    assert with_score_rr.final_score > without_score_rr.final_score


def test_score_rr_absent_falls_back_to_rr_score() -> None:
    """When score_rr is None, setup_quality must equal rr_score."""
    engine = ConvictionEngine()
    opp = _opportunity()
    opp.score_rr = None
    plan = _plan(2.0)
    breakdown = engine.score(opp, plan, DecisionConfig())

    # rr_score = (2.0 / 3.0) * 100 ≈ 66.67; setup_quality should match
    assert breakdown.setup_quality == pytest.approx(breakdown.risk_reward, abs=0.01)


def test_relative_strength_improves_score_when_weight_dominant() -> None:
    cfg = DecisionConfig(
        conviction_weights=ConvictionWeightsConfig(weights={"relative_strength": 1.0})
    )
    engine = ConvictionEngine()
    opp = _opportunity()
    plan = _plan(2.0)

    low_rs = engine.score(
        opp, plan, cfg,
        relative_strength=RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=-0.2),
    ).final_score
    high_rs = engine.score(
        opp, plan, cfg,
        relative_strength=RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.2),
    ).final_score

    assert high_rs > low_rs


def test_conviction_breakdown_metadata_contains_weights() -> None:
    cfg = DecisionConfig()
    engine = ConvictionEngine()
    breakdown = engine.score(_opportunity(), _plan(2.0), cfg)
    assert "weights" in breakdown.metadata
    assert isinstance(breakdown.metadata["weights"], dict)


def test_conviction_breakdown_notes_mention_missing_rs_when_absent() -> None:
    cfg = DecisionConfig()
    engine = ConvictionEngine()
    breakdown = engine.score(
        _opportunity(), _plan(2.0), cfg,
        relative_strength=None,
    )
    assert "relative_strength_missing_neutral" in breakdown.notes


def test_conviction_breakdown_notes_clean_when_all_context_provided() -> None:
    cfg = DecisionConfig()
    engine = ConvictionEngine()
    breakdown = engine.score(
        _opportunity(),
        _plan(2.0),
        cfg,
        regime_result=RegimeFilterResult(allowed=True, penalty=0.0),
        relative_strength=RelativeStrengthSnapshot(symbol="RELIANCE.NS", score=0.05),
    )
    assert "regime_context_missing_neutral" not in breakdown.notes
    assert "relative_strength_missing_neutral" not in breakdown.notes


def test_all_zero_weights_raises() -> None:
    """Setting all weights to zero must raise — normalizer catches it at config construction."""
    with pytest.raises(Exception):  # ValueError from ConvictionWeightsConfig normalizer
        DecisionConfig(
            conviction_weights=ConvictionWeightsConfig(weights={"scanner_score": 0.0})
        )
