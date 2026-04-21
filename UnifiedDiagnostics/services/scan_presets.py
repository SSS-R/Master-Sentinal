"""Scan presets - Quick, Standard, and Deep scan modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ScanPreset(Enum):
    """Available scan presets."""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class ScanPresetConfig:
    """Configuration for a scan preset."""

    name: str
    display_name: str
    description: str
    estimated_duration_seconds: int
    includes_repair: bool
    requires_reboot: bool


@dataclass
class ScanTask:
    """One scan task within a preset."""

    name: str
    runner: Callable[[], tuple[bool, str]]
    category: str
    estimated_seconds: int
    requires_reboot: bool = False
    caution: str = ""
    button_text: str = ""


class ScanPresetService:
    """Manages scan presets and their configurations."""

    def __init__(self, full_scan_diagnostic):
        """Initialize scan preset service."""
        self.full_scan = full_scan_diagnostic
        self.presets = {
            ScanPreset.QUICK: ScanPresetConfig(
                name="quick",
                display_name="Quick Scan",
                description="Essential checks for common issues (2 min)",
                estimated_duration_seconds=120,
                includes_repair=False,
                requires_reboot=False,
            ),
            ScanPreset.STANDARD: ScanPresetConfig(
                name="standard",
                display_name="Standard Scan",
                description="Full routine health check (10 min)",
                estimated_duration_seconds=600,
                includes_repair=True,
                requires_reboot=False,
            ),
            ScanPreset.DEEP: ScanPresetConfig(
                name="deep",
                display_name="Deep Scan",
                description="Comprehensive diagnostics including advanced tools (30 min)",
                estimated_duration_seconds=1800,
                includes_repair=True,
                requires_reboot=True,  # May trigger memory test
            ),
        }

    def get_preset_config(self, preset: ScanPreset) -> ScanPresetConfig:
        """Get configuration for a preset."""
        return self.presets[preset]

    def get_quick_scan_tasks(self) -> list[ScanTask]:
        """Get tasks for quick scan."""
        return [
            ScanTask(
                name="System File Check (Quick)",
                runner=self.full_scan.run_sfc,
                category="System Repair",
                estimated_seconds=60,
            ),
            ScanTask(
                name="Power Efficiency Check",
                runner=self.full_scan.run_power_diag,
                category="Power",
                estimated_seconds=30,
            ),
        ]

    def get_standard_scan_tasks(self) -> list[ScanTask]:
        """Get tasks for standard scan (routine health check)."""
        return [
            ScanTask(
                name="System File Checker",
                runner=self.full_scan.run_sfc,
                category="System Repair",
                estimated_seconds=180,
            ),
            ScanTask(
                name="DISM Image Repair",
                runner=self.full_scan.run_dism,
                category="System Repair",
                estimated_seconds=180,
            ),
            ScanTask(
                name="Disk Check (Scan)",
                runner=self.full_scan.run_chkdsk_scan,
                category="Storage",
                estimated_seconds=120,
            ),
            ScanTask(
                name="Power Efficiency Diagnostics",
                runner=self.full_scan.run_power_diag,
                category="Power",
                estimated_seconds=60,
            ),
            ScanTask(
                name="Battery Health Report",
                runner=self.full_scan.run_battery_report,
                category="Power",
                estimated_seconds=60,
            ),
        ]

    def get_deep_scan_tasks(self) -> list[ScanTask]:
        """Get tasks for deep scan (comprehensive)."""
        tasks = self.get_standard_scan_tasks()
        tasks.extend([
            ScanTask(
                name="Quick Disk Check (Perf)",
                runner=self.full_scan.run_chkdsk_quick,
                category="Storage",
                estimated_seconds=120,
            ),
            ScanTask(
                name="Driver Verifier",
                runner=self.full_scan.run_driver_verifier,
                category="Advanced",
                estimated_seconds=60,
                caution="Driver Verifier can destabilize your system if misconfigured. Only use when troubleshooting specific driver issues.",
            ),
            ScanTask(
                name="Memory Diagnostic",
                runner=self.full_scan.run_memory_diag,
                category="Advanced",
                estimated_seconds=60,
                requires_reboot=True,
                caution="This will schedule a memory test that runs on next reboot. Save your work before proceeding.",
            ),
        ])
        return tasks

    def get_tasks_for_preset(self, preset: ScanPreset) -> list[ScanTask]:
        """Get scan tasks for a given preset."""
        if preset == ScanPreset.QUICK:
            return self.get_quick_scan_tasks()
        elif preset == ScanPreset.STANDARD:
            return self.get_standard_scan_tasks()
        elif preset == ScanPreset.DEEP:
            return self.get_deep_scan_tasks()
        return []

    def get_total_estimated_time(self, tasks: list[ScanTask]) -> int:
        """Get total estimated time for a list of tasks."""
        return sum(task.estimated_seconds for task in tasks)
