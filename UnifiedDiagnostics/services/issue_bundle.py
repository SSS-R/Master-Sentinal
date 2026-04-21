"""Portable issue bundle export - complete diagnostic bundle for support/debugging."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.app_logging import get_logger


LOGGER = get_logger(__name__)


class IssueBundleExporter:
    """Exports complete diagnostic bundles for support and community debugging."""

    def __init__(self, diagnostic_data: dict[str, Any] | None = None):
        """
        Initialize exporter.

        Args:
            diagnostic_data: Optional pre-collected diagnostic data
        """
        self.diagnostic_data = diagnostic_data or {}

    def collect_system_info(self) -> dict[str, Any]:
        """Collect comprehensive system information."""
        info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "os": {
                "platform": platform.platform(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
            },
            "hardware": {
                "cpu": self._get_cpu_info(),
                "memory": self._get_memory_info(),
                "disks": self._get_disk_info(),
            },
            "software": {
                "installed_apps": self._get_installed_apps()[:50],  # Limit to 50
                "windows_updates": self._get_recent_updates()[:20],  # Limit to 20
            },
        }
        return info

    def _get_cpu_info(self) -> dict[str, Any]:
        """Get CPU information."""
        try:
            import psutil
            return {
                "name": platform.processor(),
                "cores": psutil.cpu_count(logical=False),
                "threads": psutil.cpu_count(logical=True),
            }
        except Exception:
            return {"error": "Unable to collect CPU info"}

    def _get_memory_info(self) -> dict[str, Any]:
        """Get memory information."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "available_gb": round(mem.available / (1024 ** 3), 2),
                "percent_used": mem.percent,
            }
        except Exception:
            return {"error": "Unable to collect memory info"}

    def _get_disk_info(self) -> list[dict[str, Any]]:
        """Get disk information."""
        disks = []
        try:
            import psutil
            for partition in psutil.disk_partitions(all=True):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total_gb": round(usage.total / (1024 ** 3), 2),
                        "used_gb": round(usage.used / (1024 ** 3), 2),
                        "percent_used": usage.percent,
                    })
                except (PermissionError, OSError):
                    continue
        except Exception:
            pass
        return disks

    def _get_installed_apps(self) -> list[str]:
        """Get list of installed applications."""
        apps = []
        try:
            # Query via PowerShell
            ps_cmd = """
            Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |
            Select-Object -Property DisplayName -ErrorAction SilentlyContinue |
            Where-Object {$_.DisplayName -ne $null} |
            Select-Object -First 50 DisplayName
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if ":" in line:
                        apps.append(line.split(":", 1)[1].strip())
        except Exception as e:
            LOGGER.debug("Failed to get installed apps: %s", e)
        return apps

    def _get_recent_updates(self) -> list[dict[str, str]]:
        """Get recent Windows Update history."""
        updates = []
        try:
            ps_cmd = """
            $updateSession = New-Object -ComObject "Microsoft.Update.Session"
            $updateSearcher = $updateSession.CreateUpdateSearcher()
            $history = $updateSearcher.QueryHistory(0, 20)
            foreach ($entry in $history) {
                [PSCustomObject]@{
                    Date = $entry.Date
                    Title = $entry.Title
                    Result = @("Failed","Succeeded","Aborted","InProgress")[$entry.ResultCode - 1]
                }
            } | ConvertTo-Json -Array
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and result.stdout.strip():
                updates = json.loads(result.stdout)
        except Exception as e:
            LOGGER.debug("Failed to get update history: %s", e)
        return updates

    def collect_logs(self) -> dict[str, str]:
        """Collect application logs."""
        logs = {}

        # Get master sentinal log
        log_path = Path("logs") / "master_sentinal.log"
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    # Get last 500 lines
                    lines = f.readlines()[-500:]
                    logs["master_sentinal.log"] = "".join(lines)
            except Exception as e:
                logs["error"] = f"Failed to read log: {e}"

        # Get Windows Event Log errors (recent)
        try:
            ps_cmd = """
            Get-WinEvent -FilterHashtable @{LogName='System';Level=1,2} -MaxEvents 50 -ErrorAction SilentlyContinue |
            Select-Object -Property TimeCreated,ProviderName,Message,Id |
            ConvertTo-Json -Compress
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and result.stdout.strip():
                logs["recent_system_errors.json"] = result.stdout
        except Exception:
            pass

        return logs

    def export_bundle(self, output_path: str) -> bool:
        """
        Export complete issue bundle as a zip file.

        Args:
            output_path: Path for the output zip file

        Returns:
            True if export succeeded
        """
        try:
            # Ensure output path ends with .zip
            if not output_path.endswith(".zip"):
                output_path += ".zip"

            # Create temp directory for bundle contents
            bundle_dir = Path(os.getenv("TEMP", ".")) / "master_sentinal_bundle"
            bundle_dir.mkdir(parents=True, exist_ok=True)

            # Collect system info
            system_info = self.collect_system_info()
            with open(bundle_dir / "system_info.json", "w", encoding="utf-8") as f:
                json.dump(system_info, f, indent=2, default=str)

            # Collect diagnostic data if available
            if self.diagnostic_data:
                with open(bundle_dir / "diagnostics.json", "w", encoding="utf-8") as f:
                    json.dump(self.diagnostic_data, f, indent=2, default=str)

            # Collect logs
            logs = self.collect_logs()
            logs_dir = bundle_dir / "logs"
            logs_dir.mkdir(exist_ok=True)
            for log_name, log_content in logs.items():
                safe_name = log_name.replace("/", "_").replace("\\", "_")
                with open(logs_dir / safe_name, "w", encoding="utf-8") as f:
                    f.write(log_content)

            # Create README with context
            readme = self._generate_readme(system_info)
            with open(bundle_dir / "README.txt", "w", encoding="utf-8") as f:
                f.write(readme)

            # Create zip archive
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in bundle_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(bundle_dir)
                        zipf.write(file_path, arcname)

            # Clean up temp directory
            try:
                for file_path in bundle_dir.rglob("*"):
                    if file_path.is_file():
                        file_path.unlink()
                bundle_dir.rmdir()
            except Exception:
                pass  # Best effort cleanup

            LOGGER.info(f"Issue bundle exported to {output_path}")
            return True

        except Exception as e:
            LOGGER.exception(f"Failed to export issue bundle: {e}")
            return False

    def _generate_readme(self, system_info: dict[str, Any]) -> str:
        """Generate README with bundle context."""
        return f"""MASTER SENTINAL - DIAGNOSTIC BUNDLE
===================================

Generated: {system_info.get('timestamp', 'Unknown')}

SYSTEM OVERVIEW
---------------
OS: {system_info.get('os', {}).get('platform', 'Unknown')}
CPU: {system_info.get('hardware', {}).get('cpu', {}).get('name', 'Unknown')}
Memory: {system_info.get('hardware', {}).get('memory', {}).get('total_gb', 'Unknown')} GB

CONTENTS
--------
- system_info.json: Comprehensive system information
- diagnostics.json: Application diagnostic data (if available)
- logs/: Application and system logs
- README.txt: This file

SHARING THIS BUNDLE
-------------------
This bundle contains system information that may include:
- Hardware configuration
- Installed software list
- System event logs

Review the contents before sharing publicly. The bundle does NOT intentionally
collect personal files, passwords, or sensitive documents.

For support, share this bundle via:
- GitHub Issues: https://github.com/SSS-R/Master-Sentinal/issues
- Community forums
- Direct to support team

VERSION INFO
------------
Bundle Format: 1.0
"""
