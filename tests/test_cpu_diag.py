"""Unit tests for CPUDiagnostic."""

from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from modules.cpu_diag import CPUDiagnostic


class TestCPUDiagnostic:
    """Tests for CPUDiagnostic methods."""

    @patch("wmi.WMI")
    @patch("pythoncom.CoInitialize")
    def test_get_cpu_details_returns_typed_model(self, mock_coinit, mock_wmi):
        from conftest import FakeCPU
        mock_wmi.return_value.Win32_Processor.return_value = [FakeCPU()]
        diag = CPUDiagnostic()
        info = diag.get_cpu_details()
        assert info.name == "Intel Core i7-12700K"
        assert info.cores == 12
        assert info.threads == 20
        assert info.max_clock_speed_text == "3600 MHz"

    @patch("psutil.cpu_percent", return_value=42.0)
    def test_get_cpu_usage_returns_float(self, mock_cpu_percent):
        diag = CPUDiagnostic()
        usage = diag.get_cpu_usage()
        assert isinstance(usage, float)
        assert usage == 42.0

    def test_get_per_core_usage_returns_list(self):
        with patch("psutil.cpu_percent", return_value=[10.0, 20.0, 30.0]):
            diag = CPUDiagnostic()
            cores = diag.get_per_core_usage()
            assert isinstance(cores, list)
            assert len(cores) == 3

    @patch("psutil.cpu_freq")
    def test_get_frequency_returns_str(self, mock_cpu_freq):
        mock_cpu_freq.return_value.current = 3600.0
        diag = CPUDiagnostic()
        freq = diag.get_frequency()
        assert "MHz" in freq

    def test_get_frequency_returns_na_when_none(self):
        with patch("psutil.cpu_freq", return_value=None):
            diag = CPUDiagnostic()
            assert diag.get_frequency() == "N/A"

