from fastapi import APIRouter
from typing import Dict, Any, List
import yaml
from pathlib import Path

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])

@router.get("/")
def list_profiles() -> List[Dict[str, Any]]:
    """List all available analysis profiles from YAML config."""
    config_path = Path("src/config/analysis_profiles.yaml")
    if not config_path.exists():
        return []
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            profiles_data = yaml.safe_load(f) or {}
    except Exception:
        return []
        
    result = []
    # All analysis families supported across the engine 
    all_families = {"technical", "quant", "fundamental", "macro", "sentiment", "intermarket", "futures", "options", "commodities", "forex", "crypto"}
    
    for prov_name, details in profiles_data.items():
        enabled_modules = details.get("enabled", [])
        
        # Determine expected providers
        dependencies = []
        if "fundamental" in enabled_modules: dependencies.append("fundamentals_provider")
        if "options" in enabled_modules: dependencies.append("market_data (options support)")
        if "macro" in enabled_modules: dependencies.append("macro_provider")
        
        # Determine asset classes based on profile name / description
        asset_classes = []
        if "equity" in prov_name: asset_classes.append("Equities")
        if "options" in prov_name: asset_classes.append("Options")
        if "futures" in prov_name: asset_classes.append("Futures")
        if "forex" in prov_name or "currency" in prov_name: asset_classes.append("Forex")
        if not asset_classes: asset_classes.append("Multi-Asset")
        
        # Compute coverage matrix
        coverage = {}
        for family in all_families:
            coverage[family] = family in enabled_modules
            
        result.append({
            "id": prov_name,
            "description": details.get("description", "No description provided.").strip(),
            "enabled_families": enabled_modules,
            "coverage": coverage,
            "dependencies": dependencies if dependencies else ["Basic Market Data"],
            "asset_classes": asset_classes
        })
        
    return result
