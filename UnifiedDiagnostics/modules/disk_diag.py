import psutil
import wmi
import pythoncom

class DiskDiagnostic:
    def get_disk_partitions_and_usage(self):
        """Returns list of disk usage stats per partition."""
        disks = []
        try:
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        'Device': partition.device,
                        'Mountpoint': partition.mountpoint,
                        'Total': f"{usage.total / (1024**3):.2f} GB",
                        'Used': f"{usage.used / (1024**3):.2f} GB",
                        'Free': f"{usage.free / (1024**3):.2f} GB",
                        'Percent': f"{usage.percent}%"
                    })
                except PermissionError:
                    continue
        except Exception as e:
            disks.append({'Error': str(e)})
        return disks

    def get_smart_status(self):
        """Checks WMI for SMART status. Returns 'OK' or 'Fail' per drive."""
        status = {}
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            for drive in c.Win32_DiskDrive():
                # Status is often 'OK', 'Pred Fail', etc.
                status[drive.Caption] = drive.Status
        except Exception as e:
            status['Error'] = str(e)
        return status
