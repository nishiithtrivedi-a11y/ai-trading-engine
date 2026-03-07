"""
Strategy scoring engine for Phase 7 discovery results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.research_lab.config import StrategyScoreConfig
from src.research_lab.models import RobustnessReport, StrategyScore


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


@dataclass
class StrategyScoreEngine:
    def score(
        self,
        strategy_name: str,
        params: dict,
        metrics: dict,
        config: StrategyScoreConfig,
        robustness_report: Optional[RobustnessReport] = None,
    ) -> StrategyScore:
        sharpe = float(metrics.get("sharpe_ratio") or 0.0)
        max_drawdown = float(metrics.get("max_drawdown_pct") or 0.0)
        win_rate = float(metrics.get("win_rate") or 0.0)
        profit_factor = float(metrics.get("profit_factor") or 0.0)
        num_trades = float(metrics.get("num_trades") or 0.0)
        sortino = float(metrics.get("sortino_ratio") or 0.0)
        calmar = float(metrics.get("calmar_ratio") or 0.0)

        sharpe_component = _clamp(((sharpe + 1.0) / 3.0) * 100.0)

        dd_pct = max_drawdown * 100.0 if max_drawdown <= 1.0 else max_drawdown
        drawdown_component = _clamp(100.0 - dd_pct * 1.5)

        robustness_component = (
            float(robustness_report.overall_robustness_score) if robustness_report else 50.0
        )
        consistency_component = _clamp((win_rate * 70.0) + min(30.0, profit_factor * 10.0))
        trade_frequency_component = _clamp((num_trades / 200.0) * 100.0)
        risk_adjusted_component = _clamp(((sortino + calmar + sharpe) / 3.0 + 1.0) / 3.0 * 100.0)

        components = {
            "sharpe": sharpe_component,
            "drawdown": drawdown_component,
            "robustness": robustness_component,
            "consistency": consistency_component,
            "trade_frequency": trade_frequency_component,
            "risk_adjusted": risk_adjusted_component,
        }

        weights = config.weights
        total = 0.0
        wsum = 0.0
        for key, value in components.items():
            w = float(weights.get(key, 0.0))
            if w <= 0:
                continue
            total += w * value
            wsum += w
        total_score = _clamp(total / wsum) if wsum > 0 else 0.0

        strategy_key = self._strategy_key(strategy_name, params)
        return StrategyScore(
            strategy_name=strategy_name,
            params=dict(params),
            strategy_key=strategy_key,
            sharpe_component=sharpe_component,
            drawdown_component=drawdown_component,
            robustness_component=robustness_component,
            consistency_component=consistency_component,
            trade_frequency_component=trade_frequency_component,
            risk_adjusted_component=risk_adjusted_component,
            total_score=total_score,
            metadata={"raw_metrics": dict(metrics)},
        )

    @staticmethod
    def rank(scores: list[StrategyScore]) -> list[StrategyScore]:
        ranked = sorted(
            scores,
            key=lambda s: (
                -float(s.total_score),
                -float(s.robustness_component),
                -float(s.sharpe_component),
                s.strategy_name,
                tuple(sorted(s.params.items())),
            ),
        )
        for idx, score in enumerate(ranked, start=1):
            score.rank = idx
        return ranked

    @staticmethod
    def _strategy_key(strategy_name: str, params: dict) -> str:
        parts = [f"{k}={params[k]}" for k in sorted(params)]
        return f"{strategy_name}|" + "|".join(parts)
