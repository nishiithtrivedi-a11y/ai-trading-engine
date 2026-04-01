"""
Data provider configuration with YAML + environment variable support.

Loads provider settings from config/data_providers.yaml and allows
environment variables to override credentials (e.g. ZERODHA_API_KEY).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.utils.logger import setup_logger

logger = setup_logger("provider_config")

# Default config file location (relative to project root)
DEFAULT_CONFIG_PATH = "config/data_providers.yaml"
_SECRET_FIELDS = ("api_key", "api_secret", "access_token")


class ProviderCredentials(BaseModel):
    """Credentials for a broker API provider."""
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""

    @property
    def is_configured(self) -> bool:
        """True if all three credential fields are non-empty."""
        return bool(self.api_key and self.api_secret and self.access_token)


class ProviderEntry(BaseModel):
    """Configuration for a single data provider."""
    enabled: bool = True
    data_dir: str = "data/"
    timezone: str = "Asia/Kolkata"
    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""

    def get_credentials(self) -> ProviderCredentials:
        return ProviderCredentials(
            api_key=self.api_key,
            api_secret=self.api_secret,
            access_token=self.access_token,
        )


class AnalysisProvidersConfig(BaseModel):
    """Family-specific analysis provider selection."""

    fundamentals_provider: str = "none"
    macro_provider: str = "none"
    sentiment_provider: str = "none"
    intermarket_provider: str = "derived"
    allow_derived_sentiment_fallback: bool = True

    def provider_for_family(self, family: str) -> str:
        clean_family = str(family).strip().lower()
        mapping = {
            "fundamentals": self.fundamentals_provider,
            "fundamental": self.fundamentals_provider,
            "macro": self.macro_provider,
            "sentiment": self.sentiment_provider,
            "intermarket": self.intermarket_provider,
        }
        value = mapping.get(clean_family, "none")
        clean_value = str(value).strip().lower()
        if not clean_value:
            return "none"
        return clean_value

    def normalized(self) -> dict[str, Any]:
        return {
            "fundamentals_provider": self.provider_for_family("fundamentals"),
            "macro_provider": self.provider_for_family("macro"),
            "sentiment_provider": self.provider_for_family("sentiment"),
            "intermarket_provider": self.provider_for_family("intermarket"),
            "allow_derived_sentiment_fallback": bool(self.allow_derived_sentiment_fallback),
        }


class DataProvidersConfig(BaseModel):
    """Top-level data providers configuration."""
    default_provider: str = Field(default="csv")
    providers: Dict[str, ProviderEntry] = Field(default_factory=dict)
    analysis_providers: AnalysisProvidersConfig = Field(
        default_factory=AnalysisProvidersConfig
    )

    def get_provider(self, name: str) -> Optional[ProviderEntry]:
        """Get a provider entry by name, or None if not found."""
        return self.providers.get(name)

    def get_default(self) -> Optional[ProviderEntry]:
        """Get the default provider entry."""
        return self.providers.get(self.default_provider)

    def is_provider_enabled(self, name: str) -> bool:
        """Check if a provider is enabled."""
        entry = self.providers.get(name)
        return entry is not None and entry.enabled

    def list_enabled_providers(self) -> list[str]:
        """Return names of all enabled providers."""
        return [name for name, entry in self.providers.items() if entry.enabled]

    def save_config(self, path: Optional[str | Path] = None) -> bool:
        """Persist the current configuration back to the YAML file.

        This allows promoting connected providers to primary runtime source
        without manual file editing.

        SECURITY: Secret credential fields are always scrubbed before write.
        Runtime credentials must come from environment/.env sources only.
        """
        import yaml

        target = Path(path or DEFAULT_CONFIG_PATH)
        try:
            # Use model_dump for Pydantic v2 compatibility if available, else .dict()
            data = self.model_dump() if hasattr(self, "model_dump") else self.dict()
            data = _sanitize_for_persistence(data)

            with open(target, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
            logger.info(f"Saved provider configuration to {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to save provider config to {target}: {str(e)}")
            return False


def _sanitize_for_persistence(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a persistence-safe config payload with secrets removed."""
    cleaned: Dict[str, Any] = dict(data)
    providers = cleaned.get("providers", {})
    if isinstance(providers, dict):
        sanitized_providers: Dict[str, Any] = {}
        for name, entry in providers.items():
            if not isinstance(entry, dict):
                sanitized_providers[name] = entry
                continue
            item = dict(entry)
            for secret_key in _SECRET_FIELDS:
                if secret_key in item:
                    item[secret_key] = ""
            sanitized_providers[name] = item
        cleaned["providers"] = sanitized_providers
    return cleaned


def _apply_env_overrides(config: DataProvidersConfig) -> DataProvidersConfig:
    """Override provider credentials from environment variables.

    Env var naming convention:
        {PROVIDER_NAME}_API_KEY
        {PROVIDER_NAME}_API_SECRET
        {PROVIDER_NAME}_ACCESS_TOKEN

    E.g. ZERODHA_API_KEY, UPSTOX_API_SECRET
    """
    for name, entry in config.providers.items():
        prefix = name.upper()
        env_key = os.environ.get(f"{prefix}_API_KEY")
        env_secret = os.environ.get(f"{prefix}_API_SECRET")
        env_token = os.environ.get(f"{prefix}_ACCESS_TOKEN")

        if env_key:
            entry.api_key = env_key
            logger.info(f"Loaded {prefix}_API_KEY from environment")
        if env_secret:
            entry.api_secret = env_secret
            logger.info(f"Loaded {prefix}_API_SECRET from environment")
        if env_token:
            entry.access_token = env_token
            logger.info(f"Loaded {prefix}_ACCESS_TOKEN from environment")

    analysis_env_mapping = {
        "fundamentals_provider": "FUNDAMENTALS_PROVIDER",
        "macro_provider": "MACRO_PROVIDER",
        "sentiment_provider": "SENTIMENT_PROVIDER",
        "intermarket_provider": "INTERMARKET_PROVIDER",
    }
    for field_name, env_name in analysis_env_mapping.items():
        env_value = os.environ.get(env_name)
        if env_value is not None and str(env_value).strip():
            setattr(config.analysis_providers, field_name, str(env_value).strip().lower())
            logger.info(f"Loaded {env_name} from environment")

    sentiment_fallback_env = os.environ.get("ANALYSIS_ALLOW_DERIVED_SENTIMENT_FALLBACK")
    if sentiment_fallback_env is not None:
        clean = str(sentiment_fallback_env).strip().lower()
        config.analysis_providers.allow_derived_sentiment_fallback = clean in {
            "1",
            "true",
            "yes",
            "on",
        }

    return config


def load_provider_config(
    config_path: Optional[str] = None,
) -> DataProvidersConfig:
    """Load data provider configuration from YAML file + env vars.

    Args:
        config_path: Path to YAML config file. Defaults to
                     config/data_providers.yaml in project root.

    Returns:
        Validated DataProvidersConfig instance.
    """
    path = Path(config_path or DEFAULT_CONFIG_PATH)

    if not path.exists():
        logger.warning(f"Provider config not found at {path}, using defaults")
        config = DataProvidersConfig()
        return _apply_env_overrides(config)

    try:
        import yaml
    except ImportError:
        logger.warning(
            "PyYAML not installed — cannot load provider config from YAML. "
            "Install with: pip install pyyaml. Using defaults."
        )
        config = DataProvidersConfig()
        return _apply_env_overrides(config)

    with open(path) as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    # Parse provider entries
    providers_raw = raw.get("providers", {})
    providers: Dict[str, ProviderEntry] = {}
    for name, settings in providers_raw.items():
        if isinstance(settings, dict):
            providers[name] = ProviderEntry(**settings)
        else:
            providers[name] = ProviderEntry()

    config = DataProvidersConfig(
        default_provider=raw.get("default_provider", "csv"),
        providers=providers,
        analysis_providers=(
            AnalysisProvidersConfig(**raw.get("analysis_providers", {}))
            if isinstance(raw.get("analysis_providers", {}), dict)
            else AnalysisProvidersConfig()
        ),
    )

    config = _apply_env_overrides(config)
    logger.info(
        f"Loaded provider config from {path} | "
        f"default={config.default_provider} | "
        f"enabled={config.list_enabled_providers()}"
    )

    return config
