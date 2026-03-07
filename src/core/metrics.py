"""
Performance metrics computation for the backtesting engine.

Computes a comprehensive set of trading performance metrics from
the equity curve and trade log.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from src.core.position import Trade
from src.utils.logger import setup_logger

logger = setup_logger("metrics")


class PerformanceMetrics:
    """Computes and stores backtesting performance metrics.

    Attributes:
        metrics: Dictionary of all computed metrics.
    """

    def __init__(
        self,
        equity_curve: pd.DataFrame,
        trades: list[Trade],
        initial_capital: float,
        trading_days_per_year: int = 252,
        risk_free_rate: float = 0.0,
        total_bars: int = 0,
    ) -> None:
        self.equity_curve = equity_curve
        self.trades = trades
        self.initial_capital = initial_capital
        self.trading_days_per_year = trading_days_per_year
        self.risk_free_rate = risk_free_rate
        self.total_bars = total_bars

        self.metrics: dict[str, Any] = {}
        self._compute_all()

    def _compute_all(self) -> None:
        """Compute all metrics."""
        self.metrics["initial_capital"] = self.initial_capital
        self.metrics["final_value"] = self._final_value()
        self.metrics["total_return"] = self._total_return()
        self.metrics["total_return_pct"] = self._total_return_pct()
        self.metrics["annualized_return"] = self._annualized_return()
        self.metrics["cagr"] = self._cagr()
        self.metrics["num_trades"] = len(self.trades)
        self.metrics["win_rate"] = self._win_rate()
        self.metrics["profit_factor"] = self._profit_factor()
        self.metrics["expectancy"] = self._expectancy()
        self.metrics["max_drawdown"] = self._max_drawdown()
        self.metrics["max_drawdown_pct"] = self._max_drawdown_pct()
        self.metrics["sharpe_ratio"] = self._sharpe_ratio()
        self.metrics["sortino_ratio"] = self._sortino_ratio()
        self.metrics["avg_trade_return"] = self._avg_trade_return()
        self.metrics["avg_winner"] = self._avg_winner()
        self.metrics["avg_loser"] = self._avg_loser()
        self.metrics["largest_winner"] = self._largest_winner()
        self.metrics["largest_loser"] = self._largest_loser()
        self.metrics["avg_bars_held"] = self._avg_bars_held()
        self.metrics["exposure_pct"] = self._exposure_pct()
        self.metrics["total_fees"] = self._total_fees()
        self.metrics["num_winners"] = len([t for t in self.trades if t.is_winner])
        self.metrics["num_losers"] = len([t for t in self.trades if t.is_loser])

    def _final_value(self) -> float:
        if self.equity_curve.empty:
            return self.initial_capital
        return self.equity_curve["equity"].iloc[-1]

    def _total_return(self) -> float:
        return self._final_value() - self.initial_capital

    def _total_return_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return self._total_return() / self.initial_capital

    def _annualized_return(self) -> float:
        """Annualized return based on the number of bars and trading days."""
        if self.total_bars <= 1:
            return 0.0
        total_ret = self._total_return_pct()
        years = self.total_bars / self.trading_days_per_year
        if years <= 0:
            return 0.0
        if total_ret <= -1.0:
            return -1.0
        return (1 + total_ret) ** (1 / years) - 1

    def _cagr(self) -> float:
        """Compound Annual Growth Rate.

        Identical to annualized return when computed from total return.
        Separated for clarity — both are provided.
        """
        return self._annualized_return()

    def _win_rate(self) -> float:
        if not self.trades:
            return 0.0
        winners = sum(1 for t in self.trades if t.is_winner)
        return winners / len(self.trades)

    def _profit_factor(self) -> float:
        """Gross profits / gross losses."""
        gross_profit = sum(t.net_pnl for t in self.trades if t.net_pnl > 0)
        gross_loss = abs(sum(t.net_pnl for t in self.trades if t.net_pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def _expectancy(self) -> float:
        """Average net PnL per trade."""
        if not self.trades:
            return 0.0
        return sum(t.net_pnl for t in self.trades) / len(self.trades)

    def _max_drawdown(self) -> float:
        """Maximum drawdown in absolute terms."""
        if self.equity_curve.empty:
            return 0.0
        return self.equity_curve["drawdown"].max()

    def _max_drawdown_pct(self) -> float:
        """Maximum drawdown as a percentage."""
        if self.equity_curve.empty:
            return 0.0
        return self.equity_curve["drawdown_pct"].max()

    def _sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio based on equity curve returns.

        Uses daily returns from the equity curve.
        """
        if self.equity_curve.empty or len(self.equity_curve) < 2:
            return 0.0

        returns = self.equity_curve["equity"].pct_change().dropna()
        if returns.std() == 0:
            return 0.0

        daily_rf = self.risk_free_rate / self.trading_days_per_year
        excess_returns = returns - daily_rf
        return (excess_returns.mean() / excess_returns.std()) * np.sqrt(self.trading_days_per_year)

    def _sortino_ratio(self) -> float:
        """Annualized Sortino ratio (penalizes only downside volatility)."""
        if self.equity_curve.empty or len(self.equity_curve) < 2:
            return 0.0

        returns = self.equity_curve["equity"].pct_change().dropna()
        daily_rf = self.risk_free_rate / self.trading_days_per_year
        excess_returns = returns - daily_rf

        downside = excess_returns[excess_returns < 0]
        if len(downside) == 0 or downside.std() == 0:
            return float("inf") if excess_returns.mean() > 0 else 0.0

        return (excess_returns.mean() / downside.std()) * np.sqrt(self.trading_days_per_year)

    def _avg_trade_return(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.return_pct for t in self.trades) / len(self.trades)

    def _avg_winner(self) -> float:
        winners = [t.net_pnl for t in self.trades if t.is_winner]
        return sum(winners) / len(winners) if winners else 0.0

    def _avg_loser(self) -> float:
        losers = [t.net_pnl for t in self.trades if t.is_loser]
        return sum(losers) / len(losers) if losers else 0.0

    def _largest_winner(self) -> float:
        winners = [t.net_pnl for t in self.trades if t.is_winner]
        return max(winners) if winners else 0.0

    def _largest_loser(self) -> float:
        losers = [t.net_pnl for t in self.trades if t.is_loser]
        return min(losers) if losers else 0.0

    def _avg_bars_held(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.bars_held for t in self.trades) / len(self.trades)

    def _exposure_pct(self) -> float:
        """Percentage of bars where a position was held."""
        if self.total_bars == 0:
            return 0.0
        bars_in_trade = sum(t.bars_held for t in self.trades)
        return min(bars_in_trade / self.total_bars, 1.0)

    def _total_fees(self) -> float:
        return sum(t.fees for t in self.trades)

    def to_dict(self) -> dict[str, Any]:
        """Return metrics as a dictionary."""
        return self.metrics.copy()

    def summary_string(self) -> str:
        """Format metrics as a readable summary string."""
        m = self.metrics
        lines = [
            "=" * 60,
            "BACKTEST PERFORMANCE REPORT",
            "=" * 60,
            f"  Initial Capital:      ${m['initial_capital']:>14,.2f}",
            f"  Final Value:          ${m['final_value']:>14,.2f}",
            f"  Total Return:         ${m['total_return']:>14,.2f} ({m['total_return_pct']:>8.2%})",
            f"  Annualized Return:     {m['annualized_return']:>14.2%}",
            f"  CAGR:                  {m['cagr']:>14.2%}",
            "",
            f"  Max Drawdown:         ${m['max_drawdown']:>14,.2f} ({m['max_drawdown_pct']:>8.2%})",
            f"  Sharpe Ratio:          {m['sharpe_ratio']:>14.4f}",
            f"  Sortino Ratio:         {m['sortino_ratio']:>14.4f}",
            "",
            f"  Total Trades:          {m['num_trades']:>14d}",
            f"  Winners:               {m['num_winners']:>14d}",
            f"  Losers:                {m['num_losers']:>14d}",
            f"  Win Rate:              {m['win_rate']:>14.2%}",
            f"  Profit Factor:         {m['profit_factor']:>14.4f}",
            f"  Expectancy:           ${m['expectancy']:>14,.2f}",
            "",
            f"  Avg Trade Return:      {m['avg_trade_return']:>14.4%}",
            f"  Avg Winner:           ${m['avg_winner']:>14,.2f}",
            f"  Avg Loser:            ${m['avg_loser']:>14,.2f}",
            f"  Largest Winner:       ${m['largest_winner']:>14,.2f}",
            f"  Largest Loser:        ${m['largest_loser']:>14,.2f}",
            "",
            f"  Avg Bars Held:         {m['avg_bars_held']:>14.1f}",
            f"  Exposure:              {m['exposure_pct']:>14.2%}",
            f"  Total Fees:           ${m['total_fees']:>14,.2f}",
            "=" * 60,
        ]
        return "\n".join(lines)


def compute_buy_and_hold(
    data: pd.DataFrame,
    initial_capital: float,
    fee_rate: float = 0.001,
    trading_days_per_year: int = 252,
) -> dict[str, Any]:
    """Compute buy-and-hold benchmark metrics.

    Simulates buying at the first bar's open and selling at the last
    bar's close, with fees applied.

    Args:
        data: OHLCV DataFrame.
        initial_capital: Starting capital.
        fee_rate: Fee rate for entry and exit.
        trading_days_per_year: For annualization.

    Returns:
        Dictionary of buy-and-hold metrics.
    """
    if data.empty or len(data) < 2:
        return {"buy_hold_return": 0.0, "buy_hold_return_pct": 0.0}

    entry_price = data["open"].iloc[0]
    exit_price = data["close"].iloc[-1]

    # Buy at first open with fees
    quantity = (initial_capital * (1 - fee_rate)) / entry_price
    # Sell at last close with fees
    exit_value = quantity * exit_price * (1 - fee_rate)

    total_return = exit_value - initial_capital
    total_return_pct = total_return / initial_capital
    years = len(data) / trading_days_per_year

    if years > 0 and total_return_pct > -1.0:
        annualized = (1 + total_return_pct) ** (1 / years) - 1
    else:
        annualized = -1.0 if total_return_pct <= -1.0 else 0.0

    # Compute buy-and-hold equity curve for max drawdown
    equity = quantity * data["close"]
    peak = equity.cummax()
    drawdown_pct = ((peak - equity) / peak).max()

    return {
        "buy_hold_return": total_return,
        "buy_hold_return_pct": total_return_pct,
        "buy_hold_annualized": annualized,
        "buy_hold_final_value": exit_value,
        "buy_hold_max_drawdown_pct": drawdown_pct,
    }
