import sys
from unittest.mock import MagicMock

sys.modules['pythoncom'] = MagicMock()
sys.modules['win32com'] = MagicMock()
sys.modules['win32com.client'] = MagicMock()
sys.modules['pywin32'] = MagicMock()

class FakePartition:
    device = "C:\\"
    mountpoint = "C:\\"
    fstype = "NTFS"
    opts = "rw,fixed"
    maxfile = 255
    maxpath = 260
sys.modules['pywintypes'] = MagicMock()

class FakeBoard:
    Manufacturer = "ASUS"
    Product = "ROG STRIX Z690"
    SerialNumber = "ABC123"
    SMBIOSBIOSVersion = "1.0.0"

class FakeCPU:
    Name = "Intel Core i7-12700K"
    NumberOfCores = 12
    NumberOfLogicalProcessors = 20
    MaxClockSpeed = 3600

class FakeMemory:
    total = 16 * 1024**3
    available = 8 * 1024**3
    used = 8 * 1024**3
    percent = 50.0

class FakeUsage:
    total = 500 * 1024**3
    used = 250 * 1024**3
    free = 250 * 1024**3
    percent = 50.0

class FakeDrive:
    DeviceID = "\\\\.\\PHYSICALDRIVE0"
    Caption = "Samsung SSD"
    Status = "OK"
sys.modules['pywintypes'] = MagicMock()
sys.modules['pywin32'] = MagicMock()
sys.modules['win32com'] = MagicMock()
sys.modules['win32com.client'] = MagicMock()
