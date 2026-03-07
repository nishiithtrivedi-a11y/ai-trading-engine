from __future__ import annotations

from src.research_lab.config import StrategyScoreConfig
from src.research_lab.models import RobustnessReport
from src.research_lab.strategy_score_engine import StrategyScoreEngine


def test_strategy_score_engine_higher_quality_scores_better() -> None:
    engine = StrategyScoreEngine()
    cfg = StrategyScoreConfig()

    weak = engine.score(
        strategy_name="S1",
        params={"a": 1},
        metrics={
            "sharpe_ratio": 0.5,
            "max_drawdown_pct": 0.25,
            "win_rate": 0.45,
            "profit_factor": 1.1,
            "num_trades": 30,
            "sortino_ratio": 0.6,
            "calmar_ratio": 0.4,
        },
        config=cfg,
        robustness_report=RobustnessReport(
            strategy_name="S1",
            params={"a": 1},
            walk_forward_score=50,
            monte_carlo_score=50,
            noise_resilience_score=50,
            parameter_stability_score=50,
            overall_robustness_score=50,
        ),
    )
    strong = engine.score(
        strategy_name="S2",
        params={"a": 2},
        metrics={
            "sharpe_ratio": 1.8,
            "max_drawdown_pct": 0.08,
            "win_rate": 0.62,
            "profit_factor": 1.8,
            "num_trades": 80,
            "sortino_ratio": 2.0,
            "calmar_ratio": 1.2,
        },
        config=cfg,
        robustness_report=RobustnessReport(
            strategy_name="S2",
            params={"a": 2},
            walk_forward_score=85,
            monte_carlo_score=80,
            noise_resilience_score=78,
            parameter_stability_score=82,
            overall_robustness_score=82,
        ),
    )

    assert strong.total_score > weak.total_score


def test_strategy_score_ranking() -> None:
    engine = StrategyScoreEngine()
    cfg = StrategyScoreConfig(weights={"sharpe": 1.0})
    s1 = engine.score("S1", {"x": 1}, {"sharpe_ratio": 0.5}, cfg)
    s2 = engine.score("S2", {"x": 2}, {"sharpe_ratio": 1.5}, cfg)

    ranked = engine.rank([s1, s2])
    assert ranked[0].strategy_name == "S2"
    assert ranked[0].rank == 1
