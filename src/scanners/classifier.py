"""
Opportunity horizon classification by timeframe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.scanners.config import ScannerConfig, normalize_timeframe
from src.scanners.models import OpportunityClass


@dataclass
class OpportunityClassifier:
    intraday_timeframes: set[str] = field(default_factory=lambda: {"1m", "5m", "15m"})
    swing_timeframes: set[str] = field(default_factory=lambda: {"1h"})
    positional_timeframes: set[str] = field(default_factory=lambda: {"1D"})

    def classify(self, timeframe: str, config: ScannerConfig | None = None) -> OpportunityClass:
        tf = normalize_timeframe(timeframe)

        if tf in self.intraday_timeframes:
            return OpportunityClass.INTRADAY
        if tf in self.swing_timeframes:
            return OpportunityClass.SWING
        if tf in self.positional_timeframes:
            return OpportunityClass.POSITIONAL

        # Defensive fallback for any future higher timeframe aliases.
        return OpportunityClass.POSITIONAL
