"""Summarize Windows ``powercfg /energy`` reports in plain language.

Windows' energy report is an *efficiency* audit aimed at laptop battery life. It
labels anything that reduces power efficiency as a red "Error" — even when the
setting is deliberate (e.g. a High Performance power plan on a desktop) or
universally harmless (e.g. a USB device not entering selective suspend). Surfacing
that raw file to a normal user is misleading: scary red "Errors" that are not
faults at all.

This module reads the generated report and produces an honest, non-technical
summary that reframes those entries as power-saving *suggestions* rather than
faults.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Class names used inside the powercfg HTML. The attribute value is emitted with
# embedded newlines/whitespace (``class="\n  error-log-entry\n  "``), so we
# normalize whitespace before matching.
_ERROR_CLASS = "error-log-entry"
_WARNING_CLASS = "warning-log-entry"
_INFO_CLASS = "info-log-entry"

# The human-readable entry title sits directly inside the header div, e.g.
# ``<div class="log-entry-header">Power Policy:Sleep timeout is disabled</div>``.
_NAME_RE = re.compile(r'log-entry-header">(.*?)</div>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# Plain-language descriptions keyed by the powercfg category (the text before the
# first colon in an entry name). These are the categories that account for the
# overwhelming majority of "Errors" on healthy desktop PCs.
_CATEGORY_FRIENDLY: dict[str, str] = {
    "USB Suspend": "USB device(s) not using power-saving suspend (very common, harmless)",
    "System Availability Requests": "app(s) were keeping the PC awake during the test",
    "Power Policy": "power plan favors performance over energy savings (normal on desktops)",
    "CPU Utilization": "the CPU was busy during the test (the scan itself uses the CPU)",
    "Processor Power Management": "processor power-saving options are reduced",
    "Platform Timer Resolution": "app(s) requested a high-resolution system timer",
    "Battery": "battery-related note — worth a look on laptops",
}

_MAX_DETAILS = 6


@dataclass(frozen=True)
class PowerSummary:
    """A plain-language summary of a Windows energy report."""

    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    headline: str = "Power efficiency check complete."
    details: list[str] = field(default_factory=list)

    @property
    def flagged_count(self) -> int:
        """Total entries Windows styled as errors or warnings."""
        return self.error_count + self.warning_count

    @property
    def friendly_text(self) -> str:
        """Full multi-line summary: headline followed by grouped details."""
        lines = [self.headline]
        if self.details:
            lines.append("")
            lines.extend(f"- {detail}" for detail in self.details)
        return "\n".join(lines)


def _strip_tags(value: str) -> str:
    return " ".join(_TAG_RE.sub(" ", value).split())


def _entry_names(html: str, class_name: str) -> list[str]:
    """Return the entry names for every block with the given log-entry class."""
    # Normalize whitespace inside class="..." so the class names match cleanly.
    normalized = re.sub(r'class="\s*([a-z0-9 _-]+?)\s*"', r'class="\1"', html)
    parts = re.split(
        r'<div class="(error-log-entry|warning-log-entry|info-log-entry)">',
        normalized,
    )
    names: list[str] = []
    # parts = [preamble, cls, content, cls, content, ...]
    for index in range(1, len(parts) - 1, 2):
        if parts[index] != class_name:
            continue
        match = _NAME_RE.search(parts[index + 1])
        if match:
            names.append(_strip_tags(match.group(1)))
    return names


def _friendly_details(names: list[str]) -> list[str]:
    """Group raw entry names into plain-language, de-duplicated lines."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for name in names:
        category = name.split(":", 1)[0].strip()
        friendly = _CATEGORY_FRIENDLY.get(category)
        if friendly is None:
            # Unknown category: keep the specific (cleaned) detail text.
            detail = name.split(":", 1)[-1].strip() or name
            friendly = detail
        if friendly not in counts:
            order.append(friendly)
        counts[friendly] = counts.get(friendly, 0) + 1

    details: list[str] = []
    for friendly in order[:_MAX_DETAILS]:
        count = counts[friendly]
        details.append(f"{count}x {friendly}" if count > 1 else friendly)
    remaining = len(order) - _MAX_DETAILS
    if remaining > 0:
        details.append(f"...and {remaining} more suggestion(s)")
    return details


def summarize_energy_report(path: str) -> PowerSummary:
    """Read a powercfg energy report and summarize it in plain language.

    Returns a :class:`PowerSummary`. If the file cannot be read, returns a
    neutral summary rather than raising — the scan should never fail because the
    *summary* could not be built.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as report_file:
            html = report_file.read()
    except OSError:
        return PowerSummary(headline="Power efficiency check complete (report unavailable).")

    errors = _entry_names(html, _ERROR_CLASS)
    warnings = _entry_names(html, _WARNING_CLASS)
    info = html.count(f'"{_INFO_CLASS}"') + html.count(f"{_INFO_CLASS}\n")

    flagged = len(errors) + len(warnings)
    if flagged == 0:
        headline = "Power efficiency check complete - no power-saving issues found."
    else:
        headline = (
            f"Power efficiency check complete - {flagged} power-saving suggestion(s) found. "
            "These are efficiency tips from Windows, not hardware faults "
            "(often normal on desktop PCs)."
        )

    details = _friendly_details(errors + warnings)

    return PowerSummary(
        error_count=len(errors),
        warning_count=len(warnings),
        info_count=max(info - 1, 0),  # subtract the CSS definition occurrence
        headline=headline,
        details=details,
    )
