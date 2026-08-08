"""Unit tests for the runner module.

These tests mock PortalAgent so no real browser or LLM is needed.
They verify that the runner correctly converts HTTP requests into
internal domain models and passes them to the agent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Path setup is handled by conftest.py, but we need the imports here
from schemas import RunRequest


@pytest.fixture
def sample_request() -> RunRequest:
    return RunRequest(
        portal_url="http://localhost:8001",
        username="admin",
        password="portal123",
        target_tab="Invoices",
        file_pattern="*.pdf",
        max_downloads=5,
        download_subdir="",
    )


class TestRunPortalTask:
    @pytest.mark.asyncio
    async def test_returns_result_from_agent(self, sample_request, test_settings):
        """The runner should return whatever PortalAgent.run() returns."""
        from src.models import PortalRunResult
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        expected = PortalRunResult(
            success=True,
            files_downloaded=[],
            total_steps=1,
            total_tokens=100,
            error=None,
            agent_trace=["start"],
            started_at=now,
            completed_at=now,
        )

        with patch("runner.PortalAgent") as MockAgent:
            mock_instance = MockAgent.return_value
            mock_instance.run = AsyncMock(return_value=expected)

            from runner import run_portal_task
            result = await run_portal_task(sample_request, test_settings)

            assert result is expected
            assert result.success is True

    @pytest.mark.asyncio
    async def test_passes_correct_task_to_agent(
        self, sample_request, test_settings
    ):
        """The runner should build a PortalTask from the request."""
        with patch("runner.PortalAgent") as MockAgent:
            mock_instance = MockAgent.return_value
            mock_instance.run = AsyncMock(return_value=None)

            from runner import run_portal_task
            await run_portal_task(sample_request, test_settings)

            # PortalAgent(settings=..., task=...) was called
            call_kwargs = MockAgent.call_args
            task_arg = call_kwargs.kwargs.get("task")
            assert task_arg is not None
            assert task_arg.portal_url == "http://localhost:8001"
            assert task_arg.target_tab == "Invoices"
            assert task_arg.file_pattern == "*.pdf"
            assert task_arg.max_downloads == 5

    @pytest.mark.asyncio
    async def test_passes_settings_to_agent(
        self, sample_request, test_settings
    ):
        """The runner should pass the settings to PortalAgent."""
        with patch("runner.PortalAgent") as MockAgent:
            mock_instance = MockAgent.return_value
            mock_instance.run = AsyncMock(return_value=None)

            from runner import run_portal_task
            await run_portal_task(sample_request, test_settings)

            call_kwargs = MockAgent.call_args
            settings_arg = call_kwargs.kwargs.get("settings")
            assert settings_arg is test_settings

    @pytest.mark.asyncio
    async def test_credentials_built_correctly(
        self, sample_request, test_settings
    ):
        """The runner should build PortalCredentials from the request."""
        with patch("runner.PortalAgent") as MockAgent:
            mock_instance = MockAgent.return_value
            mock_instance.run = AsyncMock(return_value=None)

            from runner import run_portal_task
            await run_portal_task(sample_request, test_settings)

            call_kwargs = MockAgent.call_args
            task_arg = call_kwargs.kwargs["task"]
            assert task_arg.credentials.username == "admin"
            # Password is SecretStr - check via get_secret_value()
            assert (
                task_arg.credentials.password.get_secret_value() == "portal123"
            )

    @pytest.mark.asyncio
    async def test_agent_run_called_once(self, sample_request, test_settings):
        """The runner should call agent.run() exactly once."""
        with patch("runner.PortalAgent") as MockAgent:
            mock_instance = MockAgent.return_value
            mock_instance.run = AsyncMock(return_value=None)

            from runner import run_portal_task
            await run_portal_task(sample_request, test_settings)

            assert mock_instance.run.call_count == 1

    @pytest.mark.asyncio
    async def test_default_values_used_when_omitted(self, test_settings):
        """When optional fields are omitted, defaults should be used."""
        req = RunRequest(
            portal_url="http://localhost:8001",
            username="admin",
            password="portal123",
        )

        with patch("runner.PortalAgent") as MockAgent:
            mock_instance = MockAgent.return_value
            mock_instance.run = AsyncMock(return_value=None)

            from runner import run_portal_task
            await run_portal_task(req, test_settings)

            call_kwargs = MockAgent.call_args
            task_arg = call_kwargs.kwargs["task"]
            assert task_arg.target_tab == "Documents"
            assert task_arg.file_pattern == "*"
            assert task_arg.max_downloads == 10