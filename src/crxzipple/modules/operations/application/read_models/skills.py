from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crxzipple.modules.operations.application.observation import (
    OperationsObservedEvent,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_MAX_SKILL_EVENT_TOPICS = 160
_MAX_RECENT_SKILL_EVENTS = 240
_RECENT_SKILL_TOPIC_LIMIT = 80


@dataclass(frozen=True, slots=True)
class SkillsOperationsQuery:
    surface: str = "interactive"
    source: str = "all"
    status: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SkillDetailModel:
    skill_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    requirements: OperationsTableSectionModel
    resources: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SkillsOperationsPage:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleModel
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
    active_tab: str
    actions: tuple[RuntimeActionModel, ...]
    recently_resolved_skills: OperationsTableSectionModel
    resolution_outcomes: OperationsChartSectionModel
    top_used_skills: OperationsTableSectionModel
    missing_capabilities: OperationsTableSectionModel
    access_requirements: OperationsTableSectionModel
    capability_requirements: OperationsTableSectionModel
    resolution_logs: OperationsTableSectionModel
    resolver_detail: OperationsTableSectionModel
    import_normalize: tuple[RuntimeActionModel, ...]
    skill_package_sources: OperationsChartSectionModel
    conflicts_overrides: OperationsTableSectionModel
    profile_usage: OperationsTableSectionModel
    skill_details: tuple[SkillDetailModel, ...]


@dataclass(frozen=True, slots=True)
class _SkillRecord:
    package: Any
    status: str
    tone: str
    missing_tools: tuple[str, ...]
    access_checks: tuple[Any, ...]


@dataclass(slots=True)
class SkillsOperationsReadModelProvider:
    skill_manager: Any | None
    tool_service: Any | None = None
    access_service: Any | None = None
    agent_service: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(SkillsOperationsQuery(limit=50))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.recently_resolved_skills),
            lane_locks=_overview_rows(_sources_table(page.skill_package_sources)),
            executor=_overview_rows(page.missing_capabilities),
            actions=page.actions,
        )

    def page(
        self,
        query: SkillsOperationsQuery | None = None,
    ) -> SkillsOperationsPage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        packages = _safe_list_skills(self.skill_manager, surface=query.surface)
        tools = _safe_list_tools(self.tool_service)
        tool_ids = {_text(getattr(tool, "id", "")) for tool in tools if _text(getattr(tool, "id", ""), "")}
        events = _recent_skill_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
        )
        records = tuple(
            _record_for_package(
                package,
                tool_ids=tool_ids,
                access_service=self.access_service,
            )
            for package in packages
        )
        filtered_records = _filter_records(records, query)
        visible_records = filtered_records[query.offset : query.offset + query.limit]
        missing_capabilities = _missing_capabilities_table(records)
        access_requirements = _access_requirements_table(records)
        capability_requirements = _capability_requirements_table(records, tool_ids)
        logs = _resolution_logs_table(events)
        resolver_detail = _resolver_detail_table(records, tool_ids)
        conflicts = _conflicts_table(packages)
        profile_usage = _profile_usage_table(
            self.agent_service,
            surface=query.surface,
            available=len(records),
            ready=sum(1 for record in records if record.status == "Ready"),
        )
        health = _health(
            skill_manager_available=self.skill_manager is not None,
            records=records,
            events=events,
        )
        installed = _skills_table(visible_records, total=len(filtered_records))
        top_used = _requirement_footprint_table(records)
        sources = _source_chart(records)

        return SkillsOperationsPage(
            module="skills",
            title="Skills",
            subtitle="观察技能包目录、声明能力、访问要求、解析结果与导入入口的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Skills operator",
                can_operate=True,
                scope="skills",
            ),
            metrics=_metrics(
                health=health,
                records=records,
                missing=missing_capabilities,
                access=access_requirements,
                events=events,
            ),
            tabs=_tabs(
                installed=installed.total,
                missing=missing_capabilities.total,
                access=access_requirements.total,
                capability=capability_requirements.total,
                logs=logs.total,
                resolver=resolver_detail.total,
                conflicts=conflicts.total,
                profile=profile_usage.total,
            ),
            active_tab="installed",
            actions=_actions(query.surface),
            recently_resolved_skills=installed,
            resolution_outcomes=_readiness_chart(records),
            top_used_skills=top_used,
            missing_capabilities=missing_capabilities,
            access_requirements=access_requirements,
            capability_requirements=capability_requirements,
            resolution_logs=logs,
            resolver_detail=resolver_detail,
            import_normalize=_import_actions(),
            skill_package_sources=sources,
            conflicts_overrides=conflicts,
            profile_usage=profile_usage,
            skill_details=_skill_details(visible_records, events),
        )


def _normalize_query(query: SkillsOperationsQuery | None) -> SkillsOperationsQuery:
    if query is None:
        return SkillsOperationsQuery()
    return SkillsOperationsQuery(
        surface=_text(query.surface, "interactive").strip() or "interactive",
        source=_normalized_filter(query.source),
        status=_normalized_filter(query.status),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _safe_list_skills(skill_manager: Any | None, *, surface: str) -> tuple[Any, ...]:
    list_available = getattr(skill_manager, "list_available", None)
    if not callable(list_available):
        return ()
    try:
        return tuple(list_available(workspace_dir=None, surface=surface) or ())
    except Exception:
        return ()


def _safe_list_tools(tool_service: Any | None) -> tuple[Any, ...]:
    list_enabled_tools = getattr(tool_service, "list_enabled_tools", None)
    if not callable(list_enabled_tools):
        list_enabled_tools = getattr(tool_service, "list_tools", None)
    if not callable(list_enabled_tools):
        return ()
    try:
        return tuple(list_enabled_tools() or ())
    except Exception:
        return ()


def _record_for_package(
    package: Any,
    *,
    tool_ids: set[str],
    access_service: Any | None,
) -> _SkillRecord:
    requirements = getattr(package, "requirements", None)
    required_tools = tuple(_items(getattr(requirements, "required_tools", ())))
    missing_tools = tuple(tool for tool in required_tools if tool not in tool_ids)
    access_values = _access_values(requirements)
    access_checks = tuple(
        _safe_access_check(access_service, requirement)
        for requirement in access_values
    )
    missing_access = tuple(
        check
        for check in access_checks
        if check is not None and not bool(getattr(check, "ready", False))
    )
    if missing_tools or missing_access:
        return _SkillRecord(
            package=package,
            status="Setup Needed",
            tone="warning",
            missing_tools=missing_tools,
            access_checks=tuple(check for check in access_checks if check is not None),
        )
    return _SkillRecord(
        package=package,
        status="Ready",
        tone="success",
        missing_tools=(),
        access_checks=tuple(check for check in access_checks if check is not None),
    )


def _safe_access_check(access_service: Any | None, requirement: str) -> Any | None:
    check_requirement = getattr(access_service, "check_requirement", None)
    if not callable(check_requirement):
        return None
    try:
        return check_requirement(requirement, workspace_dir=None)
    except Exception:
        return None


def _access_values(requirements: Any | None) -> tuple[str, ...]:
    values: list[str] = []
    for field in (
        "compatibility_auth",
        "compatibility_secrets",
        "compatibility_credential_files",
    ):
        values.extend(_items(getattr(requirements, field, ())))
    return tuple(dict.fromkeys(values))


def _recent_skill_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return _dedupe_skill_events(
        (
            *_recent_skill_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *_recent_skill_events_from_observation(operations_observation),
        )
    )


def _recent_skill_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("skills")
    except Exception:
        return ()
    return tuple(
        item
        for item in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(item, OperationsObservedEvent)
    )


def _recent_skill_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = tuple(
        topic
        for topic in _safe_list_event_topics(events_service)
        if _is_skill_event_topic(topic)
    )[:_MAX_SKILL_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=_RECENT_SKILL_TOPIC_LIMIT) or ())
        except Exception:
            continue
        for record in records:
            try:
                observed = observed_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            except Exception:
                continue
            if _is_skill_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_SKILL_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def _is_skill_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("skills.")
        or normalized.startswith("skill.")
        or normalized.startswith("events.named.skills.")
        or normalized.startswith("events.named.skill.")
    )


def _is_skill_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner in {"skills", "skill"}
        or module in {"skills", "skill"}
        or event_name.startswith("skills.")
        or event_name.startswith("skill.")
    )


def _dedupe_skill_events(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[:_MAX_RECENT_SKILL_EVENTS])


def _filter_records(
    records: tuple[_SkillRecord, ...],
    query: SkillsOperationsQuery,
) -> tuple[_SkillRecord, ...]:
    needle = query.search.lower()
    filtered: list[_SkillRecord] = []
    for record in records:
        if query.source != "all" and _normalized_filter(_source(record.package)) != query.source:
            continue
        if query.status != "all" and _normalized_filter(record.status) != query.status:
            continue
        if needle and needle not in _search_blob(record):
            continue
        filtered.append(record)
    return tuple(sorted(filtered, key=lambda item: _skill_name(item.package).lower()))


def _health(
    *,
    skill_manager_available: bool,
    records: tuple[_SkillRecord, ...],
    events: tuple[OperationsObservedEvent, ...],
) -> str:
    if not skill_manager_available:
        return "error"
    if any(event.level == "error" or event.status in {"failed", "error"} for event in events):
        return "warning"
    if any(record.status == "Setup Needed" for record in records):
        return "warning"
    return "healthy"


def _metrics(
    *,
    health: str,
    records: tuple[_SkillRecord, ...],
    missing: OperationsTableSectionModel,
    access: OperationsTableSectionModel,
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[MetricCardModel, ...]:
    ready = sum(1 for record in records if record.status == "Ready")
    sources = {record.package.source for record in records}
    event_failures = sum(1 for event in events if event.level == "error" or event.status in {"failed", "error"})
    return (
        MetricCardModel("health", "Overall Health", _health_label(health), _health_delta(health), _health_tone(health)),
        MetricCardModel("installed_skills", "Installed Skills", str(len(records)), f"{len(sources)} sources", "info" if records else "neutral"),
        MetricCardModel("ready_skills", "Ready Skills", str(ready), "requirements currently satisfied", "success" if ready == len(records) else "warning"),
        MetricCardModel("missing_capabilities", "Missing Capabilities", str(missing.total), "required tools or access not ready", "warning" if missing.total else "success"),
        MetricCardModel("declared_access", "Declared Access", str(access.total), "auth, secrets, credential files", "info" if access.total else "neutral"),
        MetricCardModel("resolution_events", "Resolution Events", str(len(events)), f"{event_failures} failed", "danger" if event_failures else "neutral"),
    )


def _tabs(
    *,
    installed: int,
    missing: int,
    access: int,
    capability: int,
    logs: int,
    resolver: int,
    conflicts: int,
    profile: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("installed", "Installed Skills", installed),
        OperationsTabModel("requirements", "Capability Requirements", capability),
        OperationsTabModel("access", "Access Requirements", access),
        OperationsTabModel("missing", "Missing Capabilities", missing),
        OperationsTabModel("logs", "Resolution Logs", logs),
        OperationsTabModel("resolver", "Resolver Detail", resolver),
        OperationsTabModel("conflicts", "Conflicts / Overrides", conflicts),
        OperationsTabModel("profiles", "Profile Usage", profile),
    )


def _actions(surface: str) -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="list_skills",
            label="List Skills",
            owner="skills",
            kind="navigation",
            method="GET",
            endpoint=f"/operations/skills?surface={surface}",
        ),
        RuntimeActionModel(
            id="validate_skill",
            label="Validate Skill",
            owner="skills",
            risk="controlled",
            audit_event="skills.package.validate",
            method="POST",
            endpoint="/operations/skills/validate",
        ),
    )


def _import_actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="validate_skill_package",
            label="Validate Package",
            owner="skills",
            risk="controlled",
            audit_event="skills.package.validate",
            method="POST",
            endpoint="/operations/skills/validate",
        ),
        RuntimeActionModel(
            id="install_global_skill",
            label="Install Global Skill",
            owner="skills",
            risk="controlled",
            requires_confirmation=True,
            audit_event="skills.global.install",
            method="POST",
            endpoint="/operations/skills/install",
        ),
    )


def _skills_table(
    records: tuple[_SkillRecord, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=_skill_id(record.package),
            cells={
                "skill": _skill_name(record.package),
                "source": _source(record.package),
                "status": record.status,
                "version": _text(getattr(record.package, "version", None), "1"),
                "tags": _joined(getattr(record.package, "tags", ())),
                "required_tools": _joined(getattr(getattr(record.package, "requirements", None), "required_tools", ())),
                "access": str(len(_access_values(getattr(record.package, "requirements", None)))),
                "resources": str(len(tuple(getattr(record.package, "resources", ()) or ()))),
                "path": _short(_text(getattr(record.package, "root_path", "")), 72),
                "action": "Open",
            },
            status=record.status,
            tone=record.tone,
        )
        for record in records
    ]
    return OperationsTableSectionModel(
        id="recently_resolved_skills",
        title="Installed Skills",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("source", "Source"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("version", "Version"),
            OperationsTableColumnModel("tags", "Tags"),
            OperationsTableColumnModel("required_tools", "Required Tools"),
            OperationsTableColumnModel("access", "Access"),
            OperationsTableColumnModel("resources", "Resources"),
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No skills available for this surface.",
    )


def _readiness_chart(records: tuple[_SkillRecord, ...]) -> OperationsChartSectionModel:
    counts = Counter(record.status for record in records)
    segments = (
        OperationsChartSegmentModel("ready", "Ready", counts["Ready"], "success"),
        OperationsChartSegmentModel("setup_needed", "Setup Needed", counts["Setup Needed"], "warning"),
    )
    return OperationsChartSectionModel(
        "resolution_outcomes",
        "Skill Readiness",
        "donut",
        sum(item.value for item in segments),
        tuple(item for item in segments if item.value),
    )


def _requirement_footprint_table(
    records: tuple[_SkillRecord, ...],
) -> OperationsTableSectionModel:
    ranked = sorted(
        records,
        key=lambda record: (
            _requirement_count(record.package),
            len(tuple(getattr(record.package, "resources", ()) or ())),
        ),
        reverse=True,
    )
    rows = [
        OperationsTableRowModel(
            id=f"footprint:{_skill_id(record.package)}",
            cells={
                "skill": _skill_name(record.package),
                "required_tools": str(len(_items(getattr(getattr(record.package, "requirements", None), "required_tools", ())))),
                "suggested_tools": str(len(_items(getattr(getattr(record.package, "requirements", None), "suggested_tools", ())))),
                "access": str(len(_access_values(getattr(record.package, "requirements", None)))),
                "effects": str(len(_items(getattr(getattr(record.package, "requirements", None), "required_effects", ())))),
                "resources": str(len(tuple(getattr(record.package, "resources", ()) or ()))),
                "status": record.status,
            },
            status=record.status,
            tone=record.tone,
        )
        for record in ranked[:12]
    ]
    return OperationsTableSectionModel(
        id="top_used_skills",
        title="Requirement Footprint",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("required_tools", "Required Tools"),
            OperationsTableColumnModel("suggested_tools", "Suggested Tools"),
            OperationsTableColumnModel("access", "Access"),
            OperationsTableColumnModel("effects", "Effects"),
            OperationsTableColumnModel("resources", "Resources"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(ranked),
        empty_state="No skill requirement footprint.",
    )


def _missing_capabilities_table(
    records: tuple[_SkillRecord, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in records:
        for tool_id in record.missing_tools:
            rows.append(
                OperationsTableRowModel(
                    id=f"missing-tool:{_skill_id(record.package)}:{tool_id}",
                    cells={
                        "type": "Tool",
                        "required": tool_id,
                        "by": _skill_name(record.package),
                        "impact": "Required",
                        "resolved_by": "Register or enable tool",
                        "status": "Setup Needed",
                    },
                    status="Setup Needed",
                    tone="warning",
                )
            )
        for check in record.access_checks:
            if bool(getattr(check, "ready", False)):
                continue
            requirement = _text(getattr(getattr(check, "requirement", None), "raw", ""))
            rows.append(
                OperationsTableRowModel(
                    id=f"missing-access:{_skill_id(record.package)}:{requirement}",
                    cells={
                        "type": "Access",
                        "required": requirement,
                        "by": _skill_name(record.package),
                        "impact": "Required",
                        "resolved_by": "Access setup",
                        "status": _status_label(getattr(check, "status", "setup_needed")),
                    },
                    status=_status_label(getattr(check, "status", "setup_needed")),
                    tone="warning",
                )
            )
    return OperationsTableSectionModel(
        id="missing_capabilities",
        title="Missing Capabilities",
        columns=(
            OperationsTableColumnModel("type", "Capability Type"),
            OperationsTableColumnModel("required", "Required Item"),
            OperationsTableColumnModel("by", "Required By"),
            OperationsTableColumnModel("impact", "Impact"),
            OperationsTableColumnModel("resolved_by", "Resolved By"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No missing skill capabilities.",
    )


def _access_requirements_table(
    records: tuple[_SkillRecord, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in records:
        for check in record.access_checks:
            requirement = _text(getattr(getattr(check, "requirement", None), "raw", ""))
            status = "Ready" if bool(getattr(check, "ready", False)) else _status_label(getattr(check, "status", "setup_needed"))
            rows.append(
                OperationsTableRowModel(
                    id=f"access:{_skill_id(record.package)}:{requirement}",
                    cells={
                        "asset": requirement,
                        "skill": _skill_name(record.package),
                        "purpose": _status_label(getattr(getattr(check, "requirement", None), "kind", "access")),
                        "status": status,
                        "reason": _short(getattr(check, "reason", ""), 96),
                        "setup": "Available" if bool(getattr(check, "setup_available", False)) else "-",
                    },
                    status=status,
                    tone="success" if bool(getattr(check, "ready", False)) else "warning",
                )
            )
    return OperationsTableSectionModel(
        id="access_requirements",
        title="Access Requirements",
        columns=(
            OperationsTableColumnModel("asset", "Access Asset"),
            OperationsTableColumnModel("skill", "Required By"),
            OperationsTableColumnModel("purpose", "Purpose"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("setup", "Setup"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No access requirements declared by skills.",
    )


def _capability_requirements_table(
    records: tuple[_SkillRecord, ...],
    tool_ids: set[str],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in records:
        requirements = getattr(record.package, "requirements", None)
        for field, requirement_type in (
            ("required_tools", "Required Tool"),
            ("suggested_tools", "Suggested Tool"),
            ("optional_tools", "Optional Tool"),
            ("required_effects", "Required Effect"),
        ):
            for value in _items(getattr(requirements, field, ())):
                is_tool = field.endswith("tools")
                ready = not is_tool or value in tool_ids or field != "required_tools"
                status = "Ready" if ready else "Setup Needed"
                rows.append(
                    OperationsTableRowModel(
                        id=f"capability:{_skill_id(record.package)}:{field}:{value}",
                        cells={
                            "capability": value,
                            "type": requirement_type,
                            "by": _skill_name(record.package),
                            "resolved": value if ready else "-",
                            "status": status,
                        },
                        status=status,
                        tone="success" if ready else "warning",
                    )
                )
    return OperationsTableSectionModel(
        id="capability_requirements",
        title="Capability Requirements",
        columns=(
            OperationsTableColumnModel("capability", "Capability"),
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("by", "Required By"),
            OperationsTableColumnModel("resolved", "Resolved To"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No capability requirements declared by skills.",
    )


def _resolution_logs_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": _short_event_name(event.event_name),
                "skill": _text(event.payload.get("skill") or event.payload.get("skill_name") or event.entity_id),
                "surface": _text(event.payload.get("surface"), "-"),
                "result": _status_label(event.status),
                "reason": _event_details(event.payload),
                "trace": _text(event.trace_id),
            },
            status=event.status,
            tone=_event_tone(event),
        )
        for event in events[:120]
    ]
    return OperationsTableSectionModel(
        id="resolution_logs",
        title="Resolution Logs",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(events),
        empty_state="No skill resolution events.",
    )


def _resolver_detail_table(
    records: tuple[_SkillRecord, ...],
    tool_ids: set[str],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"resolver:{_skill_id(record.package)}",
            cells={
                "skill": _skill_name(record.package),
                "input": _joined(getattr(getattr(record.package, "requirements", None), "required_tools", ())),
                "available": str(sum(1 for tool in _items(getattr(getattr(record.package, "requirements", None), "required_tools", ())) if tool in tool_ids)),
                "missing": _joined(record.missing_tools),
                "result": record.status,
                "next_step": "Register or enable missing tools" if record.missing_tools else "-",
            },
            status=record.status,
            tone=record.tone,
        )
        for record in records
    ]
    return OperationsTableSectionModel(
        id="resolver_detail",
        title="Resolver Detail",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("input", "Required Tools"),
            OperationsTableColumnModel("available", "Available"),
            OperationsTableColumnModel("missing", "Missing"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("next_step", "Next Step"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No resolver detail.",
    )


def _source_chart(records: tuple[_SkillRecord, ...]) -> OperationsChartSectionModel:
    counts = Counter(_source(record.package) for record in records)
    return OperationsChartSectionModel(
        "skill_package_sources",
        "Skill Package Sources",
        "donut",
        sum(counts.values()),
        tuple(
            OperationsChartSegmentModel(source, _status_label(source), count, "info")
            for source, count in sorted(counts.items())
        ),
    )


def _sources_table(chart: OperationsChartSectionModel) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"source:{segment.id}",
            cells={
                "source": segment.label,
                "skills": str(segment.value),
                "status": "Installed",
            },
            status="Installed",
            tone=segment.tone,
        )
        for segment in chart.segments
    ]
    return OperationsTableSectionModel(
        id="skill_sources",
        title="Skill Package Sources",
        columns=(
            OperationsTableColumnModel("source", "Source"),
            OperationsTableColumnModel("skills", "Skills"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No skill package sources.",
    )


def _conflicts_table(packages: tuple[Any, ...]) -> OperationsTableSectionModel:
    by_name: dict[str, list[Any]] = defaultdict(list)
    for package in packages:
        by_name[_skill_name(package)].append(package)
    conflicts = tuple((name, items) for name, items in by_name.items() if len(items) > 1)
    rows = [
        OperationsTableRowModel(
            id=f"conflict:{name}",
            cells={
                "type": "Duplicate Skill",
                "details": ", ".join(_source(item) for item in items),
                "winner": _source(items[0]),
                "action": "Inspect",
            },
            status="Conflict",
            tone="warning",
        )
        for name, items in conflicts
    ]
    return OperationsTableSectionModel(
        id="conflicts_overrides",
        title="Conflicts / Overrides",
        columns=(
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("winner", "Winner"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No skill conflicts or overrides.",
    )


def _profile_usage_table(
    agent_service: Any | None,
    *,
    surface: str,
    available: int,
    ready: int,
) -> OperationsTableSectionModel:
    list_profiles = getattr(agent_service, "list_profiles", None)
    profiles: tuple[Any, ...] = ()
    if callable(list_profiles):
        try:
            profiles = tuple(list_profiles() or ())
        except Exception:
            profiles = ()
    rows = [
        OperationsTableRowModel(
            id=f"profile:{_text(getattr(profile, 'id', ''))}",
            cells={
                "profile": _text(getattr(profile, "id", "")),
                "surface": surface,
                "available_skills": str(available),
                "ready_skills": str(ready),
                "status": "Enabled" if bool(getattr(profile, "enabled", True)) else "Disabled",
            },
            status="Enabled" if bool(getattr(profile, "enabled", True)) else "Disabled",
            tone="success" if bool(getattr(profile, "enabled", True)) else "neutral",
        )
        for profile in profiles[:40]
    ]
    if not rows and available:
        rows = [
            OperationsTableRowModel(
                id=f"profile:surface:{surface}",
                cells={
                    "profile": "all",
                    "surface": surface,
                    "available_skills": str(available),
                    "ready_skills": str(ready),
                    "status": "Available",
                },
                status="Available",
                tone="success",
            )
        ]
    return OperationsTableSectionModel(
        id="profile_usage",
        title="Profile Usage",
        columns=(
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("available_skills", "Available Skills"),
            OperationsTableColumnModel("ready_skills", "Ready Skills"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No profile usage is available.",
    )


def _skill_details(
    records: tuple[_SkillRecord, ...],
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[SkillDetailModel, ...]:
    return tuple(
        SkillDetailModel(
            skill_id=_skill_id(record.package),
            title=_skill_name(record.package),
            status=record.status,
            tone=record.tone,
            summary=(
                OperationsKeyValueItemModel("Skill", _skill_name(record.package)),
                OperationsKeyValueItemModel("Source", _source(record.package)),
                OperationsKeyValueItemModel("Version", _text(getattr(record.package, "version", None), "1")),
                OperationsKeyValueItemModel("Tags", _joined(getattr(record.package, "tags", ()))),
                OperationsKeyValueItemModel("Required Tools", _joined(getattr(getattr(record.package, "requirements", None), "required_tools", ()))),
                OperationsKeyValueItemModel("Path", _text(getattr(record.package, "root_path", ""))),
            ),
            requirements=_detail_requirements_table(record),
            resources=_resources_table(record.package),
            events=_events_for_skill_table(events, _skill_name(record.package)),
            raw_payload=_skill_payload(record.package),
        )
        for record in records[:80]
    )


def _detail_requirements_table(record: _SkillRecord) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    requirements = getattr(record.package, "requirements", None)
    for field, label in (
        ("required_tools", "Required Tool"),
        ("suggested_tools", "Suggested Tool"),
        ("optional_tools", "Optional Tool"),
        ("required_effects", "Required Effect"),
        ("compatibility_auth", "Access"),
        ("compatibility_secrets", "Secret"),
        ("compatibility_credential_files", "Credential File"),
        ("setup_hints", "Setup Hint"),
    ):
        for value in _items(getattr(requirements, field, ())):
            status = "Setup Needed" if value in record.missing_tools else "Declared"
            rows.append(
                OperationsTableRowModel(
                    id=f"detail-requirement:{field}:{value}",
                    cells={
                        "type": label,
                        "value": value,
                        "status": status,
                    },
                    status=status,
                    tone="warning" if status == "Setup Needed" else "neutral",
                )
            )
    return OperationsTableSectionModel(
        id="skill_requirements",
        title="Skill Requirements",
        columns=(
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("value", "Value"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No requirements declared.",
    )


def _resources_table(package: Any) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"resource:{_skill_id(package)}:{_text(getattr(resource, 'path', ''))}",
            cells={
                "path": _text(getattr(resource, "path", "")),
                "kind": _text(getattr(resource, "kind", "")),
                "size": _format_bytes(int(getattr(resource, "size_bytes", 0) or 0)),
            },
            status="Available",
            tone="success",
        )
        for resource in tuple(getattr(package, "resources", ()) or ())
    ]
    return OperationsTableSectionModel(
        id="skill_resources",
        title="Skill Resources",
        columns=(
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("size", "Size"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No resources bundled with this skill.",
    )


def _events_for_skill_table(
    events: tuple[OperationsObservedEvent, ...],
    skill_name: str,
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if event.entity_id == skill_name
        or _text(event.payload.get("skill"), "") == skill_name
        or _text(event.payload.get("skill_name"), "") == skill_name
    )
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": _short_event_name(event.event_name),
                "status": _status_label(event.status),
                "details": _event_details(event.payload),
            },
            status=event.status,
            tone=_event_tone(event),
        )
        for event in filtered[:30]
    ]
    return OperationsTableSectionModel(
        id="skill_events",
        title="Skill Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
        ),
        rows=tuple(rows),
        total=len(filtered),
        empty_state="No related skill events.",
    )


def _skill_payload(package: Any) -> dict[str, Any]:
    requirements = getattr(package, "requirements", None)
    manifest = getattr(package, "manifest", None)
    return {
        "name": _skill_name(package),
        "description": _text(getattr(package, "description", "")),
        "version": _text(getattr(package, "version", None), "1"),
        "source": _source(package),
        "root_path": _text(getattr(package, "root_path", "")),
        "manifest_path": _text(getattr(package, "manifest_path", "")),
        "instructions_path": _text(getattr(package, "instructions_path", "")),
        "tags": list(_items(getattr(package, "tags", ()))),
        "requirements": {
            "required_tools": list(_items(getattr(requirements, "required_tools", ()))),
            "optional_tools": list(_items(getattr(requirements, "optional_tools", ()))),
            "suggested_tools": list(_items(getattr(requirements, "suggested_tools", ()))),
            "required_effects": list(_items(getattr(requirements, "required_effects", ()))),
            "surfaces": list(_items(getattr(requirements, "surfaces", ()))),
            "compatibility_auth": list(_items(getattr(requirements, "compatibility_auth", ()))),
            "compatibility_secrets": list(_items(getattr(requirements, "compatibility_secrets", ()))),
            "compatibility_credential_files": list(_items(getattr(requirements, "compatibility_credential_files", ()))),
            "setup_hints": list(_items(getattr(requirements, "setup_hints", ()))),
        },
        "manifest": {
            "api_version": _text(getattr(manifest, "api_version", "")),
            "kind": _text(getattr(manifest, "kind", "")),
            "when_to_use": _text(getattr(manifest, "when_to_use", "")),
            "anti_patterns": list(_items(getattr(manifest, "anti_patterns", ()))),
            "surfaces": list(_items(getattr(manifest, "surfaces", ()))),
        },
    }


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def _search_blob(record: _SkillRecord) -> str:
    requirements = getattr(record.package, "requirements", None)
    return " ".join(
        (
            _skill_name(record.package),
            _source(record.package),
            _text(getattr(record.package, "description", "")),
            _joined(getattr(record.package, "tags", ())),
            _joined(getattr(requirements, "required_tools", ())),
            _joined(getattr(requirements, "suggested_tools", ())),
            record.status,
        )
    ).lower()


def _requirement_count(package: Any) -> int:
    requirements = getattr(package, "requirements", None)
    return (
        len(_items(getattr(requirements, "required_tools", ())))
        + len(_items(getattr(requirements, "optional_tools", ())))
        + len(_items(getattr(requirements, "suggested_tools", ())))
        + len(_items(getattr(requirements, "required_effects", ())))
        + len(_access_values(requirements))
    )


def _skill_name(package: Any) -> str:
    return _text(getattr(package, "name", ""))


def _skill_id(package: Any) -> str:
    return _skill_name(package).replace(" ", "_")


def _source(package: Any) -> str:
    return _text(getattr(package, "source", "unknown"), "unknown")


def _items(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,) if values.strip() else ()
    if isinstance(values, (list, tuple, set)):
        return tuple(_text(item, "") for item in values if _text(item, ""))
    return (_text(values),)


def _joined(values: Any) -> str:
    items = _items(values)
    return ", ".join(items) if items else "-"


def _event_details(payload: dict[str, Any]) -> str:
    for key in ("reason", "message", "summary", "error_message", "skill", "skill_name", "status"):
        value = payload.get(key)
        if value is not None and _text(value, ""):
            return _short(value, 120)
    return "-"


def _short_event_name(event_name: str) -> str:
    return event_name.removeprefix("skills.").removeprefix("skill.")


def _event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning":
        return "warning"
    return "success" if event.status in {"ready", "success", "observed"} else "neutral"


def _status_label(status: Any) -> str:
    raw = getattr(status, "value", status)
    text = _text(raw, "unknown").replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in text.split()) or "-"


def _normalized_filter(value: Any) -> str:
    text = _text(value, "all").strip().lower().replace(" ", "_").replace("-", "_")
    return text or "all"


def _health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def _health_delta(health: str) -> str:
    if health == "error":
        return "Skill manager is not connected"
    if health == "warning":
        return "Some skill requirements need setup"
    return "Skill packages are queryable"


def _health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"


def _format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(max(size, 0))
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} B"
    return f"{value:.1f} {unit}"


def _short(value: Any, size: int = 80) -> str:
    text = _text(value)
    if len(text) <= size:
        return text
    return f"{text[: max(8, size - 8)]}...{text[-5:]}"


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(item, "") for item in value if _text(item, ""))
    if isinstance(value, dict):
        return ", ".join(f"{key}={_text(item, '')}" for key, item in sorted(value.items()))
    text = str(value).strip()
    return text if text else default
