"""
Provider factory — creates data sources from provider config.

Registry pattern: maps provider names to data source classes.
Handles credential injection, disabled-provider errors, and CSV fallback.
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from src.data.base import BaseDataSource
from src.data.instrument_metadata import InstrumentType
from src.data.provider_capabilities import (
    AnalysisFamily,
    AnalysisProviderFeatureSet,
    ProviderFeatureSet,
    get_analysis_provider_feature_set,
    get_analysis_provider_diagnostics,
    get_provider_feature_set,
    validate_analysis_provider_family,
    validate_provider_workflow,
)
from src.data.provider_config import (
    DataProvidersConfig,
    ProviderEntry,
    load_provider_config,
)
from src.data.provider_runtime import (
    get_provider_readiness_report,
    resolve_provider_credentials,
)
from src.utils.logger import setup_logger

logger = setup_logger("provider_factory")


class ProviderError(Exception):
    """Raised when a provider cannot be created."""


class ProviderFactory:
    """Creates data source instances from provider configuration.

    Usage:
        factory = ProviderFactory.from_config()
        source = factory.create("zerodha", data_file="data/RELIANCE_1D.csv")
        dh = DataHandler.from_source(source)
    """

    _registry: Dict[str, Type[BaseDataSource]] = {}

    def __init__(self, config: Optional[DataProvidersConfig] = None) -> None:
        self.config = config or load_provider_config()
        self._register_defaults()

    @classmethod
    def from_config(
        cls, config_path: Optional[str] = None
    ) -> ProviderFactory:
        """Create factory from a YAML config file."""
        config = load_provider_config(config_path)
        return cls(config)

    def _register_defaults(self) -> None:
        """Register built-in provider classes (lazy imports to avoid cycles)."""
        # We don't import at module level to keep things lightweight.
        # Actual imports happen in create() when needed.
        pass

    def create(
        self,
        provider_name: Optional[str] = None,
        data_file: Optional[str] = None,
        **kwargs,
    ) -> BaseDataSource:
        """Create a data source instance for the given provider.

        Args:
            provider_name: Provider name (csv, indian_csv, zerodha, upstox).
                           Defaults to the config's default_provider.
            data_file: Path to data file (for CSV-based providers).
            **kwargs: Additional arguments passed to the data source constructor.

        Returns:
            A BaseDataSource instance ready for .load().

        Raises:
            ProviderError: If the provider is disabled, not found, or
                           missing required credentials.
        """
        name = provider_name or self.config.default_provider
        entry = self.config.get_provider(name)

        if entry is None:
            raise ProviderError(
                f"Unknown provider '{name}'. "
                f"Available: {list(self.config.providers.keys())}"
            )
        readiness = get_provider_readiness_report(
            name,
            config=self.config,
            require_enabled=True,
        )
        if not readiness.can_instantiate:
            raise ProviderError(readiness.reason)

        return self._build_source(name, entry, data_file, **kwargs)

    def _build_source(
        self,
        name: str,
        entry: ProviderEntry,
        data_file: Optional[str],
        **kwargs,
    ) -> BaseDataSource:
        """Build the actual data source object."""
        if name == "csv":
            return self._build_csv(entry, data_file, **kwargs)
        elif name == "indian_csv":
            return self._build_indian_csv(entry, data_file, **kwargs)
        elif name == "zerodha":
            return self._build_zerodha(entry, **kwargs)
        elif name == "upstox":
            return self._build_upstox(entry, **kwargs)
        elif name == "dhan":
            return self._build_dhan(entry, **kwargs)
        else:
            # Check custom registry
            if name in self._registry:
                cls = self._registry[name]
                return cls(**kwargs)
            raise ProviderError(
                f"No builder registered for provider '{name}'."
            )

    def _build_csv(
        self, entry: ProviderEntry, data_file: Optional[str], **kwargs
    ) -> BaseDataSource:
        """Build a plain CSV source (uses DataHandler.from_csv under the hood)."""
        from src.data.indian_data_loader import IndianCSVDataSource

        file_path = data_file or "data/sample_data.csv"
        # Plain CSV still uses IndianCSVDataSource with IST defaults
        # but without strict session validation expectations
        return IndianCSVDataSource(file_path=file_path, timezone=entry.timezone)

    def _build_indian_csv(
        self, entry: ProviderEntry, data_file: Optional[str], **kwargs
    ) -> BaseDataSource:
        """Build an Indian CSV data source."""
        from src.data.indian_data_loader import IndianCSVDataSource

        file_path = data_file or "data/sample_data.csv"
        return IndianCSVDataSource(
            file_path=file_path,
            timezone=kwargs.get("timezone", entry.timezone),
        )

    def _build_zerodha(self, entry: ProviderEntry, **kwargs) -> BaseDataSource:
        """Build a Zerodha data source with credential injection.

        Supports optional kwargs: default_symbol, default_timeframe,
        default_days, exchange — passed through to ZerodhaDataSource.
        """
        from src.data.sources import ZerodhaDataSource

        resolved = resolve_provider_credentials("zerodha", config=self.config)
        if not resolved.is_fully_configured:
            raise ProviderError(
                "Zerodha credentials not configured. "
                "Set ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN "
                "environment variables or fill in config/data_providers.yaml."
            )

        return ZerodhaDataSource(
            api_key=resolved.values.get("API_KEY", ""),
            api_secret=resolved.values.get("API_SECRET", ""),
            access_token=resolved.values.get("ACCESS_TOKEN", ""),
            **kwargs,
        )

    def _build_upstox(self, entry: ProviderEntry, **kwargs) -> BaseDataSource:
        """Build an Upstox data source with credential + safe fallback support."""
        from src.data.sources import UpstoxDataSource

        resolved = resolve_provider_credentials("upstox", config=self.config)
        if not resolved.is_fully_configured:
            logger.warning(
                "Upstox credentials are not configured. "
                "Provider will run in degraded CSV-fallback mode when data files are available."
            )

        return UpstoxDataSource(
            api_key=resolved.values.get("API_KEY", ""),
            api_secret=resolved.values.get("API_SECRET", ""),
            access_token=resolved.values.get("ACCESS_TOKEN", ""),
            data_dir=kwargs.get("data_dir", entry.data_dir),
        )

    def _build_dhan(self, entry: ProviderEntry, **kwargs) -> BaseDataSource:
        """Build a DhanHQ data source. Degrades gracefully if SDK unavailable."""
        from src.data.dhan_source import DhanHQDataSource

        resolved = resolve_provider_credentials("dhan", config=self.config)
        return DhanHQDataSource(
            client_id=resolved.values.get("CLIENT_ID", ""),
            access_token=resolved.values.get("ACCESS_TOKEN", ""),
            **kwargs,
        )

    @classmethod
    def register(cls, name: str, source_class: Type[BaseDataSource]) -> None:
        """Register a custom data source class.

        Args:
            name: Provider name to register under.
            source_class: Class implementing BaseDataSource.
        """
        cls._registry[name] = source_class
        logger.info(f"Registered custom provider: {name}")

    def list_providers(self) -> Dict[str, bool]:
        """Return dict of provider_name -> enabled status."""
        return {
            name: entry.enabled
            for name, entry in self.config.providers.items()
        }

    def get_capabilities(
        self,
        provider_name: Optional[str] = None,
    ) -> ProviderFeatureSet:
        """Return capability metadata for a provider."""
        name = provider_name or self.config.default_provider
        return get_provider_feature_set(name)

    def validate_capabilities(
        self,
        provider_name: Optional[str] = None,
        *,
        require_historical_data: bool = False,
        require_live_quotes: bool = False,
        timeframe: Optional[str] = None,
        instrument_type: InstrumentType | str | None = None,
    ) -> ProviderFeatureSet:
        """Validate that a provider can satisfy a requested workflow."""
        name = provider_name or self.config.default_provider
        return validate_provider_workflow(
            name,
            require_historical_data=require_historical_data,
            require_live_quotes=require_live_quotes,
            timeframe=timeframe,
            instrument_type=instrument_type,
        )

    def get_analysis_provider(self, family: AnalysisFamily | str) -> str:
        clean_family = (
            family.value if isinstance(family, AnalysisFamily) else str(family).strip().lower()
        )
        provider_name = self.config.analysis_providers.provider_for_family(clean_family)
        if clean_family == AnalysisFamily.INTERMARKET.value and provider_name == "none":
            return "derived"
        return provider_name

    def get_analysis_capabilities(
        self,
        family: AnalysisFamily | str,
    ) -> AnalysisProviderFeatureSet:
        provider_name = self.get_analysis_provider(family)
        return get_analysis_provider_feature_set(provider_name)

    def validate_analysis_capabilities(
        self,
        family: AnalysisFamily | str,
    ) -> AnalysisProviderFeatureSet:
        provider_name = self.get_analysis_provider(family)
        return validate_analysis_provider_family(provider_name, family)

    def analysis_capability_report(self) -> dict:
        configured = self.config.analysis_providers.normalized()
        report: dict[str, dict] = {}
        for family in (
            AnalysisFamily.FUNDAMENTALS,
            AnalysisFamily.MACRO,
            AnalysisFamily.SENTIMENT,
            AnalysisFamily.INTERMARKET,
        ):
            selected = self.get_analysis_provider(family)
            payload_available = False
            try:
                feature_set = validate_analysis_provider_family(selected, family)
                report[family.value] = get_analysis_provider_diagnostics(
                    selected,
                    configured=selected != "none",
                    payload_available=payload_available,
                    stale=False,
                )
                report[family.value]["selected_provider"] = feature_set.provider_name
                report[family.value]["available"] = True
            except Exception as exc:  # noqa: BLE001
                diagnostics = get_analysis_provider_diagnostics(
                    selected if selected else "none",
                    configured=selected != "none",
                    payload_available=payload_available,
                    stale=False,
                )
                diagnostics["available"] = False
                diagnostics["reason"] = str(exc)
                report[family.value] = diagnostics

        report["allow_derived_sentiment_fallback"] = bool(
            self.config.analysis_providers.allow_derived_sentiment_fallback
        )
        report["configured"] = configured
        return report
