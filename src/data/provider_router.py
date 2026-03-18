"""
Provider routing and switching utilities.

Supports:
- Single-provider mode (zerodha, dhan, csv, indian_csv, upstox)
- Auto mode (selects best provider for the workflow)
- Capability-based routing

This is a pure routing/capability layer — no execution behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.data.provider_capabilities import (
    AnalysisFamily,
    get_analysis_provider_feature_set,
    validate_analysis_provider_family,
    ProviderCapabilityError,
    ProviderFeatureSet,
    get_provider_feature_set,
)


class ProviderRoutingError(ValueError):
    """Raised when no provider can satisfy a routing request."""


@dataclass
class ProviderRoutingPolicy:
    """Policy for selecting providers across different workflow types.

    Attributes:
        default_provider: Used for all unspecified cases.
        derivatives_provider: Preferred for derivative data workflows.
        cash_provider: Preferred for cash/equity workflows.
        fallback_order: Ordered list of fallback providers if primary unavailable.
        allow_degraded: If True, degraded providers are still returned (with warnings).
    """

    default_provider: str = "zerodha"
    derivatives_provider: Optional[str] = None
    cash_provider: Optional[str] = None
    fallback_order: list[str] = field(
        default_factory=lambda: ["zerodha", "csv"]
    )
    allow_degraded: bool = True

    @classmethod
    def zerodha_only(cls) -> "ProviderRoutingPolicy":
        return cls(
            default_provider="zerodha",
            derivatives_provider="zerodha",
            cash_provider="zerodha",
            fallback_order=["zerodha", "csv"],
        )

    @classmethod
    def dhan_only(cls) -> "ProviderRoutingPolicy":
        return cls(
            default_provider="dhan",
            derivatives_provider="dhan",
            cash_provider="dhan",
            fallback_order=["dhan", "csv"],
        )

    @classmethod
    def dhan_primary_zerodha_cash(cls) -> "ProviderRoutingPolicy":
        """Use Dhan for derivatives, Zerodha for cash equities."""
        return cls(
            default_provider="zerodha",
            derivatives_provider="dhan",
            cash_provider="zerodha",
            fallback_order=["zerodha", "dhan", "csv"],
        )

    @classmethod
    def auto(cls) -> "ProviderRoutingPolicy":
        """Auto mode: capability-based selection with broadest fallback."""
        return cls(
            default_provider="zerodha",
            derivatives_provider=None,
            cash_provider=None,
            fallback_order=["zerodha", "dhan", "upstox", "csv"],
        )

    @classmethod
    def from_config(cls, config: dict) -> "ProviderRoutingPolicy":
        """Build from config dict (e.g., from YAML).

        Recognizes keys: default_provider, derivatives_provider,
        cash_provider, fallback_order, allow_degraded.
        """
        return cls(
            default_provider=config.get("default_provider", "zerodha"),
            derivatives_provider=config.get("derivatives_provider"),
            cash_provider=config.get("cash_provider"),
            fallback_order=config.get("fallback_order", ["zerodha", "csv"]),
            allow_degraded=config.get("allow_degraded", True),
        )


class ProviderRouter:
    """Route data requests to the appropriate provider.

    Usage::

        policy = ProviderRoutingPolicy.dhan_primary_zerodha_cash()
        router = ProviderRouter(policy)
        provider = router.select_for_derivatives("NFO")
        provider = router.select_for_cash("NSE")
    """

    def __init__(self, policy: Optional[ProviderRoutingPolicy] = None):
        self._policy = policy or ProviderRoutingPolicy()

    @property
    def policy(self) -> ProviderRoutingPolicy:
        return self._policy

    def select_for_derivatives(self, segment: str = "NFO") -> str:
        """Select the best provider for derivative data.

        Returns a provider name string from the routing policy.
        """
        preferred = (
            self._policy.derivatives_provider or self._policy.default_provider
        )
        return self._resolve_provider(
            preferred, require_derivatives=True, segment=segment
        )

    def select_for_cash(self, segment: str = "NSE") -> str:
        """Select the best provider for cash/equity data."""
        preferred = self._policy.cash_provider or self._policy.default_provider
        return self._resolve_provider(
            preferred, require_derivatives=False, segment=segment
        )

    def select_default(self) -> str:
        """Return the default provider."""
        return self._policy.default_provider

    def select_for_segment(self, segment: str) -> str:
        """Select provider based on segment (NSE→cash, NFO/MCX/CDS→derivatives)."""
        deriv_segments = {"NFO", "MCX", "CDS"}
        if segment.upper() in deriv_segments:
            return self.select_for_derivatives(segment)
        return self.select_for_cash(segment)

    def _resolve_provider(
        self,
        preferred: str,
        require_derivatives: bool = False,
        segment: str = "NSE",
    ) -> str:
        """Resolve provider with capability check and fallback."""
        candidates = [preferred] + [
            p for p in self._policy.fallback_order if p != preferred
        ]

        for candidate in candidates:
            try:
                fs = get_provider_feature_set(candidate)
                if require_derivatives and not fs.supports_derivatives:
                    continue
                if not fs.supports_segment(segment):
                    continue
                return candidate
            except ProviderCapabilityError:
                continue

        # If nothing satisfies requirements, return default
        return self._policy.default_provider

    def capability_report(self) -> dict:
        """Return a structured capability report for all providers in the policy."""
        all_providers = list(
            dict.fromkeys(
                [self._policy.default_provider]
                + (
                    [self._policy.derivatives_provider]
                    if self._policy.derivatives_provider
                    else []
                )
                + (
                    [self._policy.cash_provider]
                    if self._policy.cash_provider
                    else []
                )
                + self._policy.fallback_order
            )
        )

        report = {}
        for name in all_providers:
            try:
                fs = get_provider_feature_set(name)
                report[name] = {
                    "segments": list(fs.supported_segments),
                    "derivatives": fs.supports_derivatives,
                    "historical_derivatives": fs.supports_historical_derivatives,
                    "oi": fs.supports_oi,
                    "status": fs.implementation_status.value,
                }
            except ProviderCapabilityError:
                report[name] = {"error": "unknown provider"}

        return {
            "policy": {
                "default": self._policy.default_provider,
                "derivatives": self._policy.derivatives_provider,
                "cash": self._policy.cash_provider,
                "fallback_order": self._policy.fallback_order,
            },
            "providers": report,
        }


@dataclass
class AnalysisProviderRoutingPolicy:
    """Family-specific routing policy for non-technical analysis data."""

    fundamentals_provider: str = "none"
    macro_provider: str = "none"
    sentiment_provider: str = "none"
    intermarket_provider: str = "derived"
    fallback_order: list[str] = field(
        default_factory=lambda: ["fmp", "finnhub", "alphavantage", "eodhd", "none"]
    )
    allow_degraded: bool = True

    @classmethod
    def from_config(cls, config: dict) -> "AnalysisProviderRoutingPolicy":
        return cls(
            fundamentals_provider=str(config.get("fundamentals_provider", "none")).strip().lower(),
            macro_provider=str(config.get("macro_provider", "none")).strip().lower(),
            sentiment_provider=str(config.get("sentiment_provider", "none")).strip().lower(),
            intermarket_provider=str(config.get("intermarket_provider", "derived")).strip().lower(),
            fallback_order=[
                str(provider).strip().lower()
                for provider in config.get(
                    "fallback_order",
                    ["fmp", "finnhub", "alphavantage", "eodhd", "none"],
                )
            ],
            allow_degraded=bool(config.get("allow_degraded", True)),
        )

    def preferred_for_family(self, family: AnalysisFamily | str) -> str:
        clean_family = (
            family.value if isinstance(family, AnalysisFamily) else str(family).strip().lower()
        )
        mapping = {
            AnalysisFamily.FUNDAMENTALS.value: self.fundamentals_provider,
            AnalysisFamily.MACRO.value: self.macro_provider,
            AnalysisFamily.SENTIMENT.value: self.sentiment_provider,
            AnalysisFamily.INTERMARKET.value: self.intermarket_provider,
        }
        preferred = str(mapping.get(clean_family, "none")).strip().lower()
        if clean_family == AnalysisFamily.INTERMARKET.value and preferred == "none":
            return "derived"
        return preferred


class AnalysisProviderRouter:
    """Select providers independently for fundamentals/macro/sentiment/intermarket."""

    def __init__(self, policy: Optional[AnalysisProviderRoutingPolicy] = None):
        self._policy = policy or AnalysisProviderRoutingPolicy()

    @property
    def policy(self) -> AnalysisProviderRoutingPolicy:
        return self._policy

    def select_for_family(self, family: AnalysisFamily | str) -> str:
        clean_family = (
            family if isinstance(family, AnalysisFamily) else AnalysisFamily(str(family).strip().lower())
        )
        preferred = self._policy.preferred_for_family(clean_family)
        candidates = [preferred] + [
            provider
            for provider in self._policy.fallback_order
            if provider != preferred
        ]
        if clean_family == AnalysisFamily.INTERMARKET:
            candidates.append("derived")
        if "none" not in candidates:
            candidates.append("none")

        for candidate in candidates:
            try:
                validate_analysis_provider_family(candidate, clean_family)
                return candidate
            except ProviderCapabilityError:
                continue
        return "none"

    def capability_report(self) -> dict:
        families = (
            AnalysisFamily.FUNDAMENTALS,
            AnalysisFamily.MACRO,
            AnalysisFamily.SENTIMENT,
            AnalysisFamily.INTERMARKET,
        )
        report: dict[str, dict] = {}
        for family in families:
            configured = self._policy.preferred_for_family(family)
            selected = self.select_for_family(family)
            try:
                fs = get_analysis_provider_feature_set(selected)
                report[family.value] = {
                    "configured_provider": configured,
                    "selected_provider": selected,
                    "supports_fundamentals": fs.supports_fundamentals,
                    "supports_macro": fs.supports_macro,
                    "supports_sentiment": fs.supports_sentiment,
                    "supports_news": fs.supports_news,
                    "supports_macro_calendar": fs.supports_macro_calendar,
                    "supports_intermarket_inputs": fs.supports_intermarket_inputs,
                    "status": fs.implementation_status.value,
                }
            except ProviderCapabilityError:
                report[family.value] = {
                    "configured_provider": configured,
                    "selected_provider": selected,
                    "status": "unknown_provider",
                }

        return {
            "policy": {
                "fundamentals_provider": self._policy.fundamentals_provider,
                "macro_provider": self._policy.macro_provider,
                "sentiment_provider": self._policy.sentiment_provider,
                "intermarket_provider": self._policy.intermarket_provider,
                "fallback_order": list(self._policy.fallback_order),
                "allow_degraded": self._policy.allow_degraded,
            },
            "families": report,
        }
