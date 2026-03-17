"""
Execution interface placeholder.

Phase 9 safety boundary:
- Interface only
- No live order implementation
- Runtime adapters must explicitly opt-in in a future phase
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.execution.safety_gate import (
    ExecutionMode,
    ExecutionSafetyError,
    SafetyGateConfig,
    assert_live_execution_allowed,
)


@dataclass
class ExecutionIntent:
    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionAdapter(ABC):
    """Abstract execution adapter for future live execution integration."""

    @abstractmethod
    def submit_order(self, intent: ExecutionIntent) -> str:
        """Submit an order intent and return a broker-side order id."""

    @abstractmethod
    def modify_order(self, order_id: str, **changes: Any) -> None:
        """Modify an existing order."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        """Cancel an existing order."""


class PlaceholderExecutionAdapter(ExecutionAdapter):
    """Non-operational adapter that blocks execution by design."""

    def __init__(self, safety_config: SafetyGateConfig | None = None) -> None:
        # Safe default: explicit non-live mode.
        self.safety_config = safety_config or SafetyGateConfig(
            execution_mode=ExecutionMode.LIVE_SAFE,
            live_execution_enabled=False,
            source="placeholder_execution_adapter",
        )

    def _block(self, action: str) -> None:
        try:
            assert_live_execution_allowed(self.safety_config, action=action)
        except ExecutionSafetyError as exc:
            raise NotImplementedError(str(exc)) from exc
        raise NotImplementedError(
            "Execution adapter is a placeholder and has no live broker integration."
        )

    def submit_order(self, intent: ExecutionIntent) -> str:
        self._block("submit_order")

    def modify_order(self, order_id: str, **changes: Any) -> None:
        self._block("modify_order")

    def cancel_order(self, order_id: str) -> None:
        self._block("cancel_order")
