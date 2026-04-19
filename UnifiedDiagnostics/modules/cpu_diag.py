"""CPU diagnostics - static info and real-time usage via psutil / WMI."""

from __future__ import annotations

import psutil
import wmi
import pythoncom

from models.diagnostic_models import CPUInfo
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class CPUDiagnostic:
    """Gathers CPU information and live usage metrics."""

    def get_cpu_details(self) -> CPUInfo:
        """Return structured static CPU information."""
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            for processor in c.Win32_Processor():
                return CPUInfo(
                    name=processor.Name,
                    cores=processor.NumberOfCores,
                    threads=processor.NumberOfLogicalProcessors,
                    max_clock_speed_text=f"{processor.MaxClockSpeed} MHz",
                )
            return CPUInfo()
        except Exception as e:
            LOGGER.warning("CPU diagnostics failed: %s", e)
            return CPUInfo(error_message=friendly_exception_message(e, "CPU diagnostics"))

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
