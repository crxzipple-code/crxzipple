from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_contract_sections import (
    contracts_table as _contracts_table,
    routes_table as _routes_table,
    topics_table as _topics_table,
)
from crxzipple.modules.operations.application.read_models.events_dead_letters import (
    dead_letters_table as _dead_letters_table,
)
from crxzipple.modules.operations.application.read_models.events_event_detail_sections import (
    event_details as _event_details,
)
from crxzipple.modules.operations.application.read_models.events_event_details import (
    recent_events_table as _recent_events_table,
)
from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsPage,
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_observer_coverage_sections import (
    observer_coverage_table as _observer_coverage_table,
)
from crxzipple.modules.operations.application.read_models.events_observer_runtime_sections import (
    observer_health_table as _observer_health_table,
    observer_lag_table as _observer_lag_table,
)
from crxzipple.modules.operations.application.read_models.events_subscription_sections import (
    consumer_health_table as _consumer_health_table,
    subscriptions_table as _subscriptions_table,
)
from crxzipple.modules.operations.application.read_models.events_overview_charts import (
    events_by_surface as _events_by_surface,
    events_by_surface_from_buckets as _events_by_surface_from_buckets,
    events_over_time as _events_over_time,
    events_over_time_from_buckets as _events_over_time_from_buckets,
)
from crxzipple.modules.operations.application.read_models.events_contract_compatibility import (
    contract_compatibility as _contract_compatibility,
)
from crxzipple.modules.operations.application.read_models.events_navigation_sections import (
    events_actions as _actions,
    events_tabs as _tabs,
)
from crxzipple.modules.operations.application.read_models.events_overview_sections import (
    events_metric_cards as _metrics,
)
from crxzipple.modules.operations.application.read_models.events_owner_sections import (
    owners_by_volume as _owners_by_volume,
)
from crxzipple.modules.operations.application.read_models.events_page_facts import (
    collect_events_page_facts,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.shared.time import format_datetime_utc


def events_operations_page(
    *,
    events_service: Any | None,
    event_contract_registry: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    operations_observer_runtime: Any | None = None,
    query: EventsOperationsQuery | None = None,
) -> EventsOperationsPage:
    facts = collect_events_page_facts(
        events_service=events_service,
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        operations_observer_runtime=operations_observer_runtime,
        query=query,
    )

    return EventsOperationsPage(
        module="events",
        title="Events",
        subtitle="聚合事件总线、事件合同、订阅游标、观察者消费与死信状态。",
        health=facts.health,
        updated_at=format_datetime_utc(facts.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Events operator",
            can_operate=True,
            scope="events",
        ),
        metrics=_metrics(
            health=facts.health,
            live_topics=facts.live_topics,
            definitions=facts.definitions,
            subscriptions=facts.subscription_states,
            recent_events=facts.all_recent_events,
            dead_letters=facts.dead_letter_events,
            observer_states=facts.observer_states,
            observer_runtime_states=facts.observer_runtime_states,
        ),
        tabs=_tabs(
            recent_count=len(facts.filtered_events),
            topic_count=len(facts.live_topics),
            subscription_count=len(facts.subscription_states),
            observer_definition_count=len(facts.observer_definitions),
            contract_count=len(facts.topic_contracts),
            route_count=len(facts.route_contracts),
            observer_count=len(facts.observer_states) + len(facts.observer_runtime_states),
            observer_problem_count=(
                facts.observer_lagging_count
                + facts.observer_stuck_count
                + facts.observer_runtime_lagging_count
                + facts.observer_runtime_stuck_count
            ),
            dead_letter_count=len(facts.dead_letter_events),
            mapping_count=facts.lagging_count + facts.stuck_count,
        ),
        active_tab="recent",
        actions=_actions(),
        events_over_time=_events_over_time_from_buckets(facts.event_buckets)
        if facts.event_buckets
        else _events_over_time(facts.all_recent_events),
        events_by_surface=_events_by_surface_from_buckets(facts.event_buckets)
        if facts.event_buckets
        else _events_by_surface(facts.all_recent_events),
        owners_by_volume=_owners_by_volume(
            facts.all_recent_events,
            definitions=facts.definitions,
            surfaces=facts.surfaces,
            subscriptions=facts.subscription_states,
            event_buckets=facts.event_buckets,
        ),
        contract_compatibility=_contract_compatibility(
            live_topics=facts.live_topics,
            topic_contracts=facts.topic_contracts,
            route_contracts=facts.route_contracts,
            definitions=facts.definitions,
            surfaces=facts.surfaces,
            observer_definitions=facts.observer_definitions,
            subscriptions=facts.subscription_states,
            uncovered_topics=facts.uncovered_topics,
            uncovered_events=facts.uncovered_events,
        ),
        recent_events=_recent_events_table(
            facts.visible_events,
            total=len(facts.filtered_events),
            query=facts.query,
        ),
        consumer_health=_consumer_health_table(facts.subscription_states),
        observer_health=_observer_health_table(
            facts.observer_states,
            runtime_states=facts.observer_runtime_states,
            definitions=facts.definitions,
        ),
        observer_lag=_observer_lag_table(
            facts.subscription_states,
            facts.all_recent_events,
        ),
        topics=_topics_table(facts.live_topic_rows, total_count=len(facts.live_topics)),
        subscriptions=_subscriptions_table(facts.subscription_states, query=facts.query),
        observer_coverage=_observer_coverage_table(
            facts.observer_definitions,
            facts.all_recent_events,
        ),
        dead_letters=_dead_letters_table(facts.dead_letter_events),
        contracts=_contracts_table(facts.topic_contracts, facts.live_topics),
        routes=_routes_table(facts.route_contracts, facts.subscription_states),
        event_details=_event_details(
            facts.visible_events,
            subscription_states=facts.subscription_states,
        ),
    )
