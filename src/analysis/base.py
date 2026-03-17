"""
Base contract for all analysis plugin modules.

Every analysis module in the plugin framework must inherit from
BaseAnalysisModule and implement its interface.  Default implementations
return safe, empty values so stub modules can be registered without
providing full implementations.
"""

from __future__ import annotations

from abc import ABC
from typing import Optional

import pandas as pd


class BaseAnalysisModule(ABC):
    """
    Abstract base class for all analysis plugin modules.

    Subclasses must set ``name`` and ``version`` as class-level attributes.

    All methods have safe default implementations that return empty / neutral
    values, so partial implementations are valid.  Only ``name`` and
    ``version`` are strictly required.

    Integration contract
    -------------------
    - ``build_features(data, context)`` — compute numeric features from OHLCV data.
      Returns a flat dict of ``{feature_name: value}`` that populates the
      corresponding domain slot in :class:`~src.analysis.feature_schema.FeatureOutput`.

    - ``build_signals(features, context)`` — derive discrete signals from
      computed features.  Returns a list of signal dicts.

    - ``build_context(data, context)`` — compute higher-level context
      (e.g. regime, macro state) that other modules may consume.

    - ``health_check()`` — return a dict with at least ``{"status": ..., "module": self.name}``.
      Stub modules return ``"stub"``; fully implemented modules return ``"ok"``.
    """

    #: Unique module name (snake_case).  Must be set at class level.
    name: str = ""

    #: Semantic version string.  Must be set at class level.
    version: str = "0.1.0"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_enabled(self, config: Optional[dict] = None) -> bool:
        """Return True if this module should run for the given config.

        Override to implement conditional enablement (e.g. profile-driven).
        Default: always enabled.
        """
        return True

    def supports(self, instrument_type: str, timeframe: str) -> bool:
        """Return True if this module supports the given instrument/timeframe.

        Override to restrict operation to specific instrument types or
        timeframes.  Default: supports everything.
        """
        return True

    # ------------------------------------------------------------------
    # Core analysis methods
    # ------------------------------------------------------------------

    def build_features(
        self, data: pd.DataFrame, context: dict
    ) -> dict:
        """Compute numeric features from OHLCV data.

        Parameters
        ----------
        data:
            OHLCV DataFrame with DatetimeIndex and lowercase column names
            (``open``, ``high``, ``low``, ``close``, ``volume``).
        context:
            Contextual metadata (signal, setup, regime, etc.).

        Returns
        -------
        dict
            Flat mapping of feature names to scalar values (float or None).
        """
        return {}

    def build_signals(
        self, features: dict, context: dict
    ) -> list:
        """Derive discrete signals from computed features.

        Parameters
        ----------
        features:
            Output of :meth:`build_features`.
        context:
            Contextual metadata.

        Returns
        -------
        list
            List of signal dicts, each with at least ``{"signal": ..., "source": self.name}``.
        """
        return []

    def build_context(
        self, data: pd.DataFrame, context: dict
    ) -> dict:
        """Compute higher-level context usable by other modules.

        Returns
        -------
        dict
            Arbitrary context dict (e.g. regime state, macro outlook).
        """
        return {}

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict:
        """Return a health status dict for this module.

        Returns
        -------
        dict
            At minimum ``{"status": ..., "module": self.name, "version": self.version}``.
        """
        return {
            "status": "ok",
            "module": self.name,
            "version": self.version,
        }

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, version={self.version!r})"
