"""Tests for the redaction helpers used by anonymized bundle export."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from services.redaction import build_replacements, redact_obj, redact_text


def test_redact_text_scrubs_username():
    replacements = [(r"C:\Users\alice", r"C:\Users\[USER]"), ("alice", "[USER]")]
    text = r"Log written to C:\Users\alice\AppData and run by alice"
    result = redact_text(text, replacements)
    assert "alice" not in result
    assert "[USER]" in result


def test_redact_text_is_case_insensitive():
    replacements = [("workstation7", "[HOST]")]
    assert redact_text("Host WORKSTATION7 online", replacements) == "Host [HOST] online"


def test_redact_obj_masks_serial_keys():
    payload = {
        "System": {
            "Serial Number": "ABC-123-XYZ",
            "manufacturer": "Acme",
        },
        "items": [{"serial_number": "55-99"}],
    }
    result = redact_obj(payload)
    assert result["System"]["Serial Number"] == "[REDACTED]"
    assert result["System"]["manufacturer"] == "Acme"
    assert result["items"][0]["serial_number"] == "[REDACTED]"


def test_build_replacements_returns_pairs():
    # Should not raise and should return a list of (literal, placeholder) tuples.
    pairs = build_replacements()
    assert isinstance(pairs, list)
    for literal, placeholder in pairs:
        assert isinstance(literal, str)
        assert isinstance(placeholder, str)
