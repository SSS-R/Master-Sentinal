"""Tests for live health analysis."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from models.diagnostic_models import DiskPartition, GPUDevice, MemoryStats, SmartDriveStatus
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
    assert summary.findings[0].severity == "ok"


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
    titles = [finding.title for finding in summary.findings]
    assert any("CPU load" in title for title in titles)
    assert any("Memory pressure" in title for title in titles)
    assert any("temperature is critical" in title for title in titles)
    assert any("almost full" in title for title in titles)
    assert any("drive failure risk" in title for title in titles)


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
    assert any("diagnostics unavailable" in finding.title for finding in summary.findings)
