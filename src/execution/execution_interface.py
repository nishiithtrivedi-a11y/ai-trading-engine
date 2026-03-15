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

    def submit_order(self, intent: ExecutionIntent) -> str:
        raise NotImplementedError("Live execution is disabled in Phase 9. Use paper trading only.")

    def modify_order(self, order_id: str, **changes: Any) -> None:
        raise NotImplementedError("Live execution is disabled in Phase 9. Use paper trading only.")

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError("Live execution is disabled in Phase 9. Use paper trading only.")
