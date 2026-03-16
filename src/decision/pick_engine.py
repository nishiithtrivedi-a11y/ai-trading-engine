"""
Main Phase 5 pick/decision orchestration engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.decision.config import DecisionConfig
from src.decision.conviction_engine import ConvictionEngine
from src.decision.models import (
    DecisionHorizon,
    PickRunResult,
    RankedPick,
    RejectedOpportunity,
    RejectionReason,
)
from src.decision.portfolio_candidate_selector import PortfolioCandidateSelector
from src.decision.ranking_engine import RankingEngine
from src.decision.regime_filter import RegimeFilter
from src.decision.trade_plan_builder import TradePlanBuilder, TradePlanBuilderError
from src.monitoring.models import MonitoringRunResult, RelativeStrengthSnapshot
from src.scanners.models import Opportunity, OpportunityClass, ScanResult
from src.utils.logger import setup_logger

logger = setup_logger("pick_engine")


class PickEngineError(Exception):
    """Raised when pick engine orchestration fails."""


@dataclass
class PickEngine:
    decision_config: DecisionConfig = field(default_factory=DecisionConfig)
    regime_filter: Optional[RegimeFilter] = None
    conviction_engine: Optional[ConvictionEngine] = None
    trade_plan_builder: Optional[TradePlanBuilder] = None
    ranking_engine: Optional[RankingEngine] = None
    selector: Optional[PortfolioCandidateSelector] = None

    def __post_init__(self) -> None:
        self.regime_filter = self.regime_filter or RegimeFilter()
        self.conviction_engine = self.conviction_engine or ConvictionEngine()
        self.trade_plan_builder = self.trade_plan_builder or TradePlanBuilder()
        self.ranking_engine = self.ranking_engine or RankingEngine()
        self.selector = self.selector or PortfolioCandidateSelector()

    def run(
        self,
        scan_result: Optional[ScanResult] = None,
        monitoring_result: Optional[MonitoringRunResult] = None,
        decision_config: Optional[DecisionConfig] = None,
    ) -> PickRunResult:
        cfg = decision_config or self.decision_config
        warnings: list[str] = []
        errors: list[str] = []
        rejected: list[RejectedOpportunity] = []

        scan = self._resolve_scan_result(scan_result, monitoring_result)
        logger.info(
            "Decision run started: opportunities=%s include_rejections=%s",
            len(scan.opportunities),
            cfg.include_rejections,
        )
        regime_assessment = monitoring_result.regime_assessment if monitoring_result else None
        rs_map = self._relative_strength_map(monitoring_result)

        candidates: list[RankedPick] = []
        for opp in sorted(scan.opportunities, key=lambda o: float(o.score), reverse=True):
            try:
                plan = self.trade_plan_builder.build(opp)
            except TradePlanBuilderError as exc:
                logger.warning(
                    "Trade plan build failed for %s/%s/%s: %s",
                    opp.symbol,
                    opp.timeframe,
                    opp.strategy_name,
                    exc,
                )
                rejected.append(
                    self._reject(
                        opportunity=opp,
                        horizon=self._horizon_from_opportunity(opp),
                        reason=RejectionReason.OTHER,
                        note=f"trade_plan_error: {exc}",
                    )
                )
                continue

            min_score = cfg.thresholds.min_score(plan.horizon)
            if float(opp.score) < min_score:
                logger.debug(
                    "Rejected %s/%s/%s for score threshold: %.2f < %.2f",
                    opp.symbol,
                    opp.timeframe,
                    opp.strategy_name,
                    float(opp.score),
                    min_score,
                )
                rejected.append(
                    self._reject(
                        opportunity=opp,
                        horizon=plan.horizon,
                        reason=RejectionReason.BELOW_MIN_SCORE,
                        note=f"score {opp.score:.2f} < min_score {min_score:.2f}",
                    )
                )
                continue

            min_rr = cfg.thresholds.min_rr(plan.horizon)
            if float(plan.risk_reward) < min_rr:
                logger.debug(
                    "Rejected %s/%s/%s for RR threshold: %.2f < %.2f",
                    opp.symbol,
                    opp.timeframe,
                    opp.strategy_name,
                    float(plan.risk_reward),
                    min_rr,
                )
                rejected.append(
                    self._reject(
                        opportunity=opp,
                        horizon=plan.horizon,
                        reason=RejectionReason.BELOW_MIN_RR,
                        note=f"rr {plan.risk_reward:.2f} < min_rr {min_rr:.2f}",
                    )
                )
                continue

            regime_result = self.regime_filter.evaluate(opp, regime_assessment, cfg)
            if not regime_result.allowed:
                logger.debug(
                    "Regime blocked %s/%s/%s: %s",
                    opp.symbol,
                    opp.timeframe,
                    opp.strategy_name,
                    regime_result.reasons,
                )
                rejected.append(
                    RejectedOpportunity(
                        symbol=opp.symbol,
                        timeframe=opp.timeframe,
                        strategy_name=opp.strategy_name,
                        horizon=plan.horizon,
                        scanner_score=float(opp.score),
                        rejection_reasons=(
                            regime_result.rejection_reasons
                            if regime_result.rejection_reasons
                            else [RejectionReason.REGIME_BLOCKED]
                        ),
                        notes=list(regime_result.reasons),
                        metadata={"regime_filter": regime_result.to_dict()},
                    )
                )
                continue

            rs_row = rs_map.get(opp.symbol)
            breakdown = self.conviction_engine.score(
                opportunity=opp,
                trade_plan=plan,
                config=cfg,
                regime_result=regime_result,
                relative_strength=rs_row,
            )

            candidates.append(
                RankedPick(
                    trade_plan=plan,
                    conviction_score=breakdown.final_score,
                    conviction_breakdown=breakdown,
                    scanner_score=float(opp.score),
                    regime_compatibility=breakdown.regime_compatibility,
                    relative_strength_score=(float(rs_row.score) if rs_row is not None else None),
                    reasons=list(regime_result.reasons) + list(opp.reasons),
                    metadata={
                        "scanner_rank": opp.rank,
                        "regime_filter": regime_result.to_dict(),
                        "scanner_metadata": dict(opp.metadata),
                    },
                )
            )

        ranked = self.ranking_engine.rank(candidates)
        selected, selector_rejected = self.selector.select(ranked, cfg)
        rejected.extend(selector_rejected)

        selected_ranked = self.ranking_engine.rank(selected)
        grouped = self.ranking_engine.split_by_horizon(selected_ranked)

        logger.info(
            "Decision run complete: candidates=%s selected=%s rejected=%s",
            len(candidates),
            len(selected_ranked),
            len(rejected),
        )

        return PickRunResult(
            selected_picks=selected_ranked,
            top_intraday=grouped.get(DecisionHorizon.INTRADAY, []),
            top_swing=grouped.get(DecisionHorizon.SWING, []),
            top_positional=grouped.get(DecisionHorizon.POSITIONAL, []),
            rejected_opportunities=rejected if cfg.include_rejections else [],
            warnings=warnings,
            errors=errors,
            metadata={
                "input_opportunities": len(scan.opportunities),
                "candidate_count": len(candidates),
                "selected_count": len(selected_ranked),
            },
        )

    @staticmethod
    def _resolve_scan_result(
        scan_result: Optional[ScanResult],
        monitoring_result: Optional[MonitoringRunResult],
    ) -> ScanResult:
        if scan_result is not None:
            return scan_result
        if monitoring_result is not None and monitoring_result.scan_result is not None:
            return monitoring_result.scan_result
        raise PickEngineError("Either scan_result or monitoring_result.scan_result is required")

    @staticmethod
    def _relative_strength_map(
        monitoring_result: Optional[MonitoringRunResult],
    ) -> dict[str, RelativeStrengthSnapshot]:
        if monitoring_result is None:
            return {}
        return {row.symbol: row for row in monitoring_result.relative_strength}

    @staticmethod
    def _reject(
        opportunity: Opportunity,
        horizon: DecisionHorizon,
        reason: RejectionReason,
        note: str,
    ) -> RejectedOpportunity:
        return RejectedOpportunity(
            symbol=opportunity.symbol,
            timeframe=opportunity.timeframe,
            strategy_name=opportunity.strategy_name,
            horizon=horizon,
            scanner_score=float(opportunity.score),
            rejection_reasons=[reason],
            notes=[note],
            metadata={"scanner_metadata": dict(opportunity.metadata)},
        )

    @staticmethod
    def _horizon_from_opportunity(opportunity: Opportunity) -> DecisionHorizon:
        if opportunity.classification == OpportunityClass.INTRADAY:
            return DecisionHorizon.INTRADAY
        if opportunity.classification == OpportunityClass.SWING:
            return DecisionHorizon.SWING
        return DecisionHorizon.POSITIONAL
