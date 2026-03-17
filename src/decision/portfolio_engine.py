"""
Portfolio allocation, sizing, and risk overlay engine (Phase 18).

This module is recommendation-only and does not place orders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from src.data.symbol_mapping import SymbolMapper
from src.decision.config import DecisionHorizon
from src.decision.models import RankedPick
from src.decision.portfolio_config import PortfolioPlanningConfig
from src.decision.portfolio_models import (
    AllocationModel,
    DrawdownContext,
    DrawdownMode,
    PortfolioPlanItem,
    PortfolioPlanResult,
    PortfolioRiskSummary,
    SelectionStatus,
    SizingMethod,
)
from src.utils.logger import setup_logger

logger = setup_logger("portfolio_engine")


class PortfolioPlanningError(Exception):
    """Raised when portfolio planning cannot be completed safely."""


@dataclass
class PortfolioRiskEngine:
    config: PortfolioPlanningConfig = field(default_factory=PortfolioPlanningConfig)

    def __post_init__(self) -> None:
        self._mapper = SymbolMapper()

    def build_plan(
        self,
        picks: list[RankedPick],
        *,
        drawdown_context: Optional[DrawdownContext] = None,
    ) -> PortfolioPlanResult:
        context = drawdown_context or DrawdownContext()
        mode = self._resolve_drawdown_mode(context)
        cfg = self.config

        summary = PortfolioRiskSummary(
            drawdown_mode=mode,
            allocation_model=cfg.allocation_model.value,
            sizing_method=cfg.sizing_method.value,
            total_candidates=len(picks),
            metadata={
                "daily_drawdown_pct": context.daily_drawdown_pct,
                "rolling_drawdown_pct": context.rolling_drawdown_pct,
            },
        )
        result = PortfolioPlanResult(summary=summary)

        if not cfg.enabled:
            result.warnings.append("Portfolio planning disabled by config.")
            return result

        if not picks:
            result.warnings.append("No decision picks were available for portfolio planning.")
            return result

        if mode == DrawdownMode.NO_NEW_RISK and cfg.pause_new_risk_on_severe_drawdown:
            logger.info("Drawdown mode is NO_NEW_RISK; rejecting all new risk recommendations.")
            for pick in picks:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason="drawdown_pause_no_new_risk",
                        note="Drawdown threshold breached; new risk is paused.",
                    )
                )
            self._finalize_summary(result)
            return result

        capital_available = cfg.total_capital * (1.0 - cfg.reserve_cash_pct)
        max_deploy_capital = min(
            capital_available,
            cfg.total_capital * cfg.max_capital_deployed_pct,
        )
        risk_multiplier = cfg.reduce_risk_multiplier if mode == DrawdownMode.REDUCED_RISK else 1.0
        max_deploy_capital *= risk_multiplier

        sorted_picks = sorted(
            picks,
            key=lambda row: (
                (float(row.priority_rank) if row.priority_rank is not None else 10_000.0),
                -float(row.conviction_score),
                row.symbol,
            ),
        )
        weights = self._allocation_weights(sorted_picks)

        selected_count = 0
        deployed_capital = 0.0
        total_risk_amount = 0.0
        sector_exposure: dict[str, float] = {}
        bucket_counts: dict[str, int] = {}

        for pick in sorted_picks:
            if selected_count >= cfg.max_positions:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason="max_positions_reached",
                        note=f"Max positions reached ({cfg.max_positions}).",
                    )
                )
                continue

            remaining_capital = max(0.0, max_deploy_capital - deployed_capital)
            if remaining_capital <= 0.0:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason="max_capital_deployed_reached",
                        note="Max deployed capital reached.",
                    )
                )
                continue

            target_alloc = max_deploy_capital * weights.get(pick.symbol, 0.0)
            target_alloc = min(target_alloc, remaining_capital)
            resize_notes: list[str] = []

            per_position_cap = cfg.total_capital * cfg.max_per_position_allocation_pct
            if target_alloc > per_position_cap:
                target_alloc = per_position_cap
                resize_notes.append(
                    f"per_position_cap_applied({cfg.max_per_position_allocation_pct:.2f})"
                )

            sector = str(pick.sector or "unknown").strip() or "unknown"
            sector_cap = cfg.total_capital * cfg.max_sector_exposure_pct
            used_sector = sector_exposure.get(sector, 0.0)
            allowed_sector = max(0.0, sector_cap - used_sector)
            if allowed_sector <= 0.0:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason="max_sector_exposure_reached",
                        note=f"Sector cap reached for {sector}.",
                    )
                )
                continue
            if target_alloc > allowed_sector:
                target_alloc = allowed_sector
                resize_notes.append(f"sector_cap_applied({sector})")

            if target_alloc <= 0.0:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason="zero_target_allocation",
                        note="Target allocation resolved to zero.",
                    )
                )
                continue

            bucket = self._correlation_bucket(pick)
            if bucket_counts.get(bucket, 0) >= cfg.max_correlated_positions:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason="max_correlated_exposure_reached",
                        note=(
                            f"Correlation bucket cap reached for '{bucket}' "
                            f"({cfg.max_correlated_positions})."
                        ),
                    )
                )
                continue

            sizing = self._size_pick(
                pick=pick,
                target_allocation_amount=target_alloc,
                risk_multiplier=risk_multiplier,
            )
            if sizing.quantity <= 0:
                result.items.append(
                    self._rejected_item(
                        pick,
                        mode=mode,
                        reason=sizing.reason or "invalid_position_size",
                        note="Sizing produced a non-positive quantity.",
                    )
                )
                continue

            if sizing.notional_exposure > remaining_capital:
                capped_qty = int(math.floor(remaining_capital / max(1e-9, sizing.entry_price)))
                if capped_qty < 1:
                    result.items.append(
                        self._rejected_item(
                            pick,
                            mode=mode,
                            reason="insufficient_remaining_capital",
                            note="Remaining capital cannot fund at least one unit.",
                        )
                    )
                    continue
                resize_notes.append("remaining_capital_cap_applied")
                sizing = sizing.with_quantity(capped_qty)

            max_trade_risk_amt = cfg.total_capital * cfg.max_per_trade_risk_pct * risk_multiplier
            if sizing.estimated_risk_amount > max_trade_risk_amt:
                if sizing.risk_per_unit <= 0:
                    result.items.append(
                        self._rejected_item(
                            pick,
                            mode=mode,
                            reason="invalid_risk_per_unit",
                            note="Risk-per-unit could not be computed safely.",
                        )
                    )
                    continue
                capped_qty = int(math.floor(max_trade_risk_amt / sizing.risk_per_unit))
                if capped_qty < 1:
                    result.items.append(
                        self._rejected_item(
                            pick,
                            mode=mode,
                            reason="max_per_trade_risk_rejection",
                            note="Per-trade risk cap blocks this setup.",
                        )
                    )
                    continue
                resize_notes.append("max_per_trade_risk_cap_applied")
                sizing = sizing.with_quantity(capped_qty)

            selection_status = (
                SelectionStatus.RESIZED if resize_notes or sizing.was_fallback else SelectionStatus.SELECTED
            )
            resize_reason = "; ".join(resize_notes + sizing.notes)
            correlation_note = (
                "bucket_limit_applied"
                if bucket_counts.get(bucket, 0) >= cfg.max_correlated_positions - 1
                else "within_bucket_limit"
            )

            item = PortfolioPlanItem(
                symbol=pick.symbol,
                canonical_symbol=self._mapper.to_canonical(pick.symbol),
                strategy_name=pick.trade_plan.strategy_name,
                timeframe=pick.trade_plan.timeframe,
                confidence_score=float(pick.conviction_score),
                allocation_model=cfg.allocation_model.value,
                allocation_percent=sizing.notional_exposure / cfg.total_capital if cfg.total_capital > 0 else 0.0,
                allocation_amount=sizing.notional_exposure,
                sizing_method=sizing.method,
                quantity=sizing.quantity,
                notional_exposure=sizing.notional_exposure,
                estimated_entry=sizing.entry_price,
                estimated_stop=sizing.stop_price,
                estimated_target=sizing.target_price,
                estimated_risk_amount=sizing.estimated_risk_amount,
                estimated_risk_percent=(
                    sizing.estimated_risk_amount / cfg.total_capital if cfg.total_capital > 0 else 0.0
                ),
                sector=sector,
                correlation_bucket=bucket,
                correlation_note=correlation_note,
                selection_status=selection_status,
                resize_reason=resize_reason,
                drawdown_mode=mode,
                notes=list(pick.reasons),
                metadata={
                    "priority_rank": pick.priority_rank,
                    "horizon_rank": pick.horizon_rank,
                    "horizon": pick.horizon.value,
                    "scanner_score": float(pick.scanner_score),
                    "risk_per_unit": sizing.risk_per_unit,
                },
            )
            result.items.append(item)
            selected_count += 1
            deployed_capital += sizing.notional_exposure
            total_risk_amount += sizing.estimated_risk_amount
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + sizing.notional_exposure
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

            logger.info(
                "Portfolio selection %s/%s: qty=%s alloc=%.2f risk=%.2f mode=%s",
                item.symbol,
                item.strategy_name,
                item.quantity,
                item.allocation_amount,
                item.estimated_risk_amount,
                item.drawdown_mode.value,
            )

        result.summary.deployed_capital = deployed_capital
        result.summary.deployed_capital_pct = deployed_capital / cfg.total_capital if cfg.total_capital > 0 else 0.0
        result.summary.reserved_cash = max(0.0, cfg.total_capital - deployed_capital)
        result.summary.estimated_total_risk_amount = total_risk_amount
        result.summary.estimated_total_risk_pct = (
            total_risk_amount / cfg.total_capital if cfg.total_capital > 0 else 0.0
        )
        self._finalize_summary(result)
        return result

    def _finalize_summary(self, result: PortfolioPlanResult) -> None:
        selected = [row for row in result.items if row.selection_status != SelectionStatus.REJECTED]
        resized = [row for row in selected if row.selection_status == SelectionStatus.RESIZED]
        rejected = [row for row in result.items if row.selection_status == SelectionStatus.REJECTED]
        result.summary.selected_count = len(selected)
        result.summary.resized_count = len(resized)
        result.summary.rejected_count = len(rejected)

    def _resolve_drawdown_mode(self, context: DrawdownContext) -> DrawdownMode:
        cfg = self.config
        if (
            context.daily_drawdown_pct >= cfg.max_daily_drawdown_pct
            or context.rolling_drawdown_pct >= cfg.max_rolling_drawdown_pct
        ):
            return DrawdownMode.NO_NEW_RISK if cfg.pause_new_risk_on_severe_drawdown else DrawdownMode.REDUCED_RISK
        if (
            context.daily_drawdown_pct >= cfg.drawdown_daily_reduce_risk_pct
            or context.rolling_drawdown_pct >= cfg.drawdown_rolling_reduce_risk_pct
        ):
            return DrawdownMode.REDUCED_RISK
        return DrawdownMode.NORMAL

    def _allocation_weights(self, picks: list[RankedPick]) -> dict[str, float]:
        if not picks:
            return {}
        raw_weights: dict[str, float] = {}
        if self.config.allocation_model == AllocationModel.EQUAL_WEIGHT:
            raw_weights = {pick.symbol: 1.0 for pick in picks}
        elif self.config.allocation_model == AllocationModel.CONVICTION_WEIGHTED:
            for pick in picks:
                raw_weights[pick.symbol] = max(1.0, float(pick.conviction_score))
        else:
            for pick in picks:
                volatility = self._volatility_proxy(pick)
                raw_weights[pick.symbol] = 1.0 / max(1e-9, volatility)

        total = sum(raw_weights.values())
        if total <= 0:
            return {pick.symbol: 1.0 / len(picks) for pick in picks}
        return {symbol: value / total for symbol, value in raw_weights.items()}

    @staticmethod
    def _volatility_proxy(pick: RankedPick) -> float:
        metadata = pick.trade_plan.metadata or {}
        atr = metadata.get("atr")
        if atr is not None:
            try:
                atr_value = float(atr)
                if atr_value > 0:
                    return atr_value / max(1e-9, float(pick.trade_plan.entry_price))
            except (TypeError, ValueError):
                pass
        risk_proxy = max(1e-9, float(pick.trade_plan.entry_price - pick.trade_plan.stop_loss))
        return risk_proxy / max(1e-9, float(pick.trade_plan.entry_price))

    @staticmethod
    def _correlation_bucket(pick: RankedPick) -> str:
        metadata = pick.trade_plan.metadata or {}
        cluster = str(metadata.get("cluster", "")).strip()
        if cluster:
            return cluster
        horizon = pick.horizon.value if isinstance(pick.horizon, DecisionHorizon) else str(pick.horizon)
        return f"{pick.trade_plan.strategy_name}:{horizon}"

    @dataclass
    class _SizingOutcome:
        quantity: int
        method: str
        entry_price: float
        stop_price: float
        target_price: float
        notional_exposure: float
        estimated_risk_amount: float
        risk_per_unit: float
        notes: list[str] = field(default_factory=list)
        reason: str = ""
        was_fallback: bool = False

        def with_quantity(self, quantity: int) -> "PortfolioRiskEngine._SizingOutcome":
            qty = int(max(0, quantity))
            notional = qty * self.entry_price
            risk_amt = qty * self.risk_per_unit
            return PortfolioRiskEngine._SizingOutcome(
                quantity=qty,
                method=self.method,
                entry_price=self.entry_price,
                stop_price=self.stop_price,
                target_price=self.target_price,
                notional_exposure=notional,
                estimated_risk_amount=risk_amt,
                risk_per_unit=self.risk_per_unit,
                notes=list(self.notes),
                reason=self.reason,
                was_fallback=self.was_fallback,
            )

    def _size_pick(
        self,
        *,
        pick: RankedPick,
        target_allocation_amount: float,
        risk_multiplier: float,
    ) -> _SizingOutcome:
        cfg = self.config
        plan = pick.trade_plan
        entry = float(plan.entry_price)
        stop = float(plan.stop_loss)
        target = float(plan.target_price)
        risk_unit = max(1e-9, entry - stop)
        cap_qty = int(math.floor(target_allocation_amount / max(1e-9, entry)))

        if cap_qty < 1:
            return self._SizingOutcome(
                quantity=0,
                method=cfg.sizing_method.value,
                entry_price=entry,
                stop_price=stop,
                target_price=target,
                notional_exposure=0.0,
                estimated_risk_amount=0.0,
                risk_per_unit=risk_unit,
                reason="allocation_too_small_for_one_unit",
            )

        if cfg.sizing_method == SizingMethod.FIXED_FRACTIONAL:
            qty = int(
                math.floor(
                    (target_allocation_amount * cfg.fixed_fractional_position_pct) / max(1e-9, entry)
                )
            )
            qty = max(0, min(cap_qty, qty))
            return self._build_outcome(
                quantity=qty,
                method=SizingMethod.FIXED_FRACTIONAL.value,
                entry=entry,
                stop=stop,
                target=target,
                risk_per_unit=risk_unit,
            )

        risk_budget = cfg.total_capital * cfg.risk_per_trade_pct * risk_multiplier
        if cfg.sizing_method == SizingMethod.RISK_PER_TRADE:
            risk_qty = int(math.floor(risk_budget / risk_unit))
            qty = max(0, min(cap_qty, risk_qty))
            return self._build_outcome(
                quantity=qty,
                method=SizingMethod.RISK_PER_TRADE.value,
                entry=entry,
                stop=stop,
                target=target,
                risk_per_unit=risk_unit,
            )

        # ATR sizing path with fallback.
        atr = self._extract_atr(plan.metadata)
        if atr is not None and atr > 0:
            atr_qty = int(math.floor(risk_budget / atr))
            qty = max(0, min(cap_qty, atr_qty))
            return self._build_outcome(
                quantity=qty,
                method=SizingMethod.ATR_BASED.value,
                entry=entry,
                stop=stop,
                target=target,
                risk_per_unit=atr,
            )

        # fallback to risk-per-trade using stop-distance.
        risk_qty = int(math.floor(risk_budget / risk_unit))
        qty = max(0, min(cap_qty, risk_qty))
        outcome = self._build_outcome(
            quantity=qty,
            method="atr_based_fallback_risk_per_trade",
            entry=entry,
            stop=stop,
            target=target,
            risk_per_unit=risk_unit,
        )
        outcome.was_fallback = True
        outcome.notes.append("atr_missing_fallback_to_risk_per_trade")
        return outcome

    @staticmethod
    def _extract_atr(metadata: Optional[dict]) -> Optional[float]:
        if not isinstance(metadata, dict):
            return None
        for key in ("atr", "atr_value", "atr_14"):
            if key not in metadata:
                continue
            try:
                value = float(metadata[key])
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    @staticmethod
    def _build_outcome(
        *,
        quantity: int,
        method: str,
        entry: float,
        stop: float,
        target: float,
        risk_per_unit: float,
    ) -> _SizingOutcome:
        qty = int(max(0, quantity))
        notional = qty * entry
        risk_amount = qty * risk_per_unit
        return PortfolioRiskEngine._SizingOutcome(
            quantity=qty,
            method=method,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            notional_exposure=notional,
            estimated_risk_amount=risk_amount,
            risk_per_unit=risk_per_unit,
        )

    def _rejected_item(
        self,
        pick: RankedPick,
        *,
        mode: DrawdownMode,
        reason: str,
        note: str,
    ) -> PortfolioPlanItem:
        logger.info(
            "Portfolio rejected %s/%s/%s: %s",
            pick.symbol,
            pick.trade_plan.timeframe,
            pick.trade_plan.strategy_name,
            reason,
        )
        return PortfolioPlanItem(
            symbol=pick.symbol,
            canonical_symbol=self._mapper.to_canonical(pick.symbol),
            strategy_name=pick.trade_plan.strategy_name,
            timeframe=pick.trade_plan.timeframe,
            confidence_score=float(pick.conviction_score),
            allocation_model=self.config.allocation_model.value,
            allocation_percent=0.0,
            allocation_amount=0.0,
            sizing_method=self.config.sizing_method.value,
            quantity=0,
            notional_exposure=0.0,
            estimated_entry=float(pick.trade_plan.entry_price),
            estimated_stop=float(pick.trade_plan.stop_loss),
            estimated_target=float(pick.trade_plan.target_price),
            estimated_risk_amount=0.0,
            estimated_risk_percent=0.0,
            sector=str(pick.sector or "unknown"),
            correlation_bucket=self._correlation_bucket(pick),
            correlation_note="rejected",
            selection_status=SelectionStatus.REJECTED,
            rejection_reason=reason,
            drawdown_mode=mode,
            notes=[note],
            metadata={
                "priority_rank": pick.priority_rank,
                "horizon": pick.horizon.value,
                "scanner_score": float(pick.scanner_score),
            },
        )
