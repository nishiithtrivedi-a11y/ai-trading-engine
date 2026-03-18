from fastapi import APIRouter
from src.api.services.artifact_service import get_overview_data

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])

@router.get("")
def read_overview(output_dir: str = "output"):
    """Get aggregated data for the Overview dashboard."""
    return get_overview_data(output_dir)
