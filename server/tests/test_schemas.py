"""Tests for the HTTP request/response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import RunRequest, ServerInfo


class TestRunRequestValidation:
    def test_valid_request_with_defaults(self):
        req = RunRequest(
            portal_url="http://localhost:8001",
            username="admin",
            password="portal123",
        )
        assert req.portal_url == "http://localhost:8001"
        assert req.username == "admin"
        assert req.password == "portal123"
        assert req.target_tab == "Documents"
        assert req.file_pattern == "*"
        assert req.max_downloads == 10
        assert req.download_subdir == ""

    def test_valid_request_with_custom_values(self):
        req = RunRequest(
            portal_url="http://example.com",
            username="user1",
            password="pass1",
            target_tab="Invoices",
            file_pattern="*.pdf",
            max_downloads=5,
            download_subdir="subfolder",
        )
        assert req.target_tab == "Invoices"
        assert req.file_pattern == "*.pdf"
        assert req.max_downloads == 5
        assert req.download_subdir == "subfolder"

    def test_missing_portal_url_fails(self):
        with pytest.raises(ValidationError):
            RunRequest(username="admin", password="portal123")

    def test_missing_username_fails(self):
        with pytest.raises(ValidationError):
            RunRequest(portal_url="http://localhost:8001", password="portal123")

    def test_missing_password_fails(self):
        with pytest.raises(ValidationError):
            RunRequest(portal_url="http://localhost:8001", username="admin")

    def test_max_downloads_zero_fails(self):
        with pytest.raises(ValidationError):
            RunRequest(
                portal_url="http://localhost:8001",
                username="admin",
                password="portal123",
                max_downloads=0,
            )

    def test_max_downloads_negative_fails(self):
        with pytest.raises(ValidationError):
            RunRequest(
                portal_url="http://localhost:8001",
                username="admin",
                password="portal123",
                max_downloads=-1,
            )

    def test_max_downloads_over_100_fails(self):
        with pytest.raises(ValidationError):
            RunRequest(
                portal_url="http://localhost:8001",
                username="admin",
                password="portal123",
                max_downloads=101,
            )

    def test_max_downloads_one_is_valid(self):
        req = RunRequest(
            portal_url="http://localhost:8001",
            username="admin",
            password="portal123",
            max_downloads=1,
        )
        assert req.max_downloads == 1

    def test_max_downloads_100_is_valid(self):
        req = RunRequest(
            portal_url="http://localhost:8001",
            username="admin",
            password="portal123",
            max_downloads=100,
        )
        assert req.max_downloads == 100


class TestServerInfo:
    def test_minimal_server_info(self):
        info = ServerInfo(
            name="Test API",
            version="1.0.0",
            docs_url="/docs",
            health_url="/health",
        )
        assert info.name == "Test API"
        assert info.version == "1.0.0"
        assert info.configured_model is None
        assert info.headless_mode is None
        assert info.max_steps is None

    def test_full_server_info(self):
        info = ServerInfo(
            name="Test API",
            version="1.0.0",
            docs_url="/docs",
            health_url="/health",
            configured_model="llama-3.3-70b-versatile",
            headless_mode=True,
            max_steps=50,
        )
        assert info.configured_model == "llama-3.3-70b-versatile"
        assert info.headless_mode is True
        assert info.max_steps == 50