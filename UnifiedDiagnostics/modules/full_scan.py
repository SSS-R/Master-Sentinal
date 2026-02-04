import subprocess
import os
import ctypes
import sys

class FullScanDiagnostic:
    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def run_sfc(self):
        """Runs System File Checker. Returns tuple (success, output)."""
        if not self.is_admin():
            return False, "Administrator privileges required."
        
        try:
            result = subprocess.run(['sfc', '/scannow'], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                # Need to scan output for "did not find any integrity violations" or "successfully repaired"
                if "Windows Resource Protection did not find any integrity violations" in result.stdout:
                    return True, "No Integrity Violations"
                elif "successfully repaired" in result.stdout:
                    return True, "Violations Found & Repaired"
                else: 
                    # It might be 0 but say something else?
                    return True, "Scan Complete"
            else:
                 # Standard error message from sfc usually in stdout
                 err = result.stdout or result.stderr
                 return False, f"Error: {err.strip()[:100]}..." # Truncate for UI
        except Exception as e:
            return False, str(e)

    def run_dism(self):
        """Runs DISM RestoreHealth. Returns tuple (success, output)."""
        if not self.is_admin():
            return False, "Administrator privileges required."
        
        try:
            cmd = ['DISM', '/Online', '/Cleanup-Image', '/RestoreHealth']
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                return True, "Restore Operation Successful"
            else:
                return False, f"Failed: {result.stdout.strip()[:100]}..."
        except Exception as e:
            return False, str(e)

    # ... (other methods similar, improving messages) ...

    def run_battery_report(self):
        """Runs Battery Report (Laptop). Returns path."""
        if not self.is_admin():
            return False, "Administrator privileges required."
            
        try:
            report_path = os.path.abspath("battery-report.html")
            cmd = ['powercfg', '/batteryreport', '/output', report_path]
             
            if os.path.exists(report_path):
                try:
                    os.remove(report_path)
                except:
                    pass

            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            output = result.stdout + (result.stderr or "")
            
            if result.returncode == 0:
                return True, f"Report generated at {report_path}"
            else:
                # Check for "No battery" specific errors
                # Common error: "Unable to perform operation. An unexpected error (0x10d2) has occurred: The library, drive, or media pool is empty."
                # Or "The system cannot find the file specified."
                # Or just check if string contains "battery"
                if "Unable to perform operation" in output or "0x10d2" in output or "no battery" in output.lower():
                    return False, "Not a Laptop (No Battery Detected)"
                
                return False, f"Failed: {output.strip()[:50]}..."
        except Exception as e:
            return False, str(e)

    def run_driver_verifier(self):
        """Launches Driver Verifier GUI. Code should be careful."""
        # verifier /gui
        try:
            subprocess.Popen(['verifier', '/gui'])
            return True, "Driver Verifier GUI launched."
        except Exception as e:
            return False, str(e)
            
    def get_full_scan_list(self):
        # Ordered list of checks
        # (Name, FunctionReference, RequiresReboot/Warning)
        return [
            ("System File Checker", self.run_sfc, False),
            ("DISM Image Repair", self.run_dism, False),
            ("Disk Check (Scan)", self.run_chkdsk_scan, False),
            ("Quick Disk Check", self.run_chkdsk_quick, False),
            ("Power Monitor", self.run_power_diag, False),
            ("Battery Health", self.run_battery_report, False),
            ("Driver Verifier", self.run_driver_verifier, False), # GUI launch, not forcing reboot immediately from our code
            ("Memory Diagnostic", self.run_memory_diag, True), # Explicit reboot warning needed
        ]
