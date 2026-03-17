from __future__ import annotations

import pytest

from src.execution.safety_gate import (
    ExecutionMode,
    ExecutionSafetyError,
    SafetyGateConfig,
    assert_execution_allowed,
    assert_live_execution_allowed,
    get_execution_mode,
    is_live_execution_allowed,
)


def test_get_execution_mode_from_config() -> None:
    cfg = SafetyGateConfig(execution_mode=ExecutionMode.PAPER, source="test")
    assert get_execution_mode(cfg) == ExecutionMode.PAPER


def test_get_execution_mode_raises_when_missing() -> None:
    cfg = SafetyGateConfig(execution_mode=None, source="test")
    with pytest.raises(ExecutionSafetyError, match="missing"):
        get_execution_mode(cfg, env_mode=None)


def test_get_execution_mode_raises_on_ambiguous_sources() -> None:
    cfg = SafetyGateConfig(execution_mode="paper", source="test")
    with pytest.raises(ExecutionSafetyError, match="Ambiguous"):
        get_execution_mode(cfg, env_mode="live_safe")


def test_non_live_modes_are_blocked() -> None:
    cfg = SafetyGateConfig(execution_mode="research", live_execution_enabled=True, source="test")
    with pytest.raises(ExecutionSafetyError, match="non-live"):
        assert_live_execution_allowed(cfg, action="place_order")


def test_live_mode_requires_explicit_enable_flag() -> None:
    cfg = SafetyGateConfig(execution_mode="live", live_execution_enabled=False, source="test")
    with pytest.raises(ExecutionSafetyError, match="requires explicit live_execution_enabled=true"):
        assert_execution_allowed(cfg, action="place_order")


def test_live_mode_with_enable_flag_allows_execution() -> None:
    cfg = SafetyGateConfig(execution_mode="live", live_execution_enabled=True, source="test")
    assert is_live_execution_allowed(cfg) is True
    assert_execution_allowed(cfg, action="place_order")
