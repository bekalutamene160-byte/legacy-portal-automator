"""
Legacy Portal Automator - Browser Factory
==========================================

Builds a configured browser-use BrowserProfile + BrowserSession from our
Settings object. Adds stealth tweaks so the agent looks like a real user
to legacy portals that try to detect automation.

Why a factory instead of using BrowserProfile directly?
- Centralizes stealth config in ONE place (so we never forget a flag)
- Pulls values from our typed Settings (no scattered env vars)
- Easy to mock in tests (we test the *config*, not the browser)
- Single source of truth for the user-agent string

Stealth techniques applied here:
1. Realistic Chrome user-agent (not Playwright's default, which screams "bot")
2. --disable-blink-features=AutomationControlled removes navigator.webdriver
3. --disable-features=IsolateOrigins,site-per-process (some portals check this)
4. --disable-infobars hides the "Chrome is being controlled by automated
   software" banner
5. disable_security=False is the SAFE default (we don't disable same-origin
   policy - that would let any page steal cookies)
6. accept_downloads=True so PDFs actually save
7. auto_download_pdfs=True so the browser doesn't open PDFs in the viewer

Usage:
    from src.browser import build_browser_session
    from src.config import settings

    async with build_browser_session(settings) as session:
        agent = Agent(task="...", llm=..., browser=session)
        await agent.run()

Or for tests / when you just need the config:
    from src.browser import build_browser_profile
    profile = build_browser_profile(settings)
    # inspect profile.headless, profile.user_agent, etc.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from urllib.parse import urlparse

from browser_use.browser.profile import BrowserProfile, ProxySettings
from browser_use.browser.session import BrowserSession

from src.config import Settings


# === Constants ===

# A realistic, current Chrome user-agent. Update annually.
# This is Chrome 124 on Windows 10/11 - the most common UA in 2024-2025.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Chromium args that make us look less like a bot.
# These are the most impactful, well-documented stealth args.
STEALTH_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-infobars",
    "--disable-dev-shm-usage",  # avoids /dev/shm issues on Linux containers
    "--no-first-run",
    "--no-default-browser-check",
]


# === Public API ===

def _parse_proxy_url(url: str) -> Optional[ProxySettings]:
    """Convert a proxy URL string into a browser-use ProxySettings object.

    Accepts formats:
        http://host:port
        http://user:pass@host:port
        https://host:port
        socks5://host:port

    Returns None if the URL is empty / invalid.
    """
    if not url or not url.strip():
        return None

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(
            f"Invalid proxy URL '{url}'. "
            "Expected format: http://user:pass@host:port or socks5://host:port"
        )

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https", "socks5"):
        raise ValueError(
            f"Unsupported proxy scheme '{scheme}'. Use http://, https://, or socks5://"
        )

    if not parsed.port:
        # Default ports for common schemes
        default_ports = {"http": 80, "https": 443, "socks5": 1080}
        port = default_ports[scheme]
    else:
        port = parsed.port

    # Build the server URL in the format Playwright expects
    server = f"{scheme}://{parsed.hostname}:{port}"

    return ProxySettings(
        server=server,
        username=parsed.username or None,
        password=parsed.password or None,
    )


def build_browser_profile(settings: Settings) -> BrowserProfile:
    """Build a stealth-configured BrowserProfile from Settings.

    This function is PURE - it doesn't launch anything, just constructs
    the config object. That makes it easy to test without a real browser.

    Args:
        settings: Our typed Settings object (from src.config)

    Returns:
        BrowserProfile ready to pass to BrowserSession(browser_profile=...)

    Raises:
        ValueError: if proxy_url is malformed (shouldn't happen - Settings
            validates it first, but we double-check defensively)
    """
    proxy = _parse_proxy_url(settings.proxy_url)

    return BrowserProfile(
        # === Core ===
        headless=settings.headless,
        user_agent=DEFAULT_USER_AGENT,
        args=list(STEALTH_ARGS),  # copy so caller can't mutate our constant

        # === Downloads (critical for our use case) ===
        accept_downloads=True,
        downloads_path=str(settings.download_path),
        auto_download_pdfs=True,

        # === Security (safe defaults) ===
        # We do NOT set disable_security=True - that disables same-origin
        # policy which would let any page steal cookies. Real portals hate it
        # and it's a security risk. Keep it False.
        disable_security=False,
        chromium_sandbox=False,  # required on Windows and most CI envs

        # === Proxy (optional) ===
        proxy=proxy,

        # === Performance ===
        # Give the page a moment to settle before we act - reduces flakiness
        minimum_wait_page_load_time=0.5,
        wait_for_network_idle_page_load_time=1.0,
        wait_between_actions=0.2,
    )


def build_browser_session(settings: Settings) -> BrowserSession:
    """Build a BrowserSession from Settings (does not launch the browser yet).

    The session lazily launches the browser on first .start() call.
    Use this when you want to manage start/stop yourself (e.g. across
    multiple agent runs).

    For most cases, prefer `browser_session()` (the async context manager)
    which handles cleanup automatically.
    """
    profile = build_browser_profile(settings)
    return BrowserSession(browser_profile=profile)


@asynccontextmanager
async def browser_session(settings: Settings) -> AsyncIterator[BrowserSession]:
    """Async context manager that yields a started BrowserSession and
    guarantees cleanup on exit.

    Usage:
        async with browser_session(settings) as session:
            agent = Agent(task="...", llm=llm, browser=session)
            await agent.run()
        # browser is closed automatically here, even on exceptions

    This is the RECOMMENDED way to use the browser - it guarantees that
    the Chromium process is killed even if the agent crashes, which
    prevents zombie processes eating memory on your laptop.
    """
    session = build_browser_session(settings)
    try:
        await session.start()
        yield session
    finally:
        await session.close()


# === Introspection helpers (used by tests and the report generator) ===

def get_stealth_summary(settings: Settings) -> dict:
    """Return a human-readable summary of the stealth config for logging.

    Used in the run report so you can see exactly what browser config
    was used for each run. No secrets included.
    """
    profile = build_browser_profile(settings)
    return {
        "headless": profile.headless,
        "user_agent": profile.user_agent,
        "stealth_args_count": len(profile.args or []),
        "accept_downloads": profile.accept_downloads,
        "downloads_path": str(profile.downloads_path),
        "proxy_in_use": profile.proxy is not None,
        "proxy_server": profile.proxy.server if profile.proxy else None,
        "disable_security": profile.disable_security,
    }