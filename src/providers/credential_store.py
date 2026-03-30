"""
Safe credential store for provider secrets.

Reads credential presence from environment variables and the .env file.
NEVER returns raw secret values; only masked presence indicators.
Supports storing credentials by updating the .env file safely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.providers.models import PROVIDER_REGISTRY, ProviderType

_CONFIG_FIELD_MAP: dict[str, str] = {
    "API_KEY": "api_key",
    "API_SECRET": "api_secret",
    "ACCESS_TOKEN": "access_token",
    "CLIENT_ID": "api_key",
}

_ENV_ALIAS_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "dhan": {
        "CLIENT_ID": ("DHAN_CLIENT_ID", "DHAN_API_KEY"),
        "ACCESS_TOKEN": ("DHAN_ACCESS_TOKEN",),
    }
}


@dataclass
class CredentialStore:
    """Manages provider credential presence and masked indicators."""

    env_file_path: Path = field(default_factory=lambda: Path(".env"))

    def _env_candidates(self, provider_type: ProviderType, credential_name: str) -> tuple[str, ...]:
        cfg = PROVIDER_REGISTRY.get(provider_type)
        if cfg is None:
            return ()
        normalized = str(credential_name).strip().upper()
        defaults = (f"{cfg.env_key_prefix}_{normalized}",)
        aliases = _ENV_ALIAS_MAP.get(provider_type.value, {}).get(normalized, ())
        merged: list[str] = []
        for key in defaults + aliases:
            if key and key not in merged:
                merged.append(key)
        return tuple(merged)

    def _resolve_config_value(
        self,
        provider_type: ProviderType,
        credential_name: str,
        *,
        config: Any | None = None,
    ) -> str:
        field_name = _CONFIG_FIELD_MAP.get(str(credential_name).strip().upper())
        if not field_name:
            return ""
        try:
            cfg = config
            if cfg is None:
                from src.data.provider_config import load_provider_config

                cfg = load_provider_config()
            entry = cfg.get_provider(provider_type.value)
            if entry is None:
                return ""
            return str(getattr(entry, field_name, "") or "").strip()
        except Exception:
            return ""

    def _resolve_credential_value(
        self,
        provider_type: ProviderType,
        credential_name: str,
        *,
        config: Any | None = None,
    ) -> str:
        for env_key in self._env_candidates(provider_type, credential_name):
            env_value = str(os.environ.get(env_key, "")).strip()
            if env_value:
                return env_value
        return self._resolve_config_value(
            provider_type,
            credential_name,
            config=config,
        )

    def has_credentials(self, provider_type: ProviderType) -> bool:
        """Check if all required credentials exist for a provider."""
        cfg = PROVIDER_REGISTRY.get(provider_type)
        if cfg is None:
            return False
        provider_cfg = None
        try:
            from src.data.provider_config import load_provider_config

            provider_cfg = load_provider_config()
        except Exception:
            provider_cfg = None
        for credential_name in cfg.required_credentials:
            if not self._resolve_credential_value(
                provider_type,
                credential_name,
                config=provider_cfg,
            ):
                return False
        return True

    def get_credential_status(self, provider_type: ProviderType) -> dict[str, bool]:
        """Return required credential presence flags without exposing values."""
        cfg = PROVIDER_REGISTRY.get(provider_type)
        if cfg is None:
            return {}
        provider_cfg = None
        try:
            from src.data.provider_config import load_provider_config

            provider_cfg = load_provider_config()
        except Exception:
            provider_cfg = None
        status: dict[str, bool] = {}
        for credential_name in cfg.required_credentials:
            status[credential_name] = bool(
                self._resolve_credential_value(
                    provider_type,
                    credential_name,
                    config=provider_cfg,
                )
            )
        return status

    def get_masked_indicators(self, provider_type: ProviderType) -> dict[str, str]:
        """Return masked indicators for required credentials."""
        cfg = PROVIDER_REGISTRY.get(provider_type)
        if cfg is None:
            return {}
        provider_cfg = None
        try:
            from src.data.provider_config import load_provider_config

            provider_cfg = load_provider_config()
        except Exception:
            provider_cfg = None
        indicators: dict[str, str] = {}
        for credential_name in cfg.required_credentials:
            value = self._resolve_credential_value(
                provider_type,
                credential_name,
                config=provider_cfg,
            )
            if value:
                indicators[credential_name] = self._mask_value(value)
            else:
                indicators[credential_name] = "Not Set"
        return indicators

    def store_credential(
        self,
        provider_type: ProviderType,
        credential_name: str,
        value: str,
    ) -> bool:
        """Store a credential in the .env file and update environment."""
        cfg = PROVIDER_REGISTRY.get(provider_type)
        if cfg is None:
            return False

        if credential_name not in cfg.required_credentials:
            return False

        env_key = f"{cfg.env_key_prefix}_{credential_name}"
        os.environ[env_key] = value
        self._update_env_file(env_key, value)
        return True

    def _update_env_file(self, key: str, value: str) -> None:
        lines: list[str] = []
        found = False

        if self.env_file_path.exists():
            raw = self.env_file_path.read_text(encoding="utf-8")
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped.startswith(f"{key}="):
                    lines.append(f"{key}={value}")
                    found = True
                else:
                    lines.append(line)

        if not found:
            lines.append(f"{key}={value}")

        self.env_file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _mask_value(value: str) -> str:
        if not value:
            return "Not Set"
        if len(value) <= 3:
            return "•" * len(value)
        return "•" * (len(value) - 3) + value[-3:]
