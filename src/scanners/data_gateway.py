"""
Thin data access layer for scanner modules.

Responsibilities:
- normalize scanner timeframe inputs
- map symbols/timeframes to local CSV files
- load validated data through existing provider architecture
- gracefully wrap provider limitations into scanner-specific errors
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.data_handler import DataHandler
from src.data.base import Timeframe
from src.data.instrument_metadata import InstrumentType
from src.data.provider_capabilities import (
    ProviderCapabilityError,
    validate_provider_workflow,
)
from src.data.provider_factory import ProviderError, ProviderFactory
from src.data.provider_runtime import get_provider_readiness_report
from src.data.symbol_mapping import SymbolMapper
from src.scanners.config import normalize_timeframe


class ScannerDataGatewayError(Exception):
    """Raised when scanner data loading fails."""


_TIMEFRAME_TO_SUFFIX = {
    "1m": "1M",
    "5m": "5M",
    "15m": "15M",
    "1h": "1H",
    "1D": "1D",
}

_TIMEFRAME_TO_ENUM = {
    "1m": Timeframe.MINUTE_1,
    "5m": Timeframe.MINUTE_5,
    "15m": Timeframe.MINUTE_15,
    "1h": Timeframe.HOURLY,
    "1D": Timeframe.DAILY,
}


@dataclass
class DataGateway:
    provider_name: str = "csv"
    data_dir: str = "data"
    provider_factory: Optional[ProviderFactory] = None

    def __post_init__(self) -> None:
        self._factory = self.provider_factory or ProviderFactory.from_config()
        self._symbol_mapper = SymbolMapper()

    @staticmethod
    def normalize_timeframe(value: str) -> str:
        return normalize_timeframe(value)

    @staticmethod
    def timeframe_to_file_suffix(timeframe: str) -> str:
        tf = normalize_timeframe(timeframe)
        return _TIMEFRAME_TO_SUFFIX[tf]

    def symbol_to_file_stem(self, symbol: str) -> str:
        return self._symbol_mapper.normalize(symbol)

    def resolve_csv_path(self, symbol: str, timeframe: str) -> Path:
        stem = self.symbol_to_file_stem(symbol)
        suffix = self.timeframe_to_file_suffix(timeframe)
        return Path(self.data_dir) / f"{stem}_{suffix}.csv"

    def load_data(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> DataHandler:
        tf = normalize_timeframe(timeframe)

        if self.provider_name in {"csv", "indian_csv"}:
            path = self.resolve_csv_path(symbol, tf)
            if not path.exists():
                raise ScannerDataGatewayError(
                    f"CSV data not found for {symbol} [{tf}] at {path}"
                )
            return self._load_from_csv(path)

        return self._load_from_provider(symbol=symbol, timeframe=tf, start=start, end=end)

    def _load_from_csv(self, path: Path) -> DataHandler:
        try:
            source = self._factory.create(self.provider_name, data_file=str(path))
        except ProviderError as exc:
            raise ScannerDataGatewayError(
                f"Failed to create provider '{self.provider_name}' for CSV file {path}: {exc}"
            ) from exc

        try:
            return DataHandler.from_source(source)
        except Exception as exc:  # noqa: BLE001
            raise ScannerDataGatewayError(
                f"Failed to load CSV data from {path}: {exc}"
            ) from exc

    def _load_from_provider(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> DataHandler:
        readiness = get_provider_readiness_report(
            self.provider_name,
            config=self._factory.config,
            require_enabled=True,
            require_historical_data=True,
            timeframe=timeframe,
            instrument_type=InstrumentType.EQUITY,
            mode="research",
        )
        if not readiness.can_instantiate:
            raise ScannerDataGatewayError(readiness.reason)

        try:
            validate_provider_workflow(
                self.provider_name,
                require_historical_data=True,
                timeframe=timeframe,
                instrument_type=InstrumentType.EQUITY,
            )
        except ProviderCapabilityError as exc:
            raise ScannerDataGatewayError(str(exc)) from exc

        try:
            source = self._factory.create(self.provider_name)
        except ProviderError as exc:
            raise ScannerDataGatewayError(
                f"Failed to create provider '{self.provider_name}': {exc}"
            ) from exc

        provider_symbol = self._to_provider_symbol(symbol)
        tf_enum = _TIMEFRAME_TO_ENUM[timeframe]

        end_ts = end or datetime.now()
        start_ts = start or (end_ts - timedelta(days=365))

        try:
            df = source.fetch_historical(
                symbol=provider_symbol,
                timeframe=tf_enum,
                start=start_ts,
                end=end_ts,
            )
        except NotImplementedError as exc:
            raise ScannerDataGatewayError(
                f"Provider '{self.provider_name}' does not support historical fetch yet"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise ScannerDataGatewayError(
                f"Historical fetch failed for provider '{self.provider_name}' "
                f"symbol={provider_symbol} timeframe={timeframe}: {exc}"
            ) from exc

        if df is None or getattr(df, "empty", True):
            raise ScannerDataGatewayError(
                f"Provider '{self.provider_name}' returned no data for "
                f"{provider_symbol} [{timeframe}]"
            )

        if hasattr(df, "attrs"):
            quality = dict(getattr(df, "attrs", {}).get("data_quality", {}))
            quality.setdefault("schema_version", "v1")
            quality.setdefault("provider", self.provider_name)
            quality.setdefault("source", "historical_fetch")
            quality.setdefault("generated_at", datetime.now(UTC).isoformat())
            quality.setdefault("fallback_provider", None)
            quality.setdefault("partial_data", False)
            quality.setdefault("stale_data", False)
            quality.setdefault("missing_bars_count", 0)
            quality.setdefault("auth_degraded", False)
            df.attrs["data_quality"] = quality

        try:
            return DataHandler(df)
        except Exception as exc:  # noqa: BLE001
            raise ScannerDataGatewayError(
                f"Fetched data validation failed for {provider_symbol} [{timeframe}]: {exc}"
            ) from exc

    def _to_provider_symbol(self, symbol: str) -> str:
        return self._symbol_mapper.to_provider_symbol(self.provider_name, symbol)
