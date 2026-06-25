from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.access_values import (
    bool_value,
    dict_value,
    int_value,
    list_value,
    short,
    string_values,
    text,
)


def target_label(target: dict[str, Any]) -> str:
    return text(target.get("display_name") or target.get("resource_id"))


def target_worst_status(target: dict[str, Any]) -> str:
    checks = target_checks(target)
    if not checks:
        return "ready" if bool_value(target.get("ready")) else "setup_needed"
    statuses = [text(check.get("status"), "unknown") for check in checks]
    for candidate in ("expired", "unsupported", "setup_needed", "waiting_user"):
        if candidate in statuses:
            return candidate
    if all(status == "ready" for status in statuses):
        return "ready"
    return statuses[0] or "unknown"


def target_checks(target: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for requirement_set in list_value(target.get("requirement_sets")):
        for check in list_value(dict_value(requirement_set).get("checks")):
            result.append(dict_value(check))
    return tuple(result)


def target_metadata(target: dict[str, Any]) -> dict[str, Any]:
    return dict_value(target.get("metadata"))


def requirements_text(target: dict[str, Any]) -> str:
    metadata = target_metadata(target)
    values = string_values(metadata.get("declared_requirements")) or string_values(
        metadata.get("requirements"),
    )
    return ", ".join(values[:5]) if values else "-"


def required_by(target: dict[str, Any]) -> str:
    metadata = target_metadata(target)
    parts: list[str] = []
    for key, label in (
        ("tool_ids", "tool"),
        ("llm_profile_ids", "llm"),
        ("channel_profiles", "channel"),
    ):
        values = string_values(metadata.get(key))
        if values:
            parts.append(f"{label}: {', '.join(values[:3])}")
    return " / ".join(parts) if parts else "-"


def target_reason(target: dict[str, Any]) -> str:
    for check in target_checks(target):
        if bool_value(check.get("ready")):
            continue
        reason = text(check.get("reason"), "")
        if reason:
            return short(reason, 140)
    return "Ready" if bool_value(target.get("ready")) else "-"


def impact(target: dict[str, Any]) -> str:
    usage_count = int_value(target_metadata(target).get("usage_count"), 0)
    if not bool_value(target.get("ready")) and usage_count >= 2:
        return "High"
    if not bool_value(target.get("ready")):
        return "Medium"
    return "Low"


def usage_records(targets: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for target in targets:
        for usage in list_value(target_metadata(target).get("usages")):
            records.append({"target": target, "usage": dict_value(usage)})
    return tuple(records)


def setup_flow_records(
    targets: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for target in targets:
        for check in target_checks(target):
            flow = check.get("setup_flow")
            if isinstance(flow, dict):
                records.append({"target": target, "check": check})
    return tuple(records)


def events_for_target(
    events: tuple[OperationsObservedEvent, ...],
    target: dict[str, Any],
) -> tuple[OperationsObservedEvent, ...]:
    resource_id = text(target.get("resource_id"), "")
    requirements = set(string_values(target_metadata(target).get("requirements")))
    return tuple(
        event
        for event in events
        if event.entity_id == resource_id
        or text(event.payload.get("resource_id"), "") == resource_id
        or text(event.payload.get("requirement"), "") in requirements
    )


def search_blob(target: dict[str, Any]) -> str:
    metadata = target_metadata(target)
    values = [
        target_label(target),
        text(target.get("resource_id")),
        requirements_text(target),
        required_by(target),
        target_reason(target),
        text(metadata.get("asset_kind")),
        text(metadata.get("usage_types")),
    ]
    return " ".join(values).lower()
