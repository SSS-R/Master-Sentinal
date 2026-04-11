"""Unit tests for BoardDiagnostic."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from modules.board_diag import BoardDiagnostic


class TestBoardDiagnostic:
    """Tests for BoardDiagnostic methods."""

    def test_get_board_details_returns_typed_model(self, mock_wmi):
        diag = BoardDiagnostic()
        info = diag.get_board_details()

        assert info.manufacturer == "ASUS"
        assert info.product == "ROG STRIX Z690"
        assert info.serial_number == "ABC123"
        assert info.bios_version == "1.0.0"

    def test_get_board_info_returns_legacy_dict(self, mock_wmi):
        diag = BoardDiagnostic()
        info = diag.get_board_info()

        assert info["Manufacturer"] == "ASUS"
        assert info["Product"] == "ROG STRIX Z690"
        assert info["BIOS Version"] == "1.0.0"

    def test_get_board_details_preserves_platform_info_on_wmi_error(self):
        with (
            patch("wmi.WMI", side_effect=Exception("WMI unavailable")),
            patch("pythoncom.CoInitialize"),
        ):
            diag = BoardDiagnostic()
            info = diag.get_board_details()

        assert info.is_error is True
        assert info.error_message == "WMI unavailable"
        assert info.system
