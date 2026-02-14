"""CPU diagnostics — static info and real-time usage via psutil / WMI."""

from __future__ import annotations

import psutil
import wmi
import pythoncom


class CPUDiagnostic:
    """Gathers CPU information and live usage metrics."""

    def get_cpu_info(self) -> dict[str, str | int]:
        """Return static CPU information (name, cores, threads, clock speed)."""
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            cpu_info: dict[str, str | int] = {}
            for processor in c.Win32_Processor():
                cpu_info['Name'] = processor.Name
                cpu_info['Cores'] = processor.NumberOfCores
                cpu_info['Threads'] = processor.NumberOfLogicalProcessors
                cpu_info['MaxClockSpeed'] = f"{processor.MaxClockSpeed} MHz"
                break  # Assume single socket
            return cpu_info
        except Exception as e:
            return {'Error': str(e)}

    def get_cpu_usage(self) -> float:
        """Return overall CPU usage percentage (non-blocking)."""
        return psutil.cpu_percent(interval=None)

    def get_per_core_usage(self) -> list[float]:
        """Return a list of per-logical-core usage percentages."""
        return psutil.cpu_percent(interval=None, percpu=True)

    def get_frequency(self) -> str:
        """Return current CPU frequency as a formatted string."""
        freq = psutil.cpu_freq()
        if freq:
            return f"{freq.current:.2f} MHz"
        return "N/A"
