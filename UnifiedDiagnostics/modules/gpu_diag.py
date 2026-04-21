"""GPU diagnostics - NVIDIA-SMI with WMI fallback."""

from __future__ import annotations

import os
import subprocess

import pythoncom
import wmi

from models.diagnostic_models import GPUDevice
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message


LOGGER = get_logger(__name__)


class GPUDiagnostic:
    """Gathers GPU information using nvidia-smi (preferred) or WMI."""

    def get_gpu_devices(self) -> list[GPUDevice]:
        """Return structured GPU devices with load, memory, and temperature data."""
        gpus: list[GPUDevice] = []

        # 1. Try NVIDIA-SMI with hidden console window
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            cmd = [
                "nvidia-smi",
                "--query-gpu=gpu_uuid,name,utilization.gpu,memory.free,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ]

            output = subprocess.check_output(cmd, startupinfo=startupinfo, stderr=subprocess.DEVNULL, timeout=5)
            lines = output.decode("utf-8").strip().split("\n")

            for line in lines:
                vals = [x.strip() for x in line.split(",")]
                if len(vals) >= 7:
                    gpus.append(
                        GPUDevice(
                            device_id=vals[0],
                            name=vals[1],
                            load_text=f"{vals[2]}%",
                            free_memory_text=f"{vals[3]}MB",
                            used_memory_text=f"{vals[4]}MB",
                            total_memory_text=f"{vals[5]}MB",
                            temperature_text=f"{vals[6]} C",
                        )
                    )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        except Exception as exc:
            LOGGER.info("NVIDIA-SMI lookup skipped: %s", exc)
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

                    gpus.append(
                        GPUDevice(
                            device_id=gpu.PNPDeviceID or gpu.DeviceID or gpu.Name,
                            name=gpu.Name,
                            load_text="N/A (WMI)",
                            total_memory_text=ram_mb,
                        )
                    )
            except Exception as e:
                LOGGER.warning("GPU WMI fallback failed: %s", e)
                gpus.append(GPUDevice(error_message=friendly_exception_message(e, "GPU diagnostics")))

        return gpus

