"""
Multi-asset portfolio backtesting layer.

This module sits on top of the existing single-asset BacktestEngine.
It runs one backtest per symbol, allocates capital per symbol, and
aggregates equity curves / trade logs / portfolio metrics.

Important:
- This is a portfolio aggregation layer, not a fully shared broker/cash engine.
- It is intentionally built this way to preserve compatibility with the current
  single-position Portfolio and single-dataset BacktestEngine.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.strategies.base_strategy import BaseStrategy
from src.utils.config import BacktestConfig
from src.utils.logger import setup_logger

logger = setup_logger("multi_asset_backtester")


class AllocationMethod:
    EQUAL_WEIGHT = "equal_weight"
    RISK_PARITY = "risk_parity"  # placeholder only


@dataclass
class MultiAssetRunResult:
    symbol: str
    metrics: dict[str, Any]
    trade_log: pd.DataFrame
    equity_curve: pd.DataFrame
    buy_hold: dict[str, Any]


class MultiAssetBacktester:
    """
    Run one strategy across multiple symbols and aggregate results.

    Current design:
    - each symbol is backtested independently using the existing engine
    - capital is split by allocation method before each symbol run
    - resulting equity curves are combined into a portfolio equity curve

    This is the safest implementation for the current architecture because
    the core Portfolio still supports a single active position only.
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        strategy_class: type[BaseStrategy],
        symbol_to_data: dict[str, DataHandler],
        allocation_method: str = AllocationMethod.EQUAL_WEIGHT,
        output_dir: str = "output/multi_asset",
    ) -> None:
        if not symbol_to_data:
            raise ValueError("symbol_to_data cannot be empty.")

        self.base_config = base_config
        self.strategy_class = strategy_class
        self.symbol_to_data = symbol_to_data
        self.allocation_method = allocation_method
        self.output_dir = Path(output_dir)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.symbol_results: dict[str, MultiAssetRunResult] = {}
        self.portfolio_equity_curve: pd.DataFrame = pd.DataFrame()
        self.portfolio_trade_log: pd.DataFrame = pd.DataFrame()
        self.portfolio_metrics: dict[str, Any] = {}
        self.correlation_matrix: pd.DataFrame = pd.DataFrame()

    def run(self) -> dict[str, Any]:
        """
        Run the multi-asset backtest.

        Returns:
            Dictionary containing:
            - symbol_results
            - portfolio_equity_curve
            - portfolio_trade_log
            - portfolio_metrics
            - correlation_matrix
        """
        logger.info(
            f"Starting multi-asset backtest for {len(self.symbol_to_data)} symbols "
            f"using {self.strategy_class.__name__}"
        )

        allocations = self._build_allocations()

        for symbol, data_handler in self.symbol_to_data.items():
            capital = allocations[symbol]
            logger.info(f"Running {symbol} with allocated capital {capital:.2f}")

            config = self._clone_config(self.base_config)
            config.initial_capital = capital
            config.output_dir = str(self.output_dir / symbol.replace(".", "_"))

            strategy = self.strategy_class()
            engine = BacktestEngine(config, strategy)
            engine.run(data_handler)

            results = engine.get_results()

            equity_curve = results.get("equity_curve", pd.DataFrame()).copy()
            trade_log = results.get("trade_log", pd.DataFrame()).copy()

            if not equity_curve.empty:
                equity_curve = equity_curve.copy()
                equity_curve["symbol"] = symbol

            if not trade_log.empty:
                trade_log = trade_log.copy()
                trade_log["symbol"] = symbol

            self.symbol_results[symbol] = MultiAssetRunResult(
                symbol=symbol,
                metrics=results.get("metrics", {}),
                trade_log=trade_log,
                equity_curve=equity_curve,
                buy_hold=results.get("buy_hold", {}),
            )

        self.portfolio_equity_curve = self._aggregate_equity_curves()
        self.portfolio_trade_log = self._aggregate_trade_logs()
        self.portfolio_metrics = self._compute_portfolio_metrics()
        self.correlation_matrix = self._compute_correlation_matrix()

        self._export_outputs()

        logger.info("Multi-asset backtest complete")
        return {
            "symbol_results": self.symbol_results,
            "portfolio_equity_curve": self.portfolio_equity_curve,
            "portfolio_trade_log": self.portfolio_trade_log,
            "portfolio_metrics": self.portfolio_metrics,
            "correlation_matrix": self.correlation_matrix,
        }

    def print_summary(self) -> None:
        if not self.portfolio_metrics:
            print("No multi-asset results available.")
            return

        print("\n" + "=" * 100)
        print(f"MULTI-ASSET PORTFOLIO SUMMARY — {self.strategy_class.__name__}")
        print("=" * 100)

        metrics = self.portfolio_metrics
        for key in [
            "num_symbols",
            "allocation_method",
            "initial_capital",
            "final_value",
            "total_return_pct",
            "annualized_return",
            "max_drawdown_pct",
            "num_trades",
            "win_rate",
            "profit_factor",
        ]:
            if key in metrics:
                print(f"{key:>22}: {metrics[key]}")

        print("\nPer-symbol results:")
        rows = []
        for symbol, result in self.symbol_results.items():
            m = result.metrics
            rows.append(
                {
                    "symbol": symbol,
                    "final_value": m.get("final_value"),
                    "total_return_pct": m.get("total_return_pct"),
                    "sharpe_ratio": m.get("sharpe_ratio"),
                    "max_drawdown_pct": m.get("max_drawdown_pct"),
                    "num_trades": m.get("num_trades"),
                }
            )

        if rows:
            print(pd.DataFrame(rows).to_string(index=False))

        print("=" * 100 + "\n")

    def _build_allocations(self) -> dict[str, float]:
        symbols = list(self.symbol_to_data.keys())
        total_capital = float(self.base_config.initial_capital)

        if self.allocation_method == AllocationMethod.EQUAL_WEIGHT:
            per_symbol = total_capital / len(symbols)
            return {symbol: per_symbol for symbol in symbols}

        if self.allocation_method == AllocationMethod.RISK_PARITY:
            # Placeholder: equal-weight fallback for now
            logger.warning(
                "risk_parity requested but not yet implemented. "
                "Falling back to equal_weight."
            )
            per_symbol = total_capital / len(symbols)
            return {symbol: per_symbol for symbol in symbols}

        raise ValueError(f"Unknown allocation method: {self.allocation_method}")

    def _aggregate_equity_curves(self) -> pd.DataFrame:
        """
        Combine per-symbol equity curves into one portfolio equity curve.
        """
        frames = []

        for symbol, result in self.symbol_results.items():
            if result.equity_curve.empty:
                continue

            eq = result.equity_curve.copy()

            # Normalize expected column name
            if "equity" not in eq.columns:
                continue

            eq = eq[["equity"]].rename(columns={"equity": symbol})
            frames.append(eq)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, axis=1).sort_index()
        combined = combined.ffill().bfill()

        symbol_cols = list(self.symbol_results.keys())
        symbol_cols = [col for col in symbol_cols if col in combined.columns]

        combined["portfolio_equity"] = combined[symbol_cols].sum(axis=1)

        initial_capital = float(self.base_config.initial_capital)
        combined["portfolio_return"] = (
            combined["portfolio_equity"] / initial_capital - 1.0
        )

        combined["portfolio_peak"] = combined["portfolio_equity"].cummax()
        combined["portfolio_drawdown"] = (
            combined["portfolio_peak"] - combined["portfolio_equity"]
        )
        combined["portfolio_drawdown_pct"] = combined["portfolio_drawdown"] / combined[
            "portfolio_peak"
        ].replace(0, pd.NA)

        return combined

    def _aggregate_trade_logs(self) -> pd.DataFrame:
        frames = []

        for result in self.symbol_results.values():
            if not result.trade_log.empty:
                frames.append(result.trade_log)

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)

        sort_col = "exit_timestamp" if "exit_timestamp" in df.columns else None
        if sort_col is not None:
            df = df.sort_values(by=sort_col).reset_index(drop=True)

        return df

    def _compute_portfolio_metrics(self) -> dict[str, Any]:
        if self.portfolio_equity_curve.empty:
            return {}

        eq = self.portfolio_equity_curve
        initial_capital = float(self.base_config.initial_capital)
        final_value = float(eq["portfolio_equity"].iloc[-1])
        total_return_pct = final_value / initial_capital - 1.0

        num_periods = len(eq)
        trading_days_per_year = float(getattr(self.base_config, "trading_days_per_year", 252))

        if num_periods > 1:
            annualized_return = (1 + total_return_pct) ** (
                trading_days_per_year / num_periods
            ) - 1
        else:
            annualized_return = 0.0

        max_drawdown_pct = float(eq["portfolio_drawdown_pct"].max()) if "portfolio_drawdown_pct" in eq else 0.0

        trade_log = self.portfolio_trade_log
        num_trades = int(len(trade_log)) if not trade_log.empty else 0

        if not trade_log.empty and "net_pnl" in trade_log.columns:
            winners = trade_log[trade_log["net_pnl"] > 0]
            losers = trade_log[trade_log["net_pnl"] < 0]

            win_rate = len(winners) / len(trade_log) if len(trade_log) > 0 else 0.0

            gross_profit = float(winners["net_pnl"].sum()) if not winners.empty else 0.0
            gross_loss = abs(float(losers["net_pnl"].sum())) if not losers.empty else 0.0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        else:
            win_rate = 0.0
            profit_factor = 0.0

        total_fees = (
            float(trade_log["fees"].sum())
            if not trade_log.empty and "fees" in trade_log.columns
            else 0.0
        )

        return {
            "num_symbols": len(self.symbol_results),
            "allocation_method": self.allocation_method,
            "initial_capital": initial_capital,
            "final_value": final_value,
            "total_return_pct": total_return_pct,
            "annualized_return": annualized_return,
            "max_drawdown_pct": max_drawdown_pct,
            "num_trades": num_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_fees": total_fees,
        }

    def _compute_correlation_matrix(self) -> pd.DataFrame:
        """
        Correlation matrix from per-symbol equity returns.
        """
        if self.portfolio_equity_curve.empty:
            return pd.DataFrame()

        eq = self.portfolio_equity_curve.copy()

        symbol_cols = [symbol for symbol in self.symbol_results.keys() if symbol in eq.columns]
        if not symbol_cols:
            return pd.DataFrame()

        returns = eq[symbol_cols].pct_change().dropna(how="all")
        if returns.empty:
            return pd.DataFrame()

        return returns.corr()

    def _export_outputs(self) -> None:
        if not self.portfolio_equity_curve.empty:
            self.portfolio_equity_curve.to_csv(
                self.output_dir / "portfolio_equity_curve.csv"
            )

        if not self.portfolio_trade_log.empty:
            self.portfolio_trade_log.to_csv(
                self.output_dir / "portfolio_trade_log.csv",
                index=False,
            )

        if self.portfolio_metrics:
            pd.DataFrame([self.portfolio_metrics]).to_csv(
                self.output_dir / "portfolio_metrics.csv",
                index=False,
            )

        if not self.correlation_matrix.empty:
            self.correlation_matrix.to_csv(
                self.output_dir / "correlation_matrix.csv"
            )

        # Per-symbol summary
        rows = []
        for symbol, result in self.symbol_results.items():
            row = {"symbol": symbol}
            row.update(result.metrics)
            rows.append(row)

        if rows:
            pd.DataFrame(rows).to_csv(
                self.output_dir / "symbol_metrics.csv",
                index=False,
            )

    @staticmethod
    def _clone_config(config: BacktestConfig) -> BacktestConfig:
        if hasattr(config, "model_copy"):
            return config.model_copy(deep=True)
        if hasattr(config, "copy"):
            try:
                return config.copy(deep=True)
            except TypeError:
                return config.copy()
        return copy.deepcopy(config)