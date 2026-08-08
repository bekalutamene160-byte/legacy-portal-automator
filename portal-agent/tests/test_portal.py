"""
Tests for the demo legacy portal.

Run: pytest tests/test_portal.py -v

These tests use FastAPI's TestClient (httpx-based) to exercise the
portal without launching a real server. No browser involved - we're
testing the portal's HTTP behavior, not the agent.

Import strategy:
We import directly from `app` and `seed_pdfs` (NOT
`legacy_portal.app`) because the demo-portal/ directory has a dash
in its name, which prevents it from being a Python package name.
Instead, we add demo-portal/ to sys.path so `app.py` is directly
importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make demo-portal/ importable so `import app` and
# `from seed_pdfs import ...` work. test_portal.py lives in
# portal-agent/tests/, so we go up 3 levels to reach the repo root,
# then into demo-portal/.
PORTAL_DIR = Path(__file__).parent.parent.parent / "demo-portal"
if str(PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_DIR))

# Now import - these imports MUST come after the sys.path manipulation above
from app import app, TABS, _is_safe_filename  # noqa: E402
from seed_pdfs import seed_default_pdfs  # noqa: E402


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Build a TestClient with PDFs in a tmp dir (so tests don't pollute)."""
    import app as app_module

    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    seed_default_pdfs(pdfs_dir, app_module.TABS)

    monkeypatch.setattr(app_module, "PDFS_DIR", pdfs_dir)

    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def logged_in_client(client):
    """A TestClient that's already logged in."""
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "portal123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    return client


# =====================================================================
# Health & info endpoints (public)
# =====================================================================

class TestPublicEndpoints:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "legacy-portal"

    def test_info_returns_portal_metadata(self, client):
        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Legacy Portal (Demo)"
        assert "Invoices" in data["tabs"]
        assert "Notices" in data["tabs"]
        assert "Reports" in data["tabs"]
        assert data["total_files"] > 0
        assert data["login_required"] is True


# =====================================================================
# Auth flow
# =====================================================================

class TestAuthFlow:
    def test_root_redirects_to_login_when_not_logged_in(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "Sign In" in resp.text
        assert "admin" in resp.text  # demo creds shown on page

    def test_login_success_redirects_to_dashboard(self, client):
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "portal123"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/dashboard"

    def test_login_with_wrong_password_returns_401(self, client):
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.text

    def test_login_with_unknown_user_returns_401(self, client):
        resp = client.post(
            "/login",
            data={"username": "hacker", "password": "anything"},
            follow_redirects=False,
        )
        assert resp.status_code == 401

    def test_logout_clears_session(self, logged_in_client):
        resp = logged_in_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200

        resp = logged_in_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

        resp = logged_in_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 303  # redirect to login


# =====================================================================
# Protected routes
# =====================================================================

class TestProtectedRoutes:
    def test_dashboard_requires_login(self, client):
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_dashboard_shows_tabs_when_logged_in(self, logged_in_client):
        resp = logged_in_client.get("/dashboard")
        assert resp.status_code == 200
        assert "Invoices" in resp.text
        assert "Notices" in resp.text
        assert "Reports" in resp.text

    def test_tab_requires_login(self, client):
        resp = client.get("/tab/Invoices", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_tab_lists_files_when_logged_in(self, logged_in_client):
        resp = logged_in_client.get("/tab/Invoices")
        assert resp.status_code == 200
        assert "invoice_001.pdf" in resp.text
        assert "invoice_002.pdf" in resp.text
        assert "invoice_003.pdf" in resp.text
        assert 'href="/download/invoice_001.pdf"' in resp.text

    def test_unknown_tab_returns_404(self, logged_in_client):
        resp = logged_in_client.get("/tab/DoesNotExist")
        assert resp.status_code == 404


# =====================================================================
# File downloads
# =====================================================================

class TestFileDownloads:
    def test_download_requires_login(self, client):
        resp = client.get("/download/invoice_001.pdf", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_download_returns_pdf(self, logged_in_client):
        resp = logged_in_client.get("/download/invoice_001.pdf")
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "invoice_001.pdf" in resp.headers["content-disposition"]

    def test_download_missing_file_returns_404(self, logged_in_client):
        resp = logged_in_client.get("/download/does_not_exist.pdf")
        assert resp.status_code == 404

    def test_download_rejects_path_traversal(self, logged_in_client):
        resp = logged_in_client.get("/download/..app.py")
        assert resp.status_code == 400

    def test_download_rejects_slashes(self, logged_in_client):
        resp = logged_in_client.get("/download/foo/bar.pdf")
        assert resp.status_code in (400, 404)

    def test_download_rejects_leading_dot(self, logged_in_client):
        resp = logged_in_client.get("/download/.env")
        assert resp.status_code == 400


# =====================================================================
# Filename sanitization (unit tests)
# =====================================================================

class TestSafeFilename:
    def test_normal_filename_is_safe(self):
        assert _is_safe_filename("invoice_001.pdf") is True

    def test_filename_with_dots_is_safe(self):
        assert _is_safe_filename("report.q1.2024.pdf") is True

    def test_filename_with_hyphen_is_safe(self):
        assert _is_safe_filename("report-q1.pdf") is True

    def test_empty_filename_is_unsafe(self):
        assert _is_safe_filename("") is False

    def test_filename_with_slash_is_unsafe(self):
        assert _is_safe_filename("foo/bar.pdf") is False

    def test_filename_with_backslash_is_unsafe(self):
        assert _is_safe_filename("foo\\bar.pdf") is False

    def test_filename_with_dotdot_is_unsafe(self):
        assert _is_safe_filename("../app.py") is False

    def test_filename_with_leading_dot_is_unsafe(self):
        assert _is_safe_filename(".env") is False

    def test_filename_with_space_is_unsafe(self):
        assert _is_safe_filename("my file.pdf") is False

    def test_filename_with_special_chars_is_unsafe(self):
        assert _is_safe_filename("file;rm.pdf") is False
        assert _is_safe_filename("file&x.pdf") is False
        assert _is_safe_filename("file*.pdf") is False