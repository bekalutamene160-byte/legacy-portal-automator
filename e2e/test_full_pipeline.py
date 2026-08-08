"""
End-to-End Integration Tests
============================

These tests verify the full pipeline works together:
  1. Demo portal serves pages and files
  2. API server receives requests and returns results
  3. PDF report generator produces valid reports from results
  4. The whole flow: portal → server → report works end-to-end

The PortalAgent is mocked (no real browser/LLM), but every other
component runs for real — real HTTP routes, real PDF generation,
real file I/O.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader


# =============================================================================
# Layer 1: Demo Portal (real HTTP, real PDFs)
# =============================================================================

class TestDemoPortalIntegration:
    """Verify the demo portal works as a standalone component."""

    def test_portal_health(self, portal_client):
        resp = portal_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_portal_login_flow(self, portal_client):
        # Login
        resp = portal_client.post(
            "/login",
            data={"username": "admin", "password": "portal123"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/dashboard"

        # Access dashboard with session cookie
        resp = portal_client.get("/dashboard")
        assert resp.status_code == 200
        assert "Invoices" in resp.text

    def test_portal_file_download(self, portal_client):
        # Login first
        portal_client.post(
            "/login",
            data={"username": "admin", "password": "portal123"},
        )
        # Download a file
        resp = portal_client.get("/download/invoice_001.pdf")
        assert resp.status_code == 200
        assert resp.content.startswith(b"%PDF")
        assert "attachment" in resp.headers.get("content-disposition", "")


# =============================================================================
# Layer 2: API Server (real HTTP, mocked agent)
# =============================================================================

class TestApiServerIntegration:
    """Verify the API server works as a standalone component."""

    def test_server_health(self, api_client):
        c, _ = api_client
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_server_info(self, api_client):
        c, _ = api_client
        resp = c.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Legacy Portal Automator API"
        assert data["configured_model"] == "llama-3.3-70b-versatile"

    def test_submit_run_returns_result(self, api_client):
        c, _ = api_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
                "target_tab": "Invoices",
                "file_pattern": "*.pdf",
                "max_downloads": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files_downloaded"]) == 2
        assert data["total_steps"] == 12


# =============================================================================
# Layer 3: PDF Report Generator (real PDF generation)
# =============================================================================

class TestReportGeneratorIntegration:
    """Verify the report generator works as a standalone component."""

    def test_generate_pdf_from_result(self, tmp_path, fake_result):
        from generator import generate_report

        output = tmp_path / "integration_report.pdf"
        result_path = generate_report(fake_result, output)

        assert result_path.exists()
        assert result_path.stat().st_size > 2000

        # Verify PDF content
        with open(output, "rb") as f:
            magic = f.read(5)
        assert magic == b"%PDF-"

    def test_pdf_contains_run_data(self, tmp_path, fake_result):
        from generator import generate_report

        output = tmp_path / "content_report.pdf"
        generate_report(fake_result, output)

        reader = PdfReader(str(output))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        assert "Legacy Portal Automator" in text
        assert "SUCCESS" in text
        assert "invoice_001.pdf" in text
        assert "4,500" in text  # token count


# =============================================================================
# Layer 4: Full Pipeline (portal → server → report)
# =============================================================================

class TestFullPipeline:
    """The real end-to-end test: everything wired together."""

    def test_portal_to_server_to_report(self, tmp_path, api_client, fake_result):
        """Full flow:
        1. Verify portal is alive (via server's perspective)
        2. Submit run to server
        3. Take the result and generate a PDF report
        4. Verify the PDF contains the run data
        """
        c, _ = api_client

        # Step 1: Server is healthy
        resp = c.get("/health")
        assert resp.status_code == 200

        # Step 2: Submit a run
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
                "target_tab": "Invoices",
                "file_pattern": "invoice_*.pdf",
                "max_downloads": 5,
            },
        )
        assert resp.status_code == 200
        run_data = resp.json()
        assert run_data["success"] is True

        # Step 3: Convert JSON response back to PortalRunResult
        from src.models import DownloadedFile, PortalRunResult

        files = [
            DownloadedFile(
                filename=f["filename"],
                size_bytes=f["size_bytes"],
                downloaded_at=f["downloaded_at"],
                local_path=f["local_path"],
            )
            for f in run_data["files_downloaded"]
        ]

        result = PortalRunResult(
            success=run_data["success"],
            files_downloaded=files,
            total_steps=run_data["total_steps"],
            total_tokens=run_data["total_tokens"],
            error=run_data["error"],
            agent_trace=run_data["agent_trace"],
            started_at=run_data["started_at"],
            completed_at=run_data["completed_at"],
        )

        # Step 4: Generate PDF report from the result
        from generator import generate_report

        output = tmp_path / "full_pipeline_report.pdf"
        generate_report(result, output)

        assert output.exists()
        assert output.stat().st_size > 2000

        # Verify the PDF contains the actual run data
        reader = PdfReader(str(output))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        assert "Legacy Portal Automator" in text
        assert "SUCCESS" in text
        assert "invoice_001.pdf" in text
        assert "invoice_002.pdf" in text
        assert "4,500" in text  # tokens
        assert "12" in text  # steps

    def test_failed_run_produces_failure_report(
        self, tmp_path, api_client, fake_result
    ):
        """Verify a failed run flows through and produces a failure report."""
        from datetime import datetime, timezone
        from src.models import PortalRunResult

        c, mock_run = api_client

        # Override the mock to return a failure
        now = datetime.now(timezone.utc)
        failed = PortalRunResult(
            success=False,
            files_downloaded=[],
            total_steps=5,
            total_tokens=1200,
            error="Login form not found",
            agent_trace=["start", "navigate", "login_failed"],
            started_at=now,
            completed_at=now,
        )
        mock_run.return_value = failed

        # Submit the run
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "wrong_password",
            },
        )
        assert resp.status_code == 200
        run_data = resp.json()
        assert run_data["success"] is False
        assert "Login form not found" in run_data["error"]

        # Generate a report from the failure
        result = PortalRunResult(
            success=run_data["success"],
            files_downloaded=[],
            total_steps=run_data["total_steps"],
            total_tokens=run_data["total_tokens"],
            error=run_data["error"],
            agent_trace=run_data["agent_trace"],
            started_at=run_data["started_at"],
            completed_at=run_data["completed_at"],
        )

        from generator import generate_report

        output = tmp_path / "failure_report.pdf"
        generate_report(result, output)

        assert output.exists()

        reader = PdfReader(str(output))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        assert "FAILED" in text
        assert "Login form not found" in text


# =============================================================================
# Layer 5: Cross-component validation
# =============================================================================

class TestCrossComponentValidation:
    """Tests that verify components agree on data formats."""

    def test_server_result_is_compatible_with_report_generator(
        self, tmp_path, api_client
    ):
        """The JSON returned by the server must be convertible to a
        PortalRunResult that the report generator accepts.
        """
        from src.models import DownloadedFile, PortalRunResult
        from generator import generate_report

        c, _ = api_client

        # Get a result from the server
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        run_data = resp.json()

        # Reconstruct PortalRunResult from JSON
        files = [
            DownloadedFile(
                filename=f["filename"],
                size_bytes=f["size_bytes"],
                downloaded_at=f["downloaded_at"],
                local_path=f["local_path"],
            )
            for f in run_data["files_downloaded"]
        ]

        result = PortalRunResult(
            success=run_data["success"],
            files_downloaded=files,
            total_steps=run_data["total_steps"],
            total_tokens=run_data["total_tokens"],
            error=run_data["error"],
            agent_trace=run_data["agent_trace"],
            started_at=run_data["started_at"],
            completed_at=run_data["completed_at"],
        )

        # Report generator should accept it without error
        output = tmp_path / "compatibility_test.pdf"
        result_path = generate_report(result, output)
        assert result_path.exists()

    def test_portal_credentials_format_matches_agent(
        self, test_settings
    ):
        """Verify the portal's credentials work with the agent's model."""
        from src.models import PortalCredentials, PortalTask

        creds = PortalCredentials(username="admin", password="portal123")
        task = PortalTask(
            portal_url="http://localhost:8001",
            credentials=creds,
            target_tab="Invoices",
        )

        assert task.credentials.username == "admin"
        assert task.credentials.password.get_secret_value() == "portal123"
        assert task.portal_url == "http://localhost:8001"