"""
Output file loaders for the Streamlit dashboard.

Reads CSV/JSON export artifacts produced by earlier phases.
All loaders return (data, error_message) tuples so the UI can
show graceful empty states without crashing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

# Default output root (relative to project root)
DEFAULT_OUTPUT_DIR = "output"


def _resolve_output_dir(output_dir: Optional[str] = None) -> Path:
    """Resolve the output directory path."""
    return Path(output_dir or DEFAULT_OUTPUT_DIR)


# ---------------------------------------------------------------------------
# Generic loaders
# ---------------------------------------------------------------------------

def load_csv(path: Union[str, Path]) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load a CSV file, returning (DataFrame, None) or (None, error)."""
    p = Path(path)
    if not p.exists():
        return None, f"File not found: {p}"
    try:
        df = pd.read_csv(p)
        if df.empty:
            return None, f"File is empty: {p}"
        return df, None
    except Exception as e:
        return None, f"Error reading {p}: {e}"


def load_json(path: Union[str, Path]) -> Tuple[Optional[Dict], Optional[str]]:
    """Load a JSON file, returning (dict, None) or (None, error)."""
    p = Path(path)
    if not p.exists():
        return None, f"File not found: {p}"
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except Exception as e:
        return None, f"Error reading {p}: {e}"


# ---------------------------------------------------------------------------
# Output directory discovery
# ---------------------------------------------------------------------------

def list_output_subdirs(output_dir: Optional[str] = None) -> List[str]:
    """List all subdirectory names under the output root."""
    root = _resolve_output_dir(output_dir)
    if not root.exists():
        return []
    return sorted([d.name for d in root.iterdir() if d.is_dir()])


def find_latest_dir(prefix: str, output_dir: Optional[str] = None) -> Optional[Path]:
    """Find the most recently modified directory matching a prefix.

    Many phases create timestamped output dirs like scanner_phase3_20260307_151132.
    This returns the latest one matching the given prefix.
    """
    root = _resolve_output_dir(output_dir)
    if not root.exists():
        return None
    candidates = sorted(
        [d for d in root.iterdir() if d.is_dir() and d.name.startswith(prefix)],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def find_file_in_dirs(
    filename: str, prefixes: List[str], output_dir: Optional[str] = None
) -> Optional[Path]:
    """Search for a file across multiple output subdirectories.

    Checks the latest directory for each prefix, returns first match.
    """
    for prefix in prefixes:
        d = find_latest_dir(prefix, output_dir)
        if d:
            candidate = d / filename
            if candidate.exists():
                return candidate
    return None


# ---------------------------------------------------------------------------
# Scanner (Phase 3)
# ---------------------------------------------------------------------------

def load_scanner_opportunities(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load the latest scanner opportunities CSV."""
    for filename in ["scanner_candidates.csv", "ranked_opportunities.csv", "opportunities.csv"]:
        path = find_file_in_dirs(
            filename, ["phase16b_scanner", "scanner"], output_dir
        )
        if path:
            return load_csv(path)
    return None, "No scanner output found. Run the scanner engine first."


def load_scanner_json(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the latest scanner opportunities JSON."""
    for filename in ["scanner_candidates.json", "ranked_opportunities.json", "opportunities.json"]:
        path = find_file_in_dirs(
            filename, ["phase16b_scanner", "scanner"], output_dir
        )
        if path:
            return load_json(path)
    return None, "No scanner JSON output found."


# ---------------------------------------------------------------------------
# Monitoring (Phase 4)
# ---------------------------------------------------------------------------

def load_monitoring_alerts(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load the latest monitoring alerts CSV."""
    path = find_file_in_dirs("alerts.csv", ["phase18_monitoring", "phase16b_monitoring", "monitoring"], output_dir)
    if path is None:
        return None, "No monitoring alerts found. Run the monitoring engine first."
    return load_csv(path)


def load_monitoring_top_picks(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load the latest monitoring top picks CSV."""
    path = find_file_in_dirs("top_picks.csv", ["phase18_monitoring", "phase16b_monitoring", "monitoring"], output_dir)
    if path is None:
        return None, "No monitoring top picks found."
    return load_csv(path)


def load_monitoring_regime(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the latest regime summary JSON."""
    path = find_file_in_dirs("regime_summary.json", ["phase18_monitoring", "phase16b_monitoring", "monitoring"], output_dir)
    if path is None:
        return None, "No regime summary found."
    return load_json(path)


def load_monitoring_relative_strength(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load the latest relative strength CSV."""
    path = find_file_in_dirs("relative_strength.csv", ["phase18_monitoring", "phase16b_monitoring", "monitoring"], output_dir)
    if path is None:
        return None, "No relative strength data found."
    return load_csv(path)


def load_monitoring_snapshot(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the latest market snapshot JSON."""
    path = find_file_in_dirs("market_snapshot.json", ["phase18_monitoring", "phase16b_monitoring", "monitoring"], output_dir)
    if path is None:
        return None, "No market snapshot found."
    return load_json(path)


# ---------------------------------------------------------------------------
# Decision Engine (Phase 5)
# ---------------------------------------------------------------------------

def load_decision_picks(
    horizon: str = "intraday",
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load decision picks CSV for a given horizon."""
    filename = f"decision_top_{horizon}.csv"
    path = find_file_in_dirs(filename, ["phase18_decision", "phase16b_decision", "decision"], output_dir)
    if path is None:
        return None, f"No {horizon} decision picks found. Run the decision engine first."
    return load_csv(path)


def load_decision_rejected(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load rejected opportunities CSV."""
    path = find_file_in_dirs("decision_rejected.csv", ["phase18_decision", "phase16b_decision", "decision"], output_dir)
    if path is None:
        return None, "No rejected opportunities found."
    return load_csv(path)


def load_decision_summary(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the decision summary JSON."""
    path = find_file_in_dirs("decision_summary.json", ["phase18_decision", "phase16b_decision", "decision"], output_dir)
    if path is None:
        return None, "No decision summary found."
    return load_json(path)


def load_portfolio_plan(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the portfolio plan JSON."""
    path = find_file_in_dirs("portfolio_plan.json", ["phase18_decision", "phase16b_decision", "decision"], output_dir)
    if path is None:
        return None, "No portfolio plan found."
    return load_json(path)


# ---------------------------------------------------------------------------
# Market Intelligence (Phase 6)
# ---------------------------------------------------------------------------

def load_market_breadth(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load market breadth CSV."""
    path = find_file_in_dirs("market_breadth.csv", ["market_intelligence"], output_dir)
    if path is None:
        return None, "No market breadth data found."
    return load_csv(path)


def load_sector_rotation(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load sector rotation CSV."""
    path = find_file_in_dirs("sector_rotation.csv", ["market_intelligence"], output_dir)
    if path is None:
        return None, "No sector rotation data found."
    return load_csv(path)


def load_market_state(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the market state summary JSON."""
    path = find_file_in_dirs(
        "market_state_summary.json", ["market_intelligence"], output_dir
    )
    if path is None:
        return None, "No market state summary found."
    return load_json(path)


def load_volatility_regime(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load volatility regime JSON."""
    path = find_file_in_dirs(
        "volatility_regime.json", ["market_intelligence"], output_dir
    )
    if path is None:
        return None, "No volatility regime data found."
    return load_json(path)


def load_volume_signals(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load volume signals CSV."""
    path = find_file_in_dirs("volume_signals.csv", ["market_intelligence"], output_dir)
    if path is None:
        return None, "No volume signals found."
    return load_csv(path)


# ---------------------------------------------------------------------------
# Research Lab (Phase 7)
# ---------------------------------------------------------------------------

def load_strategy_scores(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load strategy scores CSV."""
    path = find_file_in_dirs("strategy_scores.csv", ["research_lab"], output_dir)
    if path is None:
        return None, "No strategy scores found. Run the research lab first."
    return load_csv(path)


def load_robustness_reports(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[List], Optional[str]]:
    """Load robustness reports JSON."""
    path = find_file_in_dirs("robustness_reports.json", ["research_lab"], output_dir)
    if path is None:
        return None, "No robustness reports found."
    data, err = load_json(path)
    if err:
        return None, err
    # The JSON is a list of report dicts
    if isinstance(data, dict):
        return data.get("reports", [data]), None
    return data, None


def load_parameter_surfaces(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[List], Optional[str]]:
    """Load parameter surfaces JSON."""
    path = find_file_in_dirs("parameter_surfaces.json", ["research_lab"], output_dir)
    if path is None:
        return None, "No parameter surface data found."
    data, err = load_json(path)
    if err:
        return None, err
    if isinstance(data, dict):
        return data.get("surfaces", [data]), None
    return data, None


# ---------------------------------------------------------------------------
# Realtime (Phase 8)
# ---------------------------------------------------------------------------

def load_realtime_status(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load realtime status JSON."""
    path = find_file_in_dirs("realtime_status.json", ["realtime"], output_dir)
    if path is None:
        return None, "No realtime status found. Realtime engine has not run yet."
    return load_json(path)


def load_realtime_cycle_history(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load realtime cycle history CSV."""
    path = find_file_in_dirs("realtime_cycle_history.csv", ["realtime"], output_dir)
    if path is None:
        return None, "No realtime cycle history found."
    return load_csv(path)


def load_realtime_snapshot(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load the latest realtime snapshot JSON."""
    path = find_file_in_dirs("realtime_snapshot.json", ["realtime"], output_dir)
    if path is None:
        return None, "No realtime snapshot found."
    return load_json(path)


def load_realtime_alerts(
    output_dir: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load realtime alerts CSV."""
    path = find_file_in_dirs("realtime_alerts.csv", ["realtime"], output_dir)
    if path is None:
        return None, "No realtime alerts found."
    return load_csv(path)


# ---------------------------------------------------------------------------
# Backtest outputs (Phase 1-2 research)
# ---------------------------------------------------------------------------

def load_backtest_equity_curve(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load equity curve CSV from a backtest output subdirectory."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in ["equity_curve.csv", "portfolio_equity_curve.csv"]:
        candidate = root / name
        if candidate.exists():
            return load_csv(candidate)
    return None, f"No equity curve found in {root}"


def load_backtest_trade_log(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load trade log CSV from a backtest output subdirectory."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in ["trade_log.csv", "portfolio_trade_log.csv", "trades.csv"]:
        candidate = root / name
        if candidate.exists():
            return load_csv(candidate)
    return None, f"No trade log found in {root}"


def load_backtest_metrics(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load metrics JSON from a backtest output subdirectory."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in ["metrics.json", "strategy_metrics.json", "summary.json"]:
        candidate = root / name
        if candidate.exists():
            return load_json(candidate)
    return None, f"No metrics JSON found in {root}"


def list_backtest_runs(output_dir: Optional[str] = None) -> List[str]:
    """List all backtest output subdirectories.

    Filters out known non-backtest directories (scanner, monitoring, etc).
    """
    non_backtest = {
        "scanner", "monitoring", "decision", "market_intelligence",
        "research_lab", "realtime",
    }
    all_dirs = list_output_subdirs(output_dir)
    return [d for d in all_dirs if not any(d.startswith(nb) for nb in non_backtest)]


# ---------------------------------------------------------------------------
# Walk-Forward / Monte Carlo / Optimization (Phase 2 research)
# ---------------------------------------------------------------------------

def load_walk_forward_results(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load walk-forward window results CSV."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in ["walk_forward_windows.csv", "wf_windows.csv", "windows.csv"]:
        candidate = root / name
        if candidate.exists():
            return load_csv(candidate)
    # Try finding any CSV with 'walk' or 'wf' in the name
    if root.exists():
        for f in sorted(root.glob("*.csv")):
            if "walk" in f.name.lower() or "wf" in f.name.lower():
                return load_csv(f)
    return None, f"No walk-forward results found in {root}"


def load_walk_forward_summary(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load walk-forward aggregate summary JSON."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in ["walk_forward_summary.json", "wf_summary.json", "summary.json"]:
        candidate = root / name
        if candidate.exists():
            return load_json(candidate)
    return None, f"No walk-forward summary found in {root}"


def load_monte_carlo_results(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[Dict], Optional[str]]:
    """Load Monte Carlo results JSON."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in ["monte_carlo_results.json", "mc_results.json", "summary.json"]:
        candidate = root / name
        if candidate.exists():
            return load_json(candidate)
    return None, f"No Monte Carlo results found in {root}"


def load_optimization_results(
    subdir: str, output_dir: Optional[str] = None
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load optimization/strategy ranking results CSV."""
    root = _resolve_output_dir(output_dir) / subdir
    for name in [
        "strategy_ranking.csv", "optimization_results.csv",
        "ranked_strategies.csv", "results.csv",
    ]:
        candidate = root / name
        if candidate.exists():
            return load_csv(candidate)
    # Fallback: first CSV in the dir
    if root.exists():
        csvs = sorted(root.glob("*.csv"))
        if csvs:
            return load_csv(csvs[0])
    return None, f"No optimization results found in {root}"


# ---------------------------------------------------------------------------
# Availability summary
# ---------------------------------------------------------------------------

def get_data_availability(output_dir: Optional[str] = None) -> Dict[str, bool]:
    """Check which phase outputs are available.

    Returns a dict like {"scanner": True, "monitoring": False, ...}.
    """
    checks = {
        "backtests": bool(list_backtest_runs(output_dir)),
        "scanner": find_latest_dir("scanner", output_dir) is not None,
        "monitoring": find_latest_dir("monitoring", output_dir) is not None,
        "decision": find_latest_dir("decision", output_dir) is not None,
        "market_intelligence": find_latest_dir("market_intelligence", output_dir) is not None,
        "research_lab": find_latest_dir("research_lab", output_dir) is not None,
        "realtime": find_latest_dir("realtime", output_dir) is not None,
    }
    return checks
