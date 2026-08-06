"""
Legacy Portal Automator - The 5-Stage Agent Loop
=================================================

This is the centerpiece of the project. It wires together everything we
built in Phases 1-5:

    Settings (Phase 3) ──┐
    Models  (Phase 4) ───┼──► PortalAgent.run() ──► PortalRunResult
    Browser (Phase 5) ───┤           │
    Groq    (Phase 2) ───┘           │
                                     ▼
                          browser_use.Agent (the actual LLM-driven browser)

The 5-Stage Loop:
    1. PLAN     - Build a precise task prompt from PortalTask
    2. EXECUTE  - Run browser_use.Agent with our Groq LLM + stealth browser
    3. VERIFY   - Check that downloads actually landed on disk
    4. RECOVER  - If verify fails, retry up to N times with adjusted prompt
    5. REPORT   - Build a PortalRunResult with full audit trail

Design rules:
- The agent NEVER mutates PortalTask - it builds a prompt string from it.
- Recovery is bounded: max_retries (default 2) prevents infinite loops.
- All exceptions are caught and reported in PortalRunResult.error - the
  agent never raises to its caller. This makes the FastAPI layer simple.
- Token usage and step count are extracted from browser_use's history.
- The trace is a list of human-readable strings - perfect for the PDF report.

Usage:
    from src.agent import PortalAgent
    from src.config import settings
    from src.models import PortalCredentials, PortalTask

    task = PortalTask(
        portal_url="http://localhost:8001",
        credentials=PortalCredentials(username="admin", password="secret"),
        target_tab="Invoices",
        file_pattern="invoice_*.pdf",
    )

    agent = PortalAgent(settings=settings, task=task)
    result = await agent.run()

    if result.success:
        print(f"Downloaded {result.files_count} files in {result.duration_human}")
    else:
        print(f"Failed: {result.error}")
"""

from __future__ import annotations

import asyncio
import glob
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from browser_use import Agent
from browser_use.llm import ChatGroq

from src.browser import browser_session
from src.config import Settings
from src.models import (
    DownloadedFile,
    PortalCredentials,
    PortalRunResult,
    PortalTask,
)


logger = logging.getLogger(__name__)


# =====================================================================
# Constants
# =====================================================================

# Default retry count for the recovery stage.
# Each retry costs LLM tokens, so we keep this small.
DEFAULT_MAX_RETRIES = 2

# Delay between retries (seconds). Gives the portal a moment to recover
# if it was rate-limiting us.
RETRY_DELAY_SECONDS = 2.0

# Sleep before checking the download directory, to let Chromium finish
# writing the file to disk. Without this, we sometimes see 0 files
# immediately after the agent reports success.
POST_DOWNLOAD_SETTLE_SECONDS = 1.5


# =====================================================================
# The Agent
# =====================================================================

class PortalAgent:
    """Wraps browser_use.Agent with the 5-stage loop.

    Lifecycle:
        agent = PortalAgent(settings, task)
        result = await agent.run()   # one-shot, returns PortalRunResult

    The agent is single-use: do not call run() twice on the same instance.
    Build a new PortalAgent for each task.

    Args:
        settings: typed Settings (from src.config)
        task: PortalTask describing what to do
        max_retries: how many times to retry on failure (default 2)
    """

    def __init__(
        self,
        settings: Settings,
        task: PortalTask,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        if max_retries < 0 or max_retries > 5:
            raise ValueError(
                f"max_retries must be between 0 and 5 (got {max_retries}). "
                "More than 5 retries wastes LLM tokens."
            )

        self.settings = settings
        self.task = task
        self.max_retries = max_retries
        self._trace: list[str] = []
        self._started_at: Optional[datetime] = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def run(self) -> PortalRunResult:
        """Execute the 5-stage loop. Returns PortalRunResult (never raises).

        This is the ONLY public method. It always returns a PortalRunResult -
        success or failure is encoded in result.success, not in exceptions.
        """
        self._started_at = _utcnow()
        self._trace.clear()
        self._trace.append(
            f"START: task target_tab={self.task.target_tab!r} "
            f"pattern={self.task.file_pattern!r} "
            f"max_downloads={self.task.max_downloads}"
        )

        last_error: Optional[str] = None
        attempt = 0
        total_steps = 0
        total_tokens = 0

        # === Stages 1-4: Plan + Execute + Verify + Recover ===
        while attempt <= self.max_retries:
            attempt_label = f"attempt {attempt + 1}/{self.max_retries + 1}"
            self._trace.append(f"PLAN ({attempt_label}): building prompt")

            prompt = self._build_prompt(attempt=attempt)

            try:
                self._trace.append(f"EXECUTE ({attempt_label}): launching browser-use Agent")
                steps, tokens = await self._execute_once(prompt)

                total_steps += steps
                total_tokens += tokens
                self._trace.append(
                    f"EXECUTE ({attempt_label}): completed steps={steps} tokens={tokens}"
                )

                # Stage 3: VERIFY
                self._trace.append(f"VERIFY ({attempt_label}): checking downloads on disk")
                files = self._verify_downloads()

                if len(files) > 0:
                    # Success! Files landed.
                    self._trace.append(
                        f"VERIFY ({attempt_label}): PASSED - {len(files)} files downloaded"
                    )
                    return self._build_success_result(
                        files=files,
                        total_steps=total_steps,
                        total_tokens=total_tokens,
                    )

                # No files found - retry if we have attempts left
                last_error = (
                    f"Agent completed {steps} steps but no files matching "
                    f"'{self.task.file_pattern}' were found in "
                    f"{self._download_dir()}"
                )
                self._trace.append(f"VERIFY ({attempt_label}): FAILED - {last_error}")

            except asyncio.TimeoutError:
                last_error = (
                    f"Agent timed out after {self.settings.agent_timeout}s "
                    f"(attempt {attempt + 1})"
                )
                self._trace.append(f"EXECUTE ({attempt_label}): TIMEOUT - {last_error}")
            except Exception as e:
                # Catch ALL exceptions - we never raise to the caller
                last_error = f"{type(e).__name__}: {e}"
                self._trace.append(
                    f"EXECUTE ({attempt_label}): EXCEPTION - {last_error}"
                )
                logger.exception("Agent attempt %d failed", attempt + 1)

            # Stage 4: RECOVER (decide whether to retry)
            if attempt < self.max_retries:
                self._trace.append(
                    f"RECOVER: waiting {RETRY_DELAY_SECONDS}s before retry..."
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            attempt += 1

        # === Stage 5: REPORT (failure case) ===
        self._trace.append(f"REPORT: FAILED after {attempt} attempts")
        return self._build_failure_result(
            error=last_error or "Unknown failure",
            total_steps=total_steps,
            total_tokens=total_tokens,
        )

    # -----------------------------------------------------------------
    # Stage 1: PLAN - build the task prompt for browser-use
    # -----------------------------------------------------------------

    def _build_prompt(self, attempt: int) -> str:
        """Construct the natural-language prompt for browser_use.Agent.

        We don't just hand the raw task to the LLM - we add:
        - Explicit login instructions (portal-style: username, password, submit)
        - The target tab name
        - The file pattern to match
        - A hard cap on downloads (safety against runaway agents)
        - On retries: a hint that the previous attempt failed

        The prompt is intentionally verbose - LLMs do better with explicit
        instructions than with terse ones.
        """
        creds: PortalCredentials = self.task.credentials
        password_value = creds.password.get_secret_value()
        download_dir = self._download_dir()

        prompt_parts: list[str] = [
            f"You are an autonomous browser agent. Your job is to log into a "
            f"legacy-style web portal and download files.",
            "",
            f"PORTAL URL: {self.task.portal_url}",
            f"USERNAME: {creds.username}",
            f"PASSWORD: {password_value}",
            "",
            f"STEP-BY-STEP INSTRUCTIONS:",
            f"1. Navigate to {self.task.portal_url}",
            f"2. Find the username field and type: {creds.username}",
            f"3. Find the password field and type: {password_value}",
            f"4. Click the login button (often labelled 'Sign in' or 'Login')",
            f"5. Wait for the page to load after login",
            f"6. Find and click the tab or menu item labelled '{self.task.target_tab}'",
            f"7. Look for files matching this pattern: {self.task.file_pattern}",
            f"8. Download up to {self.task.max_downloads} matching files",
            f"9. Files will be saved automatically to: {download_dir}",
            f"10. Once all matching files are downloaded, you are done.",
            "",
            f"IMPORTANT RULES:",
            f"- Do NOT download more than {self.task.max_downloads} files.",
            f"- If a download link requires a click, click it and wait.",
            f"- If the portal shows a popup or confirmation, accept it.",
            f"- Stop as soon as you have downloaded all matching files.",
        ]

        if attempt > 0:
            prompt_parts.extend([
                "",
                f"NOTE: This is retry attempt {attempt + 1}. "
                f"A previous attempt failed. Be extra careful and try a "
                f"slightly different approach if a button is hard to find.",
            ])

        return "\n".join(prompt_parts)

    # -----------------------------------------------------------------
    # Stage 2: EXECUTE - run browser_use.Agent once
    # -----------------------------------------------------------------

    async def _execute_once(self, prompt: str) -> tuple[int, int]:
        """Run browser_use.Agent a single time.

        Returns:
            (step_count, token_count) tuple

        Raises:
            Any exception browser_use raises - the caller handles recovery.
        """
        llm = ChatGroq(
            model=self.settings.groq_model,
            api_key=self.settings.groq_api_key.get_secret_value(),
        )

        async with browser_session(self.settings) as session:
            agent = Agent(
                task=prompt,
                llm=llm,
                browser=session,
                use_vision=self.settings.use_vision,
                max_failures=3,
            )

            # Apply our hard timeout (settings.agent_timeout)
            history = await asyncio.wait_for(
                agent.run(max_steps=self.settings.max_steps),
                timeout=self.settings.agent_timeout,
            )

            step_count = history.number_of_steps()
            token_count = 0
            if history.usage is not None:
                token_count = history.usage.total_tokens

            return step_count, token_count

    # -----------------------------------------------------------------
    # Stage 3: VERIFY - check the filesystem
    # -----------------------------------------------------------------

    def _verify_downloads(self) -> list[DownloadedFile]:
        """Scan the download directory for files matching the pattern.

        Returns a list of DownloadedFile objects, sorted by filename.
        Empty list means no files matched (verification failed).

        We use a small settle delay because Chromium writes files
        asynchronously - the agent's "done" signal can arrive before
        the file is fully on disk.
        """
        import time
        time.sleep(POST_DOWNLOAD_SETTLE_SECONDS)

        download_dir = self._download_dir()
        if not download_dir.exists():
            self._trace.append(
                f"VERIFY: download dir {download_dir} does not exist"
            )
            return []

        # Convert glob pattern to filesystem search
        # e.g. "invoice_*.pdf" -> search in download_dir for matching files
        search_pattern = str(download_dir / self.task.file_pattern)
        matching_paths = sorted(glob.glob(search_pattern))

        files: list[DownloadedFile] = []
        for path_str in matching_paths:
            p = Path(path_str)
            if not p.is_file():
                continue  # skip directories
            try:
                size = p.stat().st_size
            except OSError as e:
                self._trace.append(f"VERIFY: could not stat {p}: {e}")
                continue

            files.append(DownloadedFile(
                filename=p.name,
                size_bytes=size,
                local_path=str(p.resolve()),
            ))

            # Respect max_downloads even at verify time
            if len(files) >= self.task.max_downloads:
                break

        return files

    # -----------------------------------------------------------------
    # Stage 5: REPORT - build PortalRunResult
    # -----------------------------------------------------------------

    def _build_success_result(
        self,
        files: list[DownloadedFile],
        total_steps: int,
        total_tokens: int,
    ) -> PortalRunResult:
        """Construct a successful PortalRunResult."""
        completed_at = _utcnow()
        self._trace.append(
            f"REPORT: SUCCESS - {len(files)} files, "
            f"{sum(f.size_bytes for f in files)} bytes total"
        )
        return PortalRunResult(
            success=True,
            files_downloaded=files,
            total_steps=total_steps,
            total_tokens=total_tokens,
            error=None,
            agent_trace=list(self._trace),
            started_at=self._started_at or _utcnow(),
            completed_at=completed_at,
        )

    def _build_failure_result(
        self,
        error: str,
        total_steps: int,
        total_tokens: int,
    ) -> PortalRunResult:
        """Construct a failed PortalRunResult."""
        completed_at = _utcnow()
        return PortalRunResult(
            success=False,
            files_downloaded=[],
            total_steps=total_steps,
            total_tokens=total_tokens,
            error=error,
            agent_trace=list(self._trace),
            started_at=self._started_at or _utcnow(),
            completed_at=completed_at,
        )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _download_dir(self) -> Path:
        """The download directory for this task.

        Combines settings.download_path with task.safe_filename_subdir.
        Creates the directory if it doesn't exist.
        """
        base = self.settings.download_path
        subdir = self.task.safe_filename_subdir
        if subdir:
            full = base / subdir
        else:
            full = base
        full.mkdir(parents=True, exist_ok=True)
        return full


# =====================================================================
# Helpers
# =====================================================================

def _utcnow() -> datetime:
    """Timezone-aware UTC now. Helper to keep imports tidy."""
    return datetime.now(timezone.utc)