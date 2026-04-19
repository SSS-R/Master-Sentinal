"""Disk diagnostics - partition usage and SMART status via psutil / WMI."""

from __future__ import annotations

import psutil
import pythoncom
import wmi

from models.diagnostic_models import DiskPartition, SmartDriveStatus
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class DiskDiagnostic:
    """Gathers disk partition usage and SMART health information."""

    def get_disk_partitions(self) -> list[DiskPartition]:
        """Return structured partition usage stats."""
        disks: list[DiskPartition] = []
        try:
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append(
                        DiskPartition(
                            device=partition.device,
                            mountpoint=partition.mountpoint,
                            total_text=f"{usage.total / (1024**3):.2f} GB",
                            used_text=f"{usage.used / (1024**3):.2f} GB",
                            free_text=f"{usage.free / (1024**3):.2f} GB",
                            percent_text=f"{usage.percent}%",
                        )
                    )
                except PermissionError:
                    continue
        except Exception as e:
            LOGGER.warning("Disk partition diagnostics failed: %s", e)
            disks.append(DiskPartition(error_message=friendly_exception_message(e, "Disk diagnostics")))
        return disks

    def get_smart_drive_statuses(self) -> list[SmartDriveStatus]:
        """Return structured SMART status per physical drive."""
        statuses: list[SmartDriveStatus] = []
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            for drive in c.Win32_DiskDrive():
                key = drive.DeviceID or drive.Caption
                display = f"{drive.Caption} - {drive.Status}"
                statuses.append(SmartDriveStatus(key=key, display_text=display))
        except Exception as e:
            LOGGER.warning("SMART diagnostics failed: %s", e)
            statuses.append(SmartDriveStatus(error_message=friendly_exception_message(e, "SMART diagnostics")))
        return statuses

