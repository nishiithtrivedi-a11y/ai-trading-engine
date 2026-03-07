"""
Configuration models for the Phase 7 strategy research lab.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("weights cannot be empty")
    clean: dict[str, float] = {}
    for key, value in weights.items():
        w = float(value)
        if w < 0:
            raise ValueError("weights cannot be negative")
        clean[str(key)] = w
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("weights total must be > 0")
    return {k: v / total for k, v in clean.items()}


@dataclass
class ResearchLabGeneratorConfig:
    use_default_templates: bool = True
    strategy_param_grids: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    max_candidates: int = 200

    def __post_init__(self) -> None:
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")


@dataclass
class ParameterSurfaceConfig:
    stable_top_percentile: float = 0.20
    unstable_bottom_percentile: float = 0.20
    min_trades_required: int = 5

    def __post_init__(self) -> None:
        if not 0 < self.stable_top_percentile < 1:
            raise ValueError("stable_top_percentile must be in (0, 1)")
        if not 0 < self.unstable_bottom_percentile < 1:
            raise ValueError("unstable_bottom_percentile must be in (0, 1)")
        if self.min_trades_required < 0:
            raise ValueError("min_trades_required must be >= 0")


@dataclass
class RobustnessAnalyzerConfig:
    walk_forward_train_size: int = 120
    walk_forward_test_size: int = 30
    walk_forward_step_size: int = 30
    monte_carlo_simulations: int = 100
    monte_carlo_seed: int = 42
    noise_injection_std: float = 0.005
    parameter_perturbation_pct: float = 0.10
    overall_weights: dict[str, float] = field(
        default_factory=lambda: {
            "walk_forward": 0.35,
            "monte_carlo": 0.35,
            "noise_resilience": 0.15,
            "parameter_stability": 0.15,
        }
    )

    def __post_init__(self) -> None:
        if self.walk_forward_train_size < 20:
            raise ValueError("walk_forward_train_size must be >= 20")
        if self.walk_forward_test_size < 5:
            raise ValueError("walk_forward_test_size must be >= 5")
        if self.walk_forward_step_size < 1:
            raise ValueError("walk_forward_step_size must be >= 1")
        if self.monte_carlo_simulations < 1:
            raise ValueError("monte_carlo_simulations must be >= 1")
        if self.noise_injection_std < 0:
            raise ValueError("noise_injection_std must be >= 0")
        if self.parameter_perturbation_pct < 0:
            raise ValueError("parameter_perturbation_pct must be >= 0")
        self.overall_weights = _normalize_weights(self.overall_weights)


@dataclass
class StrategyClusterConfig:
    similarity_threshold: float = 0.85
    min_cluster_size: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be in [0, 1]")
        if self.min_cluster_size < 1:
            raise ValueError("min_cluster_size must be >= 1")


@dataclass
class StrategyScoreConfig:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "sharpe": 0.25,
            "drawdown": 0.20,
            "robustness": 0.20,
            "consistency": 0.15,
            "trade_frequency": 0.10,
            "risk_adjusted": 0.10,
        }
    )

    def __post_init__(self) -> None:
        self.weights = _normalize_weights(self.weights)


@dataclass
class ResearchLabExportConfig:
    output_dir: str = "output/research_lab"
    write_csv: bool = True
    write_json: bool = True
    strategy_scores_csv: str = "strategy_scores.csv"
    strategy_clusters_csv: str = "strategy_clusters.csv"
    robustness_reports_json: str = "robustness_reports.json"
    parameter_surfaces_json: str = "parameter_surfaces.json"
    manifest_json: str = "strategy_discovery_manifest.json"

    def __post_init__(self) -> None:
        if not self.write_csv and not self.write_json:
            raise ValueError("At least one export format must be enabled")


@dataclass
class StrategyDiscoveryConfig:
    generator: ResearchLabGeneratorConfig = field(default_factory=ResearchLabGeneratorConfig)
    parameter_surface: ParameterSurfaceConfig = field(default_factory=ParameterSurfaceConfig)
    robustness: RobustnessAnalyzerConfig = field(default_factory=RobustnessAnalyzerConfig)
    cluster: StrategyClusterConfig = field(default_factory=StrategyClusterConfig)
    score: StrategyScoreConfig = field(default_factory=StrategyScoreConfig)
    export: ResearchLabExportConfig = field(default_factory=ResearchLabExportConfig)
    top_n: int = 20
    continue_on_error: bool = True

    def __post_init__(self) -> None:
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")
