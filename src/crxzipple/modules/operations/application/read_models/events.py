from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
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
    OperationsKeyValueSectionModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.shared.time import format_datetime_utc

_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0
_OBSERVER_RUNTIME_STALE_AFTER_SECONDS = 30.0
_MAX_TOPIC_ROWS = 300
_MAX_RECENT_TOPIC_SCAN = 300


@dataclass(frozen=True, slots=True)
class EventsOperationsQuery:
    status: str = "all"
    topic_prefix: str = ""
    search: str = ""
    owner: str = "all"
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class EventsEventDetailModel:
    event_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    payload: dict[str, Any]
    trace: dict[str, Any]
    contracts: OperationsTableSectionModel
    subscriptions: OperationsTableSectionModel


@dataclass(frozen=True, slots=True)
class EventsOperationsPage:
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
    events_over_time: OperationsChartSectionModel
    events_by_surface: OperationsChartSectionModel
    owners_by_volume: OperationsTableSectionModel
    contract_compatibility: OperationsKeyValueSectionModel
    recent_events: OperationsTableSectionModel
    consumer_health: OperationsTableSectionModel
    observer_health: OperationsTableSectionModel
    observer_lag: OperationsTableSectionModel
    topics: OperationsTableSectionModel
    subscriptions: OperationsTableSectionModel
    observer_coverage: OperationsTableSectionModel
    dead_letters: OperationsTableSectionModel
    contracts: OperationsTableSectionModel
    routes: OperationsTableSectionModel
    event_details: tuple[EventsEventDetailModel, ...]


@dataclass(slots=True)
class EventsOperationsReadModelProvider:
    events_service: Any | None
    event_contract_registry: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None
    operations_observer_runtime: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(EventsOperationsQuery(limit=50))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.subscriptions),
            lane_locks=_overview_rows(page.owners_by_volume),
            executor=_overview_rows(page.observer_coverage),
            actions=page.actions,
        )

    def page(
        self,
        query: EventsOperationsQuery | None = None,
    ) -> EventsOperationsPage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        topic_contracts = _safe_list(
            self.event_contract_registry,
            "list_topic_contracts",
        )
        route_contracts = _safe_list(
            self.event_contract_registry,
            "list_route_contracts",
        )
        definitions = _safe_list(
            self.event_definition_registry,
            "list_definitions",
        )
        surfaces = _safe_list(self.event_definition_registry, "list_surfaces")
        observer_definitions = _safe_list(
            self.event_definition_registry,
            "list_observers",
        )
        observer_subscriptions = _safe_observer_subscriptions(
            self.operations_observer_runtime,
        )

        live_topics = _list_live_topics(
            self.events_service,
            topic_prefix=query.topic_prefix,
        )
        subscription_cursors = _safe_subscription_cursors(self.events_service)
        source_topics = {
            state.source_topic
            for state in subscription_cursors
            if _text(getattr(state, "source_topic", None))
        }
        source_topics.update(
            subscription.source_topic
            for subscription in observer_subscriptions
            if _text(getattr(subscription, "source_topic", None))
        )
        visible_topics = _prioritized_topics(
            live_topics=live_topics,
            source_topics=source_topics,
            limit=_MAX_TOPIC_ROWS,
        )
        recent_scan_topics = _prioritized_topics(
            live_topics=live_topics,
            source_topics=source_topics,
            limit=_MAX_RECENT_TOPIC_SCAN,
        )
        snapshot_topics = tuple(sorted({*visible_topics, *source_topics}))
        latest_cursors = {
            topic: _safe_snapshot(self.events_service, topic) for topic in snapshot_topics
        }
        subscription_states = _subscription_states(
            subscription_cursors,
            latest_cursors=latest_cursors,
            now=now,
            registry=self.event_contract_registry,
        )
        observer_states = _observer_subscription_states(
            observer_subscriptions,
            subscription_cursors=subscription_cursors,
            latest_cursors=latest_cursors,
            now=now,
            registry=self.event_contract_registry,
        )
        observer_runtime_states = _observer_runtime_states(
            self.operations_observation,
            runtime=self.operations_observer_runtime,
            now=now,
        )
        all_recent_events = _recent_event_summaries(
            self.events_service,
            topics=recent_scan_topics,
            definition_registry=self.event_definition_registry,
            contract_registry=self.event_contract_registry,
            limit=max(query.limit + query.offset, query.limit),
        )
        filtered_events = _filter_events(all_recent_events, query)
        visible_events = filtered_events[query.offset : query.offset + query.limit]

        live_topic_rows = _topic_rows(
            visible_topics,
            latest_cursors=latest_cursors,
            subscription_states=subscription_states,
            recent_events=all_recent_events,
            registry=self.event_contract_registry,
        )
        uncovered_topics = _uncovered_topics(
            live_topics,
            registry=self.event_contract_registry,
        )
        uncovered_events = [
            item
            for item in all_recent_events
            if item["contract_status"] == "uncovered"
        ]
        dead_letter_events = _dead_letter_events(all_recent_events)
        lagging_count = sum(1 for item in subscription_states if item["lagging"])
        stuck_count = sum(1 for item in subscription_states if item["stuck"])
        observer_lagging_count = sum(1 for item in observer_states if item["lagging"])
        observer_stuck_count = sum(1 for item in observer_states if item["stuck"])
        observer_runtime_lagging_count = sum(
            1 for item in observer_runtime_states if item["lagging"]
        )
        observer_runtime_stuck_count = sum(
            1 for item in observer_runtime_states if item["stuck"]
        )
        health = _health(
            events_service_available=self.events_service is not None,
            stuck_count=(
                stuck_count + observer_stuck_count + observer_runtime_stuck_count
            ),
            lagging_count=(
                lagging_count
                + observer_lagging_count
                + observer_runtime_lagging_count
            ),
            dead_letter_count=len(dead_letter_events),
            uncovered_topic_count=len(uncovered_topics),
        )

        return EventsOperationsPage(
            module="events",
            title="Events",
            subtitle="聚合事件总线、事件合同、订阅游标、观察者消费与死信状态。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Events operator",
                can_operate=True,
                scope="events",
            ),
            metrics=_metrics(
                health=health,
                live_topics=live_topics,
                definitions=definitions,
                subscriptions=subscription_states,
                recent_events=all_recent_events,
                dead_letters=dead_letter_events,
                observer_states=observer_states,
                observer_runtime_states=observer_runtime_states,
            ),
            tabs=_tabs(
                recent_count=len(filtered_events),
                topic_count=len(live_topics),
                subscription_count=len(subscription_states),
                observer_definition_count=len(observer_definitions),
                contract_count=len(topic_contracts),
                route_count=len(route_contracts),
                observer_count=len(observer_states) + len(observer_runtime_states),
                observer_problem_count=(
                    observer_lagging_count
                    + observer_stuck_count
                    + observer_runtime_lagging_count
                    + observer_runtime_stuck_count
                ),
                dead_letter_count=len(dead_letter_events),
                mapping_count=lagging_count + stuck_count,
            ),
            active_tab="recent",
            actions=_actions(),
            events_over_time=_events_over_time(all_recent_events),
            events_by_surface=_events_by_surface(all_recent_events),
            owners_by_volume=_owners_by_volume(
                all_recent_events,
                definitions=definitions,
                surfaces=surfaces,
                subscriptions=subscription_states,
            ),
            contract_compatibility=_contract_compatibility(
                live_topics=live_topics,
                topic_contracts=topic_contracts,
                route_contracts=route_contracts,
                definitions=definitions,
                surfaces=surfaces,
                observer_definitions=observer_definitions,
                subscriptions=subscription_states,
                uncovered_topics=uncovered_topics,
                uncovered_events=uncovered_events,
            ),
            recent_events=_recent_events_table(
                visible_events,
                total=len(filtered_events),
                query=query,
            ),
            consumer_health=_consumer_health_table(subscription_states),
            observer_health=_observer_health_table(
                observer_states,
                runtime_states=observer_runtime_states,
                definitions=definitions,
            ),
            observer_lag=_observer_lag_table(
                subscription_states,
                all_recent_events,
            ),
            topics=_topics_table(live_topic_rows, total_count=len(live_topics)),
            subscriptions=_subscriptions_table(subscription_states, query=query),
            observer_coverage=_observer_coverage_table(
                observer_definitions,
                all_recent_events,
            ),
            dead_letters=_dead_letters_table(dead_letter_events),
            contracts=_contracts_table(topic_contracts, live_topics),
            routes=_routes_table(route_contracts, subscription_states),
            event_details=_event_details(
                visible_events,
                subscription_states=subscription_states,
            ),
        )


def _normalize_query(query: EventsOperationsQuery | None) -> EventsOperationsQuery:
    if query is None:
        return EventsOperationsQuery()
    status = (query.status or "all").strip().lower() or "all"
    allowed_statuses = {
        "all",
        "matched",
        "uncovered",
        "definition_only",
        "topic_contract_only",
        "dead_letter",
        "at_head",
        "lagging",
        "stuck",
    }
    if status not in allowed_statuses:
        status = "all"
    owner = (query.owner or "all").strip().lower() or "all"
    return EventsOperationsQuery(
        status=status,
        topic_prefix=(query.topic_prefix or "").strip(),
        search=(query.search or "").strip(),
        owner=owner,
        limit=max(1, min(int(query.limit or 80), 200)),
        offset=max(0, int(query.offset or 0)),
    )


def _metrics(
    *,
    health: str,
    live_topics: tuple[str, ...],
    definitions: tuple[Any, ...],
    subscriptions: list[dict[str, Any]],
    recent_events: list[dict[str, Any]],
    dead_letters: list[dict[str, Any]],
    observer_states: list[dict[str, Any]],
    observer_runtime_states: list[dict[str, Any]],
) -> tuple[MetricCardModel, ...]:
    at_head = sum(1 for item in subscriptions if item["at_head"])
    lagging = sum(1 for item in subscriptions if item["lagging"])
    stuck = sum(1 for item in subscriptions if item["stuck"])
    observer_stuck = sum(1 for item in observer_states if item["stuck"])
    observer_lagging = sum(1 for item in observer_states if item["lagging"])
    observer_runtime_active = sum(
        1 for item in observer_runtime_states if item["active"]
    )
    observer_runtime_stuck = sum(
        1 for item in observer_runtime_states if item["stuck"]
    )
    observer_runtime_lagging = sum(
        1 for item in observer_runtime_states if item["lagging"]
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
            id="topics",
            label="Live Topics",
            value=str(len(live_topics)),
            delta="event bus topics",
            tone="info" if live_topics else "neutral",
        ),
        MetricCardModel(
            id="recent_events",
            label="Recent Events",
            value=str(len(recent_events)),
            delta="retained bus records",
            tone="info" if recent_events else "neutral",
        ),
        MetricCardModel(
            id="definitions",
            label="Definitions",
            value=str(len(definitions)),
            delta="registered event definitions",
            tone="success" if definitions else "warning",
        ),
        MetricCardModel(
            id="subscriptions",
            label="Subscriptions",
            value=str(len(subscriptions)),
            delta=f"{at_head} at head",
            tone="info" if subscriptions else "neutral",
        ),
        MetricCardModel(
            id="lagging",
            label="Lagging",
            value=str(lagging),
            delta=f"{stuck} stuck",
            tone="danger" if stuck else "warning" if lagging else "success",
        ),
        MetricCardModel(
            id="dead_letters",
            label="Dead Letters",
            value=str(len(dead_letters)),
            delta="recent dead-letter records",
            tone="danger" if dead_letters else "success",
        ),
        MetricCardModel(
            id="observers",
            label="Observers",
            value=str(observer_runtime_active),
            delta=(
                f"{len(observer_runtime_states)} runtimes / "
                f"{len(observer_states)} subscriptions"
            ),
            tone=(
                "danger"
                if observer_stuck or observer_runtime_stuck
                else "warning"
                if observer_lagging
                or observer_runtime_lagging
                or not observer_runtime_states
                else "info"
                if observer_states or observer_runtime_states
                else "neutral"
            ),
        ),
    )


def _tabs(
    *,
    recent_count: int,
    topic_count: int,
    subscription_count: int,
    observer_definition_count: int,
    contract_count: int,
    route_count: int,
    observer_count: int,
    observer_problem_count: int,
    dead_letter_count: int,
    mapping_count: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("recent", "Recent Events", recent_count),
        OperationsTabModel("topics", "Topics", topic_count),
        OperationsTabModel("subscriptions", "Subscriptions", subscription_count),
        OperationsTabModel(
            "observer",
            "Observer Health",
            observer_count,
            "warning" if observer_problem_count else "neutral",
        ),
        OperationsTabModel(
            "observer_coverage",
            "Observer Coverage",
            observer_definition_count,
        ),
        OperationsTabModel("contracts", "Contracts", contract_count),
        OperationsTabModel("routes", "Routes", route_count),
        OperationsTabModel(
            "dead_letters",
            "Dead Letters",
            dead_letter_count,
            "danger" if dead_letter_count else "neutral",
        ),
        OperationsTabModel(
            "observer_lag",
            "Observer Lag",
            mapping_count,
            "warning" if mapping_count else "neutral",
        ),
        OperationsTabModel("owners", "Owners", None),
    )


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_trace",
            label="Open Trace",
            owner="events",
            method="GET",
            endpoint="/trace",
        ),
        RuntimeActionModel(
            id="inspect_topic",
            label="Inspect Topic",
            owner="events",
            method="GET",
            endpoint="/events/topics/{topic}/diagnostics",
        ),
        RuntimeActionModel(
            id="inspect_subscription",
            label="Inspect Subscription",
            owner="events",
            method="GET",
            endpoint="/events/subscriptions/diagnostics",
        ),
        RuntimeActionModel(
            id="advance_stuck_subscriptions",
            label="Advance Stuck Subscriptions",
            owner="events",
            risk="dangerous",
            requires_confirmation=True,
            reason_required=True,
            method="POST",
            endpoint="/operations/events/subscriptions/advance-to-head",
        ),
        RuntimeActionModel(
            id="advance_stuck_observers",
            label="Advance Stuck Observers",
            owner="events",
            risk="dangerous",
            requires_confirmation=True,
            reason_required=True,
            method="POST",
            endpoint="/operations/events/observers/advance-to-head",
        ),
    )


def _events_over_time(
    events: list[dict[str, Any]],
) -> OperationsChartSectionModel:
    counts = Counter(_display(item["kind"]) for item in events)
    segments = tuple(
        OperationsChartSegmentModel(
            id=_slug(kind),
            label=kind.title(),
            value=count,
            tone=_kind_tone(kind),
        )
        for kind, count in counts.most_common()
    )
    return OperationsChartSectionModel(
        id="events_over_time",
        title="Events by Kind",
        kind="bar",
        total=len(events),
        segments=segments,
    )


def _events_by_surface(
    events: list[dict[str, Any]],
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    for item in events:
        surfaces = item.get("surface_ids")
        if isinstance(surfaces, tuple) and surfaces:
            counts.update(surfaces)
        else:
            counts[_display(item.get("owner"))] += 1
    segments = tuple(
        OperationsChartSegmentModel(
            id=_slug(label),
            label=label,
            value=count,
            tone=_tone_for_index(index),
        )
        for index, (label, count) in enumerate(counts.most_common(8))
    )
    return OperationsChartSectionModel(
        id="events_by_surface",
        title="Events by Surface",
        kind="donut",
        total=sum(counts.values()),
        segments=segments,
    )


def _owners_by_volume(
    events: list[dict[str, Any]],
    *,
    definitions: tuple[Any, ...],
    surfaces: tuple[Any, ...],
    subscriptions: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    event_counts = Counter(_display(item.get("owner")) for item in events)
    definition_counts = Counter(_display(getattr(item, "owner", None)) for item in definitions)
    surface_counts = Counter(_display(getattr(item, "owner", None)) for item in surfaces)
    subscription_counts = Counter(
        _owner_from_subscription(item) for item in subscriptions
    )
    owners = sorted(
        {
            owner
            for owner in (
                set(event_counts)
                | set(definition_counts)
                | set(surface_counts)
                | set(subscription_counts)
            )
            if owner != "-"
        },
        key=lambda owner: (
            -event_counts[owner],
            -definition_counts[owner],
            owner,
        ),
    )
    rows = tuple(
        OperationsTableRowModel(
            id=owner,
            cells={
                "owner": owner,
                "events": str(event_counts[owner]),
                "definitions": str(definition_counts[owner]),
                "surfaces": str(surface_counts[owner]),
                "subscriptions": str(subscription_counts[owner]),
            },
            status="active" if event_counts[owner] else "registered",
            tone="info" if event_counts[owner] else "neutral",
        )
        for owner in owners[:40]
    )
    return OperationsTableSectionModel(
        id="owners_by_volume",
        title="Owners by Volume",
        columns=_columns(
            ("owner", "Owner"),
            ("events", "Events"),
            ("definitions", "Definitions"),
            ("surfaces", "Surfaces"),
            ("subscriptions", "Subscriptions"),
        ),
        rows=rows,
        total=len(owners),
        view_all_route="/operations/events?tab=owners",
        empty_state="No event owners observed.",
    )


def _contract_compatibility(
    *,
    live_topics: tuple[str, ...],
    topic_contracts: tuple[Any, ...],
    route_contracts: tuple[Any, ...],
    definitions: tuple[Any, ...],
    surfaces: tuple[Any, ...],
    observer_definitions: tuple[Any, ...],
    subscriptions: list[dict[str, Any]],
    uncovered_topics: tuple[str, ...],
    uncovered_events: list[dict[str, Any]],
) -> OperationsKeyValueSectionModel:
    lagging = sum(1 for item in subscriptions if item["lagging"])
    stuck = sum(1 for item in subscriptions if item["stuck"])
    return OperationsKeyValueSectionModel(
        id="contract_compatibility",
        title="Contract Compatibility",
        items=(
            OperationsKeyValueItemModel("Live Topics", str(len(live_topics)), "info"),
            OperationsKeyValueItemModel(
                "Topic Contracts",
                str(len(topic_contracts)),
                "success" if topic_contracts else "warning",
            ),
            OperationsKeyValueItemModel(
                "Route Contracts",
                str(len(route_contracts)),
                "success" if route_contracts else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Definitions",
                str(len(definitions)),
                "success" if definitions else "warning",
            ),
            OperationsKeyValueItemModel("Surfaces", str(len(surfaces)), "info"),
            OperationsKeyValueItemModel(
                "Observer Definitions",
                str(len(observer_definitions)),
                "info",
            ),
            OperationsKeyValueItemModel(
                "Uncovered Topics",
                str(len(uncovered_topics)),
                "warning" if uncovered_topics else "success",
            ),
            OperationsKeyValueItemModel(
                "Uncovered Events",
                str(len(uncovered_events)),
                "warning" if uncovered_events else "success",
            ),
            OperationsKeyValueItemModel(
                "Lagging Subscriptions",
                str(lagging),
                "warning" if lagging else "success",
            ),
            OperationsKeyValueItemModel(
                "Stuck Subscriptions",
                str(stuck),
                "danger" if stuck else "success",
            ),
        ),
    )


def _recent_events_table(
    events: list[dict[str, Any]],
    *,
    total: int,
    query: EventsOperationsQuery,
) -> OperationsTableSectionModel:
    rows = tuple(_recent_event_row(item) for item in events)
    return OperationsTableSectionModel(
        id="recent_events",
        title="Recent Events",
        columns=_columns(
            ("time", "Time"),
            ("owner", "Owner"),
            ("event", "Event"),
            ("kind", "Kind"),
            ("topic", "Topic"),
            ("cursor", "Cursor"),
            ("status", "Status"),
            ("contract", "Contract"),
            ("trace", "Trace"),
            ("run", "Run ID / Entity"),
        ),
        rows=rows,
        total=total,
        view_all_route="/operations/events?tab=recent",
        empty_state=_recent_empty_state(query),
    )


def _recent_event_row(item: dict[str, Any]) -> OperationsTableRowModel:
    return OperationsTableRowModel(
        id=_event_row_id(item),
        cells={
            "time": _display(item.get("created_at")),
            "owner": _display(item.get("owner")),
            "event": _display(item.get("event_name")),
            "kind": _display(item.get("kind")),
            "topic": _display(item.get("topic")),
            "cursor": _display(item.get("cursor")),
            "event_id": _display(item.get("event_id")),
            "status": _contract_status_label(_display(item.get("contract_status"))),
            "contract": _display(item.get("contract_label")),
            "trace": _display(item.get("trace_id")),
            "run": _display(item.get("run_id") or item.get("entity_id")),
            "route": _trace_route(item),
            "trace_route": _trace_route(item),
        },
        status=_display(item.get("contract_status")),
        tone=_event_tone(item),
    )


def _consumer_health_table(
    subscription_states: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=_display(item.get("subscription_id")),
            cells={
                "subscription": _display(item.get("subscription_id")),
                "source_topic": _display(item.get("source_topic")),
                "status": _display(item.get("status")),
                "lag": str(item.get("lag") or 0),
                "cursor": _display(item.get("cursor")),
                "latest_cursor": _display(item.get("latest_cursor")),
                "updated_at": _display(item.get("updated_at")),
                "contract": _display(item.get("contract_label")),
            },
            status=_display(item.get("status")).lower().replace(" ", "_"),
            tone=_subscription_tone(item),
        )
        for item in sorted(subscription_states, key=_subscription_sort_key)
    )
    return OperationsTableSectionModel(
        id="consumer_health",
        title="Consumer Health",
        columns=_columns(
            ("subscription", "Subscription"),
            ("source_topic", "Source Topic"),
            ("status", "Status"),
            ("lag", "Lag"),
            ("cursor", "Cursor"),
            ("latest_cursor", "Latest Cursor"),
            ("updated_at", "Updated At"),
            ("contract", "Contract"),
        ),
        rows=rows,
        total=len(subscription_states),
        view_all_route="/operations/events?tab=subscriptions",
        empty_state="No subscription cursors observed.",
    )


def _observer_health_table(
    observer_states: list[dict[str, Any]],
    *,
    runtime_states: list[dict[str, Any]],
    definitions: tuple[Any, ...],
) -> OperationsTableSectionModel:
    definitions_by_event_name = {
        _display(getattr(definition, "event_name", None)): definition
        for definition in definitions
    }
    rows = []
    for item in sorted(runtime_states, key=_observer_runtime_sort_key):
        rows.append(
            OperationsTableRowModel(
                id=f"runtime:{item['runtime_name']}:{item['worker_id']}",
                cells={
                    "runtime_key": _display(item.get("runtime_name")),
                    "worker_id": _display(item.get("worker_id")),
                    "event": "Observer Runtime",
                    "module": "operations",
                    "owner": "operations",
                    "status": _display(item.get("status")),
                    "lag": "-",
                    "updated_at": _display(item.get("last_seen_at")),
                    "subscriptions": str(item.get("subscription_count") or 0),
                },
                status=_display(item.get("status")).lower().replace(" ", "_"),
                tone=_display(item.get("tone"), "neutral"),
            )
        )
    for item in sorted(observer_states, key=_subscription_sort_key):
        event_name = _observer_event_name(item)
        definition = definitions_by_event_name.get(event_name)
        rows.append(
            OperationsTableRowModel(
                id=f"{item['subscription_id']}:{item['source_topic']}",
                cells={
                    "runtime_key": "-",
                    "worker_id": "-",
                    "event": event_name,
                    "module": _display(getattr(definition, "module", None)),
                    "owner": _display(getattr(definition, "owner", None)),
                    "subscription": _display(item.get("subscription_id")),
                    "source_topic": _display(item.get("source_topic")),
                    "status": _display(item.get("status")),
                    "lag": str(item.get("lag") or 0),
                    "cursor": _display(item.get("cursor")),
                    "latest_cursor": _display(item.get("latest_cursor")),
                    "updated_at": _display(item.get("updated_at")),
                    "contract": _display(item.get("contract_label")),
                },
                status=_display(item.get("status")).lower().replace(" ", "_"),
                tone=_subscription_tone(item),
            )
        )
    return OperationsTableSectionModel(
        id="observer_health",
        title="Observer Health",
        columns=_columns(
            ("runtime_key", "Runtime Key"),
            ("event", "Event"),
            ("owner", "Owner"),
            ("status", "Status"),
            ("lag", "Lag"),
            ("updated_at", "Last Seen"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=observer",
        empty_state="No operations observer subscriptions registered.",
    )


def _observer_lag_table(
    subscription_states: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for item in sorted(subscription_states, key=_subscription_sort_key):
        if not item["lagging"] and not item["stuck"]:
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"subscription:{item['subscription_id']}:{item['source_topic']}",
                cells={
                    "source": _display(item.get("source_topic")),
                    "target": _display(item.get("subscription_id")),
                    "reason": "stuck_subscription" if item["stuck"] else "lagging_subscription",
                    "count": str(item.get("lag") or 0),
                    "last": _display(item.get("updated_at")),
                },
                status="stuck" if item["stuck"] else "lagging",
                tone="danger" if item["stuck"] else "warning",
            )
        )
    for item in events:
        if not _looks_like_mapping_failure(item):
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"event:{_event_row_id(item)}",
                cells={
                    "source": _display(item.get("topic")),
                    "target": _display(item.get("event_name")),
                    "reason": _display(item.get("status")),
                    "count": "1",
                    "last": _display(item.get("created_at")),
                },
                status="failed",
                tone="danger",
            )
        )
    return OperationsTableSectionModel(
        id="observer_lag",
        title="Observer Lag",
        columns=_columns(
            ("source", "Source"),
            ("target", "Target"),
            ("reason", "Reason"),
            ("count", "Count"),
            ("last", "Last Seen"),
        ),
        rows=tuple(rows[:80]),
        total=len(rows),
        view_all_route="/operations/events?tab=observer_lag",
        empty_state="No observer lag or failed observer records observed.",
    )


def _topics_table(
    rows: list[OperationsTableRowModel],
    *,
    total_count: int,
) -> OperationsTableSectionModel:
    return OperationsTableSectionModel(
        id="topics",
        title="Topics",
        columns=_columns(
            ("topic", "Topic"),
            ("latest_cursor", "Latest Cursor"),
            ("recent_events", "Recent Events"),
            ("subscriptions", "Subscriptions"),
            ("contract", "Contract"),
            ("routes", "Routes"),
            ("latest_event", "Latest Event"),
            ("kinds", "Kinds"),
        ),
        rows=tuple(rows),
        total=total_count,
        view_all_route="/operations/events?tab=topics",
        empty_state="No event topics observed.",
    )


def _subscriptions_table(
    subscription_states: list[dict[str, Any]],
    *,
    query: EventsOperationsQuery,
) -> OperationsTableSectionModel:
    states = subscription_states
    if query.status in {"at_head", "lagging", "stuck"}:
        states = [item for item in states if item[query.status]]
    rows = tuple(
        OperationsTableRowModel(
            id=f"{item['subscription_id']}:{item['source_topic']}",
            cells={
                "subscription": _display(item.get("subscription_id")),
                "source_topic": _display(item.get("source_topic")),
                "cursor": _display(item.get("cursor")),
                "latest_cursor": _display(item.get("latest_cursor")),
                "lag": str(item.get("lag") or 0),
                "status": _display(item.get("status")),
                "updated_at": _display(item.get("updated_at")),
                "seconds_since_update": str(item.get("seconds_since_update") or 0),
                "contracts": _display(item.get("contract_label")),
                "routes": _display(item.get("route_label")),
            },
            status=_display(item.get("status")).lower().replace(" ", "_"),
            tone=_subscription_tone(item),
        )
        for item in sorted(states, key=_subscription_sort_key)
    )
    return OperationsTableSectionModel(
        id="subscriptions",
        title="Subscriptions",
        columns=_columns(
            ("subscription", "Subscription"),
            ("source_topic", "Source Topic"),
            ("cursor", "Cursor"),
            ("latest_cursor", "Latest Cursor"),
            ("lag", "Lag"),
            ("status", "Status"),
            ("updated_at", "Updated At"),
            ("seconds_since_update", "Seconds Since Update"),
            ("contracts", "Contracts"),
            ("routes", "Routes"),
        ),
        rows=rows,
        total=len(states),
        view_all_route="/operations/events?tab=subscriptions",
        empty_state="No subscription cursors observed.",
    )


def _observer_coverage_table(
    observer_definitions: tuple[Any, ...],
    events: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    event_counts = Counter(_display(item.get("event_name")) for item in events)
    rows = []
    for definition in observer_definitions:
        source_names = tuple(getattr(definition, "source_event_names", ()) or ())
        observed = sum(event_counts[name] for name in source_names)
        rows.append(
            OperationsTableRowModel(
                id=_display(getattr(definition, "observer_id", None)),
                cells={
                    "observer": _display(getattr(definition, "observer_id", None)),
                    "owner": _display(getattr(definition, "owner", None)),
                    "source_events": _join(source_names),
                    "output_definitions": _join(
                        getattr(definition, "output_definition_ids", ()) or ()
                    ),
                    "observed_inputs": str(observed),
                    "status": "Registered",
                },
                status="registered",
                tone="success",
            )
        )
    return OperationsTableSectionModel(
        id="observer_coverage",
        title="Observer Coverage",
        columns=_columns(
            ("observer", "Observer"),
            ("owner", "Owner"),
            ("source_events", "Source Events"),
            ("output_definitions", "Output Definitions"),
            ("observed_inputs", "Observed Inputs"),
            ("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=observer_coverage",
        empty_state="No observer coverage definitions registered.",
    )


def _dead_letters_table(
    events: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=_event_row_id(item),
            cells={
                "time": _display(item.get("created_at")),
                "event": _display(item.get("event_name")),
                "topic": _display(item.get("topic")),
                "cursor": _display(item.get("cursor")),
                "owner": _display(item.get("owner")),
                "reason": _display(item.get("status")),
                "trace": _display(item.get("trace_id")),
            },
            status="dead_letter",
            tone="danger",
        )
        for item in events[:80]
    )
    return OperationsTableSectionModel(
        id="dead_letters",
        title="Dead Letters",
        columns=_columns(
            ("time", "Time"),
            ("event", "Event"),
            ("topic", "Topic"),
            ("cursor", "Cursor"),
            ("owner", "Owner"),
            ("reason", "Reason"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        view_all_route="/operations/events?tab=dead_letters",
        empty_state="No dead-letter events observed.",
    )


def _contracts_table(
    topic_contracts: tuple[Any, ...],
    live_topics: tuple[str, ...],
) -> OperationsTableSectionModel:
    rows = []
    for contract in topic_contracts:
        contract_id = _display(getattr(contract, "contract_id", None))
        matches = [
            topic
            for topic in live_topics
            if _contract_matches_topic(contract, topic)
        ]
        rows.append(
            OperationsTableRowModel(
                id=contract_id,
                cells={
                    "contract": contract_id,
                    "topic_pattern": _display(getattr(contract, "topic_pattern", None)),
                    "owner": _display(getattr(contract, "owner", None)),
                    "kinds": _join(getattr(contract, "kinds", ()) or ()),
                    "producers": _join(getattr(contract, "producers", ()) or ()),
                    "consumers": _join(getattr(contract, "consumers", ()) or ()),
                    "durability": _display(getattr(contract, "durability", None)),
                    "live_matches": str(len(matches)),
                },
                status="active" if matches else "registered",
                tone="success" if matches else "neutral",
            )
        )
    return OperationsTableSectionModel(
        id="contracts",
        title="Contracts",
        columns=_columns(
            ("contract", "Contract"),
            ("topic_pattern", "Topic Pattern"),
            ("owner", "Owner"),
            ("kinds", "Kinds"),
            ("producers", "Producers"),
            ("consumers", "Consumers"),
            ("durability", "Durability"),
            ("live_matches", "Live Matches"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=contracts",
        empty_state="No topic contracts registered.",
    )


def _routes_table(
    route_contracts: tuple[Any, ...],
    subscription_states: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = []
    for contract in route_contracts:
        contract_id = _display(getattr(contract, "contract_id", None))
        source_pattern = _display(getattr(contract, "source_topic_pattern", None))
        subscription_matches = [
            item
            for item in subscription_states
            if _pattern_matches(source_pattern, _display(item.get("source_topic")))
        ]
        rows.append(
            OperationsTableRowModel(
                id=contract_id,
                cells={
                    "route": contract_id,
                    "source_topic": source_pattern,
                    "target_topic": _display(
                        getattr(contract, "target_topic_pattern", None)
                    ),
                    "owner": _display(getattr(contract, "owner", None)),
                    "observer": _display(getattr(contract, "observer", None)),
                    "source_kinds": _join(getattr(contract, "source_kinds", ()) or ()),
                    "target_kind": _display(getattr(contract, "target_kind", None)),
                    "subscriptions": str(len(subscription_matches)),
                },
                status="active" if subscription_matches else "registered",
                tone="info" if subscription_matches else "neutral",
            )
        )
    return OperationsTableSectionModel(
        id="routes",
        title="Routes",
        columns=_columns(
            ("route", "Route"),
            ("source_topic", "Source Topic"),
            ("target_topic", "Target Topic"),
            ("owner", "Owner"),
            ("observer", "Observer"),
            ("source_kinds", "Source Kinds"),
            ("target_kind", "Target Kind"),
            ("subscriptions", "Subscriptions"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=routes",
        empty_state="No route contracts registered.",
    )


def _event_details(
    events: list[dict[str, Any]],
    *,
    subscription_states: list[dict[str, Any]],
) -> tuple[EventsEventDetailModel, ...]:
    details: list[EventsEventDetailModel] = []
    for item in events[:50]:
        topic = _display(item.get("topic"))
        matching_subscriptions = [
            state for state in subscription_states if state.get("source_topic") == topic
        ]
        details.append(
            EventsEventDetailModel(
                event_id=_display(item.get("event_id")),
                title=_display(item.get("event_name")),
                status=_contract_status_label(_display(item.get("contract_status"))),
                tone=_event_tone(item),
                summary=(
                    OperationsKeyValueItemModel("Time", _display(item.get("created_at"))),
                    OperationsKeyValueItemModel("Topic", topic),
                    OperationsKeyValueItemModel("Cursor", _display(item.get("cursor"))),
                    OperationsKeyValueItemModel("Owner", _display(item.get("owner"))),
                    OperationsKeyValueItemModel("Kind", _display(item.get("kind"))),
                    OperationsKeyValueItemModel(
                        "Contract",
                        _display(item.get("contract_label")),
                        _event_tone(item),
                    ),
                    OperationsKeyValueItemModel(
                        "Run ID",
                        _display(item.get("run_id") or item.get("entity_id")),
                    ),
                    OperationsKeyValueItemModel("Trace", _display(item.get("trace_id"))),
                ),
                payload=_as_dict(item.get("payload")),
                trace=_as_dict(item.get("trace")),
                contracts=_detail_contracts_table(item),
                subscriptions=_detail_subscriptions_table(matching_subscriptions),
            )
        )
    return tuple(details)


def _detail_contracts_table(item: dict[str, Any]) -> OperationsTableSectionModel:
    rows = []
    for index, match in enumerate(_as_tuple(item.get("contract_matches"))):
        contract = _as_dict(match.get("contract") if isinstance(match, dict) else None)
        rows.append(
            OperationsTableRowModel(
                id=f"topic:{index}:{_display(contract.get('contract_id'))}",
                cells={
                    "kind": "Topic",
                    "contract": _display(contract.get("contract_id")),
                    "owner": _display(contract.get("owner")),
                    "pattern": _display(contract.get("topic_pattern")),
                    "direction": "-",
                },
                status="matched",
                tone="success",
            )
        )
    for index, match in enumerate(_as_tuple(item.get("route_matches"))):
        contract = _as_dict(match.get("contract") if isinstance(match, dict) else None)
        rows.append(
            OperationsTableRowModel(
                id=f"route:{index}:{_display(contract.get('contract_id'))}",
                cells={
                    "kind": "Route",
                    "contract": _display(contract.get("contract_id")),
                    "owner": _display(contract.get("owner")),
                    "pattern": _display(contract.get("source_topic_pattern")),
                    "direction": _display(match.get("direction") if isinstance(match, dict) else None),
                },
                status="matched",
                tone="info",
            )
        )
    return OperationsTableSectionModel(
        id="event_contracts",
        title="Event Contracts",
        columns=_columns(
            ("kind", "Kind"),
            ("contract", "Contract"),
            ("owner", "Owner"),
            ("pattern", "Pattern"),
            ("direction", "Direction"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No contract matched this event.",
    )


def _detail_subscriptions_table(
    states: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=f"{item['subscription_id']}:{item['source_topic']}",
            cells={
                "subscription": _display(item.get("subscription_id")),
                "status": _display(item.get("status")),
                "cursor": _display(item.get("cursor")),
                "latest_cursor": _display(item.get("latest_cursor")),
                "lag": str(item.get("lag") or 0),
            },
            status=_display(item.get("status")).lower().replace(" ", "_"),
            tone=_subscription_tone(item),
        )
        for item in states
    )
    return OperationsTableSectionModel(
        id="event_subscriptions",
        title="Event Subscriptions",
        columns=_columns(
            ("subscription", "Subscription"),
            ("status", "Status"),
            ("cursor", "Cursor"),
            ("latest_cursor", "Latest Cursor"),
            ("lag", "Lag"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No subscription cursor for this topic.",
    )


def _topic_rows(
    topics: tuple[str, ...],
    *,
    latest_cursors: dict[str, str | None],
    subscription_states: list[dict[str, Any]],
    recent_events: list[dict[str, Any]],
    registry: Any | None,
) -> list[OperationsTableRowModel]:
    subscriptions_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in subscription_states:
        subscriptions_by_topic[_display(item.get("source_topic"))].append(item)
    events_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in recent_events:
        events_by_topic[_display(item.get("topic"))].append(item)
    rows = []
    for topic in topics:
        topic_events = events_by_topic.get(topic, [])
        latest_event = topic_events[0] if topic_events else {}
        contract_matches = _match_topic_contracts(registry, topic)
        route_matches = _match_route_contracts(registry, topic)
        kinds = sorted({_display(item.get("kind")) for item in topic_events if item.get("kind")})
        rows.append(
            OperationsTableRowModel(
                id=topic,
                cells={
                    "topic": topic,
                    "latest_cursor": _display(latest_cursors.get(topic)),
                    "recent_events": str(len(topic_events)),
                    "subscriptions": str(len(subscriptions_by_topic.get(topic, []))),
                    "contract": _join(_contract_ids(contract_matches)),
                    "routes": _join(_contract_ids(route_matches)),
                    "latest_event": _display(latest_event.get("event_name")),
                    "kinds": _join(kinds),
                },
                status="covered" if contract_matches else "uncovered",
                tone="success" if contract_matches else "warning",
            )
        )
    return rows


def _recent_event_summaries(
    events_service: Any | None,
    *,
    topics: tuple[str, ...],
    definition_registry: Any | None,
    contract_registry: Any | None,
    limit: int,
) -> list[dict[str, Any]]:
    if events_service is None or limit <= 0:
        return []
    records = []
    per_topic_limit = min(max(limit, 20), 80)
    for topic in topics:
        try:
            topic_records = events_service.read_recent_event_topic(
                topic,
                limit=per_topic_limit,
            )
        except Exception:
            continue
        records.extend(topic_records)
    summaries = []
    for record in records:
        summary = _event_summary(
            record,
            definition_registry=definition_registry,
            contract_registry=contract_registry,
        )
        if summary is not None:
            summaries.append(summary)
    summaries.sort(
        key=lambda item: (
            _display(item.get("created_at")),
            _display(item.get("topic")),
            _display(item.get("event_id")),
        ),
        reverse=True,
    )
    return summaries[:limit]


def _event_summary(
    record: Any,
    *,
    definition_registry: Any | None,
    contract_registry: Any | None,
) -> dict[str, Any] | None:
    try:
        observed = observed_event_from_record(
            record,
            definition_registry=definition_registry,
        )
    except Exception:
        return None
    envelope = getattr(record, "envelope", None)
    if envelope is None:
        return None
    topic = _display(getattr(envelope, "topic", None))
    event_name = observed.event_name
    definition = (
        definition_registry.get_by_event_name(event_name)
        if definition_registry is not None
        else None
    )
    surfaces = (
        definition_registry.list_surfaces_for_event_name(event_name)
        if definition_registry is not None
        else ()
    )
    contract_matches = _match_topic_contracts(contract_registry, topic)
    route_matches = _match_route_contracts(contract_registry, topic)
    contract_status = _contract_status(
        observed=observed,
        definition=definition,
        contract_matches=contract_matches,
    )
    payload = _jsonable(getattr(envelope, "payload", {}) or {})
    trace = _jsonable(getattr(envelope, "trace", {}) or {})
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(trace, dict):
        trace = {}
    return {
        "event_id": observed.id,
        "cursor": _display(getattr(record, "cursor", None)),
        "topic": topic,
        "event_name": event_name,
        "owner": observed.owner,
        "module": observed.module,
        "kind": observed.kind,
        "status": observed.status,
        "level": observed.level,
        "entity_id": observed.entity_id,
        "run_id": observed.run_id,
        "trace_id": observed.trace_id,
        "created_at": format_datetime_utc(observed.occurred_at),
        "definition_id": _display(getattr(definition, "definition_id", None)),
        "surface_ids": tuple(_display(getattr(surface, "surface_id", None)) for surface in surfaces),
        "contract_status": contract_status,
        "contract_label": _contract_label(
            definition=definition,
            contract_matches=contract_matches,
        ),
        "contract_matches": tuple(_match_payload(item) for item in contract_matches),
        "route_matches": tuple(_match_payload(item) for item in route_matches),
        "payload": payload,
        "trace": trace,
        "observed": observed.to_payload(),
    }


def _filter_events(
    events: list[dict[str, Any]],
    query: EventsOperationsQuery,
) -> list[dict[str, Any]]:
    filtered = events
    if query.status in {
        "matched",
        "uncovered",
        "definition_only",
        "topic_contract_only",
        "dead_letter",
    }:
        filtered = [
            item
            for item in filtered
            if _display(item.get("contract_status")) == query.status
        ]
    if query.owner != "all":
        filtered = [
            item
            for item in filtered
            if _display(item.get("owner")).lower() == query.owner
        ]
    if query.topic_prefix:
        filtered = [
            item
            for item in filtered
            if _display(item.get("topic")).startswith(query.topic_prefix)
        ]
    if query.search:
        needle = query.search.lower()
        filtered = [
            item
            for item in filtered
            if needle
            in " ".join(
                (
                    _display(item.get("event_name")),
                    _display(item.get("topic")),
                    _display(item.get("event_id")),
                    _display(item.get("trace_id")),
                    _display(item.get("run_id")),
                    _display(item.get("owner")),
                )
            ).lower()
        ]
    return filtered


def _subscription_states(
    states: tuple[Any, ...],
    *,
    latest_cursors: dict[str, str | None],
    now: datetime,
    registry: Any | None,
) -> list[dict[str, Any]]:
    items = []
    for state in states:
        source_topic = _display(getattr(state, "source_topic", None))
        items.append(
            _subscription_state_entry(
                subscription_id=_display(getattr(state, "subscription_id", None)),
                source_topic=source_topic,
                cursor=_display(getattr(state, "cursor", None)),
                latest_cursor=latest_cursors.get(source_topic),
                updated_at=getattr(state, "updated_at", None),
                now=now,
                registry=registry,
                observer_registered=False,
            )
        )
    return items


def _observer_subscription_states(
    observer_subscriptions: tuple[Any, ...],
    *,
    subscription_cursors: tuple[Any, ...],
    latest_cursors: dict[str, str | None],
    now: datetime,
    registry: Any | None,
) -> list[dict[str, Any]]:
    states_by_subscription = {
        _display(getattr(state, "subscription_id", None)): state
        for state in subscription_cursors
    }
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for subscription in observer_subscriptions:
        subscription_id = _display(getattr(subscription, "subscription_id", None))
        if subscription_id == "-":
            continue
        state = states_by_subscription.get(subscription_id)
        source_topic = _display(
            getattr(state, "source_topic", None)
            if state is not None
            else getattr(subscription, "source_topic", None)
        )
        items.append(
            _subscription_state_entry(
                subscription_id=subscription_id,
                source_topic=source_topic,
                cursor=(
                    _display(getattr(state, "cursor", None))
                    if state is not None
                    else "-"
                ),
                latest_cursor=latest_cursors.get(source_topic),
                updated_at=(
                    getattr(state, "updated_at", None) if state is not None else None
                ),
                now=now,
                registry=registry,
                observer_registered=True,
            )
        )
        seen.add(subscription_id)

    for state in subscription_cursors:
        subscription_id = _display(getattr(state, "subscription_id", None))
        if (
            subscription_id in seen
            or not _is_operations_observer_subscription_id(subscription_id)
        ):
            continue
        source_topic = _display(getattr(state, "source_topic", None))
        items.append(
            _subscription_state_entry(
                subscription_id=subscription_id,
                source_topic=source_topic,
                cursor=_display(getattr(state, "cursor", None)),
                latest_cursor=latest_cursors.get(source_topic),
                updated_at=getattr(state, "updated_at", None),
                now=now,
                registry=registry,
                observer_registered=False,
            )
        )
    return items


def _observer_runtime_states(
    operations_observation: Any | None,
    *,
    runtime: Any | None,
    now: datetime,
) -> list[dict[str, Any]]:
    snapshot = _safe_operations_observation_snapshot(operations_observation)
    heartbeats = tuple(getattr(snapshot, "observer_heartbeats", ()) or ())
    if not heartbeats:
        subscriptions = _safe_observer_subscriptions(runtime)
        if runtime is None and not subscriptions:
            return []
        return [
            {
                "runtime_name": _display(
                    getattr(runtime, "runtime_name", None),
                    "operations.observer",
                ),
                "worker_id": "-",
                "status": "Missing Heartbeat",
                "last_seen_at": "-",
                "seconds_since_update": 0.0,
                "processed_events": 0,
                "idle_cycles": 0,
                "subscription_count": len(subscriptions),
                "active": False,
                "lagging": True,
                "stuck": False,
                "tone": "warning",
            }
        ]
    entries = [_observer_runtime_state_entry(heartbeat, now=now) for heartbeat in heartbeats]
    active_runtime_names = {
        _display(item.get("runtime_name")) for item in entries if item["active"]
    }
    if not active_runtime_names:
        return entries
    return [
        item
        for item in entries
        if not (
            _display(item.get("runtime_name")) in active_runtime_names
            and item["lagging"]
            and not item["stuck"]
            and not item["active"]
        )
    ]


def _observer_runtime_state_entry(
    heartbeat: Any,
    *,
    now: datetime,
) -> dict[str, Any]:
    raw_status = (
        _display(getattr(heartbeat, "status", None), "unknown")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    last_seen_at = getattr(heartbeat, "last_seen_at", None)
    seconds_since_update = _seconds_since_datetime(last_seen_at, now=now)
    stale = (
        raw_status in {"running", "idle"}
        and seconds_since_update >= _OBSERVER_RUNTIME_STALE_AFTER_SECONDS
    )
    failed = raw_status == "failed"
    active = raw_status in {"running", "idle"} and not stale
    status = "Stale" if stale else _observer_runtime_status_label(raw_status)
    return {
        "runtime_name": _display(getattr(heartbeat, "runtime_name", None)),
        "worker_id": _display(getattr(heartbeat, "worker_id", None)),
        "status": status,
        "last_seen_at": (
            format_datetime_utc(last_seen_at.astimezone(timezone.utc))
            if isinstance(last_seen_at, datetime)
            else "-"
        ),
        "seconds_since_update": round(seconds_since_update, 3),
        "processed_events": int(getattr(heartbeat, "processed_events", 0) or 0),
        "idle_cycles": int(getattr(heartbeat, "idle_cycles", 0) or 0),
        "subscription_count": int(
            getattr(heartbeat, "subscription_count", 0) or 0
        ),
        "active": active,
        "lagging": stale,
        "stuck": failed,
        "tone": "danger" if failed else "warning" if stale else "success" if active else "neutral",
    }


def _safe_operations_observation_snapshot(operations_observation: Any | None) -> Any | None:
    if operations_observation is None:
        return None
    snapshot = getattr(operations_observation, "snapshot", None)
    if not callable(snapshot):
        return None
    try:
        return snapshot()
    except Exception:
        return None


def _observer_runtime_status_label(status: str) -> str:
    return {
        "running": "Running",
        "idle": "Idle",
        "completed": "Completed",
        "rebuilt": "Rebuilt",
        "stopped": "Stopped",
        "failed": "Failed",
    }.get(status, status.replace("_", " ").title() or "Unknown")


def _subscription_state_entry(
    *,
    subscription_id: str,
    source_topic: str,
    cursor: str,
    latest_cursor: str | None,
    updated_at: Any,
    now: datetime,
    registry: Any | None,
    observer_registered: bool,
) -> dict[str, Any]:
    latest_cursor_label = _display(latest_cursor)
    comparison = _compare_event_cursors(cursor, latest_cursor_label)
    lagging = comparison < 0
    seconds_since_update = _seconds_since_datetime(updated_at, now=now)
    stuck = lagging and seconds_since_update >= _STUCK_SUBSCRIPTION_AFTER_SECONDS
    contract_matches = _match_topic_contracts(registry, source_topic)
    route_matches = _match_route_contracts(registry, source_topic)
    return {
        "subscription_id": subscription_id,
        "source_topic": source_topic,
        "cursor": cursor,
        "latest_cursor": latest_cursor_label,
        "lag": _cursor_gap(latest_cursor_label, cursor),
        "at_head": not lagging,
        "lagging": lagging,
        "stuck": stuck,
        "status": "Stuck" if stuck else "Lagging" if lagging else "At Head",
        "updated_at": (
            format_datetime_utc(updated_at.astimezone(timezone.utc))
            if isinstance(updated_at, datetime)
            else "-"
        ),
        "seconds_since_update": round(seconds_since_update, 3),
        "contract_label": _join(_contract_ids(contract_matches)),
        "route_label": _join(_contract_ids(route_matches)),
        "observer_registered": observer_registered,
    }


def _safe_list(target: Any | None, method_name: str) -> tuple[Any, ...]:
    if target is None:
        return ()
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        return tuple(method())
    except Exception:
        return ()


def _safe_subscription_cursors(events_service: Any | None) -> tuple[Any, ...]:
    if events_service is None:
        return ()
    try:
        return tuple(events_service.list_subscription_cursors())
    except Exception:
        return ()


def _safe_observer_subscriptions(runtime: Any | None) -> tuple[Any, ...]:
    if runtime is None:
        return ()
    try:
        subscriptions = getattr(runtime, "subscriptions", ())
    except Exception:
        return ()
    if callable(subscriptions):
        try:
            subscriptions = subscriptions()
        except Exception:
            return ()
    try:
        return tuple(subscriptions)
    except TypeError:
        return ()


def _list_live_topics(
    events_service: Any | None,
    *,
    topic_prefix: str,
) -> tuple[str, ...]:
    if events_service is None:
        return ()
    try:
        topics = tuple(
            topic.strip()
            for topic in events_service.list_event_topics()
            if isinstance(topic, str) and topic.strip()
        )
    except Exception:
        return ()
    if topic_prefix:
        topics = tuple(topic for topic in topics if topic.startswith(topic_prefix))
    return tuple(sorted(dict.fromkeys(topics)))


def _prioritized_topics(
    *,
    live_topics: tuple[str, ...],
    source_topics: set[str],
    limit: int,
) -> tuple[str, ...]:
    live_topic_set = set(live_topics)
    ordered: list[str] = []

    def add(topic: str) -> None:
        if topic in live_topic_set and topic not in ordered:
            ordered.append(topic)

    for topic in sorted(source_topics):
        add(topic)
    for prefix in (
        "events.named.orchestration.",
        "events.named.tool.",
        "events.named.llm.",
        "orchestration.",
        "tool.",
        "llm.",
        "turn.",
        "delivery.",
    ):
        for topic in live_topics:
            if topic.startswith(prefix):
                add(topic)
    for topic in live_topics:
        add(topic)
    return tuple(ordered[: max(1, limit)])


def _safe_snapshot(events_service: Any | None, topic: str) -> str | None:
    if events_service is None:
        return None
    try:
        return events_service.snapshot_event_topic(topic)
    except Exception:
        return None


def _match_topic_contracts(registry: Any | None, topic: str) -> tuple[Any, ...]:
    if registry is None:
        return ()
    try:
        return tuple(registry.match_topic_contracts(topic))
    except Exception:
        return ()


def _match_route_contracts(registry: Any | None, topic: str) -> tuple[Any, ...]:
    if registry is None:
        return ()
    try:
        return tuple(registry.match_route_contracts(topic))
    except Exception:
        return ()


def _contract_status(
    *,
    observed: OperationsObservedEvent,
    definition: Any | None,
    contract_matches: tuple[Any, ...],
) -> str:
    name = observed.event_name.lower()
    topic = observed.topic.lower()
    if "dead_letter" in name or "dead-letter" in name or "dead_letter" in topic:
        return "dead_letter"
    has_definition = definition is not None
    has_contract = bool(contract_matches)
    if has_definition and has_contract:
        return "matched"
    if has_definition:
        return "definition_only"
    if has_contract:
        return "topic_contract_only"
    return "uncovered"


def _contract_label(
    *,
    definition: Any | None,
    contract_matches: tuple[Any, ...],
) -> str:
    ids = _contract_ids(contract_matches)
    definition_id = _display(getattr(definition, "definition_id", None))
    if ids and definition_id != "-":
        return f"{definition_id} / {_join(ids)}"
    if definition_id != "-":
        return definition_id
    if ids:
        return _join(ids)
    return "-"


def _contract_ids(matches: tuple[Any, ...]) -> tuple[str, ...]:
    ids = []
    for match in matches:
        contract = getattr(match, "contract", None)
        contract_id = _display(getattr(contract, "contract_id", None))
        if contract_id != "-":
            ids.append(contract_id)
    return tuple(ids)


def _match_payload(match: Any) -> dict[str, Any]:
    to_payload = getattr(match, "to_payload", None)
    if callable(to_payload):
        try:
            return _as_dict(_jsonable(to_payload()))
        except Exception:
            return {}
    return {}


def _uncovered_topics(
    topics: tuple[str, ...],
    *,
    registry: Any | None,
) -> tuple[str, ...]:
    return tuple(
        topic
        for topic in topics
        if not _match_topic_contracts(registry, topic)
    )


def _dead_letter_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in events
        if _display(item.get("contract_status")) == "dead_letter"
        or "dead_letter" in _display(item.get("topic")).lower()
        or "dead-letter" in _display(item.get("topic")).lower()
    ]


def _looks_like_mapping_failure(item: dict[str, Any]) -> bool:
    text = " ".join(
        (
            _display(item.get("event_name")),
            _display(item.get("status")),
            _display(item.get("topic")),
            _display(item.get("level")),
        )
    ).lower()
    return any(
        token in text
        for token in (
            "observation",
            "observer",
            "mapping",
            "dead_letter",
            "failed",
            "error",
        )
    )


def _event_tone(item: dict[str, Any]) -> str:
    status = _display(item.get("contract_status"))
    level = _display(item.get("level")).lower()
    if status in {"dead_letter", "uncovered"} or level == "error":
        return "danger"
    if status in {"definition_only", "topic_contract_only"} or level == "warning":
        return "warning"
    if status == "matched":
        return "success"
    return "neutral"


def _subscription_tone(item: dict[str, Any]) -> str:
    if item.get("stuck"):
        return "danger"
    if item.get("lagging"):
        return "warning"
    return "success"


def _subscription_sort_key(item: dict[str, Any]) -> tuple[bool, bool, int, str, str]:
    return (
        not bool(item.get("stuck")),
        not bool(item.get("lagging")),
        -int(item.get("lag") or 0),
        _display(item.get("source_topic")),
        _display(item.get("subscription_id")),
    )


def _observer_runtime_sort_key(item: dict[str, Any]) -> tuple[bool, bool, str, str]:
    return (
        not bool(item.get("stuck")),
        not bool(item.get("lagging")),
        _display(item.get("runtime_name")),
        _display(item.get("worker_id")),
    )


def _owner_from_subscription(item: dict[str, Any]) -> str:
    subscription = _display(item.get("subscription_id"))
    topic = _display(item.get("source_topic"))
    for candidate in (subscription, topic):
        if candidate != "-":
            head = candidate.split(".", 1)[0].split(":", 1)[0]
            if head:
                return head
    return "-"


def _observer_event_name(item: dict[str, Any]) -> str:
    subscription_id = _display(item.get("subscription_id"))
    observer_prefix = "operations.observer."
    if subscription_id.startswith(observer_prefix):
        return subscription_id.removeprefix(observer_prefix)
    topic = _display(item.get("source_topic"))
    named_prefix = "events.named."
    if topic.startswith(named_prefix):
        return topic.removeprefix(named_prefix)
    return topic


def _is_operations_observer_subscription_id(subscription_id: str) -> bool:
    return subscription_id.startswith("operations.observer.")


def _seconds_since_update(state: Any, *, now: datetime) -> float:
    updated_at = getattr(state, "updated_at", None)
    return _seconds_since_datetime(updated_at, now=now)


def _seconds_since_datetime(updated_at: Any, *, now: datetime) -> float:
    if not isinstance(updated_at, datetime):
        return 0.0
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - updated_at.astimezone(timezone.utc)).total_seconds())


def _compare_event_cursors(left: str | None, right: str | None) -> int:
    left_cursor = _parse_event_cursor(left)
    right_cursor = _parse_event_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def _cursor_gap(latest: str | None, current: str | None) -> int:
    left = _parse_event_cursor(latest)
    right = _parse_event_cursor(current)
    if left[0] != right[0]:
        return max(0, left[0] - right[0])
    return max(0, left[1] - right[1])


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


def _contract_matches_topic(contract: Any, topic: str) -> bool:
    pattern = _display(getattr(contract, "topic_pattern", None))
    return _pattern_matches(pattern, topic)


def _pattern_matches(pattern: str, topic: str) -> bool:
    if not pattern or pattern == "-":
        return False
    pattern_parts = pattern.split(".")
    topic_parts = topic.split(".")
    if len(pattern_parts) != len(topic_parts):
        return False
    for left, right in zip(pattern_parts, topic_parts):
        if left.startswith("{") and left.endswith("}"):
            continue
        if left != right:
            return False
    return True


def _health(
    *,
    events_service_available: bool,
    stuck_count: int,
    lagging_count: int,
    dead_letter_count: int,
    uncovered_topic_count: int,
) -> str:
    if not events_service_available or stuck_count or dead_letter_count:
        return "error"
    if lagging_count or uncovered_topic_count:
        return "warning"
    return "healthy"


def _health_label(health: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "error": "Error",
    }.get(health, "Unknown")


def _health_delta(health: str) -> str:
    return {
        "healthy": "Event bus state is queryable",
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def _health_tone(health: str) -> str:
    return {
        "healthy": "success",
        "warning": "warning",
        "error": "danger",
    }.get(health, "neutral")


def _kind_tone(kind: str) -> str:
    return {
        "command": "info",
        "fact": "success",
        "broadcast": "neutral",
        "observe": "warning",
        "live": "info",
    }.get(kind.lower(), "neutral")


def _tone_for_index(index: int) -> str:
    return ("info", "success", "warning", "neutral", "danger")[index % 5]


def _contract_status_label(status: str) -> str:
    return {
        "matched": "Matched",
        "uncovered": "Uncovered",
        "definition_only": "Definition Only",
        "topic_contract_only": "Topic Contract Only",
        "dead_letter": "Dead Letter",
    }.get(status, status or "-")


def _recent_empty_state(query: EventsOperationsQuery) -> str:
    if query.search or query.status != "all" or query.owner != "all" or query.topic_prefix:
        return "No events match the current filters."
    return "No event bus records observed."


def _trace_route(item: dict[str, Any]) -> str:
    trace_id = _display(item.get("trace_id"))
    if trace_id == "-":
        return "-"
    return f"/trace?trace_id={trace_id}"


def _event_row_id(item: dict[str, Any]) -> str:
    event_id = _display(item.get("event_id"))
    if event_id != "-":
        return event_id
    return f"{_display(item.get('topic'))}:{_display(item.get('cursor'))}"


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in items)


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(
        {key: str(value) for key, value in row.cells.items()}
        for row in section.rows[:80]
    )


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        try:
            return _jsonable(to_payload())
        except Exception:
            return _display(value)
    return _display(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return _join(tuple(_display(item) for item in value))
    return str(value)


def _join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"


def _slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    return "_".join(part for part in normalized.split("_") if part) or "unknown"
