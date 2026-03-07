from __future__ import annotations

import pytest

from src.decision.config import (
    ConvictionWeightsConfig,
    DecisionConfig,
    DecisionExportConfig,
    DecisionThresholdsConfig,
    RegimePolicyConfig,
    normalize_decision_horizon,
)
from src.decision.models import DecisionHorizon
from src.monitoring.models import RegimeState


def test_normalize_decision_horizon_aliases() -> None:
    assert normalize_decision_horizon("intraday") == DecisionHorizon.INTRADAY
    assert normalize_decision_horizon("position") == DecisionHorizon.POSITIONAL

    with pytest.raises(ValueError):
        normalize_decision_horizon("weekly")


def test_threshold_helpers() -> None:
    cfg = DecisionThresholdsConfig(
        min_score_by_horizon={
            DecisionHorizon.INTRADAY: 55.0,
            DecisionHorizon.SWING: 65.0,
            DecisionHorizon.POSITIONAL: 75.0,
        },
        min_rr_by_horizon={
            DecisionHorizon.INTRADAY: 1.1,
            DecisionHorizon.SWING: 1.4,
            DecisionHorizon.POSITIONAL: 1.8,
        },
        max_picks_by_horizon={
            DecisionHorizon.INTRADAY: 3,
            DecisionHorizon.SWING: 4,
            DecisionHorizon.POSITIONAL: 5,
        },
    )
    assert cfg.min_score("swing") == pytest.approx(65.0)
    assert cfg.min_rr(DecisionHorizon.POSITIONAL) == pytest.approx(1.8)
    assert cfg.max_picks("intraday") == 3


def test_invalid_threshold_values_raise() -> None:
    with pytest.raises(ValueError):
        DecisionThresholdsConfig(
            min_score_by_horizon={
                DecisionHorizon.INTRADAY: -1.0,
                DecisionHorizon.SWING: 65.0,
                DecisionHorizon.POSITIONAL: 70.0,
            }
        )


def test_regime_policy_allowed_for() -> None:
    policy = RegimePolicyConfig(
        allowed_regimes_by_horizon={
            DecisionHorizon.INTRADAY: {RegimeState.BULLISH, RegimeState.UNKNOWN},
            DecisionHorizon.SWING: {RegimeState.BULLISH},
            DecisionHorizon.POSITIONAL: {RegimeState.BULLISH},
        }
    )
    allowed = policy.allowed_for("intraday")
    assert RegimeState.BULLISH in allowed
    assert RegimeState.BEARISH not in allowed


def test_conviction_weights_normalized() -> None:
    weights = ConvictionWeightsConfig(weights={"scanner_score": 2.0, "risk_reward": 1.0})
    assert sum(weights.weights.values()) == pytest.approx(1.0)
    assert weights.weights["scanner_score"] == pytest.approx(2.0 / 3.0)


def test_export_config_requires_format() -> None:
    with pytest.raises(ValueError):
        DecisionExportConfig(write_csv=False, write_json=False)


def test_decision_config_defaults_construct() -> None:
    cfg = DecisionConfig()
    assert cfg.thresholds.max_picks("intraday") >= 0
    assert cfg.selection_policy.enforce_unique_symbol is True
