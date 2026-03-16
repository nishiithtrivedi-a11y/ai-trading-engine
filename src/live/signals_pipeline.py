"""
Live-safe market data and signal pipeline.

This module only fetches fresh/latest data, computes context, and generates
paper-compatible signal artifacts. It never places live orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.decision.regime_policy import RegimePolicy, select_for_regime
from src.live.market_session import LiveSessionStore
from src.live.models import LiveMarketSnapshot, SessionSignalReport, SignalDecision, WatchlistState
from src.live.watchlist_manager import LiveWatchlistError, LiveWatchlistManager
from src.market_intelligence.regime_engine import MarketRegimeEngine
from src.market_intelligence.relative_strength import compute_relative_strength
from src.risk.risk_engine import PortfolioRiskManager
from src.scanners.data_gateway import DataGateway
from src.scanners.config import normalize_timeframe
from src.strategies.base_strategy import Signal


class LiveSignalPipelineError(Exception):
    """Raised when the live signal pipeline cannot continue safely."""


@dataclass
class LiveSignalPipelineConfig:
    enabled: bool = False
    provider_name: str = "indian_csv"
    universe_name: str = "nifty50"
    symbols: list[str] = field(default_factory=list)
    custom_universe_file: Optional[str] = None
    symbols_limit: int = 5

    interval: str = "day"
    lookback_bars: int = 250
    output_dir: str = "output/live_signals"

    top_n_symbols: int = 0
    benchmark_symbol: Optional[str] = None
    session_label: str = ""

    apply_relative_strength: bool = True
    apply_regime_policy: bool = True
    apply_risk_precheck: bool = True
    paper_handoff: bool = False

    data_dir: str = "data"

    risk_context_portfolio_equity: float = 100_000.0
    risk_context_current_drawdown_pct: float = 0.0
    risk_context_open_positions_count: int = 0
    risk_context_deployed_capital: float = 0.0

    def __post_init__(self) -> None:
        if self.lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2")
        if self.symbols_limit < 0:
            raise ValueError("symbols_limit must be >= 0")
        if self.top_n_symbols < 0:
            raise ValueError("top_n_symbols must be >= 0")
        if self.risk_context_portfolio_equity <= 0:
            raise ValueError("risk_context_portfolio_equity must be > 0")

    @property
    def timeframe(self) -> str:
        return _interval_to_timeframe(self.interval)


@dataclass
class LiveSignalPipeline:
    config: LiveSignalPipelineConfig
    strategy_registry: dict[str, dict[str, Any]]
    regime_policy: Optional[RegimePolicy] = None
    watchlist_manager: Optional[LiveWatchlistManager] = None
    data_gateway: Optional[DataGateway] = None
    regime_engine: Optional[MarketRegimeEngine] = None
    risk_manager: Optional[PortfolioRiskManager] = None
    session_store: Optional[LiveSessionStore] = None

    def __post_init__(self) -> None:
        if not self.strategy_registry:
            raise ValueError("strategy_registry cannot be empty")

        self.watchlist_manager = self.watchlist_manager or LiveWatchlistManager()
        self.data_gateway = self.data_gateway or DataGateway(
            provider_name=self.config.provider_name,
            data_dir=self.config.data_dir,
        )
        self.regime_engine = self.regime_engine or MarketRegimeEngine()
        self.risk_manager = self.risk_manager or PortfolioRiskManager()
        self.session_store = self.session_store or LiveSessionStore(self.config.output_dir)

    def run(self) -> SessionSignalReport:
        report = SessionSignalReport(
            enabled=self.config.enabled,
            provider_name=self.config.provider_name,
            timeframe=self.config.timeframe,
            session_label=self.config.session_label,
            universe_name=self.config.universe_name,
        )

        if not self.config.enabled:
            report.warnings.append("Live signals are disabled. Pass --live-signals to run the pipeline.")
            return report

        symbols = self._resolve_symbols(report)
        frames, snapshots = self._load_latest_data(symbols, report)
        report.market_snapshots = snapshots

        if not frames:
            report.errors.append("No symbol data was available for live signal generation")
            return report

        ranked_symbols, rs_rows = self._rank_symbols(frames, report)
        report.relative_strength_rows = rs_rows

        report.watchlist_state = WatchlistState(
            session_label=self.config.session_label or "default",
            provider_name=self.config.provider_name,
            universe_name=self.config.universe_name,
            timeframe=self.config.timeframe,
            requested_symbols=symbols,
            loaded_symbols=sorted(frames.keys()),
            ranked_symbols=ranked_symbols,
        )

        regime_labels = self._compute_regimes(ranked_symbols, frames, report)
        self._generate_decisions(ranked_symbols, frames, regime_labels, report)

        exports = self.session_store.export(
            report,
            include_paper_handoff=self.config.paper_handoff,
        )
        report.exports = {name: str(path) for name, path in exports.items()}

        report.metadata["execution_mode"] = "none"
        report.metadata["safety"] = "no_live_orders"
        report.metadata["strategy_count"] = len(self.strategy_registry)
        report.metadata["symbols_ranked"] = len(ranked_symbols)
        return report

    def _resolve_symbols(self, report: SessionSignalReport) -> list[str]:
        try:
            return self.watchlist_manager.resolve(
                universe_name=self.config.universe_name,
                symbols=self.config.symbols,
                custom_universe_file=self.config.custom_universe_file,
                symbols_limit=self.config.symbols_limit or None,
            )
        except LiveWatchlistError as exc:
            report.errors.append(str(exc))
            return []

    def _load_latest_data(
        self,
        symbols: list[str],
        report: SessionSignalReport,
    ) -> tuple[dict[str, pd.DataFrame], list[LiveMarketSnapshot]]:
        frames: dict[str, pd.DataFrame] = {}
        snapshots: list[LiveMarketSnapshot] = []

        for symbol in symbols:
            try:
                handler = self.data_gateway.load_data(symbol, self.config.timeframe)
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"{symbol}: data load failed: {exc}")
                continue

            df = handler.data.tail(self.config.lookback_bars).copy()
            if len(df) < 2:
                report.warnings.append(f"{symbol}: fewer than 2 bars after lookback filter")
                continue

            canonical = str(symbol).strip().upper()
            frames[canonical] = df

            last = df.iloc[-1]
            snapshots.append(
                LiveMarketSnapshot(
                    symbol=canonical,
                    timeframe=self.config.timeframe,
                    timestamp=pd.Timestamp(df.index[-1]),
                    open_price=float(last["open"]),
                    high_price=float(last["high"]),
                    low_price=float(last["low"]),
                    close_price=float(last["close"]),
                    volume=float(last.get("volume", 0.0)),
                    bars_loaded=len(df),
                    provider_name=self.config.provider_name,
                    metadata={"lookback_bars": self.config.lookback_bars},
                )
            )

        return frames, snapshots

    def _rank_symbols(
        self,
        frames: dict[str, pd.DataFrame],
        report: SessionSignalReport,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        ranked = sorted(frames.keys())
        rows: list[dict[str, Any]] = []

        if self.config.apply_relative_strength and len(frames) > 1:
            benchmark_series = self._load_benchmark_series(frames, report)
            lookback = min(self.config.lookback_bars, min(len(df) for df in frames.values()))
            try:
                rs_df = compute_relative_strength(
                    symbol_to_ohlcv=frames,
                    lookback=lookback,
                    benchmark_series=benchmark_series,
                )
                if not rs_df.empty and "symbol" in rs_df.columns:
                    rows = rs_df.to_dict(orient="records")
                    ranked = [str(s).strip().upper() for s in rs_df["symbol"].tolist()]
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"Relative-strength ranking failed: {exc}")

        if self.config.top_n_symbols > 0:
            ranked = ranked[: self.config.top_n_symbols]

        return ranked, rows

    def _load_benchmark_series(
        self,
        frames: dict[str, pd.DataFrame],
        report: SessionSignalReport,
    ) -> Optional[pd.Series]:
        if not self.config.benchmark_symbol:
            return None

        benchmark = str(self.config.benchmark_symbol).strip().upper()
        if benchmark in frames:
            return frames[benchmark]["close"]

        try:
            benchmark_handler = self.data_gateway.load_data(benchmark, self.config.timeframe)
            benchmark_df = benchmark_handler.data.tail(self.config.lookback_bars)
            return benchmark_df["close"]
        except Exception as exc:  # noqa: BLE001
            report.warnings.append(f"Benchmark {benchmark} could not be loaded: {exc}")
            return None

    def _compute_regimes(
        self,
        ranked_symbols: list[str],
        frames: dict[str, pd.DataFrame],
        report: SessionSignalReport,
    ) -> dict[str, str]:
        labels: dict[str, str] = {}

        for symbol in ranked_symbols:
            df = frames[symbol]
            try:
                snapshot = self.regime_engine.detect(df, symbol=symbol)
                report.regime_snapshots.append(snapshot.to_dict())
                labels[symbol] = snapshot.composite_regime.value
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"{symbol}: regime detection failed: {exc}")
                labels[symbol] = "unknown"

        return labels

    def _generate_decisions(
        self,
        ranked_symbols: list[str],
        frames: dict[str, pd.DataFrame],
        regime_labels: dict[str, str],
        report: SessionSignalReport,
    ) -> None:
        available_strategy_names = [
            name for name in self.strategy_registry.keys() if name in self.strategy_registry
        ]
        if not available_strategy_names:
            report.errors.append("No available strategies configured for signal generation")
            return

        open_positions_estimate = int(self.config.risk_context_open_positions_count)
        deployed_capital_estimate = float(self.config.risk_context_deployed_capital)
        slot_capital = self.config.risk_context_portfolio_equity / max(
            1,
            self.risk_manager.config.max_concurrent_positions,
        )

        for symbol in ranked_symbols:
            df = frames[symbol]
            bar = df.iloc[-1]
            timestamp = pd.Timestamp(df.index[-1])
            close_price = float(bar["close"])
            regime_label = regime_labels.get(symbol, "unknown")

            strategy_name, selection_reason, should_trade = self._select_strategy(
                regime_label=regime_label,
                available_strategy_names=available_strategy_names,
            )

            if not should_trade:
                report.decisions.append(
                    SignalDecision(
                        symbol=symbol,
                        timeframe=self.config.timeframe,
                        strategy_name=strategy_name,
                        signal="hold",
                        timestamp=timestamp,
                        close_price=close_price,
                        decision_type="no_trade",
                        reason=selection_reason,
                        regime_label=regime_label,
                        risk_allowed=None,
                    )
                )
                continue

            signal = self._run_strategy_signal(strategy_name, df)
            if signal != Signal.BUY:
                report.decisions.append(
                    SignalDecision(
                        symbol=symbol,
                        timeframe=self.config.timeframe,
                        strategy_name=strategy_name,
                        signal=signal.value,
                        timestamp=timestamp,
                        close_price=close_price,
                        decision_type="no_trade",
                        reason="Strategy did not produce actionable BUY signal on latest bar",
                        regime_label=regime_label,
                        risk_allowed=None,
                    )
                )
                continue

            risk_allowed = True
            risk_reason = "risk_checks_passed"
            if self.config.apply_risk_precheck:
                risk_decision = self.risk_manager.check_entry(
                    portfolio_equity=float(self.config.risk_context_portfolio_equity),
                    current_drawdown_pct=float(self.config.risk_context_current_drawdown_pct),
                    open_positions_count=open_positions_estimate,
                    deployed_capital=deployed_capital_estimate,
                    regime_label=regime_label,
                )
                risk_allowed = bool(risk_decision.allowed)
                risk_reason = risk_decision.blocked_reason or "risk_checks_passed"

            if not risk_allowed:
                report.decisions.append(
                    SignalDecision(
                        symbol=symbol,
                        timeframe=self.config.timeframe,
                        strategy_name=strategy_name,
                        signal=signal.value,
                        timestamp=timestamp,
                        close_price=close_price,
                        decision_type="risk_rejected",
                        reason=risk_reason,
                        regime_label=regime_label,
                        risk_allowed=False,
                        paper_handoff_eligible=False,
                    )
                )
                continue

            estimated_quantity = self.risk_manager.compute_position_size(
                capital=float(slot_capital),
                price=close_price,
                portfolio_equity=float(self.config.risk_context_portfolio_equity),
                stop_loss_pct=None,
            )
            estimated_notional = max(0.0, float(estimated_quantity) * close_price)
            open_positions_estimate += 1
            deployed_capital_estimate += estimated_notional

            report.decisions.append(
                SignalDecision(
                    symbol=symbol,
                    timeframe=self.config.timeframe,
                    strategy_name=strategy_name,
                    signal=signal.value,
                    timestamp=timestamp,
                    close_price=close_price,
                    decision_type="actionable_signal",
                    reason=selection_reason,
                    regime_label=regime_label,
                    risk_allowed=True,
                    paper_handoff_eligible=bool(self.config.paper_handoff),
                    metadata={
                        "estimated_deployed_capital": deployed_capital_estimate,
                        "estimated_open_positions": open_positions_estimate,
                    },
                )
            )

    def _select_strategy(
        self,
        *,
        regime_label: str,
        available_strategy_names: list[str],
    ) -> tuple[str, str, bool]:
        fallback = available_strategy_names[0]
        if not (self.config.apply_regime_policy and self.regime_policy is not None):
            return fallback, "No regime policy loaded; using fallback strategy", True

        decision = select_for_regime(
            regime_label=regime_label,
            available_strategies=available_strategy_names,
            policy=self.regime_policy,
        )

        if not decision.should_trade:
            return fallback, decision.explanation, False

        strategy_name = decision.preferred_strategy or fallback
        if strategy_name not in self.strategy_registry:
            strategy_name = fallback

        return strategy_name, decision.explanation, True

    def _run_strategy_signal(self, strategy_name: str, df: pd.DataFrame) -> Signal:
        registry_entry = self.strategy_registry[strategy_name]
        strategy_cls = registry_entry["class"]
        params = dict(registry_entry.get("params", {}))
        strategy = strategy_cls(**params)
        strategy.initialize(params)
        bar = df.iloc[-1]
        result = strategy.on_bar(df, bar, len(df) - 1)
        if not isinstance(result, Signal):
            raise LiveSignalPipelineError(
                f"Strategy '{strategy_name}' returned unsupported signal type: {type(result)}"
            )
        return result


def _interval_to_timeframe(interval: str) -> str:
    mapping = {
        "day": "1D",
        "daily": "1D",
        "1d": "1D",
        "1D": "1D",
        "5minute": "5m",
        "5m": "5m",
        "15minute": "15m",
        "15m": "15m",
        "60minute": "1h",
        "1h": "1h",
    }
    key = str(interval).strip()
    normalized = mapping.get(key, key)
    return normalize_timeframe(normalized)


def load_regime_policy_if_available(path_value: str | None) -> Optional[RegimePolicy]:
    if not path_value:
        return None

    path = Path(path_value)
    if not path.exists():
        return None

    return RegimePolicy.load_json(path)
