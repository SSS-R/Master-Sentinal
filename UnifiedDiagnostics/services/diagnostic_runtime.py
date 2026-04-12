"""Shared runtime helpers for diagnostics and subprocess handling."""

from __future__ import annotations

import subprocess


def friendly_exception_message(exc: Exception, action: str) -> str:
    """Return a clearer user-facing message for a runtime exception."""
    if isinstance(exc, subprocess.TimeoutExpired):
        timeout = getattr(exc, "timeout", None)
        if timeout is not None:
            return f"{action} timed out after {int(timeout)} seconds."
        return f"{action} timed out."
    if isinstance(exc, FileNotFoundError):
        return f"{action} could not start because a required command or component was not found."
    if isinstance(exc, PermissionError):
        return f"{action} was denied by Windows. Try running the app as administrator."

    message = str(exc).strip()
    lowered = message.lower()
    if "access is denied" in lowered:
        return f"{action} was denied by Windows. Try running the app as administrator."
    if "invalid class" in lowered or "not found" in lowered and "wmi" in lowered:
        return f"{action} is unavailable because Windows management data is missing."
    if "rpc server is unavailable" in lowered:
        return f"{action} is unavailable because the Windows management service is not responding."
    if "json" in lowered and "decode" in lowered:
        return f"{action} returned unreadable output."
    return message or f"{action} failed."
