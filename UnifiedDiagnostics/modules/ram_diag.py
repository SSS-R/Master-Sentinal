"""RAM diagnostics — memory statistics via psutil."""

from __future__ import annotations

import psutil

from models.diagnostic_models import MemoryStats


class RAMDiagnostic:
    """Gathers system memory (RAM) statistics."""

    def get_ram_stats(self) -> MemoryStats:
        """Return structured RAM statistics."""
        mem = psutil.virtual_memory()

        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)

        return MemoryStats(
            total_gb_text=f"{total_gb:.2f} GB",
            available_gb_text=f"{available_gb:.2f} GB",
            used_gb_text=f"{used_gb:.2f} GB",
            percent_used=mem.percent,
        )

