"""
Conviction scoring engine for decision candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.decision.config import DecisionConfig
from src.decision.models import ConvictionBreakdown, RegimeFilterResult, TradePlan
from src.monitoring.models import RelativeStrengthSnapshot
from src.scanners.models import Opportunity


class ConvictionEngineError(Exception):
    """Raised when conviction scoring fails."""


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


@dataclass
class ConvictionEngine:
    rr_cap: float = 3.0

    def score(
        self,
        opportunity: Opportunity,
        trade_plan: TradePlan,
        config: DecisionConfig,
        regime_result: Optional[RegimeFilterResult] = None,
        relative_strength: Optional[RelativeStrengthSnapshot] = None,
    ) -> ConvictionBreakdown:
        if trade_plan.risk_reward <= 0:
            raise ConvictionEngineError("trade_plan.risk_reward must be > 0")

        scanner_score = _clamp(float(opportunity.score))

        rr_score = _clamp((float(trade_plan.risk_reward) / self.rr_cap) * 100.0)

        setup_quality = rr_score
        if opportunity.score_rr is not None:
            setup_quality = _clamp(float(opportunity.score_rr) * 100.0)

        regime_compatibility = 100.0
        regime_penalty = 0.0
        regime_notes: list[str] = []
        if regime_result is not None:
            regime_penalty = _clamp(regime_result.penalty)
            regime_compatibility = _clamp(100.0 - regime_penalty)
            regime_notes.extend(regime_result.reasons)
        else:
            regime_compatibility = 60.0
            regime_notes.append("regime_context_missing_neutral")

        rs_score = self._relative_strength_component(relative_strength)

        liquidity = (
            _clamp(float(opportunity.score_liquidity) * 100.0)
            if opportunity.score_liquidity is not None
            else 50.0
        )
        freshness = (
            _clamp(float(opportunity.score_freshness) * 100.0)
            if opportunity.score_freshness is not None
            else 50.0
        )

        components = {
            "scanner_score": scanner_score,
            "setup_quality": setup_quality,
            "risk_reward": rr_score,
            "regime_compatibility": regime_compatibility,
            "relative_strength": rs_score,
            "liquidity": liquidity,
            "freshness": freshness,
        }

        weights = config.conviction_weights.weights
        weighted = 0.0
        total = 0.0
        for key, value in components.items():
            w = float(weights.get(key, 0.0))
            if w <= 0:
                continue
            weighted += w * value
            total += w

        if total <= 0:
            raise ConvictionEngineError("conviction weights produced zero effective total")

        final_score = _clamp(weighted / total)

        notes = []
        notes.extend(regime_notes)
        if relative_strength is None:
            notes.append("relative_strength_missing_neutral")

        return ConvictionBreakdown(
            scanner_score=scanner_score,
            setup_quality=setup_quality,
            risk_reward=rr_score,
            regime_compatibility=regime_compatibility,
            relative_strength=rs_score,
            liquidity=liquidity,
            freshness=freshness,
            final_score=final_score,
            notes=notes,
            metadata={
                "weights": dict(weights),
                "regime_penalty": regime_penalty,
                "raw_relative_strength": (
                    float(relative_strength.score) if relative_strength is not None else None
                ),
            },
        )

    @staticmethod
    def _relative_strength_component(
        relative_strength: Optional[RelativeStrengthSnapshot],
    ) -> float:
        if relative_strength is None:
            return 50.0

        raw = float(relative_strength.score)
        # Simple explicit mapping: 0 return -> 50 score, +/-0.25 -> approx 0/100 clipped.
        mapped = 50.0 + raw * 200.0
        return _clamp(mapped)
