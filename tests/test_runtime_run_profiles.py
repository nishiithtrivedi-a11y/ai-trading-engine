from __future__ import annotations

from src.runtime.run_profiles import RunMode, get_run_profile, list_run_profiles


def test_get_run_profile_for_each_mode() -> None:
    research = get_run_profile(RunMode.RESEARCH)
    paper = get_run_profile("paper")
    live_safe = get_run_profile("live_safe")

    assert research.mode == RunMode.RESEARCH
    assert research.execution_allowed is False
    assert research.requires_historical_data is True

    assert paper.mode == RunMode.PAPER
    assert paper.paper_allowed is True
    assert paper.requires_explicit_enable_flag is True

    assert live_safe.mode == RunMode.LIVE_SAFE
    assert live_safe.live_signal_allowed is True
    assert live_safe.execution_allowed is False


def test_list_run_profiles_contains_expected_keys() -> None:
    profiles = list_run_profiles()
    assert set(profiles.keys()) == {"research", "paper", "live_safe"}
