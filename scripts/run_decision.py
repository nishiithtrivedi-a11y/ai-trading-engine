#!/usr/bin/env python3
"""
Standalone decision operational runner.

Supports:
- standalone decision runs
- monitoring -> decision chaining via explicit monitoring artifact directory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.data.nse_universe import NSEUniverseLoader  # noqa: E402
from src.decision import (  # noqa: E402
    DecisionConfig,
    DecisionExporter,
    DrawdownContext,
    PickEngine,
    PortfolioPlanningConfig,
    PortfolioRiskEngine,
    normalize_allocation_model,
    normalize_sizing_method,
)
from src.monitoring import (  # noqa: E402
    MarketMonitor,
    MonitoringConfig,
    MonitoringRunResult,
    RegimeAssessment,
    RegimeDetectorConfig,
    RegimeState,
    RelativeStrengthConfig,
    RelativeStrengthSnapshot,
    SnapshotConfig,
    WatchlistDefinition,
)
from src.runtime import (  # noqa: E402
    RunMode,
    RunnerArtifactResolutionError,
    assert_artifact_contract,
    enforce_runtime_safety,
    get_artifact_contract_by_id,
    get_runner_schedule_profile,
    load_json_file,
    resolve_latest_runner_dir,
    resolve_runner_output_dir,
    validate_provider_for_mode,
    validate_symbol_inputs,
    write_output_manifest,
    write_runner_artifacts_meta,
)
from src.scanners import (  # noqa: E402
    Opportunity,
    OpportunityClass,
    OpportunitySide,
    ScanResult,
    ScannerConfig,
    StrategyScanSpec,
    normalize_timeframe,
)
from src.strategies.rsi_reversion import RSIReversionStrategy  # noqa: E402
from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone decision workflow.")
    parser.add_argument("--provider", default="indian_csv", help="Provider name.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Explicit symbol list.")
    parser.add_argument("--symbols-file", default="", help="CSV with symbol/ticker column.")
    parser.add_argument("--universe", default="nifty50", help="Universe name.")
    parser.add_argument(
        "--interval",
        default="",
        choices=["", "day", "5minute", "15minute", "60minute", "1D", "5m", "15m", "1h"],
        help="Decision interval override.",
    )
    parser.add_argument(
        "--profile",
        default="eod",
        choices=["morning", "intraday", "eod"],
        help="Operational schedule profile.",
    )
    parser.add_argument("--output-dir", default="output/decision", help="Output root directory.")
    parser.add_argument(
        "--monitoring-input-dir",
        "--input-dir",
        dest="monitoring_input_dir",
        default="",
        help="Optional monitoring artifact directory for chained decision run.",
    )
    parser.add_argument(
        "--use-latest-monitoring-input",
        action="store_true",
        help="Resolve latest monitoring run under output/monitoring when monitoring input is omitted.",
    )
    parser.add_argument("--run-once", action="store_true", help="No-op; accepted for CLI consistency.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Optional max symbols.")
    parser.add_argument("--data-dir", default="data", help="CSV data directory.")
    parser.add_argument(
        "--enable-analysis-features",
        action="store_true",
        help="Enable profile-driven analysis module features in scanner scoring context.",
    )
    parser.add_argument(
        "--analysis-profile",
        default="",
        help="Optional analysis profile name (for example: intraday_equity, swing_equity, macro_swing).",
    )
    parser.add_argument("--paper-handoff", action="store_true", help="Write paper_handoff_candidates.csv.")
    parser.add_argument(
        "--portfolio-capital",
        type=float,
        default=100_000.0,
        help="Total capital used for portfolio allocation and sizing recommendations.",
    )
    parser.add_argument(
        "--allocation-model",
        default="conviction_weighted",
        choices=["equal_weight", "volatility_weighted", "conviction_weighted"],
        help="Portfolio allocation model.",
    )
    parser.add_argument(
        "--sizing-method",
        default="risk_per_trade",
        choices=["fixed_fractional", "risk_per_trade", "atr_based"],
        help="Position sizing method.",
    )
    parser.add_argument(
        "--reserve-cash-pct",
        type=float,
        default=0.10,
        help="Fraction of capital to keep as reserve cash.",
    )
    parser.add_argument(
        "--max-capital-deployed-pct",
        type=float,
        default=0.90,
        help="Maximum fraction of capital to deploy.",
    )
    parser.add_argument(
        "--max-portfolio-positions",
        type=int,
        default=8,
        help="Maximum positions in the portfolio plan.",
    )
    parser.add_argument(
        "--max-per-position-allocation-pct",
        type=float,
        default=0.25,
        help="Maximum per-position allocation as a fraction of total capital.",
    )
    parser.add_argument(
        "--risk-per-trade-pct",
        type=float,
        default=0.01,
        help="Risk budget per trade as a fraction of total capital.",
    )
    parser.add_argument(
        "--max-per-trade-risk-pct",
        type=float,
        default=0.02,
        help="Hard cap for estimated per-trade risk as fraction of capital.",
    )
    parser.add_argument(
        "--max-sector-exposure-pct",
        type=float,
        default=0.40,
        help="Maximum sector exposure as fraction of total capital.",
    )
    parser.add_argument(
        "--max-correlated-positions",
        type=int,
        default=2,
        help="Maximum selected positions within a correlation bucket.",
    )
    parser.add_argument(
        "--drawdown-daily-pct",
        type=float,
        default=0.0,
        help="Current daily drawdown context as a fraction (for drawdown overlays).",
    )
    parser.add_argument(
        "--drawdown-rolling-pct",
        type=float,
        default=0.0,
        help="Current rolling drawdown context as a fraction (for drawdown overlays).",
    )
    parser.add_argument(
        "--max-daily-drawdown-pct",
        type=float,
        default=0.04,
        help="Severe daily drawdown threshold that can pause new risk.",
    )
    parser.add_argument(
        "--max-rolling-drawdown-pct",
        type=float,
        default=0.12,
        help="Severe rolling drawdown threshold that can pause new risk.",
    )
    parser.add_argument(
        "--reduce-risk-daily-drawdown-pct",
        type=float,
        default=0.02,
        help="Daily drawdown threshold for reduced-risk mode.",
    )
    parser.add_argument(
        "--reduce-risk-rolling-drawdown-pct",
        type=float,
        default=0.07,
        help="Rolling drawdown threshold for reduced-risk mode.",
    )
    parser.add_argument(
        "--reduce-risk-multiplier",
        type=float,
        default=0.50,
        help="Allocation/risk multiplier applied in reduced-risk mode.",
    )
    parser.add_argument("--log-level", default="INFO", help="Reserved for future logging control.")
    parser.add_argument(
        "--no-timestamped-output",
        action="store_true",
        help="Write artifacts directly into --output-dir.",
    )
    args = parser.parse_args()

    validate_symbol_inputs(
        symbols=args.symbols,
        universe=args.universe,
        universe_file=args.symbols_file or None,
    )
    if args.max_symbols < 0:
        parser.error("--max-symbols must be >= 0")
    if args.portfolio_capital <= 0:
        parser.error("--portfolio-capital must be > 0")
    if args.max_portfolio_positions < 1:
        parser.error("--max-portfolio-positions must be >= 1")
    if args.max_correlated_positions < 1:
        parser.error("--max-correlated-positions must be >= 1")
    for pct_name in (
        "reserve_cash_pct",
        "max_capital_deployed_pct",
        "max_per_position_allocation_pct",
        "risk_per_trade_pct",
        "max_per_trade_risk_pct",
        "max_sector_exposure_pct",
        "drawdown_daily_pct",
        "drawdown_rolling_pct",
        "max_daily_drawdown_pct",
        "max_rolling_drawdown_pct",
        "reduce_risk_daily_drawdown_pct",
        "reduce_risk_rolling_drawdown_pct",
        "reduce_risk_multiplier",
    ):
        value = float(getattr(args, pct_name))
        if not 0 <= value <= 1:
            parser.error(f"--{pct_name.replace('_', '-')} must be in [0, 1]")
    return args


def _interval_to_timeframe(interval: str, profile_interval: str) -> str:
    if not interval:
        interval = profile_interval
    mapping = {
        "day": "1D",
        "1d": "1D",
        "1D": "1D",
        "5minute": "5m",
        "5m": "5m",
        "15minute": "15m",
        "15m": "15m",
        "60minute": "1h",
        "1h": "1h",
    }
    return normalize_timeframe(mapping.get(str(interval).strip(), str(interval).strip()))


def _resolve_monitoring_input_dir(args: argparse.Namespace) -> Path | None:
    if args.monitoring_input_dir:
        return Path(args.monitoring_input_dir)
    if args.use_latest_monitoring_input:
        return resolve_latest_runner_dir(output_dir="output/monitoring")
    return None


def _opportunity_from_dict(row: dict[str, Any]) -> Opportunity:
    classification = OpportunityClass(str(row.get("classification", "intraday")).strip().lower())
    side = OpportunitySide(str(row.get("side", "long")).strip().lower())
    return Opportunity(
        symbol=str(row.get("symbol", "")).strip().upper(),
        timeframe=str(row.get("timeframe", "1D")),
        strategy_name=str(row.get("strategy_name", "")),
        signal=str(row.get("signal", "hold")),
        timestamp=pd.Timestamp(row.get("timestamp")),
        classification=classification,
        entry_price=float(row.get("entry_price", 0.0)),
        stop_loss=float(row.get("stop_loss", 0.0)),
        target_price=float(row.get("target_price", 0.0)),
        side=side,
        score=float(row.get("score", 0.0)),
        reasons=[str(value) for value in row.get("reasons", [])]
        if isinstance(row.get("reasons"), list)
        else [],
        metadata=dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {},
        score_signal=(float(row["score_signal"]) if row.get("score_signal") is not None else None),
        score_rr=(float(row["score_rr"]) if row.get("score_rr") is not None else None),
        score_trend=(float(row["score_trend"]) if row.get("score_trend") is not None else None),
        score_liquidity=(float(row["score_liquidity"]) if row.get("score_liquidity") is not None else None),
        score_freshness=(float(row["score_freshness"]) if row.get("score_freshness") is not None else None),
        rank=(int(row["rank"]) if row.get("rank") is not None else None),
    )


def _monitoring_result_from_artifacts(monitoring_dir: Path) -> MonitoringRunResult:
    input_path = monitoring_dir / "monitoring_decision_input.json"
    if not input_path.exists():
        raise FileNotFoundError(
            f"monitoring_decision_input.json not found in {monitoring_dir}"
        )

    payload = load_json_file(input_path)
    scan_payload = payload.get("scan_result", {}) if isinstance(payload, dict) else {}
    opportunities = [
        _opportunity_from_dict(row)
        for row in scan_payload.get("opportunities", [])
        if isinstance(row, dict)
    ]
    scan_result = ScanResult(
        opportunities=opportunities,
        universe_name=str(scan_payload.get("universe_name", "")),
        provider_name=str(scan_payload.get("provider_name", "")),
        num_symbols_scanned=int(scan_payload.get("num_symbols_scanned", 0)),
        num_jobs=int(scan_payload.get("num_jobs", 0)),
        num_errors=int(scan_payload.get("num_errors", 0)),
        errors=list(scan_payload.get("errors", [])),
    )

    regime_payload = payload.get("regime_assessment")
    regime_assessment: Optional[RegimeAssessment] = None
    if isinstance(regime_payload, dict) and regime_payload.get("regime"):
        regime_assessment = RegimeAssessment(
            regime=RegimeState(str(regime_payload.get("regime")).strip().lower()),
            timestamp=pd.Timestamp(regime_payload.get("timestamp")),
            trend_score=(
                float(regime_payload["trend_score"])
                if regime_payload.get("trend_score") is not None
                else None
            ),
            volatility_score=(
                float(regime_payload["volatility_score"])
                if regime_payload.get("volatility_score") is not None
                else None
            ),
            range_score=(
                float(regime_payload["range_score"])
                if regime_payload.get("range_score") is not None
                else None
            ),
            reason=str(regime_payload.get("reason", "")),
            metadata=dict(regime_payload.get("metadata", {})),
        )

    rs_rows: list[RelativeStrengthSnapshot] = []
    for row in payload.get("relative_strength", []) if isinstance(payload, dict) else []:
        if not isinstance(row, dict):
            continue
        rs_rows.append(
            RelativeStrengthSnapshot(
                symbol=str(row.get("symbol", "")).strip().upper(),
                score=float(row.get("score", 0.0)),
                lookback_returns=dict(row.get("lookback_returns", {})),
                benchmark_symbol=row.get("benchmark_symbol"),
                relative_return=(
                    float(row["relative_return"]) if row.get("relative_return") is not None else None
                ),
                rank=(int(row["rank"]) if row.get("rank") is not None else None),
                sector=row.get("sector"),
                timestamp=(
                    pd.Timestamp(row["timestamp"])
                    if row.get("timestamp") is not None
                    else pd.Timestamp.now(tz="UTC")
                ),
                metadata=dict(row.get("metadata", {})),
            )
        )

    return MonitoringRunResult(
        scan_result=scan_result,
        regime_assessment=regime_assessment,
        relative_strength=rs_rows,
        warnings=list(payload.get("warnings", [])),
        errors=list(payload.get("errors", [])),
    )


def _resolve_symbols_from_inputs(args: argparse.Namespace) -> list[str]:
    loader = NSEUniverseLoader()
    if args.symbols:
        return loader.normalize_symbols(args.symbols)
    if args.symbols_file:
        return loader.get_custom_universe(args.symbols_file)
    return loader.get_universe(args.universe)


def _build_monitoring_from_symbols(
    *,
    symbols: list[str],
    provider_name: str,
    data_dir: str,
    timeframe: str,
    snapshot_top_n: int,
    enable_analysis_features: bool = False,
    analysis_profile: str = "",
) -> MonitoringRunResult:
    scanner_cfg = ScannerConfig(
        universe_name="custom",
        provider_name=provider_name,
        data_dir=data_dir,
        timeframes=[timeframe],
        strategy_specs=[
            StrategyScanSpec(
                strategy_class=RSIReversionStrategy,
                params={"rsi_period": 14, "oversold": 30, "overbought": 70},
                timeframes=[timeframe],
            ),
            StrategyScanSpec(
                strategy_class=SMACrossoverStrategy,
                params={"fast_period": 20, "slow_period": 50},
                timeframes=[timeframe],
            ),
        ],
        enable_analysis_features=bool(enable_analysis_features),
        analysis_profile=str(analysis_profile).strip(),
    )
    cfg = MonitoringConfig(
        scanner_config=scanner_cfg,
        watchlists=[WatchlistDefinition(name="operational", symbols=symbols)],
        regime=RegimeDetectorConfig(
            benchmark_symbol=symbols[0],
            timeframe=timeframe,
            use_benchmark=True,
            fallback_to_symbol=True,
        ),
        relative_strength=RelativeStrengthConfig(
            benchmark_symbol=symbols[0],
            timeframe=timeframe,
            allow_missing_benchmark=True,
        ),
        snapshot=SnapshotConfig(top_n=max(1, int(snapshot_top_n))),
    )
    monitor = MarketMonitor(config=cfg)
    return monitor.run(export=False, watchlist_names=["operational"])


def _write_summary(
    path: Path,
    *,
    profile: str,
    timeframe: str,
    input_source: str,
    result,
    portfolio_result=None,  # noqa: ANN001
) -> None:
    lines = [
        "# Decision Runner Summary",
        "",
        f"- Generated at: {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- Profile: {profile}",
        f"- Timeframe: {timeframe}",
        f"- Input source: {input_source}",
        f"- Selected picks: {len(result.selected_picks)}",
        f"- Rejected opportunities: {len(result.rejected_opportunities)}",
        f"- Intraday picks: {len(result.top_intraday)}",
        f"- Swing picks: {len(result.top_swing)}",
        f"- Positional picks: {len(result.top_positional)}",
        "",
        "## Top Picks",
        "",
    ]
    if not result.selected_picks:
        lines.append("- No picks selected.")
    else:
        for pick in result.selected_picks[:10]:
            plan = pick.trade_plan
            lines.append(
                f"- `{plan.symbol}` `{plan.strategy_name}` horizon={plan.horizon.value} "
                f"conviction={pick.conviction_score:.2f} rr={plan.risk_reward:.2f}"
            )
    if portfolio_result is not None:
        summary = portfolio_result.summary
        lines += [
            "",
            "## Portfolio Plan",
            "",
            f"- Drawdown mode: {summary.drawdown_mode.value}",
            f"- Allocation model: {summary.allocation_model}",
            f"- Sizing method: {summary.sizing_method}",
            f"- Portfolio selected: {summary.selected_count}",
            f"- Portfolio rejected: {summary.rejected_count}",
            f"- Deployed capital: {summary.deployed_capital:.2f} ({summary.deployed_capital_pct:.2%})",
            f"- Estimated portfolio risk: {summary.estimated_total_risk_amount:.2f} ({summary.estimated_total_risk_pct:.2%})",
        ]
    lines += [
        "",
        "## Safety",
        "- Decision runner is research-only.",
        "- No live broker order placement is performed.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_selected_json(result, output_path: Path) -> Path:
    payload = {
        "schema_version": "v1",
        "generated_at": result.generated_at.isoformat(),
        "source": "scripts.run_decision",
        "selected": [pick.to_dict() for pick in result.selected_picks],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def _write_rejected_json(result, output_path: Path) -> Path:
    payload = {
        "schema_version": "v1",
        "generated_at": result.generated_at.isoformat(),
        "source": "scripts.run_decision",
        "rejected": [row.to_dict() for row in result.rejected_opportunities],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def _write_candidates_csv(result, output_path: Path) -> Path:
    rows = [pick.to_dict() for pick in result.selected_picks]
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def _write_paper_handoff_csv(
    result,
    output_path: Path,
    *,
    portfolio_by_symbol: Optional[dict[str, Any]] = None,
    drawdown_mode: str = "normal",
) -> Path:
    portfolio_by_symbol = portfolio_by_symbol or {}
    rows: list[dict[str, Any]] = []
    for pick in result.selected_picks:
        plan = pick.trade_plan
        portfolio_row = portfolio_by_symbol.get(plan.symbol)
        rows.append(
            {
                "symbol": plan.symbol,
                "timeframe": plan.timeframe,
                "strategy_name": plan.strategy_name,
                "entry_price": plan.entry_price,
                "stop_loss": plan.stop_loss,
                "target_price": plan.target_price,
                "risk_reward": plan.risk_reward,
                "horizon": plan.horizon.value,
                "conviction_score": pick.conviction_score,
                "allocation_amount": (
                    float(portfolio_row.allocation_amount)
                    if portfolio_row is not None
                    else None
                ),
                "allocation_percent": (
                    float(portfolio_row.allocation_percent)
                    if portfolio_row is not None
                    else None
                ),
                "recommended_quantity": (
                    int(portfolio_row.quantity)
                    if portfolio_row is not None
                    else None
                ),
                "sizing_method": (
                    str(portfolio_row.sizing_method)
                    if portfolio_row is not None
                    else None
                ),
                "drawdown_mode": drawdown_mode,
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def _portfolio_config_from_args(args: argparse.Namespace) -> PortfolioPlanningConfig:
    return PortfolioPlanningConfig(
        enabled=True,
        total_capital=float(args.portfolio_capital),
        reserve_cash_pct=float(args.reserve_cash_pct),
        allocation_model=normalize_allocation_model(args.allocation_model),
        sizing_method=normalize_sizing_method(args.sizing_method),
        risk_per_trade_pct=float(args.risk_per_trade_pct),
        max_capital_deployed_pct=float(args.max_capital_deployed_pct),
        max_positions=int(args.max_portfolio_positions),
        max_per_position_allocation_pct=float(args.max_per_position_allocation_pct),
        max_per_trade_risk_pct=float(args.max_per_trade_risk_pct),
        max_sector_exposure_pct=float(args.max_sector_exposure_pct),
        max_correlated_positions=int(args.max_correlated_positions),
        drawdown_daily_reduce_risk_pct=float(args.reduce_risk_daily_drawdown_pct),
        drawdown_rolling_reduce_risk_pct=float(args.reduce_risk_rolling_drawdown_pct),
        max_daily_drawdown_pct=float(args.max_daily_drawdown_pct),
        max_rolling_drawdown_pct=float(args.max_rolling_drawdown_pct),
        reduce_risk_multiplier=float(args.reduce_risk_multiplier),
    )


def _write_portfolio_plan_json(plan_result, output_path: Path) -> Path:  # noqa: ANN001
    payload = {
        "schema_version": "v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "scripts.run_decision.portfolio",
        "portfolio_plan": plan_result.to_dict(),
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def _write_portfolio_plan_csv(plan_result, output_path: Path) -> Path:  # noqa: ANN001
    rows = [item.to_dict() for item in plan_result.items]
    pd.DataFrame(rows).to_csv(output_path, index=False)
    return output_path


def _write_portfolio_risk_summary_json(plan_result, output_path: Path) -> Path:  # noqa: ANN001
    payload = {
        "schema_version": "v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "scripts.run_decision.portfolio",
        "summary": plan_result.summary.to_dict(),
        "warnings": list(plan_result.warnings),
        "errors": list(plan_result.errors),
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def _write_allocation_summary_md(
    plan_result,  # noqa: ANN001
    *,
    output_path: Path,
    profile: str,
    timeframe: str,
) -> Path:
    summary = plan_result.summary
    lines = [
        "# Portfolio Allocation Summary",
        "",
        f"- Generated at: {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- Profile: {profile}",
        f"- Timeframe: {timeframe}",
        f"- Drawdown mode: {summary.drawdown_mode.value}",
        f"- Allocation model: {summary.allocation_model}",
        f"- Sizing method: {summary.sizing_method}",
        f"- Total candidates: {summary.total_candidates}",
        f"- Selected: {summary.selected_count}",
        f"- Resized: {summary.resized_count}",
        f"- Rejected: {summary.rejected_count}",
        f"- Deployed capital: {summary.deployed_capital:.2f} ({summary.deployed_capital_pct:.2%})",
        f"- Reserved cash: {summary.reserved_cash:.2f}",
        f"- Estimated portfolio risk: {summary.estimated_total_risk_amount:.2f} ({summary.estimated_total_risk_pct:.2%})",
        "",
        "## Selected Portfolio Plan",
        "",
    ]
    selected = [item for item in plan_result.items if item.selection_status.value != "rejected"]
    if not selected:
        lines.append("- No positions selected.")
    else:
        for item in selected[:20]:
            lines.append(
                f"- `{item.symbol}` qty={item.quantity} alloc={item.allocation_amount:.2f} "
                f"risk={item.estimated_risk_amount:.2f} status={item.selection_status.value}"
            )
    if plan_result.warnings:
        lines += ["", "## Warnings", ""]
        for warning in plan_result.warnings:
            lines.append(f"- {warning}")

    lines += [
        "",
        "## Safety",
        "- Portfolio plan is recommendation-only.",
        "- No live orders were placed.",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _write_portfolio_artifacts_meta(
    *,
    output_path: Path,
    profile: str,
    provider: str,
    interval: str,
    drawdown_mode: str,
    artifacts: dict[str, str | Path],
    selected_count: int,
    rejected_count: int,
) -> Path:
    payload = {
        "schema_version": "v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "scripts.run_decision.portfolio",
        "runner_name": "decision",
        "profile": profile,
        "provider": provider,
        "interval": interval,
        "execution_mode": "research",
        "drawdown_mode": drawdown_mode,
        "artifacts": {
            name: {"path": str(path), "format": Path(path).suffix.lstrip(".").lower()}
            for name, path in artifacts.items()
        },
        "metadata": {
            "selected_count": selected_count,
            "rejected_count": rejected_count,
        },
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return output_path


def main() -> int:
    args = parse_args()
    enforce_runtime_safety(
        RunMode.RESEARCH,
        explicit_enable_flag=True,
        execution_requested=False,
    )

    profile = get_runner_schedule_profile(args.profile)
    timeframe = _interval_to_timeframe(args.interval, profile.default_interval)
    validate_provider_for_mode(
        provider_name=args.provider,
        mode=RunMode.RESEARCH,
        timeframe=timeframe,
    )

    monitoring_input_dir = _resolve_monitoring_input_dir(args)
    input_source = "standalone"
    if monitoring_input_dir is not None:
        monitoring_result = _monitoring_result_from_artifacts(monitoring_input_dir)
        input_source = f"monitoring:{monitoring_input_dir}"
    else:
        symbols = _resolve_symbols_from_inputs(args)
        symbol_cap = int(args.max_symbols) if int(args.max_symbols) > 0 else int(profile.default_max_symbols)
        if symbol_cap > 0:
            symbols = symbols[:symbol_cap]
        if not symbols:
            raise ValueError("No symbols resolved for standalone decision run")
        monitoring_result = _build_monitoring_from_symbols(
            symbols=symbols,
            provider_name=args.provider,
            data_dir=args.data_dir,
            timeframe=timeframe,
            snapshot_top_n=profile.monitoring_top_picks,
            enable_analysis_features=bool(args.enable_analysis_features),
            analysis_profile=str(args.analysis_profile).strip(),
        )

    decision_cfg = DecisionConfig()
    cap = int(profile.decision_max_picks_per_horizon)
    decision_cfg.thresholds.max_picks_by_horizon = {
        key: cap for key in decision_cfg.thresholds.max_picks_by_horizon
    }
    decision_cfg.portfolio = _portfolio_config_from_args(args)

    out_dir = resolve_runner_output_dir(
        output_dir=args.output_dir,
        runner_name="decision",
        timestamped=not bool(args.no_timestamped_output),
    )
    decision_cfg.export.output_dir = str(out_dir)

    result = PickEngine(decision_config=decision_cfg).run(monitoring_result=monitoring_result)
    exports = DecisionExporter().export_all(result, decision_cfg.export)
    result.exports = {name: str(path) for name, path in exports.items()}

    drawdown_context = DrawdownContext(
        daily_drawdown_pct=float(args.drawdown_daily_pct),
        rolling_drawdown_pct=float(args.drawdown_rolling_pct),
    )
    portfolio_result = PortfolioRiskEngine(config=decision_cfg.portfolio).build_plan(
        result.selected_picks,
        drawdown_context=drawdown_context,
    )
    result.metadata["portfolio_plan_summary"] = portfolio_result.summary.to_dict()
    result.metadata["portfolio_selected_symbols"] = [
        row.symbol for row in portfolio_result.selected_items
    ]

    selected_json = _write_selected_json(result, out_dir / "decision_selected.json")
    rejected_json = _write_rejected_json(result, out_dir / "decision_rejected.json")
    candidates_csv = _write_candidates_csv(result, out_dir / "decision_candidates.csv")
    summary_md = out_dir / "decision_summary.md"
    _write_summary(
        summary_md,
        profile=args.profile,
        timeframe=timeframe,
        input_source=input_source,
        result=result,
        portfolio_result=portfolio_result,
    )

    portfolio_plan_json = _write_portfolio_plan_json(portfolio_result, out_dir / "portfolio_plan.json")
    portfolio_plan_csv = _write_portfolio_plan_csv(portfolio_result, out_dir / "portfolio_plan.csv")
    portfolio_risk_summary_json = _write_portfolio_risk_summary_json(
        portfolio_result,
        out_dir / "portfolio_risk_summary.json",
    )
    allocation_summary_md = _write_allocation_summary_md(
        portfolio_result,
        output_path=out_dir / "allocation_summary.md",
        profile=args.profile,
        timeframe=timeframe,
    )

    artifacts: dict[str, str | Path] = {
        "decision_candidates_csv": candidates_csv,
        "decision_selected_json": selected_json,
        "decision_rejected_json": rejected_json,
        "decision_summary_md": summary_md,
        "decision_summary_json": exports.get("summary_json", out_dir / "decision_summary.json"),
        "portfolio_plan_json": portfolio_plan_json,
        "portfolio_plan_csv": portfolio_plan_csv,
        "portfolio_risk_summary_json": portfolio_risk_summary_json,
        "allocation_summary_md": allocation_summary_md,
    }

    portfolio_meta = _write_portfolio_artifacts_meta(
        output_path=out_dir / "portfolio_artifacts_meta.json",
        profile=args.profile,
        provider=args.provider,
        interval=timeframe,
        drawdown_mode=portfolio_result.summary.drawdown_mode.value,
        artifacts={
            "portfolio_plan_json": portfolio_plan_json,
            "portfolio_plan_csv": portfolio_plan_csv,
            "portfolio_risk_summary_json": portfolio_risk_summary_json,
            "allocation_summary_md": allocation_summary_md,
        },
        selected_count=portfolio_result.summary.selected_count,
        rejected_count=portfolio_result.summary.rejected_count,
    )
    artifacts["portfolio_artifacts_meta"] = portfolio_meta
    if args.paper_handoff:
        portfolio_by_symbol = {
            row.symbol: row for row in portfolio_result.selected_items
        }
        artifacts["paper_handoff_candidates"] = _write_paper_handoff_csv(
            result,
            out_dir / "paper_handoff_candidates.csv",
            portfolio_by_symbol=portfolio_by_symbol,
            drawdown_mode=portfolio_result.summary.drawdown_mode.value,
        )

    meta_path = write_runner_artifacts_meta(
        output_path=out_dir / "decision_artifacts_meta.json",
        runner_name="decision",
        profile=args.profile,
        provider=args.provider,
        interval=timeframe,
        execution_mode="research",
        source="scripts.run_decision",
        artifacts=artifacts,
        metadata={
            "input_source": input_source,
            "selected_total": len(result.selected_picks),
            "rejected_total": len(result.rejected_opportunities),
            "portfolio_selected_total": portfolio_result.summary.selected_count,
            "portfolio_rejected_total": portfolio_result.summary.rejected_count,
            "drawdown_mode": portfolio_result.summary.drawdown_mode.value,
            "paper_handoff": bool(args.paper_handoff),
        },
    )
    artifacts["decision_artifacts_meta"] = meta_path
    artifacts["run_manifest"] = out_dir / "run_manifest.json"

    contract = get_artifact_contract_by_id("decision_runner_v1")
    manifest_path = write_output_manifest(
        output_dir=out_dir,
        run_mode=RunMode.RESEARCH,
        provider_name=args.provider,
        artifacts=artifacts,
        metadata={
            "runner_name": "decision",
            "profile": args.profile,
            "schema_version": "v1",
            "interval": timeframe,
            "execution_mode": "research",
            "input_source": input_source,
            "paper_handoff": bool(args.paper_handoff),
        },
        contract_id=contract.contract_id,
        expected_artifacts=contract.required_names,
        schema_version=contract.schema_version,
        safety_mode=contract.safety_mode,
    )
    assert_artifact_contract(
        contract_id=contract.contract_id,
        output_dir=out_dir,
        manifest_path=manifest_path,
    )

    print("DECISION RUN COMPLETE")
    print(f"  Output dir      : {out_dir}")
    print(f"  Profile         : {args.profile}")
    print(f"  Provider        : {args.provider}")
    print(f"  Timeframe       : {timeframe}")
    print(f"  Selected picks  : {len(result.selected_picks)}")
    print(f"  Rejected picks  : {len(result.rejected_opportunities)}")
    print(f"  Manifest        : {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RunnerArtifactResolutionError, FileNotFoundError, ValueError) as exc:
        print(f"Input resolution failed: {exc}")
        raise SystemExit(1) from exc
