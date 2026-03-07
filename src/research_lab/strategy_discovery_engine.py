"""
Main orchestration engine for Phase 7 strategy discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.research.strategy_generator import get_default_templates
from src.research_lab.config import StrategyDiscoveryConfig
from src.research_lab.exporter import ResearchLabExporter
from src.research_lab.models import (
    RobustnessReport,
    StrategyCandidate,
    StrategyDiscoveryResult,
    StrategyScore,
)
from src.research_lab.parameter_surface import ParameterSurfaceAnalyzer
from src.research_lab.robustness_analyzer import RobustnessAnalyzer
from src.research_lab.strategy_cluster import StrategyClusterAnalyzer
from src.research_lab.strategy_generator import StrategyGeneratorLab
from src.research_lab.strategy_score_engine import StrategyScoreEngine
from src.utils.config import BacktestConfig


class StrategyDiscoveryEngineError(Exception):
    """Raised when strategy discovery orchestration fails."""


@dataclass
class StrategyDiscoveryEngine:
    generator: Optional[StrategyGeneratorLab] = None
    parameter_surface_analyzer: Optional[ParameterSurfaceAnalyzer] = None
    robustness_analyzer: Optional[RobustnessAnalyzer] = None
    cluster_analyzer: Optional[StrategyClusterAnalyzer] = None
    score_engine: Optional[StrategyScoreEngine] = None
    exporter: Optional[ResearchLabExporter] = None

    def __post_init__(self) -> None:
        self.generator = self.generator or StrategyGeneratorLab()
        self.parameter_surface_analyzer = self.parameter_surface_analyzer or ParameterSurfaceAnalyzer()
        self.robustness_analyzer = self.robustness_analyzer or RobustnessAnalyzer()
        self.cluster_analyzer = self.cluster_analyzer or StrategyClusterAnalyzer()
        self.score_engine = self.score_engine or StrategyScoreEngine()
        self.exporter = self.exporter or ResearchLabExporter()

    def run(
        self,
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: StrategyDiscoveryConfig,
        export: bool = False,
    ) -> StrategyDiscoveryResult:
        warnings: list[str] = []
        errors: list[str] = []

        candidates = self.generator.generate(config.generator)
        evaluated = self._evaluate_candidates(candidates, base_config, data_handler, config, warnings)

        robustness_map = self._compute_robustness(
            evaluated=evaluated,
            base_config=base_config,
            data_handler=data_handler,
            config=config,
            warnings=warnings,
        )

        scores: list[StrategyScore] = []
        for candidate, metrics in evaluated:
            robust = robustness_map.get(candidate.key())
            score = self.score_engine.score(
                strategy_name=candidate.strategy_name,
                params=candidate.params,
                metrics=metrics,
                config=config.score,
                robustness_report=robust,
            )
            scores.append(score)
        ranked_scores = self.score_engine.rank(scores)

        clusters = self.cluster_analyzer.cluster(ranked_scores, config.cluster)
        surfaces = self._compute_parameter_surfaces(base_config, data_handler, config, warnings)

        result = StrategyDiscoveryResult(
            total_candidates=len(candidates),
            total_evaluated=len(evaluated),
            strategy_scores=ranked_scores[: config.top_n],
            strategy_clusters=clusters,
            robustness_reports=[robustness_map[k] for k in sorted(robustness_map)],
            parameter_surfaces=surfaces,
            warnings=warnings,
            errors=errors,
        )

        if export:
            outputs = self.exporter.export_all(result, config.export)
            result.exports = {k: str(v) for k, v in outputs.items()}

        return result

    def _evaluate_candidates(
        self,
        candidates: list[StrategyCandidate],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: StrategyDiscoveryConfig,
        warnings: list[str],
    ) -> list[tuple[StrategyCandidate, dict[str, Any]]]:
        out: list[tuple[StrategyCandidate, dict[str, Any]]] = []
        for candidate in candidates:
            try:
                metrics = self._run_backtest(candidate, base_config, data_handler)
                out.append((candidate, metrics))
            except Exception as exc:  # noqa: BLE001
                message = f"candidate failed {candidate.key()}: {exc}"
                if config.continue_on_error:
                    warnings.append(message)
                    continue
                raise StrategyDiscoveryEngineError(message) from exc
        return out

    def _compute_robustness(
        self,
        evaluated: list[tuple[StrategyCandidate, dict[str, Any]]],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: StrategyDiscoveryConfig,
        warnings: list[str],
    ) -> dict[str, RobustnessReport]:
        if not evaluated:
            return {}

        # Limit expensive robustness analysis to top candidates by sharpe.
        sorted_eval = sorted(
            evaluated,
            key=lambda row: float(row[1].get("sharpe_ratio") or 0.0),
            reverse=True,
        )
        cap = min(len(sorted_eval), max(config.top_n * 2, 1))
        pool = sorted_eval[:cap]

        reports: dict[str, RobustnessReport] = {}
        for candidate, _ in pool:
            try:
                report = self.robustness_analyzer.analyze(
                    strategy_class=candidate.strategy_class,
                    params=candidate.params,
                    base_config=base_config,
                    data_handler=data_handler,
                    config=config.robustness,
                )
                reports[candidate.key()] = report
            except Exception as exc:  # noqa: BLE001
                if config.continue_on_error:
                    warnings.append(f"robustness failed {candidate.key()}: {exc}")
                    continue
                raise
        return reports

    def _compute_parameter_surfaces(
        self,
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: StrategyDiscoveryConfig,
        warnings: list[str],
    ):
        templates = []
        if config.generator.use_default_templates:
            templates.extend(get_default_templates())
        for strategy_name, param_grid in config.generator.strategy_param_grids.items():
            # Reconstruct template via generator by invoking known map generation.
            # Use generated candidates and infer strategy class from first matching candidate.
            for candidate in self.generator.generate(config.generator):
                if candidate.strategy_name == strategy_name:
                    from src.research.strategy_generator import StrategyTemplate

                    templates.append(
                        StrategyTemplate(
                            strategy_class=candidate.strategy_class,
                            param_grid=param_grid,
                            description=f"custom_grid:{strategy_name}",
                            tags=["custom"],
                        )
                    )
                    break

        reports = []
        for template in templates:
            try:
                report = self.parameter_surface_analyzer.analyze(
                    strategy_class=template.strategy_class,
                    param_grid=template.param_grid,
                    base_config=base_config,
                    data_handler=data_handler,
                    config=config.parameter_surface,
                )
                reports.append(report)
            except Exception as exc:  # noqa: BLE001
                if config.continue_on_error:
                    warnings.append(f"parameter surface failed for {template.name}: {exc}")
                    continue
                raise
        return reports

    @staticmethod
    def _run_backtest(
        candidate: StrategyCandidate,
        base_config: BacktestConfig,
        data_handler: DataHandler,
    ) -> dict[str, Any]:
        cfg = base_config.model_copy(deep=True)
        strategy_params = dict(cfg.strategy_params or {})
        strategy_params.update(candidate.params)
        cfg.strategy_params = strategy_params

        strategy = candidate.strategy_class()
        engine = BacktestEngine(cfg, strategy)
        engine.run(data_handler)
        return engine.get_results().get("metrics", {})
