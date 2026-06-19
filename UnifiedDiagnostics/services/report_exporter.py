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
        writer.writerow(["Section", "Key", "Value", "Detail", "State", "Persistence", "Error Code", "Basic Reason"])

        metadata = payload["metadata"]
        for key, value in metadata.items():
            writer.writerow(["Metadata", _label(key), value, "", "", "", "", ""])

        sections = payload["sections"]
        for section_name, rows in sections.items():
            for key, value in rows.items():
                writer.writerow([section_name, key, value, "", "", "", "", ""])

        for idx, finding in enumerate(payload["health"]["findings"], start=1):
            writer.writerow([
                f"Health Finding {idx}",
                finding["title"],
                finding["message"],
                finding.get("recommended_action", ""),
                finding.get("state", ""),
                finding.get("persistence", ""),
                "",
                "",
            ])

        for entry in payload.get("scan_logs", []):
            writer.writerow([
                "Scan Log",
                entry["task"],
                entry["status"],
                entry["message"],
                "",
                "",
                entry.get("error_code", ""),
                entry.get("basic_reason", ""),
            ])

        for issue in payload.get("diagnostic_report", []):
            writer.writerow([
                "Diagnostic Issue",
                issue["source"],
                issue["message"],
                issue.get("category", ""),
                issue.get("severity", ""),
                "",
                issue.get("error_code", ""),
                issue.get("basic_reason", ""),
            ])


def write_json_report(path: str, payload: dict[str, Any]) -> None:
    """Write a diagnostics report payload as JSON."""
    with open(path, "w", encoding="utf-8") as report_file:
        json.dump(payload, report_file, indent=2)


_STATUS_LEAD: dict[str, str] = {
    "ok": "Good news — no urgent problems were found on this PC.",
    "info": "This PC looks generally healthy. There are a few things worth knowing about.",
    "warning": "This PC has some warnings that are worth looking into when you have time.",
    "critical": "This PC has critical issues that should be addressed soon.",
}


def _plain_language_summary(payload: dict[str, Any]) -> str:
    """Build a friendly, non-technical summary block for the report header."""
    health = payload.get("health", {})
    status = str(health.get("overall_status") or "").lower()
    headline = str(health.get("headline") or "")
    score = health.get("score", "")
    rollup = str(health.get("severity_rollup") or "")
    findings = health.get("findings", [])

    lead = _STATUS_LEAD.get(status, "Here is a summary of your PC's current health.")
    score_line = f"Overall health score: <strong>{html.escape(str(score))}/100</strong>"
    if rollup:
        score_line += f" ({html.escape(rollup)})"

    items = []
    for finding in findings[:6]:
        title = html.escape(str(finding.get("title", "")))
        message = html.escape(str(finding.get("message", "")))
        action = html.escape(str(finding.get("recommended_action", "")))
        severity = html.escape(str(finding.get("severity", "")))
        action_html = f"<div class='action'><em>What to do:</em> {action}</div>" if action else ""
        items.append(
            f"<li class='finding sev-{severity}'><strong>{title}</strong> — {message}{action_html}</li>"
        )

    findings_html = f"<ul class='findings'>{''.join(items)}</ul>" if items else ""
    headline_html = f"<p class='headline'>{html.escape(headline)}</p>" if headline else ""

    return (
        "<section class='summary'>"
        "<h2>What's going on with your PC</h2>"
        f"<p class='lead'>{html.escape(lead)}</p>"
        f"{headline_html}"
        f"<p class='score'>{score_line}</p>"
        f"{findings_html}"
        "</section>"
    )


def write_html_report(path: str, payload: dict[str, Any]) -> None:
    """Write a diagnostics report payload as standalone HTML."""
    plain_summary = _plain_language_summary(payload)
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
        f"<td>{html.escape(entry.get('error_code', ''))}</td>"
        f"<td>{html.escape(entry.get('basic_reason', ''))}</td>"
        "</tr>"
        for entry in payload.get("scan_logs", [])
    )
    scan_block = ""
    if scan_rows:
        scan_block = (
            "<h2>Scan Logs</h2>"
            "<table><tr><th>Task</th><th>Status</th><th>Duration</th><th>Message</th><th>Error code</th><th>Basic reason</th></tr>"
            f"{scan_rows}</table>"
        )

    diagnostic_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(issue['source'])}</td>"
        f"<td>{html.escape(issue.get('category', ''))}</td>"
        f"<td>{html.escape(issue['message'])}</td>"
        f"<td>{html.escape(issue.get('severity', ''))}</td>"
        f"<td>{html.escape(issue.get('error_code', ''))}</td>"
        f"<td>{html.escape(issue.get('basic_reason', ''))}</td>"
        "</tr>"
        for issue in payload.get("diagnostic_report", [])
    )
    diagnostic_block = ""
    if diagnostic_rows:
        diagnostic_block = (
            "<h2>Diagnostic Issues</h2>"
            "<table><tr><th>Source</th><th>Category</th><th>Message</th><th>Severity</th><th>Error code</th><th>Basic reason</th></tr>"
            f"{diagnostic_rows}</table>"
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Master Sentinal Report</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; line-height: 1.45; color: #1f2937; }}
    h1, h2 {{ color: #1f2937; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    .score {{ font-size: 18px; font-weight: 700; }}
    .summary {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 10px; padding: 16px 20px; margin: 16px 0 28px; }}
    .summary .lead {{ font-size: 18px; font-weight: 600; margin: 4px 0; }}
    .summary .headline {{ color: #57606a; margin: 4px 0 12px; }}
    .findings {{ list-style: none; padding: 0; margin: 12px 0 0; }}
    .findings .finding {{ border-left: 4px solid #d0d7de; padding: 8px 12px; margin: 8px 0; background: #fff; border-radius: 0 6px 6px 0; }}
    .findings .sev-critical {{ border-left-color: #d93025; }}
    .findings .sev-warning {{ border-left-color: #f4b400; }}
    .findings .sev-info {{ border-left-color: #4f83cc; }}
    .findings .sev-ok {{ border-left-color: #2e8b57; }}
    .findings .action {{ margin-top: 4px; color: #57606a; }}
  </style>
</head>
<body>
  <h1>Master Sentinal Report</h1>
  {plain_summary}
  <h2>Metadata</h2>
  <table>{metadata_rows}</table>
  {section_blocks}
  <h2>Health Findings</h2>
  <table>
    <tr><th>Severity</th><th>Title</th><th>Message</th><th>Recommended action</th><th>State</th><th>Persistence</th></tr>
    {health_rows}
  </table>
  {diagnostic_block}
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
