"""Report serialization helpers for diagnostics exports."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def write_csv_report(path: str, payload: dict[str, Any]) -> None:
    """Write a diagnostics report payload as CSV."""
    with open(path, "w", newline="", encoding="utf-8") as report_file:
        writer = csv.writer(report_file)
        writer.writerow(["Section", "Key", "Value", "Detail", "State", "Persistence"])

        metadata = payload["metadata"]
        for key, value in metadata.items():
            writer.writerow(["Metadata", _label(key), value])

        sections = payload["sections"]
        for section_name, rows in sections.items():
            for key, value in rows.items():
                writer.writerow([section_name, key, value])

        for idx, finding in enumerate(payload["health"]["findings"], start=1):
            writer.writerow([
                f"Health Finding {idx}",
                finding["title"],
                finding["message"],
                finding.get("recommended_action", ""),
                finding.get("state", ""),
                finding.get("persistence", ""),
            ])

        for entry in payload.get("scan_logs", []):
            writer.writerow([
                "Scan Log",
                entry["task"],
                entry["status"],
                entry["message"],
                "",
                "",
            ])


def write_json_report(path: str, payload: dict[str, Any]) -> None:
    """Write a diagnostics report payload as JSON."""
    with open(path, "w", encoding="utf-8") as report_file:
        json.dump(payload, report_file, indent=2)


def write_html_report(path: str, payload: dict[str, Any]) -> None:
    """Write a diagnostics report payload as standalone HTML."""
    metadata_rows = _table_rows(payload["metadata"])
    section_blocks = "\n".join(
        f"<h2>{html.escape(section_name)}</h2><table>{_table_rows(rows)}</table>"
        for section_name, rows in payload["sections"].items()
    )
    health_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(finding['severity'])}</td>"
        f"<td>{html.escape(finding['title'])}</td>"
        f"<td>{html.escape(finding['message'])}</td>"
        f"<td>{html.escape(finding.get('recommended_action', ''))}</td>"
        f"<td>{html.escape(finding.get('state', ''))}</td>"
        f"<td>{html.escape(finding.get('persistence', ''))}</td>"
        "</tr>"
        for finding in payload["health"]["findings"]
    )
    scan_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(entry['task'])}</td>"
        f"<td>{html.escape(entry['status'])}</td>"
        f"<td>{html.escape(entry['duration'])}</td>"
        f"<td>{html.escape(entry['message'])}</td>"
        "</tr>"
        for entry in payload.get("scan_logs", [])
    )
    scan_block = ""
    if scan_rows:
        scan_block = (
            "<h2>Scan Logs</h2>"
            "<table><tr><th>Task</th><th>Status</th><th>Duration</th><th>Message</th></tr>"
            f"{scan_rows}</table>"
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Master Sentinal Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; line-height: 1.45; }}
    h1, h2 {{ color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .score {{ font-size: 18px; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Master Sentinal Report</h1>
  <p class="score">Health score: {html.escape(str(payload["health"].get("score", "")))}/100</p>
  <h2>Metadata</h2>
  <table>{metadata_rows}</table>
  {section_blocks}
  <h2>Health Findings</h2>
  <table>
    <tr><th>Severity</th><th>Title</th><th>Message</th><th>Recommended action</th><th>State</th><th>Persistence</th></tr>
    {health_rows}
  </table>
  {scan_block}
</body>
</html>
"""
    Path(path).write_text(document, encoding="utf-8")


def _table_rows(rows: dict[str, Any]) -> str:
    return "\n".join(
        f"<tr><th>{html.escape(_label(str(key)))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in rows.items()
    )


def _label(value: str) -> str:
    return value.replace("_", " ").title()
