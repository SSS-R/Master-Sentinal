"""Event Viewer and Reliability Monitor diagnostics."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from typing import Any

from models.diagnostic_models import (
    EventLogEntry,
    EventLogSummary,
    ReliabilityRecord,
    ReliabilitySummary,
)
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class EventLogDiagnostic:
    """Gathers Event Viewer and Reliability Monitor health data."""

    def get_event_log_summary(self, lookback_days: int = 7) -> EventLogSummary:
        """Return summary of recent critical and error events."""
        try:
            critical_count, error_count, recent_events = self._query_event_logs(lookback_days)
            return EventLogSummary(
                critical_count=critical_count,
                error_count=error_count,
                lookback_days=lookback_days,
                recent_events=recent_events,
                error_message=None,
            )
        except Exception as e:
            LOGGER.exception("Event log summary failed: %s", e)
            return EventLogSummary(
                error_message=friendly_exception_message(e, "Event log summary"),
                lookback_days=lookback_days,
            )

    def _query_event_logs(self, lookback_days: int) -> tuple[int, int, list[EventLogEntry]]:
        """Query System and Application logs for critical/error events."""
        critical_count = 0
        error_count = 0
        recent_events: list[EventLogEntry] = []

        try:
            # Use wevtutil to query events
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            date_filter = cutoff_date.strftime("%Y-%m-%dT%H:%M:%S")

            for log_name in ["System", "Application"]:
                # Query critical events (Level 1-2)
                cmd = [
                    "wevtutil", "qe", log_name,
                    "/q:f", f"*[System[(Level=1 or Level=2) and TimeCreated[@SystemTime>='{date_filter}']]]",
                    "/c:10",  # Max 10 events per log
                    "/rd:true",  # Reverse order (newest first)
                    "/f:text",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )

                if result.returncode == 0:
                    events = self._parse_wevtutil_output(result.stdout, log_name)
                    for event in events:
                        if event.level in ["Critical", "Error"]:
                            recent_events.append(event)
                            if event.level == "Critical":
                                critical_count += 1
                            else:
                                error_count += 1

            return critical_count, error_count, recent_events[:10]  # Return max 10 total

        except subprocess.TimeoutExpired:
            LOGGER.warning("Event log query timed out")
            return 0, 0, []
        except Exception as e:
            LOGGER.warning("Event log query failed: %s", e)
            return 0, 0, []

    @staticmethod
    def _parse_wevtutil_output(output: str, log_name: str) -> list[EventLogEntry]:
        """Parse wevtutil text output into EventLogEntry objects."""
        events = []
        current_event = {}

        for line in output.splitlines():
            line = line.strip()
            if not line:
                if current_event:
                    events.append(
                        EventLogEntry(
                            log_name=log_name,
                            level=current_event.get("Level", "Unknown"),
                            provider=current_event.get("Provider", "Unknown"),
                            event_id=current_event.get("EventID"),
                            time_created=current_event.get("TimeCreated", ""),
                            message=current_event.get("Message", ""),
                        )
                    )
                    current_event = {}
                continue

            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                if key == "Level":
                    current_event["Level"] = {"1": "Critical", "2": "Error"}.get(value, "Unknown")
                elif key == "Provider Name":
                    current_event["Provider"] = value
                elif key == "EventID":
                    try:
                        current_event["EventID"] = int(value)
                    except ValueError:
                        current_event["EventID"] = None
                elif key == "TimeCreated":
                    current_event["TimeCreated"] = value
                elif key == "Message":
                    current_event["Message"] = value[:500]  # Truncate long messages

        return events

    def get_reliability_summary(self, lookback_days: int = 7) -> ReliabilitySummary:
        """Return summary of Reliability Monitor crash/hang data."""
        try:
            crash_count, hang_count, recent_records = self._query_reliability_data(lookback_days)
            return ReliabilitySummary(
                crash_count=crash_count,
                hang_count=hang_count,
                lookback_days=lookback_days,
                recent_records=recent_records,
                error_message=None,
            )
        except Exception as e:
            LOGGER.exception("Reliability summary failed: %s", e)
            return ReliabilitySummary(
                error_message=friendly_exception_message(e, "Reliability summary"),
                lookback_days=lookback_days,
            )

    def _query_reliability_data(self, lookback_days: int) -> tuple[int, int, list[ReliabilityRecord]]:
        """Query Reliability Monitor data via Event Viewer."""
        crash_count = 0
        hang_count = 0
        records: list[ReliabilityRecord] = []

        try:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            date_filter = cutoff_date.strftime("%Y-%m-%dT%H:%M:%S")

            # Query Application hang/crash events (Event ID 1001, 1002)
            cmd = [
                "wevtutil", "qe", "Application",
                "/q:f", f"*[System[(EventID=1001 or EventID=1002) and TimeCreated[@SystemTime>='{date_filter}']]]",
                "/c:20",
                "/rd:true",
                "/f:text",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "Faulting application name:" in line:
                        source = line.split(":")[-1].strip()
                        records.append(
                            ReliabilityRecord(
                                source_name=source,
                                product_name="",
                                event_id=1001,
                                time_generated="",
                                message=f"Application crash: {source}",
                            )
                        )
                        crash_count += 1

            # Also check for Windows Error Reporting events
            cmd = [
                "wevtutil", "qe", "System",
                "/q:f", f"*[System[(EventID=1001) and TimeCreated[@SystemTime>='{date_filter}']]]",
                "/c:10",
                "/rd:true",
                "/f:text",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode == 0 and "BugcheckCode" in result.stdout:
                # Blue screen detected
                records.append(
                    ReliabilityRecord(
                        source_name="Windows",
                        product_name="Windows",
                        event_id=1001,
                        time_generated="",
                        message="System blue screen (BSOD) detected",
                    )
                )
                crash_count += 1

            return crash_count, hang_count, records[:10]

        except subprocess.TimeoutExpired:
            LOGGER.warning("Reliability data query timed out")
            return 0, 0, []
        except Exception as e:
            LOGGER.warning("Reliability data query failed: %s", e)
            return 0, 0, []
