from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
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

_MAX_ACCESS_EVENT_TOPICS = 120
_MAX_RECENT_ACCESS_EVENTS = 240
_RECENT_ACCESS_TOPIC_LIMIT = 80


@dataclass(frozen=True, slots=True)
class AccessOperationsQuery:
    status: str = "all"
    kind: str = "all"
    usage_type: str = "all"
    search: str = ""
    include_ready: bool = True
    include_disabled: bool = False
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class AccessTargetDetailModel:
    target_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    checks: OperationsTableSectionModel
    usages: OperationsTableSectionModel
    setup: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessOperationsPage:
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
    access_targets: OperationsTableSectionModel
    missing_access: OperationsTableSectionModel
    credential_health: OperationsChartSectionModel
    provider_auth_blocked: OperationsTableSectionModel
    credentials_by_kind: OperationsChartSectionModel
    expiring_soon: OperationsTableSectionModel
    auth_success_rate: OperationsChartSectionModel
    authentication_status: OperationsTableSectionModel
    access_usage: OperationsTableSectionModel
    recent_access_events: OperationsTableSectionModel
    fallback_problems: OperationsTableSectionModel
    setup_flows: OperationsTableSectionModel
    target_details: tuple[AccessTargetDetailModel, ...]


@dataclass(slots=True)
class AccessOperationsReadModelProvider:
    access_service: Any | None
    access_governance_repository: Any | None
    llm_service: Any | None
    tool_service: Any | None
    channel_profile_service: Any | None
    lark_channel_runtime_service: Any | None
    web_channel_runtime_service: Any | None
    webhook_channel_runtime_service: Any | None
    settings_query_service: Any | None = None
    settings_environment: str | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(AccessOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.missing_access),
            lane_locks=_overview_rows(page.access_targets),
            executor=_overview_rows(page.authentication_status),
            actions=page.actions,
        )

    def page(
        self,
        query: AccessOperationsQuery | None = None,
    ) -> AccessOperationsPage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        inventory = _collect_inventory(self, query=query)
        targets = tuple(_as_dict(item) for item in _as_list(inventory.get("targets")))
        filtered_targets = _filter_targets(targets, query)
        visible_targets = filtered_targets[query.offset : query.offset + query.limit]
        missing_targets = tuple(item for item in filtered_targets if not _bool(item.get("ready")))
        observed_events = _recent_access_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
        )
        health = _health(access_service=self.access_service, targets=targets)
        access_targets = _access_targets_table(
            visible_targets,
            total=len(filtered_targets),
        )
        missing_access = _missing_access_table(missing_targets)
        authentication_status = _authentication_status_table(
            visible_targets,
            total=len(filtered_targets),
        )
        access_usage = _access_usage_table(visible_targets)

        return AccessOperationsPage(
            module="access",
            title="Access",
            subtitle="观察凭证绑定、访问要求、授权缺口、setup flow 与访问相关事件的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Access operator",
                can_operate=True,
                scope="access",
            ),
            metrics=_metrics(
                health=health,
                targets=targets,
                observed_events=observed_events,
            ),
            tabs=_tabs(
                targets=len(filtered_targets),
                missing=len(missing_targets),
                usage=access_usage.total,
                setup=len(_setup_flow_records(filtered_targets)),
                events=len(observed_events),
            ),
            active_tab="targets",
            actions=_actions(),
            access_targets=access_targets,
            missing_access=missing_access,
            credential_health=_credential_health(targets),
            provider_auth_blocked=_provider_auth_blocked_table(missing_targets),
            credentials_by_kind=_credentials_by_kind(targets),
            expiring_soon=_expiring_soon_table(filtered_targets),
            auth_success_rate=_auth_success_rate(targets),
            authentication_status=authentication_status,
            access_usage=access_usage,
            recent_access_events=_access_events_table(observed_events),
            fallback_problems=_fallback_problems_table(
                targets=missing_targets,
                events=observed_events,
            ),
            setup_flows=_setup_flows_table(filtered_targets),
            target_details=_target_details(
                visible_targets,
                observed_events=observed_events,
            ),
        )


def _normalize_query(
    query: AccessOperationsQuery | None,
) -> AccessOperationsQuery:
    if query is None:
        return AccessOperationsQuery()
    return AccessOperationsQuery(
        status=_normalized_filter(query.status),
        kind=_normalized_filter(query.kind),
        usage_type=_normalized_filter(query.usage_type),
        search=query.search.strip() if isinstance(query.search, str) else "",
        include_ready=bool(query.include_ready),
        include_disabled=bool(query.include_disabled),
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _collect_inventory(
    provider: AccessOperationsReadModelProvider,
    *,
    query: AccessOperationsQuery,
) -> dict[str, Any]:
    if provider.access_service is None:
        return {"ready": False, "targets": [], "counts": {"total": 0, "ready": 0, "blocked": 0}}
    container = SimpleNamespace(
        access_service=provider.access_service,
        access_governance_repository=provider.access_governance_repository,
        settings_query_service=provider.settings_query_service,
        settings=SimpleNamespace(environment=provider.settings_environment),
        llm_service=provider.llm_service or _NullService(),
        tool_service=provider.tool_service or _NullService(),
        channel_profile_service=provider.channel_profile_service or _NullService(),
        lark_channel_runtime_service=provider.lark_channel_runtime_service
        or _NullChannelRuntime(),
        web_channel_runtime_service=provider.web_channel_runtime_service
        or _NullChannelRuntime(),
        webhook_channel_runtime_service=provider.webhook_channel_runtime_service
        or _NullChannelRuntime(),
    )
    try:
        return dict(
            collect_access_inventory(
                container,
                include_ready=query.include_ready,
                include_disabled=query.include_disabled,
            )
        )
    except Exception:
        return {"ready": False, "targets": [], "counts": {"total": 0, "ready": 0, "blocked": 0}}


def _recent_access_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return _dedupe_events(
        (
            *_recent_access_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *_recent_access_events_from_observation(operations_observation),
        )
    )


def _recent_access_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("access")
    except Exception:
        return ()
    return tuple(
        item
        for item in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(item, OperationsObservedEvent)
    )


def _recent_access_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = tuple(
        topic
        for topic in _safe_list_event_topics(events_service)
        if _is_access_event_topic(topic)
    )[:_MAX_ACCESS_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in topics:
        try:
            records = tuple(
                read_recent(topic, limit=_RECENT_ACCESS_TOPIC_LIMIT) or (),
            )
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
            if _is_access_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_ACCESS_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def _is_access_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("access.")
        or normalized.startswith("authorization.")
        or normalized.startswith("auth.")
        or normalized.startswith("events.named.access.")
        or normalized.startswith("events.named.authorization.")
        or normalized.startswith("events.named.auth.")
    )


def _is_access_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner in {"access", "authorization", "auth"}
        or module in {"access", "authorization", "auth"}
        or event_name.startswith("access.")
        or event_name.startswith("authorization.")
        or event_name.startswith("auth.")
    )


def _dedupe_events(
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
    return tuple(result[:_MAX_RECENT_ACCESS_EVENTS])


def _health(
    *,
    access_service: Any | None,
    targets: tuple[dict[str, Any], ...],
) -> str:
    if access_service is None:
        return "error"
    if any(_target_worst_status(target) in {"expired"} for target in targets):
        return "error"
    if any(not _bool(target.get("ready")) for target in targets):
        return "warning"
    return "healthy"


def _metrics(
    *,
    health: str,
    targets: tuple[dict[str, Any], ...],
    observed_events: tuple[OperationsObservedEvent, ...],
) -> tuple[MetricCardModel, ...]:
    ready = sum(1 for item in targets if _bool(item.get("ready")))
    blocked = len(targets) - ready
    setup = sum(1 for item in targets if _bool(item.get("setup_available")))
    failed_events = sum(1 for item in observed_events if item.level == "error" or item.status in {"failed", "error"})
    return (
        MetricCardModel("health", "Overall Health", _health_label(health), _health_delta(health), _health_tone(health)),
        MetricCardModel("access_assets", "Access Assets", str(len(targets)), f"{ready} ready", "info" if targets else "neutral"),
        MetricCardModel("missing_access", "Missing Access", str(blocked), "blocked or missing targets", "warning" if blocked else "success"),
        MetricCardModel("setup_available", "Setup Available", str(setup), "targets with setup flow", "info" if setup else "neutral"),
        MetricCardModel("usage", "Consumers", str(len(_usage_records(targets))), "declared LLM/tool/channel usages", "info"),
        MetricCardModel("failed_auth", "Failed Auth", str(failed_events), "observed access error events", "danger" if failed_events else "success"),
    )


def _tabs(
    *,
    targets: int,
    missing: int,
    usage: int,
    setup: int,
    events: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("targets", "Access Targets", targets),
        OperationsTabModel("missing", "Missing Access", missing, "warning" if missing else "success"),
        OperationsTabModel("auth_status", "Authentication Status", targets),
        OperationsTabModel("usage", "Access Usage", usage),
        OperationsTabModel("setup", "Setup Flows", setup),
        OperationsTabModel("events", "Access Events", events),
        OperationsTabModel("fallbacks", "Fallback Problems", missing + events),
    )


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_access_inventory",
            label="Open Access Inventory",
            owner="access",
            risk="normal",
            method="GET",
            endpoint="/operations/access/inventory",
        ),
        RuntimeActionModel(
            id="check_access",
            label="Check Access",
            owner="access",
            risk="normal",
            audit_event="access.readiness.check",
            method="POST",
            endpoint="/operations/access/check",
        ),
        RuntimeActionModel(
            id="setup_access",
            label="Setup Access",
            owner="access",
            risk="controlled",
            method="GET",
            endpoint="/operations/access/setup?target={target}",
        ),
    )


def _access_targets_table(
    targets: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = [_target_row(target) for target in targets]
    return OperationsTableSectionModel(
        id="access_targets",
        title="Access Targets",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("requirements", "Requirements"),
            OperationsTableColumnModel("usage", "Usage"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No records.",
    )


def _missing_access_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows = [_target_row(target) for target in targets]
    return OperationsTableSectionModel(
        id="missing_access",
        title="Missing Access",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("required_by", "Required By"),
            OperationsTableColumnModel("requirements", "Requirements"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("impact", "Impact"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No missing access.",
    )


def _provider_auth_blocked_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        metadata = _metadata(target)
        usage_types = _string_values(metadata.get("usage_types"))
        if usage_types and "llm_profile" not in usage_types and "tool" not in usage_types:
            continue
        rows.append(
            OperationsTableRowModel(
                id=_text(target.get("resource_id"), ""),
                cells={
                    "asset": _target_label(target),
                    "issue": _target_reason(target),
                    "affected": str(_int(metadata.get("usage_count"), 0)),
                    "action": "Setup" if _bool(target.get("setup_available")) else "Open",
                },
                status=_target_worst_status(target),
                tone=_tone_for_status(_target_worst_status(target)),
            )
        )
    return OperationsTableSectionModel(
        id="provider_auth_blocked",
        title="Provider Auth / Access Blocked",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("issue", "Issue"),
            OperationsTableColumnModel("affected", "Affected"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No provider access blockers.",
    )


def _authentication_status_table(
    targets: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        status = _target_worst_status(target)
        rows.append(
            OperationsTableRowModel(
                id=_text(target.get("resource_id"), ""),
                cells={
                    "asset": _target_label(target),
                    "status": _status_label(status),
                    "readiness": "Ready" if _bool(target.get("ready")) else "Blocked",
                    "checks": str(len(_checks(target))),
                    "usage": str(_int(_metadata(target).get("usage_count"), 0)),
                    "reason": _target_reason(target),
                },
                status=_status_label(status),
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="authentication_status",
        title="Authentication Status",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("readiness", "Readiness"),
            OperationsTableColumnModel("checks", "Checks"),
            OperationsTableColumnModel("usage", "Usage"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No records.",
    )


def _access_usage_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in _usage_records(targets):
        target = record["target"]
        usage = record["usage"]
        status = _target_worst_status(target)
        rows.append(
            OperationsTableRowModel(
                id=f"{_text(target.get('resource_id'), '')}:{_text(usage.get('usage_type'), '')}:{_text(usage.get('usage_id'), '')}",
                cells={
                    "consumer": _text(usage.get("display_name") or usage.get("usage_id")),
                    "usage_type": _text(usage.get("usage_type")),
                    "usage_id": _text(usage.get("usage_id")),
                    "asset": _target_label(target),
                    "status": _status_label(status),
                    "enabled": "Yes" if _bool(usage.get("enabled")) else "No",
                },
                status=_status_label(status),
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="access_usage",
        title="Access Usage",
        columns=(
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("usage_type", "Usage Type"),
            OperationsTableColumnModel("usage_id", "Usage ID"),
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("enabled", "Enabled"),
        ),
        rows=tuple(rows[:160]),
        total=len(rows),
        empty_state="No access usage records.",
    )


def _setup_flows_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in _setup_flow_records(targets):
        target = record["target"]
        check = record["check"]
        flow = _as_dict(check.get("setup_flow"))
        rows.append(
            OperationsTableRowModel(
                id=f"{_text(target.get('resource_id'), '')}:{_text(check.get('requirement'), '')}",
                cells={
                    "asset": _target_label(target),
                    "flow": _text(flow.get("kind")),
                    "title": _text(flow.get("title")),
                    "requirement": _text(check.get("requirement")),
                    "action": _text(flow.get("action_label") or "Setup"),
                    "path": _text(flow.get("path")),
                },
                status=_text(check.get("status"), ""),
                tone=_tone_for_status(check.get("status")),
            )
        )
    return OperationsTableSectionModel(
        id="setup_flows",
        title="Setup Flows",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("flow", "Flow Type"),
            OperationsTableColumnModel("title", "Title"),
            OperationsTableColumnModel("requirement", "Requirement"),
            OperationsTableColumnModel("action", "Action"),
            OperationsTableColumnModel("path", "Path"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No setup flows.",
    )


def _expiring_soon_table(
    targets: tuple[dict[str, Any], ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for record in _setup_flow_records(targets):
        flow = _as_dict(record["check"].get("setup_flow"))
        expires_at = _text(flow.get("expires_at"), "")
        if not expires_at:
            continue
        target = record["target"]
        rows.append(
            OperationsTableRowModel(
                id=f"{_text(target.get('resource_id'), '')}:{expires_at}",
                cells={
                    "asset": _target_label(target),
                    "expires_at": expires_at,
                    "action": "Setup",
                },
                status=_target_worst_status(target),
                tone="warning",
            )
        )
    return OperationsTableSectionModel(
        id="expiring_soon",
        title="Expiring Soon",
        columns=(
            OperationsTableColumnModel("asset", "Asset"),
            OperationsTableColumnModel("expires_at", "Expires At"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No expiring access flows.",
    )


def _access_events_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "level": event.level,
                "event": _short_event_name(event.event_name),
                "entity": _text(event.entity_id),
                "status": _status_label(event.status),
                "details": _event_details(event.payload),
                "trace": _text(event.trace_id),
                "trace_route": f"/ui/trace/{event.trace_id}" if event.trace_id else "-",
            },
            status=event.status,
            tone=_event_tone(event),
        )
        for event in events[:100]
    ]
    return OperationsTableSectionModel(
        id="recent_access_events",
        title="Recent Access Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("level", "Level"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(events),
        empty_state="No access events.",
    )


def _fallback_problems_table(
    *,
    targets: tuple[dict[str, Any], ...],
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for target in targets:
        rows.append(
            OperationsTableRowModel(
                id=f"target:{_text(target.get('resource_id'), '')}",
                cells={
                    "entity": _target_label(target),
                    "reason": _target_reason(target),
                    "status": _status_label(_target_worst_status(target)),
                    "impact": _impact(target),
                    "trace": "-",
                },
                status=_target_worst_status(target),
                tone=_tone_for_status(_target_worst_status(target)),
            )
        )
    for event in events:
        if event.level != "error" and event.status not in {"failed", "error"}:
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"event:{event.cursor or event.id}",
                cells={
                    "entity": _text(event.entity_id),
                    "reason": _event_details(event.payload),
                    "status": _status_label(event.status),
                    "impact": "High" if event.level == "error" else "Medium",
                    "trace": _text(event.trace_id),
                    "trace_route": f"/ui/trace/{event.trace_id}" if event.trace_id else "-",
                },
                status=event.status,
                tone=_event_tone(event),
            )
        )
    return OperationsTableSectionModel(
        id="fallback_problems",
        title="Fallback / Resolver Problems",
        columns=(
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("impact", "Impact"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows[:120]),
        total=len(rows),
        empty_state="No fallback or resolver problems.",
    )


def _credential_health(
    targets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(_target_worst_status(target) for target in targets)
    segments = tuple(
        OperationsChartSegmentModel(
            key,
            _status_label(key),
            counts[key],
            _tone_for_status(key),
        )
        for key in ("ready", "setup_needed", "unsupported", "waiting_user", "expired")
        if counts[key]
    )
    return OperationsChartSectionModel("credential_health", "Credential Health", "donut", len(targets), segments)


def _credentials_by_kind(
    targets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    counts = Counter(_text(_metadata(target).get("asset_kind"), "unknown") for target in targets)
    segments = tuple(
        OperationsChartSegmentModel(kind, _kind_label(kind), count, _kind_tone(kind))
        for kind, count in sorted(counts.items())
    )
    return OperationsChartSectionModel("credentials_by_kind", "Credentials by Kind", "donut", len(targets), segments)


def _auth_success_rate(
    targets: tuple[dict[str, Any], ...],
) -> OperationsChartSectionModel:
    ready = sum(1 for target in targets if _bool(target.get("ready")))
    blocked = len(targets) - ready
    return OperationsChartSectionModel(
        "auth_success_rate",
        "Access Readiness Share",
        "donut",
        len(targets),
        (
            OperationsChartSegmentModel("ready", "Ready", ready, "success"),
            OperationsChartSegmentModel("blocked", "Blocked", blocked, "warning" if blocked else "success"),
        ),
    )


def _target_details(
    targets: tuple[dict[str, Any], ...],
    *,
    observed_events: tuple[OperationsObservedEvent, ...],
) -> tuple[AccessTargetDetailModel, ...]:
    details: list[AccessTargetDetailModel] = []
    for target in targets[:80]:
        target_id = _text(target.get("resource_id"), "")
        status = _target_worst_status(target)
        details.append(
            AccessTargetDetailModel(
                target_id=target_id,
                title=_target_label(target),
                status=_status_label(status),
                tone=_tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Asset", _target_label(target)),
                    OperationsKeyValueItemModel("Kind", _kind_label(_text(_metadata(target).get("asset_kind")))),
                    OperationsKeyValueItemModel("Status", _status_label(status), _tone_for_status(status)),
                    OperationsKeyValueItemModel("Ready", "Yes" if _bool(target.get("ready")) else "No", "success" if _bool(target.get("ready")) else "warning"),
                    OperationsKeyValueItemModel("Setup Available", "Yes" if _bool(target.get("setup_available")) else "No"),
                    OperationsKeyValueItemModel("Usage Count", _text(_metadata(target).get("usage_count"))),
                    OperationsKeyValueItemModel("Requirements", _requirements_text(target)),
                    OperationsKeyValueItemModel("Reason", _target_reason(target)),
                ),
                checks=_checks_table(target),
                usages=_target_usages_table(target),
                setup=_target_setup_table(target),
                events=_access_events_table(_events_for_target(observed_events, target)),
                raw_payload={
                    "target": dict(target),
                    "events": [
                        event.to_payload()
                        for event in _events_for_target(observed_events, target)
                    ],
                },
            )
        )
    return tuple(details)


def _target_row(target: dict[str, Any]) -> OperationsTableRowModel:
    status = _target_worst_status(target)
    return OperationsTableRowModel(
        id=_text(target.get("resource_id"), ""),
        cells={
            "asset": _target_label(target),
            "kind": _kind_label(_text(_metadata(target).get("asset_kind"))),
            "status": _status_label(status),
            "readiness": "Ready" if _bool(target.get("ready")) else "Blocked",
            "requirements": _requirements_text(target),
            "required_by": _required_by(target),
            "usage": _text(_metadata(target).get("usage_count")),
            "setup": "Available" if _bool(target.get("setup_available")) else "-",
            "impact": _impact(target),
            "reason": _target_reason(target),
            "action": "Setup" if _bool(target.get("setup_available")) else "Open",
        },
        status=_status_label(status),
        tone=_tone_for_status(status),
    )


def _checks_table(target: dict[str, Any]) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for index, check in enumerate(_checks(target)):
        status = _text(check.get("status"), "unknown")
        rows.append(
            OperationsTableRowModel(
                id=f"{_text(target.get('resource_id'), '')}:check:{index}",
                cells={
                    "requirement": _text(check.get("requirement")),
                    "target_type": _text(check.get("target_type")),
                    "kind": _text(check.get("kind")),
                    "status": _status_label(status),
                    "setup": "Available" if _bool(check.get("setup_available")) else "-",
                    "reason": _text(check.get("reason")),
                },
                status=_status_label(status),
                tone=_tone_for_status(status),
            )
        )
    return OperationsTableSectionModel(
        id="checks",
        title="Checks",
        columns=(
            OperationsTableColumnModel("requirement", "Requirement"),
            OperationsTableColumnModel("target_type", "Target Type"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("setup", "Setup"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No checks.",
    )


def _target_usages_table(target: dict[str, Any]) -> OperationsTableSectionModel:
    usages = _as_list(_metadata(target).get("usages"))
    rows = [
        OperationsTableRowModel(
            id=f"{_text(target.get('resource_id'), '')}:usage:{index}",
            cells={
                "consumer": _text(_as_dict(usage).get("display_name") or _as_dict(usage).get("usage_id")),
                "usage_type": _text(_as_dict(usage).get("usage_type")),
                "usage_id": _text(_as_dict(usage).get("usage_id")),
                "enabled": "Yes" if _bool(_as_dict(usage).get("enabled")) else "No",
            },
            status="Enabled" if _bool(_as_dict(usage).get("enabled")) else "Disabled",
            tone="success" if _bool(_as_dict(usage).get("enabled")) else "neutral",
        )
        for index, usage in enumerate(usages)
    ]
    return OperationsTableSectionModel(
        id="usages",
        title="Usages",
        columns=(
            OperationsTableColumnModel("consumer", "Consumer"),
            OperationsTableColumnModel("usage_type", "Usage Type"),
            OperationsTableColumnModel("usage_id", "Usage ID"),
            OperationsTableColumnModel("enabled", "Enabled"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No usages.",
    )


def _target_setup_table(target: dict[str, Any]) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for index, record in enumerate(
        item
        for item in _setup_flow_records((target,))
        if _text(item["target"].get("resource_id"), "") == _text(target.get("resource_id"), "")
    ):
        check = record["check"]
        flow = _as_dict(check.get("setup_flow"))
        rows.append(
            OperationsTableRowModel(
                id=f"{_text(target.get('resource_id'), '')}:setup:{index}",
                cells={
                    "flow": _text(flow.get("kind")),
                    "title": _text(flow.get("title")),
                    "action": _text(flow.get("action_label") or "Setup"),
                    "path": _text(flow.get("path")),
                    "description": _short(flow.get("description"), 120),
                },
                status=_text(check.get("status"), ""),
                tone=_tone_for_status(check.get("status")),
            )
        )
    return OperationsTableSectionModel(
        id="setup",
        title="Setup",
        columns=(
            OperationsTableColumnModel("flow", "Flow Type"),
            OperationsTableColumnModel("title", "Title"),
            OperationsTableColumnModel("action", "Action"),
            OperationsTableColumnModel("path", "Path"),
            OperationsTableColumnModel("description", "Description"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No setup flow.",
    )


def _filter_targets(
    targets: tuple[dict[str, Any], ...],
    query: AccessOperationsQuery,
) -> tuple[dict[str, Any], ...]:
    needle = query.search.lower()
    filtered: list[dict[str, Any]] = []
    for target in targets:
        status = _target_worst_status(target)
        metadata = _metadata(target)
        if query.status != "all":
            if query.status == "blocked" and _bool(target.get("ready")):
                continue
            if query.status == "ready" and not _bool(target.get("ready")):
                continue
            if query.status not in {"blocked", "ready"} and _normalized_filter(status) != query.status:
                continue
        if query.kind != "all" and _normalized_filter(metadata.get("asset_kind")) != query.kind:
            continue
        usage_types = {_normalized_filter(item) for item in _string_values(metadata.get("usage_types"))}
        if query.usage_type != "all" and query.usage_type not in usage_types:
            continue
        if needle and needle not in _search_blob(target):
            continue
        filtered.append(target)
    filtered.sort(
        key=lambda item: (
            _bool(item.get("ready")),
            _target_label(item).lower(),
            _text(item.get("resource_id"), ""),
        )
    )
    return tuple(filtered)


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def _target_label(target: dict[str, Any]) -> str:
    return _text(target.get("display_name") or target.get("resource_id"))


def _target_worst_status(target: dict[str, Any]) -> str:
    checks = _checks(target)
    if not checks:
        return "ready" if _bool(target.get("ready")) else "setup_needed"
    statuses = [_text(check.get("status"), "unknown") for check in checks]
    for candidate in ("expired", "unsupported", "setup_needed", "waiting_user"):
        if candidate in statuses:
            return candidate
    if all(status == "ready" for status in statuses):
        return "ready"
    return statuses[0] or "unknown"


def _checks(target: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for requirement_set in _as_list(target.get("requirement_sets")):
        for check in _as_list(_as_dict(requirement_set).get("checks")):
            result.append(_as_dict(check))
    return tuple(result)


def _metadata(target: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(target.get("metadata"))


def _requirements_text(target: dict[str, Any]) -> str:
    metadata = _metadata(target)
    values = _string_values(metadata.get("declared_requirements")) or _string_values(metadata.get("requirements"))
    return ", ".join(values[:5]) if values else "-"


def _required_by(target: dict[str, Any]) -> str:
    metadata = _metadata(target)
    parts: list[str] = []
    for key, label in (
        ("tool_ids", "tool"),
        ("llm_profile_ids", "llm"),
        ("channel_profiles", "channel"),
    ):
        values = _string_values(metadata.get(key))
        if values:
            parts.append(f"{label}: {', '.join(values[:3])}")
    return " / ".join(parts) if parts else "-"


def _target_reason(target: dict[str, Any]) -> str:
    for check in _checks(target):
        if _bool(check.get("ready")):
            continue
        reason = _text(check.get("reason"), "")
        if reason:
            return _short(reason, 140)
    return "Ready" if _bool(target.get("ready")) else "-"


def _impact(target: dict[str, Any]) -> str:
    usage_count = _int(_metadata(target).get("usage_count"), 0)
    if not _bool(target.get("ready")) and usage_count >= 2:
        return "High"
    if not _bool(target.get("ready")):
        return "Medium"
    return "Low"


def _usage_records(targets: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for target in targets:
        for usage in _as_list(_metadata(target).get("usages")):
            records.append({"target": target, "usage": _as_dict(usage)})
    return tuple(records)


def _setup_flow_records(targets: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for target in targets:
        for check in _checks(target):
            flow = check.get("setup_flow")
            if isinstance(flow, dict):
                records.append({"target": target, "check": check})
    return tuple(records)


def _events_for_target(
    events: tuple[OperationsObservedEvent, ...],
    target: dict[str, Any],
) -> tuple[OperationsObservedEvent, ...]:
    resource_id = _text(target.get("resource_id"), "")
    requirements = set(_string_values(_metadata(target).get("requirements")))
    return tuple(
        event
        for event in events
        if event.entity_id == resource_id
        or _text(event.payload.get("resource_id"), "") == resource_id
        or _text(event.payload.get("requirement"), "") in requirements
    )


def _event_details(payload: dict[str, Any]) -> str:
    for key in ("reason", "message", "summary", "error_message", "requirement", "status"):
        value = payload.get(key)
        if value is not None and _text(value, ""):
            return _short(value, 120)
    return "-"


def _short_event_name(event_name: str) -> str:
    return event_name.removeprefix("access.")


def _event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning":
        return "warning"
    return "success" if event.status in {"ready", "success", "observed"} else "neutral"


def _tone_for_status(status: Any) -> str:
    text = _normalized_filter(status)
    if text in {"expired", "failed", "error"}:
        return "danger"
    if text in {"setup_needed", "waiting_user", "unsupported", "blocked"}:
        return "warning"
    if text in {"ready", "healthy", "available", "enabled"}:
        return "success"
    return "neutral"


def _status_label(status: Any) -> str:
    text = _text(status, "unknown").replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in text.split()) or "-"


def _kind_label(kind: str) -> str:
    mapping = {
        "env": "Env",
        "file": "File Credential",
        "codex_auth_json": "Codex Auth JSON",
        "inline_credential": "Inline Credential",
        "credential_set": "Credential Set",
        "authorization_requirement": "Authorization Requirement",
        "unknown": "Unknown",
    }
    return mapping.get(kind, _status_label(kind))


def _kind_tone(kind: str) -> str:
    if kind in {"env", "file", "codex_auth_json"}:
        return "info"
    if kind == "inline_credential":
        return "warning"
    return "neutral"


def _health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def _health_delta(health: str) -> str:
    if health == "error":
        return "Access service is not connected"
    if health == "warning":
        return "Access setup is required"
    return "Access inventory is ready"


def _health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"


def _normalized_filter(value: Any) -> str:
    text = _text(value, "all").strip().lower().replace(" ", "_").replace("-", "_")
    return text or "all"


def _search_blob(target: dict[str, Any]) -> str:
    metadata = _metadata(target)
    values = [
        _target_label(target),
        _text(target.get("resource_id")),
        _requirements_text(target),
        _required_by(target),
        _target_reason(target),
        _text(metadata.get("asset_kind")),
        _text(metadata.get("usage_types")),
    ]
    return " ".join(values).lower()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [_text(item, "") for item in value if _text(item, "")]
    return []


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(item, "") for item in value if _text(item, ""))
    if isinstance(value, dict):
        return ", ".join(f"{key}={_text(item, '')}" for key, item in sorted(value.items()))
    text = str(value).strip()
    return text if text else default


def _short(value: Any, limit: int = 80) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


class _NullService:
    def list_profiles(self) -> tuple[Any, ...]:
        return ()

    def list_enabled_tools(self) -> tuple[Any, ...]:
        return ()

    def list_tools(self) -> tuple[Any, ...]:
        return ()


class _NullChannelRuntime:
    def profile_access_requirements(self, _profile: Any) -> tuple[str, ...]:
        return ()
