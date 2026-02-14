"""GPU diagnostics — NVIDIA-SMI with WMI fallback."""

from __future__ import annotations

import os
import subprocess

import pythoncom
import wmi


class GPUDiagnostic:
    """Gathers GPU information using nvidia-smi (preferred) or WMI."""

    def get_gpu_info(self) -> list[dict[str, str]]:
        """Return a list of dicts, one per GPU, with load/memory/temp data.

        Each dict contains a stable ``DeviceID`` key suitable for widget caching.
        """
        gpus: list[dict[str, str]] = []

        # 1. Try NVIDIA-SMI with hidden console window
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            cmd = [
                'nvidia-smi',
                '--query-gpu=gpu_uuid,name,utilization.gpu,memory.free,memory.used,memory.total,temperature.gpu',
                '--format=csv,noheader,nounits',
            ]

            output = subprocess.check_output(cmd, startupinfo=startupinfo, stderr=subprocess.DEVNULL)
            lines = output.decode('utf-8').strip().split('\n')

            for line in lines:
                vals = [x.strip() for x in line.split(',')]
                if len(vals) >= 7:
                    gpus.append({
                        'DeviceID': vals[0],   # GPU UUID — stable identifier
                        'Name': vals[1],
                        'Load': f"{vals[2]}%",
                        'Free Memory': f"{vals[3]}MB",
                        'Used Memory': f"{vals[4]}MB",
                        'Total Memory': f"{vals[5]}MB",
                        'Temperature': f"{vals[6]} C",
                    })
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        except Exception:
            pass

        # 2. Fallback to WMI
        if not gpus:
            try:
                pythoncom.CoInitialize()
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    ram_mb = "N/A"
                    try:
                        if gpu.AdapterRAM:
                            ram_mb = f"{int(gpu.AdapterRAM) / (1024**2):.0f}MB"
                    except Exception:
                        pass

                    gpus.append({
                        'DeviceID': gpu.PNPDeviceID or gpu.DeviceID or gpu.Name,
                        'Name': gpu.Name,
                        'Load': "N/A (WMI)",
                        'Free Memory': "N/A",
                        'Used Memory': "N/A",
                        'Total Memory': ram_mb,
                        'Temperature': "N/A",
                    })
            except Exception as e:
                gpus.append({'Error': str(e)})

        return gpus
