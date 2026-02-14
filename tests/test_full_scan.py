"""Unit tests for FullScanDiagnostic."""

from __future__ import annotations

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from modules.full_scan import FullScanDiagnostic


class TestParseFriendlyError:
    """Tests for _parse_friendly_error() — the error-translation engine."""

    def setup_method(self):
        self.diag = FullScanDiagnostic()

    def test_source_files_missing(self):
        assert "Source Files Missing" in self.diag._parse_friendly_error("Error 0x800f081f found")

    def test_cannot_download(self):
        assert "Cannot Download" in self.diag._parse_friendly_error("0x800f0906")

    def test_access_denied(self):
        assert "Access Denied" in self.diag._parse_friendly_error("Access is denied")

    def test_access_denied_error5(self):
        assert "Access Denied" in self.diag._parse_friendly_error("Error: 5 something")

    def test_invalid_parameter(self):
        assert "Invalid Parameter" in self.diag._parse_friendly_error("Error: 87")

    def test_pending_reboot(self):
        assert "PENDING REBOOT" in self.diag._parse_friendly_error("Error: 3017")

    def test_no_battery(self):
        assert "Not a Laptop" in self.diag._parse_friendly_error("Error 0x10d2")

    def test_no_battery_alt(self):
        assert "Not a Laptop" in self.diag._parse_friendly_error("unable to perform operation library")

    def test_fallback_error_line(self):
        result = self.diag._parse_friendly_error("Line 1\nError: custom thing\nLine 3")
        assert "custom thing" in result

    def test_fallback_last_line(self):
        result = self.diag._parse_friendly_error("Some output\nLast meaningful line")
        assert "Last meaningful line" in result

    def test_empty_output(self):
        assert self.diag._parse_friendly_error("") == "Failed: Unknown Error"


class TestFullScanChecks:
    """Tests for individual scan check methods with mocked subprocess."""

    def setup_method(self):
        self.diag = FullScanDiagnostic()

    @patch.object(FullScanDiagnostic, 'is_admin', return_value=False)
    def test_sfc_requires_admin(self, _):
        ok, msg = self.diag.run_sfc()
        assert not ok
        assert "Administrator" in msg

    @patch.object(FullScanDiagnostic, 'is_admin', return_value=True)
    @patch("subprocess.run")
    def test_sfc_no_violations(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Windows Resource Protection did not find any integrity violations",
            stderr="",
        )
        ok, msg = self.diag.run_sfc()
        assert ok
        assert "No Integrity Violations" in msg

    @patch.object(FullScanDiagnostic, 'is_admin', return_value=True)
    @patch("subprocess.run")
    def test_dism_success(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        ok, msg = self.diag.run_dism()
        assert ok

    def test_get_full_scan_list_returns_tuples(self):
        items = self.diag.get_full_scan_list()
        assert len(items) == 8
        for name, func, reboot in items:
            assert isinstance(name, str)
            assert callable(func)
            assert isinstance(reboot, bool)
