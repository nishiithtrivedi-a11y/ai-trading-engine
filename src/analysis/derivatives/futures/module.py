"""
FuturesAnalysisModule — activated in Phase 3.

Computes futures-specific features using the Phase 2+3 data foundation.
Requires contract data in context (from DerivativeDataFetcher or InstrumentRegistry).
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class FuturesAnalysisModule(BaseAnalysisModule):
    """Futures-specific features: DTE, basis, roll proximity, OI context."""

    name: str = "futures"
    version: str = "1.0.0"   # upgraded from 0.1.0

    def is_enabled(self, config=None) -> bool:
        return True  # Now active — enabled when profile includes "futures"

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return str(instrument_type).lower() in (
            "future", "futures", "commodity", "forex"
        )

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        """Build futures features.

        Context keys used (all optional):
            contract_info (FuturesContractInfo): current contract metadata
            spot_price (float): spot/cash price for basis calculation
            futures_price (float): current futures price
            oi (int): open interest
            as_of (date): reference date for DTE
        """
        features: dict = {}

        # Days to expiry
        contract_info = context.get("contract_info")
        if contract_info is not None and hasattr(contract_info, "days_to_expiry"):
            features["days_to_expiry"] = float(contract_info.days_to_expiry)
            features["roll_imminent"] = float(contract_info.days_to_expiry <= 5)
            features["contract_age_pct"] = 0.0  # placeholder if no start date
        elif context.get("expiry") and context.get("as_of"):
            expiry = context["expiry"]
            as_of = (
                context["as_of"]
                if isinstance(context["as_of"], date)
                else date.today()
            )
            dte = max(0, (expiry - as_of).days)
            features["days_to_expiry"] = float(dte)
            features["roll_imminent"] = float(dte <= 5)

        # Basis (futures - spot)
        spot = context.get("spot_price")
        futures = context.get("futures_price")
        if spot is not None and futures is not None and spot > 0:
            basis = futures - spot
            features["basis"] = basis
            features["basis_pct"] = basis / spot * 100
            features["contango"] = float(basis > 0)
            features["backwardation"] = float(basis < 0)

        # OI features
        oi = context.get("oi")
        if oi is not None:
            features["open_interest"] = float(oi)

        # From OHLCV data — price momentum proxy
        if len(data) >= 2 and "close" in data.columns:
            closes = data["close"].dropna()
            if len(closes) >= 2:
                features["price_change_pct"] = float(
                    (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
                )

        return features

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Futures features: DTE, basis, roll proximity, OI context.",
        }
