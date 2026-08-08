"""
Shared test fixtures for the server test suite.

Import strategy:
    - server/ is added to sys.path so `import main`, `from schemas import ...`
      work directly.
    - portal-agent/ is added to sys.path so `from src.config import ...`
      works directly.
    - These additions are also in pytest.ini (pythonpath), but we repeat
      them here for belt-and-suspenders safety (e.g. when running tests
      from an IDE that doesn't read pytest.ini).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# -----------------------------------------------------------------------------
# Path setup (MUST be before any project imports)
# -----------------------------------------------------------------------------
SERVER_DIR = Path(__file__).resolve().parent.parent
PORTAL_AGENT_DIR = SERVER_DIR.parent / "portal-agent"

for path in (SERVER_DIR, PORTAL_AGENT_DIR):
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
    """Settings with a fake API key and temp download dir.

    Uses _env_file=None so the real .env file doesn't leak into tests.
    """
    return Settings(
        groq_api_key="gsk_test_key_for_testing_only_not_real",
        groq_model="llama-3.3-70b-versatile",
        headless=True,
        download_dir=str(tmp_path / "downloads"),
        _env_file=None,
    )


# =============================================================================
# Fixtures: fake results
# =============================================================================

@pytest.fixture
def fake_successful_result() -> PortalRunResult:
    """A PortalRunResult that looks like a successful agent run."""
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
        agent_trace=["start", "login", "navigate_to_tab", "download_files", "done"],
        started_at=now,
        completed_at=now,
    )


@pytest.fixture
def fake_failed_result() -> PortalRunResult:
    """A PortalRunResult that looks like a failed agent run."""
    now = datetime.now(timezone.utc)
    return PortalRunResult(
        success=False,
        files_downloaded=[],
        total_steps=5,
        total_tokens=1200,
        error="Could not find login form on the portal page",
        agent_trace=["start", "navigate_to_portal", "login_failed"],
        started_at=now,
        completed_at=now,
    )


# =============================================================================
# Fixtures: TestClient with mocked agent
# =============================================================================

@pytest.fixture
def client(test_settings):
    """TestClient with settings overridden and agent mocked.

    By default, the mocked agent returns a successful result. Individual
    tests can override the mock's return_value to test failure scenarios.
    """
    import main as main_module

    # Override the settings dependency so no real .env is needed
    main_module.app.dependency_overrides[main_module.get_settings] = (
        lambda: test_settings
    )

    with patch(
        "main.run_portal_task",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = None  # tests set this

        with TestClient(main_module.app) as c:
            yield c, mock_run

    # Cleanup
    main_module.app.dependency_overrides.clear()


@pytest.fixture
def success_client(client, fake_successful_result):
    """TestClient where the agent returns a successful result."""
    test_client, mock_run = client
    mock_run.return_value = fake_successful_result
    return test_client, mock_run


@pytest.fixture
def failure_client(client, fake_failed_result):
    """TestClient where the agent returns a failed result."""
    test_client, mock_run = client
    mock_run.return_value = fake_failed_result
    return test_client, mock_run