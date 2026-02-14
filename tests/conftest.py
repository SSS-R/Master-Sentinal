"""Shared pytest fixtures for Master Sentinal unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# psutil mocks
# ---------------------------------------------------------------------------

class FakeVirtualMemory:
    """Mimics ``psutil.virtual_memory()`` return value."""
    total = 16 * (1024 ** 3)       # 16 GB
    available = 8 * (1024 ** 3)    # 8 GB
    used = 8 * (1024 ** 3)         # 8 GB
    percent = 50.0


class FakePartition:
    """Mimics a single ``psutil.disk_partitions()`` entry."""
    def __init__(self, device: str = "C:\\", mountpoint: str = "C:\\"):
        self.device = device
        self.mountpoint = mountpoint
        self.fstype = "NTFS"


class FakeDiskUsage:
    """Mimics ``psutil.disk_usage()`` return value."""
    total = 500 * (1024 ** 3)
    used = 250 * (1024 ** 3)
    free = 250 * (1024 ** 3)
    percent = 50.0


class FakeCpuFreq:
    """Mimics ``psutil.cpu_freq()`` return value."""
    current = 3600.0
    min = 800.0
    max = 4200.0


@pytest.fixture
def mock_psutil():
    """Patch psutil functions used by diagnostic modules."""
    with (
        patch("psutil.virtual_memory", return_value=FakeVirtualMemory()),
        patch("psutil.cpu_percent", return_value=42.0),
        patch("psutil.cpu_freq", return_value=FakeCpuFreq()),
        patch("psutil.disk_partitions", return_value=[FakePartition()]),
        patch("psutil.disk_usage", return_value=FakeDiskUsage()),
    ):
        yield


# ---------------------------------------------------------------------------
# WMI mocks
# ---------------------------------------------------------------------------

class FakeWMIProcessor:
    Name = "Intel Core i7-12700K"
    NumberOfCores = 12
    NumberOfLogicalProcessors = 20
    MaxClockSpeed = 3600


class FakeWMIDiskDrive:
    Caption = "Samsung SSD 970 EVO"
    DeviceID = "\\\\.\\PHYSICALDRIVE0"
    Status = "OK"


class FakeWMIBaseBoard:
    Manufacturer = "ASUS"
    Product = "ROG STRIX Z690"
    SerialNumber = "ABC123"


class FakeWMIBIOS:
    SMBIOSBIOSVersion = "1.0.0"


class FakeWMI:
    """Minimal WMI mock."""
    def Win32_Processor(self):
        return [FakeWMIProcessor()]

    def Win32_DiskDrive(self):
        return [FakeWMIDiskDrive()]

    def Win32_BaseBoard(self):
        return [FakeWMIBaseBoard()]

    def Win32_BIOS(self):
        return [FakeWMIBIOS()]

    def Win32_VideoController(self):
        return []


@pytest.fixture
def mock_wmi():
    """Patch wmi.WMI() and pythoncom.CoInitialize."""
    with (
        patch("wmi.WMI", return_value=FakeWMI()),
        patch("pythoncom.CoInitialize"),
    ):
        yield
