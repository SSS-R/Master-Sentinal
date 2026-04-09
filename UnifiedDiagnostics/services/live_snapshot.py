"""Helpers for collecting live diagnostics without touching the UI layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
    ram: dict[str, Any]
    gpus: list[dict[str, str]]
    disks: list[dict[str, str]]
    smart: dict[str, str]
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
        ram = self.ram_mod.get_ram_info()
        gpus = self.gpu_mod.get_gpu_info()
        disks = self.disk_mod.get_disk_partitions_and_usage()
        smart = self.disk_mod.get_smart_status()
        health_summary = self.health_analyzer.analyze(cpu_load, ram, gpus, disks, smart)

        return DiagnosticSnapshot(
            cpu_load=cpu_load,
            per_core=per_core,
            ram=ram,
            gpus=gpus,
            disks=disks,
            smart=smart,
            summary=SnapshotSummary(
                cpu_usage_text=f"{cpu_load}%",
                ram_usage_text=f"{ram.get('Percentage', 'N/A')}%",
                gpu_status_text=self._format_collection_status(gpus, "GPU", "GPUs", "No GPUs Found"),
                disk_status_text=self._format_collection_status(
                    disks,
                    "Partition",
                    "Partitions",
                    "No Partitions Found",
                ),
            ),
            health_summary=health_summary,
        )

    @staticmethod
    def _format_collection_status(
        items: list[dict[str, str]],
        singular_label: str,
        plural_label: str,
        empty_text: str,
    ) -> str:
        """Return a safe summary string for dashboard cards."""
        if not items:
            return empty_text
        if any("Error" in item for item in items):
            return "Unavailable"
        count = len(items)
        label = singular_label if count == 1 else plural_label
        return f"{count} {label}"
