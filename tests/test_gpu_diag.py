"""Unit tests for GPUDiagnostic."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'UnifiedDiagnostics'))

from modules.gpu_diag import GPUDiagnostic


def test_get_gpu_devices_maps_nvidia_smi_payload_to_typed_model():
    payload = b"gpu-1, RTX 4070, 32, 8000, 2000, 10000, 67\n"

    with patch("subprocess.check_output", return_value=payload):
        diag = GPUDiagnostic()
        devices = diag.get_gpu_devices()

    assert len(devices) == 1
    assert devices[0].device_id == "gpu-1"
    assert devices[0].name == "RTX 4070"
    assert devices[0].temperature_text == "67 C"


def test_get_gpu_devices_maps_error_payload_to_error_model():
    with (
        patch("subprocess.check_output", side_effect=FileNotFoundError),
        patch("wmi.WMI", side_effect=Exception("WMI unavailable")),
        patch("pythoncom.CoInitialize"),
    ):
        diag = GPUDiagnostic()
        devices = diag.get_gpu_devices()

    assert len(devices) == 1
    assert devices[0].is_error is True
    assert devices[0].error_message == "WMI unavailable"


