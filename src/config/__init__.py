"""
Configuration package for the analysis plugin framework.

Provides:
- AnalysisProfileLoader: load and apply named analysis profiles
- AnalysisProfile: named set of enabled/disabled analysis modules
"""

from src.config.analysis_profiles import AnalysisProfile, AnalysisProfileLoader

__all__ = ["AnalysisProfile", "AnalysisProfileLoader"]
