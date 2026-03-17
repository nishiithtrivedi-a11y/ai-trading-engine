"""
Modular Analysis Plugin Framework.

Provides a unified, pluggable interface for technical, quantitative,
fundamental, macro, sentiment, intermarket, and derivatives analysis modules.

Usage:
    from src.analysis.registry import AnalysisRegistry
    from src.analysis.feature_schema import FeatureOutput

    registry = AnalysisRegistry.create_default()
    features = FeatureOutput.from_modules(registry.enabled_modules(), data, context)
"""

from src.analysis.base import BaseAnalysisModule
from src.analysis.feature_schema import FeatureOutput
from src.analysis.registry import AnalysisRegistry

__all__ = [
    "BaseAnalysisModule",
    "FeatureOutput",
    "AnalysisRegistry",
]
