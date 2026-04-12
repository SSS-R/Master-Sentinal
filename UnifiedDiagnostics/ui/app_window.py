"""Main application window for Master Sentinal."""

from __future__ import annotations

import os
import platform
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from tkinter import TclError, filedialog, messagebox
from typing import Any, Callable

import customtkinter as ctk

from config import (
    APPEARANCE_MODE,
    APP_VERSION,
    COLOR_THEME,
    TEMP_ALERT_THRESHOLD_C,
    UPDATE_INTERVAL_SEC,
    WINDOW_GEOMETRY,
    WINDOW_TITLE,
)
from models.diagnostic_models import DiskPartition, GPUDevice, MemoryStats, ScanResult, SmartDriveStatus
from modules.board_diag import BoardDiagnostic
from modules.cpu_diag import CPUDiagnostic
from modules.disk_diag import DiskDiagnostic
from modules.full_scan import FullScanDiagnostic
from modules.gpu_diag import GPUDiagnostic
from modules.ram_diag import RAMDiagnostic
from services.full_scan_service import FullScanService, ScanTask
from services.app_logging import get_logger
from services.live_snapshot import DiagnosticSnapshot, LiveSnapshotCollector
from services.report_exporter import write_csv_report, write_html_report, write_json_report
from ui.components import InfoRow, MetricCard, SectionFrame


# Navigation items (order matters — rendered top to bottom)
NAV_ITEMS: list[str] = ["Dashboard", "CPU", "Memory", "GPU", "Storage", "System"]
NAV_SCAN_ITEM: str = "Full Scan"

LOGGER = get_logger(__name__)


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
        self.scan_logs: list[dict[str, str]] = []
        self.last_scan_started_at: datetime | None = None
        self.last_scan_finished_at: datetime | None = None
        self._active_scan_started_at = 0.0
        self._background_threads: list[threading.Thread] = []

        # Dashboard string vars
        self.cpu_usage_var = ctk.StringVar(value="0%")
        self.ram_usage_var = ctk.StringVar(value="0%")
        self.gpu_count_var = ctk.StringVar(value="Loading...")
        self.disk_count_var = ctk.StringVar(value="Loading...")
        self.health_summary_var = ctk.StringVar(value="Analyzing live system health...")
        self.scan_progress_var = ctk.StringVar(value="Ready to scan")
        self.scan_duration_var = ctk.StringVar(value="No scan run yet")

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
        self.monitor_thread = self._start_background_thread(self._monitor_loop)

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def _start_background_thread(self, target: Callable[..., None], *args: Any) -> threading.Thread:
        """Start and track a daemon background thread."""
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()
        self._background_threads.append(thread)
        return thread

    def _safe_after(self, callback: Callable[[], None]) -> None:
        """Schedule a UI callback unless shutdown is already in progress."""
        if self._stop_event.is_set():
            return
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except (RuntimeError, TclError):
            LOGGER.debug("Skipped UI callback during shutdown.")

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

        for col in range(2):
            grid.grid_columnconfigure(col, weight=1, uniform="dashboard")

        cards = [
            ("CPU Load", self.cpu_usage_var),
            ("RAM Usage", self.ram_usage_var),
            ("GPU Status", self.gpu_count_var),
            ("Disks Found", self.disk_count_var),
        ]
        for index, (title, value_var) in enumerate(cards):
            card = MetricCard(grid, title, value_var)
            card.grid(row=index // 2, column=index % 2, padx=10, pady=10, sticky="ew")

        # Export Report button
        export_btn = ctk.CTkButton(
            df, text="📄 Export Report (CSV)", font=("Roboto", 14), height=36,
            command=self._export_report,
        )
        export_btn.configure(text="Export Report (CSV, HTML, or JSON)")
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
        self._last_cpu_info = self.cpu_mod.get_cpu_details()
        for k, v in self._last_cpu_info.as_rows().items():
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
        self._set_empty_state(self.memory_info_frame.content, "Waiting for the first memory snapshot...")

    def setup_gpu_ui(self) -> None:
        """Prepare the GPU container (populated by the monitor loop)."""
        self.gpu_container = ctk.CTkFrame(self.frames["GPU"], fg_color="transparent")
        self.gpu_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.gpu_container, "Waiting for the first GPU snapshot...")

    def setup_storage_ui(self) -> None:
        """Prepare the Storage + SMART containers."""
        sf = self.frames["Storage"]

        self.storage_container = ctk.CTkFrame(sf, fg_color="transparent")
        self.storage_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.storage_container, "Waiting for the first storage snapshot...")

        self.smart_frame = SectionFrame(sf, "SMART Health Status")
        self.smart_frame.pack(fill="x", padx=20, pady=10)
        self._set_empty_state(self.smart_frame.content, "Waiting for the first SMART snapshot...")

    def setup_system_ui(self) -> None:
        """Build the static Motherboard & BIOS info section."""
        sf = self.frames["System"]

        self.sys_info_frame = SectionFrame(sf, "Motherboard & BIOS")
        self.sys_info_frame.pack(fill="x", padx=20, pady=10)

        self._last_board_info = self.board_mod.get_board_details()
        for k, v in self._last_board_info.as_rows().items():
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

        progress_row = ctk.CTkFrame(self.fs_container, fg_color="transparent")
        progress_row.pack(fill="x", pady=(0, 12))

        self.scan_progress_label = ctk.CTkLabel(
            progress_row,
            textvariable=self.scan_progress_var,
            anchor="w",
            text_color="gray70",
        )
        self.scan_progress_label.pack(side="left", fill="x", expand=True)

        self.scan_duration_label = ctk.CTkLabel(
            progress_row,
            textvariable=self.scan_duration_var,
            anchor="e",
            text_color="gray70",
        )
        self.scan_duration_label.pack(side="right")

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
        category_sections: dict[str, SectionFrame] = {}

        for task in self.check_list:
            category = task.category or "System Repair"
            if category not in category_sections:
                section = SectionFrame(routine_section.content, category)
                section.pack(fill="x", pady=(0, 12))
                category_sections[category] = section

            row = ctk.CTkFrame(category_sections[category].content)
            row.pack(fill="x", pady=5)

            lbl_name = ctk.CTkLabel(
                row, text=task.name, width=210, anchor="w",
                font=("Roboto", 14, "bold"),
            )
            lbl_name.pack(side="left", padx=10)

            lbl_status = ctk.CTkLabel(
                row, text="Pending", width=420,
                text_color="gray", anchor="w",
                justify="left",
                wraplength=520,
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
        self.scan_logs = []
        self.last_scan_started_at = datetime.now(timezone.utc)
        self.last_scan_finished_at = None
        self._active_scan_started_at = perf_counter()
        self.scan_progress_var.set(f"Running 0 of {len(self.check_list)} routine checks")
        self.scan_duration_var.set("Elapsed 0.0s")

        for lbl in self.scan_rows.values():
            lbl.configure(text="Pending", text_color="gray")

        self._start_background_thread(
            self._run_task_batch,
            self.check_list,
            self.scan_rows,
            self.start_scan_btn,
            "Start Health Scan",
        )

    def start_advanced_task(self, task: ScanTask) -> None:
        """Run a single advanced task after explicit user confirmation."""
        if task.requires_reboot or task.caution:
            title = "Restart Required" if task.requires_reboot else "Confirm Advanced Tool"
            restart_text = "\n\nThis may require a restart." if task.requires_reboot else ""
            approved = messagebox.askyesno(
                title,
                f"{task.name}\n\n{task.caution}{restart_text}\n\n"
                "Do you want to continue?",
            )
            if not approved:
                self.advanced_scan_rows[task.name].configure(text="Cancelled", text_color="yellow")
                return

        button = self.advanced_scan_buttons[task.name]
        button.configure(state="disabled", text="Running...")
        self.advanced_scan_rows[task.name].configure(text="Running...", text_color="orange")
        self._start_background_thread(self._run_single_task, task)

    def _run_task_batch(
        self,
        tasks: list[ScanTask],
        row_map: dict[str, ctk.CTkLabel],
        trigger_button: ctk.CTkButton,
        idle_text: str,
    ) -> None:
        """Execute a group of checks sequentially in a background thread."""
        total = len(tasks)
        for index, task in enumerate(tasks, start=1):
            if self._stop_event.is_set():
                break
            self._ui_scan_progress(index - 1, total, "Running")
            self._ui_scan_status(row_map, task.name, "Running...", "orange")
            started = perf_counter()
            try:
                success, output = task.runner()
            except Exception as exc:
                self._finalize_scan_status(row_map, ScanResult.from_exception(task.name, exc), perf_counter() - started)
                continue

            self._finalize_scan_status(
                row_map,
                ScanResult.from_runner_output(task.name, success, output),
                perf_counter() - started,
            )
            self._ui_scan_progress(index, total, "Running")

        if self._stop_event.is_set():
            return
        self.last_scan_finished_at = datetime.now(timezone.utc)
        elapsed = perf_counter() - self._active_scan_started_at
        self._safe_after(lambda: self.scan_progress_var.set(f"Finished {total} of {total} checks"))
        self._safe_after(lambda: self.scan_duration_var.set(f"Completed in {elapsed:.1f}s"))
        self._safe_after(lambda: trigger_button.configure(state="normal", text=idle_text))

    def _run_single_task(self, task: ScanTask) -> None:
        """Execute one advanced task in a background thread."""
        if self._stop_event.is_set():
            return
        self._safe_after(lambda: self.scan_progress_var.set(f"Running {task.name}"))
        started = perf_counter()
        try:
            success, output = task.runner()
        except Exception as exc:
            self._finalize_scan_status(
                self.advanced_scan_rows,
                ScanResult.from_exception(task.name, exc),
                perf_counter() - started,
            )
        else:
            self._finalize_scan_status(
                self.advanced_scan_rows,
                ScanResult.from_runner_output(task.name, success, output),
                perf_counter() - started,
            )
        finally:
            elapsed = perf_counter() - started
            button = self.advanced_scan_buttons[task.name]
            self._safe_after(lambda: self.scan_progress_var.set(f"Finished {task.name}"))
            self._safe_after(lambda: self.scan_duration_var.set(f"Last advanced tool: {elapsed:.1f}s"))
            self._safe_after(lambda: button.configure(state="normal", text=task.button_text))

    def _finalize_scan_status(
        self,
        row_map: dict[str, ctk.CTkLabel],
        result: ScanResult,
        duration_sec: float,
    ) -> None:
        """Map scan output into user-facing status text."""
        self._ui_scan_status(
            row_map,
            result.task_name,
            f"{result.display_text} ({duration_sec:.1f}s)",
            result.status_color,
        )
        self.scan_logs.append(
            {
                "task": result.task_name,
                "status": "success" if result.success else "failed",
                "duration": f"{duration_sec:.1f}s",
                "message": result.message,
                "display_text": result.display_text,
                "log_message": result.log_message,
            }
        )
        if result.success:
            LOGGER.info("%s", result.log_message or f"[{result.task_name}] SUCCESS: {result.message}")
        else:
            LOGGER.warning("%s", result.log_message or f"[{result.task_name}] FAILED: {result.message}")

    def _ui_scan_progress(self, completed: int, total: int, prefix: str) -> None:
        """Thread-safe helper to update batch scan progress."""
        elapsed = perf_counter() - self._active_scan_started_at
        self._safe_after(lambda: self.scan_progress_var.set(f"{prefix} {completed} of {total} checks"))
        self._safe_after(lambda: self.scan_duration_var.set(f"Elapsed {elapsed:.1f}s"))

    def _ui_scan_status(
        self,
        row_map: dict[str, ctk.CTkLabel],
        name: str,
        text: str,
        color: str,
    ) -> None:
        """Thread-safe helper to update a scan-row label."""
        self._safe_after(lambda: row_map[name].configure(text=text, text_color=color))

    # ------------------------------------------------------------------
    # Real-time monitor
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Periodically poll diagnostics and schedule UI updates."""
        while not self._stop_event.is_set():
            try:
                snapshot = self.snapshot_collector.collect()
                self._safe_after(lambda current=snapshot: self._apply_snapshot(current))

            except Exception as e:
                LOGGER.exception("Live monitor loop failed: %s", e)
                self._safe_after(
                    lambda: self.health_summary_var.set("Live monitoring hit an error. Check logs for details.")
                )

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

        self._last_gpu_devices = snapshot.gpu_devices
        self._last_disk_partitions = snapshot.disk_partitions
        self._last_smart_drives = snapshot.smart_drives
        self._last_memory_stats = snapshot.memory_stats
        self._last_health_summary = snapshot.health_summary
        self._last_diagnostic_report = snapshot.diagnostic_report

        self._update_health_summary(snapshot.health_summary)
        self._update_ui(
            snapshot.per_core,
            snapshot.memory_stats,
            snapshot.gpu_devices,
            snapshot.disk_partitions,
            snapshot.smart_drives,
        )

    def _update_health_summary(self, summary: Any) -> None:
        """Refresh the dashboard health summary and findings."""
        score = getattr(summary, "health_score", None)
        rollup = getattr(summary, "severity_rollup", "")
        if score is not None:
            self.health_summary_var.set(f"Health score {score}/100 - {summary.headline} ({rollup})")
        else:
            self.health_summary_var.set(summary.headline)
        self.health_summary_label.configure(text_color=self._health_status_color(summary.overall_status))

        for child in self.health_findings_container.winfo_children():
            child.destroy()
        self.health_finding_labels = []

        for finding in summary.findings[:4]:
            action = getattr(finding, "recommended_action", "")
            state = getattr(finding, "state", None) or finding.severity
            persistence = getattr(finding, "persistence", "unknown")
            text = f"{finding.title}: {finding.message}"
            if action:
                text = f"{text} Action: {action}"

            row = ctk.CTkFrame(self.health_findings_container, fg_color="transparent")
            row.pack(fill="x", pady=3)

            badge = ctk.CTkLabel(
                row,
                text=f"{finding.severity.upper()} / {state} / {persistence}",
                width=190,
                fg_color=self._health_status_color(finding.severity),
                text_color="white",
                corner_radius=6,
                anchor="center",
            )
            badge.pack(side="left", padx=(0, 8), anchor="n")

            label = ctk.CTkLabel(
                row,
                text=text,
                text_color=self._health_status_color(finding.severity),
                anchor="w",
                justify="left",
                wraplength=860,
            )
            label.pack(side="left", fill="x", expand=True)
            self.health_finding_labels.append(label)

    def _update_ui(
        self,
        per_core: list[float],
        memory_stats: MemoryStats,
        gpu_devices: list[GPUDevice],
        disk_partitions: list[DiskPartition],
        smart_drives: list[SmartDriveStatus],
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
        memory_rows = memory_stats.as_rows()
        if not self.mem_widgets:
            for child in self.memory_info_frame.content.winfo_children():
                child.destroy()
            for k, v in memory_rows.items():
                row = InfoRow(self.memory_info_frame.content, k, str(v))
                row.pack(fill="x", pady=2)
                self.mem_widgets[k] = row
        else:
            for k, v in memory_rows.items():
                if k in self.mem_widgets:
                    self.mem_widgets[k].value.configure(text=str(v))

        # --- GPU / Disk / SMART — via generic helper ---
        self._update_typed_device_section(
            container=self.gpu_container,
            items=gpu_devices,
            cache=self.gpu_widgets,
            key_fn=lambda gpu: gpu.device_id or gpu.name or "gpu-error",
            title_fn=lambda gpu, i: f"GPU {i + 1}: {gpu.name or 'Unknown'}",
            rows_fn=lambda gpu: gpu.metric_rows(),
            alert_rules={"Temperature": self._temp_alert_color},
        )

        self._update_typed_device_section(
            container=self.storage_container,
            items=disk_partitions,
            cache=self.disk_widgets,
            key_fn=lambda disk: disk.mountpoint or disk.device or "disk-error",
            title_fn=lambda disk, i: f"{disk.device or '?'} ({disk.mountpoint or '?'})",
            rows_fn=lambda disk: disk.metric_rows(),
        )

        # SMART — flat key→value (no nested dicts), use simpler path
        if not smart_drives:
            self._set_empty_state(self.smart_frame.content, "No SMART diagnostics are available yet.")
            self.smart_widgets = {}
            return

        current_smart_keys = [smart_drive.label_and_value()[0] for smart_drive in smart_drives]
        if current_smart_keys != list(self.smart_widgets.keys()):
            for child in self.smart_frame.content.winfo_children():
                child.destroy()
            self.smart_widgets = {}
            for smart_drive in smart_drives:
                k, v = smart_drive.label_and_value()
                r = InfoRow(self.smart_frame.content, k, str(v))
                r.pack(fill="x", pady=2)
                self.smart_widgets[k] = r
        else:
            for smart_drive in smart_drives:
                k, v = smart_drive.label_and_value()
                if k in self.smart_widgets:
                    self.smart_widgets[k].value.configure(text=str(v))

    # ------------------------------------------------------------------
    # Generic device-section updater (eliminates GPU/Disk duplication)
    # ------------------------------------------------------------------

    @staticmethod
    def _set_empty_state(container: ctk.CTkBaseClass, message: str) -> None:
        """Replace a container's children with a quiet empty-state message."""
        for child in container.winfo_children():
            child.destroy()
        label = ctk.CTkLabel(
            container,
            text=message,
            text_color="gray70",
            anchor="w",
            justify="left",
        )
        label.pack(fill="x", padx=10, pady=10)

    def _update_typed_device_section(
        self,
        container: ctk.CTkFrame,
        items: list[Any],
        cache: dict[str, dict[str, InfoRow]],
        key_fn: Callable[[Any], str],
        title_fn: Callable[[Any, int], str],
        rows_fn: Callable[[Any], dict[str, str]],
        alert_rules: dict[str, Callable[[str], str | None]] | None = None,
    ) -> None:
        """Compare typed device items against cached widgets and rebuild when needed."""
        rules = alert_rules or {}

        if not items:
            self._set_empty_state(container, "No diagnostics are available for this section yet.")
            cache.clear()
            return

        current_sigs = [key_fn(item) for item in items]
        cached_sigs = list(cache.keys())

        if current_sigs != cached_sigs:
            for child in container.winfo_children():
                child.destroy()
            cache.clear()

            for i, item in enumerate(items):
                sid = key_fn(item)
                section = SectionFrame(container, title_fn(item, i))
                section.pack(fill="x", pady=10)

                rows: dict[str, InfoRow] = {}
                for k, v in rows_fn(item).items():
                    r = InfoRow(section.content, k, str(v))
                    r.pack(fill="x", pady=2)
                    rows[k] = r
                    color = rules.get(k, lambda _: None)(str(v))
                    if color:
                        r.value.configure(text_color=color)
                cache[sid] = rows
        else:
            for item in items:
                sid = key_fn(item)
                if sid in cache:
                    rows = cache[sid]
                    for k, v in rows_fn(item).items():
                        if k in rows:
                            rows[k].value.configure(text=str(v))
                            color = rules.get(k, lambda _: None)(str(v))
                            if color:
                                rows[k].value.configure(text_color=color)
                            else:
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

    def _build_report_payload(self) -> dict[str, Any]:
        """Build a JSON-serializable report payload from the latest diagnostics."""
        cpu_info = getattr(self, "_last_cpu_info", None) or self.cpu_mod.get_cpu_details()
        board_info = getattr(self, "_last_board_info", None) or self.board_mod.get_board_details()
        memory_stats = getattr(self, "_last_memory_stats", None) or self.ram_mod.get_ram_stats()
        gpu_devices = getattr(self, "_last_gpu_devices", None) or self.gpu_mod.get_gpu_devices()
        disk_partitions = getattr(self, "_last_disk_partitions", None) or self.disk_mod.get_disk_partitions()
        smart_drives = getattr(self, "_last_smart_drives", None) or self.disk_mod.get_smart_drive_statuses()
        health_summary = getattr(self, "_last_health_summary", None)
        diagnostic_report = getattr(self, "_last_diagnostic_report", None)

        metadata = {
            "app_name": WINDOW_TITLE,
            "app_version": APP_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "os": platform.platform(),
            "machine": platform.machine(),
            "running_as_admin": self._is_running_as_admin(),
            "workspace": os.getcwd(),
        }
        if self.last_scan_started_at:
            metadata["last_scan_started_at"] = self.last_scan_started_at.isoformat()
        if self.last_scan_finished_at:
            metadata["last_scan_finished_at"] = self.last_scan_finished_at.isoformat()

        health_payload: dict[str, Any] = {
            "overall_status": "",
            "headline": "No live health summary captured yet.",
            "score": "",
            "severity_rollup": "",
            "severity_counts": {},
            "findings": [],
        }
        if health_summary is not None:
            health_payload = {
                "overall_status": health_summary.overall_status,
                "headline": health_summary.headline,
                "score": getattr(health_summary, "health_score", ""),
                "severity_rollup": getattr(health_summary, "severity_rollup", ""),
                "severity_counts": getattr(health_summary, "severity_counts", {}),
                "findings": [
                    {
                        "title": finding.title,
                        "message": finding.message,
                        "severity": finding.severity,
                        "recommended_action": getattr(finding, "recommended_action", ""),
                        "state": getattr(finding, "state", ""),
                        "persistence": getattr(finding, "persistence", ""),
                    }
                    for finding in health_summary.findings
                ],
            }

        return {
            "metadata": metadata,
            "sections": {
                "CPU": {"Usage": self.cpu_usage_var.get(), **cpu_info.as_rows()},
                "System": board_info.as_rows(),
                "RAM": memory_stats.as_rows(),
                "GPU": self._device_rows(gpu_devices),
                "Disk": self._device_rows(disk_partitions, label_attr="mountpoint"),
                "SMART": dict(smart_drive.label_and_value() for smart_drive in smart_drives),
            },
            "health": health_payload,
            "diagnostic_report": [
                {
                    "source": issue.source,
                    "category": issue.category,
                    "message": issue.message,
                    "severity": issue.severity,
                }
                for issue in diagnostic_report.entries()
            ] if diagnostic_report is not None else [],
            "scan_logs": list(self.scan_logs),
        }

    @staticmethod
    def _device_rows(items: list[Any], label_attr: str = "name") -> dict[str, str]:
        """Flatten device rows into report-friendly key/value content."""
        rows: dict[str, str] = {}
        for index, item in enumerate(items, start=1):
            label = getattr(item, label_attr, "") or getattr(item, "device", "") or f"Device {index}"
            for key, value in item.as_dict().items():
                rows[f"{label} - {key}"] = str(value)
        return rows

    def _is_running_as_admin(self) -> bool:
        """Return whether the app is currently elevated."""
        try:
            return self.full_scan_mod.is_admin()
        except Exception:
            return False

    def _export_report(self) -> None:
        """Save current diagnostics snapshot to CSV, HTML, or JSON."""
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("HTML files", "*.html"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
            initialfile=f"MasterSentinal_Report_{datetime.now():%Y%m%d_%H%M%S}.csv",
        )
        if not path:
            return

        try:
            payload = self._build_report_payload()
            suffix = Path(path).suffix.lower()
            if suffix == ".json":
                write_json_report(path, payload)
            elif suffix in {".html", ".htm"}:
                write_html_report(path, payload)
            else:
                write_csv_report(path, payload)
            messagebox.showinfo("Export Complete", f"Report saved to:\n{path}")
        except Exception as e:
            LOGGER.exception("Report export failed: %s", e)
            messagebox.showerror("Export Failed", str(e))

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def on_closing(self) -> None:
        """Signal the monitor thread to stop and destroy the window."""
        self._stop_event.set()
        for thread in list(self._background_threads):
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=0.2)
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
