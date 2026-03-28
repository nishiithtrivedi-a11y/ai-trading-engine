"""
Main backtesting engine — orchestrates the bar-by-bar simulation loop.

Coordinates the DataHandler, Strategy, Broker, and Portfolio to run
a complete backtest, then computes metrics and generates reports.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.core.broker import Broker
from src.core.data_handler import DataHandler
from src.core.metrics import PerformanceMetrics, compute_buy_and_hold
from src.core.portfolio import Portfolio
from src.core.reporting import ReportGenerator
from src.strategies.base_strategy import BaseStrategy, Signal, StrategySignal
from src.utils.config import BacktestConfig, DataSource, ExecutionMode
from src.utils.logger import setup_logger
from src.utils.market_sessions import is_market_open, MarketSessionConfig

logger = setup_logger("engine")


class BacktestEngine:
    """Runs bar-by-bar backtests with a given strategy and configuration.

    The engine follows this loop for each bar:
        1. Update data pointer
        2. Check risk management exits (stop-loss, take-profit, trailing stop)
        3. Process any pending orders from the previous bar
        4. Let the strategy generate a signal
        5. Submit orders based on the signal
        6. Record portfolio state

    Signals generated on bar t are executed on bar t+1 open (default).

    Attributes:
        config: Backtesting configuration.
        data_handler: Manages market data access.
        portfolio: Tracks cash, positions, and trades.
        broker: Handles order creation, sizing, and execution.
        strategy: The trading strategy being tested.
        metrics: Computed after the backtest completes.
    """

    def __init__(
        self,
        config: BacktestConfig,
        strategy: BaseStrategy,
        data_handler: Optional[DataHandler] = None,
    ) -> None:
        self.config = config
        self.strategy = strategy
        self.data_handler = data_handler
        self.portfolio = Portfolio(config.initial_capital)
        self.broker = Broker(config, self.portfolio)
        self.metrics: Optional[PerformanceMetrics] = None
        self.buy_hold_metrics: dict[str, Any] = {}

    def _is_intraday_mode(self) -> bool:
        return bool(self.config.intraday)

    def _can_enter_on_bar(self, timestamp: pd.Timestamp) -> bool:
        if not self._is_intraday_mode():
            return True
        if not self.config.allow_entries_only_during_market_hours:
            return True
        sess_cfg = MarketSessionConfig(timezone=self.config.market_timezone)
        return is_market_open(timestamp, config=sess_cfg)

    def _should_force_square_off(self, timestamp: pd.Timestamp, bar_index: int) -> bool:
        if not self._is_intraday_mode():
            return False
        if not self.config.force_square_off_at_close:
            return False
        return self._is_last_bar_of_session(timestamp, bar_index)

    def _is_last_bar_of_session(self, timestamp: pd.Timestamp, bar_index: int) -> bool:
        """True when *timestamp* is the last bar of its local-timezone session day.

        Compares the local-timezone date of the current bar against the next bar.
        A date boundary means this is the session's final bar and positions must close.
        Handles naive, UTC-aware, and IST-aware timestamps uniformly.
        """
        tz = self.config.market_timezone

        def _to_local(ts: pd.Timestamp) -> pd.Timestamp:
            if ts.tzinfo is None:
                return ts.tz_localize(tz)
            return ts.tz_convert(tz)

        # Last bar of the entire dataset → always close
        if self.data_handler is None or bar_index >= len(self.data_handler) - 1:
            return True

        next_raw = self.data_handler.data.index[bar_index + 1]
        next_local = _to_local(pd.Timestamp(next_raw))
        ts_local = _to_local(timestamp)

        return ts_local.date() != next_local.date()

    def run(self, data_handler: Optional[DataHandler] = None) -> PerformanceMetrics:
        """Execute the backtest.

        Args:
            data_handler: Optional override for data_handler.

        Returns:
            PerformanceMetrics computed from the backtest results.
        """
        if data_handler is not None:
            self.data_handler = data_handler

        if self.data_handler is None:
            self.data_handler = self._load_data_from_config()

        dh = self.data_handler

        logger.info(f"Starting backtest: {len(dh)} bars")
        logger.info(f"Strategy: {self.strategy.name}")
        logger.info(f"Initial capital: ${self.config.initial_capital:,.2f}")
        logger.info(f"Execution mode: {self.config.execution_mode.value}")
        logger.info(f"Intraday mode: {self._is_intraday_mode()}")

        # Reset state
        self.portfolio.reset()
        self.broker = Broker(self.config, self.portfolio)
        dh.reset()

        # Initialize strategy
        self.strategy.initialize(self.config.strategy_params)

        # Optional precompute hook for strategies that support it.
        # Computes all indicators once on the full dataset before the
        # bar-by-bar loop, avoiding O(n^2) recomputation per bar.
        if hasattr(self.strategy, "precompute"):
            self.strategy.precompute(dh.data)

        total_bars = len(dh)

        for i in range(total_bars):
            dh.current_index = i
            bar = dh.get_current_bar()
            timestamp = dh.get_current_timestamp()

            # 1. Check risk management exits first
            if self.portfolio.has_position:
                self.broker.check_risk_exits(bar, timestamp, i)

            # 2. Process pending orders from previous bar signal
            #    (these execute at current bar's open)
            if self.broker.pending_orders:
                self.broker.process_pending_orders(bar, timestamp, i)

            # 2b. Intraday force square-off at session close
            if self.portfolio.has_position and self._should_force_square_off(timestamp, i):
                self.broker._execute_risk_exit(
                    exit_price=bar["close"],
                    timestamp=timestamp,
                    bar_index=i,
                    reason="session_close",
                )

            # 3. Check if drawdown kill switch stopped trading
            if self.broker.is_killed:
                self.portfolio.record_state(timestamp, bar["close"])
                continue

            # 4. Generate signal from strategy
            #    Strategy only sees data up to current bar
            available_data = dh.get_data_up_to_current()
            signal_payload = self.strategy.generate_signal(
                available_data,
                bar,
                i,
            )
            signal = BaseStrategy.normalize_signal(signal_payload)

            # 5. Handle signal
            can_enter = self._can_enter_on_bar(timestamp)

            if self.config.execution_mode == ExecutionMode.NEXT_BAR_OPEN:
                # Queue order for next bar execution
                self._handle_signal(signal, bar, timestamp, can_enter)
            elif self.config.execution_mode == ExecutionMode.SAME_BAR_CLOSE:
                # Execute immediately at close (explicit lookahead opt-in)
                self._handle_signal(signal, bar, timestamp, can_enter)
                if self.broker.pending_orders:
                    # Create a synthetic bar with open=close for same-bar execution
                    close_bar = bar.copy()
                    close_bar["open"] = bar["close"]
                    self.broker.process_pending_orders(close_bar, timestamp, i)

            # 6. Record portfolio state
            self.portfolio.record_state(timestamp, bar["close"])

        # Close open positions at end if configured
        if self.config.close_positions_at_end and self.portfolio.has_position:
            last_bar = dh.get_current_bar()
            last_timestamp = dh.get_current_timestamp()
            self.broker._execute_risk_exit(
                last_bar["close"],
                last_timestamp,
                total_bars - 1,
                "end_of_backtest",
            )
            # Re-record final state properly instead of mutating internals.
            # The position is now closed so total_value == cash.
            if self.portfolio._equity_records:
                final_value = self.portfolio.total_value(last_bar["close"])
                self.portfolio._equity_records[-1]["equity"] = final_value
                peak = self.portfolio.peak_value
                dd = max(0, peak - final_value)
                self.portfolio._equity_records[-1]["drawdown"] = dd
                self.portfolio._equity_records[-1]["drawdown_pct"] = dd / peak if peak > 0 else 0.0

        # Compute metrics
        self.metrics = PerformanceMetrics(
            equity_curve=self.portfolio.get_equity_curve(),
            trades=self.portfolio.trades,
            initial_capital=self.config.initial_capital,
            trading_days_per_year=self.config.trading_days_per_year,
            risk_free_rate=self.config.risk_free_rate,
            total_bars=total_bars,
        )

        # Compute buy-and-hold benchmark
        self.buy_hold_metrics = compute_buy_and_hold(
            data=dh.data,
            initial_capital=self.config.initial_capital,
            fee_rate=self.config.fee_rate,
            trading_days_per_year=self.config.trading_days_per_year,
        )

        logger.info("Backtest complete")
        logger.info(f"Final value: ${self.metrics.metrics['final_value']:,.2f}")
        logger.info(f"Total return: {self.metrics.metrics['total_return_pct']:.2%}")
        logger.info(f"Trades: {self.metrics.metrics['num_trades']}")

        return self.metrics

    def _handle_signal(
        self,
        signal: Signal | StrategySignal | str,
        bar: pd.Series,
        timestamp: pd.Timestamp,
        can_enter: bool = True,
    ) -> None:
        """Convert a strategy signal into broker orders.

        Args:
            signal: The signal generated by the strategy.
            bar: Current bar data.
            timestamp: Current bar timestamp.
            can_enter: Whether fresh entries are allowed on this bar.
        """
        normalized_signal = BaseStrategy.normalize_signal(signal)

        if normalized_signal == Signal.BUY:
            if can_enter:
                self.broker.submit_buy(
                    signal_price=bar["close"],
                    timestamp=timestamp,
                    reason="strategy_buy",
                )
        elif normalized_signal == Signal.SELL:
            self.broker.submit_sell(
                signal_price=bar["close"],
                timestamp=timestamp,
                reason="strategy_sell",
            )
        elif normalized_signal == Signal.EXIT:
            self.broker.submit_sell(
                signal_price=bar["close"],
                timestamp=timestamp,
                reason="strategy_exit",
            )
        # HOLD: do nothing

    def _load_data_from_config(self) -> DataHandler:
        """Load data based on the configured data source.

        Returns:
            DataHandler instance with loaded data.
        """
        source = self.config.data_source

        if source == DataSource.INDIAN_CSV:
            from src.data.indian_data_loader import IndianCSVDataSource
            data_source = IndianCSVDataSource(self.config.data_file)
            return DataHandler.from_source(data_source)
        elif source == DataSource.ZERODHA:
            from src.data.sources import ZerodhaDataSource
            data_source = ZerodhaDataSource(
                api_key=self.config.strategy_params.get("api_key", ""),
                api_secret=self.config.strategy_params.get("api_secret", ""),
                access_token=self.config.strategy_params.get("access_token", ""),
            )
            return DataHandler.from_source(data_source)
        elif source == DataSource.UPSTOX:
            from src.data.sources import UpstoxDataSource
            data_source = UpstoxDataSource(
                api_key=self.config.strategy_params.get("api_key", ""),
                api_secret=self.config.strategy_params.get("api_secret", ""),
                access_token=self.config.strategy_params.get("access_token", ""),
            )
            return DataHandler.from_source(data_source)
        return DataHandler.from_csv(self.config.data_file)

    def generate_report(self, show_plots: bool = True) -> None:
        """Generate and display the backtest report.

        Args:
            show_plots: Whether to display matplotlib plots.
        """
        if self.metrics is None:
            logger.error("No metrics available. Run the backtest first.")
            return

        reporter = ReportGenerator(
            metrics=self.metrics,
            equity_curve=self.portfolio.get_equity_curve(),
            trade_log=self.portfolio.get_trade_log(),
            buy_hold_metrics=self.buy_hold_metrics,
            strategy_name=self.strategy.name,
            output_dir=self.config.output_dir,
        )

        reporter.print_summary()
        reporter.export_trade_log()
        reporter.export_metrics_json()

        if show_plots:
            reporter.plot_equity_curve()
            reporter.plot_drawdown()

    def get_results(self) -> dict[str, Any]:
        """Get all backtest results as a dictionary.

        Returns:
            Dictionary with metrics, trade log, equity curve, and benchmark.
        """
        if self.metrics is None:
            return {}

        return {
            "metrics": self.metrics.to_dict(),
            "trade_log": self.portfolio.get_trade_log(),
            "equity_curve": self.portfolio.get_equity_curve(),
            "buy_hold": self.buy_hold_metrics,
        }
