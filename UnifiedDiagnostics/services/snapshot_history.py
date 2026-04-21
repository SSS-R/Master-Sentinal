"""Snapshot history tracking - save and compare diagnostic snapshots over time."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.app_logging import get_logger


LOGGER = get_logger(__name__)


@dataclass
class SnapshotRecord:
    """One saved snapshot record."""

    timestamp: str
    health_score: int | None
    cpu_usage: float
    ram_usage_percent: float
    gpu_count: int
    disk_count: int
    critical_count: int
    warning_count: int
    temp_max_c: float | None
    disk_free_percent: float | None


class SnapshotHistory:
    """Manages snapshot history for trend analysis."""

    def __init__(self, history_file: str | None = None):
        """Initialize snapshot history manager."""
        if history_file:
            self.history_file = Path(history_file)
        else:
            # Default location in user's app data
            app_data = os.getenv("APPDATA", str(Path.home()))
            history_dir = Path(app_data) / "MasterSentinal" / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            self.history_file = history_dir / "snapshot_history.jsonl"

    def save_snapshot(self, snapshot_data: dict[str, Any]) -> bool:
        """
        Save a diagnostic snapshot to history.

        Args:
            snapshot_data: Dict containing snapshot metrics

        Returns:
            True if saved successfully
        """
        try:
            record = SnapshotRecord(
                timestamp=snapshot_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                health_score=snapshot_data.get("health_score"),
                cpu_usage=snapshot_data.get("cpu_usage", 0),
                ram_usage_percent=snapshot_data.get("ram_usage_percent", 0),
                gpu_count=snapshot_data.get("gpu_count", 0),
                disk_count=snapshot_data.get("disk_count", 0),
                critical_count=snapshot_data.get("critical_count", 0),
                warning_count=snapshot_data.get("warning_count", 0),
                temp_max_c=snapshot_data.get("temp_max_c"),
                disk_free_percent=snapshot_data.get("disk_free_percent"),
            )

            with open(self.history_file, "a", encoding="utf-8") as f:
                json_line = json.dumps(asdict(record))
                f.write(json_line + "\n")

            LOGGER.info("Snapshot saved to history")
            return True

        except Exception as e:
            LOGGER.exception("Failed to save snapshot: %s", e)
            return False

    def get_history(self, limit: int = 100) -> list[SnapshotRecord]:
        """
        Get snapshot history.

        Args:
            limit: Maximum number of records to return

        Returns:
            List of SnapshotRecord objects, newest first
        """
        records = []
        try:
            if not self.history_file.exists():
                return []

            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            records.append(SnapshotRecord(**data))
                        except (json.JSONDecodeError, TypeError):
                            continue

            # Return newest first
            records.sort(key=lambda r: r.timestamp, reverse=True)
            return records[:limit]

        except Exception as e:
            LOGGER.exception("Failed to read history: %s", e)
            return []

    def get_trend(self, metric: str, lookback_hours: int = 24) -> dict[str, Any]:
        """
        Calculate trend for a specific metric.

        Args:
            metric: Metric name (cpu_usage, ram_usage_percent, health_score, etc.)
            lookback_hours: Hours to look back

        Returns:
            Dict with current, previous, change, and trend_direction
        """
        records = self.get_history()
        if not records:
            return {"current": None, "previous": None, "change": 0, "trend_direction": "stable"}

        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - (lookback_hours * 3600)

        # Find current (most recent) and previous values
        current_value = None
        previous_value = None

        for i, record in enumerate(records):
            try:
                record_time = datetime.fromisoformat(record.timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            value = getattr(record, metric, None)
            if value is None:
                continue

            if current_value is None:
                current_value = value
            elif record_time.timestamp() < cutoff:
                previous_value = value
                break
            elif i > 0:
                previous_value = value
                break

        if current_value is None:
            return {"current": None, "previous": None, "change": 0, "trend_direction": "no_data"}

        if previous_value is None:
            return {"current": current_value, "previous": None, "change": 0, "trend_direction": "new"}

        change = current_value - previous_value
        if abs(change) < 0.01:
            trend = "stable"
        elif change > 0:
            trend = "increasing" if metric in ["cpu_usage", "ram_usage_percent", "temp_max_c"] else "improving"
        else:
            trend = "decreasing" if metric in ["cpu_usage", "ram_usage_percent", "temp_max_c"] else "declining"

        # Special handling for health_score (higher is better)
        if metric == "health_score":
            trend = "improving" if change > 0 else ("declining" if change < 0 else "stable")
        # Special handling for disk_free_percent (higher is better)
        elif metric == "disk_free_percent":
            trend = "improving" if change > 0 else ("declining" if change < 0 else "stable")

        return {
            "current": current_value,
            "previous": previous_value,
            "change": round(change, 2),
            "trend_direction": trend,
        }

    def get_summary_stats(self) -> dict[str, Any]:
        """Get summary statistics from history."""
        records = self.get_history(limit=1000)
        if not records:
            return {"total_snapshots": 0}

        health_scores = [r.health_score for r in records if r.health_score is not None]
        cpu_usages = [r.cpu_usage for r in records]
        ram_usages = [r.ram_usage_percent for r in records]

        return {
            "total_snapshots": len(records),
            "first_snapshot": records[-1].timestamp if records else None,
            "last_snapshot": records[0].timestamp if records else None,
            "avg_health_score": sum(health_scores) / len(health_scores) if health_scores else None,
            "avg_cpu_usage": sum(cpu_usages) / len(cpu_usages) if cpu_usages else None,
            "avg_ram_usage": sum(ram_usages) / len(ram_usages) if ram_usages else None,
            "max_cpu_usage": max(cpu_usages) if cpu_usages else None,
            "max_ram_usage": max(ram_usages) if ram_usages else None,
        }

    def clear_history(self) -> bool:
        """Clear all snapshot history."""
        try:
            if self.history_file.exists():
                self.history_file.unlink()
            LOGGER.info("Snapshot history cleared")
            return True
        except Exception as e:
            LOGGER.exception("Failed to clear history: %s", e)
            return False
