"""Startup diagnostics - startup items and background services."""

from __future__ import annotations

import subprocess
from typing import Any

import wmi

from models.diagnostic_models import (
    BackgroundServiceStatus,
    SlowStartupService,
    StartupHealth,
    StartupItemStatus,
)
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class StartupDiagnostic:
    """Gathers startup items and background service health data."""

    def get_startup_health(self) -> StartupHealth:
        """Return structured startup and service health state."""
        try:
            startup_result = self._get_startup_items()
            slow_startup_result = self._get_slow_startup_services()
            services_result = self._get_automatic_services()

            # Aggregate errors
            errors = []
            if startup_result.get("error"):
                errors.append(startup_result["error"])
            if slow_startup_result.get("error"):
                errors.append(slow_startup_result["error"])
            if services_result.get("error"):
                errors.append(services_result["error"])

            error_message = "; ".join(errors) if errors else None

            return StartupHealth(
                startup_items=startup_result.get("items", []),
                slow_startup_services=slow_startup_result.get("slow_services", []),
                automatic_services=services_result.get("services", []),
                startup_error=startup_result.get("error", ""),
                slow_startup_error=slow_startup_result.get("error", ""),
                service_error=services_result.get("error", ""),
                error_message=error_message,
            )

        except Exception as e:
            LOGGER.exception("Startup diagnostics failed: %s", e)
            return StartupHealth(error_message=friendly_exception_message(e, "Startup diagnostics"))

    def _get_startup_items(self) -> dict[str, Any]:
        """Get list of startup items from registry and WMI."""
        try:
            items = []
            c = wmi.WMI()

            # Query startup items via WMI (Win32_StartupCommand)
            try:
                startup_commands = list(c.Win32_StartupCommand())
                for cmd in startup_commands:
                    items.append(
                        StartupItemStatus(
                            name=getattr(cmd, "Name", "Unknown") or "Unknown",
                            command=getattr(cmd, "Command", ""),
                            location=getattr(cmd, "Location", ""),
                            user=getattr(cmd, "User", ""),
                            enabled=True,  # WMI startup commands are typically enabled
                            impact_text="Unknown",
                        )
                    )
            except Exception:
                pass

            # Fallback: Check registry run keys via PowerShell
            if not items:
                ps_cmd = """
                Get-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
                                     "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" -ErrorAction SilentlyContinue |
                Select-Object -Property * |
                Format-List
                """
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0:
                    # Parse PowerShell output
                    for line in result.stdout.splitlines():
                        if ":" in line and not line.startswith("-"):
                            parts = line.split(":", 1)
                            if len(parts) == 2:
                                name = parts[0].strip()
                                command = parts[1].strip()
                                if name and command:
                                    items.append(
                                        StartupItemStatus(
                                            name=name,
                                            command=command,
                                            location="Registry Run Key",
                                            user="System",
                                            enabled=True,
                                            impact_text="Unknown",
                                        )
                                    )

            return {"items": items, "error": None}

        except subprocess.TimeoutExpired:
            LOGGER.warning("Startup items check timed out")
            return {"items": [], "error": "Startup items check timed out"}
        except Exception as e:
            LOGGER.warning("Startup items check failed: %s", e)
            return {"items": [], "error": friendly_exception_message(e, "Startup items")}

    def _get_slow_startup_services(self) -> dict[str, Any]:
        """Get services that were reported as slow during startup."""
        try:
            slow_services = []

            # Query System Event Log for slow startup events (Event ID 7001 from Service Control Manager)
            ps_cmd = """
            Get-WinEvent -FilterHashtable @{LogName='System';Id=7001} -MaxEvents 20 -ErrorAction SilentlyContinue |
            Select-Object -Property TimeCreated,Message,Id |
            Format-List -Property TimeCreated,Message,Id
            """
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                # Parse PowerShell output for service names
                current_message = ""
                for line in result.stdout.splitlines():
                    if "Message:" in line:
                        current_message = line
                    elif "The" in line and "service" in line and "took" in line:
                        # Parse: "The ServiceName service took ... seconds to start"
                        parts = line.split()
                        if len(parts) > 1:
                            service_name = parts[1]
                            slow_services.append(
                                SlowStartupService(
                                    service_name=service_name,
                                    startup_time_ms=None,  # Would need more parsing to extract
                                )
                            )

            return {"slow_services": slow_services, "error": None}

        except subprocess.TimeoutExpired:
            LOGGER.warning("Slow startup services check timed out")
            return {"slow_services": [], "error": "Slow startup services check timed out"}
        except Exception as e:
            LOGGER.warning("Slow startup services check failed: %s", e)
            return {"slow_services": [], "error": friendly_exception_message(e, "Slow startup services")}

    def _get_automatic_services(self) -> dict[str, Any]:
        """Get list of automatic (background) services."""
        try:
            services = []
            c = wmi.WMI()

            # Query services with automatic start mode
            for svc in c.Win32_Service():
                start_mode = getattr(svc, "StartMode", "")
                state = getattr(svc, "State", "")
                delayed = getattr(svc, "DelayedAutoStart", False)

                if start_mode and start_mode.lower() in ["auto", "automatic"]:
                    services.append(
                        BackgroundServiceStatus(
                            name=getattr(svc, "Name", "Unknown"),
                            display_name=getattr(svc, "DisplayName", "Unknown"),
                            state=state or "Unknown",
                            start_mode=start_mode,
                            start_name=getattr(svc, "StartName", ""),
                            delayed_auto_start=bool(delayed) if delayed is not None else None,
                        )
                    )

            return {"services": services, "error": None}

        except Exception as e:
            LOGGER.warning("Automatic services check failed: %s", e)
            return {"services": [], "error": friendly_exception_message(e, "Automatic services")}
