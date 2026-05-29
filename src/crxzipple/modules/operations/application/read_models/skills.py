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
from crxzipple.modules.operations.application.read_models.event_buckets import (
    recent_event_buckets,
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
from crxzipple.modules.skills.application.events import (
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_APPLY_FAILED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_OPERATION_EVENT_NAMES,
    SKILL_READ_FAILED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_RESOLUTION_COMPLETED_EVENT,
)
from crxzipple.modules.skills.application.environment import unsupported_platforms
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


_MAX_RECENT_SKILL_EVENTS = 240
_RECENT_SKILL_TOPIC_LIMIT = 80
_SKILL_EVENT_TOPICS = tuple(
    f"events.named.{event_name}" for event_name in SKILL_OPERATION_EVENT_NAMES
)
_AUTHORING_EVENT_PREFIX = "skills.authoring.draft."
_AUTHORING_TERMINAL_EVENTS = {
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
}
_AUTHORING_TERMINAL_STATUSES = {"applied", "rejected", "expired"}


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
    skill_reads: OperationsTableSectionModel
    resolver_detail: OperationsTableSectionModel
    authoring_backlog: OperationsTableSectionModel
    authoring_failures: OperationsTableSectionModel
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
    missing_access: tuple[str, ...]
    missing_effects: tuple[str, ...]
    unsupported_surfaces: tuple[str, ...]
    unsupported_platforms: tuple[str, ...]
    access_checks: tuple[Any, ...]
    readiness_event: OperationsObservedEvent | None = None


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
        event_buckets = recent_event_buckets(
            self.operations_observation,
            module="skills",
            hours=24,
            limit=1000,
        )
        readiness_events = _latest_readiness_events_by_skill(events)
        records = tuple(
            _record_for_package(
                package,
                tool_ids=tool_ids,
                access_service=self.access_service,
                readiness_event=readiness_events.get(_skill_name(package)),
            )
            for package in packages
        )
        filtered_records = _filter_records(records, query)
        visible_records = filtered_records[query.offset : query.offset + query.limit]
        missing_capabilities = _missing_capabilities_table(records)
        access_requirements = _access_requirements_table(records)
        capability_requirements = _capability_requirements_table(records, tool_ids)
        logs = _resolution_logs_table(events)
        skill_reads = _skill_reads_table(events)
        resolver_detail = _resolver_detail_table(records, tool_ids)
        authoring_backlog = _authoring_backlog_table(events)
        authoring_failures = _authoring_failures_table(events)
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
        top_used = _skill_usage_table(events)
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
                event_buckets=event_buckets,
            ),
            tabs=_tabs(
                installed=installed.total,
                missing=missing_capabilities.total,
                access=access_requirements.total,
                capability=capability_requirements.total,
                logs=logs.total,
                reads=skill_reads.total,
                resolver=resolver_detail.total,
                authoring=authoring_backlog.total,
                authoring_failures=authoring_failures.total,
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
            skill_reads=skill_reads,
            resolver_detail=resolver_detail,
            authoring_backlog=authoring_backlog,
            authoring_failures=authoring_failures,
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
    readiness_event: OperationsObservedEvent | None = None,
) -> _SkillRecord:
    requirements = getattr(package, "requirements", None)
    required_tools = tuple(_items(getattr(requirements, "required_tools", ())))
    missing_tools = tuple(tool for tool in required_tools if tool not in tool_ids)
    missing_access_values: tuple[str, ...] = ()
    missing_effects: tuple[str, ...] = ()
    unsupported_surfaces: tuple[str, ...] = ()
    unsupported_platform_values = unsupported_platforms(
        tuple(_items(getattr(requirements, "supported_platforms", ()))),
    )
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
    if readiness_event is not None:
        payload = readiness_event.payload
        missing_tools = _items(payload.get("missing_tools"))
        missing_access_values = _items(payload.get("missing_access"))
        missing_effects = _items(payload.get("missing_effects"))
        unsupported_surfaces = _items(payload.get("unsupported_surfaces"))
        unsupported_platform_values = _items(payload.get("unsupported_platforms"))
        status = _status_label(payload.get("status") or readiness_event.status)
        return _SkillRecord(
            package=package,
            status=status,
            tone="success" if status == "Ready" else "warning",
            missing_tools=missing_tools,
            missing_access=missing_access_values,
            missing_effects=missing_effects,
            unsupported_surfaces=unsupported_surfaces,
            unsupported_platforms=unsupported_platform_values,
            access_checks=tuple(check for check in access_checks if check is not None),
            readiness_event=readiness_event,
        )
    missing_access_values = tuple(
        _text(getattr(getattr(check, "requirement", None), "raw", ""))
        for check in missing_access
    )
    if unsupported_platform_values:
        return _SkillRecord(
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
        return _SkillRecord(
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
    return _SkillRecord(
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


def _safe_access_check(access_service: Any | None, requirement: str) -> Any | None:
    check_requirement = getattr(access_service, "check_requirement", None)
    if not callable(check_requirement):
        return None
    try:
        return check_requirement(requirement, workspace_dir=None)
    except Exception:
        return None


def _access_values(requirements: Any | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_items(getattr(requirements, "required_access", ()))))


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
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in _SKILL_EVENT_TOPICS:
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


def _latest_readiness_events_by_skill(
    events: tuple[OperationsObservedEvent, ...],
) -> dict[str, OperationsObservedEvent]:
    latest: dict[str, OperationsObservedEvent] = {}
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        if event.event_name != "skills.readiness.changed":
            continue
        skill = _text(
            event.payload.get("skill")
            or event.payload.get("skill_name")
            or event.entity_id,
            "",
        )
        if not skill or skill in latest:
            continue
        latest[skill] = event
    return latest


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
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> tuple[MetricCardModel, ...]:
    ready = sum(1 for record in records if record.status == "Ready")
    sources = {record.package.source for record in records}
    event_total = _bucket_event_count(event_buckets) or len(events)
    event_failures = _bucket_failure_count(event_buckets) if event_buckets else sum(
        1 for event in events if event.level == "error" or event.status in {"failed", "error"}
    )
    return (
        MetricCardModel("health", "Overall Health", _health_label(health), _health_delta(health), _health_tone(health)),
        MetricCardModel("installed_skills", "Installed Skills", str(len(records)), f"{len(sources)} sources", "info" if records else "neutral"),
        MetricCardModel("ready_skills", "Ready Skills", str(ready), "requirements currently satisfied", "success" if ready == len(records) else "warning"),
        MetricCardModel("missing_capabilities", "Missing Capabilities", str(missing.total), "required tools or access not ready", "warning" if missing.total else "success"),
        MetricCardModel("declared_access", "Declared Access", str(access.total), "required access declarations", "info" if access.total else "neutral"),
        MetricCardModel("resolution_events", "Resolution Events", str(event_total), f"{event_failures} failed", "danger" if event_failures else "neutral"),
    )


def _bucket_event_count(event_buckets: tuple[dict[str, Any], ...]) -> int:
    return sum(_int(bucket.get("count")) for bucket in event_buckets)


def _bucket_failure_count(event_buckets: tuple[dict[str, Any], ...]) -> int:
    return sum(
        _int(bucket.get("count"))
        for bucket in event_buckets
        if bucket.get("level") == "error" or bucket.get("status") in {"failed", "error"}
    )


def _tabs(
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
            id="sync_skill_catalog",
            label="Sync Skill Catalog",
            owner="skills",
            risk="controlled",
            audit_event="skills.source.sync",
            method="POST",
            endpoint="/operations/skills/sync",
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
        OperationsChartSegmentModel("unsupported", "Unsupported", counts["Unsupported"], "warning"),
        OperationsChartSegmentModel("disabled", "Disabled", counts["Disabled"], "neutral"),
        OperationsChartSegmentModel("invalid", "Invalid", counts["Invalid"], "danger"),
    )
    return OperationsChartSectionModel(
        "resolution_outcomes",
        "Skill Readiness",
        "donut",
        sum(item.value for item in segments),
        tuple(item for item in segments if item.value),
    )


def _skill_usage_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    usage: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "resolved": 0,
            "reads": 0,
            "failures": 0,
            "last_seen": None,
            "last_status": "observed",
            "surfaces": set(),
        },
    )
    for event in sorted(events, key=lambda item: coerce_utc_datetime(item.occurred_at)):
        if event.event_name == SKILL_RESOLUTION_COMPLETED_EVENT:
            for item in _dict_items(event.payload.get("skills")):
                skill = _text(
                    item.get("skill") or item.get("skill_name"),
                    "",
                )
                if not skill:
                    continue
                entry = usage[skill]
                entry["resolved"] += 1
                entry["last_status"] = _text(item.get("status") or event.status, "observed")
                surface = _text(event.payload.get("surface"), "")
                if surface:
                    entry["surfaces"].add(surface)
                entry["last_seen"] = event.occurred_at
        if event.event_name in {SKILL_READ_SUCCEEDED_EVENT, SKILL_READ_FAILED_EVENT}:
            skill = _text(
                event.payload.get("skill")
                or event.payload.get("skill_name")
                or event.entity_id,
                "",
            )
            if not skill:
                continue
            entry = usage[skill]
            entry["reads"] += 1
            if event.event_name == SKILL_READ_FAILED_EVENT:
                entry["failures"] += 1
            entry["last_status"] = event.status
            surface = _text(event.payload.get("surface"), "")
            if surface:
                entry["surfaces"].add(surface)
            entry["last_seen"] = event.occurred_at

    ranked = sorted(
        usage.items(),
        key=lambda item: (
            _int(item[1]["resolved"]) + _int(item[1]["reads"]),
            coerce_utc_datetime(item[1]["last_seen"]),
        ),
        reverse=True,
    )
    rows = [
        OperationsTableRowModel(
            id=f"skill-usage:{skill}",
            cells={
                "skill": skill,
                "resolved": str(_int(values["resolved"])),
                "reads": str(_int(values["reads"])),
                "failures": str(_int(values["failures"])),
                "surface": ", ".join(sorted(values["surfaces"])) or "-",
                "last_seen": (
                    format_datetime_utc(values["last_seen"])
                    if values["last_seen"] is not None
                    else "-"
                ),
                "status": _status_label(values["last_status"]),
            },
            status=_status_label(values["last_status"]),
            tone="danger" if _int(values["failures"]) else "success",
        )
        for skill, values in ranked[:12]
    ]
    return OperationsTableSectionModel(
        id="top_used_skills",
        title="Runtime Skill Usage",
        columns=(
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("resolved", "Resolved"),
            OperationsTableColumnModel("reads", "Reads"),
            OperationsTableColumnModel("failures", "Failures"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("last_seen", "Last Seen"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(ranked),
        empty_state="No runtime skill usage events.",
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
            if requirement in record.missing_access:
                continue
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
        for requirement in record.missing_access:
            rows.append(
                OperationsTableRowModel(
                    id=f"missing-access:{_skill_id(record.package)}:{requirement}",
                    cells={
                        "type": "Access",
                        "required": requirement,
                        "by": _skill_name(record.package),
                        "impact": "Required",
                        "resolved_by": "Access setup",
                        "status": "Setup Needed",
                    },
                    status="Setup Needed",
                    tone="warning",
                )
            )
        for effect_id in record.missing_effects:
            rows.append(
                OperationsTableRowModel(
                    id=f"missing-effect:{_skill_id(record.package)}:{effect_id}",
                    cells={
                        "type": "Authorization Effect",
                        "required": effect_id,
                        "by": _skill_name(record.package),
                        "impact": "Required",
                        "resolved_by": "Grant effect authorization",
                        "status": "Setup Needed",
                    },
                    status="Setup Needed",
                    tone="warning",
                )
            )
        for surface in record.unsupported_surfaces:
            rows.append(
                OperationsTableRowModel(
                    id=f"unsupported-surface:{_skill_id(record.package)}:{surface}",
                    cells={
                        "type": "Surface",
                        "required": surface,
                        "by": _skill_name(record.package),
                        "impact": "Not available on this surface",
                        "resolved_by": "Switch surface or update manifest",
                        "status": "Unsupported",
                    },
                    status="Unsupported",
                    tone="warning",
                )
            )
        for platform in record.unsupported_platforms:
            rows.append(
                OperationsTableRowModel(
                    id=f"unsupported-platform:{_skill_id(record.package)}:{platform}",
                    cells={
                        "type": "Platform",
                        "required": platform,
                        "by": _skill_name(record.package),
                        "impact": "Not available on this runtime platform",
                        "resolved_by": "Switch runtime platform or update manifest",
                        "status": "Unsupported",
                    },
                    status="Unsupported",
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
        seen_requirements: set[str] = set()
        for check in record.access_checks:
            requirement = _text(getattr(getattr(check, "requirement", None), "raw", ""))
            seen_requirements.add(requirement)
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
        for requirement in record.missing_access:
            if requirement in seen_requirements:
                continue
            rows.append(
                OperationsTableRowModel(
                    id=f"access:{_skill_id(record.package)}:{requirement}",
                    cells={
                        "asset": requirement,
                        "skill": _skill_name(record.package),
                        "purpose": "Access",
                        "status": "Setup Needed",
                        "reason": "reported by skills readiness",
                        "setup": "-",
                    },
                    status="Setup Needed",
                    tone="warning",
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
            ("supported_platforms", "Supported Platform"),
        ):
            for value in _items(getattr(requirements, field, ())):
                if field == "required_tools":
                    ready = value in tool_ids and value not in record.missing_tools
                elif field == "required_effects":
                    ready = value not in record.missing_effects
                elif field == "supported_platforms":
                    ready = not record.unsupported_platforms
                else:
                    ready = True
                status = "Ready" if ready else "Unsupported"
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


def _skill_reads_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    read_events = tuple(
        event
        for event in events
        if event.event_name in {SKILL_READ_SUCCEEDED_EVENT, SKILL_READ_FAILED_EVENT}
    )
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "skill": _text(
                    event.payload.get("skill")
                    or event.payload.get("skill_name")
                    or event.entity_id,
                ),
                "path": _short(
                    event.payload.get("resolved_path")
                    or event.payload.get("path")
                    or "SKILL.md",
                    72,
                ),
                "surface": _text(event.payload.get("surface"), "-"),
                "result": _status_label(event.status),
                "duration": _duration_label(event.payload.get("duration_ms")),
                "reason": _read_event_details(event),
            },
            status=event.status,
            tone=_event_tone(event),
        )
        for event in read_events[:80]
    ]
    return OperationsTableSectionModel(
        id="skill_reads",
        title="Skill Reads",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("duration", "Duration"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(read_events),
        empty_state="No skill read events.",
    )


def _authoring_backlog_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    latest_by_draft: dict[str, OperationsObservedEvent] = {}
    for event in sorted(
        (event for event in events if _is_authoring_event(event)),
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        draft_id = _authoring_draft_id(event)
        if not draft_id or draft_id in latest_by_draft:
            continue
        latest_by_draft[draft_id] = event

    active_events = tuple(
        event
        for event in latest_by_draft.values()
        if not _is_authoring_terminal_event(event)
    )
    rows = [
        OperationsTableRowModel(
            id=f"authoring:{_authoring_draft_id(event)}",
            cells={
                "updated": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "draft": _short(_authoring_draft_id(event), 44),
                "skill": _authoring_skill_name(event),
                "intent": _status_label(event.payload.get("intent")),
                "status": _authoring_status_label(event),
                "readiness": _authoring_readiness_label(event),
                "actor": _text(event.payload.get("actor"), "-"),
                "next_step": _authoring_next_step(event),
            },
            status=_authoring_status_label(event),
            tone=_authoring_tone(event),
        )
        for event in sorted(
            active_events,
            key=lambda item: coerce_utc_datetime(item.occurred_at),
            reverse=True,
        )[:80]
    ]
    return OperationsTableSectionModel(
        id="authoring_backlog",
        title="Authoring Backlog",
        columns=(
            OperationsTableColumnModel("updated", "Updated"),
            OperationsTableColumnModel("draft", "Draft"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("intent", "Intent"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("readiness", "Readiness"),
            OperationsTableColumnModel("actor", "Actor"),
            OperationsTableColumnModel("next_step", "Next Step"),
        ),
        rows=tuple(rows),
        total=len(active_events),
        empty_state="No active skill authoring drafts.",
    )


def _authoring_failures_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    failure_events = tuple(
        event
        for event in events
        if _is_authoring_event(event) and _is_authoring_failure_event(event)
    )
    rows = [
        OperationsTableRowModel(
            id=f"authoring-failure:{_authoring_draft_id(event)}:{event.cursor or event.id}",
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "draft": _short(_authoring_draft_id(event), 44),
                "skill": _authoring_skill_name(event),
                "event": _short_event_name(event.event_name),
                "status": _authoring_status_label(event),
                "validation": _authoring_validation_summary(event),
                "error": _authoring_error_details(event),
                "actor": _text(event.payload.get("actor"), "-"),
            },
            status=_authoring_status_label(event),
            tone="danger",
        )
        for event in failure_events[:80]
    ]
    return OperationsTableSectionModel(
        id="authoring_failures",
        title="Authoring Failures",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("draft", "Draft"),
            OperationsTableColumnModel("skill", "Skill"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("validation", "Validation"),
            OperationsTableColumnModel("error", "Error"),
            OperationsTableColumnModel("actor", "Actor"),
        ),
        rows=tuple(rows),
        total=len(failure_events),
        empty_state="No skill authoring failures.",
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
                "missing": _joined(
                    (
                        *record.missing_tools,
                        *record.missing_access,
                        *record.missing_effects,
                        *record.unsupported_platforms,
                    )
                ),
                "result": record.status,
                "next_step": _resolver_next_step(record),
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


def _resolver_next_step(record: _SkillRecord) -> str:
    if record.missing_tools:
        return "Register or enable missing tools"
    if record.missing_access:
        return "Complete Access setup"
    if record.missing_effects:
        return "Grant required authorization effects"
    if record.unsupported_surfaces:
        return "Switch surface or update skill manifest"
    if record.unsupported_platforms:
        return "Switch runtime platform or update skill manifest"
    return "-"


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
        ("required_access", "Access"),
        ("supported_platforms", "Supported Platform"),
        ("setup_hints", "Setup Hint"),
    ):
        for value in _items(getattr(requirements, field, ())):
            missing_values = (
                *record.missing_tools,
                *record.missing_access,
                *record.missing_effects,
                *record.unsupported_surfaces,
                *record.unsupported_platforms,
            )
            if field == "supported_platforms" and record.unsupported_platforms:
                status = "Unsupported"
            elif value in missing_values:
                status = "Setup Needed"
            else:
                status = "Declared"
            rows.append(
                OperationsTableRowModel(
                    id=f"detail-requirement:{field}:{value}",
                    cells={
                        "type": label,
                        "value": value,
                        "status": status,
                    },
                    status=status,
                    tone="warning" if status != "Declared" else "neutral",
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
            "required_access": list(_items(getattr(requirements, "required_access", ()))),
            "supported_platforms": list(_items(getattr(requirements, "supported_platforms", ()))),
            "setup_hints": list(_items(getattr(requirements, "setup_hints", ()))),
        },
        "manifest": {
            "api_version": _text(getattr(manifest, "api_version", "")),
            "kind": _text(getattr(manifest, "kind", "")),
            "when_to_use": _text(getattr(manifest, "when_to_use", "")),
            "anti_patterns": list(_items(getattr(manifest, "anti_patterns", ()))),
            "surfaces": list(_items(getattr(manifest, "surfaces", ()))),
            "supported_platforms": list(_items(getattr(manifest, "supported_platforms", ()))),
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


def _dict_items(values: Any) -> tuple[dict[str, Any], ...]:
    if values is None:
        return ()
    if isinstance(values, dict):
        return (dict(values),)
    if isinstance(values, (list, tuple, set)):
        return tuple(dict(item) for item in values if isinstance(item, dict))
    return ()


def _joined(values: Any) -> str:
    items = _items(values)
    return ", ".join(items) if items else "-"


def _is_authoring_event(event: OperationsObservedEvent) -> bool:
    return event.event_name.startswith(_AUTHORING_EVENT_PREFIX)


def _authoring_draft_id(event: OperationsObservedEvent) -> str:
    return _text(event.payload.get("draft_id") or event.entity_id or event.cursor or event.id)


def _authoring_skill_name(event: OperationsObservedEvent) -> str:
    return _text(
        event.payload.get("skill")
        or event.payload.get("skill_name")
        or event.entity_id,
        "-",
    )


def _authoring_status_label(event: OperationsObservedEvent) -> str:
    return _status_label(event.payload.get("draft_status") or event.status)


def _authoring_readiness_label(event: OperationsObservedEvent) -> str:
    value = event.payload.get("readiness_status")
    if value is None:
        return "-"
    return _status_label(value)


def _is_authoring_terminal_event(event: OperationsObservedEvent) -> bool:
    if event.event_name in _AUTHORING_TERMINAL_EVENTS:
        return True
    status = _normalized_filter(event.payload.get("draft_status") or event.status)
    return status in _AUTHORING_TERMINAL_STATUSES


def _is_authoring_failure_event(event: OperationsObservedEvent) -> bool:
    if event.event_name == SKILL_DRAFT_APPLY_FAILED_EVENT:
        return True
    if event.level == "error" or event.status in {"failed", "error"}:
        return True
    return _int(event.payload.get("validation_error_count")) > 0


def _authoring_tone(event: OperationsObservedEvent) -> str:
    if _is_authoring_failure_event(event):
        return "danger"
    status = _normalized_filter(event.payload.get("draft_status") or event.status)
    if status in {"invalid", "failed", "error"}:
        return "danger"
    readiness = _normalized_filter(event.payload.get("readiness_status"))
    if readiness not in {"all", "ready", "valid", "ok", "success", "succeeded"}:
        return "warning"
    if status in {"validated", "applied"}:
        return "success"
    return "neutral"


def _authoring_next_step(event: OperationsObservedEvent) -> str:
    if event.event_name == SKILL_DRAFT_APPLY_FAILED_EVENT:
        return "Review failure and revise draft"
    if _int(event.payload.get("validation_error_count")) > 0:
        return "Fix validation errors"
    status = _normalized_filter(event.payload.get("draft_status") or event.status)
    if status == "draft":
        return "Validate draft"
    if status == "invalid":
        return "Revise draft"
    if event.event_name.endswith(".diff_built"):
        return "Apply owner write after approval"
    if status == "validated":
        return "Build diff or apply owner write"
    return "Inspect draft"


def _authoring_validation_summary(event: OperationsObservedEvent) -> str:
    errors = _int(event.payload.get("validation_error_count"))
    warnings = _int(event.payload.get("validation_warning_count"))
    if errors or warnings:
        return f"{errors} errors / {warnings} warnings"
    readiness = _authoring_readiness_label(event)
    return readiness if readiness != "-" else "-"


def _authoring_error_details(event: OperationsObservedEvent) -> str:
    validation_errors = _items(event.payload.get("validation_errors"))
    if validation_errors:
        return _short("; ".join(validation_errors), 140)
    for key in ("error_message", "reason", "message"):
        value = event.payload.get(key)
        if value is not None and _text(value, ""):
            return _short(value, 140)
    return _event_details(event.payload)


def _event_details(payload: dict[str, Any]) -> str:
    missing = (
        _items(payload.get("missing_tools"))
        + _items(payload.get("missing_access"))
        + _items(payload.get("missing_effects"))
        + _items(payload.get("unsupported_platforms"))
    )
    if missing:
        return _short(", ".join(missing), 120)
    for key in ("reason", "message", "summary", "error_message", "skill", "skill_name", "status"):
        value = payload.get(key)
        if value is not None and _text(value, ""):
            return _short(value, 120)
    return "-"


def _read_event_details(event: OperationsObservedEvent) -> str:
    payload = event.payload
    if event.event_name == SKILL_READ_FAILED_EVENT:
        return _short(
            payload.get("error_message") or payload.get("reason") or payload.get("message") or "-",
            120,
        )
    return _short(payload.get("source") or payload.get("resolved_path") or "read completed", 120)


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


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def _duration_label(value: Any) -> str:
    if value is None:
        return "-"
    try:
        duration_ms = float(value)
    except (TypeError, ValueError):
        return _text(value)
    if duration_ms < 1000:
        return f"{duration_ms:.0f} ms"
    return f"{duration_ms / 1000:.2f} s"


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
