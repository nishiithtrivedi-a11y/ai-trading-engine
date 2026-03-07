"""
Institutional flow analyzer (placeholder-ready with graceful degradation).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.market_intelligence.config import InstitutionalFlowConfig
from src.market_intelligence.models import InstitutionalFlowSnapshot


class InstitutionalFlowError(Exception):
    """Raised when institutional flow analysis fails and graceful fallback is disabled."""


@dataclass
class InstitutionalFlowAnalyzer:
    def analyze(self, config: InstitutionalFlowConfig) -> InstitutionalFlowSnapshot:
        if not config.enabled:
            return InstitutionalFlowSnapshot(
                data_available=False,
                summary="institutional flow disabled",
                metadata={"enabled": False},
            )

        if not config.flow_file:
            if config.allow_missing_data:
                return InstitutionalFlowSnapshot(
                    data_available=False,
                    summary="institutional flow file not configured",
                    metadata={"enabled": True},
                )
            raise InstitutionalFlowError("institutional flow file not configured")

        path = Path(config.flow_file)
        if not path.exists():
            if config.allow_missing_data:
                return InstitutionalFlowSnapshot(
                    data_available=False,
                    summary=f"institutional flow file missing: {path}",
                    metadata={"enabled": True},
                )
            raise InstitutionalFlowError(f"institutional flow file not found: {path}")

        try:
            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            if config.allow_missing_data:
                return InstitutionalFlowSnapshot(
                    data_available=False,
                    summary=f"failed to read institutional flow file: {exc}",
                    metadata={"enabled": True, "file": str(path)},
                )
            raise InstitutionalFlowError(f"Failed to read institutional flow file: {exc}") from exc

        if df.empty:
            return InstitutionalFlowSnapshot(
                data_available=False,
                summary="institutional flow file is empty",
                metadata={"file": str(path)},
            )

        row = df.iloc[-1]
        timestamp = pd.Timestamp(row["timestamp"]) if "timestamp" in df.columns else pd.Timestamp.now(tz="UTC")
        fii_net = float(row["fii_net"]) if "fii_net" in df.columns and pd.notna(row["fii_net"]) else None
        dii_net = float(row["dii_net"]) if "dii_net" in df.columns and pd.notna(row["dii_net"]) else None
        block_notional = (
            float(row["block_trade_notional"])
            if "block_trade_notional" in df.columns and pd.notna(row["block_trade_notional"])
            else None
        )

        summary = "institutional flow snapshot available"
        if fii_net is not None and dii_net is not None:
            net = fii_net + dii_net
            summary = f"combined institutional net flow {net:.2f}"

        return InstitutionalFlowSnapshot(
            timestamp=timestamp,
            data_available=True,
            fii_net=fii_net,
            dii_net=dii_net,
            block_trade_notional=block_notional,
            summary=summary,
            metadata={"file": str(path)},
        )
