from typing import Any, Dict, List, Optional
from fastapi import HTTPException
import pandas as pd
import numpy as np

from src.ui.utils.loaders import (
    get_data_availability,
    load_monitoring_regime,
    load_decision_summary,
    load_market_state,
    load_realtime_status,
    list_backtest_runs
)
from src.dashboard.dashboard_api import _safe_dict

def _handle_loader_result(result: tuple[Optional[Any], Optional[str]]) -> Any:
    data, error = result
    
    if data is None:
        return []
        
    if isinstance(data, pd.DataFrame):
        # Convert NaN to None for JSON serialization
        data = data.replace({np.nan: None})
        return data.to_dict(orient="records")
    
    return _safe_dict(data)

def get_overview_data(output_dir: str = "output") -> Dict[str, Any]:
    """Aggregates data for the overview page."""
    avail = get_data_availability(output_dir)
    
    # Safely load components, don't raise 404 if part of overview is missing
    regime = None
    regime_data, _ = load_monitoring_regime(output_dir)
    if regime_data:
        regime = regime_data.get("regime", "Unknown")

    market_state = None
    ms_data, _ = load_market_state(output_dir)
    if ms_data:
        market_state = ms_data.get("market_state", ms_data)

    decision_summary = None
    ds_data, _ = load_decision_summary(output_dir)
    if ds_data:
        decision_summary = ds_data.get("summary", ds_data)
        
    runs = list_backtest_runs(output_dir)
    
    return {
        "availability": avail,
        "metrics": {
            "total_phases_available": sum(1 for v in avail.values() if v),
            "total_phases": len(avail),
            "backtest_runs": len(runs),
            "market_regime": regime
        },
        "market_state": market_state,
        "decision_summary": decision_summary
    }
