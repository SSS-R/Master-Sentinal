"""Redaction helpers for anonymizing exported diagnostic data.

Diagnostic bundles and reports are often shared publicly (GitHub issues,
forums). They can carry personal data: the Windows username embedded in file
paths, the PC's hostname, and hardware serial numbers. These helpers scrub that
data so a user can safely share a bundle without leaking who or which machine it
came from.

Over-redaction is preferred to under-redaction: matching is case-insensitive and
key-based redaction is applied to anything that looks like a serial number.
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from typing import Any

# Dict keys whose values are scrubbed outright (structured data).
_SENSITIVE_KEY_TOKENS = ("serial", "serialnumber", "serial_number", "uuid")

# Shortest sensitive literal we will substitute. Avoids over-matching very short
# usernames/hostnames that could appear as substrings of unrelated words.
_MIN_TOKEN_LEN = 3

Replacements = list[tuple[str, str]]


def build_replacements() -> Replacements:
    """Return ordered (literal, placeholder) pairs for the current machine.

    Most specific literals (the full user-profile path) come first so they are
    replaced before the bare username they contain.
    """
    user_profile = os.environ.get("USERPROFILE") or str(Path.home())
    username = os.environ.get("USERNAME") or ""
    hostname = platform.node() or os.environ.get("COMPUTERNAME") or ""

    candidates: Replacements = [
        (user_profile, r"C:\Users\[USER]"),
        (username, "[USER]"),
        (hostname, "[HOST]"),
    ]
    return [(literal, placeholder) for literal, placeholder in candidates if len(literal) >= _MIN_TOKEN_LEN]


def redact_text(text: str, replacements: Replacements | None = None) -> str:
    """Replace machine-identifying literals in *text* with placeholders."""
    if not text:
        return text
    repls = build_replacements() if replacements is None else replacements
    for literal, placeholder in repls:
        # Use a replacement *function* so backslashes in the placeholder (e.g.
        # ``C:\Users\[USER]``) are treated literally rather than as regex escapes.
        text = re.sub(re.escape(literal), lambda _match, value=placeholder: value, text, flags=re.IGNORECASE)
    return text


def _redact_value(value: Any, replacements: Replacements) -> Any:
    if isinstance(value, str):
        return redact_text(value, replacements)
    if isinstance(value, dict):
        return _redact_mapping(value, replacements)
    if isinstance(value, list):
        return [_redact_value(item, replacements) for item in value]
    return value


def _redact_mapping(obj: dict[Any, Any], replacements: Replacements) -> dict[Any, Any]:
    redacted: dict[Any, Any] = {}
    for key, value in obj.items():
        if isinstance(key, str) and any(token in key.lower() for token in _SENSITIVE_KEY_TOKENS):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = _redact_value(value, replacements)
    return redacted


def redact_obj(obj: Any) -> Any:
    """Return a deep copy of *obj* with personal data scrubbed.

    Strings are scrubbed for username/hostname/profile path; dict values under
    serial-number-like keys are replaced wholesale.
    """
    return _redact_value(obj, build_replacements())
