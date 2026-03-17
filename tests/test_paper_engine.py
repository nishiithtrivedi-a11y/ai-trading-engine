from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.core.data_handler import DataHandler
from src.execution.cost_model import CostConfig, CostModel
from src.paper_trading import (
    PaperPnLSnapshot,
    PaperPortfolioState,
    PaperStateStore,
    PaperTradingConfig,
    PaperTradingEngine,
)
from src.risk.risk_engine import PortfolioRiskConfig, PortfolioRiskManager
from src.strategies.base_strategy import BaseStrategy, Signal
from src.utils.config import BacktestConfig


def _make_ohlcv() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=6, freq="B")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 104.0, 106.0, 107.0],
            "high": [101.0, 102.0, 104.0, 105.0, 107.0, 108.0],
            "low": [99.0, 100.0, 101.0, 103.0, 105.0, 106.0],
            "close": [100.0, 101.0, 103.0, 104.0, 106.0, 107.0],
            "volume": [10_000.0] * 6,
        },
        index=index,
    )


class BuyExitStrategy(BaseStrategy):
    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        if bar_index == 1:
            return Signal.BUY
        if bar_index == 3:
            return Signal.EXIT
        return Signal.HOLD


class BuyOnlyStrategy(BaseStrategy):
    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        if bar_index == 1:
            return Signal.BUY
        return Signal.HOLD


class ExitOnlyStrategy(BaseStrategy):
    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        if bar_index == 1:
            return Signal.EXIT
        return Signal.HOLD


def _registry(strategy_cls: type[BaseStrategy]) -> dict[str, dict[str, object]]:
    return {"test": {"class": strategy_cls, "params": {}}}


def _engine(
    strategy_cls: type[BaseStrategy],
    paper_config: PaperTradingConfig,
    risk_manager: PortfolioRiskManager | None = None,
    state_store: PaperStateStore | None = None,
    cost_model: CostModel | None = None,
) -> PaperTradingEngine:
    return PaperTradingEngine(
        strategy_registry=_registry(strategy_cls),
        base_config=BacktestConfig(initial_capital=100_000.0),
        paper_config=paper_config,
        risk_manager=risk_manager,
        state_store=state_store,
        cost_model=cost_model
        or CostModel(CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)),
    )


def test_paper_engine_is_safe_by_default() -> None:
    engine = _engine(BuyExitStrategy, PaperTradingConfig(enabled=False))
    result = engine.run({"RELIANCE.NS": DataHandler(_make_ohlcv())}, persist=False)

    assert result.enabled is False
    assert result.state is None
    assert result.warnings
    assert "disabled" in result.warnings[0].lower()


def test_signal_to_order_and_position_lifecycle() -> None:
    engine = _engine(
        BuyExitStrategy,
        PaperTradingConfig(
            enabled=True,
            use_next_bar_fill=False,
            persist_state=False,
            default_stop_loss_pct=None,
            default_take_profit_pct=None,
        ),
    )
    result = engine.run({"RELIANCE.NS": DataHandler(_make_ohlcv())}, persist=False)

    assert result.state is not None
    assert len(result.state.orders) == 2
    assert len(result.state.fills) == 2
    assert len(result.state.open_positions) == 0
    assert len(result.state.closed_positions) == 1
    assert result.state.realized_pnl > 0.0
    assert len(result.state.pnl_history) == 6


def test_next_bar_fill_uses_following_bar_open() -> None:
    engine = _engine(
        BuyExitStrategy,
        PaperTradingConfig(
            enabled=True,
            use_next_bar_fill=True,
            persist_state=False,
            default_stop_loss_pct=None,
            default_take_profit_pct=None,
        ),
    )
    result = engine.run({"TCS.NS": DataHandler(_make_ohlcv())}, persist=False)

    assert result.state is not None
    buy_order = result.state.orders[0]
    sell_order = result.state.orders[1]
    assert str(buy_order.fill_timestamp) != str(buy_order.signal_timestamp)
    assert str(sell_order.fill_timestamp) != str(sell_order.signal_timestamp)
    assert buy_order.fill_price == 102.0
    assert sell_order.fill_price == 106.0


def test_risk_limit_blocks_new_entry() -> None:
    prior_state = PaperPortfolioState(initial_capital=100_000.0, cash=80_000.0, equity_peak=100_000.0)
    prior_state.pnl_history = [
        PaperPnLSnapshot(
            timestamp=pd.Timestamp("2025-01-01"),
            cash=100_000.0,
            market_value=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            equity=100_000.0,
            drawdown_pct=0.0,
            open_positions=0,
            pending_orders=0,
        ),
        PaperPnLSnapshot(
            timestamp=pd.Timestamp("2025-01-02"),
            cash=80_000.0,
            market_value=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            equity=80_000.0,
            drawdown_pct=0.2,
            open_positions=0,
            pending_orders=0,
        ),
    ]

    risk_manager = PortfolioRiskManager(
        PortfolioRiskConfig(
            max_drawdown_pct=0.10,
            max_concurrent_positions=5,
        )
    )
    engine = _engine(
        BuyOnlyStrategy,
        PaperTradingConfig(enabled=True, use_next_bar_fill=False, persist_state=False),
        risk_manager=risk_manager,
    )
    result = engine.run({"INFY.NS": DataHandler(_make_ohlcv())}, state=prior_state, persist=False)

    assert result.state is not None
    assert len(result.state.orders) == 0
    assert any(entry.event_type == "risk_rejection" for entry in result.state.journal)


def test_no_trade_is_logged_when_exit_signal_has_no_position() -> None:
    engine = _engine(
        ExitOnlyStrategy,
        PaperTradingConfig(enabled=True, use_next_bar_fill=False, persist_state=False),
    )
    result = engine.run({"HDFCBANK.NS": DataHandler(_make_ohlcv())}, persist=False)

    assert result.state is not None
    assert len(result.state.orders) == 0
    assert any(entry.event_type == "no_trade" for entry in result.state.journal)


def test_persistence_and_summary_are_written(tmp_path: Path) -> None:
    state_store = PaperStateStore(tmp_path / "paper_state.json")
    engine = _engine(
        BuyExitStrategy,
        PaperTradingConfig(
            enabled=True,
            use_next_bar_fill=False,
            persist_state=True,
            output_dir=str(tmp_path),
            default_stop_loss_pct=None,
            default_take_profit_pct=None,
        ),
        state_store=state_store,
    )
    result = engine.run({"ICICIBANK.NS": DataHandler(_make_ohlcv())})

    assert result.state is not None
    assert "paper_orders" in result.exports
    assert (tmp_path / "paper_orders.csv").exists()
    assert (tmp_path / "paper_positions.csv").exists()
    assert (tmp_path / "paper_pnl.csv").exists()
    assert (tmp_path / "paper_session_summary.md").exists()
    assert (tmp_path / "paper_artifacts_meta.json").exists()
    summary = (tmp_path / "paper_session_summary.md").read_text(encoding="utf-8")
    assert "Paper Trading Session Summary" in summary
    artifacts_meta = json.loads((tmp_path / "paper_artifacts_meta.json").read_text(encoding="utf-8"))
    assert artifacts_meta["schema_version"] == "v1"
    assert artifacts_meta["source"] == "paper.paper_state_store"
    state_payload = json.loads((tmp_path / "paper_state.json").read_text(encoding="utf-8"))
    assert state_payload["schema_version"] == "v1"
    assert state_payload["source"] == "paper.paper_portfolio_state"
    reloaded = state_store.load()
    assert len(reloaded.orders) == len(result.state.orders)


def test_unrealized_pnl_excludes_entry_fee_bias_for_open_positions() -> None:
    engine = _engine(
        BuyOnlyStrategy,
        PaperTradingConfig(
            enabled=True,
            use_next_bar_fill=False,
            persist_state=False,
            default_take_profit_pct=None,
        ),
        cost_model=CostModel(CostConfig(commission_per_trade=5.0, commission_bps=0.0, slippage_bps=0.0)),
    )
    result = engine.run({"SBIN.NS": DataHandler(_make_ohlcv())}, persist=False)

    assert result.state is not None
    assert len(result.state.open_positions) == 1
    position = result.state.open_positions[0]

    last_price = float(position.last_price or position.entry_price)
    gross_unrealized = (last_price - position.entry_price) * position.quantity

    assert position.unrealized_pnl(last_price) == gross_unrealized
    assert result.state.unrealized_pnl == gross_unrealized
    assert result.state.realized_pnl == -position.entry_fees


def test_realized_pnl_stays_consistent_after_open_and_close_with_fees() -> None:
    engine = _engine(
        BuyExitStrategy,
        PaperTradingConfig(
            enabled=True,
            use_next_bar_fill=False,
            persist_state=False,
            default_stop_loss_pct=None,
            default_take_profit_pct=None,
        ),
        cost_model=CostModel(CostConfig(commission_per_trade=3.0, commission_bps=0.0, slippage_bps=0.0)),
    )
    result = engine.run({"AXISBANK.NS": DataHandler(_make_ohlcv())}, persist=False)

    assert result.state is not None
    assert len(result.state.closed_positions) == 1

    closed = result.state.closed_positions[0]
    assert result.state.realized_pnl == closed.realized_pnl


def test_paper_engine_blocks_new_buys_when_allow_new_risk_is_false() -> None:
    engine = PaperTradingEngine(
        strategy_registry=_registry(BuyOnlyStrategy),
        base_config=BacktestConfig(initial_capital=100_000.0),
        paper_config=PaperTradingConfig(enabled=True, use_next_bar_fill=False, persist_state=False),
        allow_new_risk=False,
        cost_model=CostModel(CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)),
    )
    result = engine.run({"RELIANCE.NS": DataHandler(_make_ohlcv())}, persist=False)
    assert result.state is not None
    assert len(result.state.orders) == 0
    assert any("no_new_risk" in entry.message for entry in result.state.journal)


def test_paper_engine_applies_portfolio_override_quantity_cap() -> None:
    engine = PaperTradingEngine(
        strategy_registry=_registry(BuyOnlyStrategy),
        base_config=BacktestConfig(initial_capital=100_000.0),
        paper_config=PaperTradingConfig(enabled=True, use_next_bar_fill=False, persist_state=False),
        portfolio_plan_overrides={"RELIANCE.NS": {"recommended_quantity": 1}},
        cost_model=CostModel(CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)),
    )
    result = engine.run({"RELIANCE.NS": DataHandler(_make_ohlcv())}, persist=False)
    assert result.state is not None
    assert len(result.state.orders) >= 1
    buy_order = result.state.orders[0]
    assert buy_order.quantity == 1
    assert buy_order.metadata.get("portfolio_override_applied") is True
