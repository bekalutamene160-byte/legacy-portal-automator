"""
Legacy Portal (Demo Target)
============================

A deliberately OLD-LOOKING web portal that our agent learns to automate.

It looks like the kind of internal portal you'd find at a bank, hospital,
or government office circa 2010:
- Server-rendered HTML (Jinja2 templates, no React/Vue)
- Form-based login (no SPA)
- Tabbed interface with inline styling
- File download links (no JS download managers)
- Session cookie auth (no JWT, no OAuth)

This is INTENTIONAL - the whole point of the project is to show the agent
can handle legacy UIs that modern automation tools struggle with.

Run it:
    uvicorn app:app --reload --port 8001

Then open http://localhost:8001 in your browser.
Default credentials: admin / portal123
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    FileResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


# =====================================================================
# Constants
# =====================================================================

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
PDFS_DIR = BASE_DIR / "pdfs"

# Default credentials (these are DEMO creds - intentionally simple)
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "portal123"

# Session cookie secret - in production this would be a real secret.
# For the demo we generate a random one each startup so restarted servers
# invalidate old sessions (which is the safe default).
SESSION_SECRET = os.environ.get("PORTAL_SESSION_SECRET") or secrets.token_hex(32)

# Tabs that exist in the portal. Each tab has its own page.
# Files are organized into these tabs.
TABS = {
    "Invoices": ["invoice_001.pdf", "invoice_002.pdf", "invoice_003.pdf"],
    "Notices": ["notice_welcome.pdf", "notice_policy_update.pdf"],
    "Reports": ["report_q1_2024.pdf", "report_q2_2024.pdf"],
}


# =====================================================================
# Lifespan: seed default PDF files on startup
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Generate placeholder PDFs on first run so the portal has files to serve.

    Each PDF is a tiny valid PDF with just a text title. They exist purely
    so the agent has something to download - they don't contain real data.
    The seeding is idempotent - existing files are never overwritten.
    """
    from seed_pdfs import seed_default_pdfs
    seed_default_pdfs(PDFS_DIR, TABS)
    yield
    # (cleanup would go here if we had any)


# =====================================================================
# FastAPI app setup
# =====================================================================

app = FastAPI(
    title="Legacy Portal (Demo Target)",
    description=(
        "A deliberately old-fashioned web portal that the Legacy Portal "
        "Automator agent learns to navigate. Not for production use."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Session middleware - keeps users logged in via a signed cookie
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="portal_session",
    max_age=3600,  # 1 hour
    same_site="lax",
    https_only=False,  # we run on http://localhost
)

# Static files (CSS, JS, images) - mounted at /static
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Make sure the PDFs directory exists
PDFS_DIR.mkdir(exist_ok=True)


# =====================================================================
# Auth helpers
# =====================================================================

def _is_logged_in(request: Request) -> bool:
    """Check if the current request has a valid session."""
    return request.session.get("logged_in") is True


def _require_login(request: Request) -> None:
    """Raise a redirect to /login if the user isn't logged in.

    Used as a guard at the top of every protected route.
    """
    if not _is_logged_in(request):
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )


# =====================================================================
# Routes: public
# =====================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Root - redirects to /login or /dashboard depending on session."""
    if _is_logged_in(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: Optional[str] = None):
    """Show the login form."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error},
    )


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Process the login form submission.

    On success: set session cookie and redirect to /dashboard.
    On failure: re-render login page with an error message.
    """
    if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
        request.session["logged_in"] = True
        request.session["username"] = username
        return RedirectResponse(url="/dashboard", status_code=303)

    # Failed login - re-render with error
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "Invalid username or password. Please try again.",
            "username": username,  # keep what they typed (except password)
        },
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    """Clear the session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# =====================================================================
# Routes: protected (require login)
# =====================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard - shows tabs and a welcome message."""
    _require_login(request)

    # Build the list of tabs with file counts for the UI
    tabs_with_counts = [
        {"name": tab_name, "file_count": len(files)}
        for tab_name, files in TABS.items()
    ]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "username": request.session.get("username", "user"),
            "tabs": tabs_with_counts,
        },
    )


@app.get("/tab/{tab_name}", response_class=HTMLResponse)
async def view_tab(request: Request, tab_name: str):
    """Show the contents of a specific tab (list of downloadable files)."""
    _require_login(request)

    if tab_name not in TABS:
        raise HTTPException(status_code=404, detail=f"Tab '{tab_name}' not found")

    files = TABS[tab_name]
    # Check which files actually exist on disk (some may have been deleted)
    available_files = []
    for fname in files:
        fpath = PDFS_DIR / fname
        available_files.append({
            "name": fname,
            "exists": fpath.exists(),
            "size_bytes": fpath.stat().st_size if fpath.exists() else 0,
        })

    return templates.TemplateResponse(
        request,
        "tab.html",
        {
            "username": request.session.get("username", "user"),
            "tab_name": tab_name,
            "files": available_files,
            "all_tabs": list(TABS.keys()),
        },
    )


@app.get("/download/{filename}")
async def download_file(request: Request, filename: str):
    """Serve a file for download.

    The Content-Disposition: attachment header forces the browser to save
    the file rather than display it inline (critical for the agent - it
    needs files to land in the downloads folder, not open in a tab).
    """
    _require_login(request)

    # CRITICAL: sanitize filename to prevent path traversal
    # Only allow alphanumeric, underscore, hyphen, dot
    if not _is_safe_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    fpath = PDFS_DIR / filename
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    return FileResponse(
        path=str(fpath),
        filename=filename,
        media_type="application/pdf",
        # The attachment disposition is what makes the browser DOWNLOAD
        # rather than display.
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _is_safe_filename(filename: str) -> bool:
    """Return True if the filename is safe to serve (no path traversal).

    Allows: letters, digits, underscore, hyphen, dot.
    Rejects: slashes, backslashes, .., empty, leading dot.
    """
    if not filename or len(filename) > 255:
        return False
    if filename.startswith("."):
        return False
    if ".." in filename:
        return False
    # Allow only safe characters
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    return all(c in allowed for c in filename)


# =====================================================================
# Health check (for the agent / tests)
# =====================================================================

@app.get("/health")
async def health():
    """Public health endpoint - used by the agent to verify the portal is up."""
    return {"status": "ok", "service": "legacy-portal"}


@app.get("/api/info")
async def info(request: Request):
    """Public info endpoint - returns portal metadata.

    Used by the automator's tests to confirm the portal is the right one.
    """
    return {
        "name": "Legacy Portal (Demo)",
        "version": "0.1.0",
        "tabs": list(TABS.keys()),
        "total_files": sum(len(files) for files in TABS.values()),
        "login_required": True,
    }


# =====================================================================
# Main entry point
# =====================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="localhost",
        port=8001,
        reload=True,
        log_level="info",
    )