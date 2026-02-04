# Master Sentinal

Master Sentinal is a modern, unified system diagnostics tool built with Python and CustomTkinter. It provides real-time monitoring of CPU, RAM, GPU, and Storage, along with a comprehensive "Full Scan" feature for system health.

## Features

- **Dashboard**: High-level overview of system resources.
- **Real-time Monitoring**:
  - Detailed per-core CPU usage.
  - RAM statistics.
  - GPU detection and monitoring.
  - Disk usage and SMART health status.
- **Full Scan**: One-click execution of 8 system diagnostic tools:
  - System File Checker (SFC)
  - DISM Image Repair
  - Disk Check (Scan & Perf)
  - Power Efficiency Report
  - Battery Health Report
  - Driver Verifier
  - Windows Memory Diagnostic

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r UnifiedDiagnostics/requirements.txt
   ```

## Running from Source

**Note**: The application requires Administrator privileges to run diagnostics.

```bash
# Run as Administrator
python UnifiedDiagnostics/main.py
```

## Building Executable

To build a standalone `.exe` that automatically requests Admin privileges:

```bash
python build_app.py
```

The output will be in `dist/Master Sentinal/Master Sentinal.exe`.
