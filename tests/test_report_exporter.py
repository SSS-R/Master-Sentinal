"""Tests for report serialization helpers."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.report_exporter import write_html_report, write_json_report


def test_json_report_writes_bug_report_payload(tmp_path):
    payload = _payload()
    path = tmp_path / "report.json"

    write_json_report(str(path), payload)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["metadata"]["app_version"] == "test"
    assert loaded["health"]["findings"][0]["recommended_action"] == "Run updates"


def test_html_report_includes_health_actions(tmp_path):
    payload = _payload()
    path = tmp_path / "report.html"

    write_html_report(str(path), payload)

    html = path.read_text(encoding="utf-8")
    assert "Health score" in html
    assert "Run updates" in html


def _payload():
    return {
        "metadata": {
            "app_name": "Master Sentinal",
            "app_version": "test",
            "generated_at": "2026-04-12T00:00:00+00:00",
            "os": "Windows",
            "running_as_admin": False,
        },
        "sections": {"CPU": {"Usage": "1%"}},
        "health": {
            "score": 88,
            "findings": [
                {
                    "severity": "warning",
                    "title": "Windows Update services are disabled",
                    "message": "BITS is disabled.",
                    "recommended_action": "Run updates",
                    "state": "warning",
                    "persistence": "persistent",
                }
            ],
        },
        "scan_logs": [
            {
                "task": "SFC",
                "status": "success",
                "duration": "1.0s",
                "message": "No Integrity Violations",
            }
        ],
    }
