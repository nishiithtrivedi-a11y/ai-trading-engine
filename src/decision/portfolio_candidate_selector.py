"""
Portfolio-style curation of ranked decision candidates.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.decision.config import DecisionConfig
from src.decision.models import RankedPick, RejectedOpportunity, RejectionReason


class PortfolioCandidateSelectorError(Exception):
    """Raised when candidate selection fails."""


@dataclass
class PortfolioCandidateSelector:
    def select(
        self,
        ranked_candidates: list[RankedPick],
        config: DecisionConfig,
    ) -> tuple[list[RankedPick], list[RejectedOpportunity]]:
        selected: list[RankedPick] = []
        rejected: list[RejectedOpportunity] = []

        horizon_counts: dict[str, int] = {}
        sector_counts: dict[str, int] = {}
        symbol_counts: dict[str, int] = {}
        setup_keys: set[tuple[str, str, str]] = set()
        cluster_counts: dict[str, int] = {}

        for pick in ranked_candidates:
            horizon_key = pick.horizon.value
            horizon_cap = config.thresholds.max_picks(pick.horizon)
            current_horizon_count = horizon_counts.get(horizon_key, 0)

            if current_horizon_count >= horizon_cap:
                rejected.append(
                    self._to_rejected(
                        pick,
                        RejectionReason.HORIZON_CAP_REACHED,
                        f"{horizon_key} cap reached ({horizon_cap})",
                    )
                )
                continue

            sector = pick.sector
            if sector:
                sector_count = sector_counts.get(sector, 0)
                if sector_count >= config.thresholds.max_picks_per_sector:
                    rejected.append(
                        self._to_rejected(
                            pick,
                            RejectionReason.SECTOR_CAP_REACHED,
                            (
                                f"sector cap reached for {sector} "
                                f"({config.thresholds.max_picks_per_sector})"
                            ),
                        )
                    )
                    continue

            symbol = pick.symbol
            if config.selection_policy.enforce_unique_symbol and symbol_counts.get(symbol, 0) > 0:
                rejected.append(
                    self._to_rejected(
                        pick,
                        RejectionReason.DUPLICATE_SYMBOL,
                        f"symbol {symbol} already selected",
                    )
                )
                continue

            setup_key = (
                pick.trade_plan.symbol,
                pick.trade_plan.timeframe,
                pick.trade_plan.strategy_name,
            )
            if (
                config.selection_policy.enforce_unique_symbol_timeframe_strategy
                and setup_key in setup_keys
            ):
                rejected.append(
                    self._to_rejected(
                        pick,
                        RejectionReason.DUPLICATE_SETUP,
                        f"duplicate setup {setup_key}",
                    )
                )
                continue

            cluster = str(pick.trade_plan.metadata.get("cluster", "")).strip()
            if cluster:
                cluster_count = cluster_counts.get(cluster, 0)
                if cluster_count >= config.thresholds.max_correlated_picks:
                    rejected.append(
                        self._to_rejected(
                            pick,
                            RejectionReason.OTHER,
                            (
                                f"cluster cap reached for {cluster} "
                                f"({config.thresholds.max_correlated_picks})"
                            ),
                        )
                    )
                    continue

            selected.append(pick)
            horizon_counts[horizon_key] = current_horizon_count + 1
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            setup_keys.add(setup_key)
            if sector:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
            if cluster:
                cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

        return selected, rejected

    @staticmethod
    def _to_rejected(
        pick: RankedPick,
        reason: RejectionReason,
        note: str,
    ) -> RejectedOpportunity:
        return RejectedOpportunity(
            symbol=pick.trade_plan.symbol,
            timeframe=pick.trade_plan.timeframe,
            strategy_name=pick.trade_plan.strategy_name,
            horizon=pick.trade_plan.horizon,
            scanner_score=pick.scanner_score,
            rejection_reasons=[reason],
            notes=[note],
            metadata={"conviction_score": pick.conviction_score},
        )
