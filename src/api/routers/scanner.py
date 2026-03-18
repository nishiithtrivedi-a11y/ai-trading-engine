from fastapi import APIRouter
from typing import Dict, Any
from src.ui.utils.loaders import load_scanner_json, load_scanner_opportunities
from src.api.services.artifact_service import _handle_loader_result

router = APIRouter(prefix="/api/v1/scanner", tags=["scanner"])

@router.get("/latest")
def get_latest_scanner_results(output_dir: str = "output") -> Dict[str, Any]:
    """Get the latest scanner opportunities and metadata."""
    # Load JSON metadata
    json_data, json_err = load_scanner_json(output_dir)
    meta = {}
    if not json_err and json_data:
        meta = json_data.get("metadata", {})
        
    # Load CSV data directly from loaders and use artifact_service handler to format
    # which turns DataFrames into a JSON-friendly list of dicts.
    opportunities = _handle_loader_result(load_scanner_opportunities(output_dir))
    
    return {
        "metadata": meta,
        "opportunities": opportunities
    }
