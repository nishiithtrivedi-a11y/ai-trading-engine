from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pathlib import Path
import json
import pandas as pd

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])

@router.get("/runs")
def list_runs(output_dir: str = "output") -> List[Dict[str, Any]]:
    """List all available run directories and their top-level manifests if any."""
    base_path = Path(output_dir)
    if not base_path.exists():
        return []
        
    runs = []
    for d in base_path.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            # Check for inner timestamp folders
            timestamps = [t.name for t in d.iterdir() if t.is_dir() and not t.name.startswith(".")]
            timestamps.sort(reverse=True)
            
            runs.append({
                "phase": d.name,
                "latest_run": timestamps[0] if timestamps else None,
                "all_runs": timestamps
            })
    return runs

@router.get("/tree")
def get_artifact_tree(phase: str, run_id: str = "", output_dir: str = "output") -> Dict[str, Any]:
    """Get the file tree for a specific run."""
    run_path = Path(output_dir) / phase
    if run_id:
        run_path = run_path / run_id
        
    if not run_path.exists() or not run_path.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")
        
    files = []
    for f in run_path.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            try:
                size = f.stat().st_size
                files.append({
                    "name": f.name,
                    "path": str(f.relative_to(run_path)).replace("\\", "/"),
                    "size_bytes": size,
                    "extension": f.suffix.lower()
                })
            except Exception:
                pass
                
    # Also try to read run_manifest.json if it exists at the root of the run
    manifest = {}
    manifest_path = run_path / "run_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
        except Exception:
            pass
            
    return {
        "files": files,
        "manifest_preview": manifest
    }

@router.get("/preview")
def preview_artifact(phase: str, path: str, run_id: str = "", output_dir: str = "output") -> Dict[str, Any]:
    """Preview the content of a specific artifact file."""
    run_path = Path(output_dir) / phase
    if run_id:
        run_path = run_path / run_id
        
    file_path = run_path / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
        
    ext = file_path.suffix.lower()
    content = None
    preview_type = "text"
    
    try:
        # Prevent huge file loads
        if file_path.stat().st_size > 2 * 1024 * 1024:
            return {"error": "File too large to preview directly. Please download instead."}
            
        if ext == ".json":
            with open(file_path, "r") as f:
                content = json.load(f)
            preview_type = "json"
        elif ext == ".csv":
            df = pd.read_csv(file_path).fillna("")
            content = df.to_dict(orient="records")
            preview_type = "csv"
        else:
            with open(file_path, "r") as f:
                content = f.read()
            if ext == ".md":
                preview_type = "markdown"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
        
    return {
        "type": preview_type,
        "content": content
    }
