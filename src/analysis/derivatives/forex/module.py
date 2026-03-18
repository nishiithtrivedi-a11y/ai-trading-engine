"""ForexAnalysisModule — INR currency derivatives context (CDS)."""
from __future__ import annotations

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class ForexAnalysisModule(BaseAnalysisModule):
    """Currency derivatives features for INR pairs (CDS segment)."""

    name: str = "forex"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return str(instrument_type).lower() in (
            "future", "option", "forex", "currency"
        )

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        from src.analysis.derivatives.futures.module import FuturesAnalysisModule

        fut = FuturesAnalysisModule()
        features = fut.build_features(data, context)
        features["asset_class"] = "currency"
        features["pair"] = context.get("underlying", "USDINR")
        return features

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Currency derivative features for INR pairs (CDS).",
        }
