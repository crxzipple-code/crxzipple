from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any

from crxzipple.modules.channels.domain import channel_dead_letter_topic
from crxzipple.modules.operations.application.observation import observed_event_from_record
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_STALE_RUNTIME_AFTER_SECONDS = 300.0
_RECENT_TOPIC_LIMIT = 40
_MAX_EVENT_TOPICS = 180
_MAX_RECENT_EVENTS = 240


@dataclass(frozen=True, slots=True)
class ChannelsOperationsQuery:
    status: str = "all"
    channel_type: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ChannelRuntimeDetailModel:
    runtime_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    capabilities: OperationsKeyValueSectionModel
    account_bindings: OperationsTableSectionModel
    connection_bindings: OperationsTableSectionModel
    events: OperationsTableSectionModel
    dead_letters: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelRecordDetailModel:
    record_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    payload: dict[str, Any]
    trace: dict[str, Any]
    related: OperationsTableSectionModel


@dataclass(frozen=True, slots=True)
class ChannelInteractionDetailModel:
    interaction_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    routing: OperationsKeyValueSectionModel
    reply_address: OperationsKeyValueSectionModel
    metadata: OperationsKeyValueSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChannelsOperationsPage:
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
    channel_status: OperationsTableSectionModel
    message_flow: OperationsChartSectionModel
    delivery_trend: OperationsChartSectionModel
    top_channels: OperationsChartSectionModel
    dead_letter_queue: OperationsTableSectionModel
    recent_messages: OperationsTableSectionModel
    interactions: OperationsTableSectionModel
    failures_by_category: OperationsChartSectionModel
    channel_bindings: OperationsTableSectionModel
    connection_bindings: OperationsTableSectionModel
    channel_profiles: OperationsTableSectionModel
    channel_events: OperationsTableSectionModel
    contracts: OperationsTableSectionModel
    runtime_details: tuple[ChannelRuntimeDetailModel, ...]
    record_details: tuple[ChannelRecordDetailModel, ...]
    interaction_details: tuple[ChannelInteractionDetailModel, ...]


@dataclass(frozen=True, slots=True)
class _ChannelEventRecord:
    id: str
    cursor: str
    topic: str
    event_name: str
    kind: str
    status: str
    occurred_at: datetime
    channel_type: str | None = None
    runtime_id: str | None = None
    channel_account_id: str | None = None
    connection_id: str | None = None
    conversation_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChannelsOperationsReadModelProvider:
    channel_profile_service: Any | None
    channel_runtime_manager: Any | None
    channel_interaction_service: Any | None = None
    events_service: Any | None = None
    event_contract_registry: Any | None = None
    event_definition_registry: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(ChannelsOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.channel_status),
            lane_locks=_overview_rows(page.dead_letter_queue),
            executor=_overview_rows(page.channel_profiles),
            actions=page.actions,
        )

    def page(
        self,
        query: ChannelsOperationsQuery | None = None,
    ) -> ChannelsOperationsPage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        profiles = _safe_tuple(self.channel_profile_service, "list_profiles")
        runtimes = _safe_tuple(
            self.channel_runtime_manager,
            "list_runtimes",
            channel_type=None,
        )
        account_bindings = _safe_tuple(
            self.channel_runtime_manager,
            "list_account_bindings",
        )
        connection_bindings = _safe_tuple(
            self.channel_runtime_manager,
            "list_connection_bindings",
        )
        interactions = _safe_tuple(
            self.channel_interaction_service,
            "list_interactions",
        )
        channel_types = _channel_types(
            profiles=profiles,
            runtimes=runtimes,
            account_bindings=account_bindings,
            connection_bindings=connection_bindings,
            interactions=interactions,
            events_service=self.events_service,
        )
        dead_letter_events = _dead_letter_events(
            self.events_service,
            channel_types=channel_types,
            runtimes=runtimes,
            definition_registry=self.event_definition_registry,
        )
        recent_events = _recent_channel_events(
            self.events_service,
            connection_bindings=connection_bindings,
            definition_registry=self.event_definition_registry,
        )
        channel_events = _dedupe_events((*dead_letter_events, *recent_events))
        runtime_records = _runtime_records(
            runtimes=runtimes,
            account_bindings=account_bindings,
            connection_bindings=connection_bindings,
            events=channel_events,
            now=now,
        )
        filtered_runtime_records = _filter_runtime_records(runtime_records, query)
        filtered_interactions = _filter_interactions(interactions, query)
        visible_interactions = filtered_interactions[
            query.offset : query.offset + query.limit
        ]
        filtered_events = _filter_events(channel_events, query)
        visible_events = filtered_events[query.offset : query.offset + query.limit]
        filtered_dead_letters = _filter_events(dead_letter_events, query)
        health = _health(
            service_available=self.channel_runtime_manager is not None,
            runtimes=runtime_records,
            profiles=profiles,
            dead_letters=dead_letter_events,
            interactions=interactions,
        )

        channel_status = _channel_status_table(
            filtered_runtime_records,
            total=len(filtered_runtime_records),
        )
        dead_letter_queue = _dead_letter_table(filtered_dead_letters)
        recent_messages = _recent_messages_table(
            visible_events,
            total=len(filtered_events),
        )
        interactions_table = _interactions_table(
            visible_interactions,
            total=len(filtered_interactions),
        )
        channel_bindings = _account_bindings_table(
            account_bindings,
            profiles=profiles,
        )
        connection_bindings_table = _connection_bindings_table(connection_bindings)
        channel_profiles = _profiles_table(profiles)
        channel_events_table = _channel_events_table(
            visible_events,
            total=len(filtered_events),
        )
        contracts = _contracts_table(
            event_contract_registry=self.event_contract_registry,
            event_definition_registry=self.event_definition_registry,
        )

        return ChannelsOperationsPage(
            module="channels",
            title="Channels",
            subtitle="聚合通道配置、运行时、绑定、死信与通道事件的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Channels operator",
                can_operate=True,
                scope="channels",
            ),
            metrics=_metrics(
                health=health,
                profiles=profiles,
                runtimes=runtime_records,
                account_bindings=account_bindings,
                connection_bindings=connection_bindings,
                events=channel_events,
                dead_letters=dead_letter_events,
                interactions=interactions,
            ),
            tabs=_tabs(
                runtimes=len(filtered_runtime_records),
                interactions=len(filtered_interactions),
                connections=len(connection_bindings),
                accounts=len(account_bindings),
                profiles=len(profiles),
                messages=len(filtered_events),
                dead_letters=len(filtered_dead_letters),
                contracts=contracts.total,
            ),
            active_tab="runtimes",
            actions=_actions(),
            channel_status=channel_status,
            message_flow=_message_flow(channel_events, interactions),
            delivery_trend=_delivery_trend(
                channel_events,
                runtime_records,
                interactions,
            ),
            top_channels=_top_channels(channel_events, runtime_records, interactions),
            dead_letter_queue=dead_letter_queue,
            recent_messages=recent_messages,
            interactions=interactions_table,
            failures_by_category=_failures_by_category(dead_letter_events),
            channel_bindings=channel_bindings,
            connection_bindings=connection_bindings_table,
            channel_profiles=channel_profiles,
            channel_events=channel_events_table,
            contracts=contracts,
            runtime_details=_runtime_details(
                runtimes=runtimes,
                runtime_records=runtime_records,
                account_bindings=account_bindings,
                connection_bindings=connection_bindings,
                events=channel_events,
                dead_letters=dead_letter_events,
                now=now,
            ),
            record_details=_record_details(
                (*visible_events, *filtered_dead_letters[:20]),
            ),
            interaction_details=_interaction_details(
                visible_interactions,
                events=channel_events,
            ),
        )


def _normalize_query(
    query: ChannelsOperationsQuery | None,
) -> ChannelsOperationsQuery:
    if query is None:
        return ChannelsOperationsQuery()
    return ChannelsOperationsQuery(
        status=_normalized_filter(query.status),
        channel_type=_normalized_filter(query.channel_type),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _safe_tuple(target: Any, method_name: str, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        value = method(*args, **kwargs)
    except Exception:
        return ()
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return tuple(value) if isinstance(value, set) else ()


def _channel_types(
    *,
    profiles: tuple[Any, ...],
    runtimes: tuple[Any, ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    interactions: tuple[Any, ...],
    events_service: Any | None,
) -> tuple[str, ...]:
    values = {
        _text(getattr(item, "channel_type", None), "")
        for item in (
            *profiles,
            *runtimes,
            *account_bindings,
            *connection_bindings,
            *interactions,
        )
    }
    if events_service is not None:
        values.update(
            _channel_from_topic(topic) or ""
            for topic in _safe_list_event_topics(events_service)
            if topic.startswith("channel.")
        )
    values.update({"web", "lark", "webhook"})
    return tuple(sorted(value for value in values if value))


def _dead_letter_events(
    events_service: Any | None,
    *,
    channel_types: tuple[str, ...],
    runtimes: tuple[Any, ...],
    definition_registry: Any | None,
) -> tuple[_ChannelEventRecord, ...]:
    if events_service is None:
        return ()
    topics = {
        topic
        for topic in _safe_list_event_topics(events_service)
        if topic.startswith("channel.dead_letter.")
    }
    for channel_type in channel_types:
        topics.add(channel_dead_letter_topic(channel_type))
    for runtime in runtimes:
        channel_type = _text(getattr(runtime, "channel_type", None), "")
        runtime_id = _text(getattr(runtime, "runtime_id", None), "")
        if channel_type and runtime_id:
            topics.add(channel_dead_letter_topic(channel_type, runtime_id=runtime_id))
    return _read_event_records(
        events_service,
        tuple(sorted(topics)),
        definition_registry=definition_registry,
        per_topic_limit=80,
    )


def _recent_channel_events(
    events_service: Any | None,
    *,
    connection_bindings: tuple[Any, ...],
    definition_registry: Any | None,
) -> tuple[_ChannelEventRecord, ...]:
    if events_service is None:
        return ()
    live_topics = _safe_list_event_topics(events_service)
    topic_set = {
        topic
        for topic in live_topics
        if topic.startswith("channel.")
    }
    topic_set.update(
        topic
        for topic in _connection_event_topics(connection_bindings)
        if topic in live_topics
    )
    topics = tuple(sorted(topic_set))[:_MAX_EVENT_TOPICS]
    events = _read_event_records(
        events_service,
        topics,
        definition_registry=definition_registry,
        per_topic_limit=_RECENT_TOPIC_LIMIT,
    )
    binding_by_conversation = _connection_binding_by_conversation(connection_bindings)
    return tuple(
        _with_connection_binding(event, binding_by_conversation=binding_by_conversation)
        for event in events
    )


def _read_event_records(
    events_service: Any,
    topics: tuple[str, ...],
    *,
    definition_registry: Any | None,
    per_topic_limit: int,
) -> tuple[_ChannelEventRecord, ...]:
    records: list[_ChannelEventRecord] = []
    for topic in topics:
        read_recent = getattr(events_service, "read_recent_event_topic", None)
        if not callable(read_recent):
            continue
        try:
            topic_records = read_recent(topic, limit=per_topic_limit)
        except Exception:
            continue
        for record in tuple(topic_records or ()):
            records.append(
                _channel_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            )
    records.sort(key=lambda item: item.occurred_at, reverse=True)
    return tuple(records[:_MAX_RECENT_EVENTS])


def _channel_event_from_record(
    record: Any,
    *,
    definition_registry: Any | None,
) -> _ChannelEventRecord:
    observed = observed_event_from_record(
        record,
        definition_registry=definition_registry,
    )
    event = record.envelope
    payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    trace = dict(getattr(event, "trace", {}) or {})
    target_payload = (
        event.target.to_payload() if getattr(event, "target", None) is not None else {}
    )
    topic = _text(getattr(event, "topic", None), "") or _text(getattr(record, "cursor", None), "")
    return _ChannelEventRecord(
        id=_text(getattr(event, "id", None), observed.id),
        cursor=_text(getattr(record, "cursor", None), observed.cursor),
        topic=topic,
        event_name=observed.event_name,
        kind=_text(getattr(event, "kind", None), observed.kind),
        status=_event_status(observed, payload),
        occurred_at=coerce_utc_datetime(getattr(event, "occurred_at", observed.occurred_at)),
        channel_type=_first_text(
            payload.get("channel_type"),
            payload.get("channel"),
            target_payload.get("transport"),
            target_payload.get("channel_type"),
            _channel_from_topic(topic),
        ),
        runtime_id=_first_text(
            payload.get("runtime_id"),
            target_payload.get("runtime"),
            target_payload.get("runtime_id"),
            _runtime_from_topic(topic),
        ),
        channel_account_id=_first_text(
            payload.get("channel_account_id"),
            payload.get("account_id"),
            target_payload.get("account"),
            target_payload.get("channel_account_id"),
        ),
        connection_id=_first_text(
            payload.get("connection_id"),
            target_payload.get("connection"),
            target_payload.get("connection_id"),
            _connection_from_topic(topic),
        ),
        conversation_id=_first_text(
            payload.get("conversation_id"),
            payload.get("session_key"),
            target_payload.get("conversation"),
            target_payload.get("conversation_id"),
        ),
        run_id=_first_text(payload.get("run_id"), observed.run_id),
        trace_id=_first_text(trace.get("trace_id"), observed.trace_id),
        payload=payload,
        trace=trace,
    )


def _with_connection_binding(
    event: _ChannelEventRecord,
    *,
    binding_by_conversation: dict[str, Any],
) -> _ChannelEventRecord:
    if event.conversation_id is None:
        return event
    binding = binding_by_conversation.get(event.conversation_id)
    if binding is None:
        return event
    return _ChannelEventRecord(
        id=event.id,
        cursor=event.cursor,
        topic=event.topic,
        event_name=event.event_name,
        kind=event.kind,
        status=event.status,
        occurred_at=event.occurred_at,
        channel_type=event.channel_type or _text(getattr(binding, "channel_type", None), ""),
        runtime_id=event.runtime_id or _text(getattr(binding, "runtime_id", None), ""),
        channel_account_id=event.channel_account_id
        or _text(getattr(binding, "channel_account_id", None), ""),
        connection_id=event.connection_id or _text(getattr(binding, "connection_id", None), ""),
        conversation_id=event.conversation_id,
        run_id=event.run_id,
        trace_id=event.trace_id,
        payload=event.payload,
        trace=event.trace,
    )


def _runtime_records(
    *,
    runtimes: tuple[Any, ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    events: tuple[_ChannelEventRecord, ...],
    now: datetime,
) -> tuple[dict[str, Any], ...]:
    accounts_by_runtime = _group_by_runtime(account_bindings)
    connections_by_runtime = _group_by_runtime(connection_bindings)
    event_counts = Counter(
        event.runtime_id
        for event in events
        if event.runtime_id is not None and event.runtime_id
    )
    rows: list[dict[str, Any]] = []
    for runtime in runtimes:
        runtime_id = _text(getattr(runtime, "runtime_id", None), "")
        status = _runtime_status(runtime, now=now)
        rows.append(
            {
                "id": runtime_id,
                "runtime_id": runtime_id,
                "channel_type": _text(getattr(runtime, "channel_type", None)),
                "service_key": _text(getattr(runtime, "service_key", None)),
                "status": status,
                "registered_at": _format_datetime(getattr(runtime, "registered_at", None)),
                "last_heartbeat": _format_datetime(getattr(runtime, "last_heartbeat_at", None)),
                "heartbeat_age": _age_label(
                    _seconds_since(getattr(runtime, "last_heartbeat_at", None), now=now)
                ),
                "account_count": len(accounts_by_runtime.get(runtime_id, ())),
                "connection_count": len(connections_by_runtime.get(runtime_id, ())),
                "event_count": event_counts[runtime_id],
                "action": "Open",
                "route": f"/operations/channels?runtime_id={runtime_id}",
                "tone": _tone_for_status(status),
            }
        )
    rows.sort(
        key=lambda item: (
            item["status"] != "Stale",
            item["status"] not in {"Offline", "Error", "Failed"},
            item["channel_type"],
            item["runtime_id"],
        )
    )
    return tuple(rows)


def _filter_runtime_records(
    rows: tuple[dict[str, Any], ...],
    query: ChannelsOperationsQuery,
) -> tuple[dict[str, Any], ...]:
    filtered: list[dict[str, Any]] = []
    needle = query.search.lower()
    for row in rows:
        if query.channel_type != "all" and row["channel_type"].lower() != query.channel_type:
            continue
        if query.status != "all" and _normalized_filter(row["status"]) != query.status:
            continue
        if needle and needle not in " ".join(_text(value, "") for value in row.values()).lower():
            continue
        filtered.append(row)
    return tuple(filtered)


def _filter_events(
    events: tuple[_ChannelEventRecord, ...],
    query: ChannelsOperationsQuery,
) -> tuple[_ChannelEventRecord, ...]:
    filtered: list[_ChannelEventRecord] = []
    needle = query.search.lower()
    for event in events:
        if query.channel_type != "all" and (event.channel_type or "").lower() != query.channel_type:
            continue
        if query.status != "all" and _normalized_filter(event.status) != query.status:
            continue
        if needle and needle not in _event_search_text(event):
            continue
        filtered.append(event)
    return tuple(filtered)


def _filter_interactions(
    interactions: tuple[Any, ...],
    query: ChannelsOperationsQuery,
) -> tuple[Any, ...]:
    filtered: list[Any] = []
    needle = query.search.lower()
    for interaction in interactions:
        if (
            query.channel_type != "all"
            and _text(getattr(interaction, "channel_type", None), "").lower()
            != query.channel_type
        ):
            continue
        if (
            query.status != "all"
            and _normalized_filter(getattr(interaction, "status", None))
            != query.status
        ):
            continue
        if needle and needle not in _interaction_search_text(interaction):
            continue
        filtered.append(interaction)
    filtered.sort(
        key=lambda item: _sort_datetime(getattr(item, "updated_at", None)),
        reverse=True,
    )
    return tuple(filtered)


def _health(
    *,
    service_available: bool,
    runtimes: tuple[dict[str, Any], ...],
    profiles: tuple[Any, ...],
    dead_letters: tuple[_ChannelEventRecord, ...],
    interactions: tuple[Any, ...],
) -> str:
    if not service_available:
        return "error"
    if dead_letters:
        return "error"
    if any(row["status"] in {"Error", "Failed", "Offline"} for row in runtimes):
        return "error"
    if any(_interaction_tone(item) == "danger" for item in interactions):
        return "error"
    if any(row["status"] == "Stale" for row in runtimes):
        return "warning"
    if not runtimes and not profiles:
        return "warning"
    return "healthy"


def _metrics(
    *,
    health: str,
    profiles: tuple[Any, ...],
    runtimes: tuple[dict[str, Any], ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    events: tuple[_ChannelEventRecord, ...],
    dead_letters: tuple[_ChannelEventRecord, ...],
    interactions: tuple[Any, ...],
) -> tuple[MetricCardModel, ...]:
    online = sum(1 for row in runtimes if row["status"] == "Online")
    stale = sum(1 for row in runtimes if row["status"] == "Stale")
    enabled_profiles = sum(1 for profile in profiles if bool(getattr(profile, "enabled", True)))
    bound_interactions = sum(
        1 for interaction in interactions if _text(getattr(interaction, "run_id", None), "")
    )
    failed_interactions = sum(
        1 for interaction in interactions if _interaction_tone(interaction) == "danger"
    )
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=_health_label(health),
            delta=_health_delta(health),
            tone=_health_tone(health),
        ),
        MetricCardModel(
            id="runtimes",
            label="Runtimes",
            value=str(len(runtimes)),
            delta=f"{online} online / {stale} stale",
            tone="warning" if stale else "success",
        ),
        MetricCardModel(
            id="profiles",
            label="Channel Profiles",
            value=str(len(profiles)),
            delta=f"{enabled_profiles} enabled",
            tone="success" if enabled_profiles else "warning",
        ),
        MetricCardModel(
            id="connections",
            label="Connections",
            value=str(len(connection_bindings)),
            delta="runtime connection bindings",
            tone="info" if connection_bindings else "neutral",
        ),
        MetricCardModel(
            id="accounts",
            label="Accounts",
            value=str(len(account_bindings)),
            delta="runtime account bindings",
            tone="info" if account_bindings else "neutral",
        ),
        MetricCardModel(
            id="interactions",
            label="Interactions",
            value=str(len(interactions)),
            delta=f"{bound_interactions} bound / {failed_interactions} failed",
            tone="danger" if failed_interactions else "info" if interactions else "neutral",
        ),
        MetricCardModel(
            id="dead_letters",
            label="Dead Letters",
            value=str(len(dead_letters)),
            delta="retained channel failures",
            tone="danger" if dead_letters else "success",
        ),
        MetricCardModel(
            id="events",
            label="Channel Events",
            value=str(len(events)),
            delta="recent event-bus records",
            tone="info" if events else "neutral",
        ),
    )


def _tabs(
    *,
    runtimes: int,
    interactions: int,
    connections: int,
    accounts: int,
    profiles: int,
    messages: int,
    dead_letters: int,
    contracts: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("runtimes", "Runtimes", runtimes, "warning" if runtimes else "neutral"),
        OperationsTabModel("interactions", "Interactions", interactions, "danger" if interactions else "neutral"),
        OperationsTabModel("connections", "Connections", connections),
        OperationsTabModel("accounts", "Accounts", accounts),
        OperationsTabModel("profiles", "Profiles", profiles),
        OperationsTabModel("messages", "Recent Messages", messages),
        OperationsTabModel("dead_letters", "Dead Letters", dead_letters, "danger" if dead_letters else "neutral"),
        OperationsTabModel("events", "Channel Events", messages),
        OperationsTabModel("contracts", "Contracts", contracts),
    )


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_channel_runtime",
            label="Open Runtime",
            owner="channels",
            kind="navigation",
        ),
        RuntimeActionModel(
            id="inspect_dead_letter",
            label="Inspect Dead Letter",
            owner="channels",
            kind="navigation",
            risk="controlled",
        ),
        RuntimeActionModel(
            id="replay_dead_letter",
            label="Replay Dead Letter",
            owner="channels",
            risk="dangerous",
            requires_confirmation=True,
            audit_event="channels.dead_letter.replay",
            method="POST",
            endpoint="/operations/channels/dead-letters/{channel_type}/replay",
        ),
        RuntimeActionModel(
            id="prune_stale_runtimes",
            label="Prune Stale Runtimes",
            owner="channels",
            risk="dangerous",
            requires_confirmation=True,
            reason_required=True,
            audit_event="channels.runtimes.prune_stale",
            method="POST",
            endpoint="/operations/channels/runtimes/prune-stale",
        ),
    )


def _channel_status_table(
    rows: tuple[dict[str, Any], ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    return _table(
        "channel_status",
        "Channel Runtimes",
        (
            ("runtime_id", "Runtime ID"),
            ("channel_type", "Channel Type"),
            ("status", "Status"),
            ("heartbeat_age", "Heartbeat Age"),
            ("account_count", "Accounts"),
            ("connection_count", "Connections"),
            ("event_count", "Events"),
            ("action", "Action"),
        ),
        rows,
        total=total,
        empty_state="No channel runtimes registered.",
    )


def _dead_letter_table(
    events: tuple[_ChannelEventRecord, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        {
            "id": event.id,
            "time": format_datetime_utc(event.occurred_at),
            "channel_type": _text(event.channel_type),
            "runtime_id": _text(event.runtime_id),
            "status": "Dead Letter",
            "outbound_id": _text(event.payload.get("outbound_id")),
            "reason": _failure_reason(event),
            "attempt_count": _text(event.payload.get("attempt_count")),
            "topic": _display_text(event.topic),
            "cursor": event.cursor,
            "action": "Inspect",
            "trace_route": _trace_route(event),
            "route": _trace_route(event),
            "tone": "danger",
        }
        for event in events
    )
    return _table(
        "dead_letter_queue",
        "Dead Letter Queue",
        (
            ("time", "Time"),
            ("channel_type", "Channel Type"),
            ("runtime_id", "Runtime ID"),
            ("outbound_id", "Outbound ID"),
            ("reason", "Reason"),
            ("attempt_count", "Attempt"),
            ("topic", "Topic"),
            ("action", "Action"),
        ),
        rows,
        total=len(events),
        empty_state="No channel dead letters observed.",
    )


def _recent_messages_table(
    events: tuple[_ChannelEventRecord, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = tuple(_message_row(event) for event in events)
    return _table(
        "recent_messages",
        "Recent Messages",
        (
            ("time", "Time"),
            ("channel_type", "Channel Type"),
            ("direction", "Direction"),
            ("event", "Event"),
            ("runtime_id", "Runtime ID"),
            ("conversation_id", "Conversation ID"),
            ("status", "Status"),
            ("trace", "Trace"),
        ),
        rows,
        total=total,
        empty_state="No channel messages or channel events observed.",
    )


def _message_row(event: _ChannelEventRecord) -> dict[str, Any]:
    return {
        "id": event.id,
        "time": format_datetime_utc(event.occurred_at),
        "channel_type": _text(event.channel_type),
        "direction": _event_direction(event),
        "event": _display_text(event.event_name),
        "runtime_id": _text(event.runtime_id),
        "connection_id": _text(event.connection_id),
        "conversation_id": _text(event.conversation_id),
        "status": _status_label(event.status),
        "topic": _display_text(event.topic),
        "cursor": event.cursor,
        "trace": _text(event.trace_id),
        "trace_route": _trace_route(event),
        "route": _trace_route(event),
        "tone": _tone_for_status(event.status),
    }


def _interactions_table(
    interactions: tuple[Any, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = tuple(_interaction_row(interaction) for interaction in interactions)
    return _table(
        "interactions",
        "Interactions",
        (
            ("interaction_id", "Interaction ID"),
            ("channel_type", "Channel Type"),
            ("status", "Status"),
            ("account_id", "Account ID"),
            ("run_id", "Run ID"),
            ("session_key", "Session Key"),
            ("agent_id", "Agent"),
            ("updated_at", "Updated At"),
            ("last_error", "Last Error"),
        ),
        rows,
        total=total,
        empty_state="No channel interactions registered.",
    )


def _interaction_row(interaction: Any) -> dict[str, Any]:
    status = _status_label(_text(getattr(interaction, "status", None), "received"))
    return {
        "id": _text(getattr(interaction, "interaction_id", None), ""),
        "interaction_id": _text(getattr(interaction, "interaction_id", None)),
        "channel_type": _text(getattr(interaction, "channel_type", None)),
        "status": status,
        "account_id": _text(getattr(interaction, "channel_account_id", None)),
        "run_id": _text(getattr(interaction, "run_id", None)),
        "session_key": _text(getattr(interaction, "session_key", None)),
        "agent_id": _text(getattr(interaction, "agent_id", None)),
        "updated_at": _format_datetime(getattr(interaction, "updated_at", None)),
        "last_error": _short_optional(getattr(interaction, "last_error", None)),
        "observe_cursor": _text(_metadata_value(interaction, "observe_cursor")),
        "active_session_id": _text(_metadata_value(interaction, "active_session_id")),
        "tone": _interaction_tone(interaction),
    }


def _account_bindings_table(
    bindings: tuple[Any, ...],
    *,
    profiles: tuple[Any, ...],
) -> OperationsTableSectionModel:
    profile_by_type = {
        _text(getattr(profile, "channel_type", None), ""): profile for profile in profiles
    }
    rows = []
    for binding in bindings:
        channel_type = _text(getattr(binding, "channel_type", None), "")
        account_id = _text(getattr(binding, "channel_account_id", None), "")
        account_profile = _account_profile(profile_by_type.get(channel_type), account_id)
        rows.append(
            {
                "id": f"{channel_type}:{account_id}",
                "channel_type": channel_type,
                "account_id": account_id,
                "runtime_id": _text(getattr(binding, "runtime_id", None)),
                "transport_mode": _text(
                    getattr(account_profile, "transport_mode", None)
                    if account_profile is not None
                    else _metadata_value(binding, "transport_mode")
                ),
                "status": "Enabled"
                if account_profile is None or bool(getattr(account_profile, "enabled", True))
                else "Disabled",
                "updated_at": _format_datetime(getattr(binding, "updated_at", None)),
                "metadata": _short_json(getattr(binding, "metadata", {})),
                "tone": "success",
            }
        )
    return _table(
        "channel_bindings",
        "Account Bindings",
        (
            ("channel_type", "Channel Type"),
            ("account_id", "Account ID"),
            ("runtime_id", "Runtime ID"),
            ("transport_mode", "Transport Mode"),
            ("status", "Status"),
            ("updated_at", "Updated At"),
        ),
        tuple(rows),
        total=len(rows),
        empty_state="No channel account bindings registered.",
    )


def _connection_bindings_table(
    bindings: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(_connection_binding_row(binding) for binding in bindings)
    return _table(
        "connection_bindings",
        "Connection Bindings",
        (
            ("channel_type", "Channel Type"),
            ("connection_id", "Connection ID"),
            ("runtime_id", "Runtime ID"),
            ("account_id", "Account ID"),
            ("conversation_id", "Conversation ID"),
            ("supports_streaming", "Streaming"),
            ("observe_cursor", "Observe Cursor"),
            ("live_cursor", "Live Cursor"),
            ("updated_at", "Updated At"),
        ),
        rows,
        total=len(rows),
        empty_state="No channel connection bindings registered.",
    )


def _connection_binding_row(binding: Any) -> dict[str, Any]:
    return {
        "id": _text(getattr(binding, "connection_id", None), ""),
        "channel_type": _text(getattr(binding, "channel_type", None)),
        "connection_id": _text(getattr(binding, "connection_id", None)),
        "runtime_id": _text(getattr(binding, "runtime_id", None)),
        "account_id": _text(getattr(binding, "channel_account_id", None)),
        "conversation_id": _text(getattr(binding, "conversation_id", None)),
        "supports_streaming": "Yes" if bool(getattr(binding, "supports_streaming", False)) else "No",
        "updated_at": _format_datetime(getattr(binding, "updated_at", None)),
        "observe_cursor": _text(_metadata_value(binding, "observe_cursor")),
        "live_cursor": _text(_metadata_value(binding, "live_cursor")),
        "status": "Active",
        "tone": "success",
    }


def _profiles_table(
    profiles: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = []
    for profile in profiles:
        accounts = tuple(getattr(profile, "accounts", ()) or ())
        rows.append(
            {
                "id": _text(getattr(profile, "channel_type", None), ""),
                "channel_type": _text(getattr(profile, "channel_type", None)),
                "status": "Enabled" if bool(getattr(profile, "enabled", True)) else "Disabled",
                "account_count": len(accounts),
                "transport_modes": _join(
                    getattr(account, "transport_mode", None) for account in accounts
                ),
                "capabilities": _capabilities_label(getattr(profile, "capabilities", None)),
                "metadata": _short_json(getattr(profile, "metadata", {})),
                "tone": "success" if bool(getattr(profile, "enabled", True)) else "warning",
            }
        )
    return _table(
        "channel_profiles",
        "Channel Profiles",
        (
            ("channel_type", "Channel Type"),
            ("status", "Status"),
            ("account_count", "Accounts"),
            ("transport_modes", "Transport Modes"),
            ("capabilities", "Capabilities"),
            ("metadata", "Metadata"),
        ),
        tuple(rows),
        total=len(rows),
        empty_state="No channel profiles configured.",
    )


def _channel_events_table(
    events: tuple[_ChannelEventRecord, ...],
    *,
    total: int,
) -> OperationsTableSectionModel:
    rows = tuple(
        {
            **_message_row(event),
            "kind": _title(event.kind),
            "topic": event.topic,
            "cursor": event.cursor,
        }
        for event in events
    )
    return _table(
        "channel_events",
        "Channel Events",
        (
            ("time", "Time"),
            ("topic", "Topic"),
            ("event", "Event"),
            ("kind", "Kind"),
            ("status", "Status"),
            ("cursor", "Cursor"),
            ("trace", "Trace"),
        ),
        rows,
        total=total,
        empty_state="No channel event records observed.",
    )


def _contracts_table(
    *,
    event_contract_registry: Any | None,
    event_definition_registry: Any | None,
) -> OperationsTableSectionModel:
    rows: list[dict[str, Any]] = []
    for contract in _safe_tuple(event_contract_registry, "list_topic_contracts"):
        if _text(getattr(contract, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": _display_text(getattr(contract, "contract_id", None), ""),
                "type": "Topic Contract",
                "name": _display_text(getattr(contract, "contract_id", None)),
                "pattern": _display_text(getattr(contract, "topic_pattern", None)),
                "kind": _join(getattr(contract, "kinds", ()) or ()),
                "status": "Registered",
                "tone": "success",
            }
        )
    for contract in _safe_tuple(event_contract_registry, "list_route_contracts"):
        if _text(getattr(contract, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": _display_text(getattr(contract, "contract_id", None), ""),
                "type": "Route Contract",
                "name": _display_text(getattr(contract, "contract_id", None)),
                "pattern": _display_text(getattr(contract, "source_topic_pattern", None)),
                "kind": _text(getattr(contract, "target_kind", None)),
                "status": "Registered",
                "tone": "success",
            }
        )
    for definition in _safe_tuple(event_definition_registry, "list_definitions"):
        if _text(getattr(definition, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": _display_text(getattr(definition, "definition_id", None), ""),
                "type": "Definition",
                "name": _display_text(getattr(definition, "event_name", None)),
                "pattern": _join(
                    _display_text(topic)
                    for topic in getattr(definition, "topics", ()) or ()
                ),
                "kind": _text(getattr(definition, "publication_mode", None)),
                "status": "Registered",
                "tone": "success",
            }
        )
    for surface in _safe_tuple(event_definition_registry, "list_surfaces"):
        if _text(getattr(surface, "owner", None), "").lower() != "channels":
            continue
        rows.append(
            {
                "id": _display_text(getattr(surface, "surface_id", None), ""),
                "type": "Surface",
                "name": _display_text(getattr(surface, "surface_id", None)),
                "pattern": _join(
                    _display_text(topic)
                    for topic in getattr(surface, "topics", ()) or ()
                ),
                "kind": "surface",
                "status": "Registered",
                "tone": "success",
            }
        )
    return _table(
        "contracts",
        "Contracts",
        (
            ("type", "Type"),
            ("name", "Name"),
            ("pattern", "Pattern"),
            ("kind", "Kind"),
            ("status", "Status"),
        ),
        tuple(rows),
        total=len(rows),
        empty_state="No channel event contracts registered.",
    )


def _message_flow(
    events: tuple[_ChannelEventRecord, ...],
    interactions: tuple[Any, ...],
) -> OperationsChartSectionModel:
    counts = Counter(_event_direction(event) for event in events)
    for interaction in interactions:
        counts["Intake"] += 1
    return _chart(
        "message_flow",
        "Message Flow",
        "donut",
        counts,
        tone_by_label={
            "Intake": "info",
            "Observe": "info",
            "Live": "success",
            "Broadcast": "info",
            "Control": "warning",
            "Dead Letter": "danger",
            "Other": "neutral",
        },
    )


def _delivery_trend(
    events: tuple[_ChannelEventRecord, ...],
    runtime_records: tuple[dict[str, Any], ...],
    interactions: tuple[Any, ...],
) -> OperationsChartSectionModel:
    if events:
        counts = Counter(_status_label(event.status) for event in events)
    elif interactions:
        counts = Counter(
            _status_label(_text(getattr(interaction, "status", None), "received"))
            for interaction in interactions
        )
    else:
        counts = Counter(_status_label(_text(row.get("status"))) for row in runtime_records)
    return _chart(
        "delivery_trend",
        "Runtime / Delivery Status",
        "bar",
        counts,
    )


def _top_channels(
    events: tuple[_ChannelEventRecord, ...],
    runtime_records: tuple[dict[str, Any], ...],
    interactions: tuple[Any, ...],
) -> OperationsChartSectionModel:
    counts = Counter(
        event.channel_type or "unknown"
        for event in events
        if event.channel_type or event.topic.startswith("channel.")
    )
    for interaction in interactions:
        channel_type = _text(getattr(interaction, "channel_type", None), "")
        if channel_type:
            counts[channel_type] += 1
    if not counts:
        counts = Counter(_text(row.get("channel_type"), "unknown") for row in runtime_records)
    return _chart("top_channels", "Top Channels", "bar", counts)


def _failures_by_category(
    dead_letters: tuple[_ChannelEventRecord, ...],
) -> OperationsChartSectionModel:
    counts = Counter(_failure_reason(event) for event in dead_letters)
    return _chart(
        "failures_by_category",
        "Failures by Category",
        "bar",
        counts,
        default_tone="danger",
    )


def _chart(
    section_id: str,
    title: str,
    kind: str,
    counts: Counter[str],
    *,
    default_tone: str = "neutral",
    tone_by_label: dict[str, str] | None = None,
) -> OperationsChartSectionModel:
    tone_by_label = tone_by_label or {}
    segments = tuple(
        OperationsChartSegmentModel(
            id=_id_for(label),
            label=label,
            value=count,
            tone=tone_by_label.get(label, _tone_for_status(label, default=default_tone)),
        )
        for label, count in counts.most_common()
        if count > 0
    )
    return OperationsChartSectionModel(
        id=section_id,
        title=title,
        kind=kind,
        total=sum(segment.value for segment in segments),
        segments=segments,
    )


def _runtime_details(
    *,
    runtimes: tuple[Any, ...],
    runtime_records: tuple[dict[str, Any], ...],
    account_bindings: tuple[Any, ...],
    connection_bindings: tuple[Any, ...],
    events: tuple[_ChannelEventRecord, ...],
    dead_letters: tuple[_ChannelEventRecord, ...],
    now: datetime,
) -> tuple[ChannelRuntimeDetailModel, ...]:
    record_by_id = {row["runtime_id"]: row for row in runtime_records}
    accounts_by_runtime = _group_by_runtime(account_bindings)
    connections_by_runtime = _group_by_runtime(connection_bindings)
    details: list[ChannelRuntimeDetailModel] = []
    for runtime in runtimes:
        runtime_id = _text(getattr(runtime, "runtime_id", None), "")
        if not runtime_id:
            continue
        runtime_events = tuple(event for event in events if _event_matches_runtime(event, runtime_id, connections_by_runtime.get(runtime_id, ())))
        runtime_dead_letters = tuple(event for event in dead_letters if _event_matches_runtime(event, runtime_id, connections_by_runtime.get(runtime_id, ())))
        status = _text(record_by_id.get(runtime_id, {}).get("status"), _runtime_status(runtime, now=now))
        details.append(
            ChannelRuntimeDetailModel(
                runtime_id=runtime_id,
                title=runtime_id,
                status=status,
                tone=_tone_for_status(status),
                summary=(
                    OperationsKeyValueItemModel("Runtime ID", runtime_id, "neutral"),
                    OperationsKeyValueItemModel(
                        "Channel Type",
                        _text(getattr(runtime, "channel_type", None)),
                        "info",
                    ),
                    OperationsKeyValueItemModel("Status", status, _tone_for_status(status)),
                    OperationsKeyValueItemModel(
                        "Service Key",
                        _text(getattr(runtime, "service_key", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Heartbeat Age",
                        _age_label(_seconds_since(getattr(runtime, "last_heartbeat_at", None), now=now)),
                        _tone_for_status(status),
                    ),
                    OperationsKeyValueItemModel(
                        "Connections",
                        str(len(connections_by_runtime.get(runtime_id, ()))),
                        "info",
                    ),
                    OperationsKeyValueItemModel(
                        "Dead Letters",
                        str(len(runtime_dead_letters)),
                        "danger" if runtime_dead_letters else "success",
                    ),
                ),
                capabilities=_capabilities_section(getattr(runtime, "capabilities", None)),
                account_bindings=_account_bindings_table(
                    tuple(accounts_by_runtime.get(runtime_id, ())),
                    profiles=(),
                ),
                connection_bindings=_connection_bindings_table(
                    tuple(connections_by_runtime.get(runtime_id, ())),
                ),
                events=_channel_events_table(runtime_events[:40], total=len(runtime_events)),
                dead_letters=_dead_letter_table(runtime_dead_letters),
                raw_payload=_payload_from_runtime(runtime),
            )
        )
    return tuple(details)


def _record_details(
    events: tuple[_ChannelEventRecord, ...],
) -> tuple[ChannelRecordDetailModel, ...]:
    unique = _dedupe_events(events)
    return tuple(
        ChannelRecordDetailModel(
            record_id=event.id,
            title=_display_text(event.event_name),
            status=_status_label(event.status),
            tone=_tone_for_status(event.status),
            summary=(
                OperationsKeyValueItemModel("Event ID", event.id, "neutral"),
                OperationsKeyValueItemModel("Topic", _display_text(event.topic), "info"),
                OperationsKeyValueItemModel("Cursor", event.cursor, "neutral"),
                OperationsKeyValueItemModel(
                    "Channel Type",
                    _text(event.channel_type),
                    "info",
                ),
                OperationsKeyValueItemModel(
                    "Runtime ID",
                    _text(event.runtime_id),
                    "neutral",
                ),
                OperationsKeyValueItemModel(
                    "Status",
                    _status_label(event.status),
                    _tone_for_status(event.status),
                ),
            ),
            payload=_display_payload(event.payload),
            trace=_display_payload(event.trace),
            related=_table(
                "record_related",
                "Related Routing",
                (
                    ("field", "Field"),
                    ("value", "Value"),
                ),
                tuple(
                    {"id": key, "field": label, "value": value}
                    for key, label, value in (
                        ("run_id", "Run ID", _text(event.run_id)),
                        ("trace_id", "Trace", _text(event.trace_id)),
                        ("connection_id", "Connection ID", _text(event.connection_id)),
                        ("conversation_id", "Conversation ID", _text(event.conversation_id)),
                    )
                    if value != "-"
                ),
                total=4,
                empty_state="No related routing identifiers.",
            ),
        )
        for event in unique[:80]
    )


def _interaction_details(
    interactions: tuple[Any, ...],
    *,
    events: tuple[_ChannelEventRecord, ...],
) -> tuple[ChannelInteractionDetailModel, ...]:
    details: list[ChannelInteractionDetailModel] = []
    for interaction in interactions[:80]:
        interaction_id = _text(getattr(interaction, "interaction_id", None), "")
        if not interaction_id:
            continue
        status = _status_label(_text(getattr(interaction, "status", None), "received"))
        related_events = _events_for_interaction(interaction, events)
        details.append(
            ChannelInteractionDetailModel(
                interaction_id=interaction_id,
                title=interaction_id,
                status=status,
                tone=_interaction_tone(interaction),
                summary=(
                    OperationsKeyValueItemModel(
                        "Interaction ID",
                        interaction_id,
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Channel Type",
                        _text(getattr(interaction, "channel_type", None)),
                        "info",
                    ),
                    OperationsKeyValueItemModel(
                        "Account ID",
                        _text(getattr(interaction, "channel_account_id", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Status",
                        status,
                        _interaction_tone(interaction),
                    ),
                    OperationsKeyValueItemModel(
                        "Run ID",
                        _text(getattr(interaction, "run_id", None)),
                        "info",
                    ),
                    OperationsKeyValueItemModel(
                        "Session Key",
                        _text(getattr(interaction, "session_key", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Updated At",
                        _format_datetime(getattr(interaction, "updated_at", None)),
                        "neutral",
                    ),
                    OperationsKeyValueItemModel(
                        "Last Error",
                        _short_optional(getattr(interaction, "last_error", None)),
                        _interaction_tone(interaction),
                    ),
                ),
                routing=_key_value_section(
                    "interaction_routing",
                    "Routing",
                    {
                        "external_event_id": getattr(interaction, "external_event_id", None),
                        "external_message_id": getattr(interaction, "external_message_id", None),
                        "external_conversation_id": getattr(
                            interaction,
                            "external_conversation_id",
                            None,
                        ),
                        "external_user_id": getattr(interaction, "external_user_id", None),
                        "agent_id": getattr(interaction, "agent_id", None),
                        "active_session_id": _metadata_value(
                            interaction,
                            "active_session_id",
                        ),
                        "observe_cursor": _metadata_value(interaction, "observe_cursor"),
                    },
                ),
                reply_address=_key_value_section(
                    "reply_address",
                    "Reply Address",
                    getattr(interaction, "reply_address", {}) or {},
                ),
                metadata=_key_value_section(
                    "interaction_metadata",
                    "Metadata",
                    getattr(interaction, "metadata", {}) or {},
                ),
                events=_channel_events_table(
                    related_events[:40],
                    total=len(related_events),
                ),
                raw_payload=_payload_from_interaction(interaction),
            )
        )
    return tuple(details)


def _table(
    section_id: str,
    title: str,
    columns: tuple[tuple[str, str], ...],
    rows: tuple[dict[str, Any], ...],
    *,
    total: int | None = None,
    empty_state: str,
) -> OperationsTableSectionModel:
    column_keys = tuple(key for key, _ in columns)
    return OperationsTableSectionModel(
        id=section_id,
        title=title,
        columns=tuple(
            OperationsTableColumnModel(key=key, label=label)
            for key, label in columns
        ),
        rows=tuple(
            OperationsTableRowModel(
                id=_row_id(section_id, index, row),
                cells={
                    key: _text(value)
                    for key, value in row.items()
                    if not key.startswith("_") and key != "tone"
                },
                status=_text(row.get("status"), "-"),
                tone=_text(row.get("tone"), _tone_for_status(_text(row.get("status")))),
            )
            for index, row in enumerate(rows)
        ),
        total=len(rows) if total is None else total,
        view_all_route=f"/operations/channels?tab={section_id}",
        empty_state=empty_state,
    )


def _row_id(section_id: str, index: int, row: dict[str, Any]) -> str:
    for key in (
        "id",
        "interaction_id",
        "runtime_id",
        "event_id",
        "connection_id",
        "account_id",
        "channel_type",
    ):
        value = _text(row.get(key), "")
        if value:
            return value[:120]
    return f"{section_id}:{index}"


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows)


def _connection_event_topics(bindings: tuple[Any, ...]) -> tuple[str, ...]:
    topics: set[str] = set()
    for binding in bindings:
        conversation_id = _text(getattr(binding, "conversation_id", None), "")
        if not conversation_id:
            continue
        topics.add(turn_session_topic(conversation_id))
        topics.add(turn_session_live_topic(conversation_id))
    return tuple(sorted(topics))


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    method = getattr(events_service, "list_event_topics", None)
    if not callable(method):
        return ()
    try:
        value = method()
    except Exception:
        return ()
    return tuple(str(item) for item in value or () if isinstance(item, str) and item)


def _connection_binding_by_conversation(bindings: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for binding in bindings:
        conversation_id = _text(getattr(binding, "conversation_id", None), "")
        if conversation_id:
            result[conversation_id] = binding
    return result


def _group_by_runtime(items: tuple[Any, ...]) -> dict[str, tuple[Any, ...]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        runtime_id = _text(getattr(item, "runtime_id", None), "")
        if runtime_id:
            grouped[runtime_id].append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def _event_matches_runtime(
    event: _ChannelEventRecord,
    runtime_id: str,
    connection_bindings: tuple[Any, ...],
) -> bool:
    if event.runtime_id == runtime_id:
        return True
    connection_ids = {
        _text(getattr(binding, "connection_id", None), "")
        for binding in connection_bindings
    }
    conversation_ids = {
        _text(getattr(binding, "conversation_id", None), "")
        for binding in connection_bindings
    }
    return (
        bool(event.connection_id and event.connection_id in connection_ids)
        or bool(event.conversation_id and event.conversation_id in conversation_ids)
    )


def _events_for_interaction(
    interaction: Any,
    events: tuple[_ChannelEventRecord, ...],
) -> tuple[_ChannelEventRecord, ...]:
    run_id = _text(getattr(interaction, "run_id", None), "")
    session_key = _text(getattr(interaction, "session_key", None), "")
    external_conversation_id = _text(
        getattr(interaction, "external_conversation_id", None),
        "",
    )
    channel_type = _text(getattr(interaction, "channel_type", None), "")
    return tuple(
        event
        for event in events
        if (
            bool(run_id and event.run_id == run_id)
            or bool(session_key and event.conversation_id == session_key)
            or bool(
                external_conversation_id
                and event.conversation_id == external_conversation_id
            )
            or (
                bool(channel_type and event.channel_type == channel_type)
                and bool(run_id and _text(event.payload.get("run_id"), "") == run_id)
            )
        )
    )


def _event_direction(event: _ChannelEventRecord) -> str:
    topic = event.topic
    name = event.event_name.lower()
    if "dead_letter" in topic or "dead_letter" in name or "failed" in name:
        return "Dead Letter"
    if topic.startswith("turn.live."):
        return "Live"
    if topic.startswith("turn.session."):
        return "Observe"
    if ".broadcast." in topic:
        return "Broadcast"
    if ".connection." in topic and topic.endswith(".control"):
        return "Control"
    return "Other"


def _event_status(
    observed: OperationsObservedEvent,
    payload: dict[str, Any],
) -> str:
    for key in ("status", "state", "result"):
        value = _text(payload.get(key), "")
        if value:
            return value
    return observed.status


def _failure_reason(event: _ChannelEventRecord) -> str:
    for key in ("reason", "error", "error_code", "status"):
        value = _text(event.payload.get(key), "")
        if value:
            return value
    if "dead_letter" in event.topic:
        return "dead_letter"
    return "unknown"


def _event_search_text(event: _ChannelEventRecord) -> str:
    values = (
        event.id,
        event.cursor,
        event.topic,
        event.event_name,
        event.status,
        event.channel_type or "",
        event.runtime_id or "",
        event.channel_account_id or "",
        event.connection_id or "",
        event.conversation_id or "",
        event.run_id or "",
        event.trace_id or "",
        _short_json(event.payload, size=400),
    )
    return " ".join(values).lower()


def _interaction_search_text(interaction: Any) -> str:
    values = (
        getattr(interaction, "interaction_id", None),
        getattr(interaction, "channel_type", None),
        getattr(interaction, "channel_account_id", None),
        getattr(interaction, "external_event_id", None),
        getattr(interaction, "external_message_id", None),
        getattr(interaction, "external_conversation_id", None),
        getattr(interaction, "external_user_id", None),
        getattr(interaction, "agent_id", None),
        getattr(interaction, "session_key", None),
        getattr(interaction, "run_id", None),
        getattr(interaction, "status", None),
        getattr(interaction, "last_error", None),
        _short_json(getattr(interaction, "reply_address", {}) or {}, size=400),
        _short_json(getattr(interaction, "metadata", {}) or {}, size=400),
    )
    return " ".join(_text(value, "") for value in values).lower()


def _interaction_tone(interaction: Any) -> str:
    status = _text(getattr(interaction, "status", None), "")
    error = _text(getattr(interaction, "last_error", None), "")
    if error:
        return "danger"
    tone = _tone_for_status(status)
    if tone != "neutral":
        return tone
    normalized = _normalized_filter(status)
    if normalized in {"received", "submitted", "queued", "accepted", "running"}:
        return "info"
    if normalized in {"completed", "delivered"}:
        return "success"
    return "neutral"


def _runtime_status(runtime: Any, *, now: datetime) -> str:
    raw = _text(getattr(runtime, "status", None), "online")
    heartbeat = getattr(runtime, "last_heartbeat_at", None)
    if _seconds_since(heartbeat, now=now) > _STALE_RUNTIME_AFTER_SECONDS:
        return "Stale"
    normalized = raw.strip().lower().replace("_", "-")
    if normalized in {"online", "ready", "healthy"}:
        return "Online"
    if normalized in {"offline", "stopped"}:
        return "Offline"
    if normalized in {"error", "failed"}:
        return "Error"
    return _title(raw)


def _seconds_since(value: Any, *, now: datetime) -> float:
    if not isinstance(value, datetime):
        return 0.0
    return max(0.0, (now - coerce_utc_datetime(value)).total_seconds())


def _age_label(seconds: float) -> str:
    if seconds < 60:
        return f"{round(seconds)}s"
    if seconds < 3600:
        return f"{round(seconds / 60)}m"
    if seconds < 86400:
        return f"{round(seconds / 3600, 1)}h"
    return f"{round(seconds / 86400, 1)}d"


def _trace_route(event: _ChannelEventRecord) -> str:
    if event.trace_id:
        return f"/trace?trace_id={event.trace_id}"
    if event.run_id:
        return f"/trace?run_id={event.run_id}"
    return "-"


def _channel_from_topic(topic: str) -> str | None:
    parts = topic.split(".")
    if len(parts) >= 3 and parts[0] == "channel" and parts[1] in {
        "broadcast",
        "dead_letter",
        "connection",
    }:
        return parts[2]
    return None


def _runtime_from_topic(topic: str) -> str | None:
    marker = ".runtime."
    if marker not in topic:
        return None
    return topic.split(marker, 1)[1].split(".", 1)[0] or None


def _connection_from_topic(topic: str) -> str | None:
    marker = ".connection."
    if marker not in topic:
        return None
    tail = topic.split(marker, 1)[1]
    return tail.split(".", 1)[0] or None


def _account_profile(profile: Any | None, account_id: str) -> Any | None:
    if profile is None:
        return None
    for account in tuple(getattr(profile, "accounts", ()) or ()):
        if _text(getattr(account, "account_id", None), "") == account_id:
            return account
    return None


def _metadata_value(item: Any, key: str) -> Any:
    metadata = getattr(item, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get(key)
    return None


def _payload_from_runtime(runtime: Any) -> dict[str, Any]:
    to_payload = getattr(runtime, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return _display_payload(dict(payload)) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {
        "runtime_id": _text(getattr(runtime, "runtime_id", None)),
        "channel_type": _text(getattr(runtime, "channel_type", None)),
        "service_key": _text(getattr(runtime, "service_key", None)),
        "status": _text(getattr(runtime, "status", None)),
    }


def _payload_from_interaction(interaction: Any) -> dict[str, Any]:
    to_payload = getattr(interaction, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return _display_payload(dict(payload)) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {
        "interaction_id": _text(getattr(interaction, "interaction_id", None)),
        "channel_type": _text(getattr(interaction, "channel_type", None)),
        "channel_account_id": _text(
            getattr(interaction, "channel_account_id", None),
        ),
        "run_id": _text(getattr(interaction, "run_id", None)),
        "session_key": _text(getattr(interaction, "session_key", None)),
        "status": _status_label(_text(getattr(interaction, "status", None))),
        "metadata": _display_payload(dict(getattr(interaction, "metadata", {}) or {})),
    }


def _key_value_section(
    section_id: str,
    title: str,
    values: dict[str, Any],
) -> OperationsKeyValueSectionModel:
    return OperationsKeyValueSectionModel(
        id=section_id,
        title=title,
        items=tuple(
            OperationsKeyValueItemModel(
                _label_from_key(key),
                _text(value),
                _tone_for_status(_text(value), default="neutral"),
            )
            for key, value in values.items()
            if _text(value, "") != ""
        ),
    )


def _capabilities_section(capabilities: Any) -> OperationsKeyValueSectionModel:
    payload = _capabilities_payload(capabilities)
    return OperationsKeyValueSectionModel(
        id="capabilities",
        title="Capabilities",
        items=tuple(
            OperationsKeyValueItemModel(
                _label_from_key(key),
                _text(value),
                "success" if bool(value) else "neutral",
            )
            for key, value in payload.items()
            if key != "metadata"
        ),
    )


def _capabilities_label(capabilities: Any) -> str:
    payload = _capabilities_payload(capabilities)
    enabled = [
        _label_from_key(key)
        for key, value in payload.items()
        if key != "metadata" and bool(value)
    ]
    return ", ".join(enabled) if enabled else "-"


def _capabilities_payload(capabilities: Any) -> dict[str, Any]:
    if capabilities is None:
        return {}
    to_payload = getattr(capabilities, "to_payload", None)
    if callable(to_payload):
        try:
            payload = to_payload()
            return dict(payload) if isinstance(payload, dict) else {}
        except Exception:
            return {}
    return {}


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _short_json(value: Any, *, size: int = 80) -> str:
    text = _safe_json(value)
    if text in {"{}", "[]", "null"}:
        return "-"
    if len(text) <= size:
        return text
    return f"{text[: max(12, size - 8)]}..."


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    return "-"


def _sort_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    return datetime.min.replace(tzinfo=timezone.utc)


def _short_optional(value: Any, *, size: int = 96) -> str:
    text = _text(value, "")
    if not text:
        return "-"
    if len(text) <= size:
        return text
    return f"{text[: max(12, size - 8)]}..."


def _text(value: Any, default: str = "-") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return _join(value)
    if isinstance(value, dict):
        return _short_json(value)
    return str(value)


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _text(value, "")
        if text:
            return text
    return None


def _join(values: Any) -> str:
    items = [_text(value, "") for value in values if _text(value, "")]
    return ", ".join(dict.fromkeys(items)) if items else "-"


def _normalized_filter(value: str) -> str:
    normalized = str(value or "all").strip().lower().replace("_", "-")
    return normalized or "all"


def _status_label(value: str) -> str:
    normalized = _normalized_filter(value)
    if normalized == "all":
        return "-"
    return _title(normalized.replace("-", " "))


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value).replace("_", " ").split())


def _label_from_key(value: str) -> str:
    return _title(value.replace("supports_", ""))


def _display_text(value: Any, default: str = "-") -> str:
    return _text(value, default)


def _display_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _display_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_display_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_display_payload(item) for item in value)
    if isinstance(value, str):
        return value
    return value


def _id_for(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("/", " ")
        .replace(".", " ")
        .replace("-", " ")
        .replace("_", " ")
    ).replace(" ", "_") or "unknown"


def _tone_for_status(value: str, *, default: str = "neutral") -> str:
    text = value.lower()
    if any(token in text for token in ("dead", "failed", "fail", "error", "offline", "blocked")):
        return "danger"
    if any(token in text for token in ("stale", "warning", "pending", "retry", "control")):
        return "warning"
    if any(token in text for token in ("online", "ready", "healthy", "success", "succeeded", "active", "enabled", "matched", "completed", "delivered")):
        return "success"
    if any(token in text for token in ("observe", "live", "broadcast", "info", "intake", "received", "submitted", "accepted", "running", "queued")):
        return "info"
    return default


def _health_label(health: str) -> str:
    return {"healthy": "Healthy", "warning": "Warning", "error": "Error"}.get(
        health,
        "Unknown",
    )


def _health_delta(health: str) -> str:
    return {
        "healthy": "Channel runtime state is queryable",
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def _health_tone(health: str) -> str:
    return {"healthy": "success", "warning": "warning", "error": "danger"}.get(
        health,
        "neutral",
    )


def _dedupe_events(
    events: tuple[_ChannelEventRecord, ...],
) -> tuple[_ChannelEventRecord, ...]:
    by_id: dict[str, _ChannelEventRecord] = {}
    for event in sorted(events, key=lambda item: item.occurred_at):
        by_id[event.id] = event
    return tuple(
        sorted(by_id.values(), key=lambda item: item.occurred_at, reverse=True)
    )
