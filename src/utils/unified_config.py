"""
Unified Configuration Layer (C3 Architecture)
=============================================
Provides a centralized mechanism for resolving configuration parameters 
across the trading engine, enforcing a strict precedence hierarchy:

Precedence (Highest to Lowest):
  1. Explicit Overrides (e.g. CLI arguments)
  2. Environment Variables (e.g. .env)
  3. YAML Configuration Files (e.g. config/*.yaml)
  4. Code Defaults (Pydantic / dataclass default values)

This module handles merging these sources dynamically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, TypeVar, Type

try:
    import yaml
except ImportError:
    yaml = None  # Handle gracefully if yaml is not installed

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT_DIR / "config"


class UnifiedConfig:
    """Core configuration resolver utilizing the C3 precedence model."""

    def __init__(self, prefix: str = "", yaml_path: Optional[Path] = None):
        """
        Args:
            prefix: Prefix for environment variables (e.g., "AI_TRADING_").
            yaml_path: Specific YAML file to load defaults from.
        """
        self.prefix = prefix
        self.yaml_path = yaml_path
        self._yaml_cache: dict[str, Any] = {}
        if yaml_path and yaml_path.exists() and yaml is not None:
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    self._yaml_cache = yaml.safe_load(f) or {}
            except Exception as e:
                import logging
                logging.getLogger("unified_config").warning(f"Failed to load YAML {yaml_path}: {e}")

    def get(self, key: str, default: Any = None, env_key: Optional[str] = None) -> Any:
        """
        Resolve a single configuration key using the unified precedence rules.
        """
        # 1. Environment Variables (incorporating prefix)
        env_lookup = env_key or f"{self.prefix}{key.upper()}"
        if env_lookup in os.environ:
            val = os.environ[env_lookup]
            # Try to cast basic boolean strings
            if val.lower() in ("true", "1", "yes"): return True
            if val.lower() in ("false", "0", "no"): return False
            # Try to cast ints/floats if possible
            try:
                if "." in val:
                    return float(val)
                return int(val)
            except ValueError:
                return val

        # 2. YAML Configuration
        if key in self._yaml_cache:
            return self._yaml_cache[key]

        # 3. Default
        return default

    def resolve_pydantic(self, model_cls: Type[T], overrides: Optional[dict[str, Any]] = None) -> T:
        """
        Resolve an entire Pydantic config model.
        Overrides (e.g. CLI args) form the base, backfilled by ENV, then YAML.
        """
        resolved: dict[str, Any] = {}
        
        # We look at all fields defined in the Pydantic model
        for field_name, field_info in model_cls.model_fields.items():
            # If an explicit override is provided, it wins (Level 1)
            if overrides and field_name in overrides and overrides[field_name] is not None:
                resolved[field_name] = overrides[field_name]
                continue
                
            # Otherwise, resolve through ENV -> YAML -> fallback to None
            # (If it returns None, Pydantic's internal default kicks in)
            val = self.get(field_name)
            if val is not None:
                resolved[field_name] = val
                
        return model_cls(**resolved)


def load_unified_config(
    model_cls: Type[T], 
    overrides: Optional[dict[str, Any]] = None, 
    yaml_filename: Optional[str] = None,
    env_prefix: str = ""
) -> T:
    """
    Helper function to load a Pydantic configuration model seamlessly.
    """
    yaml_path = CONFIG_DIR / yaml_filename if yaml_filename else None
    resolver = UnifiedConfig(prefix=env_prefix, yaml_path=yaml_path)
    return resolver.resolve_pydantic(model_cls, overrides)
