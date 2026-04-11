"""Helpers for collecting live diagnostics without touching the UI layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from models.diagnostic_models import DiskPartition, GPUDevice, MemoryStats, SmartDriveStatus
from models.health_models import HealthSummary
from services.health_analyzer import HealthAnalyzer

if TYPE_CHECKING:
    from modules.cpu_diag import CPUDiagnostic
    from modules.disk_diag import DiskDiagnostic
    from modules.gpu_diag import GPUDiagnostic
    from modules.ram_diag import RAMDiagnostic


@dataclass(frozen=True)
class SnapshotSummary:
    """Pre-formatted values displayed on the dashboard cards."""

    cpu_usage_text: str
    ram_usage_text: str
    gpu_status_text: str
    disk_status_text: str


@dataclass(frozen=True)
class DiagnosticSnapshot:
    """Full live snapshot returned by the monitoring service."""

    cpu_load: float
    per_core: list[float]
    memory_stats: MemoryStats
    gpu_devices: list[GPUDevice]
    disk_partitions: list[DiskPartition]
    smart_drives: list[SmartDriveStatus]
    summary: SnapshotSummary
    health_summary: HealthSummary


class LiveSnapshotCollector:
    """Collects diagnostics and formats a UI-ready snapshot."""

    def __init__(
        self,
        cpu_mod: CPUDiagnostic,
        ram_mod: RAMDiagnostic,
        gpu_mod: GPUDiagnostic,
        disk_mod: DiskDiagnostic,
        health_analyzer: HealthAnalyzer | None = None,
    ) -> None:
        self.cpu_mod = cpu_mod
        self.ram_mod = ram_mod
        self.gpu_mod = gpu_mod
        self.disk_mod = disk_mod
        self.health_analyzer = health_analyzer or HealthAnalyzer()

    def collect(self) -> DiagnosticSnapshot:
        """Gather a full live snapshot from the diagnostics modules."""
        cpu_load = self.cpu_mod.get_cpu_usage()
        per_core = self.cpu_mod.get_per_core_usage()
        memory_stats = self.ram_mod.get_ram_stats()
        gpu_devices = self.gpu_mod.get_gpu_devices()
        disk_partitions = self.disk_mod.get_disk_partitions()
        smart_drives = self.disk_mod.get_smart_drive_statuses()
        health_summary = self.health_analyzer.analyze(
            cpu_load,
            memory_stats,
            gpu_devices,
            disk_partitions,
            smart_drives,
        )

        return DiagnosticSnapshot(
            cpu_load=cpu_load,
            per_core=per_core,
            memory_stats=memory_stats,
            gpu_devices=gpu_devices,
            disk_partitions=disk_partitions,
            smart_drives=smart_drives,
            summary=SnapshotSummary(
                cpu_usage_text=f"{cpu_load}%",
                ram_usage_text=f"{memory_stats.percent_used}%",
                gpu_status_text=self._format_collection_status(gpu_devices, "GPU", "GPUs", "No GPUs Found"),
                disk_status_text=self._format_collection_status(
                    disk_partitions,
                    "Partition",
                    "Partitions",
                    "No Partitions Found",
                ),
            ),
            health_summary=health_summary,
        )

    @staticmethod
    def _format_collection_status(
        items: list[object],
        singular_label: str,
        plural_label: str,
        empty_text: str,
    ) -> str:
        """Return a safe summary string for dashboard cards."""
        if not items:
            return empty_text
        if any(getattr(item, "is_error", False) for item in items):
            return "Unavailable"
        count = len(items)
        label = singular_label if count == 1 else plural_label
        return f"{count} {label}"
