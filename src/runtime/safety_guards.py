"""
Central safety guardrails shared by runner entry points.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.runtime.run_profiles import RunMode, RunProfile, get_run_profile


class RuntimeSafetyError(RuntimeError):
    """Raised when a runtime safety boundary is violated."""


@dataclass(frozen=True)
class SafetyGuardResult:
    profile: RunProfile
    enabled: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.profile.mode.value,
            "enabled": self.enabled,
            "execution_allowed": self.profile.execution_allowed,
            "paper_allowed": self.profile.paper_allowed,
            "live_signal_allowed": self.profile.live_signal_allowed,
            "requires_explicit_enable_flag": self.profile.requires_explicit_enable_flag,
            "safety_notes": list(self.profile.safety_notes),
        }


def enforce_runtime_safety(
    mode: RunMode | str,
    *,
    explicit_enable_flag: bool,
    execution_requested: bool = False,
) -> SafetyGuardResult:
    profile = get_run_profile(mode)

    if profile.requires_explicit_enable_flag and not explicit_enable_flag:
        raise RuntimeSafetyError(
            f"{profile.mode.value} mode is OFF by default. Explicit enable flag is required."
        )

    if profile.execution_allowed:
        raise RuntimeSafetyError(
            f"{profile.mode.value} mode unexpectedly allows execution. "
            "Execution must remain disabled in current phase."
        )

    if execution_requested:
        raise RuntimeSafetyError(
            f"{profile.mode.value} mode requested execution path, but live execution is disabled."
        )

    return SafetyGuardResult(profile=profile, enabled=bool(explicit_enable_flag))


def enforce_no_live_execution(mode: RunMode | str) -> None:
    profile = get_run_profile(mode)
    if profile.execution_allowed:
        raise RuntimeSafetyError(
            f"Live execution is not allowed for mode '{profile.mode.value}'."
        )
