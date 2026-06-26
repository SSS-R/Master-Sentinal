"""Tests for the plain-language powercfg energy report summarizer."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.power_report import summarize_energy_report


def _entry(cls: str, name: str) -> str:
    # Mirrors powercfg's structure: the class attribute carries embedded
    # whitespace, and the title sits directly inside the header div.
    return (
        f'<div class="\n\n   {cls}\n   ">'
        f'<div class="log-entry-header">{name}</div>'
        '<div class="log-entry-content">details</div>'
        "</div>"
    )


def _report(*entries: str) -> str:
    style = (
        "<style>.error-log-entry{}.warning-log-entry{}.info-log-entry{}</style>"
    )
    return f"<html><head>{style}</head><body>{''.join(entries)}</body></html>"


def _write(tmp_path, html: str) -> str:
    path = os.path.join(str(tmp_path), "energy.html")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return path


def test_counts_errors_and_warnings(tmp_path):
    html = _report(
        _entry("error-log-entry", "USB Suspend:USB Device not Entering Selective Suspend"),
        _entry("error-log-entry", "USB Suspend:USB Device not Entering Selective Suspend"),
        _entry("error-log-entry", "Power Policy:Power Plan Personality is High Performance (Plugged In)"),
        _entry("warning-log-entry", "Power Policy:Display timeout is long (Plugged In)"),
    )
    summary = summarize_energy_report(_write(tmp_path, html))
    assert summary.error_count == 3
    assert summary.warning_count == 1
    assert summary.flagged_count == 4


def test_headline_reframes_errors_as_suggestions(tmp_path):
    html = _report(
        _entry("error-log-entry", "USB Suspend:USB Device not Entering Selective Suspend"),
    )
    summary = summarize_energy_report(_write(tmp_path, html))
    # Must NOT call these "errors" or "faults" — that is the misleading framing.
    assert "suggestion" in summary.headline.lower()
    assert "not hardware faults" in summary.headline.lower()


def test_clean_report_says_no_issues(tmp_path):
    summary = summarize_energy_report(_write(tmp_path, _report()))
    assert summary.flagged_count == 0
    assert "no power-saving issues" in summary.headline.lower()


def test_duplicates_are_grouped_with_count(tmp_path):
    html = _report(
        *[_entry("error-log-entry", "USB Suspend:USB Device not Entering Selective Suspend")] * 5
    )
    summary = summarize_energy_report(_write(tmp_path, html))
    joined = " ".join(summary.details)
    assert "5x" in joined
    assert "USB" in joined


def test_missing_file_returns_neutral_summary():
    summary = summarize_energy_report(r"Z:\does\not\exist\energy.html")
    assert summary.flagged_count == 0
    assert "complete" in summary.headline.lower()
