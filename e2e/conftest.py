"""
Shared fixtures for end-to-end integration tests.

This conftest wires together ALL FOUR packages:
  - demo-portal/   (the target website)
  - portal-agent/  (the automation agent)
  - server/        (the FastAPI HTTP API)
  - reports/       (the PDF report generator)

The PortalAgent is mocked so no real browser or LLM is launched.
But everything else — the demo portal's HTTP routes, the server's
HTTP routes, the PDF generation — runs for real.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# -----------------------------------------------------------------------------
# Path setup: add all four packages to sys.path
# -----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent

PACKAGES = [
    REPO_ROOT / "demo-portal",
    REPO_ROOT / "portal-agent",
    REPO_ROOT / "server",
    REPO_ROOT / "reports",
    REPO_ROOT / "e2e",
]

for path in PACKAGES:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# -----------------------------------------------------------------------------
# Project imports (after path setup)
# -----------------------------------------------------------------------------
from src.config import Settings  # noqa: E402
from src.models import DownloadedFile, PortalRunResult  # noqa: E402


# =============================================================================
# Fixtures: settings
# =============================================================================

@pytest.fixture
def test_settings(tmp_path) -> Settings:
    """Settings with a fake API key and temp download dir."""
    return Settings(
        groq_api_key="gsk_test_key_for_e2e_not_real",
        groq_model="llama-3.3-70b-versatile",
        headless=True,
        download_dir=str(tmp_path / "downloads"),
        _env_file=None,
    )


# =============================================================================
# Fixtures: fake agent result
# =============================================================================

@pytest.fixture
def fake_result() -> PortalRunResult:
    """A realistic successful PortalRunResult for e2e tests."""
    now = datetime.now(timezone.utc)
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
        ],
        total_steps=12,
        total_tokens=4500,
        error=None,
        agent_trace=[
            "start",
            "navigate_to_portal",
            "login",
            "navigate_to_invoices_tab",
            "download_invoice_001.pdf",
            "download_invoice_002.pdf",
            "verify_downloads",
            "done",
        ],
        started_at=now,
        completed_at=now,
    )


# =============================================================================
# Fixtures: demo portal client (real FastAPI TestClient)
# =============================================================================

@pytest.fixture
def portal_client(tmp_path, monkeypatch):
    """A TestClient for the demo portal with PDFs in a temp dir."""
    import app as app_module
    from seed_pdfs import seed_default_pdfs

    pdfs_dir = tmp_path / "portal_pdfs"
    pdfs_dir.mkdir()
    seed_default_pdfs(pdfs_dir, app_module.TABS)

    monkeypatch.setattr(app_module, "PDFS_DIR", pdfs_dir)

    from fastapi.testclient import TestClient
    with TestClient(app_module.app) as c:
        yield c


# =============================================================================
# Fixtures: API server client (real FastAPI TestClient, mocked agent)
# =============================================================================

@pytest.fixture
def api_client(test_settings, fake_result):
    """A TestClient for the API server with the agent mocked.

    By default returns fake_result. Tests can override mock_run.return_value.
    """
    import main as main_module

    main_module.app.dependency_overrides[main_module.get_settings] = (
        lambda: test_settings
    )

    with patch(
        "main.run_portal_task",
        new_callable=AsyncMock,
        return_value=fake_result,
    ) as mock_run:
        from fastapi.testclient import TestClient
        with TestClient(main_module.app) as c:
            yield c, mock_run

    main_module.app.dependency_overrides.clear()