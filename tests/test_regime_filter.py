from __future__ import annotations

import pandas as pd
import pytest

from src.decision.config import DecisionConfig, RegimePolicyConfig
from src.decision.models import DecisionHorizon, RejectionReason
from src.decision.regime_filter import RegimeFilter
from src.monitoring.models import RegimeAssessment, RegimeState
from src.scanners.models import Opportunity, OpportunityClass


def _opportunity(classification: OpportunityClass = OpportunityClass.SWING) -> Opportunity:
    return Opportunity(
        symbol="RELIANCE.NS",
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        signal="buy",
        timestamp=pd.Timestamp("2026-03-07 10:00:00", tz="UTC"),
        classification=classification,
        entry_price=2500.0,
        stop_loss=2450.0,
        target_price=2600.0,
        score=78.0,
    )


def test_regime_filter_allows_when_regime_is_allowed() -> None:
    policy = RegimePolicyConfig(
        allowed_regimes_by_horizon={
            DecisionHorizon.INTRADAY: {RegimeState.BULLISH},
            DecisionHorizon.SWING: {RegimeState.BULLISH},
            DecisionHorizon.POSITIONAL: {RegimeState.BULLISH},
        },
        hard_block_on_mismatch=True,
    )
    regime = RegimeAssessment(regime=RegimeState.BULLISH)
    result = RegimeFilter().evaluate(_opportunity(), regime, policy)

    assert result.allowed is True
    assert result.penalty == 0.0


def test_regime_filter_blocks_when_mismatch_and_hard_block() -> None:
    policy = RegimePolicyConfig(
        allowed_regimes_by_horizon={
            DecisionHorizon.INTRADAY: {RegimeState.BULLISH},
            DecisionHorizon.SWING: {RegimeState.BULLISH},
            DecisionHorizon.POSITIONAL: {RegimeState.BULLISH},
        },
        mismatch_penalty=25.0,
        hard_block_on_mismatch=True,
    )
    regime = RegimeAssessment(regime=RegimeState.BEARISH)
    result = RegimeFilter().evaluate(_opportunity(), regime, policy)

    assert result.allowed is False
    assert RejectionReason.REGIME_BLOCKED in result.rejection_reasons
    assert result.penalty >= 25.0


def test_regime_filter_penalizes_when_not_hard_block() -> None:
    cfg = DecisionConfig()
    cfg.regime_policy.hard_block_on_mismatch = False
    cfg.regime_policy.allowed_regimes_by_horizon[DecisionHorizon.SWING] = {RegimeState.BULLISH}
    regime = RegimeAssessment(regime=RegimeState.RANGEBOUND)

    result = RegimeFilter().evaluate(_opportunity(), regime, cfg)
    assert result.allowed is True
    assert result.penalty > 0
    assert RejectionReason.REGIME_PENALIZED_OUT in result.rejection_reasons


def test_regime_filter_with_missing_regime_context_is_neutral() -> None:
    result = RegimeFilter().evaluate(_opportunity(), None, DecisionConfig())
    assert result.allowed is True
    assert result.penalty == 0.0


def test_regime_filter_logs_when_hard_blocked(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="decision_regime_filter")
    policy = RegimePolicyConfig(
        allowed_regimes_by_horizon={
            DecisionHorizon.INTRADAY: {RegimeState.BULLISH},
            DecisionHorizon.SWING: {RegimeState.BULLISH},
            DecisionHorizon.POSITIONAL: {RegimeState.BULLISH},
        },
        hard_block_on_mismatch=True,
    )
    regime = RegimeAssessment(regime=RegimeState.BEARISH)
    result = RegimeFilter().evaluate(_opportunity(), regime, policy)

    assert result.allowed is False
    assert "Regime blocked" in caplog.text
