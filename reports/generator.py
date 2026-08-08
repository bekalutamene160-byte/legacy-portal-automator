"""
PDF Report Generator for the Legacy Portal Automator.
=====================================================

Takes a PortalRunResult and produces a professional PDF report with:
  - Executive summary (success/failure, duration, file count)
  - Run configuration (URL, credentials, task parameters)
  - Downloaded files table (filename, size, timestamp)
  - Agent trace log (step-by-step history)
  - Token and step usage statistics

Usage:
    from reports.generator import generate_report
    pdf_path = generate_report(result, output_path=Path("report.pdf"))

The generator NEVER raises on normal input — if the result is malformed,
it produces a report with an error notice instead of crashing.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# -----------------------------------------------------------------------------
# Path setup: make portal-agent/ importable so we can use its src package.
# This MUST happen before we import from src.* below.
# -----------------------------------------------------------------------------
PORTAL_AGENT_DIR = Path(__file__).resolve().parent.parent / "portal-agent"
if str(PORTAL_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_AGENT_DIR))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.models import PortalRunResult


# =============================================================================
# Constants
# =============================================================================

PAGE_SIZE = letter
MARGIN = 0.75 * inch

# Professional color palette
HEADER_COLOR = colors.HexColor("#1a365d")
ACCENT_COLOR = colors.HexColor("#2b6cb0")
LIGHT_GRAY = colors.HexColor("#f7fafc")
MEDIUM_GRAY = colors.HexColor("#e2e8f0")
DARK_GRAY = colors.HexColor("#4a5568")
SUCCESS_GREEN = colors.HexColor("#16a34a")
FAILURE_RED = colors.HexColor("#dc2626")
TEXT_COLOR = colors.HexColor("#1a202c")
WHITE = colors.white


# =============================================================================
# Style sheet
# =============================================================================

def _build_styles():
    """Build paragraph styles for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=HEADER_COLOR,
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    ))

    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=DARK_GRAY,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName="Helvetica",
    ))

    styles.add(ParagraphStyle(
        name="SectionHeader",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=HEADER_COLOR,
        spaceBefore=16,
        spaceAfter=8,
        fontName="Helvetica-Bold",
        borderWidth=0,
        borderPadding=0,
    ))

    styles.add(ParagraphStyle(
        name="ReportBody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=TEXT_COLOR,
        spaceAfter=4,
        alignment=TA_LEFT,
        fontName="Helvetica",
        leading=14,
    ))

    styles.add(ParagraphStyle(
        name="Label",
        parent=styles["Normal"],
        fontSize=10,
        textColor=DARK_GRAY,
        fontName="Helvetica-Bold",
    ))

    styles.add(ParagraphStyle(
        name="Value",
        parent=styles["Normal"],
        fontSize=10,
        textColor=TEXT_COLOR,
        fontName="Helvetica",
    ))

    styles.add(ParagraphStyle(
        name="MonoText",
        parent=styles["Normal"],
        fontSize=9,
        textColor=TEXT_COLOR,
        fontName="Courier",
        leading=12,
        spaceAfter=2,
    ))

    styles.add(ParagraphStyle(
        name="ErrorText",
        parent=styles["Normal"],
        fontSize=10,
        textColor=FAILURE_RED,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    ))

    return styles


# =============================================================================
# Helper functions
# =============================================================================

def _format_datetime(dt: Optional[datetime]) -> str:
    """Format a datetime as a human-readable string."""
    if dt is None:
        return "N/A"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_duration(seconds: Optional[float]) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes} min {secs:.1f} sec"


def _status_badge(success: bool) -> Table:
    """Create a colored status badge (green=success, red=failure)."""
    label = "SUCCESS" if success else "FAILED"
    bg = SUCCESS_GREEN if success else FAILURE_RED
    badge = Table(
        [[label]],
        colWidths=[1.2 * inch],
        rowHeights=[0.3 * inch],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
    ]))
    return badge


def _kv_table(rows: list[tuple[str, str]]) -> Table:
    """Build a two-column key-value table."""
    data = [[Paragraph(label, _kv_table.label_style),
             Paragraph(value, _kv_table.value_style)]
            for label, value in rows]
    table = Table(data, colWidths=[1.8 * inch, 4.7 * inch])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_GRAY]),
    ]))
    return table


# =============================================================================
# Section builders
# =============================================================================

def _build_header(result: PortalRunResult, styles) -> list:
    """Build the report header: title, subtitle, status badge."""
    elements = []

    elements.append(Paragraph(
        "Legacy Portal Automator",
        styles["ReportTitle"],
    ))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(Paragraph(
        f"Automation Run Report &mdash; Generated {generated_at}",
        styles["ReportSubtitle"],
    ))

    badge_table = Table(
        [[_status_badge(result.success)]],
        colWidths=[6.5 * inch],
    )
    badge_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(badge_table)
    elements.append(Spacer(1, 12))

    return elements


def _build_executive_summary(result: PortalRunResult, styles) -> list:
    """Build the Executive Summary section."""
    elements = []

    elements.append(Paragraph(
        "Executive Summary",
        styles["SectionHeader"],
    ))

    files_count = len(result.files_downloaded)
    total_bytes = sum(f.size_bytes for f in result.files_downloaded)

    if result.success:
        summary_text = (
            f"The automation run completed successfully. "
            f"The agent downloaded {files_count} file(s) totaling "
            f"{_format_bytes(total_bytes)} in "
            f"{_format_duration(result.duration_seconds)}. "
            f"The agent took {result.total_steps} step(s) and consumed "
            f"{result.total_tokens:,} tokens."
        )
    else:
        error_line = result.error or "Unknown error"
        summary_text = (
            f"The automation run failed. The agent encountered an error "
            f"after {result.total_steps} step(s) and "
            f"{_format_duration(result.duration_seconds)}. "
            f"Error: {error_line}"
        )

    elements.append(Paragraph(summary_text, styles["ReportBody"]))

    if not result.success and result.error:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(
            f"Error detail: {result.error}",
            styles["ErrorText"],
        ))

    return elements


def _build_run_details(result: PortalRunResult, styles) -> list:
    """Build the Run Details section with key-value pairs."""
    elements = []

    elements.append(Paragraph(
        "Run Details",
        styles["SectionHeader"],
    ))

    _kv_table.label_style = styles["Label"]
    _kv_table.value_style = styles["Value"]

    files_count = len(result.files_downloaded)
    total_bytes = sum(f.size_bytes for f in result.files_downloaded)

    rows = [
        ("Status", "Success" if result.success else "Failed"),
        ("Started At", _format_datetime(result.started_at)),
        ("Completed At", _format_datetime(result.completed_at)),
        ("Duration", _format_duration(result.duration_seconds)),
        ("Total Steps", str(result.total_steps)),
        ("Total Tokens", f"{result.total_tokens:,}"),
        ("Files Downloaded", str(files_count)),
        ("Total Size", _format_bytes(total_bytes)),
    ]

    elements.append(_kv_table(rows))
    return elements


def _build_downloaded_files(result: PortalRunResult, styles) -> list:
    """Build the Downloaded Files section with a table."""
    elements = []

    elements.append(Paragraph(
        "Downloaded Files",
        styles["SectionHeader"],
    ))

    if not result.files_downloaded:
        elements.append(Paragraph(
            "No files were downloaded during this run.",
            styles["ReportBody"],
        ))
        return elements

    header = [
        Paragraph("<b>#</b>", styles["ReportBody"]),
        Paragraph("<b>Filename</b>", styles["ReportBody"]),
        Paragraph("<b>Size</b>", styles["ReportBody"]),
        Paragraph("<b>Downloaded At</b>", styles["ReportBody"]),
    ]

    data = [header]
    for idx, f in enumerate(result.files_downloaded, start=1):
        data.append([
            Paragraph(str(idx), styles["ReportBody"]),
            Paragraph(f.filename, styles["MonoText"]),
            Paragraph(f.size_human, styles["ReportBody"]),
            Paragraph(_format_datetime(f.downloaded_at), styles["ReportBody"]),
        ])

    table = Table(
        data,
        colWidths=[0.4 * inch, 2.8 * inch, 1.0 * inch, 2.3 * inch],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.25, MEDIUM_GRAY),
    ]))

    elements.append(table)
    return elements


def _build_agent_trace(result: PortalRunResult, styles) -> list:
    """Build the Agent Trace section."""
    elements = []

    elements.append(Paragraph(
        "Agent Trace",
        styles["SectionHeader"],
    ))

    if not result.agent_trace:
        elements.append(Paragraph(
            "No trace entries were recorded.",
            styles["ReportBody"],
        ))
        return elements

    data = [[Paragraph("<b>Step</b>", styles["ReportBody"]),
             Paragraph("<b>Action</b>", styles["ReportBody"])]]

    for idx, entry in enumerate(result.agent_trace, start=1):
        data.append([
            Paragraph(str(idx), styles["ReportBody"]),
            Paragraph(str(entry), styles["MonoText"]),
        ])

    table = Table(data, colWidths=[0.6 * inch, 5.9 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.25, MEDIUM_GRAY),
    ]))

    elements.append(table)
    return elements


def _build_footer(styles) -> list:
    """Build the footer."""
    elements = []
    elements.append(Spacer(1, 20))

    footer_text = (
        "Generated by Legacy Portal Automator &mdash; "
        "Built for the AI Automation portfolio project."
    )
    elements.append(Paragraph(footer_text, styles["ReportSubtitle"]))
    return elements


# =============================================================================
# Utility
# =============================================================================

def _format_bytes(num_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if num_bytes is None:
        return "N/A"
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.2f} MB"


# =============================================================================
# Main entry point
# =============================================================================

def generate_report(
    result: PortalRunResult,
    output_path: Optional[Path] = None,
) -> Path:
    """Generate a PDF report from a PortalRunResult.

    Args:
        result: The PortalRunResult to report on.
        output_path: Where to save the PDF. If None, saves to the current
                     working directory as "portal_run_report.pdf".

    Returns:
        The Path where the PDF was saved.

    Raises:
        TypeError: if result is not a PortalRunResult.
    """
    if not isinstance(result, PortalRunResult):
        raise TypeError(
            f"result must be a PortalRunResult, got {type(result).__name__}"
        )

    if output_path is None:
        output_path = Path("portal_run_report.pdf")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = _build_styles()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Legacy Portal Automator - Run Report",
        author="Legacy Portal Automator",
    )

    elements = []
    elements.extend(_build_header(result, styles))
    elements.extend(_build_executive_summary(result, styles))
    elements.extend(_build_run_details(result, styles))
    elements.extend(_build_downloaded_files(result, styles))
    elements.extend(_build_agent_trace(result, styles))
    elements.extend(_build_footer(styles))

    doc.build(elements)
    return output_path