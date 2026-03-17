"""
ForexAnalysisModule.

Forex-specific features (carry, interest rate differential, COT data) when fully wired.

This is a stub implementation.  It is registered in the default
AnalysisRegistry but disabled by default.  Enable it and implement
build_features() when the required data feeds are available.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class ForexAnalysisModule(BaseAnalysisModule):
    """Forex-specific features (carry, interest rate differential, COT data). Stub implementation."""

    name: str = "forex"
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
            "description": "Forex-specific features (carry, interest rate differential, COT data). Stub.",
        }
