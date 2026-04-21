"""Windows Update diagnostics - update service health and pending reboot detection."""

from __future__ import annotations

import os
import subprocess
from typing import Any

import wmi

from models.diagnostic_models import WindowsUpdateHealth
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class WindowsUpdateDiagnostic:
    """Gathers Windows Update health and pending reboot state."""

    def get_update_health(self) -> WindowsUpdateHealth:
        """Return structured Windows Update health state."""
        try:
            services_result = self._get_update_services_status()
            reboot_result = self._check_pending_reboot()

            # Aggregate errors
            errors = []
            if services_result.get("error"):
                errors.append(services_result["error"])
            if reboot_result.get("error"):
                errors.append(reboot_result["error"])

            error_message = "; ".join(errors) if errors else None

            return WindowsUpdateHealth(
                update_service_state=services_result.get("wu_state", "Unknown"),
                update_service_start_mode=services_result.get("wu_start_mode", "Unknown"),
                bits_service_state=services_result.get("bits_state", "Unknown"),
                bits_service_start_mode=services_result.get("bits_start_mode", "Unknown"),
                medic_service_state=services_result.get("medic_state", "Unknown"),
                medic_service_start_mode=services_result.get("medic_start_mode", "Unknown"),
                orchestrator_service_state=services_result.get("uso_state", "Unknown"),
                orchestrator_service_start_mode=services_result.get("uso_start_mode", "Unknown"),
                reboot_pending=reboot_result.get("reboot_pending"),
                error_message=error_message,
            )

        except Exception as e:
            LOGGER.exception("Windows Update diagnostics failed: %s", e)
            return WindowsUpdateHealth(error_message=friendly_exception_message(e, "Windows Update diagnostics"))

    def _get_update_services_status(self) -> dict[str, Any]:
        """Get status of Windows Update related services."""
        result = {
            "wu_state": "Unknown",
            "wu_start_mode": "Unknown",
            "bits_state": "Unknown",
            "bits_start_mode": "Unknown",
            "medic_state": "Unknown",
            "medic_start_mode": "Unknown",
            "uso_state": "Unknown",
            "uso_start_mode": "Unknown",
            "error": None,
        }

        try:
            c = wmi.WMI()
            services_to_check = {
                "wuauserv": ("wu_state", "wu_start_mode"),  # Windows Update
                "bits": ("bits_state", "bits_start_mode"),  # Background Intelligent Transfer
                "wuauserv": ("wu_state", "wu_start_mode"),  # Windows Update (again for start mode)
                "WaaSMedicSvc": ("medic_state", "medic_start_mode"),  # Update Medic
                "UsoSvc": ("uso_state", "uso_start_mode"),  # Update Orchestrator
            }

            for service_name, (state_key, start_mode_key) in services_to_check.items():
                try:
                    services = list(c.Win32_Service(name=service_name))
                    if services:
                        svc = services[0]
                        result[state_key] = svc.State or "Unknown"
                        result[start_mode_key] = svc.StartMode or "Unknown"
                except Exception:
                    continue

            return result

        except Exception as e:
            LOGGER.warning("Update services status check failed: %s", e)
            result["error"] = friendly_exception_message(e, "Update services status")
            return result

    def _check_pending_reboot(self) -> dict[str, Any]:
        """Check if a reboot is pending."""
        result = {"reboot_pending": None, "error": None}

        try:
            # Check multiple indicators of pending reboot

            # 1. Check PendingFileRenameOperations registry key
            reboot_pending = self._check_registry_reboot()

            # 2. Check if Windows Update has a pending reboot
            if not reboot_pending:
                reboot_pending = self._check_windows_update_reboot()

            # 3. Check Component Based Servicing (CBS) reboot
            if not reboot_pending:
                reboot_pending = self._check_cbs_reboot()

            result["reboot_pending"] = reboot_pending
            return result

        except Exception as e:
            LOGGER.warning("Pending reboot check failed: %s", e)
            result["error"] = friendly_exception_message(e, "Pending reboot check")
            return result

    def _check_registry_reboot(self) -> bool:
        """Check registry for pending file rename operations (requires reboot)."""
        try:
            ps_cmd = """
            $key = Get-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager" -Name "PendingFileRenameOperations" -ErrorAction SilentlyContinue
            if ($key -and $key.PendingFileRenameOperations) {
                Write-Output "PENDING"
            } else {
                Write-Output "NOT_PENDING"
            }
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return "PENDING" in result.stdout
        except Exception:
            return False

    def _check_windows_update_reboot(self) -> bool:
        """Check if Windows Update is waiting for a reboot."""
        try:
            ps_cmd = """
            $regKey = "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update"
            $rebootRequired = Get-ItemProperty -Path $regKey -Name "RebootRequired" -ErrorAction SilentlyContinue
            if ($rebootRequired) {
                Write-Output "PENDING"
            } else {
                Write-Output "NOT_PENDING"
            }
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return "PENDING" in result.stdout
        except Exception:
            return False

    def _check_cbs_reboot(self) -> bool:
        """Check Component Based Servicing for pending reboot."""
        try:
            # Check if RebootPending file exists in CBS log
            cbs_log_path = r"C:\Windows\Logs\CBS"
            if os.path.exists(cbs_log_path):
                # Check for pending reboot marker
                ps_cmd = """
                $cbsKey = Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing" -Name "RebootPending" -ErrorAction SilentlyContinue
                if ($cbsKey) {
                    Write-Output "PENDING"
                } else {
                    Write-Output "NOT_PENDING"
                }
                """
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return "PENDING" in result.stdout
        except Exception:
            pass
        return False

    def get_update_history(self, max_entries: int = 10) -> list[dict[str, str]]:
        """Get Windows Update history (simplified via PowerShell)."""
        try:
            ps_cmd = f"""
            Get-WindowsUpdateLog -ErrorAction SilentlyContinue | Select-Object -Last {max_entries}
            """
            # Note: Get-WindowsUpdateLog requires admin and may not work on all systems
            # Fallback to querying update history via COM
            com_cmd = """
            $updateSession = New-Object -ComObject "Microsoft.Update.Session"
            $updateSearcher = $updateSession.CreateUpdateSearcher()
            $history = $updateSearcher.QueryHistory(0, 10)
            foreach ($entry in $history) {
                [PSCustomObject]@{
                    Date = $entry.Date
                    Title = $entry.Title
                    Result = $entry.ResultCode
                }
            } | Format-List
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", com_cmd],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                # Parse the output
                updates = []
                current = {}
                for line in result.stdout.splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        current[key.strip()] = value.strip()
                        if "Result" in key:
                            updates.append(current)
                            current = {}
                return updates
        except Exception as e:
            LOGGER.warning("Update history check failed: %s", e)
        return []
