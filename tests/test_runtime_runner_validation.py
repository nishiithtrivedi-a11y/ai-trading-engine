from __future__ import annotations

import pytest

from src.runtime.runner_validation import (
    RunnerValidationError,
    normalize_fee_inputs,
    validate_polling_inputs,
    validate_provider_for_mode,
    validate_symbol_inputs,
)


def test_normalize_fee_inputs_supports_rate_to_bps_conversion() -> None:
    normalized = normalize_fee_inputs(fee_rate=0.001, slippage_rate=0.0005)
    assert normalized.commission_bps == 10.0
    assert normalized.slippage_bps == 5.0


def test_validate_symbol_inputs_requires_custom_universe_file_without_symbols() -> None:
    with pytest.raises(RunnerValidationError):
        validate_symbol_inputs(
            symbols=None,
            universe="custom",
            universe_file="",
        )


def test_validate_provider_for_mode_rejects_missing_live_quotes_requirement() -> None:
    with pytest.raises(RunnerValidationError):
        validate_provider_for_mode(
            provider_name="upstox",
            mode="live_safe",
            timeframe="1D",
            require_live_quotes=True,
        )


def test_validate_polling_inputs_allows_run_once_with_polling_interval() -> None:
    validate_polling_inputs(run_once=True, poll_seconds=5, max_cycles=3)
