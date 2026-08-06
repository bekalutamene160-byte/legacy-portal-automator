"""
Legacy Portal Automator - Domain Models
=======================================

Pydantic schemas that describe every "thing" the agent works with:
  1. PortalCredentials  - login identity for the demo portal
  2. PortalTask         - a single automation job (the user's request)
  3. DownloadedFile     - metadata for one file the agent pulled down
  4. PortalRunResult    - the full outcome of one agent run (for reports)

Design rules (read before editing):
- All sensitive fields use SecretStr so they NEVER leak in logs / repr / JSON.
- All datetime fields are timezone-aware UTC (no naive datetimes - they cause
  subtle bugs when comparing across machines).
- Path fields are stored as strings on the model and converted to Path via
  properties (Pydantic v2 + Path validation is finicky; strings are safer).
- Every model is frozen (immutable) by default - we never mutate a model in
  place; we build a new one when state changes. This makes debugging easy.
- Models are JSON-serializable via .model_dump_json() EXCEPT for SecretStr
  fields, which are masked automatically by Pydantic.

Usage:
    from src.models import PortalCredentials, PortalTask, PortalRunResult

    creds = PortalCredentials(username="admin", password="hunter2")
    task = PortalTask(
        portal_url="http://localhost:8001",
        credentials=creds,
        target_tab="Invoices",
        file_pattern="invoice_*.pdf",
    )
    print(task.model_dump_json(indent=2))  # password is masked as **********
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


# === Shared base config ===

class _FrozenModel(BaseModel):
    """Base class - all our models are immutable and use strict validation."""

    model_config = {
        "frozen": True,           # immutable after creation
        "str_strip_whitespace": True,  # trim strings automatically
        "extra": "forbid",        # reject unknown fields (catches typos)
        "validate_assignment": True,  # validate on attribute set (defensive)
    }


def _utcnow() -> datetime:
    """Timezone-aware 'now' in UTC. Helper for default factories."""
    return datetime.now(timezone.utc)


# =====================================================================
# 1. PortalCredentials
# =====================================================================

class PortalCredentials(_FrozenModel):
    """Login credentials for the demo portal.

    The password is stored as a SecretStr so it never appears in:
    - repr() / str() output
    - log messages
    - JSON dumps (shows as **********)
    - Tracebacks (shows as **********)

    To access the actual password value (only when passing to the browser):
        creds.password.get_secret_value()
    """

    username: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Portal username (1-128 chars, non-empty)",
    )
    password: SecretStr = Field(
        ...,
        min_length=1,
        description="Portal password (stored as SecretStr, never logged)",
    )

    @field_validator("username")
    @classmethod
    def _username_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("username must not be blank or whitespace-only")
        return v

    @field_validator("password")
    @classmethod
    def _password_not_blank(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value():
            raise ValueError("password must not be empty")
        return v


# =====================================================================
# 2. PortalTask
# =====================================================================

class PortalTask(_FrozenModel):
    """A single automation job: 'log into this portal and download these files.'

    This is the input the agent receives. It fully describes WHAT to do;
    the agent decides HOW to do it.

    Required fields:
        portal_url   - base URL of the portal (e.g. http://localhost:8001)
        credentials  - PortalCredentials for login

    Optional fields (with sensible defaults):
        target_tab        - which tab/section to navigate to
        file_pattern      - glob pattern for files to download (e.g. invoice_*.pdf)
        max_downloads     - safety cap to prevent runaway downloads
        download_subdir   - subfolder under download_dir to save files
    """

    portal_url: str = Field(
        ...,
        min_length=1,
        description="Base URL of the portal (e.g. http://localhost:8001)",
    )
    credentials: PortalCredentials = Field(
        ...,
        description="Login credentials for the portal",
    )

    target_tab: str = Field(
        default="Documents",
        min_length=1,
        max_length=128,
        description="Which tab/section to navigate to inside the portal",
    )
    file_pattern: str = Field(
        default="*",
        min_length=1,
        description="Glob pattern for files to download (e.g. invoice_*.pdf)",
    )
    max_downloads: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Safety cap - never download more than this per run",
    )
    download_subdir: str = Field(
        default="",
        description="Optional subfolder under download_dir (empty = root)",
    )

    @field_validator("portal_url")
    @classmethod
    def _url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"portal_url must start with http:// or https:// (got '{v}')"
            )
        return v.rstrip("/")

    @field_validator("file_pattern")
    @classmethod
    def _pattern_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("file_pattern must not be empty")
        return v

    @property
    def safe_filename_subdir(self) -> str:
        """Convert download_subdir into a filesystem-safe folder name.

        Returns empty string if no subdir is set.
        """
        if not self.download_subdir:
            return ""
        # Replace characters that are illegal in Windows/Linux paths
        illegal = '<>:"/\\|?*'
        safe = "".join("_" if c in illegal else c for c in self.download_subdir)
        return safe.strip().rstrip("/\\")


# =====================================================================
# 3. DownloadedFile
# =====================================================================

class DownloadedFile(_FrozenModel):
    """Metadata for one file the agent successfully downloaded.

    This is a record - created AFTER the download completes. It captures
    everything we need for the audit trail / PDF report.
    """

    filename: str = Field(
        ...,
        min_length=1,
        description="Original filename from the portal (e.g. invoice_2024_03.pdf)",
    )
    size_bytes: int = Field(
        ...,
        ge=0,
        description="File size in bytes (0 = empty file, still valid)",
    )
    downloaded_at: datetime = Field(
        default_factory=_utcnow,
        description="When the download completed (UTC, timezone-aware)",
    )
    local_path: str = Field(
        ...,
        min_length=1,
        description="Absolute or relative path where the file was saved",
    )

    @field_validator("filename")
    @classmethod
    def _filename_no_path_separators(cls, v: str) -> str:
        if "/" in v or "\\" in v:
            raise ValueError(
                f"filename must not contain path separators (got '{v}'). "
                "Use local_path for the full path."
            )
        return v

    @field_validator("local_path")
    @classmethod
    def _local_path_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("local_path must not be blank")
        return v

    @property
    def size_human(self) -> str:
        """Human-readable file size (e.g. '1.5 MB', '320 KB')."""
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0 or unit == "TB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{self.size_bytes} B"  # fallback

    @property
    def path_obj(self) -> Path:
        """local_path as a pathlib.Path object."""
        return Path(self.local_path)


# =====================================================================
# 4. PortalRunResult
# =====================================================================

class PortalRunResult(_FrozenModel):
    """Full outcome of one agent run.

    This is what the agent returns after completing (or failing) a PortalTask.
    It feeds directly into the PDF report generator in a later phase.

    Key invariants enforced here:
    - If success=True, error MUST be None (a successful run has no error).
    - If success=False, error MUST be a non-empty string (tell us what failed).
    - files_downloaded is a list of DownloadedFile objects (may be empty).
    - started_at <= completed_at (cannot finish before starting).
    - duration_seconds is computed automatically if not provided.
    """

    success: bool = Field(
        ...,
        description="True if the agent completed the task, False on failure",
    )
    files_downloaded: list[DownloadedFile] = Field(
        default_factory=list,
        description="List of files successfully downloaded (may be empty)",
    )
    total_steps: int = Field(
        default=0,
        ge=0,
        description="Number of agent steps taken (browser actions)",
    )
    total_tokens: int = Field(
        default=0,
        ge=0,
        description="Total LLM tokens consumed during this run (cost tracking)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if success=False, else None",
    )
    agent_trace: list[str] = Field(
        default_factory=list,
        description="Step-by-step trace of agent actions (for debugging)",
    )
    started_at: datetime = Field(
        default_factory=_utcnow,
        description="When the agent run started (UTC)",
    )
    completed_at: datetime = Field(
        default_factory=_utcnow,
        description="When the agent run completed (UTC)",
    )
    duration_seconds: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Run duration in seconds. Auto-computed if not set.",
    )

    @model_validator(mode="after")
    def _check_success_error_consistency(self) -> "PortalRunResult":
        """success=True requires error=None; success=False requires error set."""
        if self.success and self.error is not None:
            raise ValueError(
                f"success=True but error is set to '{self.error}'. "
                "A successful run must have error=None."
            )
        if not self.success and (self.error is None or not self.error.strip()):
            raise ValueError(
                "success=False but error is None or empty. "
                "A failed run must include an error message."
            )
        return self

    @model_validator(mode="after")
    def _check_timestamp_order(self) -> "PortalRunResult":
        """completed_at must be >= started_at (cannot finish before starting)."""
        if self.completed_at < self.started_at:
            raise ValueError(
                f"completed_at ({self.completed_at}) is before started_at "
                f"({self.started_at}). Cannot finish before starting."
            )
        return self

    @model_validator(mode="after")
    def _compute_duration_if_missing(self) -> "PortalRunResult":
        """If duration_seconds is None, compute it from the timestamps."""
        if self.duration_seconds is None:
            delta = (self.completed_at - self.started_at).total_seconds()
            # Use object.__setattr__ to bypass frozen check (Pydantic pattern)
            object.__setattr__(self, "duration_seconds", delta)
        return self

    @property
    def files_count(self) -> int:
        """Number of files successfully downloaded."""
        return len(self.files_downloaded)

    @property
    def total_bytes_downloaded(self) -> int:
        """Sum of all downloaded file sizes in bytes."""
        return sum(f.size_bytes for f in self.files_downloaded)

    @property
    def duration_human(self) -> str:
        """Human-readable duration (e.g. '12.3 s', '2.1 min')."""
        if self.duration_seconds is None:
            return "unknown"
        secs = self.duration_seconds
        if secs < 60:
            return f"{secs:.1f} s"
        if secs < 3600:
            return f"{secs / 60:.1f} min"
        return f"{secs / 3600:.1f} h"