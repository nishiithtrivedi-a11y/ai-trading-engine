"""
Shared runtime mode profiles for runner orchestration.

These profiles are a single source of truth for what each workflow mode
is allowed to do in the current architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RunMode(str, Enum):
    RESEARCH = "research"
    PAPER = "paper"
    LIVE_SAFE = "live_safe"


@dataclass(frozen=True)
class RunProfile:
    mode: RunMode
    execution_allowed: bool
    paper_allowed: bool
    live_signal_allowed: bool
    requires_explicit_enable_flag: bool
    requires_historical_data: bool = True
    requires_live_quotes: bool = False
    expected_artifacts: tuple[str, ...] = field(default_factory=tuple)
    safety_notes: tuple[str, ...] = field(default_factory=tuple)


_RUN_PROFILES: dict[RunMode, RunProfile] = {
    RunMode.RESEARCH: RunProfile(
        mode=RunMode.RESEARCH,
        execution_allowed=False,
        paper_allowed=False,
        live_signal_allowed=False,
        requires_explicit_enable_flag=False,
        requires_historical_data=True,
        requires_live_quotes=False,
        expected_artifacts=("all_results.csv", "top_ranked.csv", "summary.md"),
        safety_notes=(
            "Research mode does not place broker orders.",
            "Execution interface remains inert in this phase.",
        ),
    ),
    RunMode.PAPER: RunProfile(
        mode=RunMode.PAPER,
        execution_allowed=False,
        paper_allowed=True,
        live_signal_allowed=False,
        requires_explicit_enable_flag=True,
        requires_historical_data=True,
        requires_live_quotes=False,
        expected_artifacts=(
            "paper_orders.csv",
            "paper_positions.csv",
            "paper_pnl.csv",
            "paper_state.json",
            "paper_session_summary.md",
        ),
        safety_notes=(
            "Paper mode is simulation-only.",
            "No live broker order placement is allowed.",
        ),
    ),
    RunMode.LIVE_SAFE: RunProfile(
        mode=RunMode.LIVE_SAFE,
        execution_allowed=False,
        paper_allowed=False,
        live_signal_allowed=True,
        requires_explicit_enable_flag=True,
        requires_historical_data=True,
        requires_live_quotes=False,
        expected_artifacts=(
            "signals.csv",
            "watchlist.csv",
            "regime_snapshot.csv",
            "session_state.json",
            "session_summary.md",
        ),
        safety_notes=(
            "Live-safe mode generates signals/artifacts only.",
            "No submit/modify/cancel order operations are allowed.",
        ),
    ),
}


def get_run_profile(mode: RunMode | str) -> RunProfile:
    if isinstance(mode, RunMode):
        key = mode
    else:
        key = RunMode(str(mode).strip().lower())
    return _RUN_PROFILES[key]


def list_run_profiles() -> dict[str, RunProfile]:
    return {mode.value: profile for mode, profile in _RUN_PROFILES.items()}
