from fastapi import APIRouter
from typing import Dict, Any
import yaml
from pathlib import Path

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])

@router.get("/health")
def get_providers_health() -> Dict[str, Any]:
    """Get the current configuration and mock health status of data providers."""
    config_path = Path("config/data_providers.yaml")
    
    config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
            
    # Parse the configured providers
    market_providers = config.get("providers", {})
    analysis_providers = config.get("analysis_providers", {})
    
    active_default = config.get("default_provider", "csv")
    
    # We build a mock health matrix based on what is enabled
    diagnostics = []
    
    for prov_name, details in market_providers.items():
        enabled = details.get("enabled", False)
        status = "healthy" if enabled else "offline"
        latency = "12ms" if enabled else "-"
        if prov_name == active_default and enabled:
            status = "active_primary"
            
        diagnostics.append({
            "name": prov_name,
            "type": "market_data",
            "enabled": enabled,
            "status": status,
            "latency": latency,
            "details": f"Base URL: {details.get('base_url', 'Local Data')}"
        })
        
    for module_name, prov_name in analysis_providers.items():
        if isinstance(prov_name, str) and prov_name != "none":
            diagnostics.append({
                "name": prov_name,
                "type": f"analysis_{module_name}",
                "enabled": True,
                "status": "healthy",
                "latency": "45ms",
                "details": f"Plugin Provider for {module_name}"
            })
            
    return {
        "default_provider": active_default,
        "diagnostics": diagnostics
    }
