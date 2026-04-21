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

    @patch("psutil.disk_partitions")
    @patch("psutil.disk_usage")
    def test_get_disk_partitions_returns_typed_models(self, mock_disk_usage, mock_disk_partitions):
        from conftest import FakePartition, FakeUsage
        mock_disk_partitions.return_value = [FakePartition()]
        mock_disk_usage.return_value = FakeUsage()
        diag = DiskDiagnostic()
        disks = diag.get_disk_partitions()
        assert len(disks) == 1
        assert disks[0].device == "C:\\"
        assert disks[0].mountpoint == "C:\\"

    @patch("wmi.WMI")
    @patch("pythoncom.CoInitialize")
    def test_get_smart_drive_statuses_returns_typed_models(self, mock_coinit, mock_wmi):
        from conftest import FakeDrive
        mock_wmi.return_value.Win32_DiskDrive.return_value = [FakeDrive()]
        diag = DiskDiagnostic()
        smart = diag.get_smart_drive_statuses()
        assert len(smart) >= 1
        assert smart[0].key == "\\\\.\\PHYSICALDRIVE0"

    def test_partition_handles_permission_error(self):
        from conftest import FakePartition
        with patch("psutil.disk_partitions", return_value=[FakePartition()]), \
             patch("psutil.disk_usage", side_effect=PermissionError("no access")):
            diag = DiskDiagnostic()
            disks = diag.get_disk_partitions()
            assert disks == []
