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
import json
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
from src.execution.cost_model import CostConfig, CostModel  # noqa: E402
from src.paper_trading import (  # noqa: E402
    PaperStateStore,
    PaperTradingConfig,
    PaperTradingEngine,
)
from src.runtime import (  # noqa: E402
    RunMode,
    RunnerValidationError,
    assert_artifact_contract,
    enforce_runtime_safety,
    get_artifact_contract,
    normalize_fee_inputs,
    validate_provider_for_mode,
    validate_symbol_inputs,
    write_output_manifest,
)
from src.strategies.registry import (  # noqa: E402
    UnsupportedStrategyError,
    resolve_package,
    resolve_strategy,
)
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
        "--strategy", nargs="+",
        default=[],
        help="Specific strategies available to regime-aware selection.",
    )
    parser.add_argument(
        "--package", nargs="+",
        default=[],
        help="Strategy packages available to regime-aware selection.",
    )
    parser.add_argument("--paper-capital", type=float, default=100_000.0, help="Initial paper capital.")
    parser.add_argument(
        "--paper-output-dir",
        "--output-dir",
        type=str,
        dest="paper_output_dir",
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
        "--commission-bps",
        type=float,
        default=10.0,
        help="Paper cost-model commission in bps (default: 10.0).",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=5.0,
        help="Paper cost-model slippage in bps (default: 5.0).",
    )
    fill_mode = parser.add_mutually_exclusive_group()
    fill_mode.add_argument(
        "--paper-use-next-bar-fill",
        "--use-next-bar-fill",
        dest="paper_use_next_bar_fill",
        action="store_true",
        help="Use next-bar-open fills.",
    )
    fill_mode.add_argument(
        "--paper-use-same-bar-fill",
        "--use-same-bar-fill",
        dest="paper_use_next_bar_fill",
        action="store_false",
        help="Use same-bar-close fills.",
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
    parser.add_argument(
        "--portfolio-plan-json",
        type=str,
        default="",
        help=(
            "Optional portfolio_plan.json from run_decision. "
            "When provided, recommended quantities can cap paper sizing and "
            "drawdown no_new_risk mode can block new BUY entries."
        ),
    )
    parser.set_defaults(paper_use_next_bar_fill=False)
    args = parser.parse_args()
    try:
        if args.symbols_limit < 0:
            raise RunnerValidationError("--symbols-limit must be >= 0")
        if args.days < 1:
            raise RunnerValidationError("--days must be >= 1")
        if args.paper_capital <= 0:
            raise RunnerValidationError("--paper-capital must be > 0")
        if args.paper_max_orders < 1:
            raise RunnerValidationError("--paper-max-orders must be >= 1")
        validate_symbol_inputs(
            symbols=args.symbols,
            universe=args.universe,
            universe_file=args.universe_file,
        )
        normalize_fee_inputs(
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
        )
        if args.paper_session_date:
            pd.Timestamp(args.paper_session_date)
        if args.portfolio_plan_json and not Path(args.portfolio_plan_json).exists():
            raise RunnerValidationError(
                f"--portfolio-plan-json file not found: {args.portfolio_plan_json}"
            )
    except (RunnerValidationError, ValueError) as exc:
        parser.error(str(exc))
    return args


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


def build_strategy_registry(strategies: list[str], packages: list[str]) -> dict[str, dict[str, Any]]:
    unique_specs = {}

    for pkg in packages:
        for spec in resolve_package(pkg):
            unique_specs[spec.key] = spec

    for strat in strategies:
        try:
            spec = resolve_strategy(strat)
            unique_specs[spec.key] = spec
        except UnsupportedStrategyError as e:
            print(f"Warning: {e}")

    if not unique_specs:
        if not strategies and not packages:
            for strat in ["sma_crossover", "rsi_reversion", "breakout"]:
                try:
                    spec = resolve_strategy(strat)
                    unique_specs[spec.key] = spec
                except Exception:
                    pass
        if not unique_specs:
            raise ValueError("No runnable strategies resolved.")

    return {
        key: {
            "class": spec.strategy_class,
            "params": dict(spec.params),
        }
        for key, spec in unique_specs.items()
    }


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


def load_portfolio_plan_overrides(
    path_value: str,
) -> tuple[dict[str, dict[str, Any]], bool, str]:
    if not path_value:
        return {}, True, "normal"
    path = Path(path_value)
    if not path.exists():
        raise ValueError(f"portfolio plan file not found: {path}")

    root = json.loads(path.read_text(encoding="utf-8"))
    plan = root.get("portfolio_plan", root)
    if not isinstance(plan, dict):
        return {}, True, "normal"

    summary = plan.get("summary", {})
    drawdown_mode = str(summary.get("drawdown_mode", "normal"))
    allow_new_risk = drawdown_mode != "no_new_risk"

    rows = plan.get("items", [])
    if not isinstance(rows, list):
        rows = []

    overrides: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("selection_status", "")).strip().lower() == "rejected":
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        overrides[symbol] = row
    return overrides, allow_new_risk, drawdown_mode


def load_symbol_data(
    symbols: list[str],
    provider_name: str,
    timeframe: Timeframe,
    days: int,
    provider_factory: Optional[ProviderFactory] = None,
) -> dict[str, DataHandler]:
    factory = provider_factory or ProviderFactory.from_config()
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
        try:
            enforce_runtime_safety(
                RunMode.PAPER,
                explicit_enable_flag=False,
                execution_requested=False,
            )
        except Exception as exc:  # noqa: BLE001
            print(str(exc))
        return 0

    enforce_runtime_safety(
        RunMode.PAPER,
        explicit_enable_flag=True,
        execution_requested=False,
    )

    timeframe = interval_to_timeframe(args.interval)
    symbols = resolve_symbols(args)
    provider_factory = ProviderFactory.from_config()
    provider_name = args.provider or provider_factory.config.default_provider
    try:
        validate_provider_for_mode(
            provider_name=provider_name,
            mode=RunMode.PAPER,
            timeframe="1D" if timeframe == Timeframe.DAILY else timeframe.value,
        )
    except RunnerValidationError as exc:
        print(f"Provider validation failed: {exc}")
        return 1

    fee_inputs = normalize_fee_inputs(
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
    )

    symbol_to_data = load_symbol_data(
        symbols=symbols,
        provider_name=provider_name,
        timeframe=timeframe,
        days=args.days,
        provider_factory=provider_factory,
    )
    if not symbol_to_data:
        print("No symbol data could be loaded for the requested paper session.")
        return 1

    regime_policy = load_regime_policy(args.regime_policy_json)
    portfolio_overrides, allow_new_risk, drawdown_mode = load_portfolio_plan_overrides(
        args.portfolio_plan_json
    )
    if portfolio_overrides:
        planned_symbols = [symbol for symbol in symbols if symbol in portfolio_overrides]
        if planned_symbols:
            symbols = planned_symbols
            symbol_to_data = {
                symbol: data
                for symbol, data in symbol_to_data.items()
                if symbol in set(planned_symbols)
            }
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
        strategy_registry=build_strategy_registry(strategies=args.strategy, packages=args.package),
        base_config=base_config,
        paper_config=paper_config,
        regime_policy=regime_policy,
        state_store=state_store,
        portfolio_plan_overrides=portfolio_overrides,
        allow_new_risk=allow_new_risk,
        cost_model=CostModel(
            CostConfig(
                commission_bps=fee_inputs.commission_bps,
                slippage_bps=fee_inputs.slippage_bps,
            )
        ),
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
    if portfolio_overrides:
        print(f"Portfolio overrides: {len(portfolio_overrides)} symbols (drawdown_mode={drawdown_mode})")
    if result.exports:
        contract = get_artifact_contract(RunMode.PAPER)
        manifest_artifacts = dict(result.exports)
        manifest_artifacts["run_manifest"] = Path(args.paper_output_dir) / "run_manifest.json"
        manifest_path = write_output_manifest(
            output_dir=args.paper_output_dir,
            run_mode=RunMode.PAPER,
            provider_name=provider_name,
            artifacts=manifest_artifacts,
            metadata={
                "paper_enabled": bool(args.paper_trading),
                "symbols_evaluated": len(result.symbols_evaluated),
                "fill_mode": (
                    "next_bar_open"
                    if args.paper_use_next_bar_fill
                    else "current_bar_close"
                ),
                "commission_bps": fee_inputs.commission_bps,
                "slippage_bps": fee_inputs.slippage_bps,
                "portfolio_overrides_loaded": len(portfolio_overrides),
                "portfolio_drawdown_mode": drawdown_mode,
                "allow_new_risk": allow_new_risk,
            },
            contract_id=contract.contract_id,
            expected_artifacts=contract.required_names,
            schema_version=contract.schema_version,
            safety_mode=contract.safety_mode,
        )
        result.exports["run_manifest"] = str(manifest_path)
        try:
            assert_artifact_contract(
                run_mode=RunMode.PAPER,
                output_dir=args.paper_output_dir,
                manifest_path=manifest_path,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Artifact contract validation failed: {exc}")
            return 1
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
