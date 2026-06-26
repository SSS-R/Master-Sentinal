"""Unit tests for the post-reboot result reader."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.post_reboot_results import MemoryDiagnosticResult, PostRebootResultReader


class TestInferPassed:
    def test_no_errors_passes(self):
        msg = "The Windows Memory Diagnostic tested the computer's memory and detected no errors."
        assert PostRebootResultReader._infer_passed(msg, 1201) is True

    def test_errors_fail(self):
        msg = "Hardware problems were detected. Errors found in memory."
        assert PostRebootResultReader._infer_passed(msg, 1201) is False

    def test_unknown_message_returns_none(self):
        assert PostRebootResultReader._infer_passed("Test completed.", 1101) is None


class TestHeadline:
    def test_not_found(self):
        result = MemoryDiagnosticResult(found=False)
        assert "No memory test results" in result.headline

    def test_passed(self):
        result = MemoryDiagnosticResult(found=True, passed=True)
        assert "no errors" in result.headline.lower()

    def test_failed(self):
        result = MemoryDiagnosticResult(found=True, passed=False)
        assert "error" in result.headline.lower()

    def test_error_state(self):
        result = MemoryDiagnosticResult(error="event log unavailable")
        assert "event log unavailable" in result.headline
