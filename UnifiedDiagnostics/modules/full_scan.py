"""Full system scan — runs Windows diagnostic commands (SFC, DISM, CHKDSK, etc.)."""

from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
from typing import Callable

from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message
from services.power_report import PowerSummary, summarize_energy_report


LOGGER = get_logger(__name__)


class FullScanDiagnostic:
    """Executes a sequence of Windows system-health diagnostic commands."""

    SFC_TIMEOUT_SEC = 1800
    DISM_TIMEOUT_SEC = 2400
    CHKDSK_SCAN_TIMEOUT_SEC = 1200
    CHKDSK_QUICK_TIMEOUT_SEC = 900
    POWERCFG_TIMEOUT_SEC = 180
    BATTERY_TIMEOUT_SEC = 120

    #: Plain-language summary of the most recent power-efficiency check.
    last_power_summary: PowerSummary | None = None

    def is_admin(self) -> bool:
        """Return True if the current process has administrator privileges."""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _creation_flags() -> int:
        """Return flags that hide the console window on Windows."""
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW
        return 0

    def _run_shell_command(self, cmd: list[str], timeout_sec: int) -> subprocess.CompletedProcess[str]:
        """Run a shell command with a timeout and hidden window."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_sec,
            creationflags=self._creation_flags(),
        )

    @staticmethod
    def _parse_friendly_error(output: str) -> str:
        """Translate cryptic Windows error codes into user-friendly text."""
        out_lower = output.lower()

        if "0x800f081f" in out_lower:
            return "Error: Source Files Missing (Windows Update Issue)"
        if "0x800f0906" in out_lower:
            return "Error: Cannot Download Source Files"
        if "access is denied" in out_lower or "error: 5" in out_lower:
            return "Error: Access Denied (Run as Admin)"
        if "error: 87" in out_lower:
            return "Error: Invalid Parameter"
        if "error: 3017" in out_lower or "3017" in out_lower:
            return "Error: PENDING REBOOT (Restart PC & Try Again)"
        if "0x10d2" in out_lower or "no battery" in out_lower:
            return "Not a Laptop (No Battery Detected)"
        if "unable to perform operation" in out_lower and "library" in out_lower:
            return "Not a Laptop (No Battery)"

        # Fallback: Find an "Error:" line
        for line in output.splitlines():
            if "error:" in line.lower():
                return line.strip()

        # Last resort: return last meaningful line (truncated)
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        if lines:
            return f"Failed: {lines[-1][:60]}"

        return "Failed: Unknown Error"

    # ------------------------------------------------------------------
    # Individual checks — each returns ``(success, message)``
    # ------------------------------------------------------------------

    def run_sfc(self) -> tuple[bool, str]:
        """Run System File Checker (``sfc /scannow``)."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            result = self._run_shell_command(['sfc', '/scannow'], self.SFC_TIMEOUT_SEC)
            if result.returncode == 0:
                if "Windows Resource Protection did not find any integrity violations" in result.stdout:
                    return True, "No Integrity Violations"
                if "successfully repaired" in result.stdout:
                    return True, "Violations Found & Repaired"
                return True, "Scan Complete"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("SFC timed out: %s", e)
            return False, friendly_exception_message(e, "System File Checker")
        except Exception as e:
            LOGGER.warning("SFC failed: %s", e)
            return False, friendly_exception_message(e, "System File Checker")

    def run_dism(self) -> tuple[bool, str]:
        """Run DISM RestoreHealth."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            cmd = ['DISM', '/Online', '/Cleanup-Image', '/RestoreHealth']
            result = self._run_shell_command(cmd, self.DISM_TIMEOUT_SEC)
            if result.returncode == 0:
                return True, "Restore Operation Successful"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("DISM timed out: %s", e)
            return False, friendly_exception_message(e, "DISM image repair")
        except Exception as e:
            LOGGER.warning("DISM failed: %s", e)
            return False, friendly_exception_message(e, "DISM image repair")

    def run_chkdsk_scan(self) -> tuple[bool, str]:
        """Run CHKDSK in scan-only (online) mode."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            result = self._run_shell_command(['chkdsk', 'C:', '/scan'], self.CHKDSK_SCAN_TIMEOUT_SEC)
            if result.returncode == 0:
                if "found no problems" in result.stdout:
                    return True, "No Problems Found"
                return True, "Scan Complete"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("CHKDSK scan timed out: %s", e)
            return False, friendly_exception_message(e, "Disk Check")
        except Exception as e:
            LOGGER.warning("CHKDSK scan failed: %s", e)
            return False, friendly_exception_message(e, "Disk Check")

    def run_chkdsk_quick(self) -> tuple[bool, str]:
        """Run CHKDSK in quick/perf mode."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            result = self._run_shell_command(['chkdsk', 'C:', '/scan', '/perf'], self.CHKDSK_QUICK_TIMEOUT_SEC)
            if result.returncode == 0:
                if "found no problems" in result.stdout:
                    return True, "No Problems Found"
                return True, "Quick Scan Complete"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("Quick CHKDSK timed out: %s", e)
            return False, friendly_exception_message(e, "Quick Disk Check")
        except Exception as e:
            LOGGER.warning("Quick CHKDSK failed: %s", e)
            return False, friendly_exception_message(e, "Quick Disk Check")

    def run_memory_diag(self) -> tuple[bool, str]:
        """Launch the Windows Memory Diagnostic scheduler (triggers reboot)."""
        try:
            subprocess.Popen(['mdsched.exe'])
            return True, "Memory Diagnostic Launched"
        except Exception as e:
            LOGGER.warning("Memory Diagnostic launch failed: %s", e)
            return False, friendly_exception_message(e, "Memory Diagnostic")

    def run_power_diag(self) -> tuple[bool, str]:
        """Run Windows power-efficiency diagnostics and summarize them plainly.

        The raw ``powercfg /energy`` HTML is written to a temp file rather than the
        app folder: its red "Errors" are efficiency suggestions (not faults) and
        showing the raw file to users is misleading. We parse it into a friendly
        one-line summary that flows into the Master Sentinal scan report instead.
        """
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            report_path = os.path.join(tempfile.gettempdir(), "ms_energy_report.html")
            cmd = ['powercfg', '/energy', '/output', report_path, '/duration', '15']

            if os.path.exists(report_path):
                try:
                    os.remove(report_path)
                except OSError:
                    pass

            result = self._run_shell_command(cmd, self.POWERCFG_TIMEOUT_SEC)
            if result.returncode == 0:
                summary = summarize_energy_report(report_path)
                self.last_power_summary = summary
                return True, summary.friendly_text
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("Power diagnostics timed out: %s", e)
            return False, friendly_exception_message(e, "Power diagnostics")
        except Exception as e:
            LOGGER.warning("Power diagnostics failed: %s", e)
            return False, friendly_exception_message(e, "Power diagnostics")

    def run_battery_report(self) -> tuple[bool, str]:
        """Generate a battery report (laptops only)."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            report_path = os.path.abspath("battery-report.html")
            cmd = ['powercfg', '/batteryreport', '/output', report_path]

            if os.path.exists(report_path):
                try:
                    os.remove(report_path)
                except OSError:
                    pass

            result = self._run_shell_command(cmd, self.BATTERY_TIMEOUT_SEC)
            output = result.stdout + (result.stderr or "")

            if result.returncode == 0:
                return True, f"Report generated at {report_path}"
            return False, self._parse_friendly_error(output)
        except subprocess.TimeoutExpired as e:
            LOGGER.warning("Battery report timed out: %s", e)
            return False, friendly_exception_message(e, "Battery report")
        except Exception as e:
            LOGGER.warning("Battery report failed: %s", e)
            return False, friendly_exception_message(e, "Battery report")

    def run_driver_verifier(self) -> tuple[bool, str]:
        """Launch the Driver Verifier GUI."""
        try:
            subprocess.Popen(['verifier', '/gui'])
            return True, "Driver Verifier GUI launched."
        except Exception as e:
            LOGGER.warning("Driver Verifier launch failed: %s", e)
            return False, friendly_exception_message(e, "Driver Verifier")

    # ------------------------------------------------------------------
    # Scan list
    # ------------------------------------------------------------------

    def get_routine_scan_list(self) -> list[tuple[str, Callable[[], tuple[bool, str]], bool]]:
        """Return the checks included in the default routine health scan."""
        return [
            ("System File Checker", self.run_sfc, False),
            ("DISM Image Repair", self.run_dism, False),
            ("Disk Check (Scan)", self.run_chkdsk_scan, False),
            ("Quick Disk Check", self.run_chkdsk_quick, False),
            ("Power Monitor", self.run_power_diag, False),
            ("Battery Health", self.run_battery_report, False),
        ]

    def get_advanced_scan_list(self) -> list[tuple[str, Callable[[], tuple[bool, str]], bool]]:
        """Return deeper troubleshooting tools that need stronger user intent."""
        return [
            ("Driver Verifier", self.run_driver_verifier, False),
            ("Memory Diagnostic", self.run_memory_diag, True),
        ]

    def get_full_scan_list(self) -> list[tuple[str, Callable[[], tuple[bool, str]], bool]]:
        """Return every scan task for backwards compatibility."""
        return [*self.get_routine_scan_list(), *self.get_advanced_scan_list()]
