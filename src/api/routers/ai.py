from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

class AIPromptRequest(BaseModel):
    prompt: str
    context_sources: List[str]

@router.post("/prompt")
def submit_prompt(request: AIPromptRequest) -> Dict[str, Any]:
    """
    Mock endpoint for the AI Workspace.
    Currently returns a safe placeholder response as no real AI backend is connected.
    """
    return {
        "status": "success",
        "response": f"This is a local placeholder response. The AI assistant is currently running in offline simulation mode.\n\nI received your prompt regarding: '{request.prompt[:50]}...'\n\nAttached Context: {', '.join(request.context_sources) if request.context_sources else 'None'}\n\n*Reminder: AI recommendations are advisory only and cannot automatically execute trades or deploy strategies.*",
        "advisory_warning": "Warning: Advisory Mode Only. Execution authority disabled."
    }

@router.get("/status")
def get_ai_status() -> Dict[str, Any]:
    """Get the current AI integration status."""
    return {
        "connected": False,
        "mode": "local_placeholder",
        "capabilities": ["report_generation", "explanation", "analysis"]
    }
