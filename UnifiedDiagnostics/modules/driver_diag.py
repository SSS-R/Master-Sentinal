"""Driver diagnostics - driver health, outdated drivers, and missing drivers."""

from __future__ import annotations

import subprocess
from typing import Any

import wmi

from models.diagnostic_models import DiagnosticIssue, DiagnosticReport
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class DriverDiagnostic:
    """Gathers driver health and detects outdated or problematic drivers."""

    def get_driver_health(self) -> tuple[bool, list[dict[str, str]], str]:
        """
        Return driver health summary.

        Returns:
            Tuple of (is_healthy, issues_list, error_message)
            - is_healthy: True if no driver issues found
            - issues_list: List of dicts with driver issue details
            - error_message: Error string if collection failed
        """
        try:
            issues = []

            # Check for devices with problems
            problem_devices = self._get_problem_devices()
            issues.extend(problem_devices)

            # Check for outdated drivers (simplified check)
            outdated = self._check_outdated_drivers()
            issues.extend(outdated)

            # Check for driver verifier issues
            verifier_issues = self._check_driver_verifier()
            issues.extend(verifier_issues)

            is_healthy = len(issues) == 0
            return is_healthy, issues, ""

        except Exception as e:
            LOGGER.exception("Driver diagnostics failed: %s", e)
            return False, [], friendly_exception_message(e, "Driver diagnostics")

    def _get_problem_devices(self) -> list[dict[str, str]]:
        """Get devices with driver problems (Code 28, 31, 32, 43, etc.)."""
        issues = []
        try:
            c = wmi.WMI()
            # Query devices with ConfigManagerErrorCode
            for device in c.Win32_PnPEntity():
                error_code = getattr(device, "ConfigManagerErrorCode", None)
                if error_code is not None and error_code != 0:  # 0 = OK
                    device_name = getattr(device, "Name", "Unknown Device")
                    device_id = getattr(device, "DeviceID", "")
                    pnp_id = getattr(device, "PNPDeviceID", "")

                    issue = {
                        "device": str(device_name),
                        "device_id": str(device_id),
                        "pnp_id": str(pnp_id),
                        "error_code": str(error_code),
                        "error_message": self._map_device_error_code(error_code),
                        "severity": "critical" if error_code in [22, 28, 31, 32, 43] else "warning",
                    }
                    issues.append(issue)
        except Exception as e:
            LOGGER.warning("Problem devices check failed: %s", e)
        return issues

    @staticmethod
    def _map_device_error_code(code: int) -> str:
        """Map Windows device manager error codes to human-readable messages."""
        error_messages = {
            1: "Device not configured correctly",
            3: "Driver may be corrupted (Code 10)",
            10: "Device cannot start (Code 10)",
            12: "Device cannot find enough free resources (Code 12)",
            14: "Device cannot work properly until reboot (Code 14)",
            16: "Windows cannot identify all resources used by device (Code 16)",
            18: "Reinstall the drivers for device (Code 18)",
            19: "Registry might be corrupted (Code 19)",
            21: "Windows is removing device (Code 21)",
            22: "Device is disabled (Code 22)",
            24: "Device is not present or not working properly (Code 24)",
            25: "Windows still setting up device (Code 25)",
            28: "Drivers not installed (Code 28)",
            29: "Device disabled by firmware (Code 29)",
            31: "Device not working properly (Code 31)",
            32: "Driver (service) disabled (Code 32)",
            33: "Windows cannot determine resource required (Code 33)",
            34: "Device configured to use IRQ that another device is using (Code 34)",
            37: "Cannot initialize device driver (Code 37)",
            39: "Windows cannot load driver (Code 39)",
            41: "Windows loaded driver but cannot find device (Code 41)",
            42: "Cannot load driver because duplicate device already running (Code 42)",
            43: "Device stopped (Code 43)",
            44: "Device reported problems (Code 44)",
            45: "Device not connected (Code 45)",
            52: "Windows cannot verify digital signature (Code 52)",
        }
        return error_messages.get(code, f"Unknown error code {code}")

    def _check_outdated_drivers(self) -> list[dict[str, str]]:
        """Check for potentially outdated drivers (heuristic-based)."""
        issues = []
        try:
            c = wmi.WMI()

            # Check common driver categories
            for driver in c.Win32_PnPSignedDriver():
                driver_date = getattr(driver, "DriverDate", None)
                device_name = getattr(driver, "DeviceName", "")

                if driver_date and device_name:
                    # Parse driver date and check if older than 2 years
                    try:
                        # WMI date format: YYYYMMDDHHMMSS...
                        date_str = str(driver_date)[:8]
                        year = int(date_str[:4])
                        current_year = 2026
                        if year < current_year - 2:
                            issues.append({
                                "device": str(device_name),
                                "driver_date": date_str,
                                "issue": "Driver may be outdated (more than 2 years old)",
                                "severity": "warning",
                            })
                    except (ValueError, IndexError):
                        continue
        except Exception as e:
            LOGGER.warning("Outdated driver check failed: %s", e)
        return issues

    def _check_driver_verifier(self) -> list[dict[str, str]]:
        """Check if Driver Verifier is enabled (can cause instability)."""
        issues = []
        try:
            # Check Driver Verifier status via PowerShell
            ps_cmd = """
            $verifierKey = "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management"
            $verifier = Get-ItemProperty -Path $verifierKey -Name "VerifierFlags" -ErrorAction SilentlyContinue
            if ($verifier -and $verifier.VerifierFlags -ne 0) {
                Write-Output "ENABLED"
            } else {
                Write-Output "DISABLED"
            }
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if "ENABLED" in result.stdout:
                issues.append({
                    "device": "Driver Verifier",
                    "issue": "Driver Verifier is enabled and may cause system instability",
                    "severity": "warning",
                    "recommendation": "Run 'verifier /reset' in admin command prompt to disable",
                })
        except subprocess.TimeoutExpired:
            LOGGER.warning("Driver Verifier check timed out")
        except Exception as e:
            LOGGER.warning("Driver Verifier check failed: %s", e)
        return issues

    def get_driver_report(self) -> DiagnosticReport:
        """Generate a diagnostic report of driver issues."""
        is_healthy, issues, error = self.get_driver_health()

        if error:
            return DiagnosticReport(
                issues=[
                    DiagnosticIssue(
                        source="DriverDiagnostic",
                        category="Driver Health",
                        message=error,
                        severity="critical",
                    )
                ]
            )

        diagnostic_issues = []
        for issue in issues:
            severity = issue.get("severity", "warning")
            diagnostic_issues.append(
                DiagnosticIssue(
                    source=issue.get("device", "Unknown"),
                    category="Driver",
                    message=issue.get("issue", issue.get("error_message", "Driver issue detected")),
                    severity=severity,
                )
            )

        return DiagnosticReport(issues=diagnostic_issues if diagnostic_issues else None)
