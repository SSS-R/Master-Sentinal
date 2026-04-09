"""Metadata and orchestration helpers for health scan tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from modules.full_scan import FullScanDiagnostic


@dataclass(frozen=True)
class ScanTask:
    """Represents one executable health-check or advanced tool."""

    name: str
    runner: Callable[[], tuple[bool, str]]
    requires_reboot: bool = False
    is_advanced: bool = False
    caution: str = ""
    button_text: str = "Run"


class FullScanService:
    """Defines the scan experience presented by the UI."""

    def __init__(self, diagnostic: FullScanDiagnostic) -> None:
        self.diagnostic = diagnostic

    def get_routine_tasks(self) -> list[ScanTask]:
        """Return safe checks included in the default health scan."""
        return [
            ScanTask(name=name, runner=runner, requires_reboot=requires_reboot)
            for name, runner, requires_reboot in self.diagnostic.get_routine_scan_list()
        ]

    def get_advanced_tasks(self) -> list[ScanTask]:
        """Return tools that need stronger user intent before launching."""
        task_meta = {
            "Driver Verifier": {
                "caution": "Can destabilize systems and is intended for deeper driver debugging.",
                "button_text": "Launch Driver Verifier",
            },
            "Memory Diagnostic": {
                "caution": "Schedules a Windows memory test that requires a restart.",
                "button_text": "Schedule Memory Test",
            },
        }

        tasks: list[ScanTask] = []
        for name, runner, requires_reboot in self.diagnostic.get_advanced_scan_list():
            meta = task_meta.get(name, {})
            tasks.append(
                ScanTask(
                    name=name,
                    runner=runner,
                    requires_reboot=requires_reboot,
                    is_advanced=True,
                    caution=meta.get("caution", ""),
                    button_text=meta.get("button_text", "Run"),
                )
            )
        return tasks
