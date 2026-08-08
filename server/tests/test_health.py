"""Tests for the public info endpoints: GET /, GET /health, GET /api/info."""

from __future__ import annotations


class TestRootEndpoint:
    def test_root_returns_200(self, client):
        c, _ = client
        resp = c.get("/")
        assert resp.status_code == 200

    def test_root_returns_server_info(self, client):
        c, _ = client
        resp = c.get("/")
        data = resp.json()
        assert data["name"] == "Legacy Portal Automator API"
        assert data["version"] == "0.1.0"
        assert data["docs_url"] == "/docs"
        assert data["health_url"] == "/health"


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        c, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client):
        c, _ = client
        resp = c.get("/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_returns_correct_service_name(self, client):
        c, _ = client
        resp = c.get("/health")
        data = resp.json()
        assert data["service"] == "legacy-portal-automator-api"


class TestApiInfoEndpoint:
    def test_api_info_returns_200(self, client):
        c, _ = client
        resp = c.get("/api/info")
        assert resp.status_code == 200

    def test_api_info_returns_server_info(self, client):
        c, _ = client
        resp = c.get("/api/info")
        data = resp.json()
        assert data["name"] == "Legacy Portal Automator API"
        assert data["version"] == "0.1.0"

    def test_api_info_includes_configured_model(self, client):
        c, _ = client
        resp = c.get("/api/info")
        data = resp.json()
        assert data["configured_model"] == "llama-3.3-70b-versatile"

    def test_api_info_includes_headless_mode(self, client):
        c, _ = client
        resp = c.get("/api/info")
        data = resp.json()
        assert data["headless_mode"] is True

    def test_api_info_includes_max_steps(self, client):
        c, _ = client
        resp = c.get("/api/info")
        data = resp.json()
        assert data["max_steps"] is not None
        assert isinstance(data["max_steps"], int)
        assert data["max_steps"] > 0