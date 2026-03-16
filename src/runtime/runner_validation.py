"""
Shared validation helpers for runner entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from src.data.instrument_metadata import InstrumentType
from src.data.provider_capabilities import (
    ProviderCapabilityError,
    ProviderFeatureSet,
    validate_provider_workflow,
)
from src.runtime.run_profiles import RunMode, RunProfile, get_run_profile


class RunnerValidationError(ValueError):
    """Raised when runner arguments or runtime assumptions are invalid."""


@dataclass(frozen=True)
class NormalizedFeeInputs:
    """Normalized fee/slippage inputs for cost-model style workflows."""

    commission_bps: float
    slippage_bps: float

    @property
    def commission_rate(self) -> float:
        return self.commission_bps / 10_000.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bps / 10_000.0


def ensure_int(name: str, value: int, *, min_value: int | None = None) -> int:
    ivalue = int(value)
    if min_value is not None and ivalue < min_value:
        raise RunnerValidationError(f"{name} must be >= {min_value}")
    return ivalue


def ensure_float(name: str, value: float, *, min_value: float | None = None) -> float:
    fvalue = float(value)
    if min_value is not None and fvalue < min_value:
        raise RunnerValidationError(f"{name} must be >= {min_value}")
    return fvalue


def ensure_ratio(
    name: str,
    value: float,
    *,
    min_value: float = 0.0,
    max_value: float = 1.0,
    inclusive_min: bool = False,
) -> float:
    fvalue = float(value)
    if inclusive_min:
        lower_ok = fvalue >= min_value
    else:
        lower_ok = fvalue > min_value
    if not (lower_ok and fvalue <= max_value):
        bracket = "[" if inclusive_min else "("
        raise RunnerValidationError(
            f"{name} must be in {bracket}{min_value}, {max_value}]"
        )
    return fvalue


def ensure_output_dir(path_value: str, *, arg_name: str = "--output-dir") -> Path:
    raw = str(path_value).strip()
    if not raw:
        raise RunnerValidationError(f"{arg_name} cannot be empty")
    return Path(raw)


def validate_symbol_inputs(
    *,
    symbols: Optional[Sequence[str]],
    universe: str,
    universe_file: str | None = None,
) -> None:
    if symbols:
        cleaned = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]
        if not cleaned:
            raise RunnerValidationError("--symbols cannot be all empty values")

    universe_name = str(universe).strip().lower()
    if universe_name in {"custom", "csv"}:
        has_symbols = bool(symbols)
        has_file = bool(str(universe_file or "").strip())
        if not has_symbols and not has_file:
            raise RunnerValidationError(
                "--universe-file is required when --universe custom/csv is used without --symbols"
            )


def validate_polling_inputs(
    *,
    run_once: bool,
    poll_seconds: int,
    max_cycles: int,
) -> None:
    ensure_int("--poll-seconds", poll_seconds, min_value=0)
    ensure_int("--max-cycles", max_cycles, min_value=1)
    if run_once and poll_seconds > 0:
        # Not an error: run_once intentionally overrides polling loop.
        return


def normalize_fee_inputs(
    *,
    commission_bps: float | None = None,
    slippage_bps: float | None = None,
    fee_rate: float | None = None,
    slippage_rate: float | None = None,
) -> NormalizedFeeInputs:
    if commission_bps is None and fee_rate is not None:
        commission_bps = float(fee_rate) * 10_000.0
    if slippage_bps is None and slippage_rate is not None:
        slippage_bps = float(slippage_rate) * 10_000.0

    c_bps = ensure_float("--commission-bps", commission_bps if commission_bps is not None else 0.0, min_value=0.0)
    s_bps = ensure_float("--slippage-bps", slippage_bps if slippage_bps is not None else 0.0, min_value=0.0)
    return NormalizedFeeInputs(commission_bps=c_bps, slippage_bps=s_bps)


def validate_provider_for_mode(
    *,
    provider_name: str,
    mode: RunMode | str,
    timeframe: str | None = None,
    instrument_type: InstrumentType | str = InstrumentType.EQUITY,
    require_live_quotes: bool | None = None,
) -> ProviderFeatureSet:
    profile: RunProfile = get_run_profile(mode)
    live_quotes_required = (
        bool(require_live_quotes)
        if require_live_quotes is not None
        else bool(profile.requires_live_quotes)
    )
    try:
        return validate_provider_workflow(
            provider_name,
            require_historical_data=bool(profile.requires_historical_data),
            require_live_quotes=live_quotes_required,
            timeframe=timeframe,
            instrument_type=instrument_type,
        )
    except ProviderCapabilityError as exc:
        raise RunnerValidationError(str(exc)) from exc
