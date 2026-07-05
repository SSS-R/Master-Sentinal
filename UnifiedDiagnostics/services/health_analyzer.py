"""Derives user-facing health findings from live diagnostics."""

from __future__ import annotations

from dataclasses import replace

from models.diagnostic_models import (
    DiskPartition,
    EventLogSummary,
    GPUDevice,
    MemoryStats,
    NetworkHealth,
    SecurityHealth,
    StorageHealth,
    StartupHealth,
    ReliabilitySummary,
    SmartDriveStatus,
    SystemFormFactor,
    WindowsUpdateHealth,
)
from models.health_models import HealthFinding, HealthSummary


class HealthAnalyzer:
    """Turns raw diagnostics into actionable health findings."""

    def analyze(
        self,
        cpu_load: float,
        ram: MemoryStats,
        gpus: list[GPUDevice],
        disks: list[DiskPartition],
        smart: list[SmartDriveStatus],
        windows_update: WindowsUpdateHealth | None = None,
        event_log: EventLogSummary | None = None,
        reliability: ReliabilitySummary | None = None,
        network: NetworkHealth | None = None,
        storage_health: StorageHealth | None = None,
        security_health: SecurityHealth | None = None,
        startup_health: StartupHealth | None = None,
        system_form_factor: SystemFormFactor | None = None,
    ) -> HealthSummary:
        """Return a diagnosis summary for the current live snapshot."""
        findings: list[HealthFinding] = []

        findings.extend(
            self._collect_module_errors(
                gpus,
                disks,
                smart,
                windows_update,
                event_log,
                reliability,
                network,
                storage_health,
                security_health,
                startup_health,
                system_form_factor,
            )
        )
        findings.extend(self._analyze_cpu(cpu_load))
        findings.extend(self._analyze_ram(ram))
        findings.extend(self._analyze_gpus(gpus, system_form_factor))
        findings.extend(self._analyze_disks(disks))
        findings.extend(self._analyze_smart(smart))
        if windows_update is not None:
            findings.extend(self._analyze_windows_update(windows_update))
        if event_log is not None:
            findings.extend(self._analyze_event_log(event_log))
        if reliability is not None:
            findings.extend(self._analyze_reliability(reliability))
        if network is not None:
            findings.extend(self._analyze_network(network))
        if storage_health is not None:
            findings.extend(self._analyze_storage_health(storage_health))
        if security_health is not None:
            findings.extend(self._analyze_security(security_health))
        if startup_health is not None:
            findings.extend(self._analyze_startup(startup_health))

        findings.sort(key=lambda finding: self._severity_rank(finding.severity), reverse=True)
        findings = self._finalize_findings(findings)

        if not findings:
            healthy_finding = HealthFinding(
                title="System looks stable",
                message="Live diagnostics did not detect any immediate performance or storage concerns.",
                severity="ok",
                recommended_action="Keep monitoring normally.",
                state="ok",
            )
            return HealthSummary(
                overall_status="ok",
                headline="No immediate issues detected",
                findings=[healthy_finding],
                health_score=100,
                severity_counts=self._severity_counts([healthy_finding]),
                severity_rollup="No issues",
            )

        highest = findings[0].severity
        score = self._health_score(findings)
        rollup = self._severity_rollup(findings)
        if highest == "critical":
            headline = "Critical issues need attention"
        elif highest == "warning":
            headline = "Warnings detected in live diagnostics"
        else:
            headline = "Diagnostic insights available"

        return HealthSummary(
            overall_status=highest,
            headline=headline,
            findings=findings,
            health_score=score,
            severity_counts=self._severity_counts(findings),
            severity_rollup=rollup,
        )

    def _collect_module_errors(
        self,
        gpus: list[GPUDevice],
        disks: list[DiskPartition],
        smart: list[SmartDriveStatus],
        windows_update: WindowsUpdateHealth | None,
        event_log: EventLogSummary | None,
        reliability: ReliabilitySummary | None,
        network: NetworkHealth | None,
        storage_health: StorageHealth | None,
        security_health: SecurityHealth | None,
        startup_health: StartupHealth | None,
        system_form_factor: SystemFormFactor | None,
    ) -> list[HealthFinding]:
        findings: list[HealthFinding] = []

        for label, items in (("GPU", gpus), ("Disk", disks)):
            for item in items:
                if item.is_error:
                    findings.append(
                        HealthFinding(
                            title=f"{label} diagnostics unavailable",
                            message=item.error_message or "Unknown error",
                            severity="warning",
                        )
                    )

        for smart_drive in smart:
            if smart_drive.is_error:
                findings.append(
                    HealthFinding(
                        title="Drive Status diagnostics unavailable",
                        message=smart_drive.error_message or "Unknown error",
                        severity="warning",
                    )
                )

        if windows_update is not None and windows_update.is_error:
            findings.append(
                HealthFinding(
                    title="Windows Update diagnostics unavailable",
                    message=windows_update.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if event_log is not None and event_log.is_error:
            findings.append(
                HealthFinding(
                    title="Event Viewer diagnostics unavailable",
                    message=event_log.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if reliability is not None and reliability.is_error:
            findings.append(
                HealthFinding(
                    title="Reliability Monitor diagnostics unavailable",
                    message=reliability.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if network is not None and network.is_error:
            findings.append(
                HealthFinding(
                    title="Network diagnostics unavailable",
                    message=network.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if storage_health is not None and storage_health.is_error:
            findings.append(
                HealthFinding(
                    title="Storage health diagnostics unavailable",
                    message=storage_health.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if security_health is not None and security_health.is_error:
            findings.append(
                HealthFinding(
                    title="Security diagnostics unavailable",
                    message=security_health.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if startup_health is not None and startup_health.is_error:
            findings.append(
                HealthFinding(
                    title="Startup and service diagnostics unavailable",
                    message=startup_health.error_message or "Unknown error",
                    severity="warning",
                )
            )

        if system_form_factor is not None and system_form_factor.is_error:
            findings.append(
                HealthFinding(
                    title="System form-factor diagnostics unavailable",
                    message=system_form_factor.error_message or "Unknown error",
                    severity="info",
                )
            )

        return findings

    def _analyze_cpu(self, cpu_load: float) -> list[HealthFinding]:
        if cpu_load >= 95:
            return [
                HealthFinding(
                    title="CPU load is extremely high",
                    message=f"Current CPU usage is {cpu_load:.1f}%, which may indicate a runaway process or severe system load.",
                    severity="critical",
                )
            ]
        if cpu_load >= 85:
            return [
                HealthFinding(
                    title="CPU load is elevated",
                    message=f"Current CPU usage is {cpu_load:.1f}%. Check for apps or services consuming sustained processor time.",
                    severity="warning",
                )
            ]
        return []

    def _analyze_ram(self, ram: MemoryStats) -> list[HealthFinding]:
        percent = self._coerce_float(ram.percent_used)
        if percent is None:
            return []
        if percent >= 90:
            return [
                HealthFinding(
                    title="Memory pressure is critical",
                    message=f"RAM usage is {percent:.1f}%. The system may start paging heavily and feel slow.",
                    severity="critical",
                )
            ]
        if percent >= 80:
            return [
                HealthFinding(
                    title="Memory usage is high",
                    message=f"RAM usage is {percent:.1f}%. Closing heavy apps may improve responsiveness.",
                    severity="warning",
                )
            ]
        return []

    def _analyze_gpus(
        self,
        gpus: list[GPUDevice],
        system_form_factor: SystemFormFactor | None = None,
    ) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        warning_threshold = 85 if system_form_factor and system_form_factor.is_laptop else 80
        critical_threshold = 95 if system_form_factor and system_form_factor.is_laptop else 90
        for gpu in gpus:
            temp = self._parse_temperature(gpu.temperature_text)
            name = gpu.name or "GPU"
            if temp is None:
                continue
            if temp >= critical_threshold:
                findings.append(
                    HealthFinding(
                        title=f"{name} temperature is critical",
                        message=f"{name} is reporting {temp:.0f} C. Check airflow, dust buildup, and fan behavior.",
                        severity="critical",
                    )
                )
            elif temp >= warning_threshold:
                findings.append(
                    HealthFinding(
                        title=f"{name} temperature is elevated",
                        message=f"{name} is reporting {temp:.0f} C. Watch cooling if this persists under moderate load.",
                        severity="warning",
                    )
                )
        return findings

    def _analyze_disks(self, disks: list[DiskPartition]) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for disk in disks:
            percent_used = self._parse_percent(disk.percent_text)
            if percent_used is None:
                continue

            label = disk.mountpoint or disk.device or "Disk"
            if percent_used >= 95:
                findings.append(
                    HealthFinding(
                        title=f"{label} is almost full",
                        message=f"{label} is using {percent_used:.0f}% of available space. Free space is critically low.",
                        severity="critical",
                    )
                )
            elif percent_used >= 85:
                findings.append(
                    HealthFinding(
                        title=f"{label} is running low on free space",
                        message=f"{label} is using {percent_used:.0f}% of available space. Storage cleanup is recommended.",
                        severity="warning",
                    )
                )
        return findings

    def _analyze_smart(self, smart: list[SmartDriveStatus]) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for smart_drive in smart:
            if smart_drive.is_error:
                continue

            value = smart_drive.display_text
            normalized = value.lower()
            if "pred fail" in normalized or "fail" in normalized:
                findings.append(
                    HealthFinding(
                        title="Windows reported a drive failure risk",
                        message=value,
                        severity="critical",
                    )
                )
            elif "caution" in normalized or "warning" in normalized:
                findings.append(
                    HealthFinding(
                        title="Windows reported a drive warning",
                        message=value,
                        severity="warning",
                    )
                )
        return findings

    def _analyze_windows_update(self, health: WindowsUpdateHealth) -> list[HealthFinding]:
        if health.is_error:
            return []

        findings: list[HealthFinding] = []
        disabled_services = []
        for label, start_mode in (
            ("Windows Update", health.update_service_start_mode),
            ("BITS", health.bits_service_start_mode),
            ("Update Medic", health.medic_service_start_mode),
            ("Update Orchestrator", health.orchestrator_service_start_mode),
        ):
            if start_mode.lower() == "disabled":
                disabled_services.append(label)

        if disabled_services:
            findings.append(
                HealthFinding(
                    title="Windows Update services are disabled",
                    message=f"Disabled services: {', '.join(disabled_services)}. Updates may not download or install correctly.",
                    severity="warning",
                )
            )

        if health.reboot_pending:
            findings.append(
                HealthFinding(
                    title="Restart pending for Windows Update",
                    message="Windows has pending update or servicing work. Restarting can complete the update cycle.",
                    severity="warning",
                )
            )

        return findings

    def _analyze_event_log(self, summary: EventLogSummary) -> list[HealthFinding]:
        if summary.is_error or summary.total_problem_events == 0:
            return []

        detail = (
            f"System log contains {summary.critical_count} critical and {summary.error_count} error events "
            f"in the last {summary.lookback_days} days."
        )
        recent_events = summary.entries()
        if recent_events:
            first_event = recent_events[0]
            detail = f"{detail} Most recent: {first_event.provider} event {first_event.event_id}."

        severity = "critical" if summary.critical_count else "warning"
        return [
            HealthFinding(
                title="Event Viewer reported recent critical errors",
                message=detail,
                severity=severity,
            )
        ]

    def _analyze_reliability(self, summary: ReliabilitySummary) -> list[HealthFinding]:
        if summary.is_error or summary.total_problem_records == 0:
            return []

        detail = (
            f"Reliability Monitor recorded {summary.crash_count} crashes and {summary.hang_count} hangs "
            f"in the last {summary.lookback_days} days."
        )
        recent_records = summary.records()
        if recent_records:
            first_record = recent_records[0]
            product = first_record.product_name or first_record.source_name
            detail = f"{detail} Most recent: {product}."

        severity = "critical" if summary.total_problem_records >= 5 or summary.crash_count >= 3 else "warning"
        return [
            HealthFinding(
                title="Recent crash history found",
                message=detail,
                severity=severity,
            )
        ]

    def _analyze_network(self, health: NetworkHealth) -> list[HealthFinding]:
        if health.is_error:
            return []

        findings: list[HealthFinding] = []
        if health.connected_adapter_count == 0:
            findings.append(
                HealthFinding(
                    title="No active network adapter detected",
                    message="No network adapters are reporting an up or connected state.",
                    severity="critical",
                )
            )

        if not health.gateway_list():
            findings.append(
                HealthFinding(
                    title="No default gateway detected",
                    message="Network diagnostics did not find an IPv4 default gateway.",
                    severity="warning",
                )
            )

        if not health.dns_server_list():
            findings.append(
                HealthFinding(
                    title="No DNS servers detected",
                    message="Network diagnostics did not find configured IPv4 DNS servers.",
                    severity="warning",
                )
            )
        elif health.dns_resolution_ok is False:
            findings.append(
                HealthFinding(
                    title="DNS resolution failed",
                    message="DNS servers are configured, but resolving www.microsoft.com failed.",
                    severity="warning",
                )
            )

        if health.internet_reachable is False:
            findings.append(
                HealthFinding(
                    title="Internet reachability check failed",
                    message="The app could not connect to 1.1.1.1 on port 53 within the timeout.",
                    severity="warning",
                )
            )

        return findings

    def _analyze_storage_health(self, health: StorageHealth) -> list[HealthFinding]:
        if health.is_error:
            return []

        findings: list[HealthFinding] = []
        for drive in health.warning_drives():
            label = drive.friendly_name or "Physical drive"
            specific_issue = False
            if drive.temperature_c is not None and drive.temperature_c >= 65:
                findings.append(
                    HealthFinding(
                        title=f"{label} temperature is critical",
                        message=f"{label} is reporting {drive.temperature_c:.0f} C. Check cooling and drive health.",
                        severity="critical",
                    )
                )
                specific_issue = True
            elif drive.temperature_c is not None and drive.temperature_c >= 55:
                findings.append(
                    HealthFinding(
                        title=f"{label} temperature is elevated",
                        message=f"{label} is reporting {drive.temperature_c:.0f} C. Watch drive cooling and workload.",
                        severity="warning",
                    )
                )
                specific_issue = True

            if drive.read_errors_uncorrected is not None and drive.read_errors_uncorrected > 0:
                findings.append(
                    HealthFinding(
                        title=f"{label} read errors detected",
                        message=f"{label} has {drive.read_errors_uncorrected} uncorrected read errors. This is a leading indicator of drive failure.",
                        severity="warning",
                    )
                )
                specific_issue = True
                
            if drive.wear is not None and drive.wear >= 80:
                severity = "warning" if drive.wear >= 95 else "info"
                findings.append(
                    HealthFinding(
                        title=f"{label} wear level is high",
                        message=f"{label} reports {int(drive.wear)}% wear. {'Plan for replacement soon.' if drive.wear >= 95 else 'Keep an eye on it.'}",
                        severity=severity,
                    )
                )
                specific_issue = True

            if not specific_issue:
                findings.append(
                    HealthFinding(
                        title=f"{label} storage health needs attention",
                        message=(
                            f"{label} reports health '{drive.health_status}' and operational status "
                            f"'{drive.operational_status}'. Media type: {drive.media_type}, bus: {drive.bus_type}."
                        ),
                        severity="warning",
                    )
                )

        return findings

    def _analyze_security(self, health: SecurityHealth) -> list[HealthFinding]:
        if health.is_error:
            return []

        findings: list[HealthFinding] = []
        if health.defender_error:
            findings.append(
                HealthFinding(
                    title="Defender status unavailable",
                    message=health.defender_error,
                    severity="warning",
                )
            )
        else:
            if health.defender_enabled is False:
                findings.append(
                    HealthFinding(
                        title="Microsoft Defender antivirus is disabled",
                        message="Windows reports Defender antivirus protection is disabled.",
                        severity="critical",
                    )
                )
            if health.real_time_protection_enabled is False:
                findings.append(
                    HealthFinding(
                        title="Defender real-time protection is disabled",
                        message="Windows reports Defender real-time protection is turned off.",
                        severity="critical",
                    )
                )
            if health.antivirus_signature_age_days is not None and health.antivirus_signature_age_days >= 7:
                findings.append(
                    HealthFinding(
                        title="Defender signatures are stale",
                        message=(
                            f"Antivirus signatures are {health.antivirus_signature_age_days} days old. "
                            "Run Windows Update or Defender updates."
                        ),
                        severity="warning",
                    )
                )

        if health.firewall_error:
            findings.append(
                HealthFinding(
                    title="Firewall status unavailable",
                    message=health.firewall_error,
                    severity="warning",
                )
            )
        else:
            disabled_profiles = health.disabled_firewall_profiles()
            if disabled_profiles:
                profile_names = ", ".join(profile.name for profile in disabled_profiles)
                findings.append(
                    HealthFinding(
                        title="Windows Firewall profile disabled",
                        message=f"Disabled profiles: {profile_names}. Network exposure may be higher than expected.",
                        severity="warning",
                    )
                )

        if health.bitlocker_error:
            findings.append(
                HealthFinding(
                    title="BitLocker status unavailable",
                    message=health.bitlocker_error,
                    severity="info",
                )
            )
        else:
            system_volumes = [
                volume
                for volume in health.unprotected_bitlocker_volumes()
                if volume.mount_point.rstrip("\\").upper() == "C:"
            ]
            if system_volumes:
                findings.append(
                    HealthFinding(
                        title="System drive BitLocker protection is off",
                        message="The C: volume reports BitLocker protection is off.",
                        severity="warning",
                    )
                )

        return findings

    def _analyze_startup(self, health: StartupHealth) -> list[HealthFinding]:
        if health.is_error:
            return []

        findings: list[HealthFinding] = []
        if health.startup_error:
            findings.append(
                HealthFinding(
                    title="Startup item diagnostics unavailable",
                    message=health.startup_error,
                    severity="warning",
                )
            )
        elif len(health.items()) >= 20:
            findings.append(
                HealthFinding(
                    title="Many startup items are enabled",
                    message=(
                        f"{len(health.items())} startup items are configured to run at sign-in. "
                        "Disabling non-essential entries can improve login time."
                    ),
                    severity="info",
                )
            )

        if health.slow_startup_error:
            findings.append(
                HealthFinding(
                    title="Startup impact diagnostics unavailable",
                    message=health.slow_startup_error,
                    severity="info",
                )
            )
        elif health.slow_services():
            slowest = sorted(
                health.slow_services(),
                key=lambda service: service.startup_time_ms or 0,
                reverse=True,
            )
            service_names = ", ".join(service.service_name for service in slowest[:3])
            findings.append(
                HealthFinding(
                    title="Slow startup services detected",
                    message=f"Windows reported slow service startup for: {service_names}.",
                    severity="warning",
                )
            )

        if health.service_error:
            findings.append(
                HealthFinding(
                    title="Background service diagnostics unavailable",
                    message=health.service_error,
                    severity="warning",
                )
            )
        else:
            stopped_services = health.stopped_automatic_services()
            if len(stopped_services) >= 10:
                findings.append(
                    HealthFinding(
                        title="Several automatic services are stopped",
                        message=(
                            f"{len(stopped_services)} non-delayed automatic services are not running. "
                            "Some may be trigger-start services, so review only if features are failing."
                        ),
                        severity="info",
                    )
                )

        return findings

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {
            "ok": 0,
            "info": 1,
            "warning": 2,
            "critical": 3,
        }.get(severity, 0)

    @classmethod
    def _health_score(cls, findings: list[HealthFinding]) -> int:
        penalties = {"critical": 30, "warning": 12, "info": 3, "ok": 0}
        total_penalty = sum(penalties.get(finding.severity, 0) for finding in findings)
        return max(0, 100 - total_penalty)

    @classmethod
    def _severity_counts(cls, findings: list[HealthFinding]) -> dict[str, int]:
        counts = {"critical": 0, "warning": 0, "info": 0, "ok": 0}
        for finding in findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    @classmethod
    def _severity_rollup(cls, findings: list[HealthFinding]) -> str:
        counts = cls._severity_counts(findings)
        parts = []
        for severity in ("critical", "warning", "info"):
            count = counts[severity]
            if count:
                label = severity if count == 1 else f"{severity}s"
                parts.append(f"{count} {label}")
        return ", ".join(parts) if parts else "No issues"

    def _finalize_findings(self, findings: list[HealthFinding]) -> list[HealthFinding]:
        findings = self._with_recommended_actions(findings)
        findings = self._with_diagnostic_states(findings)
        return self._with_persistence(findings)

    def _with_recommended_actions(self, findings: list[HealthFinding]) -> list[HealthFinding]:
        return [
            finding if finding.recommended_action else replace(
                finding,
                recommended_action=self._recommended_action(finding),
            )
            for finding in findings
        ]

    def _with_diagnostic_states(self, findings: list[HealthFinding]) -> list[HealthFinding]:
        return [
            finding if finding.state else replace(finding, state=self._diagnostic_state(finding))
            for finding in findings
        ]

    def _with_persistence(self, findings: list[HealthFinding]) -> list[HealthFinding]:
        return [
            finding if finding.persistence != "unknown" else replace(
                finding,
                persistence=self._finding_persistence(finding),
            )
            for finding in findings
        ]

    @staticmethod
    def _diagnostic_state(finding: HealthFinding) -> str:
        text = f"{finding.title} {finding.message}".lower()
        if "unavailable" in text:
            unsupported_terms = (
                "not available",
                "not supported",
                "unsupported",
                "not found",
                "missing",
                "is not recognized",
                "does not exist",
            )
            if any(term in text for term in unsupported_terms):
                return "unsupported"
            return "error"
        return finding.severity

    @staticmethod
    def _finding_persistence(finding: HealthFinding) -> str:
        text = f"{finding.title} {finding.message}".lower()
        snapshot_terms = (
            "current cpu",
            "cpu load",
            "ram usage",
            "memory usage",
            "memory pressure",
            "temperature is elevated",
            "temperature is critical",
            "internet reachability",
            "dns resolution",
        )
        persistent_terms = (
            "almost full",
            "low on free space",
            "drive failure risk",
            "drive warning",
            "wear level",
            "read errors",
            "drive status",
            "diagnostics unavailable",
            "storage health",
            "windows update",
            "restart pending",
            "event viewer",
            "reliability monitor",
            "crash history",
            "defender",
            "firewall",
            "bitlocker",
            "startup",
            "automatic services",
            "slow startup",
        )
        if any(term in text for term in snapshot_terms):
            return "snapshot"
        if any(term in text for term in persistent_terms):
            return "persistent"
        return "unknown"

    @staticmethod
    def _recommended_action(finding: HealthFinding) -> str:
        text = f"{finding.title} {finding.message}".lower()
        if "diagnostics unavailable" in text or "status unavailable" in text:
            return "Run the app as administrator and retry the diagnostic."
        if "cpu load" in text:
            return "Open Task Manager and sort processes by CPU usage."
        if "memory" in text or "ram usage" in text:
            return "Close memory-heavy apps or restart the system if usage stays high."
        if "temperature" in text:
            return "Check fans, airflow, dust buildup, and sustained workload."
        if "almost full" in text or "low on free space" in text:
            return "Free disk space with Storage Sense or remove large unused files."
        if "smart" in text or "drive failure" in text or "storage health" in text:
            return "Back up important data and check the drive with the vendor's tool."
        if "windows update" in text or "restart pending" in text:
            return "Open Windows Update, install pending updates, then restart when ready."
        if "event viewer" in text:
            return "Open Event Viewer and review the newest System log errors."
        if "reliability" in text or "crash history" in text:
            return "Open Reliability Monitor and inspect the most recent crash details."
        if "network" in text or "gateway" in text or "dns" in text or "internet reachability" in text:
            return "Check the adapter connection, router/gateway, and DNS settings."
        if "defender" in text:
            return "Open Windows Security and enable Defender protection or update signatures."
        if "firewall" in text:
            return "Open Windows Security and re-enable the affected firewall profile."
        if "bitlocker" in text:
            return "Open BitLocker settings and review protection for the listed volume."
        if "startup" in text:
            return "Open Task Manager Startup apps and disable non-essential entries."
        if "service" in text:
            return "Open Services and review the affected automatic service state."
        return "Review the finding details and rerun diagnostics after making changes."

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_percent(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value.replace("%", "").strip())
        except (AttributeError, ValueError):
            return None

    @staticmethod
    def _parse_temperature(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value.replace("C", "").replace("°", "").strip())
        except (AttributeError, ValueError):
            return None
