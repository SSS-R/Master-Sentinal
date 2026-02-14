"""Disk diagnostics — partition usage and SMART status via psutil / WMI."""

from __future__ import annotations

import psutil
import pythoncom
import wmi


class DiskDiagnostic:
    """Gathers disk partition usage and SMART health information."""

    def get_disk_partitions_and_usage(self) -> list[dict[str, str]]:
        """Return a list of dicts with usage stats per partition."""
        disks: list[dict[str, str]] = []
        try:
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        'Device': partition.device,
                        'Mountpoint': partition.mountpoint,
                        'Total': f"{usage.total / (1024**3):.2f} GB",
                        'Used': f"{usage.used / (1024**3):.2f} GB",
                        'Free': f"{usage.free / (1024**3):.2f} GB",
                        'Percent': f"{usage.percent}%",
                    })
                except PermissionError:
                    continue
        except Exception as e:
            disks.append({'Error': str(e)})
        return disks

    def get_smart_status(self) -> dict[str, str]:
        """Return SMART status per physical drive (keyed by DeviceID for stability)."""
        status: dict[str, str] = {}
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            for drive in c.Win32_DiskDrive():
                key = drive.DeviceID or drive.Caption
                display = f"{drive.Caption} — {drive.Status}"
                status[key] = display
        except Exception as e:
            status['Error'] = str(e)
        return status
