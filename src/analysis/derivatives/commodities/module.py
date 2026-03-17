"""
CommoditiesAnalysisModule.

Commodities-specific features (contango/backwardation, seasonal patterns) when fully wired.

This is a stub implementation.  It is registered in the default
AnalysisRegistry but disabled by default.  Enable it and implement
build_features() when the required data feeds are available.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class CommoditiesAnalysisModule(BaseAnalysisModule):
    """Commodities-specific features (contango/backwardation, seasonal patterns). Stub implementation."""

    name: str = "commodities"
    version: str = "0.1.0"

    def is_enabled(self, config=None) -> bool:
        return False  # disabled until data feed is wired

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        return {}

    def health_check(self) -> dict:
        return {
            "status": "stub",
            "module": self.name,
            "version": self.version,
            "description": "Commodities-specific features (contango/backwardation, seasonal patterns). Stub.",
        }
