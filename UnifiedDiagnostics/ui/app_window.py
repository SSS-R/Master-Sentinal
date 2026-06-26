"""Main application window for Master Sentinal."""

from __future__ import annotations

import os
import platform
import subprocess
import threading
import webbrowser
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
    DEEP_REFRESH_INTERVAL_SEC,
    DONATE_URL,
    REPO_URL,
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
from services.error_explanations import explain_error_message
from services.live_snapshot import (
    DiagnosticSnapshot,
    LiveSnapshotCollector,
    NetworkDiagnostic as LiveNetworkDiagnostic,
    SecurityDiagnostic as LiveSecurityDiagnostic,
    StartupServiceDiagnostic,
    WindowsUpdateDiagnostic as LiveWindowsUpdateDiagnostic,
)
from services.live_meters import SpeedTester
from services.post_reboot_results import PostRebootResultReader
from services.report_exporter import write_csv_report, write_html_report, write_json_report
from services.snapshot_history import SnapshotHistory
from services.monitoring_alerts import MonitoringAlerts, AlertSeverity
from services.scan_presets import ScanPresetService, ScanPreset
from services.issue_bundle import IssueBundleExporter
from ui.components import InfoRow, LiveChart, MetricCard, SectionFrame


# Navigation items (order matters — rendered top to bottom)
NAV_ITEMS: list[str] = ["Dashboard", "CPU", "Memory", "GPU", "Storage", "Security", "Network", "Startup", "Update", "Trends", "System"]
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
            self.nav_frame, text="Master Sentinal",
            font=ctk.CTkFont(size=18, weight="bold"),
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
        self.security_mod = self.snapshot_collector.security_mod or LiveSecurityDiagnostic()
        self.network_mod = self.snapshot_collector.network_mod or LiveNetworkDiagnostic()
        self.startup_mod = self.snapshot_collector.startup_mod or StartupServiceDiagnostic()
        self.update_mod = self.snapshot_collector.windows_update_mod or LiveWindowsUpdateDiagnostic()
        # New services for v1.0
        self.snapshot_history = SnapshotHistory()
        self.monitoring_alerts = MonitoringAlerts()
        self.scan_preset_service = ScanPresetService(self.full_scan_mod)
        self.issue_bundle_exporter = IssueBundleExporter()
        self.scan_service = FullScanService(self.full_scan_mod)
        # On-demand internet speed test + post-reboot result reader (memory test).
        self.speed_tester = SpeedTester()
        self.post_reboot_reader = PostRebootResultReader()
        self.scan_logs: list[dict[str, str]] = []
        self.last_scan_started_at: datetime | None = None
        self.last_scan_finished_at: datetime | None = None
        self.last_scan_report_path: str | None = None
        self._active_scan_started_at = 0.0
        self._background_threads: list[threading.Thread] = []
        self._refresh_in_progress: dict[str, bool] = {}
        # Global shutdown event (gates UI callbacks). Created before any tab
        # setup so early background work (e.g. the memory-result check) can use
        # _safe_after safely; the monitor threads that observe it start later.
        self._stop_event = threading.Event()
        # Cancels an in-progress health scan without touching the global
        # shutdown event (which would also stop live monitoring).
        self._scan_cancel_event = threading.Event()
        self._speed_test_running = False
        # Cache of the expensive PowerShell/WMI diagnostics. Starts empty and is
        # filled by the deep-collect loop; the fast loop reuses it every tick so
        # the live UI never blocks on PowerShell.
        self._deep_cache = self.snapshot_collector.empty_deep()
        # Latest GPU devices from the fast loop, read by the temperature alert
        # monitor. Initialized empty so the alert thread can read it safely
        # before the first snapshot lands.
        self._last_gpu_devices: list[GPUDevice] = []

        # Dashboard string vars
        self.cpu_usage_var = ctk.StringVar(value="0%")
        self.ram_usage_var = ctk.StringVar(value="0%")
        self.gpu_count_var = ctk.StringVar(value="Loading...")
        self.disk_count_var = ctk.StringVar(value="Loading...")
        self.health_summary_var = ctk.StringVar(value="Analyzing live system health...")
        self.scan_progress_var = ctk.StringVar(value="Ready to scan")
        self.scan_duration_var = ctk.StringVar(value="No scan run yet")
        self.net_down_var = ctk.StringVar(value="0 B/s")
        self.net_up_var = ctk.StringVar(value="0 B/s")
        self.speedtest_var = ctk.StringVar(value="Run a speed test to measure your connection.")
        self.mem_result_var = ctk.StringVar(value="No memory test results loaded yet.")

        # Build each tab's UI
        self.setup_dashboard()
        self.setup_cpu_ui()
        self.setup_memory_ui()
        self.setup_gpu_ui()
        self.setup_storage_ui()
        self.setup_security_ui()
        self.setup_network_ui()
        self.setup_startup_ui()
        self.setup_update_ui()
        self.setup_trends_ui()
        self.setup_system_ui()
        self.setup_full_scan_ui()

        self.select_frame_by_name("Dashboard")

        # Monitoring threads (use Event for clean shutdown).
        # Fast loop: cheap psutil metrics every UPDATE_INTERVAL_SEC.
        # Deep loop: expensive PowerShell/WMI diagnostics on a slow cadence.
        self.monitor_thread = self._start_background_thread(self._monitor_loop)
        self.deep_monitor_thread = self._start_background_thread(self._deep_monitor_loop)

        # Start monitoring alerts (GPU temperature fed from the live snapshot)
        self.monitoring_alerts.add_alert_callback(self._on_monitoring_alert)
        self.monitoring_alerts.set_temperature_provider(self._current_gpu_temperatures)
        self.monitoring_alerts.start_monitoring()

        # Toast container (overlay for notifications)
        self.toast_container = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "gray10"))
        self.toast_container.grid(row=0, column=0, columnspan=2, sticky="ne", padx=20, pady=20)
        self.toast_container.grid_forget()  # Hidden by default
        self.toast_labels: list[ctk.CTkLabel] = []

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
            ("Network ↓ Download", self.net_down_var),
            ("Network ↑ Upload", self.net_up_var),
        ]
        for index, (title, value_var) in enumerate(cards):
            card = MetricCard(grid, title, value_var)
            card.grid(row=index // 2, column=index % 2, padx=10, pady=10, sticky="ew")

        # Export Report button
        export_btn = ctk.CTkButton(
            df, text="Export Report (CSV, HTML, or JSON)", font=("Roboto", 14), height=36,
            command=self._export_report,
        )
        export_btn.pack(fill="x", padx=20, pady=(0, 10))

        # Export Issue Bundle button
        bundle_btn = ctk.CTkButton(
            df, text="📦 Export Diagnostic Bundle", font=("Roboto", 14), height=36,
            command=self._export_issue_bundle,
        )
        bundle_btn.pack(fill="x", padx=20, pady=(0, 10))

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

        # Live chart with a histogram (per-thread) ⇄ line (overall history) toggle.
        chart_header = ctk.CTkFrame(cf, fg_color="transparent")
        chart_header.pack(fill="x", padx=20, pady=(20, 6))

        self.cpu_chart_title_var = ctk.StringVar(value="Per-Thread Usage (Histogram)")
        ctk.CTkLabel(
            chart_header, textvariable=self.cpu_chart_title_var,
            font=("Roboto", 16, "bold"),
        ).pack(side="left")

        self.cpu_chart_toggle_btn = ctk.CTkButton(
            chart_header, text="Switch to Line Graph", width=170, height=30,
            command=self._toggle_cpu_chart,
        )
        self.cpu_chart_toggle_btn.pack(side="right")

        self.cpu_chart = LiveChart(cf, height=180, mode="bars")
        self.cpu_chart.pack(fill="x", padx=20, pady=(0, 10))

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
        mf = self.frames["Memory"]

        ctk.CTkLabel(
            mf, text="Real-time RAM Usage (%)", font=("Roboto", 16, "bold"),
        ).pack(pady=(20, 6), padx=20, anchor="w")

        self.ram_chart = LiveChart(mf, height=160, mode="line")
        self.ram_chart.pack(fill="x", padx=20, pady=(0, 10))

        self.memory_info_frame = SectionFrame(mf, "Memory Statistics")
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

    def setup_security_ui(self) -> None:
        """Build the Security diagnostics section."""
        sf = self.frames["Security"]

        title = ctk.CTkLabel(
            sf, text="Security & Privacy Status",
            font=("Roboto", 24, "bold"),
        )
        title.pack(anchor="w", padx=20, pady=(20, 10))

        hint = ctk.CTkLabel(
            sf,
            text="Monitor Defender, Firewall, and BitLocker encryption status.",
            text_color="gray70",
            anchor="w",
        )
        hint.pack(anchor="w", padx=20, pady=(0, 20))

        self.security_container = ctk.CTkFrame(sf, fg_color="transparent")
        self.security_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.security_container, "Click 'Refresh' to load security status...")

        self.security_refresh_btn = ctk.CTkButton(
            sf, text="Refresh Status", height=36,
            command=self._refresh_security_ui,
        )
        self.security_refresh_btn.pack(fill="x", padx=20, pady=(0, 20))

        self.security_widgets: dict[str, InfoRow] = {}

    def setup_network_ui(self) -> None:
        """Build the Network diagnostics section."""
        sf = self.frames["Network"]

        title = ctk.CTkLabel(
            sf, text="Network Connectivity",
            font=("Roboto", 24, "bold"),
        )
        title.pack(anchor="w", padx=20, pady=(20, 10))

        hint = ctk.CTkLabel(
            sf,
            text="Check adapter status, DNS configuration, and gateway connectivity.",
            text_color="gray70",
            anchor="w",
        )
        hint.pack(anchor="w", padx=20, pady=(0, 20))

        # Live throughput + on-demand speed test.
        speed_frame = SectionFrame(sf, "Internet Speed")
        speed_frame.pack(fill="x", padx=20, pady=(0, 10))

        live_row = ctk.CTkFrame(speed_frame.content, fg_color="transparent")
        live_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(live_row, text="Live throughput:", text_color="gray60").pack(side="left", padx=(0, 10))
        ctk.CTkLabel(live_row, text="↓", font=("Roboto", 14, "bold")).pack(side="left")
        ctk.CTkLabel(live_row, textvariable=self.net_down_var, font=("Roboto", 14, "bold")).pack(side="left", padx=(2, 16))
        ctk.CTkLabel(live_row, text="↑", font=("Roboto", 14, "bold")).pack(side="left")
        ctk.CTkLabel(live_row, textvariable=self.net_up_var, font=("Roboto", 14, "bold")).pack(side="left", padx=(2, 0))

        self.speed_test_btn = ctk.CTkButton(
            speed_frame.content, text="Run Speed Test", height=36,
            command=self._run_speed_test,
        )
        self.speed_test_btn.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(
            speed_frame.content, textvariable=self.speedtest_var,
            text_color="gray70", anchor="w", justify="left", wraplength=820,
        ).pack(fill="x")

        self.network_container = ctk.CTkFrame(sf, fg_color="transparent")
        self.network_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.network_container, "Click 'Refresh' to load network status...")

        self.network_refresh_btn = ctk.CTkButton(
            sf, text="Refresh Status", height=36,
            command=self._refresh_network_ui,
        )
        self.network_refresh_btn.pack(fill="x", padx=20, pady=(0, 20))

        self.network_widgets: dict[str, dict[str, InfoRow]] = {}

    def setup_startup_ui(self) -> None:
        """Build the Startup diagnostics section."""
        sf = self.frames["Startup"]

        title = ctk.CTkLabel(
            sf, text="Startup Programs & Services",
            font=("Roboto", 24, "bold"),
        )
        title.pack(anchor="w", padx=20, pady=(20, 10))

        hint = ctk.CTkLabel(
            sf,
            text="Review startup items and detect services with slow startup times.",
            text_color="gray70",
            anchor="w",
        )
        hint.pack(anchor="w", padx=20, pady=(0, 20))

        self.startup_container = ctk.CTkFrame(sf, fg_color="transparent")
        self.startup_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.startup_container, "Click 'Refresh' to load startup items...")

        self.startup_refresh_btn = ctk.CTkButton(
            sf, text="Refresh Status", height=36,
            command=self._refresh_startup_ui,
        )
        self.startup_refresh_btn.pack(fill="x", padx=20, pady=(0, 20))

        self.startup_widgets: dict[str, InfoRow] = {}

    def setup_update_ui(self) -> None:
        """Build the Windows Update diagnostics section."""
        sf = self.frames["Update"]

        title = ctk.CTkLabel(
            sf, text="Windows Update Health",
            font=("Roboto", 24, "bold"),
        )
        title.pack(anchor="w", padx=20, pady=(20, 10))

        hint = ctk.CTkLabel(
            sf,
            text="Check Windows Update service status and detect pending reboots.",
            text_color="gray70",
            anchor="w",
        )
        hint.pack(anchor="w", padx=20, pady=(0, 20))

        self.update_container = ctk.CTkFrame(sf, fg_color="transparent")
        self.update_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.update_container, "Click 'Refresh' to load update status...")

        self.update_refresh_btn = ctk.CTkButton(
            sf, text="Refresh Status", height=36,
            command=self._refresh_update_ui,
        )
        self.update_refresh_btn.pack(fill="x", padx=20, pady=(0, 20))

        self.update_widgets: dict[str, InfoRow] = {}

    def setup_trends_ui(self) -> None:
        """Build the historical trends section."""
        tf = self.frames["Trends"]

        title = ctk.CTkLabel(
            tf, text="System Health Trends",
            font=("Roboto", 24, "bold"),
        )
        title.pack(anchor="w", padx=20, pady=(20, 10))

        hint = ctk.CTkLabel(
            tf,
            text="Track how your system health changes over time. Snapshots are saved automatically.",
            text_color="gray70",
            anchor="w",
        )
        hint.pack(anchor="w", padx=20, pady=(0, 20))

        # Trend metric selector
        selector_frame = ctk.CTkFrame(tf)
        selector_frame.pack(fill="x", padx=20, pady=10)

        selector_label = ctk.CTkLabel(
            selector_frame, text="View trend for:",
            font=("Roboto", 14),
        )
        selector_label.pack(side="left", padx=10, pady=10)

        self.trend_metric_var = ctk.StringVar(value="health_score")
        metric_selector = ctk.CTkOptionMenu(
            selector_frame, variable=self.trend_metric_var,
            values=["health_score", "cpu_usage", "ram_usage_percent", "disk_free_percent"],
            command=self._on_trend_metric_changed,
        )
        metric_selector.pack(side="left", padx=10, pady=10)

        refresh_btn = ctk.CTkButton(
            selector_frame, text="Refresh Trends", height=36,
            command=self._refresh_trends_ui,
        )
        refresh_btn.pack(side="right", padx=10, pady=10)

        self.trend_container = ctk.CTkFrame(tf, fg_color="transparent")
        self.trend_container.pack(fill="both", expand=True, padx=20, pady=10)
        self._set_empty_state(self.trend_container, "Click 'Refresh Trends' to load history...")

        self.trend_widgets: dict[str, InfoRow] = {}

    def setup_system_ui(self) -> None:
        """Build the static Motherboard & BIOS info section."""
        sf = self.frames["System"]

        self.sys_info_frame = SectionFrame(sf, "Motherboard & BIOS")
        self.sys_info_frame.pack(fill="x", padx=20, pady=10)

        self._last_board_info = self.board_mod.get_board_details()
        for k, v in self._last_board_info.as_rows().items():
            self.sys_info_frame.add_row(k, str(v))

        # About & Support
        about_frame = SectionFrame(sf, "About & Support")
        about_frame.pack(fill="x", padx=20, pady=10)

        about_frame.add_row("Application", WINDOW_TITLE)
        about_frame.add_row("Version", APP_VERSION)
        about_frame.add_row("License", "MIT (free and open source)")

        support_note = ctk.CTkLabel(
            about_frame.content,
            text=(
                "Master Sentinal is free and open source. If it helped you, a star on "
                "GitHub or an optional donation keeps it going — but it will always be free."
            ),
            text_color="gray70",
            anchor="w",
            justify="left",
            wraplength=900,
        )
        support_note.pack(fill="x", pady=(8, 8))

        button_row = ctk.CTkFrame(about_frame.content, fg_color="transparent")
        button_row.pack(fill="x", pady=(0, 4))

        github_btn = ctk.CTkButton(
            button_row, text="View on GitHub", height=36,
            command=lambda: self._open_url(REPO_URL),
        )
        github_btn.pack(side="left", padx=(0, 10))

        donate_btn = ctk.CTkButton(
            button_row, text="Support / Donate (optional)", height=36,
            fg_color="#2e8b57", hover_color="#256e46",
            command=lambda: self._open_url(DONATE_URL),
        )
        donate_btn.pack(side="left")

    def _open_url(self, url: str) -> None:
        """Open an external URL in the user's default browser."""
        try:
            webbrowser.open(url, new=2)
        except Exception as e:
            LOGGER.warning("Failed to open URL %s: %s", url, e)

    @staticmethod
    def _executable_path_from_command(command: str) -> str:
        """Extract the executable path from a startup command string.

        Startup commands may be quoted and carry arguments, e.g.
        ``"C:\\Program Files\\App\\app.exe" --minimized``. Return just the
        executable path, with surrounding quotes and trailing args removed.
        """
        command = (command or "").strip()
        if not command:
            return ""
        if command.startswith('"'):
            end = command.find('"', 1)
            return command[1:end] if end != -1 else command.strip('"')
        # Unquoted: cut at the first ".exe" boundary if present, else first space.
        lowered = command.lower()
        exe_index = lowered.find(".exe")
        if exe_index != -1:
            return command[: exe_index + 4]
        return command.split(" ", 1)[0]

    def _open_file_location(self, command: str) -> None:
        """Open Explorer at a startup item's executable, selecting the file."""
        path = self._executable_path_from_command(command)
        if not path:
            messagebox.showinfo("No Location", "This startup item has no file path to open.")
            return
        try:
            if os.path.isfile(path):
                # /select, highlights the file inside its folder.
                subprocess.run(["explorer", "/select,", path])
                return
            folder = os.path.dirname(path)
            if folder and os.path.isdir(folder):
                os.startfile(folder)  # type: ignore[attr-defined]
                return
            messagebox.showwarning(
                "Location Not Found",
                f"Could not find this file on disk:\n\n{path}\n\n"
                "The startup entry may point to a removed or renamed program.",
            )
        except Exception as e:
            LOGGER.warning("Failed to open file location for %s: %s", path, e)
            messagebox.showerror("Open Location Failed", str(e))

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

        # Scan preset selector
        preset_frame = ctk.CTkFrame(self.fs_container)
        preset_frame.pack(fill="x", pady=(0, 20))

        preset_label = ctk.CTkLabel(
            preset_frame, text="Scan Mode:",
            font=("Roboto", 14),
        )
        preset_label.pack(side="left", padx=10, pady=10)

        self.scan_preset_var = ctk.StringVar(value="Standard Scan")
        preset_selector = ctk.CTkOptionMenu(
            preset_frame, variable=self.scan_preset_var,
            values=["Quick Scan", "Standard Scan", "Deep Scan"],
            command=self._on_scan_preset_changed,
        )
        preset_selector.pack(side="left", padx=10, pady=10)

        # Preset description label
        self.preset_description_label = ctk.CTkLabel(
            self.fs_container,
            text="Full routine health check (10 min) - Includes SFC, DISM, Disk Check, Power & Battery diagnostics",
            text_color="gray70",
            anchor="w",
            justify="left",
        )
        self.preset_description_label.pack(fill="x", padx=20, pady=(0, 20))

        button_row = ctk.CTkFrame(self.fs_container, fg_color="transparent")
        button_row.pack(fill="x", pady=(0, 12))

        self.start_scan_btn = ctk.CTkButton(
            button_row, text="Start Health Scan",
            command=self.start_full_scan, font=("Roboto", 16), height=40,
        )
        self.start_scan_btn.pack(side="left", fill="x", expand=True)

        # Appears enabled only while a scan is running — cancels it (and
        # terminates the in-flight Windows tool) without killing live monitoring.
        self.stop_scan_btn = ctk.CTkButton(
            button_row, text="Stop Scan",
            command=self._stop_full_scan, font=("Roboto", 16), height=40,
            width=140, fg_color="#b03a2e", hover_color="#922d24",
            state="disabled",
        )
        self.stop_scan_btn.pack(side="right", padx=(10, 0))

        # Determinate progress bar that fills as checks complete.
        self.scan_progress_bar = ctk.CTkProgressBar(self.fs_container, height=14)
        self.scan_progress_bar.set(0)
        self.scan_progress_bar.pack(fill="x", pady=(0, 12))

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

        # Appears after a scan finishes — opens the friendly Master Sentinal
        # report (not Windows' raw, technical powercfg/battery files).
        self.view_report_btn = ctk.CTkButton(
            self.fs_container,
            text="View Scan Report",
            command=self._open_last_scan_report,
            font=("Roboto", 14),
            height=36,
            fg_color="#2e8b57",
            hover_color="#256f46",
            state="disabled",
        )
        self.view_report_btn.pack(fill="x", pady=(0, 20))

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

        # Results for scans that only finish after a restart (Memory Diagnostic).
        # Windows writes these to the Event Log during boot, so we read them back
        # here instead of leaving the user with no visible outcome.
        results_section = SectionFrame(self.fs_container, "Restart-Required Scan Results")
        results_section.pack(fill="x", pady=(10, 10))

        ctk.CTkLabel(
            results_section.content,
            text=(
                "The Windows Memory Diagnostic runs during a restart and reports its "
                "result afterwards. Click below after rebooting to see the outcome."
            ),
            text_color="gray70", anchor="w", justify="left", wraplength=820,
        ).pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            results_section.content, textvariable=self.mem_result_var,
            font=("Roboto", 14, "bold"), anchor="w", justify="left", wraplength=820,
        ).pack(fill="x", pady=(0, 8))

        self.mem_result_btn = ctk.CTkButton(
            results_section.content, text="Check Memory Test Result", height=36,
            command=self._refresh_memory_result,
        )
        self.mem_result_btn.pack(fill="x")

        # Surface any existing result automatically on first load.
        self._refresh_memory_result()

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

        # Get selected preset
        preset_name = self.scan_preset_var.get()
        preset_map = {
            "Quick Scan": ScanPreset.QUICK,
            "Standard Scan": ScanPreset.STANDARD,
            "Deep Scan": ScanPreset.DEEP,
        }
        preset = preset_map.get(preset_name, ScanPreset.STANDARD)
        tasks = self.scan_preset_service.get_tasks_for_preset(preset)

        # Safety gate: batch presets (e.g. Deep Scan) can include advanced tools
        # that change system state or require a restart (Driver Verifier, Memory
        # Diagnostic). The single-tool path confirms these individually, so the
        # batch path must too — otherwise picking Deep Scan would silently launch
        # them. Confirm once, up front, listing exactly what will run.
        risky_tasks = [
            task for task in tasks
            if getattr(task, "caution", "") or getattr(task, "requires_reboot", False)
        ]
        if risky_tasks:
            detail_lines = []
            for task in risky_tasks:
                note = getattr(task, "caution", "") or ""
                if getattr(task, "requires_reboot", False):
                    note = f"{note} This requires a restart.".strip()
                detail_lines.append(f"• {task.name}: {note}".strip())
            details = "\n\n".join(detail_lines)
            approved = messagebox.askyesno(
                "Confirm Advanced Tools",
                f"{preset_name} includes advanced tools that can change system state "
                f"or require a restart:\n\n{details}\n\nDo you want to continue?",
            )
            if not approved:
                self.scan_progress_var.set("Scan cancelled")
                return

        self._scan_cancel_event.clear()
        self.start_scan_btn.configure(state="disabled", text="Scanning...")
        self.stop_scan_btn.configure(state="normal")
        self.scan_progress_bar.set(0)
        self.scan_logs = []
        self.last_scan_started_at = datetime.now(timezone.utc)
        self.last_scan_finished_at = None
        self._active_scan_started_at = perf_counter()
        self.scan_progress_var.set(f"Running 0 of {len(tasks)} checks ({preset_name})")
        self.scan_duration_var.set("Elapsed 0.0s")

        for lbl in self.scan_rows.values():
            lbl.configure(text="Pending", text_color="gray")

        self._start_background_thread(
            self._run_task_batch,
            tasks,
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
        completed = 0
        cancelled = False
        for index, task in enumerate(tasks, start=1):
            if self._stop_event.is_set():
                return
            if self._scan_cancel_event.is_set():
                cancelled = True
                break
            self._ui_scan_progress(index - 1, total, "Running")
            self._ui_scan_status(row_map, task.name, "Running...", "orange")
            started = perf_counter()
            try:
                success, output = task.runner()
            except Exception as exc:
                self._finalize_scan_status(row_map, ScanResult.from_exception(task.name, exc), perf_counter() - started)
                completed = index
                self._ui_scan_progress(index, total, "Running")
                continue

            # A cancel during a long check terminates the tool; report it as such
            # rather than as a genuine failure.
            if self._scan_cancel_event.is_set():
                self._ui_scan_status(row_map, task.name, "Stopped", "gray")
                cancelled = True
                break

            self._finalize_scan_status(
                row_map,
                ScanResult.from_runner_output(task.name, success, output),
                perf_counter() - started,
            )
            completed = index
            self._ui_scan_progress(index, total, "Running")

        if self._stop_event.is_set():
            return

        self.last_scan_finished_at = datetime.now(timezone.utc)
        elapsed = perf_counter() - self._active_scan_started_at
        self._safe_after(lambda: trigger_button.configure(state="normal", text=idle_text))
        self._safe_after(lambda: self.stop_scan_btn.configure(state="disabled"))

        if cancelled:
            done = completed
            self._safe_after(lambda: self.scan_progress_var.set(f"Scan stopped after {done} of {total} checks"))
            self._safe_after(lambda: self.scan_duration_var.set(f"Stopped at {elapsed:.1f}s"))
            return

        self._safe_after(lambda: self.scan_progress_var.set(f"Finished {total} of {total} checks"))
        self._safe_after(lambda: self.scan_duration_var.set(f"Completed in {elapsed:.1f}s"))
        # Turn the scan into a friendly, shareable Master Sentinal report and open
        # it automatically, instead of leaving the user to hunt for Windows' raw
        # technical files.
        self._safe_after(self._generate_scan_report)

    def _stop_full_scan(self) -> None:
        """Request cancellation of the running scan and kill the active tool."""
        self._scan_cancel_event.set()
        self.stop_scan_btn.configure(state="disabled", text="Stopping...")
        self.scan_progress_var.set("Stopping scan - waiting for the current check to halt...")
        # Terminate the in-flight Windows tool (SFC/DISM/CHKDSK) so the scan
        # stops promptly instead of waiting minutes for it to finish.
        self._start_background_thread(self.full_scan_mod.terminate_current)
        self._safe_after(lambda: self.stop_scan_btn.configure(text="Stop Scan"))

    # ------------------------------------------------------------------
    # Live charts, network speed, and post-reboot results
    # ------------------------------------------------------------------

    def _toggle_cpu_chart(self) -> None:
        """Flip the CPU chart between per-thread histogram and line history."""
        mode = self.cpu_chart.toggle_mode()
        if mode == "bars":
            self.cpu_chart_title_var.set("Per-Thread Usage (Histogram)")
            self.cpu_chart_toggle_btn.configure(text="Switch to Line Graph")
        else:
            self.cpu_chart_title_var.set("Overall CPU Usage (Line)")
            self.cpu_chart_toggle_btn.configure(text="Switch to Histogram")

    def _run_speed_test(self) -> None:
        """Run an on-demand internet capacity test on a background thread."""
        if self._speed_test_running:
            return
        self._speed_test_running = True
        self.speed_test_btn.configure(state="disabled", text="Testing...")
        self.speedtest_var.set("Running speed test - this takes about 15-30 seconds...")

        def _work() -> None:
            result = self.speed_tester.run()
            self._speed_test_running = False
            self._safe_after(lambda: self.speedtest_var.set(result.summary))
            self._safe_after(lambda: self.speed_test_btn.configure(state="normal", text="Run Speed Test"))

        self._start_background_thread(_work)

    def _refresh_memory_result(self) -> None:
        """Read the latest Windows Memory Diagnostic result from the Event Log."""
        self.mem_result_btn.configure(state="disabled", text="Checking...")
        self.mem_result_var.set("Reading memory test results from the Windows Event Log...")

        def _work() -> None:
            result = self.post_reboot_reader.get_memory_diagnostic_result()
            text = result.headline
            if result.found and result.time_created:
                text = f"{text}\n(Recorded: {result.time_created})"
            self._safe_after(lambda: self.mem_result_var.set(text))
            self._safe_after(lambda: self.mem_result_btn.configure(state="normal", text="Check Memory Test Result"))

        self._start_background_thread(_work)

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
                "error_code": result.error_code,
                "basic_reason": result.basic_reason,
            }
        )
        if result.success:
            LOGGER.info("%s", result.log_message or f"[{result.task_name}] SUCCESS: {result.message}")
        else:
            LOGGER.warning("%s", result.log_message or f"[{result.task_name}] FAILED: {result.message}")

    def _ui_scan_progress(self, completed: int, total: int, prefix: str) -> None:
        """Thread-safe helper to update batch scan progress (text + bar)."""
        elapsed = perf_counter() - self._active_scan_started_at
        fraction = (completed / total) if total else 0.0
        self._safe_after(lambda: self.scan_progress_var.set(f"{prefix} {completed} of {total} checks"))
        self._safe_after(lambda: self.scan_duration_var.set(f"Elapsed {elapsed:.1f}s"))
        self._safe_after(lambda: self.scan_progress_bar.set(fraction))

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
        """Poll cheap live metrics and schedule UI updates on the fast cadence.

        Only psutil/nvidia-smi reads happen here, combined with the cached deep
        snapshot, so this stays responsive regardless of how slow the machine's
        PowerShell/WMI diagnostics are.
        """
        while not self._stop_event.is_set():
            try:
                fast = self.snapshot_collector.collect_fast()
                snapshot = self.snapshot_collector.assemble(fast, self._deep_cache)
                self._safe_after(lambda current=snapshot: self._apply_snapshot(current))
            except Exception as e:
                LOGGER.exception("Live monitor loop failed: %s", e)
                self._safe_after(
                    lambda: self.health_summary_var.set("Live monitoring hit an error. Check logs for details.")
                )

            # Use Event.wait instead of time.sleep for clean cancellation
            self._stop_event.wait(UPDATE_INTERVAL_SEC)

    def _deep_monitor_loop(self) -> None:
        """Collect the expensive PowerShell/WMI diagnostics on a slow cadence.

        Runs once immediately at startup, then every DEEP_REFRESH_INTERVAL_SEC.
        Results are cached for the fast loop and a fresh combined snapshot is
        pushed so the dashboard health summary and SMART section update.
        """
        while not self._stop_event.is_set():
            try:
                deep = self.snapshot_collector.collect_deep()
                if self._stop_event.is_set():
                    break
                self._deep_cache = deep
                fast = self.snapshot_collector.collect_fast()
                snapshot = self.snapshot_collector.assemble(fast, deep)
                self._safe_after(lambda current=snapshot: self._apply_snapshot(current))
                self._save_snapshot_to_history(snapshot)
            except Exception as e:
                LOGGER.exception("Deep monitor loop failed: %s", e)

            # Wait for the slow interval (cancellable).
            self._stop_event.wait(DEEP_REFRESH_INTERVAL_SEC)

    def _save_snapshot_to_history(self, snapshot) -> None:
        """Save a snapshot to history for trend tracking."""
        try:
            health = snapshot.health_summary
            disk_free = None
            if snapshot.disk_partitions:
                # Get system drive free space
                for disk in snapshot.disk_partitions:
                    if disk.mountpoint == "C:\\":
                        disk_free = 100 - ((disk.used / disk.total) * 100) if disk.total > 0 else None
                        break

            snapshot_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "health_score": getattr(health, "health_score", None),
                "cpu_usage": float(snapshot.summary.cpu_usage_text.replace("%", "")) if snapshot.summary.cpu_usage_text else 0,
                "ram_usage_percent": float(snapshot.summary.ram_usage_text.replace("%", "")) if snapshot.summary.ram_usage_text else 0,
                "gpu_count": len(snapshot.gpu_devices) if snapshot.gpu_devices else 0,
                "disk_count": len(snapshot.disk_partitions) if snapshot.disk_partitions else 0,
                "critical_count": len([f for f in getattr(health, "findings", []) if f.severity == "critical"]) if health else 0,
                "warning_count": len([f for f in getattr(health, "findings", []) if f.severity == "warning"]) if health else 0,
                "temp_max_c": max([gpu.temperature_c for gpu in snapshot.gpu_devices if gpu.temperature_c is not None], default=None) if snapshot.gpu_devices else None,
                "disk_free_percent": disk_free,
            }
            self.snapshot_history.save_snapshot(snapshot_data)
        except Exception as e:
            LOGGER.debug("Failed to save snapshot to history: %s", e)

    # ------------------------------------------------------------------
    # UI update (runs on main thread)
    # ------------------------------------------------------------------

    def _apply_snapshot(self, snapshot: DiagnosticSnapshot) -> None:
        """Apply a collected snapshot on the Tk main thread."""
        self.cpu_usage_var.set(snapshot.summary.cpu_usage_text)
        self.ram_usage_var.set(snapshot.summary.ram_usage_text)
        self.gpu_count_var.set(snapshot.summary.gpu_status_text)
        self.disk_count_var.set(snapshot.summary.disk_status_text)
        self.net_down_var.set(snapshot.summary.net_down_text)
        self.net_up_var.set(snapshot.summary.net_up_text)

        # Live charts: CPU (per-thread histogram + overall line) and RAM line.
        self.cpu_chart.update_values(snapshot.per_core, overall=snapshot.cpu_load)
        ram_pct = float(getattr(snapshot.memory_stats, "percent_used", 0) or 0)
        self.ram_chart.update_values([ram_pct], overall=ram_pct)

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

    @staticmethod
    def _append_error_label(container: ctk.CTkBaseClass, title: str, message: str) -> None:
        """Add a wrapped error label when a section collected partial data with warnings."""
        if not message:
            return
        label = ctk.CTkLabel(
            container,
            text=f"{title}: {message}",
            text_color="red",
            anchor="w",
            justify="left",
            wraplength=1200,
        )
        label.pack(fill="x", padx=20, pady=5)

    def _run_async_refresh(
        self,
        section_key: str,
        container: ctk.CTkBaseClass,
        refresh_button: ctk.CTkButton,
        loading_text: str,
        collector: Callable[[], Any],
        apply_callback: Callable[[Any], None],
        error_context: str,
    ) -> None:
        """Run a refresh job once at a time while keeping the UI responsive."""
        if self._refresh_in_progress.get(section_key):
            return

        self._refresh_in_progress[section_key] = True
        refresh_button.configure(state="disabled", text="Refreshing...")
        self._set_empty_state(container, loading_text)

        def _collect() -> None:
            try:
                payload = collector()
                self._safe_after(lambda: apply_callback(payload))
            except Exception as e:
                LOGGER.exception("%s refresh failed: %s", error_context, e)
                self._safe_after(
                    lambda err=e: self._set_empty_state(container, f"{error_context} refresh failed: {err}")
                )
            finally:
                def _reset_button() -> None:
                    self._refresh_in_progress[section_key] = False
                    refresh_button.configure(state="normal", text="Refresh Status")

                self._safe_after(_reset_button)

        self._start_background_thread(_collect)

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

    def _refresh_security_ui(self) -> None:
        """Refresh Security tab diagnostics."""
        self._run_async_refresh(
            section_key="security",
            container=self.security_container,
            refresh_button=self.security_refresh_btn,
            loading_text="Loading security status...",
            collector=self.security_mod.get_security_health,
            apply_callback=self._apply_security_ui,
            error_context="Security",
        )

    def _apply_security_ui(self, health) -> None:
        """Apply security diagnostics to UI."""
        for child in self.security_container.winfo_children():
            child.destroy()
        self.security_widgets.clear()

        # Defender status section
        defender_frame = SectionFrame(self.security_container, "Microsoft Defender")
        defender_frame.pack(fill="x", pady=10)
        defender_frame.add_row("Antivirus Enabled", str(health.defender_enabled))
        defender_frame.add_row("Real-time Protection", str(health.real_time_protection_enabled))
        defender_frame.add_row("Signature Age (AV)", f"{health.antivirus_signature_age_days} days" if health.antivirus_signature_age_days else "Unknown")
        defender_frame.add_row("Signature Age (AS)", f"{health.antispyware_signature_age_days} days" if health.antispyware_signature_age_days else "Unknown")

        # Firewall section
        firewall_frame = SectionFrame(self.security_container, "Windows Firewall")
        firewall_frame.pack(fill="x", pady=10)
        for profile in health.firewall_profiles:
            profile_frame = SectionFrame(firewall_frame.content, f"{profile.name} Profile")
            profile_frame.pack(fill="x", pady=5)
            profile_frame.add_row("Enabled", str(profile.enabled))
            profile_frame.add_row("Default Inbound", profile.default_inbound_action)
            profile_frame.add_row("Default Outbound", profile.default_outbound_action)

        # BitLocker section
        if health.bitlocker_volumes:
            bitlocker_frame = SectionFrame(self.security_container, "BitLocker Encryption")
            bitlocker_frame.pack(fill="x", pady=10)
            for volume in health.bitlocker_volumes:
                vol_frame = SectionFrame(bitlocker_frame.content, f"Volume {volume.mount_point}")
                vol_frame.pack(fill="x", pady=5)
                vol_frame.add_row("Status", volume.volume_status)
                vol_frame.add_row("Protection", volume.protection_status)
                if volume.encryption_percentage is not None:
                    vol_frame.add_row("Encrypted", f"{volume.encryption_percentage}%")

        # Errors
        if health.defender_error:
            self._append_error_label(self.security_container, "Defender", health.defender_error)
        if health.firewall_error:
            self._append_error_label(self.security_container, "Firewall", health.firewall_error)
        if health.bitlocker_error:
            self._append_error_label(self.security_container, "BitLocker", health.bitlocker_error)
        if health.error_message and not (health.defender_error or health.firewall_error or health.bitlocker_error):
            self._append_error_label(self.security_container, "Security", health.error_message)

    def _refresh_network_ui(self) -> None:
        """Refresh Network tab diagnostics."""
        self._run_async_refresh(
            section_key="network",
            container=self.network_container,
            refresh_button=self.network_refresh_btn,
            loading_text="Loading network status...",
            collector=self.network_mod.get_network_health,
            apply_callback=self._apply_network_ui,
            error_context="Network",
        )

    def _apply_network_ui(self, health) -> None:
        """Apply network diagnostics to UI."""
        for child in self.network_container.winfo_children():
            child.destroy()
        self.network_widgets.clear()

        # Adapters section
        if health.adapters:
            adapters_frame = SectionFrame(self.network_container, "Network Adapters")
            adapters_frame.pack(fill="x", pady=10)
            for adapter in health.adapters:
                adapter_frame = SectionFrame(adapters_frame.content, adapter.name)
                adapter_frame.pack(fill="x", pady=5)
                adapter_frame.add_row("Status", adapter.status)
                adapter_frame.add_row("Link Speed", adapter.link_speed)

        # DNS section
        dns_frame = SectionFrame(self.network_container, "DNS Configuration")
        dns_frame.pack(fill="x", pady=10)
        for i, dns in enumerate(health.dns_servers, 1):
            dns_frame.add_row(f"DNS Server {i}", dns)

        # Gateway section
        if health.gateway_addresses:
            gateway_frame = SectionFrame(self.network_container, "Default Gateway")
            gateway_frame.pack(fill="x", pady=10)
            for i, gw in enumerate(health.gateway_addresses, 1):
                gateway_frame.add_row(f"Gateway {i}", gw)

        # Connectivity
        conn_frame = SectionFrame(self.network_container, "Connectivity Status")
        conn_frame.pack(fill="x", pady=10)
        conn_frame.add_row("DNS Resolution", "OK" if health.dns_resolution_ok else "FAILED")
        conn_frame.add_row("Internet Reachable", "Yes" if health.internet_reachable else "No")
        if health.error_message:
            self._append_error_label(self.network_container, "Network", health.error_message)

    def _refresh_startup_ui(self) -> None:
        """Refresh Startup tab diagnostics."""
        self._run_async_refresh(
            section_key="startup",
            container=self.startup_container,
            refresh_button=self.startup_refresh_btn,
            loading_text="Loading startup programs and services...",
            collector=self.startup_mod.get_startup_health,
            apply_callback=self._apply_startup_ui,
            error_context="Startup",
        )

    def _apply_startup_ui(self, health) -> None:
        """Apply startup diagnostics to UI."""
        for child in self.startup_container.winfo_children():
            child.destroy()
        self.startup_widgets.clear()

        # Startup items
        if health.startup_items:
            startup_frame = SectionFrame(self.startup_container, "Startup Programs")
            startup_frame.pack(fill="x", pady=10)
            for item in health.startup_items[:20]:  # Limit display
                item_frame = SectionFrame(startup_frame.content, item.name)
                item_frame.pack(fill="x", pady=5)
                item_frame.add_row("Command", item.command)
                item_frame.add_row("Location", item.location)
                item_frame.add_row("Enabled", str(item.enabled))
                item_frame.add_row("Impact", item.impact_text)

                # Open the app's actual folder in Explorer — helps users spot
                # unknown or suspicious programs running from odd locations.
                ctk.CTkButton(
                    item_frame.content,
                    text="📂 Open File Location",
                    height=30, width=180,
                    command=lambda cmd=item.command: self._open_file_location(cmd),
                ).pack(anchor="w", pady=(4, 2), padx=5)

        # Slow services
        if health.slow_startup_services:
            slow_frame = SectionFrame(self.startup_container, "Slow-Starting Services")
            slow_frame.pack(fill="x", pady=10)
            for svc in health.slow_startup_services:
                svc_frame = SectionFrame(slow_frame.content, svc.service_name)
                svc_frame.pack(fill="x", pady=5)
                svc_frame.add_row("Startup Time", f"{svc.startup_time_ms} ms" if svc.startup_time_ms else "Unknown")

        # Automatic services
        if health.automatic_services:
            auto_frame = SectionFrame(self.startup_container, "Automatic Services (Sample)")
            auto_frame.pack(fill="x", pady=10)
            for svc in health.automatic_services[:15]:  # Limit display
                svc_frame = SectionFrame(auto_frame.content, svc.display_name)
                svc_frame.pack(fill="x", pady=5)
                svc_frame.add_row("Service Name", svc.name)
                svc_frame.add_row("State", svc.state)
                svc_frame.add_row("Start Mode", svc.start_mode)
        if health.startup_error:
            self._append_error_label(self.startup_container, "Startup Items", health.startup_error)
        if health.slow_startup_error:
            self._append_error_label(self.startup_container, "Slow Startup", health.slow_startup_error)
        if health.service_error:
            self._append_error_label(self.startup_container, "Automatic Services", health.service_error)
        if health.error_message and not (health.startup_error or health.slow_startup_error or health.service_error):
            self._append_error_label(self.startup_container, "Startup", health.error_message)

    def _refresh_update_ui(self) -> None:
        """Refresh Windows Update tab diagnostics."""
        self._run_async_refresh(
            section_key="update",
            container=self.update_container,
            refresh_button=self.update_refresh_btn,
            loading_text="Loading Windows Update health...",
            collector=self.update_mod.get_windows_update_health,
            apply_callback=self._apply_update_ui,
            error_context="Update",
        )

    def _on_scan_preset_changed(self, new_preset: str) -> None:
        """Handle scan preset selection change."""
        preset_map = {
            "Quick Scan": ScanPreset.QUICK,
            "Standard Scan": ScanPreset.STANDARD,
            "Deep Scan": ScanPreset.DEEP,
        }
        preset = preset_map.get(new_preset, ScanPreset.STANDARD)
        config = self.scan_preset_service.get_preset_config(preset)
        tasks = self.scan_preset_service.get_tasks_for_preset(preset)

        desc = f"{config.description} - Includes: {', '.join(t.name for t in tasks[:3])}"
        if len(tasks) > 3:
            desc += f" +{len(tasks) - 3} more"
        if config.requires_reboot:
            desc += " [May require reboot]"

        self._safe_after(lambda: self.preset_description_label.configure(text=desc))

    def _on_trend_metric_changed(self, new_metric: str) -> None:
        """Handle trend metric selection change."""
        self._refresh_trends_ui()

    def _refresh_trends_ui(self) -> None:
        """Refresh Trends tab with historical data."""
        def _collect():
            try:
                metric = self.trend_metric_var.get()
                trend_data = self.snapshot_history.get_trend(metric, lookback_hours=24)
                summary = self.snapshot_history.get_summary_stats()
                self._safe_after(lambda: self._apply_trends_ui(trend_data, summary, metric))
            except Exception as e:
                LOGGER.exception("Trends refresh failed: %s", e)
                self._safe_after(lambda err=e: self._set_empty_state(self.trend_container, f"Error: {err}"))

        self._start_background_thread(_collect)

    def _apply_trends_ui(self, trend_data: dict, summary: dict, metric: str) -> None:
        """Apply trend data to UI."""
        for child in self.trend_container.winfo_children():
            child.destroy()
        self.trend_widgets.clear()

        # Metric display names
        metric_names = {
            "health_score": "Health Score",
            "cpu_usage": "CPU Usage",
            "ram_usage_percent": "RAM Usage",
            "disk_free_percent": "Disk Free Space",
        }

        # Trend direction indicators
        trend_icons = {
            "improving": "↑",
            "declining": "↓",
            "stable": "→",
            "increasing": "↑",
            "decreasing": "↓",
            "new": "New",
            "no_data": "—",
        }

        trend_colors = {
            "improving": "green",
            "declining": "red",
            "stable": "gray",
            "increasing": "orange",
            "decreasing": "orange",
            "new": "blue",
            "no_data": "gray",
        }

        # Current value frame
        current_frame = SectionFrame(self.trend_container, f"Current {metric_names.get(metric, metric)}")
        current_frame.pack(fill="x", pady=10)

        current_value = trend_data.get("current")
        if current_value is not None:
            if metric in ["cpu_usage", "ram_usage_percent"]:
                value_text = f"{current_value:.1f}%"
            elif metric == "health_score":
                value_text = f"{current_value}/100"
            elif metric == "disk_free_percent":
                value_text = f"{current_value:.1f}% free"
            else:
                value_text = str(current_value)

            current_frame.add_row("Current Value", value_text)
        else:
            current_frame.add_row("Current Value", "No data")

        # Trend frame
        trend_frame = SectionFrame(self.trend_container, "24h Trend")
        trend_frame.pack(fill="x", pady=10)

        trend_direction = trend_data.get("trend_direction", "no_data")
        trend_icon = trend_icons.get(trend_direction, "—")
        trend_color = trend_colors.get(trend_direction, "gray")

        change = trend_data.get("change", 0)
        change_text = f"{change:+.2f}" if change != 0 else "0"

        direction_row = trend_frame.add_row("Direction", f"{trend_icon} {trend_direction}")
        direction_row.value.configure(text_color=trend_color)
        trend_frame.add_row("Change (24h)", change_text)

        previous = trend_data.get("previous")
        if previous is not None:
            trend_frame.add_row("Previous", str(previous))

        # Summary stats
        if summary.get("total_snapshots", 0) > 0:
            stats_frame = SectionFrame(self.trend_container, "Summary Statistics")
            stats_frame.pack(fill="x", pady=10)

            stats_frame.add_row("Total Snapshots", str(summary.get("total_snapshots", 0)))

            if metric == "health_score" and summary.get("avg_health_score"):
                stats_frame.add_row("Average", f"{summary['avg_health_score']:.1f}")
            elif metric == "cpu_usage":
                if summary.get("avg_cpu_usage"):
                    stats_frame.add_row("Average", f"{summary['avg_cpu_usage']:.1f}%")
                if summary.get("max_cpu_usage"):
                    stats_frame.add_row("Peak", f"{summary['max_cpu_usage']:.1f}%")
            elif metric == "ram_usage_percent":
                if summary.get("avg_ram_usage"):
                    stats_frame.add_row("Average", f"{summary['avg_ram_usage']:.1f}%")
                if summary.get("max_ram_usage"):
                    stats_frame.add_row("Peak", f"{summary['max_ram_usage']:.1f}%")

        # Empty state if no data
        if trend_data.get("current") is None and summary.get("total_snapshots", 0) == 0:
            self._set_empty_state(self.trend_container, "No snapshot history yet. Snapshots are saved automatically every few minutes while the app runs.")

    def _apply_update_ui(self, health) -> None:
        """Apply update diagnostics to UI."""
        for child in self.update_container.winfo_children():
            child.destroy()
        self.update_widgets.clear()

        # Services section
        services_frame = SectionFrame(self.update_container, "Update Services")
        services_frame.pack(fill="x", pady=10)
        services_frame.add_row("Windows Update", health.update_service_state)
        services_frame.add_row("BITS", health.bits_service_state)
        services_frame.add_row("Medic Service", health.medic_service_state)
        services_frame.add_row("Orchestrator", health.orchestrator_service_state)

        # Reboot status
        reboot_frame = SectionFrame(self.update_container, "Reboot Status")
        reboot_frame.pack(fill="x", pady=10)
        reboot_text = "Pending reboot detected" if health.reboot_pending else "No pending reboot"
        reboot_color = "orange" if health.reboot_pending else "green"
        reboot_label = ctk.CTkLabel(reboot_frame.content, text=reboot_text, text_color=reboot_color, font=("Roboto", 14, "bold"))
        reboot_label.pack(pady=10)

        if health.error_message:
            err = ctk.CTkLabel(self.update_container, text=f"Error: {health.error_message}", text_color="red")
            err.pack(fill="x", padx=20, pady=5)

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
                    "error_code": explain_error_message(issue.message).error_code,
                    "basic_reason": explain_error_message(issue.message).basic_reason,
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
            for key, value in item.as_rows().items():
                rows[f"{label} - {key}"] = str(value)
        return rows

    def _is_running_as_admin(self) -> bool:
        """Return whether the app is currently elevated."""
        try:
            return self.full_scan_mod.is_admin()
        except Exception:
            return False

    @staticmethod
    def _reports_dir() -> str:
        """Return (and create) the folder where scan reports are saved."""
        base = os.path.join(os.path.expanduser("~"), "Documents", "Master Sentinal Reports")
        os.makedirs(base, exist_ok=True)
        return base

    def _generate_scan_report(self) -> None:
        """Build a friendly HTML report after a scan and open it for the user.

        Runs on the UI thread (it reads widget state). The raw Windows tool output
        (powercfg/battery HTML) is intentionally *not* surfaced — this report is in
        Master Sentinal's own plain-language format.
        """
        try:
            payload = self._build_report_payload()
            filename = f"Master_Sentinal_Scan_{datetime.now():%Y%m%d_%H%M%S}.html"
            path = os.path.join(self._reports_dir(), filename)
            write_html_report(path, payload)
            self.last_scan_report_path = path
            self.view_report_btn.configure(state="normal")
            self.scan_progress_var.set("Scan complete - opening your report")
            webbrowser.open(Path(path).as_uri(), new=2)
        except Exception as e:
            LOGGER.exception("Failed to generate scan report: %s", e)
            self.scan_progress_var.set("Scan complete (report could not be generated)")

    def _open_last_scan_report(self) -> None:
        """Re-open the most recent scan report in the default browser."""
        path = self.last_scan_report_path
        if path and os.path.exists(path):
            webbrowser.open(Path(path).as_uri(), new=2)
        else:
            messagebox.showinfo(
                "No report yet",
                "Run a health scan first — a report opens automatically when it finishes.",
            )

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
            initialfile=f"Master_Sentinal_Report_{datetime.now():%Y%m%d_%H%M%S}.csv",
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

    def _export_issue_bundle(self) -> None:
        """Export complete diagnostic bundle for support/debugging."""
        path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("Zip files", "*.zip"), ("All files", "*.*")],
            initialfile=f"Master_Sentinal_Bundle_{datetime.now():%Y%m%d_%H%M%S}.zip",
        )
        if not path:
            return

        # Offer to scrub personal data. Default to anonymized for safe sharing.
        anonymize = messagebox.askyesno(
            "Anonymize bundle?",
            "Remove personal data from this bundle before saving?\n\n"
            "This replaces your Windows username, PC name, and hardware serial "
            "numbers with placeholders. Recommended if you plan to share it "
            "publicly (for example, on GitHub).",
        )

        # Build the report payload on the UI thread (reads widget state), then do
        # the slow collection + zip on a background thread so the UI stays live.
        diagnostic_data = self._build_report_payload()

        def _work() -> None:
            try:
                exporter = IssueBundleExporter(diagnostic_data=diagnostic_data)
                success = exporter.export_bundle(path, anonymize=anonymize)
                if success:
                    self._safe_after(
                        lambda: messagebox.showinfo("Export Complete", f"Diagnostic bundle saved to:\n{path}")
                    )
                else:
                    self._safe_after(
                        lambda: messagebox.showerror(
                            "Export Failed",
                            "Failed to create diagnostic bundle. Check logs for details.",
                        )
                    )
            except Exception as e:
                LOGGER.exception("Issue bundle export failed: %s", e)
                self._safe_after(lambda err=e: messagebox.showerror("Export Failed", str(err)))

        self.scan_progress_var.set("Exporting diagnostic bundle...")
        self._start_background_thread(_work)

    def _current_gpu_temperatures(self) -> list[tuple[str, float]]:
        """Return current GPU ``(label, °C)`` readings for the alert monitor.

        Reads the latest GPU devices captured by the fast loop. GPU temperature
        comes from nvidia-smi today; CPU/fan/voltage sensors are deferred until
        a signed build can ship the sensor driver without antivirus flags.
        """
        readings: list[tuple[str, float]] = []
        for gpu in self._last_gpu_devices or []:
            if getattr(gpu, "is_error", False):
                continue
            temp = gpu.temperature_c
            if temp is not None:
                readings.append((gpu.name or "GPU", temp))
        return readings

    def _on_monitoring_alert(self, alert) -> None:
        """Handle monitoring alert by showing a toast notification."""
        def _show_toast():
            # Clear previous toasts
            for child in self.toast_container.winfo_children():
                child.destroy()
            self.toast_labels.clear()

            # Set background color based on severity
            color_map = {
                AlertSeverity.INFO: "#4f83cc",
                AlertSeverity.WARNING: "#f4b400",
                AlertSeverity.CRITICAL: "#d93025",
            }
            bg_color = color_map.get(alert.severity, "gray")

            # Title label
            title = ctk.CTkLabel(
                self.toast_container,
                text=f"{alert.severity.value.upper()}: {alert.title}",
                font=("Roboto", 12, "bold"),
                text_color=bg_color,
                anchor="w",
            )
            title.pack(fill="x", padx=10, pady=(10, 5))

            # Message label
            msg = ctk.CTkLabel(
                self.toast_container,
                text=alert.message,
                font=("Roboto", 11),
                text_color=("gray10", "gray90"),
                anchor="w",
                justify="left",
                wraplength=300,
            )
            msg.pack(fill="x", padx=10, pady=(0, 10))

            # Show toast
            self.toast_container.grid(row=0, column=0, columnspan=2, sticky="ne", padx=20, pady=20)

            # Auto-hide after 10 seconds
            def _hide_toast():
                if self.toast_container.winfo_viewable():
                    self.toast_container.grid_forget()

            self.after(10000, _hide_toast)

        self._safe_after(_show_toast)

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
