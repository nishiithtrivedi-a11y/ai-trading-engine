"""
Snapshot builder for "top picks now" outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.monitoring.config import SnapshotConfig
from src.monitoring.models import (
    MarketSnapshot,
    RegimeAssessment,
    RelativeStrengthSnapshot,
    TopPick,
    Watchlist,
)
from src.scanners.models import Opportunity, ScanResult


class SnapshotEngineError(Exception):
    """Raised when snapshot generation fails."""


@dataclass
class SnapshotEngine:
    def build_snapshot(
        self,
        scan_result: ScanResult,
        config: SnapshotConfig,
        regime_assessment: Optional[RegimeAssessment] = None,
        relative_strength: Optional[list[RelativeStrengthSnapshot]] = None,
        watchlists: Optional[dict[str, Watchlist]] = None,
    ) -> MarketSnapshot:
        if scan_result is None:
            raise SnapshotEngineError("scan_result is required")

        candidates = [o for o in scan_result.opportunities if float(o.score) >= config.min_score]
        candidates = sorted(candidates, key=lambda o: float(o.score), reverse=True)[: config.top_n]

        rs_map = {
            row.symbol: row
            for row in (relative_strength or [])
        }
        watchlist_tags = self._build_watchlist_tags_map(watchlists or {})

        picks: list[TopPick] = []
        for opp in candidates:
            picks.append(
                self._to_top_pick(
                    opportunity=opp,
                    regime_assessment=regime_assessment if config.include_regime_context else None,
                    rs_snapshot=rs_map.get(opp.symbol) if config.include_relative_strength_context else None,
                    watchlist_symbol_tags=watchlist_tags.get(opp.symbol, [])
                    if config.include_watchlist_context
                    else [],
                )
            )

        return MarketSnapshot(
            top_picks=picks,
            regime_assessment=regime_assessment if config.include_regime_context else None,
            metadata={
                "total_candidates": len(scan_result.opportunities),
                "selected_picks": len(picks),
                "min_score": config.min_score,
                "top_n": config.top_n,
            },
        )

    @staticmethod
    def _build_watchlist_tags_map(watchlists: dict[str, Watchlist]) -> dict[str, list[str]]:
        symbol_tags: dict[str, list[str]] = {}
        for watchlist in watchlists.values():
            for item in watchlist.items:
                merged_tags = list(item.tags)
                if watchlist.name not in merged_tags:
                    merged_tags.append(watchlist.name)
                symbol_tags.setdefault(item.symbol, [])
                for tag in merged_tags:
                    if tag not in symbol_tags[item.symbol]:
                        symbol_tags[item.symbol].append(tag)
        return symbol_tags

    @staticmethod
    def _to_top_pick(
        opportunity: Opportunity,
        regime_assessment: Optional[RegimeAssessment],
        rs_snapshot: Optional[RelativeStrengthSnapshot],
        watchlist_symbol_tags: list[str],
    ) -> TopPick:
        regime_context = regime_assessment.regime.value if regime_assessment else None
        rs_score = float(rs_snapshot.score) if rs_snapshot else None

        return TopPick(
            symbol=opportunity.symbol,
            timeframe=opportunity.timeframe,
            strategy_name=opportunity.strategy_name,
            timestamp=opportunity.timestamp,
            entry_price=opportunity.entry_price,
            stop_loss=opportunity.stop_loss,
            target_price=opportunity.target_price,
            score=float(opportunity.score),
            horizon=opportunity.classification.value,
            regime_context=regime_context,
            relative_strength_score=rs_score,
            watchlist_tags=watchlist_symbol_tags,
            reasons=list(opportunity.reasons),
            metadata={
                "rank": opportunity.rank,
                "signal": opportunity.signal,
                "score_signal": opportunity.score_signal,
                "score_rr": opportunity.score_rr,
                "score_trend": opportunity.score_trend,
                "score_liquidity": opportunity.score_liquidity,
                "score_freshness": opportunity.score_freshness,
            },
        )
