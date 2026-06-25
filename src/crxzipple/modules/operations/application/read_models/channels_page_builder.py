from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_details import (
    runtime_details as _runtime_details,
)
from crxzipple.modules.operations.application.read_models.channels_interaction_details import (
    interaction_details as _interaction_details,
)
from crxzipple.modules.operations.application.read_models.channels_record_details import (
    record_details as _record_details,
)
from crxzipple.modules.operations.application.read_models.channels_charts import (
    delivery_trend as _delivery_trend,
    failures_by_category as _failures_by_category,
    message_flow as _message_flow,
    top_channels as _top_channels,
)
from crxzipple.modules.operations.application.read_models.channels_page_summary import (
    actions as _actions,
    metrics as _metrics,
    tabs as _tabs,
)
from crxzipple.modules.operations.application.read_models.channels_contract_tables import (
    contracts_table as _contracts_table,
)
from crxzipple.modules.operations.application.read_models.channels_page_data import (
    build_channels_page_data,
)
from crxzipple.modules.operations.application.read_models.channels_binding_tables import (
    account_bindings_table as _account_bindings_table,
    connection_bindings_table as _connection_bindings_table,
    profiles_table as _profiles_table,
)
from crxzipple.modules.operations.application.read_models.channels_interaction_tables import (
    interactions_table as _interactions_table,
)
from crxzipple.modules.operations.application.read_models.channels_message_tables import (
    channel_events_table as _channel_events_table,
    dead_letter_table as _dead_letter_table,
    recent_messages_table as _recent_messages_table,
)
from crxzipple.modules.operations.application.read_models.channels_runtime_tables import (
    channel_status_table as _channel_status_table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelsOperationsPage,
    ChannelsOperationsQuery,
)
from crxzipple.shared.time import format_datetime_utc


def channels_operations_page(
    *,
    channel_profile_service: Any | None,
    channel_runtime_manager: Any | None,
    channel_interaction_service: Any | None = None,
    events_service: Any | None = None,
    event_contract_registry: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    query: ChannelsOperationsQuery | None = None,
) -> ChannelsOperationsPage:
    data = build_channels_page_data(
        channel_profile_service=channel_profile_service,
        channel_runtime_manager=channel_runtime_manager,
        channel_interaction_service=channel_interaction_service,
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        operations_observation=operations_observation,
        query=query,
    )

    channel_status = _channel_status_table(
        data.filtered_runtime_records,
        total=len(data.filtered_runtime_records),
    )
    dead_letter_queue = _dead_letter_table(data.filtered_dead_letters)
    recent_messages = _recent_messages_table(
        data.visible_events,
        total=len(data.filtered_events),
    )
    interactions_table = _interactions_table(
        data.visible_interactions,
        total=len(data.filtered_interactions),
    )
    channel_bindings = _account_bindings_table(
        data.account_bindings,
        profiles=data.profiles,
    )
    connection_bindings_table = _connection_bindings_table(data.connection_bindings)
    channel_profiles = _profiles_table(data.profiles)
    channel_events_table = _channel_events_table(
        data.visible_events,
        total=len(data.filtered_events),
    )
    contracts = _contracts_table(
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
    )

    return ChannelsOperationsPage(
        module="channels",
        title="Channels",
        subtitle="聚合通道配置、运行时、绑定、死信与通道事件的运维视图。",
        health=data.health,
        updated_at=format_datetime_utc(data.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Channels operator",
            can_operate=True,
            scope="channels",
        ),
        metrics=_metrics(
            health=data.health,
            profiles=data.profiles,
            runtimes=data.runtime_records,
            account_bindings=data.account_bindings,
            connection_bindings=data.connection_bindings,
            events=data.channel_events,
            dead_letters=data.dead_letter_events,
            interactions=data.interactions,
            now=data.now,
        ),
        tabs=_tabs(
            runtimes=len(data.filtered_runtime_records),
            interactions=len(data.filtered_interactions),
            connections=len(data.connection_bindings),
            accounts=len(data.account_bindings),
            profiles=len(data.profiles),
            messages=len(data.filtered_events),
            dead_letters=len(data.filtered_dead_letters),
            contracts=contracts.total,
        ),
        active_tab="runtimes",
        actions=_actions(),
        channel_status=channel_status,
        message_flow=_message_flow(data.channel_events, data.interactions),
        delivery_trend=_delivery_trend(
            data.channel_events,
            data.runtime_records,
            data.interactions,
            event_buckets=data.event_buckets,
        ),
        top_channels=_top_channels(
            data.channel_events,
            data.runtime_records,
            data.interactions,
        ),
        dead_letter_queue=dead_letter_queue,
        recent_messages=recent_messages,
        interactions=interactions_table,
        failures_by_category=_failures_by_category(data.dead_letter_events),
        channel_bindings=channel_bindings,
        connection_bindings=connection_bindings_table,
        channel_profiles=channel_profiles,
        channel_events=channel_events_table,
        contracts=contracts,
        runtime_details=_runtime_details(
            runtimes=data.runtimes,
            runtime_records=data.runtime_records,
            account_bindings=data.account_bindings,
            connection_bindings=data.connection_bindings,
            events=data.channel_events,
            dead_letters=data.dead_letter_events,
            now=data.now,
        ),
        record_details=_record_details(
            (*data.visible_events, *data.filtered_dead_letters[:20]),
        ),
        interaction_details=_interaction_details(
            data.visible_interactions,
            events=data.channel_events,
        ),
    )
