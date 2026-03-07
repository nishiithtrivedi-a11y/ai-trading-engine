"""
Strategy clustering based on metric similarity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.research_lab.config import StrategyClusterConfig
from src.research_lab.models import StrategyCluster, StrategyScore


class StrategyClusterAnalyzerError(Exception):
    """Raised when strategy clustering fails."""


@dataclass
class StrategyClusterAnalyzer:
    def cluster(
        self,
        strategy_scores: list[StrategyScore],
        config: StrategyClusterConfig,
    ) -> list[StrategyCluster]:
        if not strategy_scores:
            return []

        clusters: list[list[StrategyScore]] = []
        for score in sorted(strategy_scores, key=lambda s: float(s.total_score), reverse=True):
            assigned = False
            for cluster_scores in clusters:
                sim = self._similarity(score, self._centroid_like(cluster_scores))
                if sim >= config.similarity_threshold:
                    cluster_scores.append(score)
                    assigned = True
                    break
            if not assigned:
                clusters.append([score])

        out: list[StrategyCluster] = []
        cluster_id = 1
        for cluster_scores in clusters:
            if len(cluster_scores) < config.min_cluster_size:
                continue
            centroid = self._centroid(cluster_scores)
            out.append(
                StrategyCluster(
                    cluster_id=cluster_id,
                    strategy_keys=[s.strategy_key for s in cluster_scores],
                    centroid_metrics=centroid,
                    metadata={"size": len(cluster_scores)},
                )
            )
            cluster_id += 1

        return out

    def _similarity(self, score: StrategyScore, centroid: dict[str, float]) -> float:
        a = self._vector_from_score(score)
        b = self._vector_from_dict(centroid)
        return self._cosine_similarity(a, b)

    @staticmethod
    def _vector_from_score(score: StrategyScore) -> list[float]:
        return [
            float(score.sharpe_component),
            float(score.drawdown_component),
            float(score.robustness_component),
            float(score.consistency_component),
            float(score.trade_frequency_component),
            float(score.risk_adjusted_component),
        ]

    @staticmethod
    def _vector_from_dict(values: dict[str, float]) -> list[float]:
        return [
            float(values.get("sharpe_component", 0.0)),
            float(values.get("drawdown_component", 0.0)),
            float(values.get("robustness_component", 0.0)),
            float(values.get("consistency_component", 0.0)),
            float(values.get("trade_frequency_component", 0.0)),
            float(values.get("risk_adjusted_component", 0.0)),
        ]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _centroid_like(self, scores: list[StrategyScore]) -> dict[str, float]:
        return self._centroid(scores)

    @staticmethod
    def _centroid(scores: list[StrategyScore]) -> dict[str, float]:
        if not scores:
            return {}
        n = len(scores)
        return {
            "sharpe_component": sum(s.sharpe_component for s in scores) / n,
            "drawdown_component": sum(s.drawdown_component for s in scores) / n,
            "robustness_component": sum(s.robustness_component for s in scores) / n,
            "consistency_component": sum(s.consistency_component for s in scores) / n,
            "trade_frequency_component": sum(s.trade_frequency_component for s in scores) / n,
            "risk_adjusted_component": sum(s.risk_adjusted_component for s in scores) / n,
            "total_score": sum(s.total_score for s in scores) / n,
        }
