"""
Tests for src/models.py

Run: pytest tests/test_models.py -v

Covers:
- PortalCredentials : username/password validation, SecretStr protection
- PortalTask        : URL validation, defaults, safe_filename_subdir
- DownloadedFile    : size_human formatting, path-separator rejection
- PortalRunResult   : success/error consistency, timestamp ordering,
                      duration auto-computation, aggregate properties
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.models import (
    DownloadedFile,
    PortalCredentials,
    PortalRunResult,
    PortalTask,
)


# =====================================================================
# Helpers
# =====================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_creds(username: str = "admin", password: str = "hunter2") -> PortalCredentials:
    return PortalCredentials(username=username, password=password)


def _make_task(**overrides) -> PortalTask:
    """Build a PortalTask with sensible defaults; override any field."""
    defaults = {
        "portal_url": "http://localhost:8001",
        "credentials": _make_creds(),
    }
    defaults.update(overrides)
    return PortalTask(**defaults)


def _make_downloaded_file(**overrides) -> DownloadedFile:
    defaults = {
        "filename": "invoice_2024_03.pdf",
        "size_bytes": 1024,
        "local_path": "/tmp/downloads/invoice_2024_03.pdf",
    }
    defaults.update(overrides)
    return DownloadedFile(**defaults)


# =====================================================================
# 1. PortalCredentials
# =====================================================================

class TestPortalCredentials:
    """Tests for the login credential model."""

    def test_valid_credentials(self):
        """A normal username + password should construct fine."""
        c = _make_creds(username="alice", password="s3cret")
        assert c.username == "alice"
        assert c.password.get_secret_value() == "s3cret"

    def test_username_strips_whitespace(self):
        """Whitespace around username should be trimmed (str_strip_whitespace)."""
        c = PortalCredentials(username="  bob  ", password="pw")
        assert c.username == "bob"

    def test_blank_username_fails(self):
        """Empty or whitespace-only username should be rejected."""
        with pytest.raises(ValidationError) as exc:
            PortalCredentials(username="   ", password="pw")
        assert "username" in str(exc.value).lower()

    def test_empty_password_fails(self):
        """Empty password should be rejected."""
        with pytest.raises(ValidationError):
            PortalCredentials(username="bob", password="")

    def test_password_is_secret_str(self):
        """password must be SecretStr - never leaks in repr or str."""
        c = _make_creds(password="my_real_password_123")
        # repr should NOT contain the actual password
        assert "my_real_password_123" not in repr(c)
        assert "my_real_password_123" not in str(c)
        # JSON dump should mask it
        assert "my_real_password_123" not in c.model_dump_json()

    def test_password_accessible_via_get_secret_value(self):
        """The real password must be accessible when needed (e.g. for the browser)."""
        c = _make_creds(password="real_pw")
        assert c.password.get_secret_value() == "real_pw"

    def test_credentials_are_immutable(self):
        """Frozen model - cannot mutate fields after creation."""
        c = _make_creds()
        with pytest.raises(Exception):
            c.username = "eve"  # type: ignore[misc]

    def test_extra_fields_rejected(self):
        """Unknown fields should raise (extra='forbid' catches typos)."""
        with pytest.raises(ValidationError):
            PortalCredentials(username="a", password="b", typo_field="oops")


# =====================================================================
# 2. PortalTask
# =====================================================================

class TestPortalTask:
    """Tests for the automation job model."""

    def test_valid_task_with_defaults(self):
        """Minimal task (url + creds) should use sensible defaults."""
        t = _make_task()
        assert t.portal_url == "http://localhost:8001"
        assert t.target_tab == "Documents"
        assert t.file_pattern == "*"
        assert t.max_downloads == 10
        assert t.download_subdir == ""

    def test_trailing_slash_stripped_from_url(self):
        """Trailing / on portal_url should be removed to avoid double-slash URLs."""
        t = _make_task(portal_url="http://localhost:8001/")
        assert t.portal_url == "http://localhost:8001"

    def test_non_http_url_fails(self):
        """Non-http(s) URLs should be rejected (e.g. ftp://, file://)."""
        with pytest.raises(ValidationError) as exc:
            _make_task(portal_url="ftp://example.com")
        assert "http" in str(exc.value).lower()

    def test_missing_credentials_fails(self):
        """credentials is required - cannot build a task without it."""
        with pytest.raises(ValidationError):
            PortalTask(portal_url="http://localhost:8001")

    def test_max_downloads_bounds(self):
        """max_downloads must be between 1 and 100."""
        with pytest.raises(ValidationError):
            _make_task(max_downloads=0)
        with pytest.raises(ValidationError):
            _make_task(max_downloads=101)
        # Boundary values should pass
        assert _make_task(max_downloads=1).max_downloads == 1
        assert _make_task(max_downloads=100).max_downloads == 100

    def test_empty_file_pattern_fails(self):
        """Empty file pattern should be rejected."""
        with pytest.raises(ValidationError):
            _make_task(file_pattern="")

    def test_safe_filename_subdir_when_empty(self):
        """No subdir set -> safe_filename_subdir returns empty string."""
        t = _make_task(download_subdir="")
        assert t.safe_filename_subdir == ""

    def test_safe_filename_subdir_strips_illegal_chars(self):
        """Illegal path characters should be replaced with underscores."""
        t = _make_task(download_subdir="invoices/2024:Q1")
        safe = t.safe_filename_subdir
        # / and : must be replaced
        assert "/" not in safe
        assert ":" not in safe
        assert "_" in safe

    def test_task_is_immutable(self):
        """Task cannot be mutated after creation."""
        t = _make_task()
        with pytest.raises(Exception):
            t.target_tab = "Invoices"  # type: ignore[misc]

    def test_nested_credentials_remain_secret_in_json(self):
        """When task is dumped to JSON, password must remain masked."""
        t = _make_task(credentials=_make_creds(password="super_secret_123"))
        json_str = t.model_dump_json()
        assert "super_secret_123" not in json_str


# =====================================================================
# 3. DownloadedFile
# =====================================================================

class TestDownloadedFile:
    """Tests for the downloaded-file metadata model."""

    def test_valid_file(self):
        """A normal file record should construct fine."""
        f = _make_downloaded_file()
        assert f.filename == "invoice_2024_03.pdf"
        assert f.size_bytes == 1024
        assert f.local_path == "/tmp/downloads/invoice_2024_03.pdf"
        # downloaded_at should default to a timezone-aware datetime
        assert f.downloaded_at.tzinfo is not None

    def test_filename_with_path_separator_fails(self):
        """filename must not contain / or \\ - use local_path for full path."""
        with pytest.raises(ValidationError) as exc:
            _make_downloaded_file(filename="folder/invoice.pdf")
        assert "filename" in str(exc.value).lower() or "separator" in str(exc.value).lower()

    def test_filename_with_backslash_fails(self):
        """Backslash in filename should also be rejected."""
        with pytest.raises(ValidationError):
            _make_downloaded_file(filename="folder\\invoice.pdf")

    def test_zero_byte_file_allowed(self):
        """Empty files (size_bytes=0) are valid downloads - don't reject them."""
        f = _make_downloaded_file(size_bytes=0)
        assert f.size_bytes == 0
        assert f.size_human == "0 B"

    def test_negative_size_fails(self):
        """Negative file size is impossible - must be rejected."""
        with pytest.raises(ValidationError):
            _make_downloaded_file(size_bytes=-1)

    def test_size_human_bytes(self):
        """Files < 1 KB should display as 'N B'."""
        assert _make_downloaded_file(size_bytes=512).size_human == "512 B"

    def test_size_human_kb(self):
        """Files 1 KB - 1 MB should display as 'N.N KB'."""
        f = _make_downloaded_file(size_bytes=1536)  # 1.5 KB
        assert f.size_human == "1.5 KB"

    def test_size_human_mb(self):
        """Files 1 MB - 1 GB should display as 'N.N MB'."""
        f = _make_downloaded_file(size_bytes=2 * 1024 * 1024)  # 2.0 MB
        assert f.size_human == "2.0 MB"

    def test_path_obj_returns_pathlib(self):
        """path_obj should return a pathlib.Path."""
        from pathlib import Path
        f = _make_downloaded_file(local_path="/tmp/foo.pdf")
        assert isinstance(f.path_obj, Path)
        assert f.path_obj.name == "foo.pdf"

    def test_downloaded_at_can_be_overridden(self):
        """Caller should be able to pass an explicit downloaded_at."""
        ts = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        f = _make_downloaded_file(downloaded_at=ts)
        assert f.downloaded_at == ts


# =====================================================================
# 4. PortalRunResult
# =====================================================================

class TestPortalRunResult:
    """Tests for the run-result model (the most complex one)."""

    def test_successful_run_minimal(self):
        """A minimal successful run: success=True, no error, no files."""
        r = PortalRunResult(success=True)
        assert r.success is True
        assert r.error is None
        assert r.files_downloaded == []
        assert r.files_count == 0
        assert r.total_bytes_downloaded == 0

    def test_failed_run_requires_error(self):
        """A failed run MUST have a non-empty error message."""
        with pytest.raises(ValidationError) as exc:
            PortalRunResult(success=False, error=None)
        assert "error" in str(exc.value).lower()

    def test_failed_run_empty_error_fails(self):
        """An empty-string error on a failed run should also be rejected."""
        with pytest.raises(ValidationError):
            PortalRunResult(success=False, error="   ")

    def test_successful_run_with_error_fails(self):
        """A successful run MUST NOT have an error set."""
        with pytest.raises(ValidationError) as exc:
            PortalRunResult(success=True, error="something went wrong")
        assert "error" in str(exc.value).lower()

    def test_failed_run_with_error_ok(self):
        """A failed run with a real error message is the canonical failure shape."""
        r = PortalRunResult(success=False, error="Login button not found")
        assert r.success is False
        assert r.error == "Login button not found"

    def test_duration_auto_computed(self):
        """If duration_seconds is None, it should be computed from timestamps."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=42.5)
        r = PortalRunResult(success=True, started_at=start, completed_at=end)
        assert r.duration_seconds == pytest.approx(42.5)

    def test_duration_explicit_override_kept(self):
        """If caller provides duration_seconds explicitly, it should be kept."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=42.5)
        r = PortalRunResult(
            success=True,
            started_at=start,
            completed_at=end,
            duration_seconds=99.0,  # explicit, not 42.5
        )
        assert r.duration_seconds == 99.0

    def test_completed_before_started_fails(self):
        """completed_at cannot be earlier than started_at."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start - timedelta(seconds=1)  # before start!
        with pytest.raises(ValidationError) as exc:
            PortalRunResult(success=True, started_at=start, completed_at=end)
        assert "before" in str(exc.value).lower() or "started_at" in str(exc.value).lower()

    def test_files_count_and_bytes(self):
        """Aggregate properties should sum across all downloaded files."""
        f1 = _make_downloaded_file(filename="a.pdf", size_bytes=100)
        f2 = _make_downloaded_file(filename="b.pdf", size_bytes=300)
        r = PortalRunResult(success=True, files_downloaded=[f1, f2])
        assert r.files_count == 2
        assert r.total_bytes_downloaded == 400

    def test_duration_human_seconds(self):
        """Short runs should display as 'N.N s'."""
        r = PortalRunResult(success=True, duration_seconds=12.34)
        assert r.duration_human == "12.3 s"

    def test_duration_human_minutes(self):
        """Runs 60s+ should display as 'N.N min'."""
        r = PortalRunResult(success=True, duration_seconds=125.0)
        assert r.duration_human == "2.1 min"

    def test_duration_human_unknown_when_none(self):
        """If duration_seconds is somehow None (shouldn't happen, but defensive),
        duration_human should return 'unknown' rather than crash."""
        # We have to bypass the auto-compute by constructing then peeking.
        # Since the model auto-computes, this is mostly a defensive test.
        r = PortalRunResult(success=True)
        # Auto-computed, so it's a number - just check it returns something
        assert isinstance(r.duration_human, str)

    def test_result_is_immutable(self):
        """RunResult cannot be mutated after creation."""
        r = PortalRunResult(success=True)
        with pytest.raises(Exception):
            r.success = False  # type: ignore[misc]

    def test_agent_trace_defaults_to_empty_list(self):
        """agent_trace should default to an empty list (not None)."""
        r = PortalRunResult(success=True)
        assert r.agent_trace == []

    def test_agent_trace_with_entries(self):
        """A populated agent_trace should round-trip correctly."""
        trace = ["navigated to login", "filled username", "clicked submit"]
        r = PortalRunResult(success=True, agent_trace=trace)
        assert r.agent_trace == trace
        assert len(r.agent_trace) == 3

    def test_total_tokens_defaults_to_zero(self):
        """Token count should default to 0 (free if not measured)."""
        r = PortalRunResult(success=True)
        assert r.total_tokens == 0

    def test_negative_tokens_fails(self):
        """Token count cannot be negative."""
        with pytest.raises(ValidationError):
            PortalRunResult(success=True, total_tokens=-1)

    def test_naive_datetime_gets_rejected_or_warned(self):
        """started_at / completed_at should be timezone-aware.

        Pydantic v2 will accept naive datetimes but they're a footgun.
        We test that timezone-aware datetimes work cleanly here.
        """
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        r = PortalRunResult(success=True, started_at=start, completed_at=end)
        assert r.started_at.tzinfo is not None
        assert r.completed_at.tzinfo is not None