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


# ---------------------------------------------------------------------------
# Additional tests added in regression-hardening pass
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty_list() -> None:
    ranked = RankingEngine().rank([])
    assert ranked == []


def test_single_pick_gets_rank_1() -> None:
    picks = [_pick("RELIANCE.NS", DecisionHorizon.POSITIONAL, 75, 2.0, 60)]
    ranked = RankingEngine().rank(picks)
    assert len(ranked) == 1
    assert ranked[0].priority_rank == 1
    assert ranked[0].horizon_rank == 1


def test_priority_ranks_are_contiguous_from_1() -> None:
    picks = [
        _pick("A.NS", DecisionHorizon.SWING, 80, 2.0, 70),
        _pick("B.NS", DecisionHorizon.SWING, 70, 2.0, 70),
        _pick("C.NS", DecisionHorizon.SWING, 60, 2.0, 70),
        _pick("D.NS", DecisionHorizon.SWING, 50, 2.0, 70),
    ]
    ranked = RankingEngine().rank(picks)
    assert [p.priority_rank for p in ranked] == [1, 2, 3, 4]


def test_rs_score_breaks_rr_tie() -> None:
    """When conviction and RR are equal, higher RS score should rank first."""
    picks = [
        _pick("LOW_RS.NS", DecisionHorizon.SWING, 80, 2.0, 70, rs=-0.5),
        _pick("HIGH_RS.NS", DecisionHorizon.SWING, 80, 2.0, 70, rs=0.5),
    ]
    ranked = RankingEngine().rank(picks)
    assert ranked[0].symbol == "HIGH_RS.NS"
    assert ranked[1].symbol == "LOW_RS.NS"


def test_none_rs_score_ranks_below_explicit_rs() -> None:
    """A pick with rs=None should rank below a pick with explicit rs score."""
    picks = [
        _pick("NO_RS.NS", DecisionHorizon.POSITIONAL, 80, 2.0, 70, rs=None),
        _pick("HAS_RS.NS", DecisionHorizon.POSITIONAL, 80, 2.0, 70, rs=0.0),
    ]
    ranked = RankingEngine().rank(picks)
    assert ranked[0].symbol == "HAS_RS.NS"


def test_scanner_score_breaks_rs_tie() -> None:
    """When conviction, RR, RS are equal, higher scanner_score should rank first."""
    picks = [
        _pick("LOW_SC.NS", DecisionHorizon.SWING, 80, 2.0, scanner_score=60, rs=0.2),
        _pick("HIGH_SC.NS", DecisionHorizon.SWING, 80, 2.0, scanner_score=90, rs=0.2),
    ]
    ranked = RankingEngine().rank(picks)
    assert ranked[0].symbol == "HIGH_SC.NS"


def test_split_by_horizon_groups_correctly() -> None:
    picks = [
        _pick("A.NS", DecisionHorizon.INTRADAY, 90, 2.0, 70),
        _pick("B.NS", DecisionHorizon.SWING, 85, 2.0, 70),
        _pick("C.NS", DecisionHorizon.SWING, 80, 2.0, 70),
        _pick("D.NS", DecisionHorizon.POSITIONAL, 75, 2.0, 70),
    ]
    grouped = RankingEngine.split_by_horizon(picks)

    assert len(grouped[DecisionHorizon.INTRADAY]) == 1
    assert len(grouped[DecisionHorizon.SWING]) == 2
    assert len(grouped[DecisionHorizon.POSITIONAL]) == 1


def test_split_by_horizon_empty_returns_empty_groups() -> None:
    grouped = RankingEngine.split_by_horizon([])
    for horizon in DecisionHorizon:
        assert grouped[horizon] == []


def test_all_three_horizon_ranks_independent() -> None:
    picks = [
        _pick("I1.NS", DecisionHorizon.INTRADAY, 90, 2.0, 70),
        _pick("I2.NS", DecisionHorizon.INTRADAY, 80, 2.0, 70),
        _pick("S1.NS", DecisionHorizon.SWING, 85, 2.0, 70),
        _pick("P1.NS", DecisionHorizon.POSITIONAL, 75, 2.0, 70),
        _pick("P2.NS", DecisionHorizon.POSITIONAL, 65, 2.0, 70),
        _pick("P3.NS", DecisionHorizon.POSITIONAL, 55, 2.0, 70),
    ]
    ranked = RankingEngine().rank(picks)
    by_symbol = {p.symbol: p for p in ranked}

    assert by_symbol["I1.NS"].horizon_rank == 1
    assert by_symbol["I2.NS"].horizon_rank == 2
    assert by_symbol["S1.NS"].horizon_rank == 1
    assert by_symbol["P1.NS"].horizon_rank == 1
    assert by_symbol["P2.NS"].horizon_rank == 2
    assert by_symbol["P3.NS"].horizon_rank == 3
