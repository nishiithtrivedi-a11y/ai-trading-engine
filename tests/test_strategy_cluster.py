from __future__ import annotations

from src.research_lab.config import StrategyClusterConfig
from src.research_lab.models import StrategyScore
from src.research_lab.strategy_cluster import StrategyClusterAnalyzer


def _score(name: str, total: float, sharpe: float, drawdown: float) -> StrategyScore:
    return StrategyScore(
        strategy_name=name,
        params={"p": 1},
        strategy_key=f"{name}|p=1",
        sharpe_component=sharpe,
        drawdown_component=drawdown,
        robustness_component=70.0,
        consistency_component=65.0,
        trade_frequency_component=60.0,
        risk_adjusted_component=68.0,
        total_score=total,
    )


def test_strategy_clustering_basic() -> None:
    scores = [
        _score("A", 85, 80, 75),
        _score("B", 84, 79, 74),
        _score("C", 60, 45, 40),
    ]
    clusters = StrategyClusterAnalyzer().cluster(
        scores,
        StrategyClusterConfig(similarity_threshold=0.95, min_cluster_size=1),
    )

    assert len(clusters) >= 1
    total_members = sum(len(c.strategy_keys) for c in clusters)
    assert total_members == len(scores)
