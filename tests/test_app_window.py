"""Practical tests for app-window update/report helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from models.diagnostic_models import CPUInfo, DiskPartition, GPUDevice, MemoryStats, SmartDriveStatus
from models.health_models import HealthFinding, HealthSummary
from services.live_snapshot import DiagnosticReport
from ui.app_window import App


class _Value:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _Module:
    def __init__(self, value):
        self.value = value

    def get_cpu_details(self):
        return self.value

    def get_board_details(self):
        return self.value

    def get_ram_stats(self):
        return self.value

    def get_gpu_devices(self):
        return self.value

    def get_disk_partitions(self):
        return self.value

    def get_smart_drive_statuses(self):
        return self.value

    def is_admin(self):
        return False


class _DummyApp:
    _build_report_payload = App._build_report_payload
    _device_rows = staticmethod(App._device_rows)
    _is_running_as_admin = App._is_running_as_admin
    _finalize_scan_status = App._finalize_scan_status

    def __init__(self):
        self.cpu_usage_var = _Value("12%")
        self.ram_usage_var = _Value("44%")
        self.cpu_mod = _Module(CPUInfo(name="CPU", cores=8))
        self.board_mod = _Module(type("Board", (), {"as_rows": lambda self: {"System": "Windows"}})())
        self.ram_mod = _Module(MemoryStats("16 GB", "8 GB", "8 GB", 50.0))
        self.gpu_mod = _Module([GPUDevice(name="GPU 0", load_text="20%")])
        self.disk_mod = _Module([DiskPartition(device="C:", mountpoint="C:\\", percent_text="40%")])
        self.full_scan_mod = _Module(None)
        self._last_cpu_info = CPUInfo(name="CPU", cores=8)
        self._last_board_info = type("Board", (), {"as_rows": lambda self: {"System": "Windows"}})()
        self._last_memory_stats = MemoryStats("16 GB", "8 GB", "8 GB", 50.0)
        self._last_gpu_devices = [GPUDevice(name="GPU 0", load_text="20%")]
        self._last_disk_partitions = [DiskPartition(device="C:", mountpoint="C:\\", percent_text="40%")]
        self._last_smart_drives = [SmartDriveStatus(key="disk0", display_text="OK")]
        self._last_health_summary = HealthSummary(
            overall_status="warning",
            headline="Warnings detected",
            findings=[
                HealthFinding(
                    title="Disk warning",
                    message="Disk usage is high",
                    severity="warning",
                    recommended_action="Free some space",
                    state="warning",
                    persistence="persistent",
                )
            ],
            health_score=88,
            severity_counts={"warning": 1},
            severity_rollup="1 warning",
        )
        self._last_diagnostic_report = DiagnosticReport()
        self.scan_logs = []
        self.last_scan_started_at = None
        self.last_scan_finished_at = None
        self._status_updates = []

    def _ui_scan_status(self, row_map, name, text, color):
        self._status_updates.append((row_map, name, text, color))


def test_build_report_payload_includes_health_and_scan_data():
    app = _DummyApp()
    app.scan_logs = [{"task": "SFC", "status": "success", "duration": "1.0s", "message": "OK"}]

    payload = app._build_report_payload()

    assert payload["metadata"]["app_name"] == "Master Sentinal"
    assert payload["sections"]["CPU"]["Usage"] == "12%"
    assert payload["health"]["score"] == 88
    assert payload["health"]["findings"][0]["recommended_action"] == "Free some space"
    assert payload["scan_logs"][0]["task"] == "SFC"


def test_finalize_scan_status_records_log_entry():
    app = _DummyApp()
    result = type(
        "ScanResultLike",
        (),
        {
            "task_name": "SFC",
            "success": False,
            "message": "Timed out",
            "display_text": "Timed out",
            "status_color": "red",
            "log_message": "[SFC] FAILED: Timed out",
        },
    )()

    app._finalize_scan_status({"SFC": object()}, result, 3.2)

    assert app.scan_logs[0]["task"] == "SFC"
    assert app.scan_logs[0]["duration"] == "3.2s"
    assert app._status_updates[0][2] == "Timed out (3.2s)"
