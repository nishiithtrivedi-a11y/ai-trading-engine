"""
Regime-aware filtering and penalty logic for decision candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.decision.config import DecisionConfig, RegimePolicyConfig
from src.decision.models import DecisionHorizon, RegimeFilterResult, RejectionReason
from src.monitoring.models import RegimeAssessment, RegimeState
from src.scanners.models import Opportunity, OpportunityClass
from src.utils.logger import setup_logger

logger = setup_logger("decision_regime_filter")


class RegimeFilterError(Exception):
    """Raised when regime filter evaluation fails."""


def _horizon_from_classification(classification: OpportunityClass) -> DecisionHorizon:
    if classification == OpportunityClass.INTRADAY:
        return DecisionHorizon.INTRADAY
    if classification == OpportunityClass.SWING:
        return DecisionHorizon.SWING
    return DecisionHorizon.POSITIONAL


@dataclass
class RegimeFilter:
    def evaluate(
        self,
        opportunity: Opportunity,
        regime_assessment: Optional[RegimeAssessment],
        config: DecisionConfig | RegimePolicyConfig,
    ) -> RegimeFilterResult:
        policy = config.regime_policy if isinstance(config, DecisionConfig) else config
        horizon = _horizon_from_classification(opportunity.classification)

        if regime_assessment is None:
            logger.info(
                "Regime context unavailable for %s/%s; applying neutral decision.",
                opportunity.symbol,
                opportunity.strategy_name,
            )
            return RegimeFilterResult(
                allowed=True,
                penalty=0.0,
                reasons=["regime_unavailable_neutral"],
                metadata={"horizon": horizon.value, "regime": None},
            )

        regime = regime_assessment.regime
        allowed_regimes = policy.allowed_for(horizon)
        reasons: list[str] = []
        rejection_reasons: list[RejectionReason] = []
        penalty = 0.0

        if regime not in allowed_regimes:
            penalty += float(policy.mismatch_penalty)
            reasons.append(
                f"regime {regime.value} not in allowed set for {horizon.value}"
            )
            if policy.hard_block_on_mismatch:
                rejection_reasons.append(RejectionReason.REGIME_BLOCKED)
                logger.info(
                    "Regime blocked %s/%s (%s): %s",
                    opportunity.symbol,
                    opportunity.strategy_name,
                    horizon.value,
                    reasons,
                )
                return RegimeFilterResult(
                    allowed=False,
                    penalty=min(100.0, penalty),
                    reasons=reasons,
                    rejection_reasons=rejection_reasons,
                    metadata={"horizon": horizon.value, "regime": regime.value},
                )
            rejection_reasons.append(RejectionReason.REGIME_PENALIZED_OUT)

        if regime == RegimeState.HIGH_VOLATILITY:
            penalty += float(policy.high_volatility_extra_penalty)
            reasons.append("high_volatility_penalty_applied")

        if regime == RegimeState.BEARISH:
            penalty += float(policy.bearish_extra_penalty)
            reasons.append("bearish_regime_penalty_applied")

        logger.debug(
            "Regime filter decision for %s/%s: allowed=%s penalty=%.2f reasons=%s",
            opportunity.symbol,
            opportunity.strategy_name,
            True,
            min(100.0, penalty),
            reasons or ["regime_aligned"],
        )

        return RegimeFilterResult(
            allowed=True,
            penalty=min(100.0, penalty),
            reasons=reasons or ["regime_aligned"],
            rejection_reasons=rejection_reasons,
            metadata={"horizon": horizon.value, "regime": regime.value},
        )
