"""
Safe credential store for provider secrets.

Reads credential presence from environment variables and the .env file.
NEVER returns raw secret values — only masked presence indicators.
Supports storing credentials by updating the .env file safely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.providers.models import PROVIDER_REGISTRY, ProviderType


@dataclass
class CredentialStore:
    """Manages provider credential presence and masked indicators.

    All credential access goes through environment variables.
    Raw secrets are NEVER returned by any public method.
    """

    env_file_path: Path = field(default_factory=lambda: Path(".env"))

    def has_credentials(self, provider_type: ProviderType) -> bool:
        """Check if all required credentials exist for a provider."""
        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return False
        for cred_name in config.required_credentials:
            env_key = f"{config.env_key_prefix}_{cred_name}"
            if not os.environ.get(env_key):
                return False
        return True

    def get_credential_status(self, provider_type: ProviderType) -> dict[str, bool]:
        """Return which credentials are present (True/False) — never the values."""
        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return {}
        status: dict[str, bool] = {}
        for cred_name in config.required_credentials:
            env_key = f"{config.env_key_prefix}_{cred_name}"
            status[cred_name] = bool(os.environ.get(env_key))
        return status

    def get_masked_indicators(self, provider_type: ProviderType) -> dict[str, str]:
        """Return masked presence indicators for all credentials.

        Format: "•••••xyz" (last 3 chars visible) or "Not Set".
        """
        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return {}
        indicators: dict[str, str] = {}
        for cred_name in config.required_credentials:
            env_key = f"{config.env_key_prefix}_{cred_name}"
            value = os.environ.get(env_key, "")
            if value:
                indicators[cred_name] = self._mask_value(value)
            else:
                indicators[cred_name] = "Not Set"
        return indicators

    def store_credential(
        self,
        provider_type: ProviderType,
        credential_name: str,
        value: str,
    ) -> bool:
        """Store a credential in the .env file and update the environment.

        Returns True if stored successfully.
        """
        config = PROVIDER_REGISTRY.get(provider_type)
        if config is None:
            return False

        if credential_name not in config.required_credentials:
            return False

        env_key = f"{config.env_key_prefix}_{credential_name}"

        # Update runtime environment
        os.environ[env_key] = value

        # Update .env file
        self._update_env_file(env_key, value)
        return True

    def _update_env_file(self, key: str, value: str) -> None:
        """Update or add a key=value pair in the .env file."""
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

        self.env_file_path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _mask_value(value: str) -> str:
        """Mask a credential value, showing only the last 3 characters."""
        if not value:
            return "Not Set"
        if len(value) <= 3:
            return "•" * len(value)
        return "•" * (len(value) - 3) + value[-3:]
