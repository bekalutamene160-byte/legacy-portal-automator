"""
Tests for src/config.py

Run: pytest tests/test_config.py -v

NOTE: All tests use _env_file=None to disable .env file loading.
This ensures test isolation - tests don't depend on whether the user
has a real .env file on their machine.
"""

import pytest
from pydantic import ValidationError


# === Test fixtures ===

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clear all relevant env vars before each test.

    This ensures each test starts with a clean slate, regardless of
    what's in the user's real environment or .env file.
    """
    for var in [
        "GROQ_API_KEY", "GROQ_MODEL", "HEADLESS", "USE_VISION",
        "PROXY_URL", "DOWNLOAD_DIR", "MAX_STEPS", "AGENT_TIMEOUT",
        "PORTAL_HOST", "PORTAL_PORT",
    ]:
        monkeypatch.delenv(var, raising=False)


def _make_env(**overrides):
    """Create a clean env dict for testing.

    Returns a dict with all required env vars set to valid test values.
    Override individual values by passing them as kwargs.
    """
    env = {
        "GROQ_API_KEY": "gsk_testkey_1234567890abcdefghijklmnopqrstuvwxyz",
        "GROQ_MODEL": "llama-3.3-70b-versatile",
        "HEADLESS": "true",
        "USE_VISION": "false",
        "PROXY_URL": "",
        "DOWNLOAD_DIR": "./test_downloads",
        "MAX_STEPS": "20",
        "AGENT_TIMEOUT": "120",
        "PORTAL_HOST": "localhost",
        "PORTAL_PORT": "8001",
    }
    env.update({k: str(v) for k, v in overrides.items()})
    return env


def _set_env(monkeypatch, env):
    """Helper: set multiple env vars at once."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)


# === Tests ===

def test_settings_loads_from_env(monkeypatch):
    """Settings should load all fields from environment variables."""
    env = _make_env()
    _set_env(monkeypatch, env)

    from src.config import Settings

    # _env_file=None prevents loading from the user's real .env file
    s = Settings(_env_file=None)
    assert s.groq_api_key.get_secret_value() == env["GROQ_API_KEY"]
    assert s.groq_model == "llama-3.3-70b-versatile"
    assert s.headless is True
    assert s.use_vision is False
    assert s.max_steps == 20
    assert s.agent_timeout == 120
    assert s.portal_port == 8001


def test_settings_missing_api_key_fails(monkeypatch):
    """Missing GROQ_API_KEY should raise a clear ValidationError."""
    # clean_env fixture already deleted GROQ_API_KEY, so we just don't set it
    from src.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    # Pydantic reports the field name (groq_api_key), not the env var name
    assert "groq_api_key" in str(exc_info.value)


def test_settings_placeholder_api_key_fails(monkeypatch):
    """The placeholder value 'your-groq-api-key-here' should be rejected."""
    env = _make_env(GROQ_API_KEY="your-groq-api-key-here")
    _set_env(monkeypatch, env)
    from src.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "gsk_" in str(exc_info.value) or "not set" in str(exc_info.value).lower()


def test_settings_wrong_prefix_fails(monkeypatch):
    """API key must start with 'gsk_'."""
    env = _make_env(GROQ_API_KEY="sk_wrong_prefix_key")
    _set_env(monkeypatch, env)
    from src.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "gsk_" in str(exc_info.value)


def test_settings_invalid_proxy_fails(monkeypatch):
    """Proxy URL must start with http://, https://, or socks5://."""
    env = _make_env(PROXY_URL="not-a-url")
    _set_env(monkeypatch, env)
    from src.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "PROXY_URL" in str(exc_info.value) or "proxy" in str(exc_info.value).lower()


def test_settings_max_steps_bounds(monkeypatch):
    """max_steps must be between 1 and 100."""
    from src.config import Settings

    # Too low
    env = _make_env(MAX_STEPS="0")
    _set_env(monkeypatch, env)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    # Too high
    env = _make_env(MAX_STEPS="999")
    _set_env(monkeypatch, env)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_immutable(monkeypatch):
    """Settings should be frozen - cannot be mutated at runtime."""
    env = _make_env()
    _set_env(monkeypatch, env)
    from src.config import Settings

    s = Settings(_env_file=None)
    with pytest.raises(Exception):
        s.headless = False  # Should raise (frozen=True)


def test_settings_portal_url_property(monkeypatch):
    """portal_url property should return the full URL."""
    env = _make_env(PORTAL_HOST="example.com", PORTAL_PORT="9000")
    _set_env(monkeypatch, env)
    from src.config import Settings

    s = Settings(_env_file=None)
    assert s.portal_url == "http://example.com:9000"


def test_settings_secret_str_not_in_repr(monkeypatch):
    """API key should NOT appear in repr output (SecretStr protection)."""
    env = _make_env()
    _set_env(monkeypatch, env)
    from src.config import Settings

    s = Settings(_env_file=None)
    repr_str = repr(s)
    assert "gsk_testkey" not in repr_str
    assert "**********" in repr_str or "SecretStr" in repr_str