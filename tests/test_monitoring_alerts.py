"""Tests for GPU temperature alerting and the GPUDevice temperature parser."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from models.diagnostic_models import GPUDevice
from services.monitoring_alerts import AlertConfig, AlertSeverity, MonitoringAlerts


def test_gpu_temperature_c_parses_text():
    assert GPUDevice(temperature_text="74 C").temperature_c == 74.0
    assert GPUDevice(temperature_text="81").temperature_c == 81.0
    assert GPUDevice(temperature_text="N/A").temperature_c is None
    assert GPUDevice(temperature_text="").temperature_c is None


def test_hot_gpu_triggers_critical_alert():
    alerts = MonitoringAlerts(AlertConfig(temp_warning_c=85, temp_critical_c=92))
    fired = []
    alerts.add_alert_callback(fired.append)
    alerts.set_temperature_provider(lambda: [("RTX 3060 Ti", 95.0)])

    alerts._check_temperature()

    assert len(fired) == 1
    assert fired[0].severity == AlertSeverity.CRITICAL
    assert fired[0].alert_type == "temperature"
    assert "RTX 3060 Ti" in fired[0].title


def test_cool_gpu_triggers_nothing():
    alerts = MonitoringAlerts(AlertConfig(temp_warning_c=85, temp_critical_c=92))
    fired = []
    alerts.add_alert_callback(fired.append)
    alerts.set_temperature_provider(lambda: [("GPU", 65.0)])

    alerts._check_temperature()

    assert fired == []


def test_repeated_hot_reading_deduped_within_window():
    alerts = MonitoringAlerts(AlertConfig(temp_warning_c=85, temp_critical_c=92))
    fired = []
    alerts.add_alert_callback(fired.append)
    alerts.set_temperature_provider(lambda: [("GPU", 95.0)])

    alerts._check_temperature()
    alerts._check_temperature()  # within dedup window -> suppressed

    assert len(fired) == 1


def test_no_provider_is_safe():
    alerts = MonitoringAlerts()
    fired = []
    alerts.add_alert_callback(fired.append)
    # No provider registered -> must not raise and must not alert.
    alerts._check_temperature()
    assert fired == []
