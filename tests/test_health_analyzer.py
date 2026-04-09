"""Tests for live health analysis."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.health_analyzer import HealthAnalyzer


def test_analyzer_reports_healthy_system_when_no_issues_found():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=18.0,
        ram={"Percentage": 42.0},
        gpus=[{"Name": "RTX", "Temperature": "65 C"}],
        disks=[{"Mountpoint": "C:\\", "Percent": "55%"}],
        smart={"disk0": "Samsung SSD - OK"},
    )

    assert summary.overall_status == "ok"
    assert "No immediate issues" in summary.headline
    assert summary.findings[0].severity == "ok"


def test_analyzer_flags_multiple_problem_types():
    analyzer = HealthAnalyzer()

    summary = analyzer.analyze(
        cpu_load=97.0,
        ram={"Percentage": 92.0},
        gpus=[{"Name": "RTX", "Temperature": "91 C"}],
        disks=[{"Mountpoint": "C:\\", "Percent": "96%"}],
        smart={"disk0": "Samsung SSD - Pred Fail"},
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
        ram={"Percentage": 35.0},
        gpus=[{"Error": "nvidia-smi missing"}],
        disks=[],
        smart={"Error": "WMI unavailable"},
    )

    assert summary.overall_status == "warning"
    assert any("diagnostics unavailable" in finding.title for finding in summary.findings)
