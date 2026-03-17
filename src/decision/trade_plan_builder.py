"""
Builds explicit trade plans from scanner opportunities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.decision.models import DecisionHorizon, TradePlan
from src.scanners.models import Opportunity, OpportunityClass
from src.utils.logger import setup_logger

logger = setup_logger("trade_plan_builder")


class TradePlanBuilderError(Exception):
    """Raised when a trade plan cannot be built."""


def _horizon_from_classification(classification: OpportunityClass) -> DecisionHorizon:
    if classification == OpportunityClass.INTRADAY:
        return DecisionHorizon.INTRADAY
    if classification == OpportunityClass.SWING:
        return DecisionHorizon.SWING
    return DecisionHorizon.POSITIONAL


@dataclass
class TradePlanBuilder:
    def build(
        self,
        opportunity: Opportunity,
        additional_notes: Optional[list[str]] = None,
    ) -> TradePlan:
        entry = float(opportunity.entry_price)
        stop = float(opportunity.stop_loss)
        target = float(opportunity.target_price)

        risk = entry - stop
        reward = target - entry
        if risk <= 0:
            logger.warning(
                "Rejecting %s: stop_loss %.2f >= entry_price %.2f",
                opportunity.symbol, stop, entry,
            )
            raise TradePlanBuilderError("Invalid long setup: stop must be below entry")
        if reward <= 0:
            logger.warning(
                "Rejecting %s: target_price %.2f <= entry_price %.2f",
                opportunity.symbol, target, entry,
            )
            raise TradePlanBuilderError("Invalid long setup: target must be above entry")

        rr = reward / risk
        logger.debug(
            "Building trade plan: %s entry=%.2f stop=%.2f target=%.2f rr=%.2f",
            opportunity.symbol, entry, stop, target, rr,
        )
        horizon = _horizon_from_classification(opportunity.classification)
        hold_policy = self._default_hold_policy(horizon)

        notes = list(opportunity.reasons)
        notes.extend(additional_notes or [])

        metadata = {
            "scanner_score": float(opportunity.score),
            "score_signal": opportunity.score_signal,
            "score_rr": opportunity.score_rr,
            "score_trend": opportunity.score_trend,
            "score_liquidity": opportunity.score_liquidity,
            "score_freshness": opportunity.score_freshness,
        }
        metadata.update(opportunity.metadata or {})

        setup_tags = [opportunity.strategy_name, opportunity.timeframe, horizon.value]

        return TradePlan(
            symbol=opportunity.symbol,
            timeframe=opportunity.timeframe,
            strategy_name=opportunity.strategy_name,
            entry_price=entry,
            stop_loss=stop,
            target_price=target,
            risk_reward=rr,
            horizon=horizon,
            setup_tags=setup_tags,
            max_hold_policy=hold_policy,
            notes=notes,
            metadata=metadata,
        )

    @staticmethod
    def _default_hold_policy(horizon: DecisionHorizon) -> str:
        if horizon == DecisionHorizon.INTRADAY:
            return "same_day_exit"
        if horizon == DecisionHorizon.SWING:
            return "multi_day_5_to_20_bars_placeholder"
        return "multi_week_20_plus_bars_placeholder"
