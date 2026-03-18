from fastapi import APIRouter
from typing import Dict, Any
from src.ui.utils.loaders import (
    load_monitoring_regime,
    load_monitoring_snapshot,
    load_monitoring_alerts,
    load_monitoring_top_picks
)
from src.api.services.artifact_service import _handle_loader_result

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

@router.get("/latest")
def get_latest_monitoring(output_dir: str = "output") -> Dict[str, Any]:
    """Get the latest monitoring dashboard data."""
    
    # JSONs
    regime_data, _ = load_monitoring_regime(output_dir)
    snapshot_data, _ = load_monitoring_snapshot(output_dir)
    
    # CSVs
    alerts = _handle_loader_result(load_monitoring_alerts(output_dir))
    top_picks = _handle_loader_result(load_monitoring_top_picks(output_dir))
    
    return {
        "regime": regime_data or {},
        "snapshot": snapshot_data or {},
        "alerts": alerts,
        "top_picks": top_picks
    }
