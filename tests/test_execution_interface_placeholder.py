from __future__ import annotations

import pytest

from src.execution.execution_interface import ExecutionIntent, PlaceholderExecutionAdapter


def test_placeholder_execution_adapter_is_inert() -> None:
    adapter = PlaceholderExecutionAdapter()
    intent = ExecutionIntent(symbol="RELIANCE.NS", side="buy", quantity=10)

    with pytest.raises(NotImplementedError):
        adapter.submit_order(intent)

    with pytest.raises(NotImplementedError):
        adapter.modify_order("ORD-1", quantity=20)

    with pytest.raises(NotImplementedError):
        adapter.cancel_order("ORD-1")
