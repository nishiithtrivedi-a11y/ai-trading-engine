"""
Data poller for realtime cycles.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.data.instrument_metadata import InstrumentType
from src.data.provider_capabilities import (
    ProviderCapabilityError,
    validate_provider_workflow,
)
from src.data.provider_factory import ProviderFactory
from src.realtime.config import RealtimeConfig
from src.realtime.models import PollResult, PolledSymbolData, RealTimeMode
from src.scanners.data_gateway import DataGateway


class DataPollerError(Exception):
    """Raised for unrecoverable poller errors."""


@dataclass
class DataPoller:
    provider_name: str = "csv"
    data_gateway: Optional[DataGateway] = None
    provider_factory: Optional[ProviderFactory] = None

    def __post_init__(self) -> None:
        self.data_gateway = self.data_gateway or DataGateway(
            provider_name=self.provider_name,
        )
        self.provider_factory = self.provider_factory or ProviderFactory.from_config()

    def poll(
        self,
        symbols: list[str],
        timeframes: list[str],
        config: RealtimeConfig,
    ) -> PollResult:
        mode = config.mode if config.enabled else RealTimeMode.OFF
        result = PollResult(mode=mode)

        if mode == RealTimeMode.OFF:
            result.warnings.append("realtime disabled or mode=off; polling skipped")
            return result

        if not symbols:
            result.warnings.append("No symbols provided to poll")
            return result
        if not timeframes:
            result.warnings.append("No timeframes provided to poll")
            return result

        for symbol in symbols:
            for timeframe in timeframes:
                record: Optional[PolledSymbolData] = None

                if mode == RealTimeMode.POLLING and config.enable_live_provider:
                    record = self._poll_live(symbol=symbol, timeframe=timeframe, result=result)

                if record is None:
                    record = self._poll_latest_bar(symbol=symbol, timeframe=timeframe)

                result.records.append(record)
                if not record.success:
                    result.errors.append(f"{record.symbol} {record.timeframe}: {record.message}")

        return result

    def _poll_latest_bar(self, symbol: str, timeframe: str) -> PolledSymbolData:
        try:
            handler = self.data_gateway.load_data(symbol, timeframe)
            frame = handler.data
            if frame.empty:
                return PolledSymbolData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=None,
                    close_price=None,
                    bars=0,
                    source="historical_snapshot",
                    success=False,
                    message="no data returned",
                )
            last = frame.iloc[-1]
            timestamp = pd.Timestamp(frame.index[-1])
            freshness_seconds = self._freshness_seconds(timestamp)
            stale_data = freshness_seconds > self._stale_threshold_seconds(timeframe)
            quality = {
                "schema_version": "v1",
                "provider": self.provider_name,
                "source": "historical_snapshot",
                "freshness_seconds": freshness_seconds,
                "stale_data": stale_data,
                "partial_data": len(frame) < 2,
                "missing_bars_count": 0,
                "fallback_provider": None,
                "auth_degraded": False,
            }
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                close_price=float(last["close"]),
                bars=len(frame),
                source="historical_snapshot",
                success=True,
                metadata={"data_quality": quality},
            )
        except Exception as exc:  # noqa: BLE001
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=None,
                close_price=None,
                bars=0,
                source="historical_snapshot",
                success=False,
                message=str(exc),
            )

    def _poll_live(
        self,
        symbol: str,
        timeframe: str,
        result: PollResult,
    ) -> Optional[PolledSymbolData]:
        try:
            validate_provider_workflow(
                self.provider_name,
                require_live_quotes=True,
                timeframe=timeframe,
                instrument_type=InstrumentType.EQUITY,
            )
        except ProviderCapabilityError as exc:
            result.warnings.append(f"{exc}; fallback to historical snapshot")
            return None

        try:
            source = self.provider_factory.create(self.provider_name)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(
                f"live provider create failed for '{self.provider_name}': {exc}; fallback to historical snapshot"
            )
            return None

        fetch_live = getattr(source, "fetch_live", None)
        if not callable(fetch_live):
            result.warnings.append(
                f"provider '{self.provider_name}' does not support fetch_live; fallback to historical snapshot"
            )
            return None

        try:
            payload = self._call_fetch_live(
                fetch_live=fetch_live,
                symbol=symbol,
                timeframe=timeframe,
            )
        except NotImplementedError:
            result.warnings.append(
                f"provider '{self.provider_name}' fetch_live not implemented; fallback to historical snapshot"
            )
            return None
        except Exception as exc:  # noqa: BLE001
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=None,
                close_price=None,
                bars=0,
                source="live_poll",
                success=False,
                message=f"live poll failed: {exc}",
            )

        return self._parse_live_payload(symbol=symbol, timeframe=timeframe, payload=payload)

    @staticmethod
    def _call_fetch_live(fetch_live, symbol: str, timeframe: str):
        """Call provider fetch_live with a normalized scanner contract."""
        errors: list[Exception] = []

        def _try_call(*args, **kwargs):
            try:
                return fetch_live(*args, **kwargs)
            except TypeError as exc:
                errors.append(exc)
                return None

        # Preferred explicit keyword contract.
        result = _try_call(symbol=symbol, timeframe=timeframe)
        if result is not None:
            return result

        # Common symbol-only keyword signature.
        result = _try_call(symbol=symbol)
        if result is not None:
            return result

        # Positional contracts for sources with non-standard parameter names.
        result = _try_call(symbol, timeframe)
        if result is not None:
            return result

        result = _try_call(symbol)
        if result is not None:
            return result

        # Signature inspection fallback for custom callables.
        try:
            signature = inspect.signature(fetch_live)
            params = signature.parameters
            if "timeframe" in params:
                return fetch_live(symbol=symbol, timeframe=timeframe)
            if "symbol" in params:
                return fetch_live(symbol=symbol)
        except (TypeError, ValueError):
            pass

        if errors:
            raise errors[-1]
        return fetch_live(symbol)

    @staticmethod
    def _parse_live_payload(
        symbol: str,
        timeframe: str,
        payload,
    ) -> PolledSymbolData:
        if isinstance(payload, pd.DataFrame):
            if payload.empty:
                return PolledSymbolData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=None,
                    close_price=None,
                    bars=0,
                    source="live_poll",
                    success=False,
                    message="empty live dataframe",
                )
            last = payload.iloc[-1]
            ts = payload.index[-1] if len(payload.index) > 0 else None
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=pd.Timestamp(ts) if ts is not None else None,
                close_price=float(last.get("close")),
                bars=len(payload),
                source="live_poll",
                success=True,
                metadata={
                    "data_quality": {
                        "schema_version": "v1",
                        "provider": "unknown",
                        "source": "live_dataframe",
                        "freshness_seconds": (
                            DataPoller._freshness_seconds(pd.Timestamp(ts))
                            if ts is not None
                            else None
                        ),
                        "stale_data": False,
                        "partial_data": len(payload) < 2,
                        "missing_bars_count": 0,
                        "fallback_provider": None,
                        "auth_degraded": False,
                    }
                },
            )

        if isinstance(payload, pd.Series):
            timestamp = payload.get("timestamp")
            ts_value = pd.Timestamp(timestamp) if timestamp is not None else None
            freshness = DataPoller._freshness_seconds(ts_value) if ts_value is not None else None
            quality = payload.attrs.get("data_quality", {}) if hasattr(payload, "attrs") else {}
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts_value,
                close_price=(float(payload.get("close")) if payload.get("close") is not None else None),
                bars=1,
                source="live_poll",
                success=payload.get("close") is not None,
                message="" if payload.get("close") is not None else "missing close in payload",
                metadata={
                    "data_quality": (
                        quality
                        if quality
                        else {
                            "schema_version": "v1",
                            "provider": "unknown",
                            "source": "live_series",
                            "freshness_seconds": freshness,
                            "stale_data": False,
                            "partial_data": False,
                            "missing_bars_count": 0,
                            "fallback_provider": None,
                            "auth_degraded": False,
                        }
                    )
                },
            )

        if isinstance(payload, dict):
            ts_value = (
                pd.Timestamp(payload["timestamp"])
                if payload.get("timestamp") is not None
                else None
            )
            quality = dict(payload.get("data_quality", {})) if isinstance(payload.get("data_quality"), dict) else {}
            if not quality:
                quality = {
                    "schema_version": "v1",
                    "provider": "unknown",
                    "source": "live_dict",
                    "freshness_seconds": (
                        DataPoller._freshness_seconds(ts_value)
                        if ts_value is not None
                        else None
                    ),
                    "stale_data": False,
                    "partial_data": False,
                    "missing_bars_count": 0,
                    "fallback_provider": None,
                    "auth_degraded": False,
                }
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts_value,
                close_price=(
                    float(payload["close"]) if payload.get("close") is not None else None
                ),
                bars=int(payload.get("bars", 1)),
                source="live_poll",
                success=payload.get("close") is not None,
                message="" if payload.get("close") is not None else "missing close in payload",
                metadata={
                    **{k: v for k, v in payload.items() if k not in {"timestamp", "close", "bars", "data_quality"}},
                    "data_quality": quality,
                },
            )

        return PolledSymbolData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=None,
            close_price=None,
            bars=0,
            source="live_poll",
            success=False,
            message=f"unsupported live payload type: {type(payload).__name__}",
        )

    @staticmethod
    def _freshness_seconds(timestamp: pd.Timestamp | None) -> float:
        if timestamp is None:
            return 0.0
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        now = pd.Timestamp.now(tz="UTC")
        return max(0.0, float((now - ts).total_seconds()))

    @staticmethod
    def _stale_threshold_seconds(timeframe: str) -> float:
        mapping = {
            "1m": 3 * 60.0,
            "5m": 20 * 60.0,
            "15m": 45 * 60.0,
            "1h": 3 * 3600.0,
            "1D": 3 * 24 * 3600.0,
        }
        return mapping.get(str(timeframe).strip(), 24 * 3600.0)
