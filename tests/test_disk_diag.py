"""Unit tests for DiskDiagnostic."""

from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from modules.disk_diag import DiskDiagnostic


class TestDiskDiagnostic:
    """Tests for DiskDiagnostic methods."""

    def test_get_disk_partitions_returns_list(self, mock_psutil):
        diag = DiskDiagnostic()
        disks = diag.get_disk_partitions_and_usage()
        assert isinstance(disks, list)
        assert len(disks) == 1

    def test_partition_data_has_expected_keys(self, mock_psutil):
        diag = DiskDiagnostic()
        disks = diag.get_disk_partitions_and_usage()
        d = disks[0]
        assert 'Device' in d
        assert 'Mountpoint' in d
        assert 'Total' in d
        assert 'Percent' in d

    def test_partition_total_formatted(self, mock_psutil):
        diag = DiskDiagnostic()
        disks = diag.get_disk_partitions_and_usage()
        assert "GB" in disks[0]['Total']

    def test_get_smart_status_returns_dict(self, mock_wmi):
        diag = DiskDiagnostic()
        smart = diag.get_smart_status()
        assert isinstance(smart, dict)
        assert len(smart) >= 1

    def test_get_smart_status_error_handling(self):
        with patch("wmi.WMI", side_effect=Exception("WMI fail")), \
             patch("pythoncom.CoInitialize"):
            diag = DiskDiagnostic()
            smart = diag.get_smart_status()
            assert 'Error' in smart

    def test_partition_handles_permission_error(self):
        from conftest import FakePartition
        with patch("psutil.disk_partitions", return_value=[FakePartition()]), \
             patch("psutil.disk_usage", side_effect=PermissionError("no access")):
            diag = DiskDiagnostic()
            disks = diag.get_disk_partitions_and_usage()
            assert disks == []
