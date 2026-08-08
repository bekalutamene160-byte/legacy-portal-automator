"""
Tests for the PDF report generator.

These tests generate real PDFs in tmp_path directories and verify:
  - The PDF file is created
  - The file has valid PDF magic bytes
  - The file is non-trivial in size
  - The PDF contains expected text content (via pypdf text extraction)
  - Both successful and failed runs produce valid reports
  - The function handles edge cases gracefully
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# pypdf for text extraction
from pypdf import PdfReader


# =============================================================================
# Tests: basic file generation
# =============================================================================

class TestReportGeneration:
    def test_returns_path_to_generated_pdf(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        result_path = generate_report(successful_result, output)
        assert result_path == output
        assert result_path.exists()

    def test_pdf_has_valid_magic_bytes(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        with open(output, "rb") as f:
            magic = f.read(5)
        assert magic == b"%PDF-"

    def test_pdf_is_non_trivial_size(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        size = output.stat().st_size
        # A report with content should be at least 2KB
        assert size > 2000

    def test_pdf_is_not_huge(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        size = output.stat().st_size
        # Should be under 500KB for a simple report
        assert size < 500_000

    def test_default_output_path_when_none(self, tmp_path, successful_result):
        from generator import generate_report
        # Change to tmp dir so default path lands there
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_path)
            result_path = generate_report(successful_result)
            assert result_path.name == "portal_run_report.pdf"
            assert result_path.exists()
        finally:
            os.chdir(original_cwd)

    def test_creates_parent_directories(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "nested" / "deep" / "report.pdf"
        generate_report(successful_result, output)
        assert output.exists()


# =============================================================================
# Tests: successful run content
# =============================================================================

class TestSuccessfulReportContent:
    def _extract_text(self, pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    def test_contains_title(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "Legacy Portal Automator" in text

    def test_contains_success_status(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "SUCCESS" in text

    def test_contains_executive_summary(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "Executive Summary" in text

    def test_contains_file_count(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "3" in text  # 3 files downloaded

    def test_contains_downloaded_filenames(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "invoice_001.pdf" in text
        assert "invoice_002.pdf" in text
        assert "report_q1_2024.pdf" in text

    def test_contains_token_count(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "4,500" in text

    def test_contains_step_count(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "12" in text

    def test_contains_agent_trace(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "Agent Trace" in text
        assert "navigate_to_portal" in text

    def test_contains_run_details_section(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        text = self._extract_text(output)
        assert "Run Details" in text
        assert "Started At" in text
        assert "Completed At" in text
        assert "Duration" in text


# =============================================================================
# Tests: failed run content
# =============================================================================

class TestFailedReportContent:
    def _extract_text(self, pdf_path: Path) -> str:
        reader = PdfReader(str(pdf_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    def test_contains_failure_status(self, tmp_path, failed_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(failed_result, output)
        text = self._extract_text(output)
        assert "FAILED" in text

    def test_contains_error_message(self, tmp_path, failed_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(failed_result, output)
        text = self._extract_text(output)
        assert "Could not find login form" in text

    def test_contains_no_files_message(self, tmp_path, failed_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(failed_result, output)
        text = self._extract_text(output)
        assert "No files" in text or "0" in text

    def test_contains_agent_trace_on_failure(self, tmp_path, failed_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(failed_result, output)
        text = self._extract_text(output)
        assert "login_failed" in text


# =============================================================================
# Tests: edge cases
# =============================================================================

class TestEdgeCases:
    def test_empty_files_list_success(self, tmp_path, empty_success_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(empty_success_result, output)
        assert output.exists()
        assert output.stat().st_size > 1000

    def test_empty_files_list_contains_message(self, tmp_path, empty_success_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(empty_success_result, output)
        reader = PdfReader(str(output))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        assert "No files were downloaded" in text

    def test_empty_trace_still_generates(self, tmp_path, now):
        from generator import generate_report
        from src.models import PortalRunResult

        result = PortalRunResult(
            success=True,
            files_downloaded=[],
            total_steps=1,
            total_tokens=100,
            error=None,
            agent_trace=[],
            started_at=now,
            completed_at=now,
        )
        output = tmp_path / "report.pdf"
        generate_report(result, output)
        assert output.exists()

    def test_non_portalrunresult_raises_type_error(self, tmp_path):
        from generator import generate_report
        with pytest.raises(TypeError):
            generate_report("not a result", tmp_path / "report.pdf")

    def test_non_portalrunresult_raises_with_message(self, tmp_path):
        from generator import generate_report
        with pytest.raises(TypeError, match="PortalRunResult"):
            generate_report({"success": True}, tmp_path / "report.pdf")


# =============================================================================
# Tests: multiple runs produce valid PDFs
# =============================================================================

class TestMultipleReports:
    def test_generates_multiple_reports_without_conflict(
        self, tmp_path, successful_result, failed_result
    ):
        from generator import generate_report
        output1 = tmp_path / "success_report.pdf"
        output2 = tmp_path / "failure_report.pdf"

        generate_report(successful_result, output1)
        generate_report(failed_result, output2)

        assert output1.exists()
        assert output2.exists()
        assert output1.stat().st_size > 1000
        assert output2.stat().st_size > 1000

    def test_overwriting_existing_file_works(self, tmp_path, successful_result):
        from generator import generate_report
        output = tmp_path / "report.pdf"
        generate_report(successful_result, output)
        first_size = output.stat().st_size

        # Overwrite
        generate_report(successful_result, output)
        second_size = output.stat().st_size

        assert output.exists()
        assert first_size > 0
        assert second_size > 0