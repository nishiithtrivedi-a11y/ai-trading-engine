"""
Execution realism package -- cost modelling and fill simulation.

Provides tools to convert *gross* backtest P&L into realistic *net* P&L by
applying commission and slippage costs to existing trade logs.

MODULES
-------
  cost_model  : CostConfig, TradeCost, CostModel
  fill_model  : FillConfig, FillResult, FillModel

PUBLIC API (this module)
------------------------
  ExecutionRealism comparison and reporting:
    GrossNetRecord              Per-symbol/strategy gross vs net comparison.
    ExecutionCostAnalyzer       Apply costs to a trade log DataFrame.
    generate_execution_report() Produce research/execution_realism.md.

TYPICAL USAGE
-------------

  from src.execution import (
      CostConfig, CostModel, FillConfig, FillModel,
      ExecutionCostAnalyzer, generate_execution_report,
  )

  # 1. Configure costs
  cost_cfg = CostConfig(commission_bps=10, slippage_bps=5)

  # 2. Analyze an existing trade log (from PortfolioBacktester.run())
  analyzer = ExecutionCostAnalyzer(cost_config=cost_cfg)
  records  = analyzer.analyze_trade_log(trade_log_df, initial_capital=100_000)

  # 3. Generate report
  generate_execution_report(records, cost_cfg, output_path="research/execution_realism.md")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .cost_model import CostConfig, CostModel, TradeCost
from .fill_model import FillConfig, FillModel, FillResult

from src.utils.logger import setup_logger

logger = setup_logger("execution")

__all__ = [
    # Cost model
    "CostConfig",
    "CostModel",
    "TradeCost",
    # Fill model
    "FillConfig",
    "FillModel",
    "FillResult",
    # High-level analysis
    "GrossNetRecord",
    "ExecutionCostAnalyzer",
    "generate_execution_report",
]


# ---------------------------------------------------------------------------
# Per-group result record
# ---------------------------------------------------------------------------

@dataclass
class GrossNetRecord:
    """Gross vs net P&L comparison for one (symbol, strategy) group.

    Attributes
    ----------
    symbol : str
        Instrument name.
    strategy : str
        Strategy short name.
    num_trades : int
        Number of round-trip trades analysed.
    gross_pnl : float
        Summed gross P&L from the trade log (before any execution costs).
    total_cost : float
        Total all-in execution cost (commission + slippage) for all trades.
    net_pnl : float
        ``gross_pnl - total_cost``
    initial_capital : float
        The capital base used to compute return percentages.
    gross_return_pct : float
        ``gross_pnl / initial_capital``
    net_return_pct : float
        ``net_pnl / initial_capital``
    cost_drag_pct : float
        ``gross_return_pct - net_return_pct`` (always >= 0).
    avg_cost_per_trade : float
        ``total_cost / num_trades`` (0 when no trades).
    """

    symbol: str
    strategy: str
    num_trades: int
    gross_pnl: float
    total_cost: float
    net_pnl: float
    initial_capital: float
    gross_return_pct: float
    net_return_pct: float
    cost_drag_pct: float
    avg_cost_per_trade: float


# ---------------------------------------------------------------------------
# ExecutionCostAnalyzer
# ---------------------------------------------------------------------------

class ExecutionCostAnalyzer:
    """Apply execution costs to an existing trade log to compute net P&L.

    Parameters
    ----------
    cost_config : CostConfig
        Commission and slippage parameters.
    fill_config : FillConfig
        Fill mode (next-bar-open or current-bar-close).
    """

    def __init__(
        self,
        cost_config: Optional[CostConfig] = None,
        fill_config: Optional[FillConfig] = None,
    ) -> None:
        self.cost_config = cost_config or CostConfig()
        self.fill_config = fill_config or FillConfig()
        self._cost_model = CostModel(self.cost_config)

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    def analyze_trade_log(
        self,
        trade_log: pd.DataFrame,
        initial_capital: float = 100_000.0,
    ) -> list[GrossNetRecord]:
        """Apply execution costs to each trade in ``trade_log``.

        Expects a trade log in the format produced by ``PortfolioBacktester``
        or ``MultiAssetBacktester``::

          Required columns: entry_price, exit_price, quantity, gross_pnl
          Optional columns: symbol, strategy

        Costs are applied as a **round-trip** cost per trade:
          - Entry side : buy cost (commission + slippage on entry_price)
          - Exit side  : sell cost (commission + slippage on exit_price)

        Parameters
        ----------
        trade_log : pd.DataFrame
            Trade log from a completed backtest.
        initial_capital : float
            Capital base for return percentage calculation.

        Returns
        -------
        list[GrossNetRecord]
            One record per (symbol, strategy) group; sorted by gross_pnl desc.
        """
        if trade_log is None or trade_log.empty:
            logger.info("ExecutionCostAnalyzer: trade_log is empty; no records to analyze.")
            return []

        required = {"entry_price", "exit_price", "quantity", "gross_pnl"}
        missing = required - set(trade_log.columns)
        if missing:
            logger.warning(f"ExecutionCostAnalyzer: missing columns {missing}; returning empty.")
            return []

        # Add cost columns to a working copy
        df = self._apply_costs_to_trades(trade_log)

        # Group by (symbol, strategy) if available; else treat as single group
        group_cols: list[str] = []
        if "symbol"   in df.columns: group_cols.append("symbol")
        if "strategy" in df.columns: group_cols.append("strategy")

        records: list[GrossNetRecord] = []
        if group_cols:
            for keys, grp in df.groupby(group_cols):
                if isinstance(keys, str):
                    keys = (keys,)
                keys_map = dict(zip(group_cols, keys))
                rec = self._build_record(
                    grp,
                    symbol=keys_map.get("symbol", "ALL"),
                    strategy=keys_map.get("strategy", "ALL"),
                    initial_capital=initial_capital,
                )
                records.append(rec)
        else:
            rec = self._build_record(df, symbol="ALL", strategy="ALL",
                                     initial_capital=initial_capital)
            records.append(rec)

        records.sort(key=lambda r: r.gross_pnl, reverse=True)
        return records

    def apply_costs_to_trade_log(self, trade_log: pd.DataFrame) -> pd.DataFrame:
        """Return the trade log with added cost columns (non-destructive).

        Adds the following columns:
          entry_cost    : total cost of the entry leg
          exit_cost     : total cost of the exit leg
          round_trip_cost : entry_cost + exit_cost
          net_pnl       : gross_pnl - round_trip_cost
          fill_mode     : description of fill mode active

        Parameters
        ----------
        trade_log : pd.DataFrame
            Existing trade log.

        Returns
        -------
        pd.DataFrame
            New DataFrame with extra columns; original is not modified.
        """
        if trade_log is None or trade_log.empty:
            return pd.DataFrame()
        return self._apply_costs_to_trades(trade_log)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_costs_to_trades(self, trade_log: pd.DataFrame) -> pd.DataFrame:
        """Add cost columns to trade_log; returns a copy."""
        df = trade_log.copy()
        fill_mode_str = "next_bar_open" if self.fill_config.use_next_bar_open else "current_bar_close"

        entry_costs:  list[float] = []
        exit_costs:   list[float] = []
        round_trips:  list[float] = []
        net_pnls:     list[float] = []

        for _, row in df.iterrows():
            entry_price = float(row.get("entry_price") or 0.0)
            exit_price  = float(row.get("exit_price")  or 0.0)
            quantity    = abs(float(row.get("quantity")  or 0.0))
            gross_pnl   = float(row.get("gross_pnl")   or 0.0)

            ec = self._cost_model.compute(entry_price, quantity, side="buy").total_cost
            xc = self._cost_model.compute(exit_price,  quantity, side="sell").total_cost
            rt = ec + xc

            entry_costs.append(ec)
            exit_costs.append(xc)
            round_trips.append(rt)
            net_pnls.append(gross_pnl - rt)

        df["entry_cost"]       = entry_costs
        df["exit_cost"]        = exit_costs
        df["round_trip_cost"]  = round_trips
        df["net_pnl"]          = net_pnls
        df["fill_mode"]        = fill_mode_str
        return df

    def _build_record(
        self,
        grp: pd.DataFrame,
        symbol: str,
        strategy: str,
        initial_capital: float,
    ) -> GrossNetRecord:
        n_trades    = len(grp)
        gross_pnl   = float(grp["gross_pnl"].sum())
        total_cost  = float(grp["round_trip_cost"].sum()) if "round_trip_cost" in grp.columns else 0.0
        net_pnl     = gross_pnl - total_cost
        cap         = initial_capital if initial_capital > 0 else 1.0
        gross_ret   = gross_pnl / cap
        net_ret     = net_pnl   / cap
        drag        = max(0.0, gross_ret - net_ret)
        avg_cost    = total_cost / n_trades if n_trades > 0 else 0.0

        return GrossNetRecord(
            symbol=symbol,
            strategy=strategy,
            num_trades=n_trades,
            gross_pnl=gross_pnl,
            total_cost=total_cost,
            net_pnl=net_pnl,
            initial_capital=cap,
            gross_return_pct=gross_ret,
            net_return_pct=net_ret,
            cost_drag_pct=drag,
            avg_cost_per_trade=avg_cost,
        )


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def generate_execution_report(
    records: list[GrossNetRecord],
    cost_config: Optional[CostConfig] = None,
    fill_config: Optional[FillConfig] = None,
    output_path: Optional[str | Path] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Generate and save the execution realism markdown report.

    Parameters
    ----------
    records : list[GrossNetRecord]
        Output of :meth:`ExecutionCostAnalyzer.analyze_trade_log`.
    cost_config : CostConfig, optional
        Cost configuration used (for display in the report).
    fill_config : FillConfig, optional
        Fill configuration used.
    output_path : str or Path, optional
        Where to write the markdown file.  Defaults to
        ``research/execution_realism.md``.
    metadata : dict, optional
        Extra context (symbols, strategies, interval, etc.).

    Returns
    -------
    str
        Full markdown content of the report.
    """
    output_path = (
        Path(output_path)
        if output_path
        else Path("research") / "execution_realism.md"
    )
    cost_config = cost_config or CostConfig()
    fill_config = fill_config or FillConfig()
    metadata    = dict(metadata) if metadata else {}

    lines = _build_execution_report_lines(records, cost_config, fill_config, metadata)
    content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Execution realism report written to {output_path}")

    return content


# ---------------------------------------------------------------------------
# Report builder (ASCII-only for Windows cp1252 compatibility)
# ---------------------------------------------------------------------------

def _pct(v: float) -> str:
    return f"{v * 100.0:.4f}%"


def _fmt(v: Any) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, int):
        return str(v)
    return str(v)


def _build_execution_report_lines(
    records: list[GrossNetRecord],
    cost_config: CostConfig,
    fill_config: FillConfig,
    metadata: dict[str, Any],
) -> list[str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        "# Execution Realism Report",
        "",
        "## Run Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
    ]
    for key, val in metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")
    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Cost configuration applied
    # ------------------------------------------------------------------
    fill_mode_str = "Next-Bar Open" if fill_config.use_next_bar_open else "Current-Bar Close"
    lines += [
        "",
        "## Cost Configuration Applied",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        f"| Commission (fixed per trade) | Rs. {cost_config.commission_per_trade:.2f} |",
        f"| Commission (bps of notional) | {cost_config.commission_bps:.1f} bps "
        f"({cost_config.commission_bps / 100:.2f}%) |",
        f"| Slippage (bps of notional) | {cost_config.slippage_bps:.1f} bps "
        f"({cost_config.slippage_bps / 100:.2f}%) |",
        f"| Fill mode | {fill_mode_str} |",
        "",
        "---",
    ]

    # ------------------------------------------------------------------
    # Summary (aggregate totals)
    # ------------------------------------------------------------------
    if records:
        total_gross  = sum(r.gross_pnl  for r in records)
        total_cost   = sum(r.total_cost for r in records)
        total_net    = sum(r.net_pnl    for r in records)
        total_trades = sum(r.num_trades for r in records)
        avg_capital  = records[0].initial_capital  # same for all records
        agg_gross_ret = total_gross / avg_capital if avg_capital > 0 else 0.0
        agg_net_ret   = total_net   / avg_capital if avg_capital > 0 else 0.0
        agg_drag      = max(0.0, agg_gross_ret - agg_net_ret)

        lines += [
            "",
            "## Portfolio-Level Gross vs Net Summary",
            "",
            "| Metric | Gross (before costs) | Net (after costs) |",
            "| --- | --- | --- |",
            f"| Total P&L | {total_gross:,.2f} | {total_net:,.2f} |",
            f"| Portfolio Return | {_pct(agg_gross_ret)} | {_pct(agg_net_ret)} |",
            f"| Total execution costs | -- | {total_cost:,.2f} |",
            f"| Cost drag on return | -- | {_pct(agg_drag)} |",
            f"| Total trades | {total_trades} | {total_trades} |",
            "",
            "---",
        ]
    else:
        lines += [
            "",
            "## Portfolio-Level Gross vs Net Summary",
            "",
            "> _No trade records to analyse._",
            "",
            "---",
        ]

    # ------------------------------------------------------------------
    # Per-group breakdown table
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Gross vs Net Breakdown by Symbol / Strategy",
        "",
        "| Symbol | Strategy | Trades | Gross P&L | Total Cost | Net P&L | "
        "Gross Return | Net Return | Cost Drag |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in records:
        lines.append(
            f"| {r.symbol} | {r.strategy} | {r.num_trades} "
            f"| {r.gross_pnl:,.2f} | {r.total_cost:,.2f} | {r.net_pnl:,.2f} "
            f"| {_pct(r.gross_return_pct)} | {_pct(r.net_return_pct)} "
            f"| {_pct(r.cost_drag_pct)} |"
        )
    if not records:
        lines.append("| _No data_ | -- | -- | -- | -- | -- | -- | -- | -- |")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Cost breakdown explanation
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Cost Component Definitions",
        "",
        "| Component | Formula |",
        "| --- | --- |",
        "| Commission (bps) | notional x commission_bps / 10000 |",
        "| Fixed commission | commission_per_trade per leg (entry + exit) |",
        "| Slippage (bps) | notional x slippage_bps / 10000 |",
        "| Round-trip cost | entry_commission + entry_slippage + exit_commission + exit_slippage |",
        "| Net P&L | gross_pnl - round_trip_cost |",
        "| Cost drag | (gross_return - net_return) as a percentage of initial capital |",
        "",
        "---",
        "",
        "## Fill Mode",
        "",
        f"> **{fill_mode_str}** fill mode is active.",
    ]
    if fill_config.use_next_bar_open:
        lines.append(
            "> Signals generated on bar T are filled at bar T+1 open price "
            "-- consistent with the ``NEXT_BAR_OPEN`` backtest execution mode."
        )
    else:
        lines.append(
            "> Signals generated on bar T are filled at bar T close price "
            "-- introduces slight look-ahead; use next-bar mode for realistic research."
        )

    lines += [
        "",
        "---",
        "",
        "## Caveats",
        "",
        "- Cost estimates are illustrative; actual brokerage costs depend on "
        "the broker, account type, regulatory charges, and market conditions.",
        "- Slippage is modelled as a fixed bps rate; real slippage varies "
        "with liquidity, order size, and market volatility.",
        "- This analysis is post-hoc: costs are applied to the original "
        "trade prices rather than re-simulating with adjusted fills.",
        "- No live trading. This output must not be used for real capital deployment.",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with "
        "`--execution-realism` enabled._",
    ]

    return lines
