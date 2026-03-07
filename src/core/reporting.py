"""
Report generation for the backtesting engine.

Generates terminal output, plots, CSV exports, and JSON metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from src.core.metrics import PerformanceMetrics
from src.utils.logger import setup_logger

logger = setup_logger("reporting")


class ReportGenerator:
    """Generates backtest reports in multiple formats.

    Attributes:
        metrics: Computed performance metrics.
        equity_curve: Portfolio equity over time.
        trade_log: DataFrame of completed trades.
        buy_hold_metrics: Benchmark buy-and-hold results.
        strategy_name: Name of the strategy tested.
        output_dir: Directory for file outputs.
    """

    def __init__(
        self,
        metrics: PerformanceMetrics,
        equity_curve: pd.DataFrame,
        trade_log: pd.DataFrame,
        buy_hold_metrics: dict[str, Any],
        strategy_name: str = "Strategy",
        output_dir: str = "output",
    ) -> None:
        self.metrics = metrics
        self.equity_curve = equity_curve
        self.trade_log = trade_log
        self.buy_hold_metrics = buy_hold_metrics
        self.strategy_name = strategy_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def print_summary(self) -> None:
        """Print the performance summary to the terminal."""
        print("\n" + self.metrics.summary_string())

        # Print buy-and-hold comparison
        if self.buy_hold_metrics:
            bh = self.buy_hold_metrics
            print("\n" + "=" * 60)
            print("BUY-AND-HOLD BENCHMARK")
            print("=" * 60)
            print(f"  Final Value:          ${bh.get('buy_hold_final_value', 0):>14,.2f}")
            print(f"  Total Return:          {bh.get('buy_hold_return_pct', 0):>14.2%}")
            print(f"  Annualized Return:     {bh.get('buy_hold_annualized', 0):>14.2%}")
            print(f"  Max Drawdown:          {bh.get('buy_hold_max_drawdown_pct', 0):>14.2%}")
            print("=" * 60)

            # Comparison
            strat_ret = self.metrics.metrics.get("total_return_pct", 0)
            bh_ret = bh.get("buy_hold_return_pct", 0)
            diff = strat_ret - bh_ret
            print(f"\n  Strategy vs B&H:       {diff:>+14.2%}")
            if diff > 0:
                print("  Strategy OUTPERFORMS buy-and-hold")
            elif diff < 0:
                print("  Strategy UNDERPERFORMS buy-and-hold")
            else:
                print("  Strategy MATCHES buy-and-hold")
            print("=" * 60 + "\n")

    def plot_equity_curve(self, save: bool = True, show: bool = True) -> None:
        """Plot the equity curve with buy-and-hold benchmark.

        Args:
            save: Save the plot to a file.
            show: Display the plot.
        """
        if self.equity_curve.empty:
            logger.warning("No equity curve data to plot")
            return

        fig, ax = plt.subplots(figsize=(14, 7))

        # Strategy equity
        ax.plot(
            self.equity_curve.index,
            self.equity_curve["equity"],
            label=f"{self.strategy_name}",
            color="#2196F3",
            linewidth=1.5,
        )

        # Initial capital line
        ax.axhline(
            y=self.metrics.metrics["initial_capital"],
            color="gray",
            linestyle="--",
            alpha=0.5,
            label="Initial Capital",
        )

        # Mark trades on the curve
        if not self.trade_log.empty:
            for _, trade in self.trade_log.iterrows():
                if trade["net_pnl"] >= 0:
                    color = "#4CAF50"
                else:
                    color = "#F44336"

                # Entry marker
                if trade["entry_timestamp"] in self.equity_curve.index:
                    entry_val = self.equity_curve.loc[trade["entry_timestamp"], "equity"]
                    ax.scatter(
                        trade["entry_timestamp"],
                        entry_val,
                        color=color,
                        marker="^",
                        s=30,
                        zorder=5,
                        alpha=0.7,
                    )

        ax.set_title(f"Equity Curve — {self.strategy_name}", fontsize=14)
        ax.set_xlabel("Date")
        ax.set_ylabel("Portfolio Value ($)")
        ax.legend(loc="upper left")
        ax.grid(True, alpha=0.3)

        fig.autofmt_xdate()
        plt.tight_layout()

        if save:
            filepath = self.output_dir / "equity_curve.png"
            fig.savefig(filepath, dpi=150)
            logger.info(f"Equity curve saved to {filepath}")

        if show:
            plt.show()
        else:
            plt.close(fig)

    def plot_drawdown(self, save: bool = True, show: bool = True) -> None:
        """Plot the drawdown over time.

        Args:
            save: Save the plot to a file.
            show: Display the plot.
        """
        if self.equity_curve.empty:
            logger.warning("No equity curve data to plot")
            return

        fig, ax = plt.subplots(figsize=(14, 5))

        ax.fill_between(
            self.equity_curve.index,
            -self.equity_curve["drawdown_pct"] * 100,
            0,
            color="#F44336",
            alpha=0.4,
            label="Drawdown",
        )
        ax.plot(
            self.equity_curve.index,
            -self.equity_curve["drawdown_pct"] * 100,
            color="#D32F2F",
            linewidth=0.8,
        )

        max_dd = self.metrics.metrics["max_drawdown_pct"]
        ax.axhline(
            y=-max_dd * 100,
            color="#B71C1C",
            linestyle="--",
            alpha=0.5,
            label=f"Max Drawdown ({max_dd:.1%})",
        )

        ax.set_title(f"Drawdown — {self.strategy_name}", fontsize=14)
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.legend(loc="lower left")
        ax.grid(True, alpha=0.3)

        fig.autofmt_xdate()
        plt.tight_layout()

        if save:
            filepath = self.output_dir / "drawdown.png"
            fig.savefig(filepath, dpi=150)
            logger.info(f"Drawdown plot saved to {filepath}")

        if show:
            plt.show()
        else:
            plt.close(fig)

    def export_trade_log(self, filename: str = "trade_log.csv") -> Path:
        """Export the trade log to CSV.

        Args:
            filename: Output filename.

        Returns:
            Path to the exported file.
        """
        filepath = self.output_dir / filename

        if self.trade_log.empty:
            logger.warning("No trades to export")
            return filepath

        self.trade_log.to_csv(filepath, index=False)
        logger.info(f"Trade log exported to {filepath} ({len(self.trade_log)} trades)")
        return filepath

    def export_metrics_json(self, filename: str = "metrics.json") -> Path:
        """Export metrics to JSON.

        Args:
            filename: Output filename.

        Returns:
            Path to the exported file.
        """
        filepath = self.output_dir / filename

        # Combine strategy and benchmark metrics
        output = {
            "strategy": self.strategy_name,
            "metrics": {},
            "benchmark": self.buy_hold_metrics,
        }

        # Convert metrics, handling non-JSON-serializable float values
        for key, value in self.metrics.to_dict().items():
            if isinstance(value, float):
                if value != value:  # NaN check (NaN != NaN is True)
                    output["metrics"][key] = None
                elif value == float("inf") or value == float("-inf"):
                    output["metrics"][key] = str(value)
                else:
                    output["metrics"][key] = value
            else:
                output["metrics"][key] = value

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2, default=str)

        logger.info(f"Metrics exported to {filepath}")
        return filepath
