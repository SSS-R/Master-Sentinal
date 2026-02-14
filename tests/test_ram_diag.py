"""Unit tests for RAMDiagnostic."""

from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from modules.ram_diag import RAMDiagnostic


class TestRAMDiagnostic:
    """Tests for RAMDiagnostic methods."""

    def test_get_ram_info_returns_expected_keys(self, mock_psutil):
        diag = RAMDiagnostic()
        info = diag.get_ram_info()
        assert 'Total' in info
        assert 'Available' in info
        assert 'Used' in info
        assert 'Percentage' in info

    def test_get_ram_info_values_are_formatted(self, mock_psutil):
        diag = RAMDiagnostic()
        info = diag.get_ram_info()
        assert 'GB' in info['Total']
        assert info['Percentage'] == 50.0

    def test_get_ram_info_total_calculation(self, mock_psutil):
        diag = RAMDiagnostic()
        info = diag.get_ram_info()
        assert info['Total'] == "16.00 GB"
        assert info['Available'] == "8.00 GB"
        assert info['Used'] == "8.00 GB"
