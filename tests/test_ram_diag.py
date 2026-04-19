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

    @patch("psutil.virtual_memory")
    def test_get_ram_stats_returns_typed_model(self, mock_vm):
        from conftest import FakeMemory
        mock_vm.return_value = FakeMemory()
        diag = RAMDiagnostic()
        stats = diag.get_ram_stats()
        assert stats.total_gb_text == "16.00 GB"
        assert stats.available_gb_text == "8.00 GB"
        assert stats.used_gb_text == "8.00 GB"
        assert stats.percent_used == 50.0

