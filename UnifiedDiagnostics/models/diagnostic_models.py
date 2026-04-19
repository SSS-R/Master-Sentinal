"""Typed diagnostic models used by modules and services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CPUInfo:
    """Structured static CPU information with optional collection error."""

    name: str = ""
    cores: int | None = None
    threads: int | None = None
    max_clock_speed_text: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when CPU info collection failed."""
        return self.error_message is not None

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}

        info: dict[str, str] = {}
        if self.name:
            info["Name"] = self.name
        if self.cores is not None:
            info["Cores"] = str(self.cores)
        if self.threads is not None:
            info["Threads"] = str(self.threads)
        if self.max_clock_speed_text:
            info["MaxClockSpeed"] = self.max_clock_speed_text
        return info


@dataclass(frozen=True)
class BoardInfo:
    """Structured motherboard, BIOS, and OS platform information."""

    system: str = ""
    node_name: str = ""
    release: str = ""
    version: str = ""
    machine: str = ""
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""
    bios_version: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when board or BIOS collection hit an error."""
        return self.error_message is not None

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        info = {
            "System": self.system,
            "Node Name": self.node_name,
            "Release": self.release,
            "Version": self.version,
            "Machine": self.machine,
        }
        if self.manufacturer:
            info["Manufacturer"] = self.manufacturer
        if self.product:
            info["Product"] = self.product
        if self.serial_number:
            info["SerialNumber"] = self.serial_number
        if self.bios_version:
            info["BIOS Version"] = self.bios_version
        if self.error_message:
            info["Error"] = self.error_message
        return info


@dataclass(frozen=True)
class ScanResult:
    """Display-ready result for a completed full-scan task."""

    task_name: str
    success: bool
    message: str
    display_text: str
    status_color: str
    log_message: str = ""

    @classmethod
    def from_runner_output(cls, task_name: str, success: bool, output: str) -> ScanResult:
        """Build a scan result from a diagnostic runner tuple."""
        if success:
            display = cls._display_summary(output, fallback="Completed")
            return cls(
                task_name=task_name,
                success=True,
                message=output,
                display_text=display,
                status_color="green",
                log_message=f"[{task_name}] SUCCESS: {output}",
            )

        if "Not a Laptop" in output:
            return cls(
                task_name=task_name,
                success=False,
                message=output,
                display_text="Skipped (Not a Laptop)",
                status_color="yellow",
            )

        return cls(
            task_name=task_name,
            success=False,
            message=output,
            display_text=output,
            status_color="red",
            log_message=f"[{task_name}] {output}",
        )

    @classmethod
    def from_exception(cls, task_name: str, exc: Exception) -> ScanResult:
        """Build a scan result from a runner exception."""
        message = str(exc)
        return cls(
            task_name=task_name,
            success=False,
            message=message,
            display_text=f"Error: {message[:50]}",
            status_color="red",
            log_message=f"[{task_name}] EXCEPTION: {message}",
        )

    @staticmethod
    def _display_summary(output: str, fallback: str) -> str:
        """Return a readable one-line status while preserving detailed logs separately."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return fallback
        summary = lines[0]
        if len(summary) > 140:
            return f"{summary[:137]}..."
        return summary


@dataclass(frozen=True)
class WindowsUpdateHealth:
    """Structured Windows Update health state."""

    update_service_state: str = "Unknown"
    update_service_start_mode: str = "Unknown"
    bits_service_state: str = "Unknown"
    bits_service_start_mode: str = "Unknown"
    medic_service_state: str = "Unknown"
    medic_service_start_mode: str = "Unknown"
    orchestrator_service_state: str = "Unknown"
    orchestrator_service_start_mode: str = "Unknown"
    reboot_pending: bool | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when Windows Update health collection failed."""
        return self.error_message is not None

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for reports."""
        if self.error_message:
            return {"Error": self.error_message}
        reboot_text = "Unknown" if self.reboot_pending is None else ("Yes" if self.reboot_pending else "No")
        return {
            "Windows Update Service": f"{self.update_service_state} ({self.update_service_start_mode})",
            "BITS Service": f"{self.bits_service_state} ({self.bits_service_start_mode})",
            "Update Medic Service": f"{self.medic_service_state} ({self.medic_service_start_mode})",
            "Update Orchestrator Service": f"{self.orchestrator_service_state} ({self.orchestrator_service_start_mode})",
            "Reboot Pending": reboot_text,
        }


@dataclass(frozen=True)
class EventLogEntry:
    """One summarized Windows Event Viewer entry."""

    log_name: str = "System"
    level: str = "Unknown"
    provider: str = "Unknown"
    event_id: int | None = None
    time_created: str = ""
    message: str = ""


@dataclass(frozen=True)
class EventLogSummary:
    """Structured summary of recent critical and error events."""

    critical_count: int = 0
    error_count: int = 0
    lookback_days: int = 7
    recent_events: list[EventLogEntry] | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when Event Viewer collection failed."""
        return self.error_message is not None

    @property
    def total_problem_events(self) -> int:
        """Return the total critical/error event count."""
        return self.critical_count + self.error_count

    def entries(self) -> list[EventLogEntry]:
        """Return recent event entries without exposing an optional list."""
        return self.recent_events or []


@dataclass(frozen=True)
class ReliabilityRecord:
    """One Reliability Monitor crash or hang record."""

    source_name: str = "Unknown"
    product_name: str = ""
    event_id: int | None = None
    time_generated: str = ""
    message: str = ""


@dataclass(frozen=True)
class ReliabilitySummary:
    """Structured summary of recent Reliability Monitor problem history."""

    crash_count: int = 0
    hang_count: int = 0
    lookback_days: int = 7
    recent_records: list[ReliabilityRecord] | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when Reliability Monitor collection failed."""
        return self.error_message is not None

    @property
    def total_problem_records(self) -> int:
        """Return the total crash/hang record count."""
        return self.crash_count + self.hang_count

    def records(self) -> list[ReliabilityRecord]:
        """Return recent reliability records without exposing an optional list."""
        return self.recent_records or []


@dataclass(frozen=True)
class NetworkAdapterStatus:
    """One network adapter state summary."""

    name: str = "Unknown"
    status: str = "Unknown"
    link_speed: str = ""


@dataclass(frozen=True)
class NetworkHealth:
    """Structured network diagnostics summary."""

    adapters: list[NetworkAdapterStatus] | None = None
    dns_servers: list[str] | None = None
    gateway_addresses: list[str] | None = None
    dns_resolution_ok: bool | None = None
    internet_reachable: bool | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when network diagnostics collection failed."""
        return self.error_message is not None

    @property
    def connected_adapter_count(self) -> int:
        """Return the number of adapters reporting an up/connected state."""
        return sum(1 for adapter in self.adapter_statuses() if adapter.status.lower() in {"up", "connected"})

    def adapter_statuses(self) -> list[NetworkAdapterStatus]:
        """Return adapter statuses without exposing an optional list."""
        return self.adapters or []

    def dns_server_list(self) -> list[str]:
        """Return DNS servers without exposing an optional list."""
        return self.dns_servers or []

    def gateway_list(self) -> list[str]:
        """Return gateway addresses without exposing an optional list."""
        return self.gateway_addresses or []


@dataclass(frozen=True)
class PhysicalDriveHealth:
    """One physical drive health summary."""

    friendly_name: str = "Unknown"
    media_type: str = "Unknown"
    bus_type: str = "Unknown"
    health_status: str = "Unknown"
    operational_status: str = "Unknown"
    size_text: str = ""
    temperature_c: float | None = None

    @property
    def is_warning(self) -> bool:
        """Return True when the drive reports a non-OK status or high temperature."""
        health = self.health_status.lower()
        operational = self.operational_status.lower()
        unhealthy = health not in {"", "healthy", "ok", "unknown"}
        not_ready = operational not in {"", "ok", "unknown", "in service"}
        hot = self.temperature_c is not None and self.temperature_c >= 55
        return unhealthy or not_ready or hot


@dataclass(frozen=True)
class StorageHealth:
    """Structured storage diagnostics beyond partition usage and SMART text."""

    drives: list[PhysicalDriveHealth] | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when physical drive health collection failed."""
        return self.error_message is not None

    def drive_statuses(self) -> list[PhysicalDriveHealth]:
        """Return drive statuses without exposing an optional list."""
        return self.drives or []

    def warning_drives(self) -> list[PhysicalDriveHealth]:
        """Return drives with non-OK status or high temperature."""
        return [drive for drive in self.drive_statuses() if drive.is_warning]


@dataclass(frozen=True)
class FirewallProfileStatus:
    """One Windows Firewall profile state."""

    name: str = "Unknown"
    enabled: bool | None = None
    default_inbound_action: str = ""
    default_outbound_action: str = ""


@dataclass(frozen=True)
class BitLockerVolumeStatus:
    """One BitLocker volume protection state."""

    mount_point: str = ""
    volume_status: str = "Unknown"
    protection_status: str = "Unknown"
    encryption_percentage: float | None = None


@dataclass(frozen=True)
class SecurityHealth:
    """Structured Defender, firewall, and BitLocker health state."""

    defender_enabled: bool | None = None
    antivirus_signature_age_days: int | None = None
    antispyware_signature_age_days: int | None = None
    real_time_protection_enabled: bool | None = None
    firewall_profiles: list[FirewallProfileStatus] | None = None
    bitlocker_volumes: list[BitLockerVolumeStatus] | None = None
    defender_error: str = ""
    firewall_error: str = ""
    bitlocker_error: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when security diagnostics collection failed."""
        return self.error_message is not None

    def profiles(self) -> list[FirewallProfileStatus]:
        """Return firewall profiles without exposing an optional list."""
        return self.firewall_profiles or []

    def volumes(self) -> list[BitLockerVolumeStatus]:
        """Return BitLocker volumes without exposing an optional list."""
        return self.bitlocker_volumes or []

    def disabled_firewall_profiles(self) -> list[FirewallProfileStatus]:
        """Return firewall profiles explicitly reporting disabled state."""
        return [profile for profile in self.profiles() if profile.enabled is False]

    def unprotected_bitlocker_volumes(self) -> list[BitLockerVolumeStatus]:
        """Return volumes explicitly reporting BitLocker protection off."""
        return [
            volume for volume in self.volumes()
            if volume.protection_status.lower() in {"off", "protection off"}
        ]


@dataclass(frozen=True)
class StartupItemStatus:
    """One startup command entry."""

    name: str = "Unknown"
    command: str = ""
    location: str = ""
    user: str = ""
    enabled: bool | None = None
    impact_text: str = "Unknown"


@dataclass(frozen=True)
class SlowStartupService:
    """One service reported as slow during startup."""

    service_name: str = "Unknown"
    startup_time_ms: int | None = None


@dataclass(frozen=True)
class BackgroundServiceStatus:
    """One automatic background service state."""

    name: str = "Unknown"
    display_name: str = "Unknown"
    state: str = "Unknown"
    start_mode: str = "Unknown"
    start_name: str = ""
    delayed_auto_start: bool | None = None


@dataclass(frozen=True)
class StartupHealth:
    """Structured startup item and automatic service health state."""

    startup_items: list[StartupItemStatus] | None = None
    slow_startup_services: list[SlowStartupService] | None = None
    automatic_services: list[BackgroundServiceStatus] | None = None
    startup_error: str = ""
    slow_startup_error: str = ""
    service_error: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when startup/service diagnostics collection failed."""
        return self.error_message is not None

    def items(self) -> list[StartupItemStatus]:
        """Return startup items without exposing an optional list."""
        return self.startup_items or []

    def slow_services(self) -> list[SlowStartupService]:
        """Return slow startup services without exposing an optional list."""
        return self.slow_startup_services or []

    def services(self) -> list[BackgroundServiceStatus]:
        """Return automatic services without exposing an optional list."""
        return self.automatic_services or []

    def stopped_automatic_services(self) -> list[BackgroundServiceStatus]:
        """Return non-delayed automatic services that are not running."""
        return [
            service for service in self.services()
            if service.state.lower() != "running" and service.delayed_auto_start is not True
        ]


@dataclass(frozen=True)
class SystemFormFactor:
    """Structured system chassis and battery context."""

    device_type: str = "unknown"
    chassis_types: list[int] | None = None
    has_battery: bool | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when form-factor collection failed."""
        return self.error_message is not None

    @property
    def is_laptop(self) -> bool:
        """Return True when chassis or battery data suggests a laptop-class device."""
        return self.device_type.lower() in {"laptop", "portable", "notebook", "tablet", "convertible", "detachable"}

    @property
    def is_desktop(self) -> bool:
        """Return True when chassis data suggests a desktop-class device."""
        return self.device_type.lower() in {"desktop", "tower", "mini tower", "all-in-one"}


@dataclass(frozen=True)
class DiagnosticIssue:
    """One structured diagnostic failure or degraded-collection entry."""

    source: str = ""
    category: str = ""
    message: str = ""
    severity: str = "warning"


@dataclass(frozen=True)
class DiagnosticReport:
    """Structured report of diagnostic collection issues."""

    issues: list[DiagnosticIssue] | None = None

    def entries(self) -> list[DiagnosticIssue]:
        """Return diagnostic issues without exposing an optional list."""
        return self.issues or []

    @property
    def has_issues(self) -> bool:
        """Return True when any diagnostic issues were recorded."""
        return bool(self.entries())


@dataclass(frozen=True)
class MemoryStats:
    """Structured RAM statistics."""

    total_gb_text: str
    available_gb_text: str
    used_gb_text: str
    percent_used: float



    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        return {
            "Total": self.total_gb_text,
            "Available": self.available_gb_text,
            "Used": self.used_gb_text,
            "Percentage": f"{self.percent_used}%",
        }


@dataclass(frozen=True)
class GPUDevice:
    """Structured GPU status with optional collection error."""

    device_id: str = ""
    name: str = ""
    load_text: str = "N/A"
    free_memory_text: str = "N/A"
    used_memory_text: str = "N/A"
    total_memory_text: str = "N/A"
    temperature_text: str = "N/A"
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when the GPU entry represents a collection error."""
        return self.error_message is not None

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "DeviceID": self.device_id,
            "Name": self.name,
            "Load": self.load_text,
            "Free Memory": self.free_memory_text,
            "Used Memory": self.used_memory_text,
            "Total Memory": self.total_memory_text,
            "Temperature": self.temperature_text,
        }

    def metric_rows(self) -> dict[str, str]:
        """Return display-ready metric rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "Load": self.load_text,
            "Free Memory": self.free_memory_text,
            "Used Memory": self.used_memory_text,
            "Total Memory": self.total_memory_text,
            "Temperature": self.temperature_text,
        }


@dataclass(frozen=True)
class DiskPartition:
    """Structured disk partition usage with optional collection error."""

    device: str = ""
    mountpoint: str = ""
    total_text: str = "N/A"
    used_text: str = "N/A"
    free_text: str = "N/A"
    percent_text: str = "N/A"
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when the partition entry represents a collection error."""
        return self.error_message is not None

    def as_rows(self) -> dict[str, str]:
        """Return display-ready rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "Device": self.device,
            "Mountpoint": self.mountpoint,
            "Total": self.total_text,
            "Used": self.used_text,
            "Free": self.free_text,
            "Percent": self.percent_text,
        }

    def metric_rows(self) -> dict[str, str]:
        """Return display-ready metric rows for the UI."""
        if self.error_message:
            return {"Error": self.error_message}
        return {
            "Total": self.total_text,
            "Used": self.used_text,
            "Free": self.free_text,
            "Percent": self.percent_text,
        }


@dataclass(frozen=True)
class SmartDriveStatus:
    """Structured SMART status with optional collection error."""

    key: str = ""
    display_text: str = ""
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when the SMART entry represents a collection error."""
        return self.error_message is not None

    def as_pair(self) -> tuple[str, str]:
        """Return the legacy key/value pair expected by older callers."""
        if self.error_message:
            return "Error", self.error_message
        return self.key, self.display_text
    def label_and_value(self) -> tuple[str, str]:
        """Return display-ready label/value content for the UI."""
        if self.error_message:
            return "Error", self.error_message
        return self.key, self.display_text
