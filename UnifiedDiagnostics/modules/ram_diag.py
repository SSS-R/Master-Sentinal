"""RAM diagnostics — memory statistics via psutil."""

from __future__ import annotations

import psutil


class RAMDiagnostic:
    """Gathers system memory (RAM) statistics."""

    def get_ram_info(self) -> dict[str, str | float]:
        """Return a dictionary of RAM statistics (Total, Available, Used, Percentage)."""
        mem = psutil.virtual_memory()

        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)

        return {
            'Total': f"{total_gb:.2f} GB",
            'Available': f"{available_gb:.2f} GB",
            'Used': f"{used_gb:.2f} GB",
            'Percentage': mem.percent,
        }
