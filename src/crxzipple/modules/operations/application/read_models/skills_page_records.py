from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.skills_common import (
    items,
    normalized_filter,
    search_blob,
    skill_name,
    source,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.skills_models import (
    SkillRecord,
    SkillsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.skills_requirement_tables import (
    access_values,
)
from crxzipple.modules.skills.application.environment import unsupported_platforms


def skill_records_for_packages(
    packages: tuple[Any, ...],
    *,
    tool_ids: set[str],
    access_service: Any | None,
    readiness_events_by_skill: dict[str, OperationsObservedEvent],
) -> tuple[SkillRecord, ...]:
    return tuple(
        skill_record_for_package(
            package,
            tool_ids=tool_ids,
            access_service=access_service,
            readiness_event=readiness_events_by_skill.get(skill_name(package)),
        )
        for package in packages
    )


def skill_record_for_package(
    package: Any,
    *,
    tool_ids: set[str],
    access_service: Any | None,
    readiness_event: OperationsObservedEvent | None = None,
) -> SkillRecord:
    requirements = getattr(package, "requirements", None)
    required_tools = tuple(items(getattr(requirements, "required_tools", ())))
    missing_tools = tuple(tool for tool in required_tools if tool not in tool_ids)
    unsupported_platform_values = unsupported_platforms(
        tuple(items(getattr(requirements, "supported_platforms", ()))),
    )
    required_access = access_values(requirements)
    access_checks = tuple(
        _safe_access_check(access_service, requirement)
        for requirement in required_access
    )
    missing_access = tuple(
        check
        for check in access_checks
        if check is not None and not bool(getattr(check, "ready", False))
    )
    if readiness_event is not None:
        return _readiness_event_record(
            package,
            readiness_event=readiness_event,
            access_checks=access_checks,
        )
    missing_access_values = tuple(
        text(getattr(getattr(check, "requirement", None), "raw", ""))
        for check in missing_access
    )
    if unsupported_platform_values:
        return SkillRecord(
            package=package,
            status="Unsupported",
            tone="warning",
            missing_tools=missing_tools,
            missing_access=missing_access_values,
            missing_effects=(),
            unsupported_surfaces=(),
            unsupported_platforms=unsupported_platform_values,
            access_checks=tuple(check for check in access_checks if check is not None),
        )
    if missing_tools or missing_access_values:
        return SkillRecord(
            package=package,
            status="Setup Needed",
            tone="warning",
            missing_tools=missing_tools,
            missing_access=missing_access_values,
            missing_effects=(),
            unsupported_surfaces=(),
            unsupported_platforms=(),
            access_checks=tuple(check for check in access_checks if check is not None),
        )
    return SkillRecord(
        package=package,
        status="Ready",
        tone="success",
        missing_tools=(),
        missing_access=(),
        missing_effects=(),
        unsupported_surfaces=(),
        unsupported_platforms=(),
        access_checks=tuple(check for check in access_checks if check is not None),
    )


def filter_skill_records(
    records: tuple[SkillRecord, ...],
    query: SkillsOperationsQuery,
) -> tuple[SkillRecord, ...]:
    needle = query.search.lower()
    filtered: list[SkillRecord] = []
    for record in records:
        if query.source != "all" and normalized_filter(source(record.package)) != query.source:
            continue
        if query.status != "all" and normalized_filter(record.status) != query.status:
            continue
        if needle and needle not in search_blob(record):
            continue
        filtered.append(record)
    return tuple(sorted(filtered, key=lambda item: skill_name(item.package).lower()))


def _readiness_event_record(
    package: Any,
    *,
    readiness_event: OperationsObservedEvent,
    access_checks: tuple[Any | None, ...],
) -> SkillRecord:
    payload = readiness_event.payload
    status = status_label(payload.get("status") or readiness_event.status)
    return SkillRecord(
        package=package,
        status=status,
        tone="success" if status == "Ready" else "warning",
        missing_tools=items(payload.get("missing_tools")),
        missing_access=items(payload.get("missing_access")),
        missing_effects=items(payload.get("missing_effects")),
        unsupported_surfaces=items(payload.get("unsupported_surfaces")),
        unsupported_platforms=items(payload.get("unsupported_platforms")),
        access_checks=tuple(check for check in access_checks if check is not None),
        readiness_event=readiness_event,
    )


def _safe_access_check(access_service: Any | None, requirement: str) -> Any | None:
    check_requirement = getattr(access_service, "check_requirement", None)
    if not callable(check_requirement):
        return None
    try:
        return check_requirement(requirement, workspace_dir=None)
    except Exception:
        return None
