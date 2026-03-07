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


class DataProvidersConfig(BaseModel):
    """Top-level data providers configuration."""
    default_provider: str = Field(default="csv")
    providers: Dict[str, ProviderEntry] = Field(default_factory=dict)

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
    )

    config = _apply_env_overrides(config)
    logger.info(
        f"Loaded provider config from {path} | "
        f"default={config.default_provider} | "
        f"enabled={config.list_enabled_providers()}"
    )

    return config
