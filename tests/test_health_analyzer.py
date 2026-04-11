"""Tests for live health analysis."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from models.diagnostic_models import (
    BackgroundServiceStatus,
    BitLockerVolumeStatus,
    DiskPartition,
    FirewallProfileStatus,
    GPUDevice,
    MemoryStats,
    SecurityHealth,
    SlowStartupService,
    SmartDriveStatus,
    StartupHealth,
    StartupItemStatus,
    SystemFormFactor,
)
from services.health_analyzer import HealthAnalyzer


def test_analyzer_reports_healthy_system_when_no_issues_found():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=18.0,
        ram=MemoryStats("16.00 GB", "9.00 GB", "7.00 GB", 42.0),
        gpus=[GPUDevice(name="RTX", temperature_text="65 C")],
        disks=[DiskPartition(mountpoint="C:\\", percent_text="55%")],
        smart=[SmartDriveStatus(key="disk0", display_text="Samsung SSD - OK")],
    )

    assert summary.overall_status == "ok"
    assert "No immediate issues" in summary.headline
    assert summary.health_score == 100
    assert summary.severity_rollup == "No issues"
    assert summary.findings[0].severity == "ok"
    assert summary.findings[0].recommended_action == "Keep monitoring normally."


def test_analyzer_flags_multiple_problem_types():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=97.0,
        ram=MemoryStats("16.00 GB", "1.00 GB", "15.00 GB", 92.0),
        gpus=[GPUDevice(name="RTX", temperature_text="91 C")],
        disks=[DiskPartition(mountpoint="C:\\", percent_text="96%")],
        smart=[SmartDriveStatus(key="disk0", display_text="Samsung SSD - Pred Fail")],
    )

    assert summary.overall_status == "critical"
    assert summary.health_score == 0
    assert summary.severity_rollup == "5 criticals"
    titles = [finding.title for finding in summary.findings]
    assert any("CPU load" in title for title in titles)
    assert any("Memory pressure" in title for title in titles)
    assert any("temperature is critical" in title for title in titles)
    assert any("almost full" in title for title in titles)
    assert any("drive failure risk" in title for title in titles)
    persistence_by_title = {finding.title: finding.persistence for finding in summary.findings}
    assert persistence_by_title["CPU load is extremely high"] == "snapshot"
    assert persistence_by_title["Memory pressure is critical"] == "snapshot"
    assert persistence_by_title["C:\\ is almost full"] == "persistent"
    assert persistence_by_title["SMART reported a drive failure risk"] == "persistent"


def test_analyzer_surfaces_diagnostic_errors_as_warnings():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=20.0,
        ram=MemoryStats("16.00 GB", "10.00 GB", "6.00 GB", 35.0),
        gpus=[GPUDevice(error_message="nvidia-smi missing")],
        disks=[],
        smart=[SmartDriveStatus(error_message="WMI unavailable")],
    )

    assert summary.overall_status == "warning"
    assert summary.health_score == 76
    assert summary.severity_counts["warning"] == 2
    assert any("diagnostics unavailable" in finding.title for finding in summary.findings)
    assert all(finding.recommended_action for finding in summary.findings)
    assert {finding.state for finding in summary.findings} == {"error", "unsupported"}


def test_analyzer_marks_unavailable_unsupported_diagnostics_explicitly():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=20.0,
        ram=MemoryStats("16.00 GB", "10.00 GB", "6.00 GB", 35.0),
        gpus=[GPUDevice(error_message="nvidia-smi not found")],
        disks=[],
        smart=[],
    )

    assert summary.overall_status == "warning"
    assert summary.findings[0].state == "unsupported"


def test_analyzer_uses_laptop_thermal_thresholds_to_reduce_false_positives():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=20.0,
        ram=MemoryStats("16.00 GB", "10.00 GB", "6.00 GB", 35.0),
        gpus=[GPUDevice(name="Laptop GPU", temperature_text="82 C")],
        disks=[],
        smart=[],
        system_form_factor=SystemFormFactor(device_type="laptop", has_battery=True),
    )

    assert summary.overall_status == "ok"
    assert not any("temperature" in finding.title for finding in summary.findings)


def test_analyzer_flags_security_protection_findings():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=20.0,
        ram=MemoryStats("16.00 GB", "10.00 GB", "6.00 GB", 35.0),
        gpus=[],
        disks=[],
        smart=[],
        security_health=SecurityHealth(
            defender_enabled=False,
            real_time_protection_enabled=False,
            firewall_profiles=[FirewallProfileStatus(name="Public", enabled=False)],
            bitlocker_volumes=[BitLockerVolumeStatus(mount_point="C:", protection_status="Off")],
        ),
    )

    titles = [finding.title for finding in summary.findings]
    assert summary.overall_status == "critical"
    assert summary.health_score == 16
    assert "Microsoft Defender antivirus is disabled" in titles
    assert "Defender real-time protection is disabled" in titles
    assert "Windows Firewall profile disabled" in titles
    assert "System drive BitLocker protection is off" in titles


def test_analyzer_surfaces_startup_and_service_findings_conservatively():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=20.0,
        ram=MemoryStats("16.00 GB", "10.00 GB", "6.00 GB", 35.0),
        gpus=[],
        disks=[],
        smart=[],
        startup_health=StartupHealth(
            startup_items=[StartupItemStatus(name=f"app-{index}") for index in range(20)],
            slow_startup_services=[SlowStartupService(service_name="SlowSvc", startup_time_ms=12000)],
            automatic_services=[
                BackgroundServiceStatus(name=f"svc-{index}", state="Stopped", delayed_auto_start=False)
                for index in range(10)
            ],
        ),
    )

    titles = [finding.title for finding in summary.findings]
    assert summary.overall_status == "warning"
    assert summary.health_score == 82
    assert "Slow startup services detected" in titles
    assert "Many startup items are enabled" in titles
    assert "Several automatic services are stopped" in titles
    assert all(finding.recommended_action for finding in summary.findings)
