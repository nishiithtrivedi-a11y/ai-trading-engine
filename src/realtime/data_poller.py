"""
Data poller for realtime cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

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
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=frame.index[-1],
                close_price=float(last["close"]),
                bars=len(frame),
                source="historical_snapshot",
                success=True,
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
            payload = fetch_live(symbol=symbol, timeframe=timeframe)
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
            )

        if isinstance(payload, dict):
            return PolledSymbolData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=(
                    pd.Timestamp(payload["timestamp"])
                    if payload.get("timestamp") is not None
                    else None
                ),
                close_price=(
                    float(payload["close"]) if payload.get("close") is not None else None
                ),
                bars=int(payload.get("bars", 1)),
                source="live_poll",
                success=payload.get("close") is not None,
                message="" if payload.get("close") is not None else "missing close in payload",
                metadata={k: v for k, v in payload.items() if k not in {"timestamp", "close", "bars"}},
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
