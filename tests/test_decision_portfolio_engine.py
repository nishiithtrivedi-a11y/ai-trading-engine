from __future__ import annotations

import pandas as pd
import pytest

from src.decision import (
    AllocationModel,
    ConvictionBreakdown,
    DecisionHorizon,
    DrawdownContext,
    PortfolioPlanningConfig,
    PortfolioRiskEngine,
    RankedPick,
    SelectionStatus,
    SizingMethod,
    TradePlan,
)


def _pick(
    symbol: str,
    *,
    conviction: float,
    entry: float = 100.0,
    stop: float = 98.0,
    target: float = 106.0,
    sector: str = "IT",
    atr: float | None = None,
    cluster: str | None = None,
) -> RankedPick:
    metadata: dict[str, object] = {"sector": sector}
    if atr is not None:
        metadata["atr"] = atr
    if cluster is not None:
        metadata["cluster"] = cluster

    plan = TradePlan(
        symbol=symbol,
        timeframe="1D",
        strategy_name="SMACrossoverStrategy",
        entry_price=entry,
        stop_loss=stop,
        target_price=target,
        risk_reward=(target - entry) / (entry - stop),
        horizon=DecisionHorizon.SWING,
        metadata=metadata,
    )
    breakdown = ConvictionBreakdown(
        scanner_score=conviction,
        setup_quality=conviction,
        risk_reward=conviction,
        regime_compatibility=conviction,
        relative_strength=conviction,
        liquidity=conviction,
        freshness=conviction,
        final_score=conviction,
    )
    return RankedPick(
        trade_plan=plan,
        conviction_score=conviction,
        conviction_breakdown=breakdown,
        scanner_score=conviction,
        reasons=["unit_test"],
    )


def test_equal_weight_allocation_is_balanced() -> None:
    cfg = PortfolioPlanningConfig(
        total_capital=100_000.0,
        reserve_cash_pct=0.0,
        max_capital_deployed_pct=0.9,
        max_sector_exposure_pct=1.0,
        max_correlated_positions=3,
        allocation_model=AllocationModel.EQUAL_WEIGHT,
        sizing_method=SizingMethod.FIXED_FRACTIONAL,
        fixed_fractional_position_pct=1.0,
        max_positions=3,
    )
    engine = PortfolioRiskEngine(cfg)
    picks = [
        _pick("RELIANCE.NS", conviction=85.0),
        _pick("TCS.NS", conviction=80.0),
        _pick("INFY.NS", conviction=75.0),
    ]

    plan = engine.build_plan(picks)
    selected = [row for row in plan.items if row.selection_status != SelectionStatus.REJECTED]
    assert len(selected) == 3
    allocs = [row.allocation_amount for row in selected]
    assert max(allocs) - min(allocs) < 200.0
    assert plan.summary.selected_count == 3


def test_conviction_weighted_allocates_more_to_higher_conviction() -> None:
    cfg = PortfolioPlanningConfig(
        total_capital=100_000.0,
        reserve_cash_pct=0.0,
        allocation_model=AllocationModel.CONVICTION_WEIGHTED,
        sizing_method=SizingMethod.FIXED_FRACTIONAL,
        fixed_fractional_position_pct=1.0,
        max_positions=2,
    )
    engine = PortfolioRiskEngine(cfg)
    picks = [
        _pick("RELIANCE.NS", conviction=90.0),
        _pick("TCS.NS", conviction=60.0),
    ]
    plan = engine.build_plan(picks)
    selected = {row.symbol: row for row in plan.selected_items}
    assert selected["RELIANCE.NS"].allocation_amount > selected["TCS.NS"].allocation_amount


def test_volatility_weighted_prefers_lower_volatility() -> None:
    cfg = PortfolioPlanningConfig(
        total_capital=100_000.0,
        reserve_cash_pct=0.0,
        allocation_model=AllocationModel.VOLATILITY_WEIGHTED,
        sizing_method=SizingMethod.FIXED_FRACTIONAL,
        fixed_fractional_position_pct=1.0,
        max_positions=2,
    )
    engine = PortfolioRiskEngine(cfg)
    low_vol = _pick("RELIANCE.NS", conviction=70.0, atr=1.5)
    high_vol = _pick("TCS.NS", conviction=90.0, atr=6.0)
    plan = engine.build_plan([low_vol, high_vol])
    selected = {row.symbol: row for row in plan.selected_items}
    assert selected["RELIANCE.NS"].allocation_amount > selected["TCS.NS"].allocation_amount


def test_drawdown_no_new_risk_blocks_new_positions() -> None:
    cfg = PortfolioPlanningConfig(
        total_capital=100_000.0,
        max_daily_drawdown_pct=0.03,
        max_rolling_drawdown_pct=0.10,
        pause_new_risk_on_severe_drawdown=True,
    )
    engine = PortfolioRiskEngine(cfg)
    plan = engine.build_plan(
        [_pick("RELIANCE.NS", conviction=88.0)],
        drawdown_context=DrawdownContext(daily_drawdown_pct=0.04, rolling_drawdown_pct=0.05),
    )
    assert plan.summary.drawdown_mode.value == "no_new_risk"
    assert plan.summary.selected_count == 0
    assert plan.items[0].selection_status == SelectionStatus.REJECTED
    assert "drawdown" in plan.items[0].rejection_reason


def test_sector_and_bucket_caps_reject_excess_candidates() -> None:
    cfg = PortfolioPlanningConfig(
        total_capital=100_000.0,
        reserve_cash_pct=0.0,
        max_positions=5,
        max_sector_exposure_pct=0.20,
        max_correlated_positions=1,
        allocation_model=AllocationModel.EQUAL_WEIGHT,
        sizing_method=SizingMethod.FIXED_FRACTIONAL,
    )
    engine = PortfolioRiskEngine(cfg)
    picks = [
        _pick("RELIANCE.NS", conviction=80.0, sector="ENERGY", cluster="A"),
        _pick("ONGC.NS", conviction=78.0, sector="ENERGY", cluster="A"),
        _pick("TCS.NS", conviction=82.0, sector="IT", cluster="B"),
    ]
    plan = engine.build_plan(picks)
    rejected_reasons = [row.rejection_reason for row in plan.rejected_items]
    assert any("max_sector_exposure_reached" in value for value in rejected_reasons) or any(
        "max_correlated_exposure_reached" in value for value in rejected_reasons
    )


def test_atr_sizing_falls_back_when_atr_missing() -> None:
    cfg = PortfolioPlanningConfig(
        total_capital=100_000.0,
        reserve_cash_pct=0.0,
        sizing_method=SizingMethod.ATR_BASED,
        risk_per_trade_pct=0.01,
        max_positions=1,
    )
    engine = PortfolioRiskEngine(cfg)
    plan = engine.build_plan([_pick("INFY.NS", conviction=85.0, atr=None)])
    assert plan.selected_items
    row = plan.selected_items[0]
    assert "fallback" in row.sizing_method
    assert row.quantity >= 1
    assert row.estimated_risk_amount > 0


def test_portfolio_planning_config_validation() -> None:
    with pytest.raises(ValueError):
        PortfolioPlanningConfig(total_capital=0.0)
    with pytest.raises(ValueError):
        PortfolioPlanningConfig(max_positions=0)
    with pytest.raises(ValueError):
        PortfolioPlanningConfig(reserve_cash_pct=0.7, max_capital_deployed_pct=0.5)
