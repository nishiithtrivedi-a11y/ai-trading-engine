"""
Analysis module registry.

The AnalysisRegistry is the central hub for all analysis plugin modules.
It handles:

- Module registration and unregistration
- Dynamic enable / disable per module
- Resolution by analysis type, instrument type, or timeframe
- Health aggregation across registered modules

Usage
-----
    # Use the default registry (technical + quant enabled):
    registry = AnalysisRegistry.create_default()

    # Register a custom module:
    registry.register(MyCustomModule())
    registry.enable("my_custom")

    # Get all currently-enabled modules:
    modules = registry.enabled_modules()
"""

from __future__ import annotations

from typing import Optional

from src.analysis.base import BaseAnalysisModule


class AnalysisRegistryError(ValueError):
    """Raised when a registry operation fails (e.g. duplicate name)."""


class AnalysisRegistry:
    """
    Central registry for analysis plugin modules.

    Each registered module must have a unique ``name`` attribute.
    Modules can be enabled/disabled at runtime without re-registering.
    """

    def __init__(self) -> None:
        self._modules: dict[str, BaseAnalysisModule] = {}
        self._disabled: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, module: BaseAnalysisModule, *, replace: bool = False) -> None:
        """Register a module.

        Parameters
        ----------
        module:
            Module instance to register.  Must have a non-empty ``name``.
        replace:
            If True, silently replaces an existing module with the same name.
            If False (default), raises :exc:`AnalysisRegistryError` on conflict.
        """
        if not module.name:
            raise AnalysisRegistryError(
                f"Module {module.__class__.__name__!r} has no name; "
                "set the 'name' class attribute before registering."
            )
        if module.name in self._modules and not replace:
            raise AnalysisRegistryError(
                f"A module named {module.name!r} is already registered. "
                "Use replace=True to overwrite."
            )
        self._modules[module.name] = module

    def unregister(self, name: str) -> None:
        """Remove a module by name.  No-op if not registered."""
        self._modules.pop(name, None)
        self._disabled.discard(name)

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, name: str) -> None:
        """Enable a registered module.

        Raises :exc:`AnalysisRegistryError` if the module is not registered.
        """
        if name not in self._modules:
            raise AnalysisRegistryError(
                f"Cannot enable unknown module {name!r}. Register it first."
            )
        self._disabled.discard(name)

    def disable(self, name: str) -> None:
        """Disable a registered module (keeps it registered but skips it in ``enabled_modules``).

        Raises :exc:`AnalysisRegistryError` if the module is not registered.
        """
        if name not in self._modules:
            raise AnalysisRegistryError(
                f"Cannot disable unknown module {name!r}. Register it first."
            )
        self._disabled.add(name)

    def is_enabled(self, name: str) -> bool:
        """Return True if the named module is registered and enabled."""
        return name in self._modules and name not in self._disabled

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[BaseAnalysisModule]:
        """Return the module with the given name, or None."""
        return self._modules.get(name)

    def enabled_modules(self) -> list[BaseAnalysisModule]:
        """Return all currently-enabled module instances, in insertion order."""
        return [
            mod
            for name, mod in self._modules.items()
            if name not in self._disabled
        ]

    def all_modules(self) -> list[BaseAnalysisModule]:
        """Return all registered module instances (enabled and disabled)."""
        return list(self._modules.values())

    def resolve(
        self,
        *,
        analysis_type: Optional[str] = None,
        instrument_type: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> list[BaseAnalysisModule]:
        """
        Return enabled modules filtered by optional criteria.

        Parameters
        ----------
        analysis_type:
            If provided, only return the module whose ``name`` matches.
        instrument_type:
            If provided, only return modules whose ``supports()`` method
            returns True for this instrument type.
        timeframe:
            If provided, only return modules whose ``supports()`` method
            returns True for this timeframe.

        Returns
        -------
        list[BaseAnalysisModule]
        """
        candidates = self.enabled_modules()

        if analysis_type is not None:
            candidates = [m for m in candidates if m.name == analysis_type]

        if instrument_type is not None or timeframe is not None:
            it = instrument_type or ""
            tf = timeframe or ""
            candidates = [m for m in candidates if m.supports(it, tf)]

        return candidates

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> dict:
        """Return aggregated health for all registered modules."""
        module_health = {}
        overall_status = "ok"

        for name, module in self._modules.items():
            try:
                mh = module.health_check()
            except Exception as exc:  # noqa: BLE001
                mh = {"status": "error", "module": name, "error": str(exc)}

            module_health[name] = mh
            if mh.get("status") not in ("ok", "stub"):
                overall_status = "degraded"

        return {
            "status": overall_status,
            "registered": list(self._modules.keys()),
            "enabled": [m.name for m in self.enabled_modules()],
            "disabled": sorted(self._disabled),
            "modules": module_health,
        }

    # ------------------------------------------------------------------
    # Convenience constructor
    # ------------------------------------------------------------------

    @classmethod
    def create_default(cls) -> "AnalysisRegistry":
        """
        Create a registry pre-loaded with the default module set.

        Enabled by default:
            - TechnicalAnalysisModule  (name="technical")
            - QuantAnalysisModule      (name="quant")

        Registered but disabled by default:
            - FundamentalAnalysisModule
            - MacroAnalysisModule
            - SentimentAnalysisModule
            - IntermarketAnalysisModule
            - FuturesAnalysisModule
            - OptionsAnalysisModule
            - CommoditiesAnalysisModule
            - ForexAnalysisModule
            - CryptoAnalysisModule
        """
        from src.analysis.technical.module import TechnicalAnalysisModule
        from src.analysis.quant.module import QuantAnalysisModule
        from src.analysis.fundamental.module import FundamentalAnalysisModule
        from src.analysis.macro.module import MacroAnalysisModule
        from src.analysis.sentiment.module import SentimentAnalysisModule
        from src.analysis.intermarket.module import IntermarketAnalysisModule
        from src.analysis.derivatives.futures.module import FuturesAnalysisModule
        from src.analysis.derivatives.options.module import OptionsAnalysisModule
        from src.analysis.derivatives.commodities.module import CommoditiesAnalysisModule
        from src.analysis.derivatives.forex.module import ForexAnalysisModule
        from src.analysis.derivatives.crypto.module import CryptoAnalysisModule

        registry = cls()

        # Active modules
        registry.register(TechnicalAnalysisModule())
        registry.register(QuantAnalysisModule())

        # Optional modules -- registered but disabled by default
        for stub in [
            FundamentalAnalysisModule(),
            MacroAnalysisModule(),
            SentimentAnalysisModule(),
            IntermarketAnalysisModule(),
            FuturesAnalysisModule(),
            OptionsAnalysisModule(),
            CommoditiesAnalysisModule(),
            ForexAnalysisModule(),
            CryptoAnalysisModule(),
        ]:
            registry.register(stub)
            registry.disable(stub.name)

        return registry

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._modules)

    def __repr__(self) -> str:
        enabled = [m.name for m in self.enabled_modules()]
        return (
            f"AnalysisRegistry("
            f"registered={list(self._modules.keys())}, "
            f"enabled={enabled})"
        )
