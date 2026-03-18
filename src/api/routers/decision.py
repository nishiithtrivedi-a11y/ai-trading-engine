from fastapi import APIRouter
from typing import Dict, Any
from src.ui.utils.loaders import (
    load_decision_summary,
    load_decision_picks,
    load_decision_rejected,
    load_portfolio_plan
)
from src.api.services.artifact_service import _handle_loader_result

router = APIRouter(prefix="/api/v1/decision", tags=["decision"])

@router.get("/latest")
def get_latest_decision(output_dir: str = "output") -> Dict[str, Any]:
    """Get the latest decision logic outputs and portfolio plan."""
    summary_md, _ = load_decision_summary(output_dir)
    portfolio_plan, _ = load_portfolio_plan(output_dir)
    
    # These return DataFrames, need to convert
    selected = _handle_loader_result(load_decision_picks("swing", output_dir))
    rejected = _handle_loader_result(load_decision_rejected(output_dir))

    return {
        "summary_markdown": summary_md or "",
        "selected": {"decisions": selected},
        "rejected": {"decisions": rejected},
        "portfolio_plan": portfolio_plan or {}
    }
