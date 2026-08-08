"""
Shared test fixtures for the report generator test suite.

Import strategy:
    - portal-agent/ is added to sys.path so `from src.models import ...`
      works directly.
    - reports/ is added to sys.path so `from generator import ...` works.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# -----------------------------------------------------------------------------
# Path setup (MUST be before any project imports)
# -----------------------------------------------------------------------------
REPORTS_DIR = Path(__file__).resolve().parent.parent
PORTAL_AGENT_DIR = REPORTS_DIR.parent / "portal-agent"

for path in (REPORTS_DIR, PORTAL_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# -----------------------------------------------------------------------------
# Project imports (after path setup)
# -----------------------------------------------------------------------------
from src.models import DownloadedFile, PortalRunResult  # noqa: E402


# =============================================================================
# Fixtures: fake results
# =============================================================================

@pytest.fixture
def now() -> datetime:
    """A fixed timezone-aware datetime for consistent tests."""
    return datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def successful_result(now) -> PortalRunResult:
    """A PortalRunResult that looks like a successful agent run with files."""
    return PortalRunResult(
        success=True,
        files_downloaded=[
            DownloadedFile(
                filename="invoice_001.pdf",
                size_bytes=1936,
                downloaded_at=now,
                local_path="/tmp/downloads/invoice_001.pdf",
            ),
            DownloadedFile(
                filename="invoice_002.pdf",
                size_bytes=1940,
                downloaded_at=now,
                local_path="/tmp/downloads/invoice_002.pdf",
            ),
            DownloadedFile(
                filename="report_q1_2024.pdf",
                size_bytes=5120,
                downloaded_at=now,
                local_path="/tmp/downloads/report_q1_2024.pdf",
            ),
        ],
        total_steps=12,
        total_tokens=4500,
        error=None,
        agent_trace=[
            "start",
            "navigate_to_portal",
            "login",
            "navigate_to_tab",
            "download_invoice_001.pdf",
            "download_invoice_002.pdf",
            "download_report_q1_2024.pdf",
            "verify_downloads",
            "done",
        ],
        started_at=now,
        completed_at=now,
    )


@pytest.fixture
def failed_result(now) -> PortalRunResult:
    """A PortalRunResult that looks like a failed agent run."""
    return PortalRunResult(
        success=False,
        files_downloaded=[],
        total_steps=5,
        total_tokens=1200,
        error="Could not find login form on the portal page",
        agent_trace=[
            "start",
            "navigate_to_portal",
            "locate_login_form_failed",
            "retry_attempt_1",
            "login_failed",
        ],
        started_at=now,
        completed_at=now,
    )


@pytest.fixture
def empty_success_result(now) -> PortalRunResult:
    """A successful run with zero files downloaded."""
    return PortalRunResult(
        success=True,
        files_downloaded=[],
        total_steps=8,
        total_tokens=2000,
        error=None,
        agent_trace=["start", "navigate", "login", "done"],
        started_at=now,
        completed_at=now,
    )