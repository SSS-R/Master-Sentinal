"""Storage health diagnostics - enhanced drive health with warnings and temperature."""

from __future__ import annotations

import subprocess
from typing import Any

import wmi

from models.diagnostic_models import PhysicalDriveHealth, StorageHealth
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class StorageHealthDiagnostic:
    """Enhanced storage diagnostics with health warnings and temperature monitoring."""

    def get_storage_health(self) -> StorageHealth:
        """Return structured storage health with drive statuses."""
        try:
            drives = self._get_physical_drive_health()
            error_message = None
            return StorageHealth(drives=drives, error_message=error_message)
        except Exception as e:
            LOGGER.exception("Storage health diagnostics failed: %s", e)
            return StorageHealth(error_message=friendly_exception_message(e, "Storage health diagnostics"))

    def _get_physical_drive_health(self) -> list[PhysicalDriveHealth]:
        """Get health status of all physical drives."""
        drives = []
        try:
            c = wmi.WMI()

            # Query physical disks via Win32_DiskDrive
            for disk in c.Win32_DiskDrive():
                friendly_name = getattr(disk, "Model", "Unknown")
                media_type = getattr(disk, "MediaType", "Unknown")
                bus_type = getattr(disk, "InterfaceType", "Unknown") or "Unknown"
                size_bytes = getattr(disk, "Size", None)

                # Map media type to user-friendly format
                media_type_map = {
                    "Fixed hard disk media": "HDD",
                    "SSD": "SSD",
                    "Unspecified": "Unknown",
                }
                media_type_text = media_type_map.get(str(media_type), str(media_type) or "Unknown")

                # Get operational status
                status = getattr(disk, "Status", "OK")
                status_info = getattr(disk, "StatusInfo", None)

                # Try to get temperature via SMART (requires admin)
                temperature = self._get_drive_temperature(disk.DeviceID or "")

                # Determine health status
                health_status = "Healthy"
                if status and status.lower() != "ok":
                    health_status = "Degraded"
                elif status_info and status_info.lower() not in ["ok", "other", "unknown"]:
                    health_status = "Degraded"

                # Check for SMART warnings
                smart_warning = self._check_smart_warning(disk.DeviceID or "")
                if smart_warning:
                    health_status = smart_warning

                drives.append(
                    PhysicalDriveHealth(
                        friendly_name=friendly_name,
                        media_type=media_type_text,
                        bus_type=bus_type,
                        health_status=health_status,
                        operational_status=str(status or "Unknown"),
                        size_text=self._format_size(size_bytes),
                        temperature_c=temperature,
                    )
                )

        except Exception as e:
            LOGGER.warning("Physical drive health check failed: %s", e)
        return drives

    @staticmethod
    def _format_size(size_bytes: int | None) -> str:
        """Format drive size in human-readable format."""
        if size_bytes is None:
            return "Unknown"
        try:
            size_gb = int(size_bytes) / (1024 ** 3)
            if size_gb >= 1000:
                return f"{size_gb / 1000:.1f} TB"
            return f"{size_gb:.1f} GB"
        except (ValueError, TypeError):
            return "Unknown"

    def _get_drive_temperature(self, device_id: str) -> float | None:
        """Try to get drive temperature via SMART or WMI."""
        try:
            # Try MSStorageDriver_FailurePredictData via WMI (requires admin)
            c = wmi.WMI(namespace="root/WMI")
            try:
                for drive in c.MSStorageDriver_ATAPISmartData():
                    # This is a simplified attempt - full SMART parsing is complex
                    pass
            except Exception:
                pass

            # Fallback: Use PowerShell with Get-PhysicalDisk (Storage module)
            escaped_device_id = device_id.replace('\\', '\\\\')
            ps_cmd = f"""
            Get-PhysicalDisk -DeviceId "{escaped_device_id}" -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Temperature | Select-Object -First 1
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    temp = float(result.stdout.strip())
                    return temp
                except ValueError:
                    pass
        except subprocess.TimeoutExpired:
            LOGGER.warning("Drive temperature check timed out")
        except Exception as e:
            LOGGER.debug("Drive temperature check failed (expected without admin): %s", e)
        return None

    def _check_smart_warning(self, device_id: str) -> str | None:
        """Check for SMART warnings via wmic or PowerShell."""
        try:
            # Use wmic to check SMART status
            result = subprocess.run(
                ["wmic", "diskdrive", "get", "status"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line and line.lower() not in ["status", "ok"]:
                        return "SMART Warning"
        except subprocess.TimeoutExpired:
            LOGGER.warning("SMART check timed out")
        except Exception:
            pass
        return None

    def get_storage_warnings(self) -> list[dict[str, str]]:
        """Get list of storage-related warnings."""
        warnings = []
        health = self.get_storage_health()

        for drive in health.drive_statuses():
            if drive.is_warning:
                warning = {
                    "drive": drive.friendly_name,
                    "issue": "Drive health concern",
                    "details": f"Status: {drive.health_status}, Temp: {drive.temperature_c}°C" if drive.temperature_c else f"Status: {drive.health_status}",
                    "severity": "critical" if "fail" in drive.health_status.lower() else "warning",
                }
                warnings.append(warning)

        return warnings
