import wmi
import pythoncom
import subprocess
import os
import sys

class GPUDiagnostic:
    def get_gpu_info(self):
        """Returns list of dictionaries containing GPU info."""
        gpus = []
        
        # 1. Try NVIDIA-SMI with hidden console window to avoid flicker
        try:
            # Creation flags to hide window (Windows only)
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Query UUID, name, temperature, utilization, memory
            # Note: memory.total is usually static, but fine to query
            cmd = ['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.free,memory.used,memory.total,temperature.gpu', '--format=csv,noheader,nounits']
            
            # Use check_output to get stdout. stderr=DEVNULL to ignore errors if any.
            output = subprocess.check_output(cmd, startupinfo=startupinfo, stderr=subprocess.DEVNULL)
            lines = output.decode('utf-8').strip().split('\n')
            
            for line in lines:
                vals = [x.strip() for x in line.split(',')]
                # Expecting at least 6 values
                if len(vals) >= 6:
                    gpus.append({
                        'Name': vals[0],
                        'Load': f"{vals[1]}%",
                        'Free Memory': f"{vals[2]}MB",
                        'Used Memory': f"{vals[3]}MB",
                        'Total Memory': f"{vals[4]}MB",
                        'Temperature': f"{vals[5]} C"
                    })
        except (subprocess.CalledProcessError, FileNotFoundError):
             # nvidia-smi not found or failed
             pass
        except Exception:
            pass
        
        # 2. If no dedicated GPU found via SMI (or parsing failed), use WMI
        if not gpus:
            try:
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    # WMI often lacks load/temp, but better than nothing
                    # AdapterRAM is bytes
                    ram_mb = "N/A"
                    try:
                         if gpu.AdapterRAM:
                             ram_mb = f"{int(gpu.AdapterRAM) / (1024**2):.0f}MB"
                    except:
                        pass
                        
                    gpus.append({
                        'Name': gpu.Name,
                        'Load': "N/A (WMI)",
                        'Free Memory': "N/A",
                        'Used Memory': "N/A",
                        'Total Memory': ram_mb,
                        'Temperature': "N/A"
                    })
            except Exception as e:
                gpus.append({'Error': str(e)})
        
        return gpus
