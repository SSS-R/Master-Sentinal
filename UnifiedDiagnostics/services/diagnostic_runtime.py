"""Shared runtime helpers for diagnostics and subprocess handling."""

from __future__ import annotations

import os
import subprocess


def _creation_flags() -> int:
    """Return flags that hide the console window on Windows."""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _is_admin() -> bool:
    """Return True if the current process is elevated (best effort)."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _access_denied_message(action: str) -> str:
    """Return an accurate access-denied message based on elevation state.

    Telling an already-elevated user to "run as administrator" is misleading
    (a real complaint): when we are already admin, the resource is locked or
    simply not exposed by Windows, not under-privileged.
    """
    if _is_admin():
        return (
            f"{action} was blocked by Windows even with administrator rights - "
            "the resource is locked or not available on this system."
        )
    return f"{action} was denied by Windows. Try running the app as administrator."


def run_powershell(script: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Run a PowerShell script and capture UTF-8 output reliably.

    Forces UTF-8 on both ends: PowerShell is told to emit UTF-8 and Python
    decodes as UTF-8 with replacement. Without this, output containing
    non-ASCII text (device names, service display names, localized event
    messages) is decoded with the machine's ANSI codepage and can corrupt or
    raise ``UnicodeDecodeError`` — a failure that only shows up on other
    machines (different locale), never on the developer's English install.
    """
    full_script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n" + script
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            full_script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_creation_flags(),
    )


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
        return _access_denied_message(action)

    message = str(exc).strip()
    lowered = message.lower()
    if "access is denied" in lowered:
        return _access_denied_message(action)
    if "invalid class" in lowered or "not found" in lowered and "wmi" in lowered:
        return f"{action} is unavailable because Windows management data is missing."
    if "rpc server is unavailable" in lowered:
        return f"{action} is unavailable because the Windows management service is not responding."
    if "json" in lowered and "decode" in lowered:
        return f"{action} returned unreadable output."
    return message or f"{action} failed."
