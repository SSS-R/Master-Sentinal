"""Tests for the live snapshot service."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

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


class StubGPU:
    def __init__(self, payload):
        self.payload = payload

    def get_gpu_info(self):
        return self.payload


class StubDisk:
    def __init__(self, partitions, smart):
        self.partitions = partitions
        self.smart = smart

    def get_disk_partitions_and_usage(self):
        return self.partitions

    def get_smart_status(self):
        return self.smart


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
