# Master Sentinal

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)

Master Sentinal is a modern, unified system diagnostics tool for Windows. It provides real-time monitoring and a comprehensive "Full Scan" health check — all in a single, lightweight application.

> **Security Note:** The app requests Administrator privileges so it can run Windows diagnostics (SFC, DISM, CHKDSK, etc.). The source code is fully open — feel free to audit it.

---

## ✨ Features

| Category | Details |
|---|---|
| **Dashboard** | Live CPU load, RAM usage, GPU status, and disk count at a glance |
| **CPU** | Static info (cores, threads, clock) + real-time per-thread usage bars |
| **Memory** | Total / Available / Used / Percentage — updated every 2 seconds |
| **GPU** | NVIDIA-SMI with WMI fallback — load, memory, temperature |
| **Storage** | Partition usage + SMART health status per physical drive |
| **System** | Motherboard & BIOS information |
| **Full Scan** | SFC, DISM, CHKDSK, Power Monitor, Battery Health, Driver Verifier, Memory Diagnostic |
| **Export Report** | One-click CSV export of all current stats |
| **Temp Alerts** | GPU temperature highlighted red when ≥ 90°C |

---

## 🚀 How to Download & Run (Easy Way)

You do **not** need to install Python or any coding tools.

1. **Go to the [Releases](../../releases) page** of this repository.
2. **Download** the latest `Master Sentinal.exe` from the "Assets" section.
3. **Move** it to any folder on your computer (e.g., Desktop or Documents).
4. **Double-click** `Master Sentinal.exe` to launch.
   - *Note: The app requires Administrator privileges to run diagnostics, so click "Yes" when Windows asks.*

That's it!

---

## 📸 Screenshots

<!-- Add screenshots / GIFs of the UI here for better visibility -->
*Coming soon — contributions welcome!*

---

## 🛠️ For Developers

### Prerequisites
- Python 3.10 or higher
- Git

### Installation
```bash
git clone https://github.com/YourUsername/MasterSentinal.git
cd MasterSentinal
pip install -r UnifiedDiagnostics/requirements.txt
```

### Running from Source
```bash
# Run as Administrator for full functionality
python UnifiedDiagnostics/main.py
```

### Running Tests
```bash
pip install pytest
python -m pytest tests/ -v
```

### Building the Executable
```bash
python build_app.py
```
The new file will appear in the `dist/` folder.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
