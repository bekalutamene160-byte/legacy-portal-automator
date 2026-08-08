"""
Legacy Portal Automator - FastAPI Server
========================================

HTTP API layer that wraps the PortalAgent. Users send a POST request
with portal credentials and task parameters; the server runs the agent
synchronously and returns the result as JSON.

Run it:
    cd server
    uvicorn main:app --reload --port 8000

Then open http://localhost:8000/docs for interactive API docs.

Endpoints:
    GET  /              - server info
    GET  /health        - health check
    GET  /api/info      - detailed server info (model, headless, max_steps)
    POST /api/runs      - submit a portal automation task
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status

# -----------------------------------------------------------------------------
# Path setup: make portal-agent/ importable so we can use its src package.
# This MUST happen before we import from src.* below.
# -----------------------------------------------------------------------------
PORTAL_AGENT_DIR = Path(__file__).resolve().parent.parent / "portal-agent"
if str(PORTAL_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_AGENT_DIR))

from src.config import Settings  # noqa: E402
from src.models import PortalRunResult  # noqa: E402

from schemas import RunRequest, ServerInfo  # noqa: E402
from runner import run_portal_task  # noqa: E402


# =============================================================================
# Settings dependency (testable via FastAPI dependency injection)
# =============================================================================

@lru_cache
def get_settings() -> Settings:
    """Load settings once (cached).

    Tests override this via app.dependency_overrides to inject test
    settings without touching the real .env file.
    """
    return Settings()


# =============================================================================
# FastAPI app
# =============================================================================

app = FastAPI(
    title="Legacy Portal Automator API",
    description=(
        "HTTP API for the Legacy Portal Automator. Submit a portal "
        "automation task and receive the result as JSON."
    ),
    version="0.1.0",
)


# =============================================================================
# Routes: public info
# =============================================================================

@app.get("/", response_model=ServerInfo)
async def root() -> ServerInfo:
    """Root endpoint - returns basic server info."""
    return ServerInfo(
        name="Legacy Portal Automator API",
        version="0.1.0",
        docs_url="/docs",
        health_url="/health",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint - used by monitoring tools."""
    return {"status": "ok", "service": "legacy-portal-automator-api"}


@app.get("/api/info", response_model=ServerInfo)
async def api_info(
    settings: Settings = Depends(get_settings),
) -> ServerInfo:
    """Detailed server info - includes configured model and agent settings."""
    return ServerInfo(
        name="Legacy Portal Automator API",
        version="0.1.0",
        docs_url="/docs",
        health_url="/health",
        configured_model=settings.groq_model,
        headless_mode=settings.headless,
        max_steps=settings.max_steps,
    )


# =============================================================================
# Routes: automation
# =============================================================================

@app.post(
    "/api/runs",
    response_model=PortalRunResult,
    status_code=status.HTTP_200_OK,
)
async def create_run(
    request: RunRequest,
    settings: Settings = Depends(get_settings),
) -> PortalRunResult:
    """Submit a portal automation task.

    The agent runs synchronously - the HTTP response is sent only after
    the agent finishes (or fails). A typical run takes 30-90 seconds
    depending on portal complexity and LLM response time.

    The agent NEVER raises - failures are captured in the response
    (success=False, error="...").

    Request body:
        portal_url:      URL of the legacy portal (e.g. http://localhost:8001)
        username:        Portal login username
        password:        Portal login password
        target_tab:      Tab to navigate to (default: "Documents")
        file_pattern:    Glob pattern for files (default: "*")
        max_downloads:   Max files to download (1-100, default: 10)
        download_subdir: Subdir within download folder (default: "")
    """
    try:
        result: PortalRunResult = await run_portal_task(request, settings)
        return result
    except Exception as exc:
        # This should never happen because PortalAgent.run() catches
        # everything, but we guard against it so the API never returns
        # a raw 500 with a stack trace.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during automation run: {exc}",
        )


# =============================================================================
# Main entry point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    # The API server runs on port 8000 by default.
    # The demo portal (Phase 7) runs on port 8001.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )