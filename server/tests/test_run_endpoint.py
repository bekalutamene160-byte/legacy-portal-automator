"""Tests for the POST /api/runs endpoint."""

from __future__ import annotations


class TestCreateRunSuccess:
    def test_returns_200_on_success(self, success_client):
        c, _ = success_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        assert resp.status_code == 200

    def test_returns_success_true(self, success_client):
        c, _ = success_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert data["success"] is True

    def test_returns_downloaded_files(self, success_client):
        c, _ = success_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert len(data["files_downloaded"]) == 2
        assert data["files_downloaded"][0]["filename"] == "invoice_001.pdf"
        assert data["files_downloaded"][1]["filename"] == "invoice_002.pdf"

    def test_returns_step_and_token_counts(self, success_client):
        c, _ = success_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert data["total_steps"] == 12
        assert data["total_tokens"] == 4500

    def test_returns_agent_trace(self, success_client):
        c, _ = success_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert "agent_trace" in data
        assert len(data["agent_trace"]) == 5
        assert data["agent_trace"][0] == "start"

    def test_returns_timestamps(self, success_client):
        c, _ = success_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert "started_at" in data
        assert "completed_at" in data
        assert data["started_at"] is not None
        assert data["completed_at"] is not None


class TestCreateRunFailure:
    def test_returns_200_on_failure(self, failure_client):
        """Failed agent runs still return 200 - the failure is in the body."""
        c, _ = failure_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        assert resp.status_code == 200

    def test_returns_success_false_on_failure(self, failure_client):
        c, _ = failure_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert data["success"] is False

    def test_returns_error_message_on_failure(self, failure_client):
        c, _ = failure_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert data["error"] is not None
        assert "login form" in data["error"].lower()

    def test_returns_empty_files_on_failure(self, failure_client):
        c, _ = failure_client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        data = resp.json()
        assert data["files_downloaded"] == []


class TestCreateRunValidation:
    def test_missing_url_returns_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/runs",
            json={"username": "admin", "password": "portal123"},
        )
        assert resp.status_code == 422

    def test_missing_username_returns_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/runs",
            json={"portal_url": "http://localhost:8001", "password": "portal123"},
        )
        assert resp.status_code == 422

    def test_missing_password_returns_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/runs",
            json={"portal_url": "http://localhost:8001", "username": "admin"},
        )
        assert resp.status_code == 422

    def test_max_downloads_zero_returns_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
                "max_downloads": 0,
            },
        )
        assert resp.status_code == 422

    def test_max_downloads_over_100_returns_422(self, client):
        c, _ = client
        resp = c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
                "max_downloads": 101,
            },
        )
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client):
        c, _ = client
        resp = c.post("/api/runs", json={})
        assert resp.status_code == 422


class TestCreateRunCallsRunner:
    def test_runner_called_once(self, success_client):
        c, mock_run = success_client
        c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        assert mock_run.call_count == 1

    def test_runner_receives_correct_url(self, success_client):
        c, mock_run = success_client
        c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        args = mock_run.call_args
        request_arg = args.args[0]
        assert request_arg.portal_url == "http://localhost:8001"

    def test_runner_receives_correct_username(self, success_client):
        c, mock_run = success_client
        c.post(
            "/api/runs",
            json={
                "portal_url": "http://localhost:8001",
                "username": "admin",
                "password": "portal123",
            },
        )
        args = mock_run.call_args
        request_arg = args.args[0]
        assert request_arg.username == "admin"

    def test_runner_receives_custom_task_params(self, success_client):
        c, mock_run = success_client
        c.post(
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
        args = mock_run.call_args
        request_arg = args.args[0]
        assert request_arg.target_tab == "Invoices"
        assert request_arg.file_pattern == "*.pdf"
        assert request_arg.max_downloads == 5