# Master Sentinal

Master Sentinal is a modern, unified system diagnostics tool for Windows. It provides real-time monitoring and a comprehensive "Full Scan" health check.

## 🚀 How to Download & Run (Easy Way)

You do **not** need to install Python or any coding tools.

1.  **Go to the [Releases](../../releases) page** of this repository.
2.  **Download** the latest `Master Sentinal.exe` from the "Assets" section.
3.  **Move** it to any folder on your computer (e.g., Desktop or Documents).
3.  **Double-click** `Master Sentinal.exe` to launch.
    *   *Note: The app requires Administrator privileges to run diagnostics, so click "Yes" when Windows asks.*

That's it!

---

## 🛠️ For Developers

If you want to modify the code or run from source:

### Prerequisites
- Python 3.10 or higher
- Git

### Installation
1.  Clone the repository:
    ```bash
    git clone https://github.com/YourUsername/MasterSentinal.git
    cd MasterSentinal
    ```
2.  Install dependencies:
    ```bash
    pip install -r UnifiedDiagnostics/requirements.txt
    ```

### Running Source Code
```bash
# Run as Administrator for full functionality
python UnifiedDiagnostics/main.py
```

### Building the Exe
To recreate the single-file executable yourself:
```bash
python build_app.py
```
The new file will appear in the `dist/` folder.
