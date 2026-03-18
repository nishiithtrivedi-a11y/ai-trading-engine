"""
OptionsAnalysisModule — activated in Phase 3.

Computes option-chain features using the Phase 3 option chain builder and analytics.
Requires option chain data in context.
"""
from __future__ import annotations

import pandas as pd

from src.analysis.base import BaseAnalysisModule


class OptionsAnalysisModule(BaseAnalysisModule):
    """Options-specific features: PCR, IV skew, OI concentration, max pain."""

    name: str = "options"
    version: str = "1.0.0"

    def is_enabled(self, config=None) -> bool:
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        return str(instrument_type).lower() in ("option", "options")

    def build_features(self, data: pd.DataFrame, context: dict) -> dict:
        """Build options features.

        Context keys used (all optional):
            option_chain (OptionChain): assembled option chain
            chain_analytics (ChainAnalytics): pre-computed analytics
            spot_price (float): current spot price
            days_to_expiry (float): DTE for this chain
        """
        features: dict = {}

        # From pre-computed chain analytics (preferred path)
        analytics = context.get("chain_analytics")
        if analytics is not None:
            features["pcr_overall"] = float(analytics.pcr_overall or 0)
            features["call_oi_total"] = float(analytics.call_oi_total or 0)
            features["put_oi_total"] = float(analytics.put_oi_total or 0)
            features["chain_breadth"] = float(analytics.chain_breadth or 0)
            if analytics.iv_skew is not None:
                features["iv_skew"] = float(analytics.iv_skew)
            if analytics.atm_strike is not None:
                features["atm_strike"] = float(analytics.atm_strike)
            if analytics.max_pain is not None:
                features["max_pain"] = float(analytics.max_pain)
            if analytics.call_resistance is not None:
                features["call_resistance"] = float(analytics.call_resistance)
            if analytics.put_support is not None:
                features["put_support"] = float(analytics.put_support)
            return features

        # Fallback: direct from OptionChain
        chain = context.get("option_chain")
        if chain is not None:
            pcr = chain.chain_pcr
            if pcr is not None:
                features["pcr_overall"] = float(pcr)
            features["call_oi_total"] = float(chain.call_oi_total)
            features["put_oi_total"] = float(chain.put_oi_total)
            atm = chain.get_atm_strike()
            if atm is not None:
                features["atm_strike"] = float(atm)

        # DTE
        dte = context.get("days_to_expiry")
        if dte is not None:
            features["days_to_expiry"] = float(dte)

        return features

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
            "description": "Options features: PCR, IV skew, OI concentration, max pain.",
        }
