import psutil
import wmi
import pythoncom

class CPUDiagnostic:
    def __init__(self):
        # WMI needs to be initialized in the thread it's used in, 
        # but for static info we can grab it once.
        # Note: pythoncom.CoInitialize() might be needed if running in threads.
        pass

    def get_cpu_info(self):
        """Returns static CPU information."""
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            cpu_info = {}
            for processor in c.Win32_Processor():
                cpu_info['Name'] = processor.Name
                cpu_info['Cores'] = processor.NumberOfCores
                cpu_info['Threads'] = processor.NumberOfLogicalProcessors
                cpu_info['MaxClockSpeed'] = f"{processor.MaxClockSpeed} MHz"
                break # Assume single socket for now
            return cpu_info
        except Exception as e:
            return {'Error': str(e)}

    def get_cpu_usage(self):
        """Returns real-time CPU usage percentage."""
        return psutil.cpu_percent(interval=None)

    def get_per_core_usage(self):
        """Returns list of usage per core."""
        return psutil.cpu_percent(interval=None, percpu=True)
    
    def get_frequency(self):
        """Returns current CPU frequency."""
        freq = psutil.cpu_freq()
        if freq:
            return f"{freq.current:.2f} MHz"
        return "N/A"
