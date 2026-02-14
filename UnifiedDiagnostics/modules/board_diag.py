"""Motherboard and BIOS diagnostics via WMI and platform."""

from __future__ import annotations

import platform

import pythoncom
import wmi


class BoardDiagnostic:
    """Gathers motherboard, BIOS, and OS platform information."""

    def get_board_info(self) -> dict[str, str]:
        """Return a dictionary of motherboard, BIOS, and OS info."""
        info: dict[str, str] = {
            'System': platform.system(),
            'Node Name': platform.node(),
            'Release': platform.release(),
            'Version': platform.version(),
            'Machine': platform.machine(),
        }
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            for board in c.Win32_BaseBoard():
                info['Manufacturer'] = board.Manufacturer
                info['Product'] = board.Product
                info['SerialNumber'] = board.SerialNumber
                break

            for bios in c.Win32_BIOS():
                info['BIOS Version'] = bios.SMBIOSBIOSVersion
                break
        except Exception as e:
            info['Error'] = str(e)
        return info
