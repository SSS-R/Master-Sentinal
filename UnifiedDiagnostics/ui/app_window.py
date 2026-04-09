"""Main application window for Master Sentinal."""

from __future__ import annotations

import csv
import threading
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
from services.full_scan_service import FullScanService, ScanTask
from services.live_snapshot import DiagnosticSnapshot, LiveSnapshotCollector
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
        self.snapshot_collector = LiveSnapshotCollector(
            cpu_mod=self.cpu_mod,
            ram_mod=self.ram_mod,
            gpu_mod=self.gpu_mod,
            disk_mod=self.disk_mod,
        )
        self.scan_service = FullScanService(self.full_scan_mod)

        # Dashboard string vars
        self.cpu_usage_var = ctk.StringVar(value="0%")
        self.ram_usage_var = ctk.StringVar(value="0%")
        self.gpu_count_var = ctk.StringVar(value="Searching...")
        self.disk_count_var = ctk.StringVar(value="Scanning...")
        self.health_summary_var = ctk.StringVar(value="Analyzing live system health...")

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

        self.health_frame = SectionFrame(df, "Health Overview")
        self.health_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.health_summary_label = ctk.CTkLabel(
            self.health_frame.content,
            textvariable=self.health_summary_var,
            font=("Roboto", 16, "bold"),
            anchor="w",
            justify="left",
        )
        self.health_summary_label.pack(fill="x", pady=(0, 8))

        self.health_findings_container = ctk.CTkFrame(self.health_frame.content, fg_color="transparent")
        self.health_findings_container.pack(fill="x")
        self.health_finding_labels: list[ctk.CTkLabel] = []

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
            self.fs_container, text="Start Health Scan",
            command=self.start_full_scan, font=("Roboto", 16), height=40,
        )
        self.start_scan_btn.pack(fill="x", pady=(0, 20))

        info_label = ctk.CTkLabel(
            self.fs_container,
            text="Routine health checks run together. Riskier tools are listed separately below.",
            text_color="gray70",
            anchor="w",
            justify="left",
        )
        info_label.pack(fill="x", pady=(0, 15))

        routine_section = SectionFrame(self.fs_container, "Routine Health Checks")
        routine_section.pack(fill="x", pady=(0, 20))

        self.scan_rows: dict[str, ctk.CTkLabel] = {}
        self.check_list = self.scan_service.get_routine_tasks()

        for task in self.check_list:
            row = ctk.CTkFrame(routine_section.content)
            row.pack(fill="x", pady=5)

            lbl_name = ctk.CTkLabel(
                row, text=task.name, width=200, anchor="w",
                font=("Roboto", 14, "bold"),
            )
            lbl_name.pack(side="left", padx=10)

            lbl_status = ctk.CTkLabel(
                row, text="Pending", width=300,
                text_color="gray", anchor="w",
            )
            lbl_status.pack(side="left", padx=10)

            self.scan_rows[task.name] = lbl_status

        advanced_section = SectionFrame(self.fs_container, "Advanced Tools")
        advanced_section.pack(fill="x", pady=(0, 10))

        advanced_hint = ctk.CTkLabel(
            advanced_section.content,
            text="Use these only when you intentionally want deeper troubleshooting or a restart.",
            text_color="#f4b400",
            anchor="w",
            justify="left",
        )
        advanced_hint.pack(fill="x", pady=(0, 10))

        self.advanced_scan_rows: dict[str, ctk.CTkLabel] = {}
        self.advanced_scan_buttons: dict[str, ctk.CTkButton] = {}

        for task in self.scan_service.get_advanced_tasks():
            card = ctk.CTkFrame(advanced_section.content)
            card.pack(fill="x", pady=5)

            text_col = ctk.CTkFrame(card, fg_color="transparent")
            text_col.pack(side="left", fill="both", expand=True, padx=10, pady=10)

            name_label = ctk.CTkLabel(
                text_col,
                text=task.name,
                font=("Roboto", 14, "bold"),
                anchor="w",
            )
            name_label.pack(fill="x")

            caution_label = ctk.CTkLabel(
                text_col,
                text=task.caution,
                text_color="gray70",
                justify="left",
                anchor="w",
                wraplength=520,
            )
            caution_label.pack(fill="x", pady=(2, 6))

            status_label = ctk.CTkLabel(
                text_col,
                text="Ready",
                text_color="gray",
                anchor="w",
            )
            status_label.pack(fill="x")

            button = ctk.CTkButton(
                card,
                text=task.button_text,
                command=lambda current_task=task: self.start_advanced_task(current_task),
                width=190,
            )
            button.pack(side="right", padx=10, pady=10)

            self.advanced_scan_rows[task.name] = status_label
            self.advanced_scan_buttons[task.name] = button

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

        threading.Thread(
            target=self._run_task_batch,
            args=(self.check_list, self.scan_rows, self.start_scan_btn, "Start Health Scan"),
            daemon=True,
        ).start()

    def start_advanced_task(self, task: ScanTask) -> None:
        """Run a single advanced task after explicit user confirmation."""
        if task.requires_reboot:
            approved = messagebox.askyesno(
                "Restart Required",
                f"{task.name} will schedule a restart-based diagnostic.\n\n"
                "Do you want to continue?",
            )
            if not approved:
                self.advanced_scan_rows[task.name].configure(text="Cancelled", text_color="yellow")
                return

        button = self.advanced_scan_buttons[task.name]
        button.configure(state="disabled", text="Running...")
        self.advanced_scan_rows[task.name].configure(text="Running...", text_color="orange")
        threading.Thread(target=self._run_single_task, args=(task,), daemon=True).start()

    def _run_task_batch(
        self,
        tasks: list[ScanTask],
        row_map: dict[str, ctk.CTkLabel],
        trigger_button: ctk.CTkButton,
        idle_text: str,
    ) -> None:
        """Execute a group of checks sequentially in a background thread."""
        for task in tasks:
            self._ui_scan_status(row_map, task.name, "Running...", "orange")
            try:
                success, output = task.runner()
            except Exception as exc:
                self._ui_scan_status(row_map, task.name, f"Error: {str(exc)[:50]}", "red")
                print(f"[{task.name}] EXCEPTION: {exc}")
                continue

            self._finalize_scan_status(row_map, task.name, success, output)

        self.after(0, lambda: trigger_button.configure(state="normal", text=idle_text))

    def _run_single_task(self, task: ScanTask) -> None:
        """Execute one advanced task in a background thread."""
        try:
            success, output = task.runner()
        except Exception as exc:
            self._ui_scan_status(self.advanced_scan_rows, task.name, f"Error: {str(exc)[:50]}", "red")
            print(f"[{task.name}] EXCEPTION: {exc}")
        else:
            self._finalize_scan_status(self.advanced_scan_rows, task.name, success, output)
        finally:
            button = self.advanced_scan_buttons[task.name]
            self.after(0, lambda: button.configure(state="normal", text=task.button_text))

    def _finalize_scan_status(
        self,
        row_map: dict[str, ctk.CTkLabel],
        task_name: str,
        success: bool,
        output: str,
    ) -> None:
        """Map scan output into user-facing status text."""
        if success:
            display = output if len(output) < 50 else "OK"
            self._ui_scan_status(row_map, task_name, display, "green")
            return

        if "Not a Laptop" in output:
            self._ui_scan_status(row_map, task_name, "Skipped (Not a Laptop)", "yellow")
        else:
            self._ui_scan_status(row_map, task_name, output, "red")
            print(f"[{task_name}] {output}")

    def _ui_scan_status(
        self,
        row_map: dict[str, ctk.CTkLabel],
        name: str,
        text: str,
        color: str,
    ) -> None:
        """Thread-safe helper to update a scan-row label."""
        self.after(0, lambda: row_map[name].configure(text=text, text_color=color))

    # ------------------------------------------------------------------
    # Real-time monitor
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Periodically poll diagnostics and schedule UI updates."""
        while not self._stop_event.is_set():
            try:
                snapshot = self.snapshot_collector.collect()
                self.after(0, lambda current=snapshot: self._apply_snapshot(current))

            except Exception as e:
                print(f"Error in monitor: {e}")

            # Use Event.wait instead of time.sleep for clean cancellation
            self._stop_event.wait(UPDATE_INTERVAL_SEC)

    # ------------------------------------------------------------------
    # UI update (runs on main thread)
    # ------------------------------------------------------------------

    def _apply_snapshot(self, snapshot: DiagnosticSnapshot) -> None:
        """Apply a collected snapshot on the Tk main thread."""
        self.cpu_usage_var.set(snapshot.summary.cpu_usage_text)
        self.ram_usage_var.set(snapshot.summary.ram_usage_text)
        self.gpu_count_var.set(snapshot.summary.gpu_status_text)
        self.disk_count_var.set(snapshot.summary.disk_status_text)

        self._last_gpus = snapshot.gpus
        self._last_disks = snapshot.disks
        self._last_smart = snapshot.smart
        self._last_ram = snapshot.ram
        self._last_health_summary = snapshot.health_summary

        self._update_health_summary(snapshot.health_summary)
        self._update_ui(
            snapshot.per_core,
            snapshot.ram,
            snapshot.gpus,
            snapshot.disks,
            snapshot.smart,
        )

    def _update_health_summary(self, summary: Any) -> None:
        """Refresh the dashboard health summary and findings."""
        self.health_summary_var.set(summary.headline)
        self.health_summary_label.configure(text_color=self._health_status_color(summary.overall_status))

        for child in self.health_findings_container.winfo_children():
            child.destroy()
        self.health_finding_labels = []

        for finding in summary.findings[:4]:
            label = ctk.CTkLabel(
                self.health_findings_container,
                text=f"{finding.title}: {finding.message}",
                text_color=self._health_status_color(finding.severity),
                anchor="w",
                justify="left",
                wraplength=860,
            )
            label.pack(fill="x", pady=2)
            self.health_finding_labels.append(label)

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

    @staticmethod
    def _health_status_color(status: str) -> Any:
        """Map a health status to a user-facing accent colour."""
        return {
            "ok": "#2e8b57",
            "info": "#4f83cc",
            "warning": "#f4b400",
            "critical": "#d93025",
        }.get(status, ("gray10", "gray90"))

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

                # Health Summary
                health_summary = getattr(self, "_last_health_summary", None)
                if health_summary is not None:
                    writer.writerow(["Health", "Overall Status", health_summary.overall_status])
                    writer.writerow(["Health", "Headline", health_summary.headline])
                    for idx, finding in enumerate(health_summary.findings, start=1):
                        writer.writerow([f"Health Finding {idx}", finding.title, finding.message])

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
