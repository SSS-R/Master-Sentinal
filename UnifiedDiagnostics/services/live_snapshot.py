"""Helpers for collecting live diagnostics without touching the UI layer."""

from __future__ import annotations

import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from models.diagnostic_models import (
    BitLockerVolumeStatus,
    BackgroundServiceStatus,
    DiagnosticIssue,
    DiagnosticReport,
    DiskPartition,
    EventLogEntry,
    EventLogSummary,
    FirewallProfileStatus,
    GPUDevice,
    MemoryStats,
    NetworkAdapterStatus,
    NetworkHealth,
    PhysicalDriveHealth,
    ReliabilityRecord,
    ReliabilitySummary,
    SecurityHealth,
    SlowStartupService,
    SmartDriveStatus,
    StartupHealth,
    StartupItemStatus,
    StorageHealth,
    SystemFormFactor,
    WindowsUpdateHealth,
)
from models.health_models import HealthSummary
from services.app_logging import get_logger
from services.diagnostic_runtime import friendly_exception_message, run_powershell
from services.health_analyzer import HealthAnalyzer
from services.live_meters import NetworkRate, NetworkSpeedMeter

if TYPE_CHECKING:
    from modules.cpu_diag import CPUDiagnostic
    from modules.disk_diag import DiskDiagnostic
    from modules.gpu_diag import GPUDiagnostic
    from modules.ram_diag import RAMDiagnostic


LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class SnapshotSummary:
    """Pre-formatted values displayed on the dashboard cards."""

    cpu_usage_text: str
    ram_usage_text: str
    gpu_status_text: str
    disk_status_text: str
    net_down_text: str = "0 B/s"
    net_up_text: str = "0 B/s"


@dataclass(frozen=True)
class DiagnosticSnapshot:
    """Full live snapshot returned by the monitoring service."""

    cpu_load: float
    per_core: list[float]
    memory_stats: MemoryStats
    gpu_devices: list[GPUDevice]
    disk_partitions: list[DiskPartition]
    smart_drives: list[SmartDriveStatus]
    windows_update_health: WindowsUpdateHealth
    event_log_summary: EventLogSummary
    reliability_summary: ReliabilitySummary
    network_health: NetworkHealth
    storage_health: StorageHealth
    security_health: SecurityHealth
    startup_health: StartupHealth
    system_form_factor: SystemFormFactor
    diagnostic_report: DiagnosticReport
    summary: SnapshotSummary
    health_summary: HealthSummary
    net_rate: NetworkRate = field(default_factory=NetworkRate)


@dataclass(frozen=True)
class FastSnapshot:
    """Cheap, high-frequency metrics collected via psutil/nvidia-smi.

    Safe to poll on the live (2-second) cadence — no PowerShell or repeated
    WMI connections involved.
    """

    cpu_load: float
    per_core: list[float]
    memory_stats: MemoryStats
    gpu_devices: list[GPUDevice]
    disk_partitions: list[DiskPartition]
    summary: SnapshotSummary
    net_rate: NetworkRate = field(default_factory=NetworkRate)


@dataclass(frozen=True)
class DeepSnapshot:
    """Expensive, slow-changing diagnostics collected via PowerShell/WMI.

    These spawn external processes and query Windows management data, so they
    are collected once at startup and then only on a slow timer or manual
    refresh — never on the live loop. ``collected`` is ``False`` for the
    placeholder used before the first real collection completes.
    """

    smart_drives: list[SmartDriveStatus] = field(default_factory=list)
    windows_update_health: WindowsUpdateHealth = field(default_factory=WindowsUpdateHealth)
    event_log_summary: EventLogSummary = field(default_factory=EventLogSummary)
    reliability_summary: ReliabilitySummary = field(default_factory=ReliabilitySummary)
    network_health: NetworkHealth = field(default_factory=NetworkHealth)
    storage_health: StorageHealth = field(default_factory=StorageHealth)
    security_health: SecurityHealth = field(default_factory=SecurityHealth)
    startup_health: StartupHealth = field(default_factory=StartupHealth)
    system_form_factor: SystemFormFactor = field(default_factory=SystemFormFactor)
    collected: bool = False


class WindowsUpdateDiagnostic:
    """Collects Windows Update service state and pending-reboot signals."""

    def get_windows_update_health(self) -> WindowsUpdateHealth:
        """Return structured Windows Update health information."""
        try:
            result = run_powershell(self._powershell_script(), timeout=15)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return WindowsUpdateHealth(error_message=error)
            if not output:
                return WindowsUpdateHealth(error_message="PowerShell returned no Windows Update health data.")

            payload = json.loads(output)
            return WindowsUpdateHealth(
                update_service_state=self._text(payload.get("WindowsUpdateState")),
                update_service_start_mode=self._text(payload.get("WindowsUpdateStartMode")),
                bits_service_state=self._text(payload.get("BitsState")),
                bits_service_start_mode=self._text(payload.get("BitsStartMode")),
                medic_service_state=self._text(payload.get("MedicState")),
                medic_service_start_mode=self._text(payload.get("MedicStartMode")),
                orchestrator_service_state=self._text(payload.get("OrchestratorState")),
                orchestrator_service_start_mode=self._text(payload.get("OrchestratorStartMode")),
                reboot_pending=payload.get("RebootPending"),
            )
        except Exception as e:
            LOGGER.warning("Windows Update diagnostics failed: %s", e)
            return WindowsUpdateHealth(error_message=friendly_exception_message(e, "Windows Update diagnostics"))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return "Unknown"
        return str(value)

    @staticmethod
    def _powershell_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "function Get-ServiceState($name) {\n"
            "    try {\n"
            "        $svc = Get-CimInstance Win32_Service -Filter \"Name='$name'\" -ErrorAction Stop\n"
            "        return [pscustomobject]@{ State = $svc.State; StartMode = $svc.StartMode }\n"
            "    } catch {\n"
            "        return [pscustomobject]@{ State = 'Unavailable'; StartMode = 'Unknown' }\n"
            "    }\n"
            "}\n"
            "$wu = Get-ServiceState 'wuauserv'\n"
            "$bits = Get-ServiceState 'BITS'\n"
            "$medic = Get-ServiceState 'WaaSMedicSvc'\n"
            "$orchestrator = Get-ServiceState 'UsoSvc'\n"
            "$pendingFileRename = $false\n"
            "try {\n"
            "    $pendingFileRename = $null -ne (Get-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager' -Name PendingFileRenameOperations -ErrorAction SilentlyContinue)\n"
            "} catch { $pendingFileRename = $false }\n"
            "$rebootPending = (Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending') -or "
            "(Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired') -or "
            "$pendingFileRename\n"
            "[pscustomobject]@{\n"
            "    WindowsUpdateState = $wu.State\n"
            "    WindowsUpdateStartMode = $wu.StartMode\n"
            "    BitsState = $bits.State\n"
            "    BitsStartMode = $bits.StartMode\n"
            "    MedicState = $medic.State\n"
            "    MedicStartMode = $medic.StartMode\n"
            "    OrchestratorState = $orchestrator.State\n"
            "    OrchestratorStartMode = $orchestrator.StartMode\n"
            "    RebootPending = $rebootPending\n"
            "} | ConvertTo-Json -Compress\n"
        )


class EventLogDiagnostic:
    """Collects recent System log critical and error event summaries."""

    def get_event_log_summary(self, lookback_days: int = 7, max_events: int = 20) -> EventLogSummary:
        """Return a summary of recent Event Viewer critical/error entries."""
        try:
            result = run_powershell(self._powershell_script(lookback_days, max_events), timeout=20)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return EventLogSummary(lookback_days=lookback_days, error_message=error)
            if not output:
                return EventLogSummary(lookback_days=lookback_days, error_message="PowerShell returned no event data.")

            payload = json.loads(output)
            events = [
                EventLogEntry(
                    log_name=self._text(event.get("LogName")),
                    level=self._text(event.get("Level")),
                    provider=self._text(event.get("Provider")),
                    event_id=event.get("EventId"),
                    time_created=self._text(event.get("TimeCreated")),
                    message=self._text(event.get("Message")),
                )
                for event in payload.get("RecentEvents", [])
            ]
            return EventLogSummary(
                critical_count=int(payload.get("CriticalCount") or 0),
                error_count=int(payload.get("ErrorCount") or 0),
                lookback_days=lookback_days,
                recent_events=events,
            )
        except Exception as e:
            LOGGER.warning("Event Viewer diagnostics failed: %s", e)
            return EventLogSummary(
                lookback_days=lookback_days,
                error_message=friendly_exception_message(e, "Event Viewer diagnostics"),
            )

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _powershell_script(lookback_days: int, max_events: int) -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            f"$start = (Get-Date).AddDays(-{lookback_days})\n"
            "$events = @(Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2; StartTime=$start} "
            f"-MaxEvents {max_events} -ErrorAction SilentlyContinue)\n"
            "$critical = @($events | Where-Object { $_.Level -eq 1 })\n"
            "$errors = @($events | Where-Object { $_.Level -eq 2 })\n"
            "$recent = @($events | Select-Object -First 5 | ForEach-Object {\n"
            "    [pscustomobject]@{\n"
            "        LogName = $_.LogName\n"
            "        Level = $_.LevelDisplayName\n"
            "        Provider = $_.ProviderName\n"
            "        EventId = $_.Id\n"
            "        TimeCreated = if ($_.TimeCreated) { $_.TimeCreated.ToString('o') } else { '' }\n"
            "        Message = ($_.Message -replace '\\s+', ' ').Trim()\n"
            "    }\n"
            "})\n"
            "[pscustomobject]@{\n"
            "    CriticalCount = $critical.Count\n"
            "    ErrorCount = $errors.Count\n"
            "    RecentEvents = $recent\n"
            "} | ConvertTo-Json -Depth 4 -Compress\n"
        )


class ReliabilityMonitorDiagnostic:
    """Collects recent Reliability Monitor crash and hang history."""

    def get_reliability_summary(self, lookback_days: int = 7, max_records: int = 20) -> ReliabilitySummary:
        """Return a summary of recent crash/hang reliability records."""
        try:
            result = run_powershell(self._powershell_script(lookback_days, max_records), timeout=25)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return ReliabilitySummary(lookback_days=lookback_days, error_message=error)
            if not output:
                return ReliabilitySummary(lookback_days=lookback_days, error_message="PowerShell returned no reliability data.")

            payload = json.loads(output)
            records = [
                ReliabilityRecord(
                    source_name=self._text(record.get("SourceName")),
                    product_name=self._text(record.get("ProductName")),
                    event_id=record.get("EventId"),
                    time_generated=self._text(record.get("TimeGenerated")),
                    message=self._text(record.get("Message")),
                )
                for record in payload.get("RecentRecords", [])
            ]
            return ReliabilitySummary(
                crash_count=int(payload.get("CrashCount") or 0),
                hang_count=int(payload.get("HangCount") or 0),
                lookback_days=lookback_days,
                recent_records=records,
            )
        except Exception as e:
            LOGGER.warning("Reliability diagnostics failed: %s", e)
            return ReliabilitySummary(
                lookback_days=lookback_days,
                error_message=friendly_exception_message(e, "Reliability diagnostics"),
            )

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _powershell_script(lookback_days: int, max_records: int) -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            f"$start = (Get-Date).AddDays(-{lookback_days})\n"
            "function Convert-ReliabilityTime($value) {\n"
            "    try {\n"
            "        if ($value -is [datetime]) { return $value }\n"
            "        if ($null -ne $value) { return [Management.ManagementDateTimeConverter]::ToDateTime([string]$value) }\n"
            "    } catch { return $null }\n"
            "    return $null\n"
            "}\n"
            "$records = @(Get-CimInstance -ClassName Win32_ReliabilityRecords -ErrorAction Stop | ForEach-Object {\n"
            "    $time = Convert-ReliabilityTime $_.TimeGenerated\n"
            "    if ($time -and $time -ge $start) {\n"
            "        [pscustomobject]@{\n"
            "            SourceName = $_.SourceName\n"
            "            ProductName = $_.ProductName\n"
            "            EventId = $_.EventIdentifier\n"
            "            TimeGenerated = $time.ToString('o')\n"
            "            Message = ($_.Message -replace '\\s+', ' ').Trim()\n"
            "        }\n"
            "    }\n"
            "})\n"
            "$problemRecords = @($records | Where-Object {\n"
            "    $_.SourceName -match 'Windows Error Reporting|Application Error|Application Hang|AppHang|BlueScreen|LiveKernelEvent' -or\n"
            "    $_.EventId -in 1000,1001,1002,1005,10010\n"
            "})\n"
            "$hangs = @($problemRecords | Where-Object { $_.SourceName -match 'Hang|AppHang' -or $_.EventId -eq 1002 })\n"
            "$crashes = @($problemRecords | Where-Object { $_.SourceName -notmatch 'Hang|AppHang' -and $_.EventId -ne 1002 })\n"
            "[pscustomobject]@{\n"
            "    CrashCount = $crashes.Count\n"
            "    HangCount = $hangs.Count\n"
            f"    RecentRecords = @($problemRecords | Select-Object -First {max_records})\n"
            "} | ConvertTo-Json -Depth 4 -Compress\n"
        )


class NetworkDiagnostic:
    """Collects adapter, DNS, gateway, and reachability diagnostics."""

    def get_network_health(self) -> NetworkHealth:
        """Return structured network health information."""
        try:
            result = run_powershell(self._powershell_script(), timeout=15)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return NetworkHealth(error_message=error)
            if not output:
                return NetworkHealth(error_message="PowerShell returned no network data.")

            payload = json.loads(output)
            adapters = [
                NetworkAdapterStatus(
                    name=self._text(adapter.get("Name")),
                    status=self._text(adapter.get("Status")),
                    link_speed=self._text(adapter.get("LinkSpeed")),
                )
                for adapter in payload.get("Adapters", [])
            ]
            return NetworkHealth(
                adapters=adapters,
                dns_servers=[self._text(server) for server in payload.get("DnsServers", [])],
                gateway_addresses=[self._text(gateway) for gateway in payload.get("Gateways", [])],
                dns_resolution_ok=self._dns_resolution_ok(),
                internet_reachable=self._internet_reachable(),
            )
        except Exception as e:
            LOGGER.warning("Network diagnostics failed: %s", e)
            return NetworkHealth(error_message=friendly_exception_message(e, "Network diagnostics"))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _dns_resolution_ok() -> bool:
        try:
            socket.gethostbyname("www.microsoft.com")
            return True
        except OSError:
            return False

    @staticmethod
    def _internet_reachable() -> bool:
        try:
            with socket.create_connection(("1.1.1.1", 53), timeout=3):
                return True
        except OSError:
            return False

    @staticmethod
    def _powershell_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "$adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {\n"
            "    [pscustomobject]@{ Name = $_.Name; Status = $_.Status; LinkSpeed = $_.LinkSpeed }\n"
            "})\n"
            "$dnsServers = @(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
            "ForEach-Object { $_.ServerAddresses } | Where-Object { $_ } | Select-Object -Unique)\n"
            "$gateways = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue | "
            "ForEach-Object { if ($_.IPv4DefaultGateway) { $_.IPv4DefaultGateway.NextHop } } | "
            "Where-Object { $_ } | Select-Object -Unique)\n"
            "[pscustomobject]@{\n"
            "    Adapters = $adapters\n"
            "    DnsServers = $dnsServers\n"
            "    Gateways = $gateways\n"
            "} | ConvertTo-Json -Depth 4 -Compress\n"
        )


class StorageHealthDiagnostic:
    """Collects physical drive health, type, and temperature details."""

    def get_storage_health(self) -> StorageHealth:
        """Return structured physical drive health information."""
        try:
            result = run_powershell(self._powershell_script(), timeout=20)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return StorageHealth(error_message=error)
            if not output:
                return StorageHealth(error_message="PowerShell returned no storage health data.")

            payload = json.loads(output)
            drives = [
                PhysicalDriveHealth(
                    friendly_name=self._text(drive.get("FriendlyName")),
                    media_type=self._text(drive.get("MediaType")) or "Unknown",
                    bus_type=self._text(drive.get("BusType")) or "Unknown",
                    health_status=self._text(drive.get("HealthStatus")) or "Unknown",
                    operational_status=self._text(drive.get("OperationalStatus")) or "Unknown",
                    size_text=self._text(drive.get("SizeText")),
                    temperature_c=self._float_or_none(drive.get("TemperatureC")),
                )
                for drive in payload.get("Drives", [])
            ]
            return StorageHealth(drives=drives)
        except Exception as e:
            LOGGER.warning("Storage health diagnostics failed: %s", e)
            return StorageHealth(error_message=friendly_exception_message(e, "Storage diagnostics"))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _powershell_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "$drives = @(Get-PhysicalDisk -ErrorAction Stop | ForEach-Object {\n"
            "    $disk = $_\n"
            "    $temp = $null\n"
            "    try {\n"
            "        $counter = Get-StorageReliabilityCounter -PhysicalDisk $disk -ErrorAction SilentlyContinue\n"
            "        if ($counter -and $counter.Temperature) { $temp = $counter.Temperature }\n"
            "    } catch { $temp = $null }\n"
            "    [pscustomobject]@{\n"
            "        FriendlyName = $disk.FriendlyName\n"
            "        MediaType = $disk.MediaType\n"
            "        BusType = $disk.BusType\n"
            "        HealthStatus = $disk.HealthStatus\n"
            "        OperationalStatus = ($disk.OperationalStatus -join ', ')\n"
            "        SizeText = if ($disk.Size) { '{0:N2} GB' -f ($disk.Size / 1GB) } else { '' }\n"
            "        TemperatureC = $temp\n"
            "    }\n"
            "})\n"
            "[pscustomobject]@{ Drives = $drives } | ConvertTo-Json -Depth 4 -Compress\n"
        )


class SecurityDiagnostic:
    """Collects Defender, firewall, and BitLocker health state."""

    def get_security_health(self) -> SecurityHealth:
        """Return structured Windows security health information."""
        try:
            result = run_powershell(self._powershell_script(), timeout=20)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return SecurityHealth(error_message=error)
            if not output:
                return SecurityHealth(error_message="PowerShell returned no security health data.")

            payload = json.loads(output)
            defender = payload.get("Defender") or {}
            firewall_profiles = [
                FirewallProfileStatus(
                    name=self._text(profile.get("Name")) or "Unknown",
                    enabled=self._bool_or_none(profile.get("Enabled")),
                    default_inbound_action=self._text(profile.get("DefaultInboundAction")),
                    default_outbound_action=self._text(profile.get("DefaultOutboundAction")),
                )
                for profile in payload.get("FirewallProfiles", [])
            ]
            bitlocker_volumes = [
                BitLockerVolumeStatus(
                    mount_point=self._text(volume.get("MountPoint")),
                    volume_status=self._text(volume.get("VolumeStatus")) or "Unknown",
                    protection_status=self._text(volume.get("ProtectionStatus")) or "Unknown",
                    encryption_percentage=self._float_or_none(volume.get("EncryptionPercentage")),
                )
                for volume in payload.get("BitLockerVolumes", [])
            ]
            return SecurityHealth(
                defender_enabled=self._bool_or_none(defender.get("AntivirusEnabled")),
                antivirus_signature_age_days=self._int_or_none(defender.get("AntivirusSignatureAge")),
                antispyware_signature_age_days=self._int_or_none(defender.get("AntispywareSignatureAge")),
                real_time_protection_enabled=self._bool_or_none(defender.get("RealTimeProtectionEnabled")),
                firewall_profiles=firewall_profiles,
                bitlocker_volumes=bitlocker_volumes,
                defender_error=self._text(payload.get("DefenderError")),
                firewall_error=self._text(payload.get("FirewallError")),
                bitlocker_error=self._text(payload.get("BitLockerError")),
            )
        except Exception as e:
            LOGGER.warning("Security diagnostics failed: %s", e)
            return SecurityHealth(error_message=friendly_exception_message(e, "Security diagnostics"))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _bool_or_none(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "enabled"}:
                return True
            if normalized in {"false", "0", "no", "disabled"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _powershell_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "$defender = $null\n"
            "$defenderError = ''\n"
            "try {\n"
            "    $mp = Get-MpComputerStatus -ErrorAction Stop\n"
            "    $defender = [pscustomobject]@{\n"
            "        AntivirusEnabled = $mp.AntivirusEnabled\n"
            "        RealTimeProtectionEnabled = $mp.RealTimeProtectionEnabled\n"
            "        AntivirusSignatureAge = $mp.AntivirusSignatureAge\n"
            "        AntispywareSignatureAge = $mp.AntispywareSignatureAge\n"
            "    }\n"
            "} catch { $defenderError = $_.Exception.Message }\n"
            "$firewallProfiles = @()\n"
            "$firewallError = ''\n"
            "try {\n"
            "    $firewallProfiles = @(Get-NetFirewallProfile -ErrorAction Stop | ForEach-Object {\n"
            "        [pscustomobject]@{\n"
            "            Name = $_.Name\n"
            "            Enabled = $_.Enabled\n"
            "            DefaultInboundAction = $_.DefaultInboundAction\n"
            "            DefaultOutboundAction = $_.DefaultOutboundAction\n"
            "        }\n"
            "    })\n"
            "} catch { $firewallError = $_.Exception.Message }\n"
            "$bitLockerVolumes = @()\n"
            "$bitLockerError = ''\n"
            "try {\n"
            "    if (-not (Get-Command Get-BitLockerVolume -ErrorAction SilentlyContinue)) {\n"
            "        throw 'Get-BitLockerVolume is not available on this Windows installation.'\n"
            "    }\n"
            "    $bitLockerVolumes = @(Get-BitLockerVolume -ErrorAction Stop | ForEach-Object {\n"
            "        [pscustomobject]@{\n"
            "            MountPoint = $_.MountPoint\n"
            "            VolumeStatus = $_.VolumeStatus\n"
            "            ProtectionStatus = $_.ProtectionStatus\n"
            "            EncryptionPercentage = $_.EncryptionPercentage\n"
            "        }\n"
            "    })\n"
            "} catch { $bitLockerError = $_.Exception.Message }\n"
            "[pscustomobject]@{\n"
            "    Defender = $defender\n"
            "    DefenderError = $defenderError\n"
            "    FirewallProfiles = $firewallProfiles\n"
            "    FirewallError = $firewallError\n"
            "    BitLockerVolumes = $bitLockerVolumes\n"
            "    BitLockerError = $bitLockerError\n"
            "} | ConvertTo-Json -Depth 5 -Compress\n"
        )


class StartupServiceDiagnostic:
    """Collects startup command and automatic service state."""

    def get_startup_health(self) -> StartupHealth:
        """Return structured startup and background-service health information."""
        try:
            result = run_powershell(self._powershell_script(), timeout=25)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return StartupHealth(error_message=error)
            if not output:
                return StartupHealth(error_message="PowerShell returned no startup/service data.")

            payload = json.loads(output)
            startup_items = [
                StartupItemStatus(
                    name=self._text(item.get("Name")) or "Unknown",
                    command=self._text(item.get("Command")),
                    location=self._text(item.get("Location")),
                    user=self._text(item.get("User")),
                    enabled=self._bool_or_none(item.get("Enabled")),
                    impact_text=self._text(item.get("ImpactText")) or "Unknown",
                )
                for item in payload.get("StartupItems", [])
            ]
            slow_startup_services = [
                SlowStartupService(
                    service_name=self._text(service.get("Service")) or "Unknown",
                    startup_time_ms=self._int_or_none(service.get("StartupTime")),
                )
                for service in payload.get("SlowStartupServices", [])
            ]
            automatic_services = [
                BackgroundServiceStatus(
                    name=self._text(service.get("Name")) or "Unknown",
                    display_name=self._text(service.get("DisplayName")) or "Unknown",
                    state=self._text(service.get("State")) or "Unknown",
                    start_mode=self._text(service.get("StartMode")) or "Unknown",
                    start_name=self._text(service.get("StartName")),
                    delayed_auto_start=self._bool_or_none(service.get("DelayedAutoStart")),
                )
                for service in payload.get("AutomaticServices", [])
            ]
            return StartupHealth(
                startup_items=startup_items,
                slow_startup_services=slow_startup_services,
                automatic_services=automatic_services,
                startup_error=self._text(payload.get("StartupError")),
                slow_startup_error=self._text(payload.get("SlowStartupError")),
                service_error=self._text(payload.get("ServiceError")),
            )
        except Exception as e:
            LOGGER.warning("Startup diagnostics failed: %s", e)
            return StartupHealth(error_message=friendly_exception_message(e, "Startup diagnostics"))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _bool_or_none(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "enabled"}:
                return True
            if normalized in {"false", "0", "no", "disabled"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _powershell_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "$startupItems = @()\n"
            "$startupError = ''\n"
            "try {\n"
            "    $startupItems = @(Get-CimInstance Win32_StartupCommand -ErrorAction Stop | ForEach-Object {\n"
            "        [pscustomobject]@{\n"
            "            Name = $_.Name\n"
            "            Command = $_.Command\n"
            "            Location = $_.Location\n"
            "            User = $_.User\n"
            "            Enabled = $true\n"
            "            ImpactText = 'Unknown'\n"
            "        }\n"
            "    })\n"
            "} catch { $startupError = $_.Exception.Message }\n"
            "$slowStartupServices = @()\n"
            "$slowStartupError = ''\n"
            "try {\n"
            "    $slowStartupServices = @(Get-CimInstance -ClassName MSFT_NetServiceSlowStartup -ErrorAction Stop | ForEach-Object {\n"
            "        [pscustomobject]@{ Service = $_.Service; StartupTime = $_.StartupTime }\n"
            "    })\n"
            "} catch { $slowStartupError = $_.Exception.Message }\n"
            "$automaticServices = @()\n"
            "$serviceError = ''\n"
            "try {\n"
            "    $automaticServices = @(Get-CimInstance Win32_Service -ErrorAction Stop | Where-Object { $_.StartMode -eq 'Auto' } | ForEach-Object {\n"
            "        $delayed = $null\n"
            "        try {\n"
            "            $props = Get-ItemProperty -Path ('HKLM:\\SYSTEM\\CurrentControlSet\\Services\\' + $_.Name) -Name DelayedAutoStart -ErrorAction SilentlyContinue\n"
            "            if ($null -ne $props.DelayedAutoStart) { $delayed = [bool]$props.DelayedAutoStart }\n"
            "        } catch { $delayed = $null }\n"
            "        [pscustomobject]@{\n"
            "            Name = $_.Name\n"
            "            DisplayName = $_.DisplayName\n"
            "            State = $_.State\n"
            "            StartMode = $_.StartMode\n"
            "            StartName = $_.StartName\n"
            "            DelayedAutoStart = $delayed\n"
            "        }\n"
            "    })\n"
            "} catch { $serviceError = $_.Exception.Message }\n"
            "[pscustomobject]@{\n"
            "    StartupItems = $startupItems\n"
            "    StartupError = $startupError\n"
            "    SlowStartupServices = $slowStartupServices\n"
            "    SlowStartupError = $slowStartupError\n"
            "    AutomaticServices = $automaticServices\n"
            "    ServiceError = $serviceError\n"
            "} | ConvertTo-Json -Depth 5 -Compress\n"
        )


class SystemFormFactorDiagnostic:
    """Collects chassis and battery context for false-positive reduction."""

    LAPTOP_CHASSIS_TYPES = {8, 9, 10, 11, 12, 14, 30, 31, 32}
    DESKTOP_CHASSIS_TYPES = {3, 4, 5, 6, 7, 13, 15, 16, 35, 36}

    def get_system_form_factor(self) -> SystemFormFactor:
        """Return structured form-factor context."""
        try:
            result = run_powershell(self._powershell_script(), timeout=10)
            output = (result.stdout or "").strip()
            if result.returncode != 0:
                error = (result.stderr or output or "PowerShell returned a non-zero exit code.").strip()
                return SystemFormFactor(error_message=error)
            if not output:
                return SystemFormFactor(error_message="PowerShell returned no form-factor data.")

            payload = json.loads(output)
            chassis_types = [self._int_or_none(value) for value in payload.get("ChassisTypes", [])]
            chassis_types = [value for value in chassis_types if value is not None]
            has_battery = self._bool_or_none(payload.get("HasBattery"))
            return SystemFormFactor(
                device_type=self._device_type(chassis_types, has_battery),
                chassis_types=chassis_types,
                has_battery=has_battery,
            )
        except Exception as e:
            LOGGER.warning("System form-factor diagnostics failed: %s", e)
            return SystemFormFactor(error_message=friendly_exception_message(e, "System form-factor diagnostics"))

    @staticmethod
    def _bool_or_none(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _device_type(cls, chassis_types: list[int], has_battery: bool | None) -> str:
        if any(chassis_type in cls.LAPTOP_CHASSIS_TYPES for chassis_type in chassis_types):
            return "laptop"
        if any(chassis_type in cls.DESKTOP_CHASSIS_TYPES for chassis_type in chassis_types):
            return "desktop"
        if has_battery is True:
            return "laptop"
        return "unknown"

    @staticmethod
    def _powershell_script() -> str:
        return (
            "$ErrorActionPreference = 'Stop'\n"
            "$chassisTypes = @()\n"
            "try {\n"
            "    $chassisTypes = @(Get-CimInstance Win32_SystemEnclosure -ErrorAction Stop | "
            "ForEach-Object { $_.ChassisTypes } | Where-Object { $null -ne $_ })\n"
            "} catch { $chassisTypes = @() }\n"
            "$hasBattery = $false\n"
            "try {\n"
            "    $hasBattery = [bool]@(Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue).Count\n"
            "} catch { $hasBattery = $false }\n"
            "[pscustomobject]@{ ChassisTypes = $chassisTypes; HasBattery = $hasBattery } | ConvertTo-Json -Depth 4 -Compress\n"
        )


class LiveSnapshotCollector:
    """Collects diagnostics and formats a UI-ready snapshot."""

    def __init__(
        self,
        cpu_mod: CPUDiagnostic,
        ram_mod: RAMDiagnostic,
        gpu_mod: GPUDiagnostic,
        disk_mod: DiskDiagnostic,
        windows_update_mod: WindowsUpdateDiagnostic | None = None,
        event_log_mod: EventLogDiagnostic | None = None,
        reliability_mod: ReliabilityMonitorDiagnostic | None = None,
        network_mod: NetworkDiagnostic | None = None,
        storage_health_mod: StorageHealthDiagnostic | None = None,
        security_mod: SecurityDiagnostic | None = None,
        startup_mod: StartupServiceDiagnostic | None = None,
        system_form_factor_mod: SystemFormFactorDiagnostic | None = None,
        health_analyzer: HealthAnalyzer | None = None,
    ) -> None:
        self.cpu_mod = cpu_mod
        self.ram_mod = ram_mod
        self.gpu_mod = gpu_mod
        self.disk_mod = disk_mod
        if windows_update_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            windows_update_mod = WindowsUpdateDiagnostic()
        self.windows_update_mod = windows_update_mod
        if event_log_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            event_log_mod = EventLogDiagnostic()
        self.event_log_mod = event_log_mod
        if reliability_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            reliability_mod = ReliabilityMonitorDiagnostic()
        self.reliability_mod = reliability_mod
        if network_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            network_mod = NetworkDiagnostic()
        self.network_mod = network_mod
        if storage_health_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            storage_health_mod = StorageHealthDiagnostic()
        self.storage_health_mod = storage_health_mod
        if security_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            security_mod = SecurityDiagnostic()
        self.security_mod = security_mod
        if startup_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            startup_mod = StartupServiceDiagnostic()
        self.startup_mod = startup_mod
        if system_form_factor_mod is None and os.name == "nt" and "PYTEST_CURRENT_TEST" not in os.environ:
            system_form_factor_mod = SystemFormFactorDiagnostic()
        self.system_form_factor_mod = system_form_factor_mod
        self.health_analyzer = health_analyzer or HealthAnalyzer()
        # Live up/down throughput meter — sampled once per fast tick.
        self.network_speed_meter = NetworkSpeedMeter()

    @staticmethod
    def empty_deep() -> DeepSnapshot:
        """Return a placeholder deep snapshot used before the first real collect."""
        return DeepSnapshot()

    def collect_fast(self) -> FastSnapshot:
        """Collect cheap, high-frequency metrics (psutil/nvidia-smi only).

        This is safe to call on the live 2-second loop: it never spawns the
        eight PowerShell diagnostics or rebuilds heavy WMI service queries.
        """
        cpu_load = self.cpu_mod.get_cpu_usage()
        per_core = self.cpu_mod.get_per_core_usage()
        memory_stats = self.ram_mod.get_ram_stats()
        gpu_devices = self.gpu_mod.get_gpu_devices()
        disk_partitions = self.disk_mod.get_disk_partitions()
        net_rate = self.network_speed_meter.sample()

        summary = SnapshotSummary(
            cpu_usage_text=f"{cpu_load}%",
            ram_usage_text=f"{memory_stats.percent_used}%",
            gpu_status_text=self._format_collection_status(gpu_devices, "GPU", "GPUs", "No GPUs Found"),
            disk_status_text=self._format_collection_status(
                disk_partitions,
                "Partition",
                "Partitions",
                "No Partitions Found",
            ),
            net_down_text=net_rate.download_text,
            net_up_text=net_rate.upload_text,
        )
        return FastSnapshot(
            cpu_load=cpu_load,
            per_core=per_core,
            memory_stats=memory_stats,
            gpu_devices=gpu_devices,
            disk_partitions=disk_partitions,
            summary=summary,
            net_rate=net_rate,
        )

    def collect_deep(self) -> DeepSnapshot:
        """Collect the expensive PowerShell/WMI diagnostics concurrently.

        Each diagnostic spawns an independent process or WMI query, so running
        them in a thread pool turns the wall time from the sum of all calls into
        roughly the slowest single call. Per-collector failures are isolated so
        one slow or missing component cannot sink the rest.
        """
        jobs: dict[str, tuple[Callable[[], Any] | None, Any]] = {
            "smart_drives": (self.disk_mod.get_smart_drive_statuses, []),
            "windows_update_health": (
                self.windows_update_mod.get_windows_update_health if self.windows_update_mod else None,
                WindowsUpdateHealth(),
            ),
            "event_log_summary": (
                self.event_log_mod.get_event_log_summary if self.event_log_mod else None,
                EventLogSummary(),
            ),
            "reliability_summary": (
                self.reliability_mod.get_reliability_summary if self.reliability_mod else None,
                ReliabilitySummary(),
            ),
            "network_health": (
                self.network_mod.get_network_health if self.network_mod else None,
                NetworkHealth(),
            ),
            "storage_health": (
                self.storage_health_mod.get_storage_health if self.storage_health_mod else None,
                StorageHealth(),
            ),
            "security_health": (
                self.security_mod.get_security_health if self.security_mod else None,
                SecurityHealth(),
            ),
            "startup_health": (
                self.startup_mod.get_startup_health if self.startup_mod else None,
                StartupHealth(),
            ),
            "system_form_factor": (
                self.system_form_factor_mod.get_system_form_factor if self.system_form_factor_mod else None,
                SystemFormFactor(),
            ),
        }

        results: dict[str, Any] = {}
        pending: dict[str, Callable[[], Any]] = {}
        for key, (runner, default) in jobs.items():
            if runner is None:
                results[key] = default
            else:
                pending[key] = runner

        if pending:
            with ThreadPoolExecutor(max_workers=len(pending)) as executor:
                futures = {executor.submit(runner): key for key, runner in pending.items()}
                for future, key in futures.items():
                    try:
                        results[key] = future.result()
                    except Exception as exc:  # isolate per-collector failures
                        LOGGER.warning("Deep diagnostic '%s' failed: %s", key, exc)
                        results[key] = jobs[key][1]

        return DeepSnapshot(collected=True, **results)

    def assemble(self, fast: FastSnapshot, deep: DeepSnapshot) -> DiagnosticSnapshot:
        """Combine a fast snapshot with the latest deep snapshot into a full result.

        Deep models are only fed into the health analyzer and diagnostic report
        once a real deep collection has completed (``deep.collected``) and the
        owning module exists, preserving the previous None-gating behaviour.
        """

        def deep_or_none(value: Any, mod: Any) -> Any:
            return value if (deep.collected and mod is not None) else None

        diagnostic_report = self._build_diagnostic_report(
            fast.gpu_devices,
            fast.disk_partitions,
            deep.smart_drives,
            deep.windows_update_health,
            deep.event_log_summary,
            deep.reliability_summary,
            deep.network_health,
            deep.storage_health,
            deep.security_health,
            deep.startup_health,
            deep.system_form_factor,
            include_deep=deep.collected,
        )
        health_summary = self.health_analyzer.analyze(
            fast.cpu_load,
            fast.memory_stats,
            fast.gpu_devices,
            fast.disk_partitions,
            deep.smart_drives,
            deep_or_none(deep.windows_update_health, self.windows_update_mod),
            deep_or_none(deep.event_log_summary, self.event_log_mod),
            deep_or_none(deep.reliability_summary, self.reliability_mod),
            deep_or_none(deep.network_health, self.network_mod),
            deep_or_none(deep.storage_health, self.storage_health_mod),
            deep_or_none(deep.security_health, self.security_mod),
            deep_or_none(deep.startup_health, self.startup_mod),
            deep_or_none(deep.system_form_factor, self.system_form_factor_mod),
        )

        return DiagnosticSnapshot(
            cpu_load=fast.cpu_load,
            per_core=fast.per_core,
            memory_stats=fast.memory_stats,
            gpu_devices=fast.gpu_devices,
            disk_partitions=fast.disk_partitions,
            smart_drives=deep.smart_drives,
            windows_update_health=deep.windows_update_health,
            event_log_summary=deep.event_log_summary,
            reliability_summary=deep.reliability_summary,
            network_health=deep.network_health,
            storage_health=deep.storage_health,
            security_health=deep.security_health,
            startup_health=deep.startup_health,
            system_form_factor=deep.system_form_factor,
            diagnostic_report=diagnostic_report,
            summary=fast.summary,
            health_summary=health_summary,
            net_rate=fast.net_rate,
        )

    def collect(self) -> DiagnosticSnapshot:
        """Gather a full live snapshot (fast + deep) in one call.

        Retained for tests, report generation, and any caller that wants a
        complete one-shot snapshot. The live UI uses ``collect_fast`` and a
        cached ``collect_deep`` instead.
        """
        return self.assemble(self.collect_fast(), self.collect_deep())

    @staticmethod
    def _build_diagnostic_report(
        gpu_devices: list[GPUDevice],
        disk_partitions: list[DiskPartition],
        smart_drives: list[SmartDriveStatus],
        windows_update_health: WindowsUpdateHealth,
        event_log_summary: EventLogSummary,
        reliability_summary: ReliabilitySummary,
        network_health: NetworkHealth,
        storage_health: StorageHealth,
        security_health: SecurityHealth,
        startup_health: StartupHealth,
        system_form_factor: SystemFormFactor,
        include_deep: bool = True,
    ) -> DiagnosticReport:
        issues: list[DiagnosticIssue] = []

        for gpu in gpu_devices:
            if gpu.is_error:
                issues.append(DiagnosticIssue(source="GPU", category="collection", message=gpu.error_message or "Unknown error"))
        for partition in disk_partitions:
            if partition.is_error:
                issues.append(DiagnosticIssue(source="Disk", category="collection", message=partition.error_message or "Unknown error"))
        for smart_drive in smart_drives:
            if smart_drive.is_error:
                issues.append(DiagnosticIssue(source="SMART", category="collection", message=smart_drive.error_message or "Unknown error"))

        if not include_deep:
            return DiagnosticReport(issues=issues)

        for source, model in (
            ("Windows Update", windows_update_health),
            ("Event Viewer", event_log_summary),
            ("Reliability Monitor", reliability_summary),
            ("Network", network_health),
            ("Storage", storage_health),
            ("Security", security_health),
            ("Startup", startup_health),
            ("System Form Factor", system_form_factor),
        ):
            if getattr(model, "is_error", False):
                issues.append(
                    DiagnosticIssue(
                        source=source,
                        category="collection",
                        message=getattr(model, "error_message", "") or "Unknown error",
                    )
                )

        for source, message, severity in (
            ("Security", security_health.defender_error, "warning"),
            ("Security", security_health.firewall_error, "warning"),
            ("Security", security_health.bitlocker_error, "info"),
            ("Startup", startup_health.startup_error, "warning"),
            ("Startup", startup_health.slow_startup_error, "info"),
            ("Startup", startup_health.service_error, "warning"),
        ):
            if message:
                issues.append(DiagnosticIssue(source=source, category="partial", message=message, severity=severity))

        return DiagnosticReport(issues=issues)

    @staticmethod
    def _format_collection_status(
        items: list[object],
        singular_label: str,
        plural_label: str,
        empty_text: str,
    ) -> str:
        """Return a safe summary string for dashboard cards."""
        if not items:
            return empty_text
        if any(getattr(item, "is_error", False) for item in items):
            return "Unavailable"
        count = len(items)
        label = singular_label if count == 1 else plural_label
        return f"{count} {label}"
