"""
Runner: bridges HTTP requests to the PortalAgent.

This module converts a RunRequest (HTTP schema) into the internal
PortalTask + PortalCredentials models, creates a PortalAgent, runs it,
and returns the PortalRunResult.

The runner itself never raises — the PortalAgent's run() method is
designed to catch all exceptions and return a failed PortalRunResult.
"""

from __future__ import annotations

import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Path setup: make portal-agent/ importable so we can use its src package.
# This MUST happen before we import from src.* below.
# -----------------------------------------------------------------------------
PORTAL_AGENT_DIR = Path(__file__).resolve().parent.parent / "portal-agent"
if str(PORTAL_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_AGENT_DIR))

from src.config import Settings  # noqa: E402
from src.models import PortalCredentials, PortalRunResult, PortalTask  # noqa: E402
from src.agent import PortalAgent  # noqa: E402

from schemas import RunRequest  # noqa: E402


async def run_portal_task(
    request: RunRequest,
    settings: Settings,
) -> PortalRunResult:
    """Execute a portal automation task.

    Converts the HTTP request into internal domain models, creates a
    PortalAgent, and runs it. Never raises — failures are captured in
    the returned PortalRunResult.

    Args:
        request: Validated HTTP request body.
        settings: Application settings (loaded from environment).

    Returns:
        PortalRunResult with success/failure info, downloaded files,
        token usage, and agent trace.
    """
    credentials = PortalCredentials(
        username=request.username,
        password=request.password,
    )

    task = PortalTask(
        portal_url=request.portal_url,
        credentials=credentials,
        target_tab=request.target_tab,
        file_pattern=request.file_pattern,
        max_downloads=request.max_downloads,
        download_subdir=request.download_subdir,
    )

    agent = PortalAgent(settings=settings, task=task)
    result: PortalRunResult = await agent.run()

    return result