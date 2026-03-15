"""
Persistence helpers for paper-trading state and session artifacts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.paper_trading.models import (
    PaperFill,
    PaperJournalEntry,
    PaperOrder,
    PaperOrderSide,
    PaperOrderStatus,
    PaperPnLSnapshot,
    PaperPortfolioState,
    PaperPosition,
    PaperPositionStatus,
    PaperTradingResult,
)


@dataclass
class PaperStateStore:
    state_file: str | Path = Path("output") / "paper_trading" / "paper_state.json"

    def load(self, default_initial_capital: float = 100_000.0) -> PaperPortfolioState:
        path = Path(self.state_file)
        if not path.exists():
            return PaperPortfolioState(
                initial_capital=float(default_initial_capital),
                cash=float(default_initial_capital),
            )

        raw = json.loads(path.read_text(encoding="utf-8"))
        return self._state_from_dict(raw)

    def save(self, state: PaperPortfolioState, path: str | Path | None = None) -> Path:
        target = Path(path or self.state_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return target

    def export_session(
        self,
        result: PaperTradingResult,
        output_dir: str | Path,
        state_path: str | Path | None = None,
    ) -> dict[str, Path]:
        if result.state is None:
            raise ValueError("PaperTradingResult.state is required for export")

        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)

        exports: dict[str, Path] = {}
        exports["paper_orders"] = self._write_dataframe(
            self.orders_dataframe(result.state),
            root / "paper_orders.csv",
        )
        exports["paper_positions"] = self._write_dataframe(
            self.positions_dataframe(result.state),
            root / "paper_positions.csv",
        )
        exports["paper_pnl"] = self._write_dataframe(
            self.pnl_dataframe(result.state),
            root / "paper_pnl.csv",
        )
        exports["paper_journal"] = self._write_dataframe(
            self.journal_dataframe(result.state),
            root / "paper_journal.csv",
        )
        exports["paper_state"] = self.save(
            result.state,
            path=state_path or (root / "paper_state.json"),
        )
        exports["paper_session_summary"] = self.write_summary(
            result,
            root / "paper_session_summary.md",
        )
        return exports

    @staticmethod
    def orders_dataframe(state: PaperPortfolioState) -> pd.DataFrame:
        return pd.DataFrame([row.to_dict() for row in state.orders])

    @staticmethod
    def positions_dataframe(state: PaperPortfolioState) -> pd.DataFrame:
        rows = [row.to_dict() for row in state.open_positions]
        rows.extend(row.to_dict() for row in state.closed_positions)
        return pd.DataFrame(rows)

    @staticmethod
    def pnl_dataframe(state: PaperPortfolioState) -> pd.DataFrame:
        return pd.DataFrame([row.to_dict() for row in state.pnl_history])

    @staticmethod
    def journal_dataframe(state: PaperPortfolioState) -> pd.DataFrame:
        return pd.DataFrame([row.to_dict() for row in state.journal])

    def write_summary(self, result: PaperTradingResult, path: str | Path) -> Path:
        if result.state is None:
            raise ValueError("PaperTradingResult.state is required for summary generation")

        state = result.state
        lines = [
            "# Paper Trading Session Summary",
            "",
            "## Run Metadata",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Started | {result.started_at.isoformat()} |",
            f"| Completed | {result.completed_at.isoformat() if result.completed_at is not None else 'N/A'} |",
            f"| Paper enabled | {result.enabled} |",
            f"| Symbols evaluated | {len(result.symbols_evaluated)} |",
            f"| Orders created | {len(state.orders)} |",
            f"| Fills simulated | {len(state.fills)} |",
            f"| Open positions | {len(state.open_positions)} |",
            f"| Closed positions | {len(state.closed_positions)} |",
            f"| Realized PnL | {state.realized_pnl:,.2f} |",
            f"| Unrealized PnL | {state.unrealized_pnl:,.2f} |",
            "",
            "---",
            "",
            "## Strategies Selected",
            "",
        ]
        if result.strategies_selected:
            lines.extend(
                f"- `{symbol}` -> `{strategy}`"
                for symbol, strategy in sorted(result.strategies_selected.items())
            )
        else:
            lines.append("- No strategy selections were recorded.")

        lines += [
            "",
            "## Risk Rejections",
            "",
        ]
        risk_entries = [entry for entry in state.journal if entry.event_type == "risk_rejection"]
        if risk_entries:
            lines.extend(
                f"- {entry.timestamp.isoformat()} `{entry.symbol}`: {entry.message}"
                for entry in risk_entries
            )
        else:
            lines.append("- None.")

        lines += [
            "",
            "## No-Trade Decisions",
            "",
        ]
        no_trade_entries = [entry for entry in state.journal if entry.event_type == "no_trade"]
        if no_trade_entries:
            lines.extend(
                f"- {entry.timestamp.isoformat()} `{entry.symbol}`: {entry.message}"
                for entry in no_trade_entries
            )
        else:
            lines.append("- None.")

        lines += [
            "",
            "## Open Positions",
            "",
        ]
        if state.open_positions:
            for pos in state.open_positions:
                lines.append(
                    f"- `{pos.symbol}` `{pos.strategy_name}` qty={pos.quantity:.4f} "
                    f"entry={pos.entry_price:.2f} last={float(pos.last_price or pos.entry_price):.2f}"
                )
        else:
            lines.append("- None.")

        lines += [
            "",
            "## Closed Positions",
            "",
        ]
        if state.closed_positions:
            for pos in state.closed_positions:
                lines.append(
                    f"- `{pos.symbol}` `{pos.strategy_name}` pnl={pos.realized_pnl:,.2f} "
                    f"exit_reason={pos.exit_reason or 'strategy_exit'}"
                )
        else:
            lines.append("- None.")

        lines += [
            "",
            "## Notes",
            "",
            "- Paper-trading only. No live broker orders are sent by this workflow.",
            "- Orders and fills are simulated using the configured fill mode and cost model.",
        ]

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    @staticmethod
    def _write_dataframe(df: pd.DataFrame, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return path

    @staticmethod
    def _state_from_dict(data: dict[str, Any]) -> PaperPortfolioState:
        state = PaperPortfolioState(
            initial_capital=float(data.get("initial_capital", 100_000.0)),
            cash=float(data.get("cash", data.get("initial_capital", 100_000.0))),
            created_at=(
                pd.Timestamp(data.get("created_at"))
                if data.get("created_at")
                else pd.Timestamp.now(tz="UTC")
            ),
            updated_at=(
                pd.Timestamp(data.get("updated_at"))
                if data.get("updated_at")
                else pd.Timestamp.now(tz="UTC")
            ),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            equity_peak=float(data.get("equity_peak", data.get("initial_capital", 100_000.0))),
            last_prices={str(k): float(v) for k, v in dict(data.get("last_prices", {})).items()},
            last_timestamps={str(k): str(v) for k, v in dict(data.get("last_timestamps", {})).items()},
            warnings=list(data.get("warnings", [])),
            errors=list(data.get("errors", [])),
            metadata=dict(data.get("metadata", {})),
        )
        state.orders = [PaperStateStore._order_from_dict(row) for row in data.get("orders", [])]
        state.fills = [PaperStateStore._fill_from_dict(row) for row in data.get("fills", [])]
        state.open_positions = [
            PaperStateStore._position_from_dict(row)
            for row in data.get("open_positions", [])
        ]
        state.closed_positions = [
            PaperStateStore._position_from_dict(row)
            for row in data.get("closed_positions", [])
        ]
        state.pnl_history = [PaperStateStore._pnl_from_dict(row) for row in data.get("pnl_history", [])]
        state.journal = [PaperStateStore._journal_from_dict(row) for row in data.get("journal", [])]
        return state

    @staticmethod
    def _order_from_dict(data: dict[str, Any]) -> PaperOrder:
        return PaperOrder(
            order_id=str(data["order_id"]),
            symbol=str(data["symbol"]),
            strategy_name=str(data.get("strategy_name", "")),
            side=PaperOrderSide(str(data["side"])),
            quantity=float(data["quantity"]),
            signal_timestamp=pd.Timestamp(data["signal_timestamp"]),
            signal_price=float(data["signal_price"]),
            fill_mode=str(data.get("fill_mode", "next_bar_open")),
            status=PaperOrderStatus(str(data.get("status", PaperOrderStatus.PENDING.value))),
            reason=str(data.get("reason", "")),
            stop_loss=(float(data["stop_loss"]) if data.get("stop_loss") is not None else None),
            take_profit=(float(data["take_profit"]) if data.get("take_profit") is not None else None),
            trailing_stop_pct=(
                float(data["trailing_stop_pct"])
                if data.get("trailing_stop_pct") is not None
                else None
            ),
            regime_label=data.get("regime_label"),
            fill_timestamp=(
                pd.Timestamp(data["fill_timestamp"])
                if data.get("fill_timestamp")
                else None
            ),
            fill_price=(float(data["fill_price"]) if data.get("fill_price") is not None else None),
            fees=float(data.get("fees", 0.0)),
            slippage_cost=float(data.get("slippage_cost", 0.0)),
            metadata=dict(data.get("metadata", {})),
        )

    @staticmethod
    def _fill_from_dict(data: dict[str, Any]) -> PaperFill:
        return PaperFill(
            fill_id=str(data["fill_id"]),
            order_id=str(data["order_id"]),
            symbol=str(data["symbol"]),
            strategy_name=str(data.get("strategy_name", "")),
            side=PaperOrderSide(str(data["side"])),
            timestamp=pd.Timestamp(data["timestamp"]),
            quantity=float(data["quantity"]),
            raw_price=float(data["raw_price"]),
            fill_price=float(data["fill_price"]),
            fees=float(data.get("fees", 0.0)),
            slippage_cost=float(data.get("slippage_cost", 0.0)),
            total_cost=float(data.get("total_cost", 0.0)),
            fill_mode=str(data.get("fill_mode", "next_bar_open")),
            metadata=dict(data.get("metadata", {})),
        )

    @staticmethod
    def _position_from_dict(data: dict[str, Any]) -> PaperPosition:
        return PaperPosition(
            position_id=str(data["position_id"]),
            symbol=str(data["symbol"]),
            strategy_name=str(data.get("strategy_name", "")),
            entry_order_id=str(data.get("entry_order_id", "")),
            entry_timestamp=pd.Timestamp(data["entry_timestamp"]),
            entry_price=float(data["entry_price"]),
            quantity=float(data["quantity"]),
            status=PaperPositionStatus(str(data.get("status", PaperPositionStatus.OPEN.value))),
            stop_loss=(float(data["stop_loss"]) if data.get("stop_loss") is not None else None),
            take_profit=(float(data["take_profit"]) if data.get("take_profit") is not None else None),
            trailing_stop_pct=(
                float(data["trailing_stop_pct"])
                if data.get("trailing_stop_pct") is not None
                else None
            ),
            highest_price=(float(data["highest_price"]) if data.get("highest_price") is not None else None),
            entry_fees=float(data.get("entry_fees", 0.0)),
            exit_order_id=data.get("exit_order_id"),
            exit_timestamp=(
                pd.Timestamp(data["exit_timestamp"])
                if data.get("exit_timestamp")
                else None
            ),
            exit_price=(float(data["exit_price"]) if data.get("exit_price") is not None else None),
            exit_fees=float(data.get("exit_fees", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            realized_return_pct=float(data.get("realized_return_pct", 0.0)),
            bars_held=int(data.get("bars_held", 0)),
            last_price=(float(data["last_price"]) if data.get("last_price") is not None else None),
            last_timestamp=(
                pd.Timestamp(data["last_timestamp"])
                if data.get("last_timestamp")
                else None
            ),
            exit_reason=str(data.get("exit_reason", "")),
            metadata=dict(data.get("metadata", {})),
        )

    @staticmethod
    def _pnl_from_dict(data: dict[str, Any]) -> PaperPnLSnapshot:
        return PaperPnLSnapshot(
            timestamp=pd.Timestamp(data["timestamp"]),
            cash=float(data.get("cash", 0.0)),
            market_value=float(data.get("market_value", 0.0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            equity=float(data.get("equity", 0.0)),
            drawdown_pct=float(data.get("drawdown_pct", 0.0)),
            open_positions=int(data.get("open_positions", 0)),
            pending_orders=int(data.get("pending_orders", 0)),
        )

    @staticmethod
    def _journal_from_dict(data: dict[str, Any]) -> PaperJournalEntry:
        return PaperJournalEntry(
            timestamp=pd.Timestamp(data["timestamp"]),
            symbol=str(data.get("symbol", "")),
            event_type=str(data.get("event_type", "")),
            message=str(data.get("message", "")),
            strategy_name=str(data.get("strategy_name", "")),
            metadata=dict(data.get("metadata", {})),
        )
