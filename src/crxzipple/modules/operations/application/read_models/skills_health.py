from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsTabModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    health_delta,
    health_label,
    health_tone,
    int_value,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
)


def health(
    *,
    skill_manager_available: bool,
    records: tuple[SkillRecord, ...],
    events: tuple[OperationsObservedEvent, ...],
) -> str:
    if not skill_manager_available:
        return "error"
    if any(event.level == "error" or event.status in {"failed", "error"} for event in events):
        return "warning"
    if any(record.status == "Setup Needed" for record in records):
        return "warning"
    return "healthy"


def metrics(
    *,
    health: str,
    records: tuple[SkillRecord, ...],
    missing: OperationsTableSectionModel,
    access: OperationsTableSectionModel,
    events: tuple[OperationsObservedEvent, ...],
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> tuple[MetricCardModel, ...]:
    ready = sum(1 for record in records if record.status == "Ready")
    sources = {record.package.source for record in records}
    event_total = _bucket_event_count(event_buckets) or len(events)
    event_failures = _bucket_failure_count(event_buckets) if event_buckets else sum(
        1 for event in events if event.level == "error" or event.status in {"failed", "error"}
    )
    return (
        MetricCardModel("health", "Overall Health", health_label(health), health_delta(health), health_tone(health)),
        MetricCardModel("installed_skills", "Installed Skills", str(len(records)), f"{len(sources)} sources", "info" if records else "neutral"),
        MetricCardModel("ready_skills", "Ready Skills", str(ready), "requirements currently satisfied", "success" if ready == len(records) else "warning"),
        MetricCardModel("missing_capabilities", "Missing Capabilities", str(missing.total), "required tools or access not ready", "warning" if missing.total else "success"),
        MetricCardModel("declared_access", "Declared Access", str(access.total), "required access declarations", "info" if access.total else "neutral"),
        MetricCardModel("resolution_events", "Resolution Events", str(event_total), f"{event_failures} failed", "danger" if event_failures else "neutral"),
    )


def _bucket_event_count(event_buckets: tuple[dict[str, Any], ...]) -> int:
    return sum(int_value(bucket.get("count")) for bucket in event_buckets)


def _bucket_failure_count(event_buckets: tuple[dict[str, Any], ...]) -> int:
    return sum(
        int_value(bucket.get("count"))
        for bucket in event_buckets
        if bucket.get("level") == "error" or bucket.get("status") in {"failed", "error"}
    )


def tabs(
    *,
    installed: int,
    missing: int,
    access: int,
    capability: int,
    logs: int,
    reads: int,
    resolver: int,
    authoring: int,
    authoring_failures: int,
    conflicts: int,
    profile: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("installed", "Installed Skills", installed),
        OperationsTabModel("requirements", "Capability Requirements", capability),
        OperationsTabModel("access", "Access Requirements", access),
        OperationsTabModel("missing", "Missing Capabilities", missing),
        OperationsTabModel("logs", "Resolution Logs", logs),
        OperationsTabModel("reads", "Skill Reads", reads),
        OperationsTabModel("resolver", "Resolver Detail", resolver),
        OperationsTabModel("authoring", "Authoring Backlog", authoring),
        OperationsTabModel("authoring_failures", "Authoring Failures", authoring_failures),
        OperationsTabModel("conflicts", "Conflicts / Overrides", conflicts),
        OperationsTabModel("profiles", "Profile Usage", profile),
    )

