"""Tests for typed diagnostic models."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from models.diagnostic_models import ScanResult


def test_scan_result_formats_success_messages():
    result = ScanResult.from_runner_output("SFC", True, "No Integrity Violations")

    assert result.success is True
    assert result.display_text == "No Integrity Violations"
    assert result.status_color == "green"


def test_scan_result_truncates_long_success_to_ok():
    result = ScanResult.from_runner_output("SFC", True, "x" * 60)

    assert result.display_text == "OK"


def test_scan_result_formats_laptop_skip():
    result = ScanResult.from_runner_output("Battery", False, "Not a Laptop (No Battery)")

    assert result.display_text == "Skipped (Not a Laptop)"
    assert result.status_color == "yellow"


def test_scan_result_formats_exceptions():
    result = ScanResult.from_exception("SFC", RuntimeError("boom"))

    assert result.display_text == "Error: boom"
    assert result.status_color == "red"
    assert result.log_message == "[SFC] EXCEPTION: boom"
