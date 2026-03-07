from __future__ import annotations

from src.decision.models import ConvictionBreakdown, DecisionHorizon, RankedPick, TradePlan
from src.decision.ranking_engine import RankingEngine


def _pick(
    symbol: str,
    horizon: DecisionHorizon,
    conviction: float,
    rr: float,
    scanner_score: float,
    rs: float | None = None,
) -> RankedPick:
    plan = TradePlan(
        symbol=symbol,
        timeframe="1D",
        strategy_name="S1",
        entry_price=100.0,
        stop_loss=99.0,
        target_price=100.0 + rr,
        risk_reward=rr,
        horizon=horizon,
    )
    breakdown = ConvictionBreakdown(
        scanner_score=scanner_score,
        setup_quality=70.0,
        risk_reward=70.0,
        regime_compatibility=70.0,
        relative_strength=70.0,
        liquidity=70.0,
        freshness=70.0,
        final_score=conviction,
    )
    return RankedPick(
        trade_plan=plan,
        conviction_score=conviction,
        conviction_breakdown=breakdown,
        scanner_score=scanner_score,
        relative_strength_score=rs,
    )


def test_ranking_orders_by_conviction_then_rr() -> None:
    picks = [
        _pick("B.NS", DecisionHorizon.SWING, conviction=80, rr=2.0, scanner_score=75),
        _pick("A.NS", DecisionHorizon.SWING, conviction=90, rr=1.1, scanner_score=75),
        _pick("C.NS", DecisionHorizon.SWING, conviction=80, rr=2.5, scanner_score=75),
    ]
    ranked = RankingEngine().rank(picks)

    assert ranked[0].symbol == "A.NS"
    assert ranked[1].symbol == "C.NS"
    assert ranked[2].symbol == "B.NS"
    assert ranked[0].priority_rank == 1
    assert ranked[1].priority_rank == 2


def test_ranking_is_stable_with_symbol_tie_breaker() -> None:
    picks = [
        _pick("TCS.NS", DecisionHorizon.POSITIONAL, 85, 2.0, 70, rs=0.2),
        _pick("INFY.NS", DecisionHorizon.POSITIONAL, 85, 2.0, 70, rs=0.2),
    ]
    ranked = RankingEngine().rank(picks)
    assert ranked[0].symbol == "INFY.NS"
    assert ranked[1].symbol == "TCS.NS"


def test_horizon_ranks_are_assigned_separately() -> None:
    picks = [
        _pick("A.NS", DecisionHorizon.INTRADAY, 95, 2.0, 70),
        _pick("B.NS", DecisionHorizon.SWING, 90, 2.0, 70),
        _pick("C.NS", DecisionHorizon.SWING, 85, 2.0, 70),
    ]
    ranked = RankingEngine().rank(picks)
    by_symbol = {p.symbol: p for p in ranked}

    assert by_symbol["A.NS"].horizon_rank == 1
    assert by_symbol["B.NS"].horizon_rank == 1
    assert by_symbol["C.NS"].horizon_rank == 2
