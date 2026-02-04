import wmi
import pythoncom
import platform

class BoardDiagnostic:
    def get_board_info(self):
        """Returns motherboard and BIOS info."""
        info = {
            'System': platform.system(),
            'Node Name': platform.node(),
            'Release': platform.release(),
            'Version': platform.version(),
            'Machine': platform.machine()
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
