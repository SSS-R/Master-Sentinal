"""Derives user-facing health findings from live diagnostics."""

from __future__ import annotations

from models.health_models import HealthFinding, HealthSummary


class HealthAnalyzer:
    """Turns raw diagnostics into actionable health findings."""

    def analyze(
        self,
        cpu_load: float,
        ram: dict[str, object],
        gpus: list[dict[str, str]],
        disks: list[dict[str, str]],
        smart: dict[str, str],
    ) -> HealthSummary:
        """Return a diagnosis summary for the current live snapshot."""
        findings: list[HealthFinding] = []

        findings.extend(self._collect_module_errors(gpus, disks, smart))
        findings.extend(self._analyze_cpu(cpu_load))
        findings.extend(self._analyze_ram(ram))
        findings.extend(self._analyze_gpus(gpus))
        findings.extend(self._analyze_disks(disks))
        findings.extend(self._analyze_smart(smart))

        findings.sort(key=lambda finding: self._severity_rank(finding.severity), reverse=True)

        if not findings:
            return HealthSummary(
                overall_status="ok",
                headline="No immediate issues detected",
                findings=[
                    HealthFinding(
                        title="System looks stable",
                        message="Live diagnostics did not detect any immediate performance or storage concerns.",
                        severity="ok",
                    )
                ],
            )

        highest = findings[0].severity
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
        )

    def _collect_module_errors(
        self,
        gpus: list[dict[str, str]],
        disks: list[dict[str, str]],
        smart: dict[str, str],
    ) -> list[HealthFinding]:
        findings: list[HealthFinding] = []

        for label, items in (("GPU", gpus), ("Disk", disks)):
            for item in items:
                if "Error" in item:
                    findings.append(
                        HealthFinding(
                            title=f"{label} diagnostics unavailable",
                            message=item["Error"],
                            severity="warning",
                        )
                    )

        if "Error" in smart:
            findings.append(
                HealthFinding(
                    title="SMART diagnostics unavailable",
                    message=smart["Error"],
                    severity="warning",
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

    def _analyze_ram(self, ram: dict[str, object]) -> list[HealthFinding]:
        percent = self._coerce_float(ram.get("Percentage"))
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

    def _analyze_gpus(self, gpus: list[dict[str, str]]) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for gpu in gpus:
            temp = self._parse_temperature(gpu.get("Temperature"))
            name = gpu.get("Name", "GPU")
            if temp is None:
                continue
            if temp >= 90:
                findings.append(
                    HealthFinding(
                        title=f"{name} temperature is critical",
                        message=f"{name} is reporting {temp:.0f} C. Check airflow, dust buildup, and fan behavior.",
                        severity="critical",
                    )
                )
            elif temp >= 80:
                findings.append(
                    HealthFinding(
                        title=f"{name} temperature is elevated",
                        message=f"{name} is reporting {temp:.0f} C. Watch cooling if this persists under moderate load.",
                        severity="warning",
                    )
                )
        return findings

    def _analyze_disks(self, disks: list[dict[str, str]]) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for disk in disks:
            percent_used = self._parse_percent(disk.get("Percent"))
            if percent_used is None:
                continue

            label = disk.get("Mountpoint", disk.get("Device", "Disk"))
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

    def _analyze_smart(self, smart: dict[str, str]) -> list[HealthFinding]:
        findings: list[HealthFinding] = []
        for key, value in smart.items():
            if key == "Error":
                continue

            normalized = value.lower()
            if "pred fail" in normalized or "fail" in normalized:
                findings.append(
                    HealthFinding(
                        title="SMART reported a drive failure risk",
                        message=value,
                        severity="critical",
                    )
                )
            elif "caution" in normalized or "warning" in normalized:
                findings.append(
                    HealthFinding(
                        title="SMART reported a drive warning",
                        message=value,
                        severity="warning",
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
