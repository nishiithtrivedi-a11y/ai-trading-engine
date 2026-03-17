"""
Analysis profile loader.

Loads named analysis profiles from ``analysis_profiles.yaml`` and applies
them to an :class:`~src.analysis.registry.AnalysisRegistry`, enabling
exactly the modules specified in the profile and disabling all others.

Usage
-----
    from src.config.analysis_profiles import AnalysisProfileLoader
    from src.analysis.registry import AnalysisRegistry

    registry = AnalysisRegistry.create_default()
    loader = AnalysisProfileLoader()

    # Apply a named profile
    profile = loader.get("swing_equity")
    loader.apply_to_registry(profile, registry)

    # Inspect which modules are now enabled
    print(registry.enabled_modules())
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.analysis.registry import AnalysisRegistry


class AnalysisProfileError(ValueError):
    """Raised when a profile cannot be loaded or applied."""


# Default path to the bundled YAML file
_DEFAULT_PROFILES_PATH = Path(__file__).parent / "analysis_profiles.yaml"


@dataclass
class AnalysisProfile:
    """
    Named analysis profile.

    Attributes
    ----------
    name:
        Profile identifier (matches the YAML top-level key).
    description:
        Human-readable description of the profile.
    enabled:
        Names of analysis modules to enable when this profile is applied.
    """

    name: str
    description: str = ""
    enabled: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for name in self.enabled:
            if name not in seen:
                seen.add(name)
                unique.append(name)
        self.enabled = unique


class AnalysisProfileLoader:
    """
    Loads analysis profiles from a YAML file and applies them to a registry.

    Parameters
    ----------
    path:
        Path to the YAML profiles file.  Defaults to the bundled
        ``analysis_profiles.yaml`` in the same directory as this module.
    """

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self._path = Path(path) if path is not None else _DEFAULT_PROFILES_PATH
        self._profiles: Optional[dict[str, AnalysisProfile]] = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> dict[str, AnalysisProfile]:
        """
        Load profiles from the YAML file.

        Results are cached; call :meth:`reload` to force re-read.

        Returns
        -------
        dict[str, AnalysisProfile]
            Mapping of profile name → :class:`AnalysisProfile`.
        """
        if self._profiles is not None:
            return self._profiles
        return self.reload()

    def reload(self) -> dict[str, AnalysisProfile]:
        """Force reload profiles from the YAML file."""
        if not self._path.exists():
            raise AnalysisProfileError(
                f"Analysis profiles file not found: {self._path}"
            )

        with open(self._path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            raise AnalysisProfileError(
                f"Expected a mapping at the top level of {self._path}"
            )

        profiles: dict[str, AnalysisProfile] = {}
        for profile_name, spec in raw.items():
            if not isinstance(spec, dict):
                raise AnalysisProfileError(
                    f"Profile {profile_name!r} must be a mapping, got {type(spec).__name__}"
                )
            enabled = spec.get("enabled", [])
            if not isinstance(enabled, list):
                raise AnalysisProfileError(
                    f"Profile {profile_name!r}.enabled must be a list"
                )
            profiles[profile_name] = AnalysisProfile(
                name=profile_name,
                description=str(spec.get("description", "")).strip(),
                enabled=[str(m) for m in enabled],
            )

        self._profiles = profiles
        return profiles

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, profile_name: str) -> AnalysisProfile:
        """
        Return the named profile.

        Raises
        ------
        AnalysisProfileError
            If the profile is not found.
        """
        profiles = self.load()
        if profile_name not in profiles:
            available = sorted(profiles.keys())
            raise AnalysisProfileError(
                f"Analysis profile {profile_name!r} not found. "
                f"Available profiles: {available}"
            )
        return profiles[profile_name]

    def list_profiles(self) -> list[str]:
        """Return a sorted list of available profile names."""
        return sorted(self.load().keys())

    # ------------------------------------------------------------------
    # Registry application
    # ------------------------------------------------------------------

    def apply_to_registry(
        self,
        profile: AnalysisProfile,
        registry: AnalysisRegistry,
    ) -> None:
        """
        Apply a profile to a registry.

        Modules listed in ``profile.enabled`` are enabled.
        All other registered modules are disabled.
        Modules that are listed in the profile but not registered are
        silently skipped (allows profiles to reference future modules).

        Parameters
        ----------
        profile:
            Profile to apply.
        registry:
            Registry to modify in-place.
        """
        enabled_names = set(profile.enabled)

        for module in registry.all_modules():
            name = module.name
            if name in enabled_names:
                registry.enable(name)
            else:
                registry.disable(name)

    def apply_profile_by_name(
        self,
        profile_name: str,
        registry: AnalysisRegistry,
    ) -> AnalysisProfile:
        """
        Load a profile by name and apply it to the registry.

        Convenience wrapper combining :meth:`get` and
        :meth:`apply_to_registry`.

        Parameters
        ----------
        profile_name:
            Profile identifier from the YAML file.
        registry:
            Registry to modify.

        Returns
        -------
        AnalysisProfile
            The applied profile.
        """
        profile = self.get(profile_name)
        self.apply_to_registry(profile, registry)
        return profile
