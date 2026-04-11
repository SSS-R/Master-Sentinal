"""Tests for the live snapshot service."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from models.diagnostic_models import DiskPartition, GPUDevice, MemoryStats, SmartDriveStatus
from services.live_snapshot import LiveSnapshotCollector


class StubCPU:
    def get_cpu_usage(self):
        return 42.0

    def get_per_core_usage(self):
        return [10.0, 20.0]


class StubRAM:
    def get_ram_info(self):
        return {
            "Total": "16.00 GB",
            "Available": "8.00 GB",
            "Used": "8.00 GB",
            "Percentage": 50.0,
        }

    def get_ram_stats(self):
        return MemoryStats("16.00 GB", "8.00 GB", "8.00 GB", 50.0)


class StubGPU:
    def __init__(self, payload):
        self.payload = payload

    def get_gpu_info(self):
        return self.payload

    def get_gpu_devices(self):
        return [
            GPUDevice(
                device_id=gpu.get("DeviceID", ""),
                name=gpu.get("Name", ""),
                load_text=gpu.get("Load", "N/A"),
                free_memory_text=gpu.get("Free Memory", "N/A"),
                used_memory_text=gpu.get("Used Memory", "N/A"),
                total_memory_text=gpu.get("Total Memory", "N/A"),
                temperature_text=gpu.get("Temperature", "N/A"),
                error_message=gpu.get("Error"),
            )
            for gpu in self.payload
        ]


class StubDisk:
    def __init__(self, partitions, smart):
        self.partitions = partitions
        self.smart = smart

    def get_disk_partitions_and_usage(self):
        return self.partitions

    def get_smart_status(self):
        return self.smart

    def get_disk_partitions(self):
        return [
            DiskPartition(
                device=disk.get("Device", ""),
                mountpoint=disk.get("Mountpoint", ""),
                total_text=disk.get("Total", "N/A"),
                used_text=disk.get("Used", "N/A"),
                free_text=disk.get("Free", "N/A"),
                percent_text=disk.get("Percent", "N/A"),
                error_message=disk.get("Error"),
            )
            for disk in self.partitions
        ]

    def get_smart_drive_statuses(self):
        if "Error" in self.smart:
            return [SmartDriveStatus(error_message=self.smart["Error"])]
        return [SmartDriveStatus(key=key, display_text=value) for key, value in self.smart.items()]


def test_collect_formats_dashboard_summary_for_healthy_devices():
    collector = LiveSnapshotCollector(
        cpu_mod=StubCPU(),
        ram_mod=StubRAM(),
        gpu_mod=StubGPU([{"Name": "RTX", "DeviceID": "gpu-1"}]),
        disk_mod=StubDisk([{"Device": "C:", "Mountpoint": "C:\\"}], {"disk0": "OK"}),
    )

    snapshot = collector.collect()

    assert snapshot.summary.cpu_usage_text == "42.0%"
    assert snapshot.summary.ram_usage_text == "50.0%"
    assert snapshot.summary.gpu_status_text == "1 GPU"
    assert snapshot.summary.disk_status_text == "1 Partition"
    assert snapshot.health_summary.overall_status == "ok"
    assert snapshot.memory_stats.percent_used == 50.0
    assert snapshot.gpu_devices[0].name == "RTX"
    assert snapshot.disk_partitions[0].mountpoint == "C:\\"


def test_collect_marks_device_summary_unavailable_on_errors():
    collector = LiveSnapshotCollector(
        cpu_mod=StubCPU(),
        ram_mod=StubRAM(),
        gpu_mod=StubGPU([{"Error": "WMI failure"}]),
        disk_mod=StubDisk([{"Error": "Access denied"}], {"Error": "SMART unavailable"}),
    )

    snapshot = collector.collect()

    assert snapshot.summary.gpu_status_text == "Unavailable"
    assert snapshot.summary.disk_status_text == "Unavailable"
    assert snapshot.health_summary.overall_status == "warning"
    assert snapshot.gpu_devices[0].is_error is True
    assert snapshot.disk_partitions[0].is_error is True
