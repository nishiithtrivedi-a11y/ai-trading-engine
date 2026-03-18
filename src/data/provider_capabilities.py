"""
Provider capability registry and validation helpers.

This module is the code-level source of truth for what each provider can
support in the current architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.data.instrument_metadata import InstrumentType, normalize_instrument_type


class ProviderCapabilityError(ValueError):
    """Raised when a provider/workflow capability check fails."""


class ImplementationStatus(str, Enum):
    STABLE = "stable"
    PARTIAL = "partial"
    PLACEHOLDER = "placeholder"


class ProviderFeature(str, Enum):
    HISTORICAL_DATA = "historical_data"
    LIVE_QUOTES = "live_quotes"
    INTRADAY_BARS = "intraday_bars"
    DAILY_BARS = "daily_bars"
    INSTRUMENT_LOOKUP = "instrument_lookup"
    ORDER_EXECUTION = "order_execution"
    SNAPSHOT_POLLING = "snapshot_polling"


@dataclass(frozen=True)
class ProviderFeatureSet:
    provider_name: str
    supports_historical_data: bool
    supports_live_quotes: bool
    supports_intraday_bars: bool
    supports_daily_bars: bool
    supports_instrument_lookup: bool
    supports_order_execution: bool
    supports_snapshot_polling: bool = False
    supported_instrument_types: tuple[InstrumentType, ...] = field(
        default_factory=lambda: (InstrumentType.EQUITY, InstrumentType.INDEX)
    )
    implementation_status: ImplementationStatus = ImplementationStatus.STABLE
    notes: str = ""
    # --- Segment and derivatives capability flags (Phase 1 modular foundation) ---
    supported_segments: tuple[str, ...] = ("NSE",)
    supports_derivatives: bool = False
    # --- Phase 2 derivative-specific capability flags ---
    supports_historical_derivatives: bool = False
    supports_latest_derivatives: bool = False
    supports_oi: bool = False
    supports_market_depth: bool = False
    instrument_master_available: bool = False

    def supports_segment(self, segment: str) -> bool:
        """Return True if this provider supports the given market segment."""
        return str(segment).upper() in (s.upper() for s in self.supported_segments)

    def supports_feature(self, feature: ProviderFeature) -> bool:
        feature_map = {
            ProviderFeature.HISTORICAL_DATA: self.supports_historical_data,
            ProviderFeature.LIVE_QUOTES: self.supports_live_quotes,
            ProviderFeature.INTRADAY_BARS: self.supports_intraday_bars,
            ProviderFeature.DAILY_BARS: self.supports_daily_bars,
            ProviderFeature.INSTRUMENT_LOOKUP: self.supports_instrument_lookup,
            ProviderFeature.ORDER_EXECUTION: self.supports_order_execution,
            ProviderFeature.SNAPSHOT_POLLING: self.supports_snapshot_polling,
        }
        return bool(feature_map[feature])

    def supports_instrument_type(
        self, instrument_type: InstrumentType | str
    ) -> bool:
        kind = normalize_instrument_type(instrument_type)
        return kind in self.supported_instrument_types


_DEFAULT_INSTRUMENTS = (
    InstrumentType.EQUITY,
    InstrumentType.ETF,
    InstrumentType.INDEX,
)

_PROVIDER_CAPABILITIES: dict[str, ProviderFeatureSet] = {
    "csv": ProviderFeatureSet(
        provider_name="csv",
        supports_historical_data=True,
        supports_live_quotes=False,
        supports_intraday_bars=True,
        supports_daily_bars=True,
        supports_instrument_lookup=False,
        supports_order_execution=False,
        supports_snapshot_polling=True,
        supported_instrument_types=_DEFAULT_INSTRUMENTS,
        implementation_status=ImplementationStatus.STABLE,
        notes="File-based provider with deterministic local data.",
        supported_segments=("NSE",),
        supports_derivatives=False,
        supports_historical_derivatives=False,
        supports_latest_derivatives=False,
        supports_oi=False,
        supports_market_depth=False,
        instrument_master_available=False,
    ),
    "indian_csv": ProviderFeatureSet(
        provider_name="indian_csv",
        supports_historical_data=True,
        supports_live_quotes=False,
        supports_intraday_bars=True,
        supports_daily_bars=True,
        supports_instrument_lookup=False,
        supports_order_execution=False,
        supports_snapshot_polling=True,
        supported_instrument_types=_DEFAULT_INSTRUMENTS,
        implementation_status=ImplementationStatus.STABLE,
        notes="Indian market CSV loader with timezone/session normalization.",
        supported_segments=("NSE", "BSE"),
        supports_derivatives=False,
        supports_historical_derivatives=False,
        supports_latest_derivatives=False,
        supports_oi=False,
        supports_market_depth=False,
        instrument_master_available=False,
    ),
    "zerodha": ProviderFeatureSet(
        provider_name="zerodha",
        supports_historical_data=True,
        supports_live_quotes=True,
        supports_intraday_bars=True,
        supports_daily_bars=True,
        supports_instrument_lookup=True,
        supports_order_execution=False,
        supports_snapshot_polling=False,
        supported_instrument_types=_DEFAULT_INSTRUMENTS,
        implementation_status=ImplementationStatus.PARTIAL,
        notes="Data provider + broker adapter paths exist; runtime execution remains disabled.",
        supported_segments=("NSE", "BSE", "NFO", "MCX", "CDS"),
        supports_derivatives=True,
        supports_historical_derivatives=True,
        supports_latest_derivatives=True,
        supports_oi=True,
        supports_market_depth=True,
        instrument_master_available=True,
    ),
    "upstox": ProviderFeatureSet(
        provider_name="upstox",
        supports_historical_data=True,
        supports_live_quotes=False,
        supports_intraday_bars=True,
        supports_daily_bars=True,
        supports_instrument_lookup=True,
        supports_order_execution=False,
        supports_snapshot_polling=True,
        supported_instrument_types=_DEFAULT_INSTRUMENTS,
        implementation_status=ImplementationStatus.PARTIAL,
        notes=(
            "Safe data-only integration with CSV fallback. "
            "SDK/API path remains integration-ready and health-checks report degradation explicitly."
        ),
        supported_segments=("NSE", "NFO"),
        supports_derivatives=False,
        supports_historical_derivatives=False,
        supports_latest_derivatives=False,
        supports_oi=False,
        supports_market_depth=False,
        instrument_master_available=False,
    ),
    "dhan": ProviderFeatureSet(
        provider_name="dhan",
        supports_historical_data=True,
        supports_live_quotes=True,
        supports_intraday_bars=True,
        supports_daily_bars=True,
        supports_instrument_lookup=False,   # No full instrument list API
        supports_order_execution=False,     # Execution disabled by design
        supports_snapshot_polling=True,
        supported_instrument_types=_DEFAULT_INSTRUMENTS,
        implementation_status=ImplementationStatus.PARTIAL,
        notes=(
            "DhanHQ optional provider. Requires dhanhq package and credentials. "
            "Provides historical candles, option chain, and expiry list. "
            "SDK path degrades gracefully when package or auth is unavailable."
        ),
        supported_segments=("NSE", "BSE", "NFO", "MCX", "CDS"),
        supports_derivatives=True,
        supports_historical_derivatives=True,
        supports_latest_derivatives=True,
        supports_oi=True,
        supports_market_depth=True,
        instrument_master_available=False,
    ),
}


def _normalize_provider_name(provider_name: str) -> str:
    name = str(provider_name).strip().lower()
    if not name:
        raise ProviderCapabilityError("provider_name cannot be empty")
    return name


def get_provider_feature_set(provider_name: str) -> ProviderFeatureSet:
    name = _normalize_provider_name(provider_name)
    if name not in _PROVIDER_CAPABILITIES:
        raise ProviderCapabilityError(
            f"Unknown provider '{provider_name}'. Known providers: {sorted(_PROVIDER_CAPABILITIES.keys())}"
        )
    return _PROVIDER_CAPABILITIES[name]


def list_provider_feature_sets() -> dict[str, ProviderFeatureSet]:
    return dict(_PROVIDER_CAPABILITIES)


def validate_provider_feature(provider_name: str, feature: ProviderFeature) -> None:
    feature_set = get_provider_feature_set(provider_name)
    if not feature_set.supports_feature(feature):
        raise ProviderCapabilityError(
            f"Provider '{feature_set.provider_name}' does not support feature '{feature.value}'"
        )


def validate_provider_workflow(
    provider_name: str,
    *,
    require_historical_data: bool = False,
    require_live_quotes: bool = False,
    timeframe: str | None = None,
    instrument_type: InstrumentType | str | None = None,
) -> ProviderFeatureSet:
    feature_set = get_provider_feature_set(provider_name)
    missing: list[str] = []

    if require_historical_data and not feature_set.supports_historical_data:
        missing.append("historical_data")
    if require_live_quotes and not feature_set.supports_live_quotes:
        missing.append("live_quotes")

    if timeframe is not None:
        normalized_tf = normalize_capability_timeframe(timeframe)
        if normalized_tf in {"1m", "5m", "15m", "1h"} and not feature_set.supports_intraday_bars:
            missing.append(f"intraday_bars({normalized_tf})")
        if normalized_tf == "1D" and not feature_set.supports_daily_bars:
            missing.append("daily_bars(1D)")

    if instrument_type is not None and not feature_set.supports_instrument_type(instrument_type):
        kind = normalize_instrument_type(instrument_type)
        missing.append(f"instrument_type({kind.value})")

    if missing:
        raise ProviderCapabilityError(
            f"Provider '{feature_set.provider_name}' does not support required capability set: {missing}. "
            f"status={feature_set.implementation_status.value}; notes={feature_set.notes}"
        )

    return feature_set


def get_derivative_capability_summary(provider_name: str) -> dict:
    """Return a structured summary of derivative capabilities for a provider.

    Parameters
    ----------
    provider_name:
        Provider name string (e.g. "zerodha", "upstox").

    Returns
    -------
    dict
        Keys: provider, supports_derivatives, supports_historical_derivatives,
        supports_latest_derivatives, supports_oi, supports_market_depth,
        instrument_master_available, supported_segments, implementation_status.

    Raises
    ------
    ProviderCapabilityError
        If the provider is unknown.
    """
    fs = get_provider_feature_set(provider_name)
    return {
        "provider": fs.provider_name,
        "supports_derivatives": fs.supports_derivatives,
        "supports_historical_derivatives": fs.supports_historical_derivatives,
        "supports_latest_derivatives": fs.supports_latest_derivatives,
        "supports_oi": fs.supports_oi,
        "supports_market_depth": fs.supports_market_depth,
        "instrument_master_available": fs.instrument_master_available,
        "supported_segments": list(fs.supported_segments),
        "implementation_status": fs.implementation_status.value,
    }


def normalize_capability_timeframe(timeframe: str) -> str:
    key = str(timeframe).strip().lower()
    mapping = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "60m": "1h",
        "1d": "1D",
        "d": "1D",
        "day": "1D",
        "daily": "1D",
    }
    normalized = mapping.get(key, str(timeframe).strip())
    supported = {"1m", "5m", "15m", "1h", "1D"}
    if normalized not in supported:
        raise ProviderCapabilityError(
            f"Unsupported timeframe '{timeframe}' for capability validation. Supported: {sorted(supported)}"
        )
    return normalized

