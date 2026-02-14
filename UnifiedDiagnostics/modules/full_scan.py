"""Full system scan — runs Windows diagnostic commands (SFC, DISM, CHKDSK, etc.)."""

from __future__ import annotations

import ctypes
import os
import subprocess
from typing import Callable


class FullScanDiagnostic:
    """Executes a sequence of Windows system-health diagnostic commands."""

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
            result = subprocess.run(
                ['sfc', '/scannow'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                if "Windows Resource Protection did not find any integrity violations" in result.stdout:
                    return True, "No Integrity Violations"
                if "successfully repaired" in result.stdout:
                    return True, "Violations Found & Repaired"
                return True, "Scan Complete"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except Exception as e:
            return False, str(e)

    def run_dism(self) -> tuple[bool, str]:
        """Run DISM RestoreHealth."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            cmd = ['DISM', '/Online', '/Cleanup-Image', '/RestoreHealth']
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return True, "Restore Operation Successful"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except Exception as e:
            return False, str(e)

    def run_chkdsk_scan(self) -> tuple[bool, str]:
        """Run CHKDSK in scan-only (online) mode."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            result = subprocess.run(
                ['chkdsk', 'C:', '/scan'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                if "found no problems" in result.stdout:
                    return True, "No Problems Found"
                return True, "Scan Complete"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except Exception as e:
            return False, str(e)

    def run_chkdsk_quick(self) -> tuple[bool, str]:
        """Run CHKDSK in quick/perf mode."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            result = subprocess.run(
                ['chkdsk', 'C:', '/scan', '/perf'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                if "found no problems" in result.stdout:
                    return True, "No Problems Found"
                return True, "Quick Scan Complete"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except Exception as e:
            return False, str(e)

    def run_memory_diag(self) -> tuple[bool, str]:
        """Launch the Windows Memory Diagnostic scheduler (triggers reboot)."""
        try:
            subprocess.Popen(['mdsched.exe'])
            return True, "Memory Diagnostic Launched"
        except Exception as e:
            return False, str(e)

    def run_power_diag(self) -> tuple[bool, str]:
        """Run Power Efficiency Diagnostics and return the report path."""
        if not self.is_admin():
            return False, "Administrator privileges required."

        try:
            report_path = os.path.abspath("energy-report.html")
            cmd = ['powercfg', '/energy', '/output', report_path, '/duration', '15']

            if os.path.exists(report_path):
                try:
                    os.remove(report_path)
                except OSError:
                    pass

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return True, f"Report generated at {report_path}"
            output = result.stdout + (result.stderr or "")
            return False, self._parse_friendly_error(output)
        except Exception as e:
            return False, str(e)

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

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            output = result.stdout + (result.stderr or "")

            if result.returncode == 0:
                return True, f"Report generated at {report_path}"
            return False, self._parse_friendly_error(output)
        except Exception as e:
            return False, str(e)

    def run_driver_verifier(self) -> tuple[bool, str]:
        """Launch the Driver Verifier GUI."""
        try:
            subprocess.Popen(['verifier', '/gui'])
            return True, "Driver Verifier GUI launched."
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Scan list
    # ------------------------------------------------------------------

    def get_full_scan_list(self) -> list[tuple[str, Callable[[], tuple[bool, str]], bool]]:
        """Return an ordered list of ``(name, function, requires_reboot)`` tuples."""
        return [
            ("System File Checker", self.run_sfc, False),
            ("DISM Image Repair", self.run_dism, False),
            ("Disk Check (Scan)", self.run_chkdsk_scan, False),
            ("Quick Disk Check", self.run_chkdsk_quick, False),
            ("Power Monitor", self.run_power_diag, False),
            ("Battery Health", self.run_battery_report, False),
            ("Driver Verifier", self.run_driver_verifier, False),
            ("Memory Diagnostic", self.run_memory_diag, True),
        ]
