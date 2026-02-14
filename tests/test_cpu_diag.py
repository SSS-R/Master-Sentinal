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

    def test_get_cpu_info_returns_expected_keys(self, mock_wmi):
        diag = CPUDiagnostic()
        info = diag.get_cpu_info()
        assert 'Name' in info
        assert 'Cores' in info
        assert info['Cores'] == 12
        assert info['Threads'] == 20

    def test_get_cpu_usage_returns_float(self, mock_psutil):
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

    def test_get_frequency_returns_str(self, mock_psutil):
        diag = CPUDiagnostic()
        freq = diag.get_frequency()
        assert "MHz" in freq

    def test_get_frequency_returns_na_when_none(self):
        with patch("psutil.cpu_freq", return_value=None):
            diag = CPUDiagnostic()
            assert diag.get_frequency() == "N/A"

    def test_get_cpu_info_error_handling(self):
        with patch("wmi.WMI", side_effect=Exception("WMI unavailable")), \
             patch("pythoncom.CoInitialize"):
            diag = CPUDiagnostic()
            info = diag.get_cpu_info()
            assert 'Error' in info
