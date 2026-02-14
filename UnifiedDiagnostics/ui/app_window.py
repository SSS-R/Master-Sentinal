"""Main application window for Master Sentinal."""

from __future__ import annotations

import csv
import os
import threading
import time
from datetime import datetime
from tkinter import messagebox, filedialog
from typing import Any, Callable

import customtkinter as ctk

from config import (
    APPEARANCE_MODE,
    COLOR_THEME,
    TEMP_ALERT_THRESHOLD_C,
    UPDATE_INTERVAL_SEC,
    WINDOW_GEOMETRY,
    WINDOW_TITLE,
)
from modules.board_diag import BoardDiagnostic
from modules.cpu_diag import CPUDiagnostic
from modules.disk_diag import DiskDiagnostic
from modules.full_scan import FullScanDiagnostic
from modules.gpu_diag import GPUDiagnostic
from modules.ram_diag import RAMDiagnostic
from ui.components import InfoRow, MetricCard, SectionFrame


# Navigation items (order matters — rendered top to bottom)
NAV_ITEMS: list[str] = ["Dashboard", "CPU", "Memory", "GPU", "Storage", "System"]
NAV_SCAN_ITEM: str = "Full Scan"


class App(ctk.CTk):
    """Top-level window that hosts every diagnostic tab."""

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()

        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_GEOMETRY)
        ctk.set_appearance_mode(APPEARANCE_MODE)
        ctk.set_default_color_theme(COLOR_THEME)

        # Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Navigation (pack-based — easy to reorder)
        self.nav_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.nav_frame.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(
            self.nav_frame, text="SYS DIAG",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.logo_label.pack(padx=20, pady=20)

        # Build nav buttons from the ordered list
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for name in NAV_ITEMS:
            self._add_nav_button(name)

        # Spacer between main items and Full Scan
        spacer = ctk.CTkFrame(self.nav_frame, height=20, fg_color="transparent")
        spacer.pack(fill="x")

        self._add_nav_button(NAV_SCAN_ITEM)

        # Content frames
        self.frames: dict[str, ctk.CTkScrollableFrame] = {}

        # Widget caches — {stable_key: {metric_key: InfoRow}}
        self.gpu_widgets: dict[str, dict[str, InfoRow]] = {}
        self.disk_widgets: dict[str, dict[str, InfoRow]] = {}
        self.smart_widgets: dict[str, InfoRow] = {}
        self.mem_widgets: dict[str, InfoRow] = {}

        for frame_name in [*NAV_ITEMS, NAV_SCAN_ITEM]:
            f = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
            self.frames[frame_name] = f

        # Diagnostic modules
        self.cpu_mod = CPUDiagnostic()
        self.ram_mod = RAMDiagnostic()
        self.gpu_mod = GPUDiagnostic()
        self.disk_mod = DiskDiagnostic()
        self.board_mod = BoardDiagnostic()
        self.full_scan_mod = FullScanDiagnostic()

        # Dashboard string vars
        self.cpu_usage_var = ctk.StringVar(value="0%")
        self.ram_usage_var = ctk.StringVar(value="0%")
        self.gpu_count_var = ctk.StringVar(value="Searching...")
        self.disk_count_var = ctk.StringVar(value="Scanning...")

        # Build each tab's UI
        self.setup_dashboard()
        self.setup_cpu_ui()
        self.setup_memory_ui()
        self.setup_gpu_ui()
        self.setup_storage_ui()
        self.setup_system_ui()
        self.setup_full_scan_ui()

        self.select_frame_by_name("Dashboard")

        # Monitoring thread (uses Event for clean shutdown)
        self._stop_event = threading.Event()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _add_nav_button(self, name: str) -> None:
        """Create a sidebar button and register it in *nav_buttons*."""
        btn = ctk.CTkButton(
            self.nav_frame, corner_radius=0, height=40, border_spacing=10,
            text=name, fg_color="transparent",
            text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"),
            anchor="w",
            command=lambda n=name: self.select_frame_by_name(n),
        )
        btn.pack(fill="x")
        self.nav_buttons[name] = btn

    def select_frame_by_name(self, name: str) -> None:
        """Show *name*'s frame, hide the rest, update button highlights."""
        for btn_name, btn in self.nav_buttons.items():
            btn.configure(fg_color=("gray75", "gray25") if btn_name == name else "transparent")

        for frame_name, frame in self.frames.items():
            if frame_name == name:
                frame.grid(row=0, column=1, sticky="nsew")
            else:
                frame.grid_forget()

    # ------------------------------------------------------------------
    # Tab setup
    # ------------------------------------------------------------------

    def setup_dashboard(self) -> None:
        """Build the high-level dashboard cards and export button."""
        df = self.frames["Dashboard"]

        grid = ctk.CTkFrame(df, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=20)

        MetricCard(grid, "CPU Load", self.cpu_usage_var).pack(side="left", padx=10, expand=True, fill="x")
        MetricCard(grid, "RAM Usage", self.ram_usage_var).pack(side="left", padx=10, expand=True, fill="x")
        MetricCard(grid, "GPU Status", self.gpu_count_var).pack(side="left", padx=10, expand=True, fill="x")
        MetricCard(grid, "Disks Found", self.disk_count_var).pack(side="left", padx=10, expand=True, fill="x")

        # Export Report button
        export_btn = ctk.CTkButton(
            df, text="📄 Export Report (CSV)", font=("Roboto", 14), height=36,
            command=self._export_report,
        )
        export_btn.pack(fill="x", padx=20, pady=(0, 10))

    def setup_cpu_ui(self) -> None:
        """Build static CPU info and per-thread progress bars."""
        cf = self.frames["CPU"]

        self.cpu_static_frame = SectionFrame(cf, "Processor Information")
        self.cpu_static_frame.pack(fill="x", padx=20, pady=10)
        info = self.cpu_mod.get_cpu_info()
        for k, v in info.items():
            self.cpu_static_frame.add_row(k, str(v))

        self.cpu_realtime_label = ctk.CTkLabel(
            cf, text="Real-time Usage per Thread",
            font=("Roboto", 16, "bold"),
        )
        self.cpu_realtime_label.pack(pady=(20, 10), padx=20, anchor="w")

        self.core_bars: list[tuple[ctk.CTkProgressBar, ctk.CTkLabel]] = []
        self.core_container = ctk.CTkFrame(cf, fg_color="transparent")
        self.core_container.pack(fill="x", padx=20)

    def setup_memory_ui(self) -> None:
        """Prepare the Memory section (populated by the monitor loop)."""
        self.memory_info_frame = SectionFrame(self.frames["Memory"], "Memory Statistics")
        self.memory_info_frame.pack(fill="x", padx=20, pady=10)

    def setup_gpu_ui(self) -> None:
        """Prepare the GPU container (populated by the monitor loop)."""
        self.gpu_container = ctk.CTkFrame(self.frames["GPU"], fg_color="transparent")
        self.gpu_container.pack(fill="both", expand=True, padx=20, pady=10)

    def setup_storage_ui(self) -> None:
        """Prepare the Storage + SMART containers."""
        sf = self.frames["Storage"]

        self.storage_container = ctk.CTkFrame(sf, fg_color="transparent")
        self.storage_container.pack(fill="both", expand=True, padx=20, pady=10)

        self.smart_frame = SectionFrame(sf, "SMART Health Status")
        self.smart_frame.pack(fill="x", padx=20, pady=10)

    def setup_system_ui(self) -> None:
        """Build the static Motherboard & BIOS info section."""
        sf = self.frames["System"]

        self.sys_info_frame = SectionFrame(sf, "Motherboard & BIOS")
        self.sys_info_frame.pack(fill="x", padx=20, pady=10)

        info = self.board_mod.get_board_info()
        for k, v in info.items():
            self.sys_info_frame.add_row(k, str(v))

    def setup_full_scan_ui(self) -> None:
        """Build the Full Scan results table and Start button."""
        ff = self.frames[NAV_SCAN_ITEM]

        self.fs_container = ctk.CTkFrame(ff, fg_color="transparent")
        self.fs_container.pack(fill="both", expand=True, padx=20, pady=20)

        title = ctk.CTkLabel(
            self.fs_container, text="System Health Scan",
            font=("Roboto", 24, "bold"),
        )
        title.pack(anchor="w", pady=(0, 20))

        self.start_scan_btn = ctk.CTkButton(
            self.fs_container, text="Start Full Scan",
            command=self.start_full_scan, font=("Roboto", 16), height=40,
        )
        self.start_scan_btn.pack(fill="x", pady=(0, 20))

        self.scan_rows: dict[str, ctk.CTkLabel] = {}
        self.check_list = self.full_scan_mod.get_full_scan_list()

        for name, _func, _reboot in self.check_list:
            row = ctk.CTkFrame(self.fs_container)
            row.pack(fill="x", pady=5)

            lbl_name = ctk.CTkLabel(
                row, text=name, width=200, anchor="w",
                font=("Roboto", 14, "bold"),
            )
            lbl_name.pack(side="left", padx=10)

            lbl_status = ctk.CTkLabel(
                row, text="Pending", width=300,
                text_color="gray", anchor="w",
            )
            lbl_status.pack(side="left", padx=10)

            self.scan_rows[name] = lbl_status

    # ------------------------------------------------------------------
    # Full Scan
    # ------------------------------------------------------------------

    def start_full_scan(self) -> None:
        """Validate admin rights, reset status labels, and kick off the scan thread."""
        if not self.full_scan_mod.is_admin():
            messagebox.showwarning(
                "Admin Required",
                "This feature requires Administrator privileges.\n"
                "Please restart the application as Administrator.",
            )
            return

        self.start_scan_btn.configure(state="disabled", text="Scanning...")

        for lbl in self.scan_rows.values():
            lbl.configure(text="Pending", text_color="gray")

        threading.Thread(target=self._run_full_scan, daemon=True).start()

    def _run_full_scan(self) -> None:
        """Execute each check sequentially in a background thread."""
        for name, func, reboot in self.check_list:
            self._ui_scan_status(name, "Running...", "orange")

            if reboot:
                if not messagebox.askyesno(
                    "Reboot Required",
                    f"The check '{name}' requires a system restart.\n\n"
                    "Do you want to proceed knowing your PC will reboot?",
                ):
                    self._ui_scan_status(name, "Skipped by User", "yellow")
                    continue

            # Error-protected execution (per review feedback)
            try:
                success, output = func()
            except Exception as exc:
                self._ui_scan_status(name, f"Error: {str(exc)[:50]}", "red")
                print(f"[{name}] EXCEPTION: {exc}")
                continue

            if success:
                display = output if len(output) < 50 else "OK"
                self._ui_scan_status(name, display, "green")
            else:
                if "Not a Laptop" in output:
                    self._ui_scan_status(name, "Skipped (Not a Laptop)", "yellow")
                else:
                    self._ui_scan_status(name, output, "red")
                    print(f"[{name}] {output}")

        self.after(0, lambda: self.start_scan_btn.configure(state="normal", text="Start Full Scan"))

    def _ui_scan_status(self, name: str, text: str, color: str) -> None:
        """Thread-safe helper to update a scan-row label."""
        self.after(0, lambda: self.scan_rows[name].configure(text=text, text_color=color))

    # ------------------------------------------------------------------
    # Real-time monitor
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Periodically poll diagnostics and schedule UI updates."""
        while not self._stop_event.is_set():
            try:
                cpu_load = self.cpu_mod.get_cpu_usage()
                per_core = self.cpu_mod.get_per_core_usage()
                self.cpu_usage_var.set(f"{cpu_load}%")

                ram = self.ram_mod.get_ram_info()
                self.ram_usage_var.set(f"{ram['Percentage']}%")

                gpus = self.gpu_mod.get_gpu_info()
                self.gpu_count_var.set(f"{len(gpus)} Device(s)")

                disks = self.disk_mod.get_disk_partitions_and_usage()
                self.disk_count_var.set(f"{len(disks)} Partitions")
                smart = self.disk_mod.get_smart_status()

                # Store latest data for export
                self._last_gpus = gpus
                self._last_disks = disks
                self._last_smart = smart
                self._last_ram = ram

                self.after(0, self._update_ui, per_core, ram, gpus, disks, smart)

            except Exception as e:
                print(f"Error in monitor: {e}")

            # Use Event.wait instead of time.sleep for clean cancellation
            self._stop_event.wait(UPDATE_INTERVAL_SEC)

    # ------------------------------------------------------------------
    # UI update (runs on main thread)
    # ------------------------------------------------------------------

    def _update_ui(
        self,
        per_core: list[float],
        ram: dict[str, Any],
        gpus: list[dict[str, str]],
        disks: list[dict[str, str]],
        smart: dict[str, str],
    ) -> None:
        """Refresh all live-data widgets. Called via ``self.after()``."""

        # --- CPU per-thread bars ---
        if len(self.core_bars) != len(per_core):
            for child in self.core_container.winfo_children():
                child.destroy()
            self.core_bars = []
            for i in range(len(per_core)):
                f = ctk.CTkFrame(self.core_container)
                f.pack(fill="x", pady=2)
                lbl = ctk.CTkLabel(f, text=f"Thread {i}", width=70)
                lbl.pack(side="left")
                pb = ctk.CTkProgressBar(f)
                pb.pack(side="left", fill="x", expand=True, padx=10)
                val = ctk.CTkLabel(f, text="0%", width=40)
                val.pack(side="left")
                self.core_bars.append((pb, val))

        for i, usage in enumerate(per_core):
            if i < len(self.core_bars):
                pb, val = self.core_bars[i]
                pb.set(usage / 100)
                val.configure(text=f"{usage}%")

        # --- Memory ---
        if not self.mem_widgets:
            for k, v in ram.items():
                row = InfoRow(self.memory_info_frame.content, k, str(v))
                row.pack(fill="x", pady=2)
                self.mem_widgets[k] = row
        else:
            for k, v in ram.items():
                if k in self.mem_widgets:
                    self.mem_widgets[k].value.configure(text=str(v))

        # --- GPU / Disk / SMART — via generic helper ---
        self._update_device_section(
            container=self.gpu_container,
            items=gpus,
            cache=self.gpu_widgets,
            key_fn=lambda g: g.get('DeviceID', g.get('Name', '')),
            title_fn=lambda g, i: f"GPU {i + 1}: {g.get('Name', 'Unknown')}",
            skip_keys={'DeviceID', 'Name'},
            alert_rules={'Temperature': self._temp_alert_color},
        )

        self._update_device_section(
            container=self.storage_container,
            items=disks,
            cache=self.disk_widgets,
            key_fn=lambda d: d.get('Mountpoint', ''),
            title_fn=lambda d, i: f"{d.get('Device', '?')} ({d.get('Mountpoint', '?')})",
            skip_keys={'Device', 'Mountpoint'},
        )

        # SMART — flat key→value (no nested dicts), use simpler path
        current_smart_keys = list(smart.keys())
        if current_smart_keys != list(self.smart_widgets.keys()):
            for child in self.smart_frame.content.winfo_children():
                child.destroy()
            self.smart_widgets = {}
            for k, v in smart.items():
                r = InfoRow(self.smart_frame.content, k, str(v))
                r.pack(fill="x", pady=2)
                self.smart_widgets[k] = r
        else:
            for k, v in smart.items():
                if k in self.smart_widgets:
                    self.smart_widgets[k].value.configure(text=str(v))

    # ------------------------------------------------------------------
    # Generic device-section updater (eliminates GPU/Disk duplication)
    # ------------------------------------------------------------------

    def _update_device_section(
        self,
        container: ctk.CTkFrame,
        items: list[dict[str, str]],
        cache: dict[str, dict[str, InfoRow]],
        key_fn: Callable[[dict[str, str]], str],
        title_fn: Callable[[dict[str, str], int], str],
        skip_keys: set[str] | None = None,
        alert_rules: dict[str, Callable[[str], str | None]] | None = None,
    ) -> None:
        """Compare *items* against *cache*; rebuild only when keys change.

        Parameters
        ----------
        container:
            Parent frame that holds SectionFrame children.
        items:
            Latest data from a diagnostic module.
        cache:
            Mutable dict ``{stable_id: {metric: InfoRow}}``.
        key_fn:
            Extracts a stable identifier from each item dict.
        title_fn:
            Produces the SectionFrame title ``(item, index) -> str``.
        skip_keys:
            Keys in item dict NOT rendered as rows (e.g. identifiers).
        alert_rules:
            Optional ``{metric_key: fn(value_str) -> color_or_None}`` for
            conditional highlighting.
        """
        skip = skip_keys or set()
        rules = alert_rules or {}

        current_sigs = [key_fn(item) for item in items]
        cached_sigs = list(cache.keys())

        if current_sigs != cached_sigs:
            # Full rebuild
            for child in container.winfo_children():
                child.destroy()
            cache.clear()

            for i, item in enumerate(items):
                sid = key_fn(item)
                section = SectionFrame(container, title_fn(item, i))
                section.pack(fill="x", pady=10)

                rows: dict[str, InfoRow] = {}
                for k, v in item.items():
                    if k not in skip:
                        r = InfoRow(section.content, k, str(v))
                        r.pack(fill="x", pady=2)
                        rows[k] = r
                        # Apply alert colour if rule matches
                        color = rules.get(k, lambda _: None)(str(v))
                        if color:
                            r.value.configure(text_color=color)
                cache[sid] = rows
        else:
            # In-place update
            for item in items:
                sid = key_fn(item)
                if sid in cache:
                    rows = cache[sid]
                    for k, v in item.items():
                        if k in rows:
                            rows[k].value.configure(text=str(v))
                            color = rules.get(k, lambda _: None)(str(v))
                            if color:
                                rows[k].value.configure(text_color=color)
                            else:
                                # Reset to default
                                rows[k].value.configure(text_color=("gray10", "gray90"))

    # ------------------------------------------------------------------
    # Temperature alert helper
    # ------------------------------------------------------------------

    @staticmethod
    def _temp_alert_color(value: str) -> str | None:
        """Return ``'red'`` if *value* represents a temperature ≥ threshold."""
        try:
            num = float(value.replace("°", "").replace("C", "").strip())
            if num >= TEMP_ALERT_THRESHOLD_C:
                return "red"
        except (ValueError, AttributeError):
            pass
        return None

    # ------------------------------------------------------------------
    # Export report
    # ------------------------------------------------------------------

    def _export_report(self) -> None:
        """Save current diagnostics snapshot to a CSV file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"MasterSentinal_Report_{datetime.now():%Y%m%d_%H%M%S}.csv",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Section", "Key", "Value"])

                # CPU
                writer.writerow(["CPU", "Usage", self.cpu_usage_var.get()])
                info = self.cpu_mod.get_cpu_info()
                for k, v in info.items():
                    writer.writerow(["CPU", k, v])

                # RAM
                ram = getattr(self, "_last_ram", self.ram_mod.get_ram_info())
                for k, v in ram.items():
                    writer.writerow(["RAM", k, v])

                # GPUs
                gpus = getattr(self, "_last_gpus", self.gpu_mod.get_gpu_info())
                for i, gpu in enumerate(gpus):
                    for k, v in gpu.items():
                        writer.writerow([f"GPU {i}", k, v])

                # Disks
                disks = getattr(self, "_last_disks", self.disk_mod.get_disk_partitions_and_usage())
                for disk in disks:
                    label = disk.get("Mountpoint", "?")
                    for k, v in disk.items():
                        writer.writerow([f"Disk {label}", k, v])

                # SMART
                smart = getattr(self, "_last_smart", self.disk_mod.get_smart_status())
                for k, v in smart.items():
                    writer.writerow(["SMART", k, v])

            messagebox.showinfo("Export Complete", f"Report saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def on_closing(self) -> None:
        """Signal the monitor thread to stop and destroy the window."""
        self._stop_event.set()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
