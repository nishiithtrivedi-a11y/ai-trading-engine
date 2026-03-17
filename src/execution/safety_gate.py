"""
Execution safety policy for blocking real broker order flow by default.

This module is the single source of truth for whether live broker execution
is allowed in the current runtime context.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExecutionSafetyError(RuntimeError):
    """Raised when execution safety boundaries are violated."""


class ExecutionMode(str, Enum):
    RESEARCH = "research"
    PAPER = "paper"
    LIVE_SAFE = "live_safe"
    LIVE = "live"


@dataclass(frozen=True)
class SafetyGateConfig:
    execution_mode: ExecutionMode | str | None = None
    live_execution_enabled: bool = False
    source: str = "unknown"
    env_var_name: str = "EXECUTION_MODE"


def get_execution_mode(
    config: SafetyGateConfig | None = None,
    *,
    mode: ExecutionMode | str | None = None,
    env_mode: str | None = None,
) -> ExecutionMode:
    """
    Resolve execution mode from explicit input and/or environment.

    Resolution rules:
    - explicit `mode` argument overrides config value.
    - config value is used when explicit mode is not provided.
    - environment is used only when neither explicit nor config mode is set.
    - hard-fail when mode is missing, invalid, or ambiguous.
    """
    source_name = config.source if config is not None else "unknown"
    env_key = config.env_var_name if config is not None else "EXECUTION_MODE"

    configured_mode = mode if mode is not None else (config.execution_mode if config is not None else None)
    if env_mode is None:
        env_mode = os.getenv(env_key)

    def _normalize_mode(value: ExecutionMode | str) -> str:
        if isinstance(value, ExecutionMode):
            return value.value
        return str(value).strip().lower()

    if configured_mode is None and env_mode is None:
        raise ExecutionSafetyError(
            "Execution mode is missing. Set an explicit mode "
            f"(research/paper/live_safe/live) or define {env_key}."
        )

    if configured_mode is not None and env_mode is not None:
        configured_raw = _normalize_mode(configured_mode)
        env_raw = str(env_mode).strip().lower()
        if configured_raw != env_raw:
            raise ExecutionSafetyError(
                f"Ambiguous execution mode for '{source_name}': "
                f"configured='{configured_raw}' vs env {env_key}='{env_raw}'."
            )

    if configured_mode is not None:
        raw = _normalize_mode(configured_mode)
    else:
        raw = str(env_mode).strip().lower()
    try:
        return ExecutionMode(raw)
    except ValueError as exc:
        raise ExecutionSafetyError(
            f"Unsupported execution mode '{raw}'. "
            "Allowed values: research, paper, live_safe, live."
        ) from exc


def is_live_execution_allowed(config: SafetyGateConfig) -> bool:
    mode = get_execution_mode(config)
    return mode == ExecutionMode.LIVE and bool(config.live_execution_enabled)


def assert_execution_allowed(
    config: SafetyGateConfig,
    *,
    action: str = "broker_order_execution",
) -> None:
    """
    Guard for real broker execution paths.

    In current safety policy, only explicit LIVE mode with explicit enable flag
    is allowed to pass this gate.
    """
    assert_live_execution_allowed(config, action=action)


def assert_live_execution_allowed(
    config: SafetyGateConfig,
    *,
    action: str = "broker_order_execution",
) -> None:
    mode = get_execution_mode(config)

    if mode != ExecutionMode.LIVE:
        raise ExecutionSafetyError(
            f"{action} blocked: mode='{mode.value}' is non-live. "
            "Only mode='live' can permit broker order execution."
        )

    if not bool(config.live_execution_enabled):
        raise ExecutionSafetyError(
            f"{action} blocked: mode='live' requires explicit live_execution_enabled=true."
        )
