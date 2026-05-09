from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.channels.domain import channel_dead_letter_topic
from crxzipple.modules.daemon import DaemonNotFoundError, DaemonValidationError
from crxzipple.modules.daemon.interfaces.presenters import (
    instance_payload,
    lease_payload,
    service_set_payload,
    spec_payload,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    OperationsTabModel,
    RuntimeActionModel,
    OperationsModuleRoleModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import format_datetime_utc

_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class OperationsModuleQuerySet:
    access_service: Any
    access_governance_repository: Any | None
    agent_service: Any
    channel_profile_service: Any
    channel_runtime_manager: Any
    daemon_manager: Any
    daemon_service: Any
    event_contract_registry: Any
    event_definition_registry: Any
    events_service: Any
    operations_observation_store: Any | None
    file_memory_service: Any
    lark_channel_runtime_service: Any
    llm_service: Any
    memory_context_resolver: Any
    skill_manager: Any
    tool_service: Any
    web_channel_runtime_service: Any
    webhook_channel_runtime_service: Any


@dataclass(frozen=True, slots=True)
class OperationsModulePage:
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
    sections: tuple[OperationsTableSectionModel, ...]


@dataclass(frozen=True, slots=True)
class OperationsModuleReadModelProvider:
    module_query: OperationsModuleQuerySet

    def page(self, module: str) -> OperationsModulePage | None:
        return operations_module_page(module, self.module_query)

    def overview(self, module: str) -> OperationsModuleOverview | None:
        return operations_module_overview(module, self.module_query)


def operations_module_page(
    module: str,
    container: OperationsModuleQuerySet,
) -> OperationsModulePage | None:
    overview = operations_module_overview(module, container)
    if overview is None:
        return None
    sections = _sections_for_overview(overview)
    return OperationsModulePage(
        module=overview.module,
        title=overview.title,
        subtitle=overview.subtitle,
        health=overview.health,
        updated_at=overview.updated_at,
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label=f"{overview.title} operator",
            can_operate=True,
            scope=overview.module,
        ),
        metrics=overview.metrics,
        tabs=tuple(
            OperationsTabModel(
                id=section.id,
                label=section.title,
                count=section.total,
                tone="neutral",
            )
            for section in sections
        ),
        active_tab=sections[0].id if sections else "overview",
        actions=overview.actions,
        sections=sections,
    )


def operations_module_overview(
    module: str,
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview | None:
    if module == "access":
        return access_operations_overview(container)
    if module == "channels":
        return channels_operations_overview(container)
    if module == "memory":
        return memory_operations_overview(container)
    if module == "skills":
        return skills_operations_overview(container)
    if module == "events":
        return events_operations_overview(container)
    if module == "daemon":
        return daemon_operations_overview(container)
    return None


def access_operations_overview(
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview:
    now = _now()
    inventory = collect_access_inventory(container, include_ready=True)
    targets = _as_list(inventory.get("targets"))
    counts = _as_dict(inventory.get("counts"))
    total = _int(counts.get("total"), len(targets))
    ready = _int(counts.get("ready"))
    blocked = _int(counts.get("blocked"), total - ready)
    health = "warning" if blocked else "healthy"
    blocked_targets = [target for target in targets if not bool(target.get("ready"))]

    return _overview(
        module="access",
        title="Access",
        subtitle="聚合凭证、授权要求与访问可用性，前端只消费 UI readiness 读面。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=(
            _health_metric(health, "Loaded from access inventory"),
            MetricCardModel(
                "access_assets", "Access Assets", str(total), f"{ready} ready", "info"
            ),
            MetricCardModel(
                "missing_access",
                "Missing Access",
                str(blocked),
                "blocked or missing targets",
                "warning" if blocked else "success",
            ),
            MetricCardModel("ready", "Ready", str(ready), "ready targets", "success"),
            MetricCardModel(
                "setup_available",
                "Setup Available",
                str(_setup_available_count(targets)),
                "targets with setup flow",
                "info",
            ),
            MetricCardModel(
                "failed_auth",
                "Failed Auth",
                "N/A",
                "auth event metric not exposed",
                "neutral",
            ),
        ),
        queue=tuple(_access_target_row(target) for target in blocked_targets[:20]),
        lane_locks=tuple(_access_target_row(target) for target in targets[:40]),
        executor=tuple(_access_target_row(target) for target in targets[:40]),
        actions=(
            RuntimeActionModel(id="open_access", label="Open Access", owner="access"),
            RuntimeActionModel(
                id="setup_access",
                label="Setup Access",
                owner="access",
                risk="controlled",
            ),
            RuntimeActionModel(id="open_trace", label="Open Trace", owner="access"),
        ),
    )


def memory_operations_overview(
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview:
    now = _now()
    profiles = container.agent_service.list_profiles()
    selected_profile = _select_memory_profile(profiles)
    recent_files: list[Any] = []
    long_term = None
    context = None
    if selected_profile is not None:
        context = container.memory_context_resolver.resolve(selected_profile.id)
    if context is not None:
        long_term = container.file_memory_service.get(
            context=context, path="MEMORY.md"
        ) or container.file_memory_service.get(context=context, path="memory.md")
        recent_files = container.file_memory_service.list_files(
            context=context, limit=12
        )

    health = "healthy" if context is not None else "warning"
    store_count = len(recent_files) + (1 if long_term is not None else 0)
    agent_id = getattr(selected_profile, "id", None) or "-"
    return _overview(
        module="memory",
        title="Memory",
        subtitle="聚合文件存储记忆空间、长期记忆与最近记忆文件。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=(
            _health_metric(health, "Loaded from memory read model"),
            MetricCardModel(
                "memory_stores",
                "Memory Stores",
                str(store_count),
                f"agent {agent_id}",
                "info",
            ),
            MetricCardModel(
                "agents",
                "Agents",
                str(len(profiles)),
                "registered agent homes",
                "neutral",
            ),
            MetricCardModel(
                "source_documents",
                "Source Documents",
                str(len(recent_files)),
                "recent memory files",
                "info",
            ),
            MetricCardModel(
                "index_health",
                "Index Health",
                "N/A",
                "index metric not exposed",
                "neutral",
            ),
            MetricCardModel(
                "errors",
                "0" if context is not None else "1",
                "memory context availability",
                "success" if context is not None else "warning",
            ),
        ),
        queue=tuple(
            [_memory_long_term_row(agent_id, long_term)]
            if long_term is not None
            else [],
        )
        + tuple(_memory_file_row(agent_id, item) for item in recent_files),
        lane_locks=tuple(_memory_agent_row(profile) for profile in profiles[:20]),
        executor=tuple(_memory_file_row(agent_id, item) for item in recent_files),
        actions=(
            RuntimeActionModel(id="open_memory", label="Open Memory", owner="memory"),
            RuntimeActionModel(
                id="refresh_memory", label="Refresh Memory", owner="memory"
            ),
        ),
    )


def skills_operations_overview(
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview:
    now = _now()
    skills = container.skill_manager.list_available(
        workspace_dir=None, surface="interactive"
    )
    source_counts = Counter(skill.source for skill in skills)
    requirement_rows = _skill_requirement_rows(skills)
    health = "healthy"
    return _overview(
        module="skills",
        title="Skills",
        subtitle="聚合技能包目录、来源、声明能力与访问要求。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=(
            _health_metric(health, "Loaded from skills registry"),
            MetricCardModel(
                "installed_skills",
                "Installed Skills",
                str(len(skills)),
                f"{len(source_counts)} sources",
                "info",
            ),
            MetricCardModel(
                "available_skills",
                "Available Skills",
                str(len(skills)),
                "interactive surface",
                "neutral",
            ),
            MetricCardModel(
                "declared_requirements",
                "Declared Requirements",
                str(len(requirement_rows)),
                "tools/auth/credentials",
                "info" if requirement_rows else "success",
            ),
            MetricCardModel(
                "resolution_success_rate",
                "Resolution Success Rate",
                "N/A",
                "resolution metric not exposed",
                "neutral",
            ),
            MetricCardModel(
                "resolution_failures",
                "Resolution Failures",
                "N/A",
                "resolution metric not exposed",
                "neutral",
            ),
        ),
        queue=tuple(_skill_row(skill) for skill in skills),
        lane_locks=tuple(
            {
                "source": _s(source),
                "skills": str(count),
                "status": "Installed",
            }
            for source, count in sorted(source_counts.items())
        ),
        executor=tuple(requirement_rows),
        actions=(
            RuntimeActionModel(id="open_skill", label="Open Skill", owner="skills"),
            RuntimeActionModel(
                id="validate_skill",
                label="Validate Skill",
                owner="skills",
                risk="controlled",
            ),
        ),
    )


def channels_operations_overview(
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview:
    now = _now()
    runtimes = container.channel_runtime_manager.list_runtimes(channel_type=None)
    runtime_rows = [_channel_runtime_row(container, runtime) for runtime in runtimes]
    stale_count = sum(1 for row in runtime_rows if row["status"] == "Stale")
    online_count = sum(1 for row in runtime_rows if row["status"] == "online")
    dead_letters = _channel_dead_letter_rows(container, runtime_rows)
    health = "error" if dead_letters else "warning" if stale_count else "healthy"
    type_counts = Counter(row["channel_type"] for row in runtime_rows)

    return _overview(
        module="channels",
        title="Channels",
        subtitle="聚合通道 runtime、连接绑定、账号绑定与死信。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=(
            _health_metric(health, "Loaded from channel runtime registry"),
            MetricCardModel(
                "runtimes",
                "Runtimes",
                str(len(runtime_rows)),
                f"{online_count} online",
                "info",
            ),
            MetricCardModel(
                "connections",
                "Connections",
                str(sum(_int(row.get("connection_count")) for row in runtime_rows)),
                "active bindings",
                "info",
            ),
            MetricCardModel(
                "accounts",
                "Accounts",
                str(sum(_int(row.get("account_count")) for row in runtime_rows)),
                "account bindings",
                "neutral",
            ),
            MetricCardModel(
                "stale",
                "Stale",
                str(stale_count),
                "heartbeat older than 5 minutes",
                "warning" if stale_count else "success",
            ),
            MetricCardModel(
                "dead_letters",
                "Dead Letters",
                str(len(dead_letters)),
                "across channel types",
                "danger" if dead_letters else "success",
            ),
        ),
        queue=tuple(runtime_rows),
        lane_locks=tuple(dead_letters),
        executor=tuple(
            {
                "channel_type": channel_type,
                "runtime_count": str(count),
                "status": "online" if count else "unknown",
            }
            for channel_type, count in sorted(type_counts.items())
        ),
        actions=(
            RuntimeActionModel(
                id="open_channel_runtime", label="Open Runtime", owner="channels"
            ),
            RuntimeActionModel(
                id="inspect_dead_letter",
                label="Inspect Dead Letter",
                owner="channels",
                risk="controlled",
            ),
        ),
    )


def events_operations_overview(
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview:
    now = _now()
    contract_payload = container.event_contract_registry.to_payload()
    definition_payload = container.event_definition_registry.to_payload()
    topics = _as_list(contract_payload.get("topics"))
    definitions = _as_list(definition_payload.get("definitions"))
    observer_definitions = _as_list(definition_payload.get("observers"))
    surfaces = _as_list(definition_payload.get("surfaces"))
    subscription_items = _event_subscription_rows(container)
    operations_snapshot = (
        container.operations_observation_store.snapshot()
        if container.operations_observation_store is not None
        else None
    )
    observed_module_count = (
        len(getattr(operations_snapshot, "modules", ()))
        if operations_snapshot is not None
        else 0
    )
    lagging = sum(
        1 for item in subscription_items if item["status"] in {"Lagging", "Stuck"}
    )
    stuck = sum(1 for item in subscription_items if item["status"] == "Stuck")
    health = "error" if stuck else "warning" if lagging else "healthy"
    owner_counts = Counter(_s(item.get("owner")) for item in topics + definitions)

    return _overview(
        module="events",
        title="Events",
        subtitle="聚合事件合同、订阅游标、Topic 与观察者健康。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=(
            MetricCardModel(
                "topics",
                "Topics",
                str(_int(contract_payload.get("topic_count"), len(topics))),
                "contract registry",
                "info",
            ),
            MetricCardModel(
                "definitions",
                "Definitions",
                str(_int(definition_payload.get("definition_count"), len(definitions))),
                "event definitions",
                "success",
            ),
            MetricCardModel(
                "subscriptions",
                "Subscriptions",
                str(len(subscription_items)),
                "runtime cursors",
                "info" if subscription_items else "neutral",
            ),
            MetricCardModel(
                "surfaces",
                "Surfaces",
                str(len(surfaces)),
                "registered UI/event surfaces",
                "neutral",
            ),
            MetricCardModel(
                "lagging",
                "Lagging",
                str(lagging),
                "subscriptions behind head",
                "warning" if lagging else "success",
            ),
            MetricCardModel(
                "stuck",
                "Stuck",
                str(stuck),
                "past stuck threshold",
                "danger" if stuck else "success",
            ),
            MetricCardModel(
                "observers",
                "Observers",
                str(len(observer_definitions)),
                "observer definitions",
                "info",
            ),
            MetricCardModel(
                "observed_modules",
                "Observed Modules",
                str(observed_module_count),
                "operations observer read model",
                "info" if observed_module_count else "neutral",
            ),
        ),
        queue=tuple(subscription_items[:80]),
        lane_locks=tuple(
            {
                "owner": owner,
                "events": str(count),
                "percent": _percent(count, sum(owner_counts.values())),
                "trend": "registry",
            }
            for owner, count in sorted(owner_counts.items())
        ),
        executor=tuple(
            _event_observer_definition_row(definition)
            for definition in observer_definitions
        ),
        actions=(
            RuntimeActionModel(
                id="open_event_stream", label="Open Event Stream", owner="events"
            ),
            RuntimeActionModel(
                id="inspect_subscription", label="Inspect Subscription", owner="events"
            ),
        ),
    )


def daemon_operations_overview(
    container: OperationsModuleQuerySet,
) -> OperationsModuleOverview:
    now = _now()
    services = [
        spec_payload(spec) for spec in container.daemon_service.list_service_specs()
    ]
    service_sets = [
        service_set_payload(item)
        for item in container.daemon_service.list_service_sets()
    ]
    leases = [lease_payload(item) for item in container.daemon_service.list_leases()]
    try:
        instances = [
            instance_payload(item)
            for item in container.daemon_manager.list_instances(refresh=False)
        ]
    except (DaemonValidationError, DaemonNotFoundError):
        instances = []

    status_counts = Counter(_s(item.get("status")) for item in instances)
    ready = status_counts["ready"]
    stopped = status_counts["stopped"]
    other = max(0, len(instances) - ready - stopped)
    health = "warning" if stopped or other else "healthy"
    service_by_key = {_s(service.get("key")): service for service in services}

    return _overview(
        module="daemon",
        title="Daemons",
        subtitle="聚合守护进程服务集、进程实例、租约与服务组健康。",
        health=health,
        updated_at=format_datetime_utc(now),
        metrics=(
            _health_metric(health, "Loaded from daemon registry"),
            MetricCardModel(
                "service_sets",
                "Service Sets",
                str(len(service_sets)),
                "configured sets",
                "info",
            ),
            MetricCardModel(
                "processes",
                "Processes",
                str(len(instances)),
                f"ready {ready} / stopped {stopped}",
                "info",
            ),
            MetricCardModel(
                "healthy", "Healthy", str(ready), "ready instances", "success"
            ),
            MetricCardModel(
                "unhealthy",
                "Unhealthy",
                str(other),
                "non-ready non-stopped instances",
                "warning" if other else "success",
            ),
            MetricCardModel(
                "stopped",
                "Stopped",
                str(stopped),
                "historical stopped instances",
                "warning" if stopped else "success",
            ),
            MetricCardModel(
                "leases",
                "Leases",
                str(len(leases)),
                "active daemon leases",
                "info" if leases else "neutral",
            ),
        ),
        queue=tuple(
            _daemon_service_set_row(item, services, instances) for item in service_sets
        ),
        lane_locks=tuple(_daemon_service_row(item) for item in services),
        executor=tuple(
            _daemon_instance_row(item, service_by_key.get(_s(item.get("service_key"))))
            for item in instances[:80]
        ),
        actions=(
            RuntimeActionModel(
                id="ensure_service",
                label="Ensure Service",
                owner="daemon",
                risk="controlled",
            ),
            RuntimeActionModel(
                id="stop_service",
                label="Stop Service",
                owner="daemon",
                risk="dangerous",
                requires_confirmation=True,
            ),
            RuntimeActionModel(
                id="restart_service",
                label="Restart Service",
                owner="daemon",
                risk="controlled",
                requires_confirmation=True,
            ),
        ),
    )


def _sections_for_overview(
    overview: OperationsModuleOverview,
) -> tuple[OperationsTableSectionModel, ...]:
    section_specs = {
        "access": (
            ("missing_access", "Missing Access", overview.queue),
            ("access_targets", "Access Targets", overview.executor),
        ),
        "channels": (
            ("runtimes", "Channel Runtimes", overview.queue),
            ("dead_letters", "Dead Letters", overview.lane_locks),
            ("channel_types", "Channel Types", overview.executor),
        ),
        "memory": (
            ("memory_files", "Memory Files", overview.queue),
            ("agents", "Agents", overview.lane_locks),
        ),
        "skills": (
            ("installed_skills", "Installed Skills", overview.queue),
            ("sources", "Skill Sources", overview.lane_locks),
            ("requirements", "Declared Requirements", overview.executor),
        ),
        "events": (
            ("subscriptions", "Subscriptions", overview.queue),
            ("owners", "Owners", overview.lane_locks),
            ("observer_coverage", "Observer Coverage", overview.executor),
        ),
        "daemon": (
            ("service_sets", "Service Sets", overview.queue),
            ("services", "Services", overview.lane_locks),
            ("instances", "Instances", overview.executor),
        ),
    }.get(
        overview.module,
        (
            ("queue", "Queue", overview.queue),
            ("lane_locks", "Lane Locks", overview.lane_locks),
            ("executor", "Executor", overview.executor),
        ),
    )
    return tuple(
        _table_section(
            section_id=section_id,
            title=title,
            rows=rows,
            route=f"/operations/{overview.module}?tab={section_id}",
        )
        for section_id, title, rows in section_specs
    )


def _table_section(
    *,
    section_id: str,
    title: str,
    rows: tuple[dict[str, str], ...],
    route: str,
) -> OperationsTableSectionModel:
    keys = _table_keys(rows)
    return OperationsTableSectionModel(
        id=section_id,
        title=title,
        columns=tuple(
            OperationsTableColumnModel(key=key, label=_column_label(key))
            for key in keys
        ),
        rows=tuple(
            OperationsTableRowModel(
                id=_row_id(section_id, index, row),
                cells={key: _s(row.get(key)) for key in keys},
                status=row.get("status"),
                tone=_row_tone(row),
            )
            for index, row in enumerate(rows)
        ),
        total=len(rows),
        view_all_route=route,
        empty_state=f"No {title.lower()} records.",
    )


def _table_keys(rows: tuple[dict[str, str], ...]) -> tuple[str, ...]:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    return tuple(keys)


def _column_label(key: str) -> str:
    return " ".join(part.capitalize() for part in key.split("_") if part) or key


def _row_id(section_id: str, index: int, row: dict[str, str]) -> str:
    for key in (
        "id",
        "key",
        "runtime_id",
        "subscription_id",
        "service_key",
        "path",
        "name",
    ):
        value = row.get(key)
        if value:
            return _short(value, 80)
    return f"{section_id}:{index}"


def _row_tone(row: dict[str, str]) -> str:
    status = _s(row.get("status")).lower()
    if any(
        token in status
        for token in (
            "error",
            "failed",
            "stuck",
            "dead",
            "missing",
            "blocked",
            "stopped",
        )
    ):
        return "danger"
    if any(token in status for token in ("warning", "lagging", "stale", "degraded")):
        return "warning"
    if any(
        token in status
        for token in (
            "ready",
            "healthy",
            "online",
            "installed",
            "registered",
            "configured",
        )
    ):
        return "success"
    return "neutral"


def _overview(
    *,
    module: str,
    title: str,
    subtitle: str,
    health: str,
    updated_at: str,
    metrics: tuple[MetricCardModel, ...],
    queue: tuple[dict[str, str], ...],
    lane_locks: tuple[dict[str, str], ...],
    executor: tuple[dict[str, str], ...],
    actions: tuple[RuntimeActionModel, ...],
) -> OperationsModuleOverview:
    return OperationsModuleOverview(
        module=module,
        title=title,
        subtitle=subtitle,
        health=health,
        updated_at=updated_at,
        metrics=metrics,
        queue=queue,
        lane_locks=lane_locks,
        executor=executor,
        actions=actions,
    )


def _health_metric(health: str, delta: str) -> MetricCardModel:
    return MetricCardModel(
        id="health",
        label="Overall Health",
        value={"healthy": "Healthy", "warning": "Warning", "error": "Error"}.get(
            health, "Unknown"
        ),
        delta=delta,
        tone={"healthy": "success", "warning": "warning", "error": "danger"}.get(
            health, "neutral"
        ),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _s(value: Any, default: str = "-") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, (list, tuple, set)):
        items = [_s(item) for item in value]
        return ", ".join(item for item in items if item != "-") or default
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value] if isinstance(value, list) else []


def _percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((part / total) * 100, 1)}%"


def _short(value: Any, size: int = 28) -> str:
    text = _s(value)
    if len(text) <= size:
        return text
    return f"{text[: max(8, size - 8)]}...{text[-5:]}"


def _setup_available_count(targets: list[dict[str, Any]]) -> int:
    return sum(1 for target in targets if bool(target.get("setup_available")))


def _access_target_row(target: dict[str, Any]) -> dict[str, str]:
    metadata = _as_dict(target.get("metadata"))
    checks = [
        check
        for requirement_set in target.get("requirement_sets", [])
        if isinstance(requirement_set, dict)
        for check in requirement_set.get("checks", [])
        if isinstance(check, dict)
    ]
    first_missing = next(
        (check for check in checks if not bool(check.get("ready"))), None
    )
    status = (
        "Ready"
        if bool(target.get("ready"))
        else _s(first_missing.get("status") if first_missing else "Missing")
    )
    return {
        "id": _s(target.get("resource_id")),
        "key": _s(target.get("display_name") or target.get("resource_id")),
        "name": _s(target.get("display_name") or target.get("resource_id")),
        "asset": _s(target.get("display_name") or target.get("resource_id")),
        "kind": _s(metadata.get("asset_kind") or target.get("resource_type")),
        "status": status,
        "ready": _s(target.get("ready")),
        "required_by": _s(metadata.get("usage_types")),
        "affected": _s(metadata.get("usage_count")),
        "impact": "High" if not bool(target.get("ready")) else "Low",
        "last_failed_at": "-",
        "setup_available": _s(target.get("setup_available")),
        "actions": "Setup" if bool(target.get("setup_available")) else "Open",
    }


def _select_memory_profile(profiles: list[Any]) -> Any | None:
    for preferred_id in ("crxzipple", "assistant"):
        for profile in profiles:
            if getattr(profile, "id", None) == preferred_id:
                return profile
    return next(
        (profile for profile in profiles if getattr(profile, "enabled", True)),
        profiles[0] if profiles else None,
    )


def _memory_long_term_row(agent_id: str, long_term: Any) -> dict[str, str]:
    return {
        "path": _s(getattr(long_term, "path", "MEMORY.md")),
        "title": _s(getattr(long_term, "path", "MEMORY.md")),
        "kind": _s(getattr(long_term, "kind", "long_term")),
        "preview": _short(getattr(long_term, "text", ""), 120),
        "updated_at": "-",
        "agent_id": agent_id,
        "status": "Ready",
    }


def _memory_file_row(agent_id: str, item: Any) -> dict[str, str]:
    return {
        "path": _s(getattr(item, "path", None)),
        "title": _s(getattr(item, "title", None) or getattr(item, "path", None)),
        "kind": _s(getattr(item, "kind", None)),
        "preview": _short(getattr(item, "preview", ""), 120),
        "updated_at": _s(getattr(item, "updated_at", None)),
        "agent_id": agent_id,
        "status": "Ready",
    }


def _memory_agent_row(profile: Any) -> dict[str, str]:
    preferences = getattr(profile, "runtime_preferences", None)
    return {
        "agent_id": _s(getattr(profile, "id", None)),
        "name": _s(getattr(profile, "name", None)),
        "status": "Enabled" if bool(getattr(profile, "enabled", True)) else "Disabled",
        "home_dir": _short(getattr(preferences, "home_dir", None), 42),
    }


def _skill_row(skill: Any) -> dict[str, str]:
    requirements = getattr(skill, "requirements", None)
    requirement_payload = {
        "required_tools": list(getattr(requirements, "required_tools", ())),
        "optional_tools": list(getattr(requirements, "optional_tools", ())),
        "suggested_tools": list(getattr(requirements, "suggested_tools", ())),
        "compatibility_auth": list(getattr(requirements, "compatibility_auth", ())),
        "compatibility_secrets": list(
            getattr(requirements, "compatibility_secrets", ())
        ),
        "compatibility_credential_files": list(
            getattr(requirements, "compatibility_credential_files", ())
        ),
    }
    return {
        "name": _s(getattr(skill, "name", None)),
        "skill": _s(getattr(skill, "name", None)),
        "description": _s(getattr(skill, "description", None)),
        "version": _s(getattr(skill, "version", None), "1"),
        "tags": _s(getattr(skill, "tags", ())),
        "source": _s(getattr(skill, "source", None)),
        "root_path": _s(getattr(skill, "root_path", None)),
        "result": "Installed",
        "requirements": json.dumps(requirement_payload, ensure_ascii=False),
    }


def _skill_requirement_rows(skills: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for skill in skills:
        requirements = getattr(skill, "requirements", None)
        for field, capability_type in (
            ("required_tools", "Tool"),
            ("compatibility_auth", "Access"),
            ("compatibility_secrets", "Secret"),
            ("compatibility_credential_files", "Credential File"),
        ):
            for value in getattr(requirements, field, ()):
                rows.append(
                    {
                        "type": capability_type,
                        "capability": _s(value),
                        "required": _s(value),
                        "by": _s(getattr(skill, "name", None)),
                        "resolved": _s(value),
                        "status": "Declared",
                    }
                )
    return rows


def _channel_runtime_row(
    container: OperationsModuleQuerySet,
    runtime: Any,
) -> dict[str, str]:
    accounts = container.channel_runtime_manager.list_account_bindings(
        runtime_id=runtime.runtime_id
    )
    connections = container.channel_runtime_manager.list_connection_bindings(
        runtime_id=runtime.runtime_id
    )
    heartbeat = getattr(runtime, "last_heartbeat_at", None)
    status = runtime.status
    if (
        isinstance(heartbeat, datetime)
        and (_now() - heartbeat.astimezone(timezone.utc)).total_seconds() > 300
    ):
        status = "Stale"
    return {
        "runtime_id": runtime.runtime_id,
        "channel_type": runtime.channel_type,
        "service_key": _s(runtime.service_key),
        "status": status,
        "registered_at": runtime.registered_at.isoformat(),
        "last_heartbeat_at": runtime.last_heartbeat_at.isoformat(),
        "account_count": str(len(accounts)),
        "connection_count": str(len(connections)),
    }


def _channel_dead_letter_rows(
    container: OperationsModuleQuerySet,
    runtime_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    if container.events_service is None:
        return []
    rows: list[dict[str, str]] = []
    for channel_type in sorted(
        {row["channel_type"] for row in runtime_rows} | {"web", "lark", "webhook"}
    ):
        topic = channel_dead_letter_topic(channel_type)
        for record in container.events_service.read_event_topic(topic, limit=20):
            rows.append(
                {
                    "cursor": record.cursor,
                    "topic": record.envelope.topic,
                    "event_id": record.envelope.id,
                    "channel_type": channel_type,
                    "reason": _s(
                        record.envelope.payload.get("reason")
                        if isinstance(record.envelope.payload, dict)
                        else None
                    ),
                    "created_at": record.envelope.created_at.isoformat(),
                    "status": "Dead Letter",
                }
            )
    return rows


def _event_subscription_rows(
    container: OperationsModuleQuerySet,
) -> list[dict[str, str]]:
    if container.events_service is None:
        return []
    states = container.events_service.list_subscription_cursors()
    latest_cursors = {
        state.source_topic: container.events_service.snapshot_event_topic(
            state.source_topic
        )
        for state in states
    }
    rows: list[dict[str, str]] = []
    for state in states:
        latest_cursor = latest_cursors.get(state.source_topic)
        at_head = _compare_event_cursors(state.cursor, latest_cursor) >= 0
        seconds_since_update = max(
            0.0, (_now() - state.updated_at.astimezone(timezone.utc)).total_seconds()
        )
        stuck = (
            not at_head
        ) and seconds_since_update >= _STUCK_SUBSCRIPTION_AFTER_SECONDS
        rows.append(
            {
                "subscription_id": state.subscription_id,
                "source_topic": state.source_topic,
                "cursor": state.cursor,
                "latest_cursor": _s(latest_cursor),
                "updated_at": state.updated_at.isoformat(),
                "at_head": _s(at_head),
                "lagging": _s(not at_head),
                "stuck": _s(stuck),
                "seconds_since_update": str(round(seconds_since_update, 3)),
                "status": "Stuck" if stuck else "Healthy" if at_head else "Lagging",
            }
        )
    rows.sort(
        key=lambda item: (
            item["status"] != "Stuck",
            item["status"] != "Lagging",
            item["subscription_id"],
        )
    )
    return rows


def _event_observer_definition_row(definition: dict[str, Any]) -> dict[str, str]:
    return {
        "observer": _s(definition.get("observer_id")),
        "owner": _s(definition.get("owner")),
        "inputs": _s(definition.get("source_event_names")),
        "outputs": _s(definition.get("output_definition_ids")),
        "status": "Registered",
    }


def _daemon_service_set_row(
    service_set: dict[str, Any],
    services: list[dict[str, Any]],
    instances: list[dict[str, Any]],
) -> dict[str, str]:
    matched = _daemon_matching_services(service_set, services)
    matched_keys = {_s(service.get("key")) for service in matched}
    matched_instances = [
        item for item in instances if _s(item.get("service_key")) in matched_keys
    ]
    status_counts = Counter(_s(item.get("status")) for item in matched_instances)
    ready = status_counts["ready"]
    stopped = status_counts["stopped"]
    unhealthy = max(0, len(matched_instances) - ready - stopped)
    return {
        "key": _s(service_set.get("key")),
        "set": _s(service_set.get("display_name") or service_set.get("key")),
        "display_name": _s(service_set.get("display_name") or service_set.get("key")),
        "description": _s(service_set.get("description")),
        "service_keys": _s(service_set.get("service_keys")),
        "service_roles": _s(service_set.get("service_roles")),
        "service_groups": _s(service_set.get("service_groups")),
        "processes": str(len(matched_instances)),
        "healthy": str(ready),
        "unhealthy": str(unhealthy),
        "stopped": str(stopped),
        "status": "Warning" if unhealthy or stopped else "Healthy",
    }


def _daemon_matching_services(
    service_set: dict[str, Any], services: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    keys = set(_split_csv(_s(service_set.get("service_keys"))))
    roles = set(_split_csv(_s(service_set.get("service_roles"))))
    groups = set(_split_csv(_s(service_set.get("service_groups"))))
    return [
        service
        for service in services
        if _s(service.get("key")) in keys
        or _s(service.get("role")) in roles
        or _s(service.get("service_group")) in groups
    ]


def _daemon_service_row(service: dict[str, Any]) -> dict[str, str]:
    return {
        "key": _s(service.get("key")),
        "display_name": _s(service.get("display_name")),
        "service_group": _s(service.get("service_group")),
        "role": _s(service.get("role")),
        "status": "Configured",
        "restart_policy": _s(service.get("restart_policy")),
    }


def _daemon_instance_row(
    instance: dict[str, Any],
    service: dict[str, Any] | None,
) -> dict[str, str]:
    return {
        "id": _s(instance.get("id")),
        "service_key": _s(instance.get("service_key")),
        "process": _s(
            (service or {}).get("display_name") or instance.get("service_key")
        ),
        "set": _s((service or {}).get("service_group")),
        "loop": _s((service or {}).get("role")),
        "status": _s(instance.get("status")).title(),
        "worker_id": _s(instance.get("worker_id")),
        "pid": _s(instance.get("pid")),
        "endpoint": _s(instance.get("endpoint")),
        "last_healthcheck_at": _s(instance.get("last_healthcheck_at")),
        "started_at": _s(instance.get("started_at")),
        "env_fingerprint": _short(instance.get("env_fingerprint"), 18),
        "env_drift_detected": _s(instance.get("env_drift_detected")),
        "last_error": _short(instance.get("last_error"), 80),
    }


def _split_csv(value: str) -> list[str]:
    if value == "-":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _compare_event_cursors(left: str | None, right: str | None) -> int:
    left_cursor = _parse_event_cursor(left)
    right_cursor = _parse_event_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def _parse_event_cursor(cursor: str | None) -> tuple[int, int]:
    if not isinstance(cursor, str) or not cursor.strip():
        return (0, 0)
    if "-" not in cursor:
        try:
            return (int(cursor), 0)
        except ValueError:
            return (0, 0)
    left, right = cursor.split("-", 1)
    try:
        return (int(left), int(right))
    except ValueError:
        return (0, 0)
