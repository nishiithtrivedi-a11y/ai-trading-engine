"""
Standardised feature output schema for the analysis plugin framework.

All analysis modules contribute their outputs to domain-specific slots in
:class:`FeatureOutput`.  Downstream consumers (scanner, decision engine,
monitoring) read features from this structured container rather than from
ad-hoc dicts, enabling safe forward/backward compatibility.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.analysis.base import BaseAnalysisModule


@dataclass
class FeatureOutput:
    """
    Structured container for multi-domain analysis features.

    Each field is a flat dict mapping ``feature_name`` → ``scalar_value``
    (typically ``float | None``).  Empty dicts represent modules that did
    not run or returned no features.

    Domain slots
    ------------
    technical:    Technical indicator features (RSI, SMA, ATR, trend state …)
    quant:        Quantitative / statistical features (volatility, momentum, z-score …)
    fundamental:  Fundamental data features (P/E, revenue growth …) — stub
    macro:        Macro-economic features (rates, GDP, inflation …) — stub
    sentiment:    Sentiment features (news score, options flow …) — stub
    intermarket:  Intermarket features (correlation, sector rotation …) — stub
    derivatives:  Derivatives-specific features (OI, PCR, basis …) — stub
    """

    technical: dict = field(default_factory=dict)
    quant: dict = field(default_factory=dict)
    fundamental: dict = field(default_factory=dict)
    macro: dict = field(default_factory=dict)
    sentiment: dict = field(default_factory=dict)
    intermarket: dict = field(default_factory=dict)
    derivatives: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain dict representation (JSON-serialisable)."""
        return asdict(self)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def empty(cls) -> "FeatureOutput":
        """Return a FeatureOutput with all domain slots empty."""
        return cls()

    @classmethod
    def from_modules(
        cls,
        modules: "list[BaseAnalysisModule]",
        data: pd.DataFrame,
        context: dict,
    ) -> "FeatureOutput":
        """
        Run a list of enabled modules and collect their features into a
        FeatureOutput instance.

        Each module's ``name`` attribute is used to identify which domain
        slot to populate.  If a module name does not match a known domain
        slot, its features are silently skipped (future-proof).

        Errors from individual modules are caught and silently suppressed
        so that a single failing module does not abort the pipeline.

        Parameters
        ----------
        modules:
            List of :class:`~src.analysis.base.BaseAnalysisModule` instances
            to run (already filtered to enabled-only).
        data:
            OHLCV DataFrame.
        context:
            Contextual metadata dict.

        Returns
        -------
        FeatureOutput
        """
        output = cls()
        _DOMAIN_SLOTS = frozenset(output.to_dict().keys())

        for module in modules:
            try:
                features = module.build_features(data, context)
                if not isinstance(features, dict):
                    continue
                # Map module name to domain slot (e.g. "technical" → output.technical)
                slot_name = module.name
                if slot_name in _DOMAIN_SLOTS:
                    existing: dict = getattr(output, slot_name)
                    existing.update(features)
            except Exception:  # noqa: BLE001 — module errors must not propagate
                pass

        return output

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def has_features(self) -> bool:
        """Return True if any domain slot contains at least one feature."""
        return any(getattr(self, slot) for slot in self.to_dict().keys())

    def merged(self) -> dict:
        """Return all features merged into a single flat dict.

        Keys from later domains overwrite earlier ones on collision
        (technical < quant < fundamental < macro < sentiment <
         intermarket < derivatives).
        """
        merged: dict = {}
        for slot_features in self.to_dict().values():
            merged.update(slot_features)
        return merged
