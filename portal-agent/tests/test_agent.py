"""
Tests for src/agent.py

Run: pytest tests/test_agent.py -v

CRITICAL DESIGN:
These tests mock browser_use.Agent.run() and the browser session so that
NO real browser launches and NO real LLM calls are made. This keeps tests
fast (<1s) and free (no Groq tokens consumed).

We test:
  1. Prompt building (the PLAN stage)
  2. Success path (execute + verify + report)
  3. Failure path (execute raises, recovery kicks in, final failure reported)
  4. Recovery (first attempt fails, second succeeds)
  5. Verify stage (download directory scanning)
  6. max_retries validation
  7. Trace contents (audit trail correctness)

The mocking strategy:
- Monkeypatch src.agent.browser_session to yield a fake session
- Monkeypatch src.agent.Agent to a fake that returns a fake AgentHistoryList
- Monkeypatch asyncio.sleep so retries don't actually wait
- Use real tmp_path for downloads so _verify_downloads is exercised for real
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent import (
    DEFAULT_MAX_RETRIES,
    PortalAgent,
    RETRY_DELAY_SECONDS,
)
from src.config import Settings
from src.models import PortalCredentials, PortalTask


# =====================================================================
# Fixtures and helpers
# =====================================================================

def _make_settings(download_dir: Path, **overrides) -> Settings:
    """Build Settings with a real tmp_path as download_dir."""
    defaults = {
        "groq_api_key": "gsk_testkey_1234567890abcdefghijklmnopqrstuvwxyz",
        "groq_model": "llama-3.3-70b-versatile",
        "headless": True,
        "use_vision": False,
        "proxy_url": "",
        "download_dir": str(download_dir),
        "max_steps": 20,
        "agent_timeout": 120,
        "portal_host": "localhost",
        "portal_port": 8001,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _make_task(**overrides) -> PortalTask:
    """Build a PortalTask with sensible test defaults."""
    defaults = {
        "portal_url": "http://localhost:8001",
        "credentials": PortalCredentials(username="admin", password="hunter2"),
        "target_tab": "Invoices",
        "file_pattern": "invoice_*.pdf",
        "max_downloads": 5,
    }
    defaults.update(overrides)
    return PortalTask(**defaults)


class _FakeUsage:
    """Mimics browser_use's UsageSummary - just the fields we read."""
    def __init__(self, total_tokens: int = 1000):
        self.total_tokens = total_tokens


class _FakeAgentHistory:
    """Mimics browser_use's AgentHistoryList - just the methods we call."""
    def __init__(self, steps: int = 5, tokens: int = 1000):
        self._steps = steps
        self.usage = _FakeUsage(tokens)

    def number_of_steps(self) -> int:
        return self._steps


def _make_fake_agent_run(history: _FakeAgentHistory):
    """Build a fake Agent class whose .run() returns the given history.

    The fake Agent is constructed with the same kwargs as the real one
    (task, llm, browser, use_vision, max_failures) so we can assert on them.
    """
    class _FakeAgent:
        instances = []

        def __init__(self, task, llm, browser, use_vision, max_failures):
            self.task = task
            self.llm = llm
            self.browser = browser
            self.use_vision = use_vision
            self.max_failures = max_failures
            _FakeAgent.instances.append(self)

        async def run(self, max_steps: int = 500):
            _FakeAgent.last_max_steps = max_steps
            return history

    return _FakeAgent


def _make_failing_agent_run(error: Exception):
    """Build a fake Agent whose .run() always raises the given error."""
    class _FailingAgent:
        def __init__(self, task, llm, browser, use_vision, max_failures):
            self.task = task

        async def run(self, max_steps: int = 500):
            raise error

    return _FailingAgent


# =====================================================================
# Tests: prompt building (PLAN stage)
# =====================================================================

class TestPromptBuilding:
    """Tests for the _build_prompt method (Stage 1: PLAN)."""

    def test_prompt_contains_portal_url(self):
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "http://localhost:8001" in prompt

    def test_prompt_contains_username(self):
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "admin" in prompt

    def test_prompt_contains_password(self):
        """Password must be in the prompt (LLM needs it to type into the form).

        Note: this is the prompt STRING, not a log. The prompt is sent to the
        LLM only - it never appears in agent_trace or PortalRunResult.
        """
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "hunter2" in prompt

    def test_prompt_contains_target_tab(self):
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "Invoices" in prompt

    def test_prompt_contains_file_pattern(self):
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "invoice_*.pdf" in prompt

    def test_prompt_contains_max_downloads(self):
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task(max_downloads=7))
        prompt = agent._build_prompt(attempt=0)
        assert "7" in prompt

    def test_prompt_first_attempt_has_no_retry_note(self):
        """On attempt 0, the retry hint should NOT be in the prompt."""
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "retry attempt" not in prompt.lower()

    def test_prompt_retry_attempt_has_note(self):
        """On attempt 1+, a retry hint should be added."""
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=1)
        assert "retry attempt" in prompt.lower()
        assert "2" in prompt  # attempt 1 = "retry attempt 2"

    def test_prompt_contains_step_by_step_instructions(self):
        """The prompt should include numbered step-by-step instructions."""
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        prompt = agent._build_prompt(attempt=0)
        assert "STEP-BY-STEP INSTRUCTIONS" in prompt
        assert "1." in prompt
        assert "10." in prompt


# =====================================================================
# Tests: max_retries validation
# =====================================================================

class TestMaxRetriesValidation:
    """Tests for the constructor's max_retries bounds checking."""

    def test_zero_retries_allowed(self):
        """max_retries=0 means 'try once, no retries' - valid."""
        agent = PortalAgent(
            _make_settings(Path("/tmp")),
            _make_task(),
            max_retries=0,
        )
        assert agent.max_retries == 0

    def test_five_retries_allowed(self):
        """max_retries=5 is the upper bound - valid."""
        agent = PortalAgent(
            _make_settings(Path("/tmp")),
            _make_task(),
            max_retries=5,
        )
        assert agent.max_retries == 5

    def test_negative_retries_rejected(self):
        with pytest.raises(ValueError) as exc:
            PortalAgent(_make_settings(Path("/tmp")), _make_task(), max_retries=-1)
        assert "max_retries" in str(exc.value).lower()

    def test_six_retries_rejected(self):
        with pytest.raises(ValueError) as exc:
            PortalAgent(_make_settings(Path("/tmp")), _make_task(), max_retries=6)
        assert "max_retries" in str(exc.value).lower()

    def test_default_max_retries_is_two(self):
        """If not specified, max_retries should default to DEFAULT_MAX_RETRIES."""
        agent = PortalAgent(_make_settings(Path("/tmp")), _make_task())
        assert agent.max_retries == DEFAULT_MAX_RETRIES == 2


# =====================================================================
# Tests: verify downloads (VERIFY stage)
# =====================================================================

class TestVerifyDownloads:
    """Tests for the _verify_downloads method (Stage 3: VERIFY)."""

    def test_verify_finds_matching_files(self, tmp_path, monkeypatch):
        """Files matching the pattern should be discovered."""
        # Disable the post-download settle delay for tests
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)

        # Create test files
        (tmp_path / "invoice_001.pdf").write_bytes(b"fake pdf 1")
        (tmp_path / "invoice_002.pdf").write_bytes(b"fake pdf 2")
        (tmp_path / "other.txt").write_bytes(b"not a match")

        settings = _make_settings(tmp_path)
        task = _make_task(file_pattern="invoice_*.pdf")
        agent = PortalAgent(settings, task)

        files = agent._verify_downloads()
        assert len(files) == 2
        filenames = {f.filename for f in files}
        assert filenames == {"invoice_001.pdf", "invoice_002.pdf"}

    def test_verify_returns_empty_when_no_matches(self, tmp_path, monkeypatch):
        """When no files match the pattern, return empty list (not error)."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        (tmp_path / "other.txt").write_bytes(b"not a match")

        settings = _make_settings(tmp_path)
        task = _make_task(file_pattern="invoice_*.pdf")
        agent = PortalAgent(settings, task)

        files = agent._verify_downloads()
        assert files == []

    def test_verify_respects_max_downloads(self, tmp_path, monkeypatch):
        """Even if 10 files match, max_downloads caps the result list."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)

        # Create 10 matching files
        for i in range(10):
            (tmp_path / f"invoice_{i:03d}.pdf").write_bytes(b"x" * 100)

        settings = _make_settings(tmp_path)
        task = _make_task(file_pattern="invoice_*.pdf", max_downloads=3)
        agent = PortalAgent(settings, task)

        files = agent._verify_downloads()
        assert len(files) == 3

    def test_verify_includes_size_bytes(self, tmp_path, monkeypatch):
        """DownloadedFile.size_bytes should match the actual file size."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        (tmp_path / "invoice_001.pdf").write_bytes(b"x" * 1234)

        settings = _make_settings(tmp_path)
        agent = PortalAgent(settings, _make_task())
        files = agent._verify_downloads()

        assert len(files) == 1
        assert files[0].size_bytes == 1234

    def test_verify_uses_subdir_when_set(self, tmp_path, monkeypatch):
        """When task.download_subdir is set, verify looks in that subdir."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)

        # Create the subdir and put a file there
        subdir = tmp_path / "2024_Q1"
        subdir.mkdir()
        (subdir / "invoice_001.pdf").write_bytes(b"in subdir")

        # Also put a file in the root - should NOT be picked up
        (tmp_path / "invoice_root.pdf").write_bytes(b"in root")

        settings = _make_settings(tmp_path)
        task = _make_task(
            file_pattern="invoice_*.pdf",
            download_subdir="2024/Q1",  # / and : get replaced with _
        )
        agent = PortalAgent(settings, task)

        files = agent._verify_downloads()
        assert len(files) == 1
        assert files[0].filename == "invoice_001.pdf"

    def test_verify_creates_missing_download_dir(self, tmp_path, monkeypatch):
        """If the download dir doesn't exist, _download_dir should create it."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)

        missing_dir = tmp_path / "does_not_exist_yet"
        settings = _make_settings(missing_dir)
        agent = PortalAgent(settings, _make_task())

        # This should not raise - the dir gets created
        files = agent._verify_downloads()
        assert files == []
        assert missing_dir.exists()


# =====================================================================
# Tests: full run() with mocked browser-use
# =====================================================================

class TestPortalAgentRun:
    """Integration tests for PortalAgent.run() with mocked browser-use."""

    @pytest.mark.asyncio
    async def test_successful_run_returns_success_result(self, tmp_path, monkeypatch):
        """A run where the agent succeeds and files exist should return success=True."""
        # Disable sleeps for fast tests
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)

        # Pre-create the file that _verify_downloads will find
        (tmp_path / "invoice_001.pdf").write_bytes(b"fake pdf content")

        settings = _make_settings(tmp_path)
        task = _make_task()
        agent = PortalAgent(settings, task, max_retries=0)

        # Mock the browser session and Agent
        fake_history = _FakeAgentHistory(steps=5, tokens=750)
        fake_agent_cls = _make_fake_agent_run(fake_history)

        # Mock browser_session to yield a dummy session
        class _FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False

        fake_session_ctx = _FakeSession()

        with patch("src.agent.browser_session", return_value=fake_session_ctx), \
             patch("src.agent.Agent", fake_agent_cls), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        assert result.success is True
        assert result.files_count == 1
        assert result.files_downloaded[0].filename == "invoice_001.pdf"
        assert result.total_steps == 5
        assert result.total_tokens == 750
        assert result.error is None
        assert len(result.agent_trace) > 0
        # The trace should include START, PLAN, EXECUTE, VERIFY, REPORT entries
        trace_str = "\n".join(result.agent_trace)
        assert "START" in trace_str
        assert "PLAN" in trace_str
        assert "EXECUTE" in trace_str
        assert "VERIFY" in trace_str
        assert "REPORT" in trace_str

    @pytest.mark.asyncio
    async def test_no_files_downloaded_returns_failure(self, tmp_path, monkeypatch):
        """If agent runs but no files match, result should be failure."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)

        # No files created - verify will find nothing
        settings = _make_settings(tmp_path)
        task = _make_task()
        agent = PortalAgent(settings, task, max_retries=0)

        fake_history = _FakeAgentHistory(steps=3, tokens=500)
        fake_agent_cls = _make_fake_agent_run(fake_history)

        class _FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False

        with patch("src.agent.browser_session", return_value=_FakeSession()), \
             patch("src.agent.Agent", fake_agent_cls), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        assert result.success is False
        assert result.files_count == 0
        assert result.error is not None
        assert "no files matching" in result.error.lower()
        # We still tracked steps/tokens even though it failed
        assert result.total_steps == 3
        assert result.total_tokens == 500

    @pytest.mark.asyncio
    async def test_exception_during_run_is_caught(self, tmp_path, monkeypatch):
        """If Agent.run raises, we should catch it and report failure."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)

        settings = _make_settings(tmp_path)
        task = _make_task()
        agent = PortalAgent(settings, task, max_retries=1)

        # Agent that always raises
        failing_agent = _make_failing_agent_run(
            RuntimeError("Browser crashed")
        )

        class _FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False

        with patch("src.agent.browser_session", return_value=_FakeSession()), \
             patch("src.agent.Agent", failing_agent), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        assert result.success is False
        assert "RuntimeError" in result.error
        assert "Browser crashed" in result.error
        # Trace should show the exception
        trace_str = "\n".join(result.agent_trace)
        assert "EXCEPTION" in trace_str

    @pytest.mark.asyncio
    async def test_recovery_succeeds_on_second_attempt(self, tmp_path, monkeypatch):
        """If first attempt fails but second succeeds, result should be success."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)

        # File exists, but only the second attempt will find it
        # (We control this via the fake agent returning success on attempt 2)
        (tmp_path / "invoice_001.pdf").write_bytes(b"found on retry")

        settings = _make_settings(tmp_path)
        task = _make_task()
        agent = PortalAgent(settings, task, max_retries=2)

        # First call: simulate failure (no exception, but no files)
        # Second call: success (files exist now)
        # Since _verify_downloads is the same both times and the file exists
        # from the start, we need a different approach: make first attempt
        # raise an exception, second succeed.
        call_count = {"n": 0}

        class _AgentThatFailsFirst:
            def __init__(self, task, llm, browser, use_vision, max_failures):
                pass
            async def run(self, max_steps=500):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("First attempt fails")
                return _FakeAgentHistory(steps=4, tokens=600)

        class _FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False

        with patch("src.agent.browser_session", return_value=_FakeSession()), \
             patch("src.agent.Agent", _AgentThatFailsFirst), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        assert result.success is True
        assert result.files_count == 1
        # The error from the first attempt should NOT be in the final result
        assert result.error is None
        # But the trace should mention the first failure
        trace_str = "\n".join(result.agent_trace)
        assert "EXCEPTION" in trace_str
        assert "First attempt fails" in trace_str
        # Total steps/tokens should be cumulative
        assert result.total_steps == 4  # only the successful attempt's steps
        assert result.total_tokens == 600

    @pytest.mark.asyncio
    async def test_timeout_is_handled(self, tmp_path, monkeypatch):
        """If agent.run times out, we should report it as a failure."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)

        settings = _make_settings(tmp_path, agent_timeout=10)
        task = _make_task()
        agent = PortalAgent(settings, task, max_retries=0)

        # Agent whose run hangs forever (will be timed out by asyncio.wait_for)
        class _HangingAgent:
            def __init__(self, task, llm, browser, use_vision, max_failures):
                pass
            async def run(self, max_steps=500):
                await asyncio.sleep(1000)  # way longer than timeout
                return _FakeAgentHistory()

        class _FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False

        with patch("src.agent.browser_session", return_value=_FakeSession()), \
             patch("src.agent.Agent", _HangingAgent), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        assert result.success is False
        assert "timed out" in result.error.lower() or "timeout" in result.error.lower()
        trace_str = "\n".join(result.agent_trace)
        assert "TIMEOUT" in trace_str

    @pytest.mark.asyncio
    async def test_trace_starts_with_start_entry(self, tmp_path, monkeypatch):
        """Every run's trace should begin with a START entry."""
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)
        (tmp_path / "invoice_001.pdf").write_bytes(b"x")

        settings = _make_settings(tmp_path)
        agent = PortalAgent(settings, _make_task(), max_retries=0)

        fake_agent_cls = _make_fake_agent_run(_FakeAgentHistory())

        class _FakeSession:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False

        with patch("src.agent.browser_session", return_value=_FakeSession()), \
             patch("src.agent.Agent", fake_agent_cls), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        assert result.agent_trace[0].startswith("START:")

    @pytest.mark.asyncio
    async def test_run_never_raises_to_caller(self, tmp_path, monkeypatch):
        """Even if everything goes wrong, run() returns a PortalRunResult.

        This is the most important contract: the FastAPI layer relies on
        never getting an exception from run().
        """
        monkeypatch.setattr("src.agent.POST_DOWNLOAD_SETTLE_SECONDS", 0.0)
        monkeypatch.setattr("src.agent.RETRY_DELAY_SECONDS", 0.0)

        settings = _make_settings(tmp_path)
        task = _make_task()
        agent = PortalAgent(settings, task, max_retries=0)

        # Make EVERYTHING raise - browser session, agent, etc.
        class _ExplodingSession:
            async def __aenter__(self):
                raise ConnectionError("Browser binary not found")
            async def __aexit__(self, *args):
                return False

        with patch("src.agent.browser_session", return_value=_ExplodingSession()), \
             patch("src.agent.Agent", _make_failing_agent_run(RuntimeError("x"))), \
             patch("src.agent.ChatGroq"):
            result = await agent.run()

        # Should NOT have raised - we get a failure result
        assert result.success is False
        assert result.error is not None