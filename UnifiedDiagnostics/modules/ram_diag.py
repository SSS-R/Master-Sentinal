import psutil

class RAMDiagnostic:
    def get_ram_info(self):
        """Returns dictionary of RAM statistics."""
        mem = psutil.virtual_memory()
        
        # Convert bytes to GB
        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)

        return {
            'Total': f"{total_gb:.2f} GB",
            'Available': f"{available_gb:.2f} GB",
            'Used': f"{used_gb:.2f} GB",
            'Percentage': mem.percent
        }
