#!/usr/bin/env python3
"""
Paper-trading runner.

Safe by default:
  - no action unless --paper-trading is explicitly passed
  - no live broker orders are ever sent
  - paper session artifacts are written to output/paper_trading/
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.core.data_handler import DataHandler  # noqa: E402
from src.data.base import Timeframe  # noqa: E402
from src.data.nse_universe import NSEUniverseLoader  # noqa: E402
from src.data.provider_factory import ProviderFactory  # noqa: E402
from src.data.symbol_mapping import SymbolMapper  # noqa: E402
from src.decision.regime_policy import RegimePolicy  # noqa: E402
from src.paper_trading import (  # noqa: E402
    PaperStateStore,
    PaperTradingConfig,
    PaperTradingEngine,
)
from src.strategies.breakout import BreakoutStrategy  # noqa: E402
from src.strategies.rsi_reversion import RSIReversionStrategy  # noqa: E402
from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402
from src.utils.config import BacktestConfig, ExecutionMode  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the safe paper-trading engine.")
    parser.add_argument("--paper-trading", action="store_true", help="Explicitly enable paper trading.")
    parser.add_argument("--provider", default="", help="Provider name (csv, indian_csv, zerodha, upstox).")
    parser.add_argument("--universe", default="nifty50", help="Universe name: nifty50, banknifty, nifty_next_50, custom.")
    parser.add_argument("--universe-file", default="", help="CSV file for a custom universe.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbols to override universe selection.")
    parser.add_argument("--symbols-limit", type=int, default=5, help="Limit symbols for safe validation runs.")
    parser.add_argument("--days", type=int, default=365, help="Lookback days for provider historical fetch.")
    parser.add_argument(
        "--interval",
        choices=["day", "5minute", "15minute", "60minute"],
        default="day",
        help="Bar interval to load.",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=["sma", "rsi", "breakout"],
        default=["sma", "rsi", "breakout"],
        help="Strategies available to regime-aware selection.",
    )
    parser.add_argument("--paper-capital", type=float, default=100_000.0, help="Initial paper capital.")
    parser.add_argument(
        "--paper-output-dir",
        type=str,
        default="output/paper_trading",
        help="Output directory for paper-trading artifacts.",
    )
    parser.add_argument(
        "--paper-session-date",
        type=str,
        default="",
        help="Optional session cutoff date (YYYY-MM-DD or full timestamp).",
    )
    parser.add_argument(
        "--paper-max-orders",
        type=int,
        default=20,
        help="Maximum paper orders created in one session.",
    )
    parser.add_argument(
        "--paper-use-next-bar-fill",
        action="store_true",
        default=False,
        help="Use next-bar-open fills instead of same-bar-close fills.",
    )
    parser.add_argument(
        "--paper-close-at-end",
        action="store_true",
        default=False,
        help="Force-close open paper positions at the end of the session replay.",
    )
    parser.add_argument(
        "--regime-policy-json",
        type=str,
        default="",
        help="Optional regime policy JSON artifact to reuse.",
    )
    return parser.parse_args()


def interval_to_timeframe(interval: str) -> Timeframe:
    mapping = {
        "day": Timeframe.DAILY,
        "5minute": Timeframe.MINUTE_5,
        "15minute": Timeframe.MINUTE_15,
        "60minute": Timeframe.HOURLY,
    }
    try:
        return mapping[interval]
    except KeyError as exc:  # pragma: no cover
        raise ValueError(f"Unsupported interval: {interval}") from exc


def timeframe_to_filename_suffix(timeframe: Timeframe) -> str:
    mapping = {
        Timeframe.DAILY: "1D",
        Timeframe.MINUTE_5: "5M",
        Timeframe.MINUTE_15: "15M",
        Timeframe.HOURLY: "1H",
        Timeframe.MINUTE_1: "1M",
    }
    return mapping[timeframe]


def build_strategy_registry(selected: list[str]) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {
        "sma": {
            "class": SMACrossoverStrategy,
            "params": {"fast_period": 20, "slow_period": 50},
        },
        "rsi": {
            "class": RSIReversionStrategy,
            "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
        },
        "breakout": {
            "class": BreakoutStrategy,
            "params": {"entry_period": 20, "exit_period": 10},
        },
    }
    return {name: registry[name] for name in selected}


def resolve_symbols(args: argparse.Namespace) -> list[str]:
    loader = NSEUniverseLoader()
    if args.symbols:
        symbols = loader.normalize_symbols(args.symbols)
    elif args.universe.lower() in {"custom", "csv"}:
        if not args.universe_file:
            raise ValueError("--universe-file is required when --universe custom is used")
        symbols = loader.get_custom_universe(args.universe_file)
    else:
        symbols = loader.get_universe(args.universe, args.universe_file or None)

    if args.symbols_limit and args.symbols_limit > 0:
        return symbols[: args.symbols_limit]
    return symbols


def load_regime_policy(path_value: str) -> Optional[RegimePolicy]:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    return RegimePolicy.load_json(path)


def load_symbol_data(
    symbols: list[str],
    provider_name: str,
    timeframe: Timeframe,
    days: int,
) -> dict[str, DataHandler]:
    factory = ProviderFactory.from_config()
    provider = provider_name or factory.config.default_provider
    mapper = SymbolMapper()
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    data: dict[str, DataHandler] = {}

    for symbol in symbols:
        base_symbol = mapper.to_zerodha(symbol)
        try:
            if provider in {"csv", "indian_csv"}:
                file_path = Path("data") / f"{base_symbol}_{timeframe_to_filename_suffix(timeframe)}.csv"
                source = factory.create(provider, data_file=str(file_path))
                data[symbol] = DataHandler.from_source(source)
                continue

            if provider == "zerodha":
                source = factory.create("zerodha")
                df = source.fetch_historical(base_symbol, timeframe, start, end)
                data[symbol] = DataHandler(df)
                continue

            if provider == "upstox":
                source = factory.create("upstox")
                df = source.fetch_historical(base_symbol, timeframe, start, end)
                data[symbol] = DataHandler(df)
                continue

            raise ValueError(f"Unsupported provider: {provider}")
        except Exception:
            fallback_path = Path("data") / f"{base_symbol}_{timeframe_to_filename_suffix(timeframe)}.csv"
            if fallback_path.exists():
                source = factory.create("indian_csv", data_file=str(fallback_path))
                data[symbol] = DataHandler.from_source(source)
    return data


def main() -> int:
    args = parse_args()
    if not args.paper_trading:
        print("Paper trading is OFF by default. Re-run with --paper-trading to execute a safe paper session.")
        return 0

    timeframe = interval_to_timeframe(args.interval)
    symbols = resolve_symbols(args)
    symbol_to_data = load_symbol_data(
        symbols=symbols,
        provider_name=args.provider,
        timeframe=timeframe,
        days=args.days,
    )
    if not symbol_to_data:
        print("No symbol data could be loaded for the requested paper session.")
        return 1

    regime_policy = load_regime_policy(args.regime_policy_json)
    paper_config = PaperTradingConfig(
        enabled=True,
        initial_capital=args.paper_capital,
        max_orders_per_session=args.paper_max_orders,
        use_next_bar_fill=bool(args.paper_use_next_bar_fill),
        output_dir=args.paper_output_dir,
        session_date=(pd.Timestamp(args.paper_session_date) if args.paper_session_date else None),
        close_open_positions_at_end=bool(args.paper_close_at_end),
    )

    base_config = BacktestConfig(
        initial_capital=args.paper_capital,
        execution_mode=(
            ExecutionMode.NEXT_BAR_OPEN
            if args.paper_use_next_bar_fill
            else ExecutionMode.SAME_BAR_CLOSE
        ),
    )

    state_store = PaperStateStore(Path(args.paper_output_dir) / "paper_state.json")
    engine = PaperTradingEngine(
        strategy_registry=build_strategy_registry(args.strategies),
        base_config=base_config,
        paper_config=paper_config,
        regime_policy=regime_policy,
        state_store=state_store,
    )
    result = engine.run(symbol_to_data)

    if result.state is None:
        print("Paper session completed without a state object.")
        return 1

    print("PAPER TRADING SESSION COMPLETE")
    print(f"Symbols evaluated : {len(result.symbols_evaluated)}")
    print(f"Orders created    : {len(result.state.orders)}")
    print(f"Fills simulated   : {len(result.state.fills)}")
    print(f"Open positions    : {len(result.state.open_positions)}")
    print(f"Closed positions  : {len(result.state.closed_positions)}")
    print(f"Realized PnL      : {result.state.realized_pnl:,.2f}")
    print(f"Unrealized PnL    : {result.state.unrealized_pnl:,.2f}")
    if result.exports:
        print("Artifacts:")
        for name, path in sorted(result.exports.items()):
            print(f"  {name:<22} {path}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    if result.errors:
        print("Errors:")
        for error in result.errors:
            print(f"  - {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
