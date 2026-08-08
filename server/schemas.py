"""
HTTP request and response schemas for the Legacy Portal Automator API.

These schemas define the public HTTP contract. They are deliberately
separate from the internal domain models (portal-agent/src/models.py)
so the API can evolve without coupling to internal implementation.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request body for POST /api/runs.

    Contains everything the agent needs: the portal URL, credentials,
    and task parameters (which tab, what file pattern, how many files).
    """

    portal_url: str = Field(
        ...,
        description="Full URL of the legacy portal to automate",
        examples=["http://localhost:8001"],
    )
    username: str = Field(
        ...,
        description="Portal login username",
        examples=["admin"],
    )
    password: str = Field(
        ...,
        description="Portal login password",
        examples=["portal123"],
    )
    target_tab: str = Field(
        "Documents",
        description="Name of the tab to navigate to inside the portal",
        examples=["Invoices"],
    )
    file_pattern: str = Field(
        "*",
        description="Glob pattern to match downloaded files (e.g. *.pdf, invoice_*)",
        examples=["*.pdf"],
    )
    max_downloads: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of files to download in a single run",
    )
    download_subdir: str = Field(
        "",
        description="Optional subdirectory within the download folder",
    )


class ServerInfo(BaseModel):
    """Server metadata returned by GET / and GET /api/info."""

    name: str
    version: str
    docs_url: str
    health_url: str
    configured_model: Optional[str] = None
    headless_mode: Optional[bool] = None
    max_steps: Optional[int] = None