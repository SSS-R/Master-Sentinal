import customtkinter as ctk
import threading
import time
from modules.cpu_diag import CPUDiagnostic
from modules.ram_diag import RAMDiagnostic
from modules.gpu_diag import GPUDiagnostic
from modules.disk_diag import DiskDiagnostic
from modules.board_diag import BoardDiagnostic
from modules.full_scan import FullScanDiagnostic
from ui.components import MetricCard, SectionFrame
from tkinter import messagebox

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Master Sentinal")
        self.geometry("1100x700")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Navigation Frame
        self.nav_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.nav_frame.grid(row=0, column=0, sticky="nsew")
        # Row 9 is spacer to push everything up (so buttons stay at top)
        self.nav_frame.grid_rowconfigure(9, weight=1)

        self.logo_label = ctk.CTkLabel(self.nav_frame, text="SYS DIAG", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=20)

        self.nav_buttons = []
        self.create_nav_button("Dashboard", 1)
        self.create_nav_button("CPU", 2)
        self.create_nav_button("Memory", 3)
        self.create_nav_button("GPU", 4)
        self.create_nav_button("Storage", 5)
        self.create_nav_button("System", 6)
        
        # Fixed Spacer at row 7
        self.nav_spacer = ctk.CTkFrame(self.nav_frame, height=20, fg_color="transparent")
        self.nav_spacer.grid(row=7, column=0, sticky="ew")

        # Full Scan at row 8
        self.create_nav_button("Full Scan", 8)

        # Content Frames and Caches
        self.frames = {}
        
        # Cache dictionaries to store references to widgets {key: widget_instance}
        self.gpu_widgets = {} 
        self.disk_widgets = {} 
        self.smart_widgets = {} 
        self.mem_widgets = {}
        
        self.dashboard_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["Dashboard"] = self.dashboard_frame
        
        self.cpu_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["CPU"] = self.cpu_frame
        
        self.memory_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["Memory"] = self.memory_frame
        
        self.gpu_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["GPU"] = self.gpu_frame
        
        self.storage_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["Storage"] = self.storage_frame
        
        self.system_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["System"] = self.system_frame

        self.full_scan_frame = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.frames["Full Scan"] = self.full_scan_frame

        # Initialize Modules
        self.cpu_mod = CPUDiagnostic()
        self.ram_mod = RAMDiagnostic()
        self.gpu_mod = GPUDiagnostic()
        self.disk_mod = DiskDiagnostic()
        self.board_mod = BoardDiagnostic()
        self.full_scan_mod = FullScanDiagnostic()

        # Dashboard Variables
        self.cpu_usage_var = ctk.StringVar(value="0%")
        self.ram_usage_var = ctk.StringVar(value="0%")
        self.gpu_count_var = ctk.StringVar(value="Searching...")
        self.disk_count_var = ctk.StringVar(value="Scanning...")

        self.setup_dashboard()
        self.setup_cpu_ui()
        self.setup_memory_ui()
        self.setup_gpu_ui()
        self.setup_storage_ui()
        self.setup_system_ui()
        self.setup_full_scan_ui()

        self.select_frame_by_name("Dashboard")
        
        # Start Monitoring
        self.running = True
        self.monitor_thread = threading.Thread(target=self.update_metrics, daemon=True)
        self.monitor_thread.start()

    def create_nav_button(self, text, row):
        btn = ctk.CTkButton(self.nav_frame, corner_radius=0, height=40, border_spacing=10, text=text,
                            fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("gray70", "gray30"),
                            anchor="w", command=lambda: self.select_frame_by_name(text))
        btn.grid(row=row, column=0, sticky="ew")
        self.nav_buttons.append((text, btn))

    def select_frame_by_name(self, name):
        # Update button colors
        for btn_text, btn in self.nav_buttons:
            if btn_text == name:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color="transparent")
        
        # Show frame
        for frame_name, frame in self.frames.items():
            if frame_name == name:
                frame.grid(row=0, column=1, sticky="nsew")
            else:
                frame.grid_forget()

    def setup_dashboard(self):
        # High level metrics
        grid = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=20)
        
        MetricCard(grid, "CPU Load", self.cpu_usage_var).pack(side="left", padx=10, expand=True, fill="x")
        MetricCard(grid, "RAM Usage", self.ram_usage_var).pack(side="left", padx=10, expand=True, fill="x")
        MetricCard(grid, "GPU Status", self.gpu_count_var).pack(side="left", padx=10, expand=True, fill="x")
        MetricCard(grid, "Disks Found", self.disk_count_var).pack(side="left", padx=10, expand=True, fill="x")

    def setup_cpu_ui(self):
        self.cpu_static_frame = SectionFrame(self.cpu_frame, "Processor Information")
        self.cpu_static_frame.pack(fill="x", padx=20, pady=10)
        # We fill this once in update loop or init if possible
        info = self.cpu_mod.get_cpu_info()
        for k, v in info.items():
            self.cpu_static_frame.add_row(k, str(v))
            
        self.cpu_realtime_label = ctk.CTkLabel(self.cpu_frame, text="Real-time Usage per Thread", font=("Roboto", 16, "bold"))
        self.cpu_realtime_label.pack(pady=(20, 10), padx=20, anchor="w")
        
        self.core_bars = []
        self.core_container = ctk.CTkFrame(self.cpu_frame, fg_color="transparent")
        self.core_container.pack(fill="x", padx=20)

    def setup_memory_ui(self):
        self.memory_info_frame = SectionFrame(self.memory_frame, "Memory Statistics")
        self.memory_info_frame.pack(fill="x", padx=20, pady=10)
        # Initializes empty, populated by update_ui

    def setup_gpu_ui(self):
        self.gpu_container = ctk.CTkFrame(self.gpu_frame, fg_color="transparent")
        self.gpu_container.pack(fill="both", expand=True, padx=20, pady=10)

    def setup_storage_ui(self):
        self.storage_container = ctk.CTkFrame(self.storage_frame, fg_color="transparent")
        self.storage_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.smart_frame = SectionFrame(self.storage_frame, "SMART Health Status")
        self.smart_frame.pack(fill="x", padx=20, pady=10)

    def setup_system_ui(self):
        self.sys_info_frame = SectionFrame(self.system_frame, "Motherboard & BIOS")
        self.sys_info_frame.pack(fill="x", padx=20, pady=10)
        
        info = self.board_mod.get_board_info()
        for k, v in info.items():
            self.sys_info_frame.add_row(k, str(v))

    def setup_full_scan_ui(self):
        self.fs_container = ctk.CTkFrame(self.full_scan_frame, fg_color="transparent")
        self.fs_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header
        title = ctk.CTkLabel(self.fs_container, text="System Health Scan", font=("Roboto", 24, "bold"))
        title.pack(anchor="w", pady=(0, 20))

        start_btn = ctk.CTkButton(self.fs_container, text="Start Full Scan", command=self.start_full_scan,
                                  font=("Roboto", 16), height=40)
        start_btn.pack(fill="x", pady=(0, 20))
        self.start_scan_btn = start_btn

        # Status Table area
        self.scan_rows = {} # Name -> {status_label, result_label/icon}
        
        # Pre-populate list
        self.check_list = self.full_scan_mod.get_full_scan_list()
        
        for name, func, reboot in self.check_list:
            row = ctk.CTkFrame(self.fs_container)
            row.pack(fill="x", pady=5)
            
            lbl_name = ctk.CTkLabel(row, text=name, width=200, anchor="w", font=("Roboto", 14, "bold"))
            lbl_name.pack(side="left", padx=10)
            
            lbl_status = ctk.CTkLabel(row, text="Pending", width=300, text_color="gray", anchor="w")
            lbl_status.pack(side="left", padx=10)
            
            self.scan_rows[name] = lbl_status

    def start_full_scan(self):
        if not self.full_scan_mod.is_admin():
            messagebox.showwarning("Admin Required", "This feature requires Administrator privileges.\nPlease restart the application as Administrator.")
            return

        self.start_scan_btn.configure(state="disabled", text="Scanning...")
        
        # Reset statuses
        for name, lbl in self.scan_rows.items():
            lbl.configure(text="Pending", text_color="gray")
            
        threading.Thread(target=self.run_full_scan_thread, daemon=True).start()

    def run_full_scan_thread(self):
        for name, func, reboot in self.check_list:
            # Update status to Running
            self.ui_update_scan_status(name, "Running...", "orange")
            
            if reboot:
                # Ask user confirmation before final step
                if not messagebox.askyesno("Reboot Required", f"The check '{name}' requires a system restart.\n\nDo you want to proceed knowing your PC will reboot?"):
                    self.ui_update_scan_status(name, "Skipped by User", "yellow")
                    continue
                pass 
                
            # Run the check
            success, output = func()
            
            if success:
                # Output might be "OK" or a short message
                # If output is long, we might want to truncate or just show "OK" and log it?
                # User wants details. Our updated modules return short summaries on success too.
                display_text = output if len(output) < 50 else "OK"
                self.ui_update_scan_status(name, display_text, "green")
            else:
                 # Check if it was just a "Skipped" or "Info" return? 
                 # Our functions return (False, Error) on failure.
                 # Check for specific "Not a Laptop" case
                 if "Not a Laptop" in output:
                     self.ui_update_scan_status(name, "Skipped (Not a Laptop)", "yellow")
                 else:
                     self.ui_update_scan_status(name, f"{output}", "red")
                     print(f"[{name}] {output}")

        self.after(0, lambda: self.start_scan_btn.configure(state="normal", text="Start Full Scan"))

    def ui_update_scan_status(self, name, text, color):
        self.after(0, lambda: self.scan_rows[name].configure(text=text, text_color=color))

    def update_metrics(self):
        while self.running:
            try:
                # 1. CPU
                cpu_load = self.cpu_mod.get_cpu_usage()
                per_core = self.cpu_mod.get_per_core_usage()
                # freq = self.cpu_mod.get_frequency() # Optional, sometimes slow
                
                self.cpu_usage_var.set(f"{cpu_load}%")
                
                # 2. RAM
                ram = self.ram_mod.get_ram_info()
                self.ram_usage_var.set(f"{ram['Percentage']}%")

                # 3. GPU
                gpus = self.gpu_mod.get_gpu_info()
                self.gpu_count_var.set(f"{len(gpus)} Device(s)")

                # 4. Disk
                disks = self.disk_mod.get_disk_partitions_and_usage()
                self.disk_count_var.set(f"{len(disks)} Partitions")
                smart = self.disk_mod.get_smart_status()

                # Schedule UI updates safe on main thread
                self.after(0, self.update_ui_elements, per_core, ram, gpus, disks, smart)
                
            except Exception as e:
                print(f"Error in monitor: {e}")
            
            time.sleep(2)

    def update_ui_elements(self, per_core, ram, gpus, disks, smart):
        # --- Update CPU Cores (Using cache implicitly via index) ---
        if len(self.core_bars) != len(per_core):
            # Rebuild needed if count changes (unlikely)
            for child in self.core_container.winfo_children():
                child.destroy()
            self.core_bars = []
            for i, _ in enumerate(per_core):
                f = ctk.CTkFrame(self.core_container)
                f.pack(fill="x", pady=2)
                l = ctk.CTkLabel(f, text=f"Thread {i}", width=70)
                l.pack(side="left")
                p = ctk.CTkProgressBar(f)
                p.pack(side="left", fill="x", expand=True, padx=10)
                v = ctk.CTkLabel(f, text="0%", width=40)
                v.pack(side="left")
                self.core_bars.append((p, v))
        
        for i, usage in enumerate(per_core):
            if i < len(self.core_bars):
                p, v = self.core_bars[i]
                p.set(usage / 100)
                v.configure(text=f"{usage}%")

        # --- Update Memory (Cache by key) ---
        # ram = {'Total': ..., 'Used': ...}
        # Iterate over keys, if cached row exists, update value. Else create.
        for k, v in ram.items():
            if k in self.mem_widgets:
                # Update existing label value
                self.mem_widgets[k].value.configure(text=str(v))
            else:
                # Create NEW row within the helper SectionFrame logic
                # SectionFrame.add_row returns the created row (InfoRow) if we modify components.py
                # But currently add_row doesn't return anything. 
                # We need to manually access the created widget or modify add_row.
                # EASIER: Just Peek at children? No, unstable.
                # Let's Modify add_row in next iteration? 
                # OR: Just implement add_row logic here for caching.
                # Hack: Using the fact that SectionFrame.content is a frame.
                # Let's assume keys are static for RAM? Yes usually.
                # So first time we populate.
                pass
        
        # If mem_widgets is empty, it means first run. Populate it.
        if not self.mem_widgets:
            for k, v in ram.items():
                # We recreate the logic of SectionFrame.add_row to capture the reference
                # This depends on components.py imports
                from ui.components import InfoRow
                row = InfoRow(self.memory_info_frame.content, k, str(v))
                row.pack(fill="x", pady=2)
                self.mem_widgets[k] = row

        # --- Update GPU ---
        # GPUs can change if eGPU? Unlikely but possible.
        # Assuming fixed request order for simplicity or match by Name?
        # Let's simple clear/recreate if count mismatches, otherwise update.
        # GPU widgets cache structure: { gpu_index: { 'Load': row_widget, 'Temp': row_widget ... } }
        
        # Full Rebuild for GPU/Disk on change is okay if rare, but flickering comes from frequent full rebuilds.
        # Check if we have same number of GPUs and names.
        current_gpu_signatures = [g.get('Name') for g in gpus]
        cached_gpu_signatures = list(self.gpu_widgets.keys())
        
        if current_gpu_signatures != cached_gpu_signatures:
            # Rebuild All
            for child in self.gpu_container.winfo_children():
                child.destroy()
            self.gpu_widgets = {}
            for i, gpu in enumerate(gpus):
                name = gpu.get('Name', f'GPU {i}')
                f = SectionFrame(self.gpu_container, f"GPU {i+1}: {name}")
                f.pack(fill="x", pady=10)
                
                # Create rows and store refs
                rows = {}
                from ui.components import InfoRow
                for k, v in gpu.items():
                    if k != 'Name':
                        r = InfoRow(f.content, k, str(v))
                        r.pack(fill="x", pady=2)
                        rows[k] = r
                self.gpu_widgets[name] = rows
        else:
            # Update Existing
            for gpu in gpus:
                name = gpu.get('Name')
                if name in self.gpu_widgets:
                    rows = self.gpu_widgets[name]
                    for k, v in gpu.items():
                        if k in rows:
                            rows[k].value.configure(text=str(v))

        # --- Update Storage ---
        # Similar logic. Match by Mountpoint usually unique?
        current_disk_sigs = [d.get('Mountpoint') for d in disks]
        cached_disk_sigs = list(self.disk_widgets.keys())
        
        if current_disk_sigs != cached_disk_sigs:
            for child in self.storage_container.winfo_children():
                child.destroy()
            self.disk_widgets = {}
            for disk in disks:
                mp = disk.get('Mountpoint')
                f = SectionFrame(self.storage_container, f"{disk.get('Device')} ({mp})")
                f.pack(fill="x", pady=10)
                
                rows = {}
                from ui.components import InfoRow
                for k, v in disk.items():
                    if k not in ['Device', 'Mountpoint']:
                        r = InfoRow(f.content, k, str(v))
                        r.pack(fill="x", pady=2)
                        rows[k] = r
                self.disk_widgets[mp] = rows
        else:
            for disk in disks:
                mp = disk.get('Mountpoint')
                if mp in self.disk_widgets:
                    rows = self.disk_widgets[mp]
                    for k, v in disk.items():
                        if k in rows:
                            rows[k].value.configure(text=str(v))

        # --- Update SMART ---
        # Keys are Drive Captions
        current_smart_sigs = list(smart.keys())
        if current_smart_sigs != list(self.smart_widgets.keys()):
            for child in self.smart_frame.content.winfo_children():
                child.destroy()
            self.smart_widgets = {}
            for k, v in smart.items():
                from ui.components import InfoRow
                r = InfoRow(self.smart_frame.content, k, str(v))
                r.pack(fill="x", pady=2)
                self.smart_widgets[k] = r
        else:
            for k, v in smart.items():
                if k in self.smart_widgets:
                    self.smart_widgets[k].value.configure(text=str(v))


    def on_closing(self):
        self.running = False
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
