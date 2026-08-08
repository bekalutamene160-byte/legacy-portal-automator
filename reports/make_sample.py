"""Generate a sample PDF report for visual verification."""

import sys
from datetime import datetime, timezone
from pathlib import Path

PORTAL_AGENT_DIR = Path(__file__).resolve().parent.parent / "portal-agent"
if str(PORTAL_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_AGENT_DIR))

from src.models import DownloadedFile, PortalRunResult
from generator import generate_report

now = datetime.now(timezone.utc)

result = PortalRunResult(
    success=True,
    files_downloaded=[
        DownloadedFile(
            filename="invoice_001.pdf",
            size_bytes=1936,
            downloaded_at=now,
            local_path="/tmp/downloads/invoice_001.pdf",
        ),
        DownloadedFile(
            filename="invoice_002.pdf",
            size_bytes=1940,
            downloaded_at=now,
            local_path="/tmp/downloads/invoice_002.pdf",
        ),
    ],
    total_steps=12,
    total_tokens=4500,
    error=None,
    agent_trace=[
        "start",
        "navigate_to_portal",
        "login",
        "navigate_to_tab",
        "download_invoice_001.pdf",
        "download_invoice_002.pdf",
        "verify_downloads",
        "done",
    ],
    started_at=now,
    completed_at=now,
)

output = Path(__file__).parent / "sample_report.pdf"
generate_report(result, output)
print(f"Sample report saved to: {output}")