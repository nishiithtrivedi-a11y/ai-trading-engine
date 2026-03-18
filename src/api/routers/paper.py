from fastapi import APIRouter
from typing import Dict, Any
from src.ui.utils.loaders import find_file_in_dirs, load_csv, load_json
from src.api.services.artifact_service import _handle_loader_result

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])

def _load_paper_artifact(filename, loader_func, output_dir):
    path = find_file_in_dirs(filename, ["phase16b17_paper", "paper_trading", "paper"], output_dir)
    if not path:
        return None, f"No {filename} found."
    return loader_func(path)

@router.get("/state")
def get_paper_state(output_dir: str = "output") -> Dict[str, Any]:
    """Get the latest paper trading state and logs."""
    
    # Read Markdown
    summary_md, _ = _load_paper_artifact("paper_session_summary.md", lambda p: (open(p, 'r').read(), None), output_dir)
    
    # Read CSVs mapping to dicts
    journal = _handle_loader_result(_load_paper_artifact("paper_journal.csv", load_csv, output_dir))
    orders = _handle_loader_result(_load_paper_artifact("paper_orders.csv", load_csv, output_dir))
    positions = _handle_loader_result(_load_paper_artifact("paper_positions.csv", load_csv, output_dir))
    
    return {
        "summary_markdown": summary_md or "",
        "journal": journal,
        "orders": orders,
        "positions": positions
    }
