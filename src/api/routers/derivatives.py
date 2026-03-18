from fastapi import APIRouter
from typing import Dict, Any

router = APIRouter(prefix="/api/v1/derivatives", tags=["derivatives"])

@router.get("/summary")
def get_derivatives_summary(output_dir: str = "output") -> Dict[str, Any]:
    """
    Get derivatives top-level summary.
    Currently, as live provider data is disabled, this returns gracefully degraded state.
    """
    return {
        "status": "unavailable",
        "message": "Options and Futures analysis modules are inactive. Underlying spot data only.",
        "diagnostics": {
            "source": "None",
            "coverage": "0%",
            "freshness": "Offline"
        },
        "spot_reference": {
            "symbol": "NIFTY50",
            "price": 22100.50
        }
    }

@router.get("/chain")
def get_options_chain(symbol: str, expiry: str = "", output_dir: str = "output") -> Dict[str, Any]:
    """
    Returns an option chain. Returns empty data since live data mapping is disabled.
    """
    return {
        "status": "unavailable",
        "message": f"Option chain for {symbol} unavailable without live broker feed.",
        "calls": [],
        "puts": [],
        "iv_surface": None
    }
