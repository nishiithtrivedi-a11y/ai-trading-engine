from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI app
app = FastAPI(
    title="AI Trading Engine API",
    description="Backend API for the Trading Command Center",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v1/status")
def get_status():
    return {"status": "ok", "message": "API is running"}

from src.api.routers import overview, scanner, monitoring, decision, paper, providers, artifacts, logs, profiles, derivatives, ai, automation, provider_sessions

app.include_router(overview.router)
app.include_router(scanner.router)
app.include_router(monitoring.router)
app.include_router(decision.router)
app.include_router(paper.router)
app.include_router(providers.router)
app.include_router(artifacts.router)
app.include_router(logs.router)
app.include_router(profiles.router)
app.include_router(derivatives.router)
app.include_router(ai.router)
app.include_router(automation.router)
app.include_router(provider_sessions.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)
