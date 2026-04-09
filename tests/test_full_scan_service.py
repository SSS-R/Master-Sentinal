"""Tests for scan-task categorisation."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.full_scan_service import FullScanService


class FakeDiagnostic:
    def run_sfc(self):
        return True, "ok"

    def run_dism(self):
        return True, "ok"

    def run_chkdsk_scan(self):
        return True, "ok"

    def run_chkdsk_quick(self):
        return True, "ok"

    def run_power_diag(self):
        return True, "ok"

    def run_battery_report(self):
        return True, "ok"

    def run_driver_verifier(self):
        return True, "ok"

    def run_memory_diag(self):
        return True, "ok"

    def get_routine_scan_list(self):
        return [
            ("System File Checker", self.run_sfc, False),
            ("DISM Image Repair", self.run_dism, False),
            ("Disk Check (Scan)", self.run_chkdsk_scan, False),
            ("Quick Disk Check", self.run_chkdsk_quick, False),
            ("Power Monitor", self.run_power_diag, False),
            ("Battery Health", self.run_battery_report, False),
        ]

    def get_advanced_scan_list(self):
        return [
            ("Driver Verifier", self.run_driver_verifier, False),
            ("Memory Diagnostic", self.run_memory_diag, True),
        ]


def test_routine_tasks_exclude_advanced_tools():
    service = FullScanService(FakeDiagnostic())

    names = [task.name for task in service.get_routine_tasks()]

    assert "Driver Verifier" not in names
    assert "Memory Diagnostic" not in names
    assert len(names) == 6


def test_advanced_tasks_capture_risky_actions():
    service = FullScanService(FakeDiagnostic())

    tasks = {task.name: task for task in service.get_advanced_tasks()}

    assert tasks["Driver Verifier"].is_advanced is True
    assert tasks["Memory Diagnostic"].requires_reboot is True
