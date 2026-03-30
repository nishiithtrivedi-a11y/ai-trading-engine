#!/usr/bin/env python3
"""
Resumable regime x strategy matrix research runner.

Scope:
- intraday strategy inventory (registry + intraday folder audit)
- backtest matrix across strategy x symbol x timeframe x time window
- professional regime classification per run slice
- checkpoint/resume with incremental artifacts
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.data.nse_universe import NSEUniverseLoader
from src.data.provider_factory import ProviderFactory, ProviderError
from src.market_intelligence.professional_regime import (
    ProfessionalRegimeClassifier,
    ProfessionalRegimeConfig,
)
from src.market_intelligence.regime_engine import MarketRegimeEngine, MarketRegimeEngineConfig
from src.research.regime_strategy_matrix import (
    build_regime_strategy_matrix,
    build_regime_strategy_summary,
    infer_strategy_archetype,
    select_top_candidates_by_regime,
    write_research_markdown,
)
from src.scanners.data_gateway import DataGateway
from src.strategies.registry import create_strategy, get_strategies_by_category, get_strategy_catalog
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


def _print(msg: str, *, quiet: bool = False, force: bool = False) -> None:
    if force or not quiet:
        print(msg)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run resumable regime x strategy matrix research.")
    p.add_argument("--output-dir", default="output/regime_strategy_matrix")
    p.add_argument("--provider", default="auto", choices=["auto", "zerodha", "csv", "indian_csv"])
    p.add_argument("--data-dir", default="data")
    p.add_argument("--symbols", nargs="*", default=[])
    p.add_argument("--symbols-limit", type=int, default=0)
    p.add_argument("--timeframes", default="5m,15m")
    p.add_argument("--window-count", type=int, default=3)
    p.add_argument("--min-window-bars", type=int, default=220)
    p.add_argument("--days", type=int, default=720, help="Lookback days for provider fetches.")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--max-units", type=int, default=0, help="Optional cap for debugging runs (0=all).")
    p.add_argument("--initial-capital", type=float, default=100_000.0)
    p.add_argument("--fee-rate", type=float, default=0.001)
    p.add_argument("--slippage-rate", type=float, default=0.0005)
    args = p.parse_args()

    if args.symbols_limit < 0:
        p.error("--symbols-limit must be >= 0")
    if args.window_count < 1:
        p.error("--window-count must be >= 1")
    if args.min_window_bars < 20:
        p.error("--min-window-bars must be >= 20")
    if args.days < 30:
        p.error("--days must be >= 30")
    if args.max_units < 0:
        p.error("--max-units must be >= 0")
    return args


def _parse_timeframes(raw: str) -> list[str]:
    mapping = {
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "60m": "1h",
        "5minute": "5m",
        "15minute": "15m",
        "60minute": "1h",
    }
    out: list[str] = []
    for token in str(raw).split(","):
        clean = token.strip().lower()
        if not clean:
            continue
        if clean not in mapping:
            raise ValueError(f"Unsupported timeframe: {clean}")
        out.append(mapping[clean])
    deduped = list(dict.fromkeys(out))
    if not deduped:
        raise ValueError("No valid timeframes provided")
    return deduped


def _tf_suffix(tf: str) -> str:
    return {"5m": "5M", "15m": "15M", "1h": "1H"}[tf]


def _discover_csv_symbols(
    *,
    data_dir: Path,
    timeframes: list[str],
    nifty_set: set[str],
) -> list[str]:
    sets: list[set[str]] = []
    for tf in timeframes:
        suffix = _tf_suffix(tf)
        tf_syms: set[str] = set()
        for fp in data_dir.glob(f"*_{suffix}.csv"):
            stem = fp.stem
            if stem.endswith(f"_{suffix}"):
                tf_syms.add(stem[: -len(f"_{suffix}")].upper())
        sets.append(tf_syms)
    if not sets:
        return []
    intersection = set.intersection(*sets)
    if nifty_set:
        intersection &= nifty_set
    return sorted(intersection)


def _resolve_provider(
    provider_arg: str,
    *,
    quiet: bool,
) -> tuple[str, str]:
    if provider_arg in {"csv", "indian_csv", "zerodha"}:
        return provider_arg, f"provider={provider_arg} (explicit)"

    factory = ProviderFactory.from_config()
    try:
        factory.create("zerodha")
        return "zerodha", "provider=zerodha (auto detected credentials)"
    except Exception as exc:  # noqa: BLE001
        return "indian_csv", f"provider=indian_csv (auto fallback: {exc})"


def _make_strategy_inventory(
    *,
    output_dir: Path,
    quiet: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    catalog = get_strategy_catalog()
    intraday_keys = sorted(get_strategies_by_category().get("intraday", []))
    intraday_dir = ROOT / "src" / "strategies" / "intraday"
    intraday_files = sorted(fp for fp in intraday_dir.glob("*.py") if fp.name != "__init__.py")

    include_rows: list[dict[str, Any]] = []
    exclude_rows: list[dict[str, Any]] = []
    module_paths_in_registry: set[Path] = set()

    for key in intraday_keys:
        entry = catalog.get(key)
        if not entry:
            exclude_rows.append(
                {
                    "strategy_key": key,
                    "file_path": None,
                    "archetype": infer_strategy_archetype(key),
                    "factory_ok": False,
                    "include_in_research": False,
                    "reason": "missing_catalog_entry",
                }
            )
            continue

        module = str(entry.get("module", ""))
        rel_path = module.replace(".", "/") + ".py"
        file_path = ROOT / rel_path
        module_paths_in_registry.add(file_path.resolve())
        try:
            _ = create_strategy(key)
            factory_ok = True
            reason = "wired_via_registry"
        except Exception as exc:  # noqa: BLE001
            factory_ok = False
            reason = f"factory_error: {exc}"

        row = {
            "strategy_key": key,
            "file_path": str(file_path),
            "archetype": infer_strategy_archetype(key),
            "factory_ok": factory_ok,
            "include_in_research": bool(factory_ok),
            "reason": reason,
        }
        if factory_ok:
            include_rows.append(row)
        else:
            exclude_rows.append(row)

    for fp in intraday_files:
        resolved = fp.resolve()
        if resolved in module_paths_in_registry:
            continue
        exclude_rows.append(
            {
                "strategy_key": None,
                "file_path": str(fp),
                "file_name": fp.name,
                "archetype": infer_strategy_archetype(fp.stem),
                "factory_ok": False,
                "include_in_research": False,
                "reason": "present_in_intraday_folder_but_not_registered",
            }
        )

    include_df = pd.DataFrame(include_rows).sort_values("strategy_key").reset_index(drop=True)
    exclude_df = pd.DataFrame(exclude_rows).sort_values(["reason", "strategy_key"], na_position="last").reset_index(drop=True)

    include_df.to_csv(output_dir / "strategy_inventory.csv", index=False)
    exclude_df.to_csv(output_dir / "excluded_strategies.csv", index=False)
    _print(f"[inventory] included={len(include_df)} excluded={len(exclude_df)}", quiet=quiet)
    return include_df, exclude_df


def _build_windows(
    df: pd.DataFrame,
    *,
    window_count: int,
    min_window_bars: int,
) -> list[dict[str, Any]]:
    n = len(df)
    if n <= min_window_bars:
        return [
            {
                "window_id": "W1",
                "start_idx": 0,
                "end_idx": n,
                "start_ts": pd.Timestamp(df.index[0]),
                "end_ts": pd.Timestamp(df.index[-1]),
                "bars": n,
            }
        ]

    windows: list[dict[str, Any]] = []
    chunk = max(int(n / window_count), min_window_bars)
    start = 0
    idx = 1
    while start < n:
        end = min(n, start + chunk)
        if end - start < min_window_bars:
            if windows:
                windows[-1]["end_idx"] = n
                windows[-1]["end_ts"] = pd.Timestamp(df.index[-1])
                windows[-1]["bars"] = int(windows[-1]["end_idx"] - windows[-1]["start_idx"])
            break
        windows.append(
            {
                "window_id": f"W{idx}",
                "start_idx": start,
                "end_idx": end,
                "start_ts": pd.Timestamp(df.index[start]),
                "end_ts": pd.Timestamp(df.index[end - 1]),
                "bars": end - start,
            }
        )
        start = end
        idx += 1
        if len(windows) >= window_count:
            if windows[-1]["end_idx"] < n:
                windows[-1]["end_idx"] = n
                windows[-1]["end_ts"] = pd.Timestamp(df.index[-1])
                windows[-1]["bars"] = int(windows[-1]["end_idx"] - windows[-1]["start_idx"])
            break

    return windows


def _load_csv_symbol_timeframe(
    *,
    data_dir: Path,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    suffix = _tf_suffix(timeframe)
    bare = str(symbol).replace(".NS", "").upper()
    candidates = [
        data_dir / f"{bare}_{suffix}.csv",
        data_dir / f"{bare}_{suffix}_2024.csv",
        data_dir / f"{bare}_KITE_{suffix}.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        raise FileNotFoundError(f"no CSV found for {bare} [{timeframe}] in {data_dir}")

    df = pd.read_csv(path)
    ts_col = None
    for candidate in ("timestamp", "date", "datetime", "time"):
        if candidate in df.columns:
            ts_col = candidate
            break
    if ts_col is None:
        raise ValueError(f"timestamp column not found in {path}")

    parsed = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    if parsed.isna().any():
        bad = int(parsed.isna().sum())
        raise ValueError(f"failed to parse {bad} timestamps in {path.name}")
    df = df.copy()
    df["timestamp"] = parsed
    df = df.set_index("timestamp").sort_index()
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required OHLCV columns in {path.name}: {sorted(missing)}")
    return df[["open", "high", "low", "close", "volume"]]


def _append_row_csv(path: Path, row: dict[str, Any]) -> None:
    df = pd.DataFrame([row])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _config_hash(
    *,
    provider: str,
    symbols: list[str],
    strategy_keys: list[str],
    timeframes: list[str],
    args: argparse.Namespace,
) -> str:
    blob = json.dumps(
        {
            "provider": provider,
            "symbols": symbols,
            "timeframes": timeframes,
            "strategies": strategy_keys,
            "window_count": args.window_count,
            "min_window_bars": args.min_window_bars,
            "days": args.days,
            "initial_capital": args.initial_capital,
            "fee_rate": args.fee_rate,
            "slippage_rate": args.slippage_rate,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_checkpoint(
    checkpoint_path: Path,
    *,
    config_hash: str,
    quiet: bool,
) -> set[str]:
    if not checkpoint_path.exists():
        return set()
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if payload.get("config_hash") != config_hash:
            _print("[resume] checkpoint hash mismatch, ignoring previous state", quiet=quiet)
            return set()
        completed = payload.get("completed_units", [])
        if not isinstance(completed, list):
            return set()
        return {str(v) for v in completed}
    except Exception as exc:  # noqa: BLE001
        _print(f"[resume] failed to load checkpoint: {exc}", quiet=quiet, force=True)
        return set()


def _write_checkpoint(
    checkpoint_path: Path,
    *,
    config_hash: str,
    completed_units: set[str],
    total_units: int,
    error_count: int,
) -> None:
    payload = {
        "config_hash": config_hash,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "completed_units": sorted(completed_units),
        "completed_count": len(completed_units),
        "total_units": total_units,
        "error_count": error_count,
    }
    tmp = checkpoint_path.with_suffix(".tmp")
    _write_json(tmp, payload)
    tmp.replace(checkpoint_path)


def _safe_metric(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = metrics.get(key, default)
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return float(default)


def _backtest_config(args: argparse.Namespace, *, output_dir: Path) -> BacktestConfig:
    return BacktestConfig(
        initial_capital=float(args.initial_capital),
        fee_rate=float(args.fee_rate),
        slippage_rate=float(args.slippage_rate),
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.30,
        intraday=True,
        force_square_off_at_close=True,
        allow_entries_only_during_market_hours=True,
        market_timezone="Asia/Kolkata",
        close_positions_at_end=True,
        risk=RiskConfig(
            stop_loss_pct=0.015,
            trailing_stop_pct=0.010,
        ),
        output_dir=str(output_dir / "backtests_tmp"),
    )


def main() -> int:
    args = parse_args()
    timeframes = _parse_timeframes(args.timeframes)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = output_dir / "checkpoint.json"
    resume_state_path = output_dir / "resume_state.json"
    strategy_results_path = output_dir / "strategy_results.csv"
    regime_results_path = output_dir / "strategy_regime_results.csv"
    summary_path = output_dir / "strategy_regime_summary.csv"
    matrix_path = output_dir / "regime_strategy_matrix.csv"
    top_path = output_dir / "top_candidates_by_regime.csv"
    errors_path = output_dir / "errors.csv"
    run_manifest_path = output_dir / "run_manifest.json"

    _print("[phase] provider + universe resolution", quiet=args.quiet)
    provider_name, provider_note = _resolve_provider(args.provider, quiet=args.quiet)
    _print(f"[provider] {provider_note}", quiet=args.quiet)

    loader = NSEUniverseLoader()
    nifty_universe = loader.get_universe("nifty50")
    nifty_set = {str(s).replace(".NS", "").upper() for s in nifty_universe}

    explicit_symbols = [str(s).replace(".NS", "").upper() for s in args.symbols if str(s).strip()]
    if explicit_symbols:
        symbols = sorted(dict.fromkeys(explicit_symbols))
    elif provider_name in {"csv", "indian_csv"}:
        symbols = _discover_csv_symbols(
            data_dir=Path(args.data_dir),
            timeframes=timeframes,
            nifty_set=nifty_set,
        )
    else:
        symbols = sorted(nifty_set)

    if args.symbols_limit > 0:
        symbols = symbols[: int(args.symbols_limit)]
    if not symbols:
        raise SystemExit("No symbols resolved for matrix run")

    _print(f"[universe] symbols={len(symbols)} timeframes={timeframes}", quiet=args.quiet)

    _print("[phase] strategy inventory", quiet=args.quiet)
    include_df, exclude_df = _make_strategy_inventory(output_dir=output_dir, quiet=args.quiet)
    strategy_keys = include_df["strategy_key"].astype(str).tolist()
    if not strategy_keys:
        raise SystemExit("No runnable intraday strategies found in registry")

    _print("[phase] data loading + windowing", quiet=args.quiet)
    gateway = DataGateway(provider_name=provider_name, data_dir=args.data_dir)
    start_dt = datetime.now() - timedelta(days=int(args.days))
    end_dt = datetime.now()

    data_cache: dict[tuple[str, str], pd.DataFrame] = {}
    windows_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    data_errors: list[dict[str, Any]] = []

    for symbol in symbols:
        for tf in timeframes:
            try:
                if provider_name in {"csv", "indian_csv"}:
                    df = _load_csv_symbol_timeframe(
                        data_dir=Path(args.data_dir),
                        symbol=symbol,
                        timeframe=tf,
                    )
                else:
                    dh = gateway.load_data(symbol=symbol, timeframe=tf, start=start_dt, end=end_dt)
                    df = dh.data.copy()
                if df is None or df.empty:
                    raise ValueError("empty dataframe")
                data_cache[(symbol, tf)] = df
                windows_cache[(symbol, tf)] = _build_windows(
                    df,
                    window_count=int(args.window_count),
                    min_window_bars=int(args.min_window_bars),
                )
            except Exception as exc:  # noqa: BLE001
                data_errors.append(
                    {
                        "symbol": symbol,
                        "timeframe": tf,
                        "error": str(exc),
                        "stage": "data_load",
                    }
                )

    if data_errors:
        for row in data_errors:
            _append_row_csv(errors_path, row)
    if not data_cache:
        raise SystemExit("No symbol/timeframe data available for research run")

    units: list[dict[str, Any]] = []
    for strategy_key in strategy_keys:
        for (symbol, tf), windows in windows_cache.items():
            if not windows:
                continue
            for win in windows:
                unit_key = f"{strategy_key}|{symbol}|{tf}|{win['window_id']}"
                units.append(
                    {
                        "unit_key": unit_key,
                        "strategy": strategy_key,
                        "archetype": infer_strategy_archetype(strategy_key),
                        "symbol": symbol,
                        "timeframe": tf,
                        "window_id": win["window_id"],
                        "start_idx": int(win["start_idx"]),
                        "end_idx": int(win["end_idx"]),
                        "window_start": str(win["start_ts"]),
                        "window_end": str(win["end_ts"]),
                        "window_bars": int(win["bars"]),
                    }
                )

    if args.max_units and args.max_units > 0:
        units = units[: int(args.max_units)]
    if not units:
        raise SystemExit("No runnable units resolved for matrix")

    cfg_hash = _config_hash(
        provider=provider_name,
        symbols=symbols,
        strategy_keys=strategy_keys,
        timeframes=timeframes,
        args=args,
    )
    completed_units: set[str] = set()
    if args.resume:
        completed_units |= _load_checkpoint(checkpoint_path, config_hash=cfg_hash, quiet=args.quiet)
        if strategy_results_path.exists():
            try:
                existing = pd.read_csv(strategy_results_path, usecols=["unit_key"])
                completed_units |= set(existing["unit_key"].dropna().astype(str).tolist())
            except Exception:
                pass

    remaining_units = [u for u in units if u["unit_key"] not in completed_units]
    _print(
        f"[phase] run matrix units total={len(units)} completed={len(completed_units)} pending={len(remaining_units)}",
        quiet=args.quiet,
    )

    regime_engine = MarketRegimeEngine()
    regime_cfg = MarketRegimeEngineConfig(symbol="NIFTY50", long_ma_period=200)
    pro_classifier = ProfessionalRegimeClassifier(config=ProfessionalRegimeConfig())
    bt_config = _backtest_config(args, output_dir=output_dir)

    error_count = 0
    for idx, unit in enumerate(remaining_units, start=1):
        unit_key = unit["unit_key"]
        symbol = unit["symbol"]
        tf = unit["timeframe"]
        strategy_key = unit["strategy"]

        try:
            df_full = data_cache[(symbol, tf)]
            df_slice = df_full.iloc[unit["start_idx"] : unit["end_idx"]].copy()
            if len(df_slice) < int(args.min_window_bars):
                raise ValueError(
                    f"window too short for backtest: {len(df_slice)} < {int(args.min_window_bars)}"
                )

            strategy = create_strategy(strategy_key)
            engine = BacktestEngine(bt_config, strategy, DataHandler(df_slice))
            metrics_obj = engine.run()
            metrics = metrics_obj.metrics

            try:
                legacy_snapshot = regime_engine.detect(df_slice, config=regime_cfg, symbol=symbol)
            except Exception:
                legacy_snapshot = None
            professional_snapshot = pro_classifier.detect(
                df_slice,
                symbol=symbol,
                legacy_snapshot=legacy_snapshot,
            )

            avg_bars_held = (
                metrics.get("avg_bars_held")
                or metrics.get("average_bars_held")
                or metrics.get("avg_holding_bars")
                or 0.0
            )
            result_row = {
                "unit_key": unit_key,
                "symbol": symbol,
                "timeframe": tf,
                "window_id": unit["window_id"],
                "window_start": unit["window_start"],
                "window_end": unit["window_end"],
                "window_bars": unit["window_bars"],
                "strategy": strategy_key,
                "archetype": unit["archetype"],
                "regime_label": professional_snapshot.regime.value,
                "legacy_regime_label": professional_snapshot.legacy_composite_regime,
                "regime_reason": professional_snapshot.reason,
                "trend_score": professional_snapshot.trend_score,
                "atr_ratio": professional_snapshot.atr_ratio,
                "range_width": professional_snapshot.range_width,
                "path_efficiency": professional_snapshot.path_efficiency,
                "crossover_count": professional_snapshot.crossover_count,
                "total_return_pct": _safe_metric(metrics, "total_return_pct"),
                "max_drawdown_pct": _safe_metric(metrics, "max_drawdown_pct"),
                "profit_factor": _safe_metric(metrics, "profit_factor"),
                "expectancy": _safe_metric(metrics, "expectancy"),
                "sharpe_ratio": _safe_metric(metrics, "sharpe_ratio"),
                "sortino_ratio": _safe_metric(metrics, "sortino_ratio"),
                "num_trades": _safe_metric(metrics, "num_trades"),
                "win_rate": _safe_metric(metrics, "win_rate"),
                "avg_bars_held": float(avg_bars_held),
                "exposure_pct": _safe_metric(metrics, "exposure_pct"),
                "total_fees": _safe_metric(metrics, "total_fees"),
                "run_timestamp": datetime.now(timezone.utc).isoformat(),
            }
            _append_row_csv(strategy_results_path, result_row)
            completed_units.add(unit_key)
            _write_checkpoint(
                checkpoint_path,
                config_hash=cfg_hash,
                completed_units=completed_units,
                total_units=len(units),
                error_count=error_count,
            )
            if idx % 25 == 0 or idx == len(remaining_units):
                _print(
                    f"[progress] {idx}/{len(remaining_units)} pending units processed",
                    quiet=args.quiet,
                )
        except Exception as exc:  # noqa: BLE001
            error_count += 1
            _append_row_csv(
                errors_path,
                {
                    "unit_key": unit_key,
                    "symbol": symbol,
                    "timeframe": tf,
                    "strategy": strategy_key,
                    "window_id": unit["window_id"],
                    "error": str(exc),
                    "stage": "backtest",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            _write_checkpoint(
                checkpoint_path,
                config_hash=cfg_hash,
                completed_units=completed_units,
                total_units=len(units),
                error_count=error_count,
            )

    # Summary artifacts
    if not strategy_results_path.exists():
        raise SystemExit("No strategy results produced; cannot build matrix artifacts")

    results_df = pd.read_csv(strategy_results_path)
    results_df.to_csv(regime_results_path, index=False)

    summary_df = build_regime_strategy_summary(results_df)
    summary_df.to_csv(summary_path, index=False)

    matrix_df = build_regime_strategy_matrix(summary_df, value_col="balanced_score")
    matrix_df.to_csv(matrix_path, index=False)

    top_df = select_top_candidates_by_regime(summary_df, top_n=2)
    top_df.to_csv(top_path, index=False)

    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": provider_name,
        "symbols_tested": len(set(results_df["symbol"].astype(str))),
        "timeframes_tested": ", ".join(sorted(set(results_df["timeframe"].astype(str)))),
        "strategies_tested": len(set(results_df["strategy"].astype(str))),
        "units_total": len(units),
        "units_completed": len(completed_units),
        "errors": error_count,
        "resume_mode": bool(args.resume),
    }
    research_log_path = write_research_markdown(
        summary_df=summary_df,
        candidates_df=top_df,
        excluded_df=exclude_df,
        output_path=output_dir / "research_log.md",
        metadata=metadata,
    )

    manifest = {
        "schema_version": "v1",
        "runner": "scripts.run_regime_strategy_matrix",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_hash": cfg_hash,
        "provider": provider_name,
        "symbols": symbols,
        "timeframes": timeframes,
        "window_count": int(args.window_count),
        "min_window_bars": int(args.min_window_bars),
        "strategies": strategy_keys,
        "artifacts": {
            "checkpoint": str(checkpoint_path),
            "resume_state": str(resume_state_path),
            "strategy_inventory": str(output_dir / "strategy_inventory.csv"),
            "excluded_strategies": str(output_dir / "excluded_strategies.csv"),
            "strategy_results": str(strategy_results_path),
            "strategy_regime_results": str(regime_results_path),
            "strategy_regime_summary": str(summary_path),
            "regime_strategy_matrix": str(matrix_path),
            "top_candidates_by_regime": str(top_path),
            "errors": str(errors_path),
            "research_log": str(research_log_path),
        },
        "stats": {
            "units_total": len(units),
            "units_completed": len(completed_units),
            "units_pending": max(0, len(units) - len(completed_units)),
            "errors": error_count,
        },
    }
    _write_json(run_manifest_path, manifest)
    _write_json(
        resume_state_path,
        {
            "config_hash": cfg_hash,
            "completed_units": sorted(completed_units),
            "total_units": len(units),
            "pending_units": max(0, len(units) - len(completed_units)),
            "errors": error_count,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    _print("[done] regime matrix research complete", quiet=args.quiet, force=True)
    _print(f"  output_dir: {output_dir.resolve()}", quiet=args.quiet, force=True)
    _print(f"  run_manifest: {run_manifest_path.resolve()}", quiet=args.quiet, force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
