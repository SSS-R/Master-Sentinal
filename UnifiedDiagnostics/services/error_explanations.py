"""Helpers for attaching plain-language reasons to known Windows error codes."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorExplanation:
    """A compact error-code explanation suitable for exports and logs."""

    error_code: str = ""
    basic_reason: str = ""


_EXACT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        "0x800f081f",
        "0x800F081F",
        "Windows could not find the repair source files it needs to complete the scan.",
    ),
    (
        "0x800f0906",
        "0x800F0906",
        "Windows could not download the repair files, usually because update access is blocked or unavailable.",
    ),
    (
        "error: 87",
        "87",
        "The command was run with an invalid parameter or unsupported syntax.",
    ),
    (
        "error 87",
        "87",
        "The command was run with an invalid parameter or unsupported syntax.",
    ),
    (
        "error: 3017",
        "3017",
        "Windows has a pending restart from an earlier repair or update, so this scan cannot continue yet.",
    ),
    (
        "error 3017",
        "3017",
        "Windows has a pending restart from an earlier repair or update, so this scan cannot continue yet.",
    ),
    (
        "0x10d2",
        "0x10D2",
        "The battery report only works when Windows detects a battery, so this system is likely a desktop or has no battery available.",
    ),
)

_DRIVER_CODE_REASONS: dict[str, str] = {
    "1": "The device is not configured correctly, usually because its driver or settings are incomplete.",
    "3": "The device driver reported a problem and may be corrupted or incompatible.",
    "10": "Windows started the device, but the device could not initialize successfully.",
    "12": "Windows could not assign enough hardware resources to the device.",
    "14": "The device needs a restart before it can work normally again.",
    "16": "Windows could not identify all of the resources the device needs.",
    "18": "The device driver needs to be reinstalled.",
    "19": "The device configuration in the registry may be damaged.",
    "21": "Windows is removing the device and it is not ready yet.",
    "22": "The device is disabled in Windows.",
    "24": "The device is missing, disconnected, or not working properly.",
    "25": "Windows is still setting up the device.",
    "28": "A required driver is missing, so Windows cannot use the device.",
    "29": "The device was disabled by firmware or BIOS settings.",
    "31": "Windows loaded the driver, but the device is still not working properly.",
    "32": "The device service or driver is disabled.",
    "33": "Windows could not determine which hardware resources the device needs.",
    "34": "The device is using a conflicting hardware setting such as an IRQ.",
    "37": "Windows could not initialize the device driver.",
    "39": "Windows could not load the device driver, often because it is corrupted.",
    "41": "Windows loaded a driver entry, but cannot find the physical device.",
    "42": "Windows detected a duplicate device instance and cannot load this one.",
    "43": "The device stopped because the hardware or driver reported a serious problem.",
    "44": "An application or service shut down the device because it reported problems.",
    "45": "The device is not currently connected to the computer.",
    "52": "Windows cannot verify the driver's digital signature.",
}


def explain_error_message(message: str) -> ErrorExplanation:
    """Return a short reason for a known scan or device-manager error message."""
    if not message:
        return ErrorExplanation()

    lowered = message.lower()

    if "administrator privileges required" in lowered or "access is denied" in lowered or "error: 5" in lowered:
        return ErrorExplanation(
            error_code="5" if "error: 5" in lowered or "access is denied" in lowered else "",
            basic_reason="The scan needs Administrator permissions and could not access the required system components.",
        )

    if "timed out" in lowered:
        return ErrorExplanation(
            basic_reason="The check took longer than the allowed time, often because the system was busy or the repair was still running.",
        )

    if "not a laptop" in lowered or "no battery" in lowered:
        return ErrorExplanation(
            error_code="0x10D2" if "0x10d2" in lowered else "",
            basic_reason="This check depends on battery hardware, but Windows did not detect a battery on this system.",
        )

    for token, error_code, basic_reason in _EXACT_PATTERNS:
        if token in lowered:
            return ErrorExplanation(error_code=error_code, basic_reason=basic_reason)

    driver_match = re.search(r"\b(?:code|error code|error)\s*[:(]?\s*(\d+)\)?\b", lowered)
    if driver_match:
        error_code = driver_match.group(1)
        if error_code in _DRIVER_CODE_REASONS:
            return ErrorExplanation(error_code=error_code, basic_reason=_DRIVER_CODE_REASONS[error_code])
        return ErrorExplanation(
            error_code=error_code,
            basic_reason="Windows reported an error code here, but this build does not have a plain-language reason mapped for it yet.",
        )

    return ErrorExplanation()
