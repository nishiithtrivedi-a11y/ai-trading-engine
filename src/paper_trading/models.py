"""
Core models for the paper-trading layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import pandas as pd


def _now_utc() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _ts_to_str(value: Optional[pd.Timestamp]) -> Optional[str]:
    if value is None:
        return None
    return pd.Timestamp(value).isoformat()


class PaperOrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PaperOrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaperPositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class PaperTradingConfig:
    enabled: bool = False
    paper_only: bool = True
    initial_capital: float = 100_000.0
    max_orders_per_session: int = 20
    use_next_bar_fill: bool = True
    persist_state: bool = True
    output_dir: str = "output/paper_trading"
    session_date: Optional[pd.Timestamp] = None
    default_stop_loss_pct: Optional[float] = 0.02
    default_take_profit_pct: Optional[float] = 0.04
    default_trailing_stop_pct: Optional[float] = None
    close_open_positions_at_end: bool = False

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.max_orders_per_session < 1:
            raise ValueError("max_orders_per_session must be >= 1")
        for name in (
            "default_stop_loss_pct",
            "default_take_profit_pct",
            "default_trailing_stop_pct",
        ):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive when provided")
        if self.session_date is not None:
            self.session_date = pd.Timestamp(self.session_date)

    @property
    def fill_mode(self) -> str:
        return "next_bar_open" if self.use_next_bar_fill else "current_bar_close"

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "paper_only": self.paper_only,
            "initial_capital": self.initial_capital,
            "max_orders_per_session": self.max_orders_per_session,
            "use_next_bar_fill": self.use_next_bar_fill,
            "persist_state": self.persist_state,
            "output_dir": self.output_dir,
            "session_date": _ts_to_str(self.session_date),
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "default_take_profit_pct": self.default_take_profit_pct,
            "default_trailing_stop_pct": self.default_trailing_stop_pct,
            "close_open_positions_at_end": self.close_open_positions_at_end,
        }


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    strategy_name: str
    side: PaperOrderSide
    quantity: float
    signal_timestamp: pd.Timestamp
    signal_price: float
    fill_mode: str
    status: PaperOrderStatus = PaperOrderStatus.PENDING
    reason: str = ""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    regime_label: Optional[str] = None
    fill_timestamp: Optional[pd.Timestamp] = None
    fill_price: Optional[float] = None
    fees: float = 0.0
    slippage_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        self.strategy_name = str(self.strategy_name).strip()
        self.signal_timestamp = pd.Timestamp(self.signal_timestamp)
        self.quantity = float(self.quantity)
        self.signal_price = float(self.signal_price)
        self.fees = float(self.fees)
        self.slippage_cost = float(self.slippage_cost)
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.signal_price <= 0:
            raise ValueError("signal_price must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "side": self.side.value,
            "quantity": self.quantity,
            "signal_timestamp": _ts_to_str(self.signal_timestamp),
            "signal_price": self.signal_price,
            "fill_mode": self.fill_mode,
            "status": self.status.value,
            "reason": self.reason,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_stop_pct": self.trailing_stop_pct,
            "regime_label": self.regime_label,
            "fill_timestamp": _ts_to_str(self.fill_timestamp),
            "fill_price": self.fill_price,
            "fees": self.fees,
            "slippage_cost": self.slippage_cost,
            "metadata": dict(self.metadata),
        }


@dataclass
class PaperFill:
    fill_id: str
    order_id: str
    symbol: str
    strategy_name: str
    side: PaperOrderSide
    timestamp: pd.Timestamp
    quantity: float
    raw_price: float
    fill_price: float
    fees: float
    slippage_cost: float
    total_cost: float
    fill_mode: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        self.strategy_name = str(self.strategy_name).strip()
        self.timestamp = pd.Timestamp(self.timestamp)
        self.quantity = float(self.quantity)
        self.raw_price = float(self.raw_price)
        self.fill_price = float(self.fill_price)
        self.fees = float(self.fees)
        self.slippage_cost = float(self.slippage_cost)
        self.total_cost = float(self.total_cost)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "side": self.side.value,
            "timestamp": _ts_to_str(self.timestamp),
            "quantity": self.quantity,
            "raw_price": self.raw_price,
            "fill_price": self.fill_price,
            "fees": self.fees,
            "slippage_cost": self.slippage_cost,
            "total_cost": self.total_cost,
            "fill_mode": self.fill_mode,
            "metadata": dict(self.metadata),
        }


@dataclass
class PaperPosition:
    position_id: str
    symbol: str
    strategy_name: str
    entry_order_id: str
    entry_timestamp: pd.Timestamp
    entry_price: float
    quantity: float
    status: PaperPositionStatus = PaperPositionStatus.OPEN
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    highest_price: Optional[float] = None
    entry_fees: float = 0.0
    exit_order_id: Optional[str] = None
    exit_timestamp: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_fees: float = 0.0
    realized_pnl: float = 0.0
    realized_return_pct: float = 0.0
    bars_held: int = 0
    last_price: Optional[float] = None
    last_timestamp: Optional[pd.Timestamp] = None
    exit_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        self.strategy_name = str(self.strategy_name).strip()
        self.entry_timestamp = pd.Timestamp(self.entry_timestamp)
        self.entry_price = float(self.entry_price)
        self.quantity = float(self.quantity)
        self.entry_fees = float(self.entry_fees)
        self.exit_fees = float(self.exit_fees)
        self.realized_pnl = float(self.realized_pnl)
        self.realized_return_pct = float(self.realized_return_pct)
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if self.highest_price is None:
            self.highest_price = self.entry_price
        if self.last_price is None:
            self.last_price = self.entry_price
        if self.last_timestamp is None:
            self.last_timestamp = self.entry_timestamp

    def current_value(self, current_price: Optional[float] = None) -> float:
        price = float(current_price if current_price is not None else self.last_price or 0.0)
        return price * self.quantity

    def unrealized_pnl(self, current_price: Optional[float] = None) -> float:
        price = float(current_price if current_price is not None else self.last_price or self.entry_price)
        gross = (price - self.entry_price) * self.quantity
        return gross - self.entry_fees

    def update_market_price(self, price: float, timestamp: pd.Timestamp) -> None:
        value = float(price)
        self.last_price = value
        self.last_timestamp = pd.Timestamp(timestamp)
        if self.highest_price is None or value > self.highest_price:
            self.highest_price = value
        if self.trailing_stop_pct:
            trailing_stop = (self.highest_price or value) * (1.0 - self.trailing_stop_pct)
            if self.stop_loss is None or trailing_stop > self.stop_loss:
                self.stop_loss = trailing_stop

    def close(
        self,
        exit_order_id: str,
        exit_timestamp: pd.Timestamp,
        exit_price: float,
        exit_fees: float,
        exit_reason: str,
    ) -> None:
        self.status = PaperPositionStatus.CLOSED
        self.exit_order_id = exit_order_id
        self.exit_timestamp = pd.Timestamp(exit_timestamp)
        self.exit_price = float(exit_price)
        self.exit_fees = float(exit_fees)
        self.exit_reason = exit_reason
        gross = (self.exit_price - self.entry_price) * self.quantity
        self.realized_pnl = gross - self.entry_fees - self.exit_fees
        notional = self.entry_price * self.quantity
        self.realized_return_pct = self.realized_pnl / notional if notional > 0 else 0.0
        self.last_price = self.exit_price
        self.last_timestamp = self.exit_timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "entry_order_id": self.entry_order_id,
            "entry_timestamp": _ts_to_str(self.entry_timestamp),
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "status": self.status.value,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_stop_pct": self.trailing_stop_pct,
            "highest_price": self.highest_price,
            "entry_fees": self.entry_fees,
            "exit_order_id": self.exit_order_id,
            "exit_timestamp": _ts_to_str(self.exit_timestamp),
            "exit_price": self.exit_price,
            "exit_fees": self.exit_fees,
            "realized_pnl": self.realized_pnl,
            "realized_return_pct": self.realized_return_pct,
            "bars_held": self.bars_held,
            "last_price": self.last_price,
            "last_timestamp": _ts_to_str(self.last_timestamp),
            "exit_reason": self.exit_reason,
            "metadata": dict(self.metadata),
        }


@dataclass
class PaperPnLSnapshot:
    timestamp: pd.Timestamp
    cash: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    equity: float
    drawdown_pct: float
    open_positions: int
    pending_orders: int

    def __post_init__(self) -> None:
        self.timestamp = pd.Timestamp(self.timestamp)
        self.cash = float(self.cash)
        self.market_value = float(self.market_value)
        self.realized_pnl = float(self.realized_pnl)
        self.unrealized_pnl = float(self.unrealized_pnl)
        self.equity = float(self.equity)
        self.drawdown_pct = float(self.drawdown_pct)
        self.open_positions = int(self.open_positions)
        self.pending_orders = int(self.pending_orders)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": _ts_to_str(self.timestamp),
            "cash": self.cash,
            "market_value": self.market_value,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "equity": self.equity,
            "drawdown_pct": self.drawdown_pct,
            "open_positions": self.open_positions,
            "pending_orders": self.pending_orders,
        }


@dataclass
class PaperJournalEntry:
    timestamp: pd.Timestamp
    symbol: str
    event_type: str
    message: str
    strategy_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timestamp = pd.Timestamp(self.timestamp)
        self.symbol = str(self.symbol).strip().upper()
        self.event_type = str(self.event_type).strip().lower()
        self.message = str(self.message).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": _ts_to_str(self.timestamp),
            "symbol": self.symbol,
            "event_type": self.event_type,
            "message": self.message,
            "strategy_name": self.strategy_name,
            "metadata": dict(self.metadata),
        }


@dataclass
class PaperPortfolioState:
    initial_capital: float
    cash: float
    created_at: pd.Timestamp = field(default_factory=_now_utc)
    updated_at: pd.Timestamp = field(default_factory=_now_utc)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    equity_peak: float = 0.0
    open_positions: list[PaperPosition] = field(default_factory=list)
    closed_positions: list[PaperPosition] = field(default_factory=list)
    orders: list[PaperOrder] = field(default_factory=list)
    fills: list[PaperFill] = field(default_factory=list)
    pnl_history: list[PaperPnLSnapshot] = field(default_factory=list)
    journal: list[PaperJournalEntry] = field(default_factory=list)
    last_prices: dict[str, float] = field(default_factory=dict)
    last_timestamps: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.initial_capital = float(self.initial_capital)
        self.cash = float(self.cash)
        self.realized_pnl = float(self.realized_pnl)
        self.unrealized_pnl = float(self.unrealized_pnl)
        self.equity_peak = float(self.equity_peak or self.initial_capital)
        self.created_at = pd.Timestamp(self.created_at)
        self.updated_at = pd.Timestamp(self.updated_at)
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")

    @property
    def market_value(self) -> float:
        return float(sum(pos.current_value() for pos in self.open_positions))

    @property
    def equity(self) -> float:
        return float(self.cash + self.market_value)

    @property
    def open_positions_count(self) -> int:
        return len(self.open_positions)

    @property
    def pending_orders_count(self) -> int:
        return len([order for order in self.orders if order.status == PaperOrderStatus.PENDING])

    def get_open_position(self, symbol: str) -> Optional[PaperPosition]:
        clean = str(symbol).strip().upper()
        for position in self.open_positions:
            if position.symbol == clean and position.status == PaperPositionStatus.OPEN:
                return position
        return None

    def has_pending_order(
        self,
        symbol: str,
        side: Optional[PaperOrderSide] = None,
    ) -> bool:
        clean = str(symbol).strip().upper()
        for order in self.orders:
            if order.symbol != clean or order.status != PaperOrderStatus.PENDING:
                continue
            if side is None or order.side == side:
                return True
        return False

    def add_journal(
        self,
        timestamp: pd.Timestamp,
        symbol: str,
        event_type: str,
        message: str,
        strategy_name: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        self.journal.append(
            PaperJournalEntry(
                timestamp=timestamp,
                symbol=symbol,
                event_type=event_type,
                message=message,
                strategy_name=strategy_name,
                metadata=dict(metadata or {}),
            )
        )
        self.updated_at = _now_utc()

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "created_at": _ts_to_str(self.created_at),
            "updated_at": _ts_to_str(self.updated_at),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "equity_peak": self.equity_peak,
            "open_positions": [pos.to_dict() for pos in self.open_positions],
            "closed_positions": [pos.to_dict() for pos in self.closed_positions],
            "orders": [order.to_dict() for order in self.orders],
            "fills": [fill.to_dict() for fill in self.fills],
            "pnl_history": [snap.to_dict() for snap in self.pnl_history],
            "journal": [entry.to_dict() for entry in self.journal],
            "last_prices": dict(self.last_prices),
            "last_timestamps": dict(self.last_timestamps),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


@dataclass
class PaperTradingResult:
    started_at: pd.Timestamp = field(default_factory=_now_utc)
    completed_at: Optional[pd.Timestamp] = None
    enabled: bool = False
    state: Optional[PaperPortfolioState] = None
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    symbols_evaluated: list[str] = field(default_factory=list)
    strategies_selected: dict[str, str] = field(default_factory=dict)
    regime_labels: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exports: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": _ts_to_str(self.started_at),
            "completed_at": _ts_to_str(self.completed_at),
            "enabled": self.enabled,
            "config_snapshot": dict(self.config_snapshot),
            "summary": {
                "symbols_evaluated": len(self.symbols_evaluated),
                "orders_total": len(self.state.orders) if self.state is not None else 0,
                "fills_total": len(self.state.fills) if self.state is not None else 0,
                "open_positions": len(self.state.open_positions) if self.state is not None else 0,
                "closed_positions": len(self.state.closed_positions) if self.state is not None else 0,
                "warnings_total": len(self.warnings),
                "errors_total": len(self.errors),
            },
            "symbols_evaluated": list(self.symbols_evaluated),
            "strategies_selected": dict(self.strategies_selected),
            "regime_labels": dict(self.regime_labels),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "exports": dict(self.exports),
            "metadata": dict(self.metadata),
            "state": self.state.to_dict() if self.state is not None else None,
        }
