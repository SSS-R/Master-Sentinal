"""Background monitoring with alerts - temperature and disk space monitoring."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

import psutil

from services.app_logging import get_logger


LOGGER = get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class MonitoringAlert:
    """One monitoring alert."""

    timestamp: str
    severity: AlertSeverity
    alert_type: str
    title: str
    message: str
    value: float | None = None
    threshold: float | None = None


@dataclass
class AlertConfig:
    """Configuration for monitoring alerts."""

    temp_warning_c: float = 70.0
    temp_critical_c: float = 85.0
    disk_warning_percent: float = 15.0  # Warn when free space below 15%
    disk_critical_percent: float = 5.0  # Critical when free space below 5%
    ram_warning_percent: float = 85.0
    ram_critical_percent: float = 95.0
    cpu_sustained_warning_percent: float = 90.0  # If CPU stays above this for N seconds


class MonitoringAlerts:
    """Background monitoring with configurable alerts."""

    def __init__(self, config: AlertConfig | None = None):
        """Initialize monitoring alerts."""
        self.config = config or AlertConfig()
        self.alerts: list[MonitoringAlert] = []
        self.alert_callbacks: list[Callable[[MonitoringAlert], None]] = []
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self._check_interval = 30  # seconds
        self._cpu_sustained_start: float | None = None

    def add_alert_callback(self, callback: Callable[[MonitoringAlert], None]) -> None:
        """Add a callback to be called when an alert is triggered."""
        self.alert_callbacks.append(callback)

    def start_monitoring(self, check_interval: int = 30) -> None:
        """Start background monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._check_interval = check_interval
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        LOGGER.info("Background monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None
        LOGGER.info("Background monitoring stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                self._check_temperature()
                self._check_disk_space()
                self._check_memory()
                self._check_cpu_sustained()
            except Exception as e:
                LOGGER.exception("Monitoring loop error: %s", e)

            time.sleep(self._check_interval)

    def _check_temperature(self) -> None:
        """Check system temperatures."""
        try:
            # Note: psutil doesn't directly expose CPU temp on Windows
            # We rely on the diagnostic modules for this
            # This is a placeholder for integration with the GPU/CPU modules
            temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}

            # Windows typically doesn't expose sensors via psutil
            # Integration point: call into cpu_diag/gpu_diag for temp data
            pass

        except Exception as e:
            LOGGER.debug("Temperature check skipped: %s", e)

    def _check_disk_space(self) -> None:
        """Check disk space on all partitions."""
        try:
            for partition in psutil.disk_partitions(all=True):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    free_percent = (usage.free / usage.total) * 100

                    if free_percent < self.config.disk_critical_percent:
                        self._trigger_alert(
                            MonitoringAlert(
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                severity=AlertSeverity.CRITICAL,
                                alert_type="disk_space",
                                title=f"Critical: Low disk space on {partition.mountpoint}",
                                message=f"Only {free_percent:.1f}% free ({usage.free / (1024**3):.1f} GB)",
                                value=free_percent,
                                threshold=self.config.disk_critical_percent,
                            )
                        )
                    elif free_percent < self.config.disk_warning_percent:
                        self._trigger_alert(
                            MonitoringAlert(
                                timestamp=datetime.now(timezone.utc).isoformat(),
                                severity=AlertSeverity.WARNING,
                                alert_type="disk_space",
                                title=f"Warning: Low disk space on {partition.mountpoint}",
                                message=f"Only {free_percent:.1f}% free ({usage.free / (1024**3):.1f} GB)",
                                value=free_percent,
                                threshold=self.config.disk_warning_percent,
                            )
                        )
                except (PermissionError, OSError):
                    # Skip inaccessible drives
                    continue

        except Exception as e:
            LOGGER.debug("Disk space check error: %s", e)

    def _check_memory(self) -> None:
        """Check memory usage."""
        try:
            mem = psutil.virtual_memory()

            if mem.percent >= self.config.ram_critical_percent:
                self._trigger_alert(
                    MonitoringAlert(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        severity=AlertSeverity.CRITICAL,
                        alert_type="memory",
                        title="Critical: High memory usage",
                        message=f"Memory usage at {mem.percent:.1f}% ({mem.available / (1024**3):.1f} GB available)",
                        value=mem.percent,
                        threshold=self.config.ram_critical_percent,
                    )
                )
            elif mem.percent >= self.config.ram_warning_percent:
                self._trigger_alert(
                    MonitoringAlert(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        severity=AlertSeverity.WARNING,
                        alert_type="memory",
                        title="Warning: High memory usage",
                        message=f"Memory usage at {mem.percent:.1f}%",
                        value=mem.percent,
                        threshold=self.config.ram_warning_percent,
                    )
                )
        except Exception as e:
            LOGGER.debug("Memory check error: %s", e)

    def _check_cpu_sustained(self) -> None:
        """Check for sustained high CPU usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)

            if cpu_percent >= self.config.cpu_sustained_warning_percent:
                if self._cpu_sustained_start is None:
                    self._cpu_sustained_start = time.time()
                elif time.time() - self._cpu_sustained_start > 60:  # 1 minute sustained
                    self._trigger_alert(
                        MonitoringAlert(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            severity=AlertSeverity.WARNING,
                            alert_type="cpu_sustained",
                            title="Warning: Sustained high CPU usage",
                            message=f"CPU usage has been above {self.config.cpu_sustained_warning_percent}% for over 1 minute",
                            value=cpu_percent,
                            threshold=self.config.cpu_sustained_warning_percent,
                        )
                    )
                    self._cpu_sustained_start = None  # Reset after alert
            else:
                self._cpu_sustained_start = None

        except Exception as e:
            LOGGER.debug("CPU sustained check error: %s", e)

    def _trigger_alert(self, alert: MonitoringAlert) -> None:
        """Trigger an alert and notify callbacks."""
        # Avoid duplicate alerts within a short window
        recent_duplicates = [
            a for a in self.alerts
            if a.alert_type == alert.alert_type and a.title == alert.title
        ]
        if recent_duplicates:
            return

        self.alerts.append(alert)
        LOGGER.warning(f"Alert triggered: {alert.title}")

        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                LOGGER.exception("Alert callback error: %s", e)

    def get_recent_alerts(self, limit: int = 50) -> list[MonitoringAlert]:
        """Get recent alerts."""
        return self.alerts[-limit:]

    def clear_alerts(self) -> None:
        """Clear all alerts."""
        self.alerts.clear()

    def get_alert_summary(self) -> dict[str, int]:
        """Get count of alerts by severity."""
        summary = {
            "info": 0,
            "warning": 0,
            "critical": 0,
        }
        for alert in self.alerts:
            summary[alert.severity.value] += 1
        return summary
