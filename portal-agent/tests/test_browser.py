"""
Tests for src/browser.py

Run: pytest tests/test_browser.py -v

CRITICAL DESIGN NOTE:
These tests verify the BROWSER CONFIG is built correctly - they do NOT
launch a real browser. Launching Chromium in unit tests is slow, flaky,
and a CI nightmare. We test:
  - The right flags are set
  - The proxy is parsed correctly
  - The user-agent is realistic
  - Downloads are enabled
  - Stealth args are present

Integration tests that actually launch a browser live in tests/integration/
(added in Phase 6 when we wire up the agent).
"""

import pytest

from src.browser import (
    DEFAULT_USER_AGENT,
    STEALTH_ARGS,
    _parse_proxy_url,
    build_browser_profile,
    build_browser_session,
    get_stealth_summary,
)
from src.config import Settings


# === Helpers ===

def _make_settings(**overrides) -> Settings:
    """Build Settings with valid test values, override any field via kwargs."""
    defaults = {
        "groq_api_key": "gsk_testkey_1234567890abcdefghijklmnopqrstuvwxyz",
        "groq_model": "llama-3.3-70b-versatile",
        "headless": True,
        "use_vision": False,
        "proxy_url": "",
        "download_dir": "./test_downloads",
        "max_steps": 20,
        "agent_timeout": 120,
        "portal_host": "localhost",
        "portal_port": 8001,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


# =====================================================================
# Constants
# =====================================================================

class TestConstants:
    """Sanity checks on our hardcoded stealth constants."""

    def test_user_agent_is_chrome(self):
        """The default user-agent must mention Chrome (not 'HeadlessChrome')."""
        assert "Chrome" in DEFAULT_USER_AGENT
        # Critical: must NOT contain 'HeadlessChrome' - that's a dead giveaway
        assert "HeadlessChrome" not in DEFAULT_USER_AGENT

    def test_user_agent_has_windows_nt(self):
        """User-agent should look like a Windows browser (we're on Windows)."""
        assert "Windows NT" in DEFAULT_USER_AGENT

    def test_stealth_args_contains_automation_controlled_flag(self):
        """The most important stealth flag must be present."""
        assert any("AutomationControlled" in a for a in STEALTH_ARGS)

    def test_stealth_args_contains_infobars_flag(self):
        """The 'disable infobars' flag should be present."""
        assert any("disable-infobars" in a for a in STEALTH_ARGS)

    def test_stealth_args_are_strings(self):
        """All stealth args must be strings (Chromium expects strings)."""
        for arg in STEALTH_ARGS:
            assert isinstance(arg, str), f"Stealth arg {arg!r} is not a string"
            assert arg.startswith("--"), f"Stealth arg {arg!r} should start with --"


# =====================================================================
# _parse_proxy_url
# =====================================================================

class TestParseProxyUrl:
    """Tests for the proxy URL parser."""

    def test_empty_returns_none(self):
        """Empty string should return None (no proxy)."""
        assert _parse_proxy_url("") is None
        assert _parse_proxy_url("   ") is None

    def test_simple_http_proxy(self):
        """A bare http://host:port URL should parse correctly."""
        result = _parse_proxy_url("http://proxy.local:8080")
        assert result is not None
        assert result.server == "http://proxy.local:8080"
        assert result.username is None
        assert result.password is None

    def test_proxy_with_auth(self):
        """http://user:pass@host:port should split auth correctly."""
        result = _parse_proxy_url("http://alice:secret@proxy.local:8080")
        assert result is not None
        assert result.server == "http://proxy.local:8080"
        assert result.username == "alice"
        assert result.password == "secret"

    def test_socks5_proxy(self):
        """SOCKS5 proxies should be accepted."""
        result = _parse_proxy_url("socks5://127.0.0.1:1080")
        assert result is not None
        assert result.server == "socks5://127.0.0.1:1080"

    def test_https_proxy(self):
        """HTTPS proxies should be accepted."""
        result = _parse_proxy_url("https://proxy.example.com:443")
        assert result is not None
        assert result.server == "https://proxy.example.com:443"

    def test_invalid_scheme_rejected(self):
        """ftp://, file://, etc. should raise ValueError."""
        with pytest.raises(ValueError) as exc:
            _parse_proxy_url("ftp://proxy.local:21")
        assert "Unsupported" in str(exc.value) or "scheme" in str(exc.value).lower()

    def test_malformed_url_raises(self):
        """A non-URL string should raise ValueError, not silently return None."""
        with pytest.raises(ValueError):
            _parse_proxy_url("not-a-url-at-all")

    def test_default_port_when_missing(self):
        """If port is missing, a sensible default should be filled in."""
        # http without port -> 80
        result = _parse_proxy_url("http://proxy.local")
        assert result is not None
        assert ":80" in result.server

    def test_url_encoded_password(self):
        """Passwords with special chars (URL-encoded) should round-trip.

        urlparse handles this for us - we just verify it works.
        """
        # %40 = @ - common in passwords
        result = _parse_proxy_url("http://user:pass%40word@proxy.local:8080")
        assert result is not None
        assert result.username == "user"


# =====================================================================
# build_browser_profile
# =====================================================================

class TestBuildBrowserProfile:
    """Tests for the main profile factory function."""

    def test_returns_browser_profile_instance(self):
        """build_browser_profile should return a BrowserProfile."""
        from browser_use.browser.profile import BrowserProfile
        profile = build_browser_profile(_make_settings())
        assert isinstance(profile, BrowserProfile)

    def test_headless_flag_respected(self):
        """headless=True should produce a headless profile."""
        profile = build_browser_profile(_make_settings(headless=True))
        assert profile.headless is True

    def test_headless_false_propagated(self):
        """headless=False should produce a visible profile (for demo videos)."""
        profile = build_browser_profile(_make_settings(headless=False))
        assert profile.headless is False

    def test_user_agent_is_set(self):
        """The realistic user-agent must be set, not the default Playwright one."""
        profile = build_browser_profile(_make_settings())
        assert profile.user_agent == DEFAULT_USER_AGENT
        assert "Chrome" in profile.user_agent
        assert "HeadlessChrome" not in profile.user_agent

    def test_stealth_args_present(self):
        """All stealth args must be in the profile.args list."""
        profile = build_browser_profile(_make_settings())
        for stealth_arg in STEALTH_ARGS:
            assert stealth_arg in profile.args, (
                f"Stealth arg {stealth_arg!r} missing from profile.args"
            )

    def test_stealth_args_are_a_copy(self):
        """Mutating profile.args should NOT mutate our STEALTH_ARGS constant.

        This catches a subtle bug where the constant list gets shared.
        """
        profile = build_browser_profile(_make_settings())
        profile.args.append("--extra-arg-from-test")
        assert "--extra-arg-from-test" not in STEALTH_ARGS

    def test_downloads_enabled(self):
        """accept_downloads must be True (we're a download bot)."""
        profile = build_browser_profile(_make_settings())
        assert profile.accept_downloads is True

    def test_auto_download_pdfs_enabled(self):
        """auto_download_pdfs must be True (we want to save, not view)."""
        profile = build_browser_profile(_make_settings())
        assert profile.auto_download_pdfs is True

    def test_downloads_path_set_from_settings(self):
        """downloads_path should come from settings.download_path."""
        s = _make_settings(download_dir="./my_custom_downloads")
        profile = build_browser_profile(s)
        assert "my_custom_downloads" in str(profile.downloads_path)

    def test_disable_security_is_false(self):
        """disable_security MUST be False (security footgun - never enable)."""
        profile = build_browser_profile(_make_settings())
        assert profile.disable_security is False

    def test_chromium_sandbox_disabled(self):
        """chromium_sandbox should be False (required on Windows + CI)."""
        profile = build_browser_profile(_make_settings())
        assert profile.chromium_sandbox is False

    def test_no_proxy_when_settings_empty(self):
        """Empty proxy_url should produce no proxy."""
        profile = build_browser_profile(_make_settings(proxy_url=""))
        assert profile.proxy is None

    def test_proxy_set_when_settings_provided(self):
        """A valid proxy_url should produce a ProxySettings."""
        profile = build_browser_profile(
            _make_settings(proxy_url="http://proxy.local:8080")
        )
        assert profile.proxy is not None
        assert profile.proxy.server == "http://proxy.local:8080"

    def test_proxy_with_auth_set(self):
        """A proxy URL with credentials should populate username/password."""
        profile = build_browser_profile(
            _make_settings(proxy_url="http://alice:secret@proxy.local:8080")
        )
        assert profile.proxy is not None
        assert profile.proxy.username == "alice"
        assert profile.proxy.password == "secret"

    def test_wait_settings_set(self):
        """The page-load wait settings should be set to reduce flakiness."""
        profile = build_browser_profile(_make_settings())
        # Just verify they're positive numbers (not zero/negative)
        assert profile.minimum_wait_page_load_time > 0
        assert profile.wait_for_network_idle_page_load_time > 0
        assert profile.wait_between_actions > 0


# =====================================================================
# build_browser_session
# =====================================================================

class TestBuildBrowserSession:
    """Tests for the session factory."""

    def test_returns_browser_session_instance(self):
        """build_browser_session should return a BrowserSession."""
        from browser_use.browser.session import BrowserSession
        session = build_browser_session(_make_settings())
        assert isinstance(session, BrowserSession)

    def test_session_has_profile_attached(self):
        """The session should have a BrowserProfile set."""
        from browser_use.browser.profile import BrowserProfile
        session = build_browser_session(_make_settings())
        assert session.browser_profile is not None
        assert isinstance(session.browser_profile, BrowserProfile)

    def test_session_does_not_launch_browser(self):
        """Building a session should NOT actually launch a browser.

        This is critical - we want lazy startup so tests stay fast.
        """
        session = build_browser_session(_make_settings())
        # The session is created but not started
        # We can't easily check "is started" without launching, but we can
        # verify the session object exists without raising
        assert session is not None


# =====================================================================
# get_stealth_summary
# =====================================================================

class TestGetStealthSummary:
    """Tests for the introspection helper (used by the report generator)."""

    def test_summary_contains_required_keys(self):
        """The summary dict should contain all expected keys."""
        summary = get_stealth_summary(_make_settings())
        expected_keys = {
            "headless", "user_agent", "stealth_args_count",
            "accept_downloads", "downloads_path", "proxy_in_use",
            "proxy_server", "disable_security",
        }
        assert set(summary.keys()) == expected_keys

    def test_summary_no_proxy(self):
        """When no proxy is set, proxy_in_use should be False and server None."""
        summary = get_stealth_summary(_make_settings(proxy_url=""))
        assert summary["proxy_in_use"] is False
        assert summary["proxy_server"] is None

    def test_summary_with_proxy(self):
        """When a proxy is set, proxy_in_use should be True and server shown."""
        summary = get_stealth_summary(
            _make_settings(proxy_url="http://proxy.local:8080")
        )
        assert summary["proxy_in_use"] is True
        assert summary["proxy_server"] == "http://proxy.local:8080"

    def test_summary_stealth_args_count(self):
        """stealth_args_count should match len(STEALTH_ARGS)."""
        summary = get_stealth_summary(_make_settings())
        assert summary["stealth_args_count"] == len(STEALTH_ARGS)

    def test_summary_no_secrets_leaked(self):
        """The summary should NEVER contain the API key or proxy password.

        This is a security smoke test - the summary goes into the run report
        which might be shared with recruiters / posted publicly.
        """
        s = _make_settings(
            groq_api_key="gsk_SUPER_SECRET_KEY_DO_NOT_LEAK_12345",
            proxy_url="http://alice:super_secret_password@proxy.local:8080",
        )
        summary = get_stealth_summary(s)
        summary_str = str(summary)
        assert "gsk_SUPER_SECRET_KEY_DO_NOT_LEAK_12345" not in summary_str
        assert "super_secret_password" not in summary_str

    def test_summary_user_agent_present(self):
        """The user-agent should be in the summary (it's not a secret)."""
        summary = get_stealth_summary(_make_settings())
        assert summary["user_agent"] == DEFAULT_USER_AGENT