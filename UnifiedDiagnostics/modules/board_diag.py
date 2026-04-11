"""Motherboard and BIOS diagnostics via WMI and platform."""

from __future__ import annotations

import platform

import pythoncom
import wmi

from models.diagnostic_models import BoardInfo


class BoardDiagnostic:
    """Gathers motherboard, BIOS, and OS platform information."""

    def get_board_details(self) -> BoardInfo:
        """Return structured motherboard, BIOS, and OS platform information."""
        info = BoardInfo(
            system=platform.system(),
            node_name=platform.node(),
            release=platform.release(),
            version=platform.version(),
            machine=platform.machine(),
        )
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            for board in c.Win32_BaseBoard():
                info = BoardInfo(
                    system=info.system,
                    node_name=info.node_name,
                    release=info.release,
                    version=info.version,
                    machine=info.machine,
                    manufacturer=board.Manufacturer,
                    product=board.Product,
                    serial_number=board.SerialNumber,
                    bios_version=info.bios_version,
                )
                break

            for bios in c.Win32_BIOS():
                info = BoardInfo(
                    system=info.system,
                    node_name=info.node_name,
                    release=info.release,
                    version=info.version,
                    machine=info.machine,
                    manufacturer=info.manufacturer,
                    product=info.product,
                    serial_number=info.serial_number,
                    bios_version=bios.SMBIOSBIOSVersion,
                )
                break
        except Exception as e:
            return BoardInfo(
                system=info.system,
                node_name=info.node_name,
                release=info.release,
                version=info.version,
                machine=info.machine,
                manufacturer=info.manufacturer,
                product=info.product,
                serial_number=info.serial_number,
                bios_version=info.bios_version,
                error_message=str(e),
            )
        return info

    def get_board_info(self) -> dict[str, str]:
        """Return the legacy dict representation expected by older callers."""
        return self.get_board_details().as_dict()
