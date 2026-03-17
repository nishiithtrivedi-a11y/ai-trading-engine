"""
Deterministic ranking engine for decision candidates.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.decision.models import DecisionHorizon, RankedPick
from src.utils.logger import setup_logger

logger = setup_logger("ranking_engine")


@dataclass
class RankingEngine:
    def rank(self, picks: list[RankedPick]) -> list[RankedPick]:
        logger.debug("Ranking %d picks", len(picks))
        ranked = sorted(picks, key=self._sort_key)

        horizon_counters: dict[DecisionHorizon, int] = {
            DecisionHorizon.INTRADAY: 0,
            DecisionHorizon.SWING: 0,
            DecisionHorizon.POSITIONAL: 0,
        }

        for idx, pick in enumerate(ranked, start=1):
            pick.priority_rank = idx
            horizon_counters[pick.horizon] += 1
            pick.horizon_rank = horizon_counters[pick.horizon]

        return ranked

    @staticmethod
    def split_by_horizon(picks: list[RankedPick]) -> dict[DecisionHorizon, list[RankedPick]]:
        grouped = {
            DecisionHorizon.INTRADAY: [],
            DecisionHorizon.SWING: [],
            DecisionHorizon.POSITIONAL: [],
        }
        for pick in picks:
            grouped[pick.horizon].append(pick)
        return grouped

    @staticmethod
    def _sort_key(pick: RankedPick):
        rr = float(pick.trade_plan.risk_reward)
        rs = float(pick.relative_strength_score) if pick.relative_strength_score is not None else -1e9
        return (
            -float(pick.conviction_score),
            -rr,
            -rs,
            -float(pick.scanner_score),
            pick.trade_plan.symbol,
            pick.trade_plan.timeframe,
            pick.trade_plan.strategy_name,
        )
