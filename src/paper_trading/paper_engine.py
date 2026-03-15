"""
Paper-trading engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from src.core.data_handler import DataHandler
from src.decision.regime_policy import select_for_regime
from src.execution.cost_model import CostModel
from src.execution.fill_model import FillConfig, FillModel
from src.market_intelligence.regime_engine import MarketRegimeEngine
from src.market_intelligence.relative_strength import compute_relative_strength
from src.paper_trading.models import (
    PaperFill,
    PaperOrder,
    PaperOrderSide,
    PaperOrderStatus,
    PaperPnLSnapshot,
    PaperPortfolioState,
    PaperPosition,
    PaperTradingConfig,
    PaperTradingResult,
)
from src.paper_trading.state_store import PaperStateStore
from src.risk.risk_engine import PortfolioRiskManager
from src.strategies.base_strategy import Signal
from src.utils.config import BacktestConfig


class PaperTradingError(Exception):
    """Raised when the paper-trading engine cannot continue safely."""


@dataclass
class PaperTradingEngine:
    strategy_registry: dict[str, dict[str, Any]]
    base_config: BacktestConfig
    paper_config: PaperTradingConfig = field(default_factory=PaperTradingConfig)
    risk_manager: Optional[PortfolioRiskManager] = None
    cost_model: Optional[CostModel] = None
    fill_model: Optional[FillModel] = None
    regime_engine: Optional[MarketRegimeEngine] = None
    regime_policy: Optional[Any] = None
    state_store: Optional[PaperStateStore] = None

    def __post_init__(self) -> None:
        if not self.strategy_registry:
            raise ValueError("strategy_registry cannot be empty")
        self.risk_manager = self.risk_manager or PortfolioRiskManager()
        self.cost_model = self.cost_model or CostModel()
        self.fill_model = self.fill_model or FillModel(
            FillConfig(use_next_bar_open=self.paper_config.use_next_bar_fill)
        )
        self.regime_engine = self.regime_engine or MarketRegimeEngine()
        self.state_store = self.state_store or PaperStateStore(
            self.paper_config.output_path / "paper_state.json"
        )

    def run(
        self,
        symbol_to_data: dict[str, DataHandler],
        state: Optional[PaperPortfolioState] = None,
        persist: Optional[bool] = None,
    ) -> PaperTradingResult:
        result = PaperTradingResult(
            enabled=self.paper_config.enabled,
            config_snapshot=self.paper_config.to_dict(),
        )

        if not self.paper_config.enabled:
            result.completed_at = pd.Timestamp.now(tz="UTC")
            result.warnings.append("Paper trading disabled. Pass --paper-trading to run a session.")
            return result

        working_state = state or self.state_store.load(self.paper_config.initial_capital)
        frames = self._prepare_frames(symbol_to_data, result)
        if not frames:
            result.completed_at = pd.Timestamp.now(tz="UTC")
            result.errors.append("No valid market data was available for the paper-trading session.")
            result.state = working_state
            return result

        ranked_symbols = self._rank_symbols(frames, result)
        timeline = sorted({timestamp for df in frames.values() for timestamp in df.index})

        session_order_count = 0
        for timestamp in timeline:
            bars_now = {
                symbol: df.loc[timestamp]
                for symbol, df in frames.items()
                if timestamp in df.index
            }
            if not bars_now:
                continue

            for symbol in ranked_symbols:
                if symbol not in bars_now:
                    continue
                self._fill_pending_orders(symbol, timestamp, bars_now[symbol], working_state)

            for symbol in ranked_symbols:
                if symbol not in bars_now:
                    continue
                self._process_protective_exits(symbol, timestamp, bars_now[symbol], working_state)

            for symbol in ranked_symbols:
                if symbol not in bars_now:
                    continue
                df_slice = frames[symbol].loc[:timestamp]
                if df_slice.empty:
                    continue
                created = self._evaluate_symbol(
                    symbol=symbol,
                    timestamp=timestamp,
                    data_slice=df_slice,
                    current_bar=bars_now[symbol],
                    state=working_state,
                    result=result,
                    session_order_count=session_order_count,
                )
                session_order_count += created

            for symbol, bar in bars_now.items():
                close_price = float(bar["close"])
                working_state.last_prices[symbol] = close_price
                working_state.last_timestamps[symbol] = pd.Timestamp(timestamp).isoformat()
                position = working_state.get_open_position(symbol)
                if position is not None:
                    position.update_market_price(close_price, pd.Timestamp(timestamp))
                    position.bars_held += 1

            self._record_pnl_snapshot(pd.Timestamp(timestamp), working_state)

        if self.paper_config.close_open_positions_at_end and timeline:
            self._close_all_positions_at_end(timeline[-1], frames, working_state)
            self._record_pnl_snapshot(pd.Timestamp(timeline[-1]), working_state)

        working_state.updated_at = pd.Timestamp.now(tz="UTC")
        result.completed_at = pd.Timestamp.now(tz="UTC")
        result.state = working_state
        result.symbols_evaluated = sorted(frames.keys())
        result.metadata["timeline_bars"] = len(timeline)
        result.metadata["session_orders_created"] = session_order_count

        should_persist = self.paper_config.persist_state if persist is None else bool(persist)
        if should_persist:
            exports = self.state_store.export_session(result, self.paper_config.output_path)
            result.exports = {name: str(path) for name, path in exports.items()}

        return result

    def _prepare_frames(
        self,
        symbol_to_data: dict[str, DataHandler],
        result: PaperTradingResult,
    ) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for symbol, handler in symbol_to_data.items():
            df = handler.data.copy()
            if self.paper_config.session_date is not None:
                df = df.loc[df.index <= self.paper_config.session_date]
            if df.empty or len(df) < 2:
                result.warnings.append(f"{symbol}: skipped because fewer than 2 bars were available")
                continue
            frames[str(symbol).strip().upper()] = df.sort_index()
        return frames

    @staticmethod
    def _fallback_strategy_name(strategy_registry: dict[str, dict[str, Any]]) -> str:
        return sorted(strategy_registry.keys())[0]

    def _rank_symbols(
        self,
        frames: dict[str, pd.DataFrame],
        result: PaperTradingResult,
    ) -> list[str]:
        try:
            rs_df = compute_relative_strength(
                frames,
                lookback=min(90, min(len(df) for df in frames.values())),
            )
            if not rs_df.empty and "symbol" in rs_df.columns:
                ranked = rs_df["symbol"].tolist()
                result.metadata["relative_strength_ranking"] = rs_df.to_dict(orient="records")
                return [str(symbol).strip().upper() for symbol in ranked]
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Relative strength ranking failed, falling back to alphabetical order: {exc}")
        return sorted(frames.keys())

    def _evaluate_symbol(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        data_slice: pd.DataFrame,
        current_bar: pd.Series,
        state: PaperPortfolioState,
        result: PaperTradingResult,
        session_order_count: int,
    ) -> int:
        selection = self._select_strategy(symbol, data_slice)
        result.regime_labels[symbol] = selection["regime_label"]

        if not selection["should_trade"]:
            state.add_journal(
                timestamp=timestamp,
                symbol=symbol,
                event_type="no_trade",
                message=selection["reason"],
                strategy_name=selection["strategy_name"],
                metadata={"regime_label": selection["regime_label"]},
            )
            return 0

        strategy_name = selection["strategy_name"]
        result.strategies_selected[symbol] = strategy_name

        if state.has_pending_order(symbol):
            return 0

        registry_entry = self.strategy_registry[strategy_name]
        strategy_cls = registry_entry["class"]
        params = dict(registry_entry.get("params", {}))
        strategy = strategy_cls(**params)
        strategy.initialize(params)

        signal = strategy.on_bar(
            data=data_slice,
            current_bar=current_bar,
            bar_index=len(data_slice) - 1,
        )
        if signal == Signal.HOLD:
            return 0

        current_close = float(current_bar["close"])
        open_position = state.get_open_position(symbol)
        stop_loss_pct = (
            self.base_config.risk.stop_loss_pct
            if self.base_config.risk.stop_loss_pct is not None
            else self.paper_config.default_stop_loss_pct
        )
        take_profit_pct = (
            self.base_config.risk.take_profit_pct
            if self.base_config.risk.take_profit_pct is not None
            else self.paper_config.default_take_profit_pct
        )
        trailing_stop_pct = (
            self.base_config.risk.trailing_stop_pct
            if self.base_config.risk.trailing_stop_pct is not None
            else self.paper_config.default_trailing_stop_pct
        )

        if signal == Signal.BUY:
            if open_position is not None:
                state.add_journal(
                    timestamp=timestamp,
                    symbol=symbol,
                    event_type="no_trade",
                    message="BUY signal ignored because a paper position is already open",
                    strategy_name=strategy_name,
                )
                return 0
            if session_order_count >= self.paper_config.max_orders_per_session:
                state.add_journal(
                    timestamp=timestamp,
                    symbol=symbol,
                    event_type="no_trade",
                    message="Session max order limit reached",
                    strategy_name=strategy_name,
                )
                return 0

            risk_decision = self.risk_manager.check_entry(
                portfolio_equity=self._current_equity(state),
                current_drawdown_pct=self._current_drawdown(state),
                open_positions_count=state.open_positions_count,
                deployed_capital=self._deployed_capital(state),
                regime_label=selection["regime_label"],
            )
            if not risk_decision.allowed:
                state.add_journal(
                    timestamp=timestamp,
                    symbol=symbol,
                    event_type="risk_rejection",
                    message=risk_decision.blocked_reason,
                    strategy_name=strategy_name,
                    metadata={
                        "regime_label": selection["regime_label"],
                        "effective_max_positions": risk_decision.effective_max_positions,
                        "effective_max_exposure_pct": risk_decision.effective_max_exposure_pct,
                    },
                )
                return 0

            slot_count = max(1, risk_decision.effective_max_positions)
            slot_capital = min(state.cash, self._current_equity(state) / slot_count)
            quantity = self.risk_manager.compute_position_size(
                capital=slot_capital,
                price=current_close,
                portfolio_equity=self._current_equity(state),
                stop_loss_pct=stop_loss_pct,
            )
            if quantity <= 0:
                state.add_journal(
                    timestamp=timestamp,
                    symbol=symbol,
                    event_type="no_trade",
                    message="Computed position size was zero",
                    strategy_name=strategy_name,
                )
                return 0

            order = PaperOrder(
                order_id=self._next_order_id(state),
                symbol=symbol,
                strategy_name=strategy_name,
                side=PaperOrderSide.BUY,
                quantity=quantity,
                signal_timestamp=timestamp,
                signal_price=current_close,
                fill_mode=self.paper_config.fill_mode,
                stop_loss=(current_close * (1.0 - stop_loss_pct) if stop_loss_pct else None),
                take_profit=(current_close * (1.0 + take_profit_pct) if take_profit_pct else None),
                trailing_stop_pct=trailing_stop_pct,
                regime_label=selection["regime_label"],
                reason="strategy_buy_signal",
                metadata={"signal": signal.value, "selection_reason": selection["reason"]},
            )
            state.orders.append(order)
            state.add_journal(
                timestamp=timestamp,
                symbol=symbol,
                event_type="order_created",
                message=f"Created BUY order {order.order_id}",
                strategy_name=strategy_name,
                metadata={"fill_mode": order.fill_mode},
            )
            if not self.paper_config.use_next_bar_fill:
                self._execute_order(
                    order=order,
                    timestamp=timestamp,
                    raw_fill_price=current_close,
                    state=state,
                    fill_reason="same_bar_close",
                )
            return 1

        if signal in {Signal.EXIT, Signal.SELL}:
            if open_position is None:
                state.add_journal(
                    timestamp=timestamp,
                    symbol=symbol,
                    event_type="no_trade",
                    message="Exit signal ignored because no paper position is open",
                    strategy_name=strategy_name,
                )
                return 0

            order = PaperOrder(
                order_id=self._next_order_id(state),
                symbol=symbol,
                strategy_name=strategy_name,
                side=PaperOrderSide.SELL,
                quantity=open_position.quantity,
                signal_timestamp=timestamp,
                signal_price=current_close,
                fill_mode=self.paper_config.fill_mode,
                regime_label=selection["regime_label"],
                reason="strategy_exit_signal",
                metadata={"signal": signal.value, "selection_reason": selection["reason"]},
            )
            state.orders.append(order)
            state.add_journal(
                timestamp=timestamp,
                symbol=symbol,
                event_type="order_created",
                message=f"Created SELL order {order.order_id}",
                strategy_name=strategy_name,
                metadata={"fill_mode": order.fill_mode},
            )
            if not self.paper_config.use_next_bar_fill:
                self._execute_order(
                    order=order,
                    timestamp=timestamp,
                    raw_fill_price=current_close,
                    state=state,
                    fill_reason="same_bar_close",
                )
            return 1

        return 0

    def _select_strategy(self, symbol: str, data_slice: pd.DataFrame) -> dict[str, Any]:
        fallback = self._fallback_strategy_name(self.strategy_registry)
        if self.regime_policy is None:
            return {
                "strategy_name": fallback,
                "regime_label": "unknown",
                "should_trade": True,
                "reason": "No regime policy provided; using fallback strategy",
            }

        regime_label = "unknown"
        try:
            snapshot = self.regime_engine.detect(data_slice, symbol=symbol)
            regime_label = snapshot.composite_regime.value
        except Exception:
            regime_label = "unknown"

        decision = select_for_regime(
            regime_label=regime_label,
            available_strategies=list(self.strategy_registry.keys()),
            policy=self.regime_policy,
        )

        if not decision.should_trade:
            return {
                "strategy_name": fallback,
                "regime_label": regime_label,
                "should_trade": False,
                "reason": decision.explanation,
            }

        strategy_name = decision.preferred_strategy or fallback
        if strategy_name not in self.strategy_registry:
            strategy_name = fallback
        return {
            "strategy_name": strategy_name,
            "regime_label": regime_label,
            "should_trade": True,
            "reason": decision.explanation,
        }

    def _fill_pending_orders(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        current_bar: pd.Series,
        state: PaperPortfolioState,
    ) -> None:
        for order in list(state.orders):
            if order.symbol != symbol or order.status != PaperOrderStatus.PENDING:
                continue
            if order.fill_mode != "next_bar_open":
                continue
            if pd.Timestamp(timestamp) <= order.signal_timestamp:
                continue
            self._execute_order(
                order=order,
                timestamp=timestamp,
                raw_fill_price=float(current_bar["open"]),
                state=state,
                fill_reason="next_bar_open",
            )

    def _execute_order(
        self,
        order: PaperOrder,
        timestamp: pd.Timestamp,
        raw_fill_price: float,
        state: PaperPortfolioState,
        fill_reason: str,
    ) -> None:
        trade_cost = self.cost_model.compute(
            price=float(raw_fill_price),
            quantity=order.quantity,
            side=order.side.value,
        )
        fill = PaperFill(
            fill_id=self._next_fill_id(state),
            order_id=order.order_id,
            symbol=order.symbol,
            strategy_name=order.strategy_name,
            side=order.side,
            timestamp=timestamp,
            quantity=order.quantity,
            raw_price=float(raw_fill_price),
            fill_price=trade_cost.fill_price,
            fees=trade_cost.commission,
            slippage_cost=trade_cost.slippage_cost,
            total_cost=trade_cost.total_cost,
            fill_mode=order.fill_mode,
            metadata={"fill_reason": fill_reason},
        )

        if order.side == PaperOrderSide.BUY:
            cash_needed = fill.fill_price * fill.quantity + fill.total_cost
            if cash_needed > state.cash + 1e-9:
                order.status = PaperOrderStatus.REJECTED
                order.reason = "insufficient_cash_for_paper_fill"
                state.add_journal(
                    timestamp=timestamp,
                    symbol=order.symbol,
                    event_type="order_rejected",
                    message="BUY order rejected because cash was insufficient at fill time",
                    strategy_name=order.strategy_name,
                    metadata={"cash_needed": cash_needed, "cash_available": state.cash},
                )
                return

            state.cash -= cash_needed
            position = PaperPosition(
                position_id=self._next_position_id(state),
                symbol=order.symbol,
                strategy_name=order.strategy_name,
                entry_order_id=order.order_id,
                entry_timestamp=timestamp,
                entry_price=fill.fill_price,
                quantity=fill.quantity,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                trailing_stop_pct=order.trailing_stop_pct,
                entry_fees=fill.total_cost,
                last_price=fill.fill_price,
                last_timestamp=timestamp,
                metadata={"regime_label": order.regime_label},
            )
            state.open_positions.append(position)
            state.add_journal(
                timestamp=timestamp,
                symbol=order.symbol,
                event_type="position_opened",
                message=f"Opened paper position {position.position_id}",
                strategy_name=order.strategy_name,
                metadata={"fill_price": fill.fill_price},
            )
        else:
            position = state.get_open_position(order.symbol)
            if position is None:
                order.status = PaperOrderStatus.REJECTED
                order.reason = "no_open_position_to_close"
                state.add_journal(
                    timestamp=timestamp,
                    symbol=order.symbol,
                    event_type="order_rejected",
                    message="SELL order rejected because no open paper position existed",
                    strategy_name=order.strategy_name,
                )
                return

            proceeds = fill.fill_price * fill.quantity - fill.total_cost
            state.cash += proceeds
            position.close(
                exit_order_id=order.order_id,
                exit_timestamp=timestamp,
                exit_price=fill.fill_price,
                exit_fees=fill.total_cost,
                exit_reason=order.reason or fill_reason,
            )
            state.realized_pnl += position.realized_pnl
            state.open_positions = [
                existing
                for existing in state.open_positions
                if existing.position_id != position.position_id
            ]
            state.closed_positions.append(position)
            state.add_journal(
                timestamp=timestamp,
                symbol=order.symbol,
                event_type="position_closed",
                message=f"Closed paper position {position.position_id}",
                strategy_name=order.strategy_name,
                metadata={"fill_price": fill.fill_price, "realized_pnl": position.realized_pnl},
            )

        order.status = PaperOrderStatus.FILLED
        order.fill_timestamp = pd.Timestamp(timestamp)
        order.fill_price = fill.fill_price
        order.fees = fill.total_cost
        order.slippage_cost = fill.slippage_cost
        state.fills.append(fill)

    def _process_protective_exits(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        current_bar: pd.Series,
        state: PaperPortfolioState,
    ) -> None:
        position = state.get_open_position(symbol)
        if position is None or state.has_pending_order(symbol, side=PaperOrderSide.SELL):
            return

        position.update_market_price(float(current_bar["high"]), pd.Timestamp(timestamp))

        exit_price: Optional[float] = None
        exit_reason = ""
        current_open = float(current_bar["open"])
        current_low = float(current_bar["low"])
        current_high = float(current_bar["high"])

        if position.stop_loss is not None:
            if current_open <= position.stop_loss:
                exit_price = current_open
                exit_reason = "stop_loss_gap"
            elif current_low <= position.stop_loss:
                exit_price = float(position.stop_loss)
                exit_reason = "stop_loss"

        if exit_price is None and position.take_profit is not None:
            if current_open >= position.take_profit:
                exit_price = current_open
                exit_reason = "take_profit_gap"
            elif current_high >= position.take_profit:
                exit_price = float(position.take_profit)
                exit_reason = "take_profit"

        if exit_price is None:
            return

        order = PaperOrder(
            order_id=self._next_order_id(state),
            symbol=symbol,
            strategy_name=position.strategy_name,
            side=PaperOrderSide.SELL,
            quantity=position.quantity,
            signal_timestamp=timestamp,
            signal_price=exit_price,
            fill_mode="protective_exit",
            reason=exit_reason,
        )
        state.orders.append(order)
        self._execute_order(
            order=order,
            timestamp=timestamp,
            raw_fill_price=exit_price,
            state=state,
            fill_reason=exit_reason,
        )

    def _record_pnl_snapshot(self, timestamp: pd.Timestamp, state: PaperPortfolioState) -> None:
        market_value = 0.0
        unrealized = 0.0
        for position in state.open_positions:
            price = state.last_prices.get(
                position.symbol,
                float(position.last_price or position.entry_price),
            )
            position.update_market_price(price, timestamp)
            market_value += position.current_value(price)
            unrealized += position.unrealized_pnl(price)

        state.unrealized_pnl = unrealized
        equity = state.cash + market_value
        state.equity_peak = max(state.equity_peak, equity)
        drawdown_pct = 0.0
        if state.equity_peak > 0:
            drawdown_pct = (state.equity_peak - equity) / state.equity_peak

        snapshot = PaperPnLSnapshot(
            timestamp=timestamp,
            cash=state.cash,
            market_value=market_value,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=unrealized,
            equity=equity,
            drawdown_pct=drawdown_pct,
            open_positions=len(state.open_positions),
            pending_orders=state.pending_orders_count,
        )
        state.pnl_history.append(snapshot)
        state.updated_at = pd.Timestamp.now(tz="UTC")

    def _close_all_positions_at_end(
        self,
        timestamp: pd.Timestamp,
        frames: dict[str, pd.DataFrame],
        state: PaperPortfolioState,
    ) -> None:
        for position in list(state.open_positions):
            if position.symbol not in frames:
                continue
            end_bar = frames[position.symbol].iloc[-1]
            order = PaperOrder(
                order_id=self._next_order_id(state),
                symbol=position.symbol,
                strategy_name=position.strategy_name,
                side=PaperOrderSide.SELL,
                quantity=position.quantity,
                signal_timestamp=timestamp,
                signal_price=float(end_bar["close"]),
                fill_mode="session_end",
                reason="session_end_close",
            )
            state.orders.append(order)
            self._execute_order(
                order=order,
                timestamp=timestamp,
                raw_fill_price=float(end_bar["close"]),
                state=state,
                fill_reason="session_end_close",
            )

    @staticmethod
    def _current_equity(state: PaperPortfolioState) -> float:
        market_value = 0.0
        for position in state.open_positions:
            price = state.last_prices.get(
                position.symbol,
                float(position.last_price or position.entry_price),
            )
            market_value += position.current_value(price)
        return float(state.cash + market_value)

    @staticmethod
    def _deployed_capital(state: PaperPortfolioState) -> float:
        deployed = 0.0
        for position in state.open_positions:
            price = state.last_prices.get(
                position.symbol,
                float(position.last_price or position.entry_price),
            )
            deployed += position.current_value(price)
        return float(deployed)

    @staticmethod
    def _current_drawdown(state: PaperPortfolioState) -> float:
        if not state.pnl_history:
            return 0.0
        equity_series = pd.Series([snap.equity for snap in state.pnl_history], dtype=float)
        current_dd, _ = PortfolioRiskManager.compute_drawdown(equity_series)
        return current_dd

    @staticmethod
    def _next_order_id(state: PaperPortfolioState) -> str:
        return f"PO-{len(state.orders) + 1:05d}"

    @staticmethod
    def _next_fill_id(state: PaperPortfolioState) -> str:
        return f"PF-{len(state.fills) + 1:05d}"

    @staticmethod
    def _next_position_id(state: PaperPortfolioState) -> str:
        active_count = len(state.open_positions) + len(state.closed_positions) + 1
        return f"PP-{active_count:05d}"
