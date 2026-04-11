"""Health-analysis models used by the service layer and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

HealthSeverity = Literal["ok", "info", "warning", "critical"]
HealthFindingState = Literal["ok", "info", "warning", "critical", "error", "unsupported"]
HealthFindingPersistence = Literal["snapshot", "persistent", "unknown"]


@dataclass(frozen=True)
class HealthFinding:
    """One diagnosis finding derived from the current live snapshot."""

    title: str
    message: str
    severity: HealthSeverity
    recommended_action: str = ""
    state: HealthFindingState | None = None
    persistence: HealthFindingPersistence = "unknown"


@dataclass(frozen=True)
class HealthSummary:
    """Aggregate diagnosis result for the current system snapshot."""

    overall_status: HealthSeverity
    headline: str
    findings: list[HealthFinding] = field(default_factory=list)
    health_score: int = 100
    severity_counts: dict[str, int] = field(default_factory=dict)
    severity_rollup: str = "No issues"
