"""CommoditiesAnalysisModule — thin wrapper over futures module for MCX context."""
from __future__ import annotations

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class CommoditiesAnalysisModule(BaseAnalysisModule):
    """Commodity futures features (thin wrapper). Delegates to futures logic."""

    name: str = "commodities"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return str(instrument_type).lower() in ("future", "commodity", "futures")

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        from src.analysis.derivatives.futures.module import FuturesAnalysisModule

        fut = FuturesAnalysisModule()
        features = fut.build_features(data, context)
        features["asset_class"] = "commodity"
        return features

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Commodity futures features (MCX). Delegates to futures module.",
        }
