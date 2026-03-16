from __future__ import annotations

import pytest

from src.runtime.safety_guards import RuntimeSafetyError, enforce_runtime_safety


def test_paper_mode_requires_explicit_enable() -> None:
    with pytest.raises(RuntimeSafetyError):
        enforce_runtime_safety("paper", explicit_enable_flag=False)


def test_research_mode_allows_guard_check_without_enable_flag() -> None:
    result = enforce_runtime_safety("research", explicit_enable_flag=False)
    assert result.profile.mode.value == "research"
    assert result.profile.execution_allowed is False


def test_execution_requested_is_blocked() -> None:
    with pytest.raises(RuntimeSafetyError):
        enforce_runtime_safety(
            "live_safe",
            explicit_enable_flag=True,
            execution_requested=True,
        )
