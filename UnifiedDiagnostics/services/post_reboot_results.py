"""Read results of scans that only complete after a restart.

The Windows Memory Diagnostic (``mdsched.exe``) and similar tools cannot report
back inside the same app session: they run during a reboot and write their
outcome to the Windows Event Log afterwards. Master Sentinal launches them, then
has no result to show — which reads as "nothing happened."

This service closes that loop. After a reboot it reads the
``Microsoft-Windows-MemoryDiagnostics-Results`` provider from the System log and
returns the most recent outcome in plain language, so the Full Scan screen can
display "Last memory test: no errors found (2 hours ago)" without the user
hunting through Event Viewer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message, run_powershell

LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class MemoryDiagnosticResult:
    """The most recent Windows Memory Diagnostic outcome from the Event Log."""

    found: bool = False
    passed: bool | None = None
    time_created: str = ""
    message: str = ""
    error: str = ""

    @property
    def headline(self) -> str:
        """A short, plain-language summary suitable for a status label."""
        if self.error:
            return f"Could not read memory test results: {self.error}"
        if not self.found:
            return "No memory test results found yet. Run the Memory Diagnostic, then restart."
        if self.passed is True:
            return "Last memory test: no errors detected."
        if self.passed is False:
            return "Last memory test: MEMORY ERRORS DETECTED - back up your data and contact support."
        return "Last memory test completed (see details)."


class PostRebootResultReader:
    """Reads post-reboot diagnostic outcomes from the Windows Event Log."""

    def get_memory_diagnostic_result(self) -> MemoryDiagnosticResult:
        """Return the latest Windows Memory Diagnostic result, if any."""
        try:
            result = run_powershell(self._memory_script(), timeout=15)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return MemoryDiagnosticResult(error=error)
            if not output or output == "null":
                return MemoryDiagnosticResult(found=False)

            payload = json.loads(output)
            message = str(payload.get("Message") or "").strip()
            return MemoryDiagnosticResult(
                found=True,
                passed=self._infer_passed(message, payload.get("EventId")),
                time_created=str(payload.get("TimeCreated") or ""),
                message=message,
            )
        except Exception as exc:
            LOGGER.warning("Reading memory diagnostic result failed: %s", exc)
            return MemoryDiagnosticResult(error=friendly_exception_message(exc, "Memory diagnostic results"))

    @staticmethod
    def _infer_passed(message: str, event_id: object) -> bool | None:
        """Decide pass/fail from the result message text (event 1201/1101)."""
        text = message.lower()
        if "no errors" in text or "did not detect" in text or "no problems" in text:
            return True
        if "error" in text or "problem" in text or "detected" in text:
            return False
        return None

    @staticmethod
    def _memory_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "$event = Get-WinEvent -FilterHashtable @{\n"
            "    LogName='System'; ProviderName='Microsoft-Windows-MemoryDiagnostics-Results'\n"
            "} -MaxEvents 1 -ErrorAction SilentlyContinue\n"
            "if ($null -eq $event) { 'null' }\n"
            "else {\n"
            "    [pscustomobject]@{\n"
            "        EventId = $event.Id\n"
            "        TimeCreated = if ($event.TimeCreated) { $event.TimeCreated.ToString('o') } else { '' }\n"
            "        Message = ($event.Message -replace '\\s+', ' ').Trim()\n"
            "    } | ConvertTo-Json -Compress\n"
            "}\n"
        )
