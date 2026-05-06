from __future__ import annotations

from crxzipple.modules.channels.domain import (
    channel_broadcast_topic,
    channel_connection_control_topic,
    channel_dead_letter_topic,
)
from crxzipple.modules.events import EventRouteContract, EventTopicContract
from crxzipple.modules.orchestration.application.observers import turn_session_topic
from crxzipple.shared import EventDefinition, EventDefinitionField, EventSurface


def channel_event_topic_contracts() -> tuple[EventTopicContract, ...]:
    return (
        EventTopicContract(
            contract_id="channel.broadcast",
            topic_pattern=channel_broadcast_topic("{channel_type}"),
            owner="channels",
            description="Broadcast topic for all clients of a channel type.",
            kinds=("broadcast",),
            producers=("channel control/runtime services",),
            consumers=("WebChannel SSE /channels/web/events",),
        ),
        EventTopicContract(
            contract_id="channel.broadcast.account",
            topic_pattern=channel_broadcast_topic(
                "{channel_type}",
                channel_account_id="{channel_account_id}",
            ),
            owner="channels",
            description="Broadcast topic scoped to a channel account.",
            kinds=("broadcast",),
            producers=("channel control/runtime services",),
            consumers=("WebChannel SSE /channels/web/events",),
        ),
        EventTopicContract(
            contract_id="channel.dead_letter",
            topic_pattern=channel_dead_letter_topic("{channel_type}"),
            owner="channels",
            description="Channel dead-letter topic for failed observation delivery.",
            kinds=("fact",),
            producers=("channel runtime observation delivery loops",),
            consumers=("dead-letter inspection/replay endpoints",),
        ),
        EventTopicContract(
            contract_id="channel.dead_letter.runtime",
            topic_pattern=channel_dead_letter_topic(
                "{channel_type}",
                runtime_id="{runtime_id}",
            ),
            owner="channels",
            description="Runtime scoped channel dead-letter topic.",
            kinds=("fact",),
            producers=(
                "LarkChannelRuntimeService._publish_dead_letter",
                "WebhookChannelRuntimeService._publish_dead_letter",
            ),
            consumers=("dead-letter inspection/replay endpoints",),
        ),
        EventTopicContract(
            contract_id="channel.connection.control",
            topic_pattern=channel_connection_control_topic(
                "{channel_type}",
                connection_id="{connection_id}",
            ),
            owner="channels",
            description="Per-connection control topic used to wake active channel streams.",
            kinds=("control",),
            producers=("channel HTTP/control endpoints",),
            consumers=("active channel SSE streams",),
        ),
    )


def channel_event_route_contracts() -> tuple[EventRouteContract, ...]:
    return ()


def channel_event_definitions() -> tuple[EventDefinition, ...]:
    return (
        EventDefinition(
            definition_id="channel.observation.dead_lettered",
            owner="channels",
            event_name="channel.observation.dead_lettered",
            description=(
                "Channel observation delivery failed after retries and was persisted "
                "to a dead-letter topic."
            ),
            topics=(
                "channel.dead_letter.{channel_type}",
                "channel.dead_letter.{channel_type}.runtime.{runtime_id}",
            ),
            producers=("WebhookChannelRuntimeService._publish_observe_dead_letter",),
            consumers=("dead-letter inspection/replay endpoints", "web console"),
            fields=(
                EventDefinitionField(
                    "event_name",
                    "Stable channel dead-letter event name.",
                    "string",
                    True,
                ),
                EventDefinitionField(
                    "outbound_id",
                    "Delivery outbound identifier.",
                    "string",
                    True,
                ),
                EventDefinitionField(
                    "outbound",
                    "Original outbound payload that failed to deliver.",
                    "object",
                    True,
                ),
                EventDefinitionField(
                    "conversation_id",
                    "External conversation identifier when present.",
                    "string",
                ),
                EventDefinitionField(
                    "session_key",
                    "Owning session key when present.",
                    "string",
                ),
                EventDefinitionField(
                    "message",
                    "Observed message payload.",
                    "object",
                ),
                EventDefinitionField(
                    "reply_address",
                    "Reply routing payload used by the channel runtime.",
                    "object",
                ),
                EventDefinitionField(
                    "callback_url",
                    "Webhook callback URL when delivery used callbacks.",
                    "string",
                ),
                EventDefinitionField(
                    "status",
                    "Last delivery failure status.",
                    "string",
                    True,
                ),
                EventDefinitionField(
                    "attempt_count",
                    "Number of delivery attempts before dead-lettering.",
                    "integer",
                    True,
                ),
                EventDefinitionField(
                    "created_at",
                    "Original outbound creation timestamp.",
                    "string",
                ),
            ),
            durability="persistent",
            publication_mode="direct",
            notes=(
                "This is a channel-owned failure fact, not a mirrored orchestration event.",
            ),
        ),
        EventDefinition(
            definition_id="channel.connection.subscription_updated",
            owner="channels",
            event_name="channel.connection.subscription_updated",
            description=(
                "A channel connection subscription changed and active stream consumers "
                "should refresh binding state."
            ),
            topics=(
                "channel.connection.{channel_type}.connection.{connection_id}.control",
            ),
            producers=("web channel subscription endpoint",),
            consumers=("active channel SSE streams",),
            fields=(
                EventDefinitionField(
                    "event_name",
                    "Stable channel connection control event name.",
                    "string",
                    True,
                ),
                EventDefinitionField(
                    "channel_type",
                    "Owning channel type.",
                    "string",
                    True,
                ),
                EventDefinitionField(
                    "channel_account_id",
                    "Channel account bound to the connection.",
                    "string",
                ),
                EventDefinitionField(
                    "connection_id",
                    "Connection identifier whose subscription changed.",
                    "string",
                    True,
                ),
                EventDefinitionField(
                    "conversation_id",
                    "New conversation/session subscription.",
                    "string",
                ),
                EventDefinitionField(
                    "runtime_id",
                    "Owning runtime identifier.",
                    "string",
                ),
            ),
            durability="transient",
            publication_mode="direct",
        ),
    )


def channel_event_surfaces() -> tuple[EventSurface, ...]:
    return (
        EventSurface(
            surface_id="channels.dead_letter",
            owner="channels",
            description="Channel observation delivery failure surface.",
            definition_ids=("channel.observation.dead_lettered",),
            topics=(
                "channel.dead_letter.{channel_type}",
                "channel.dead_letter.{channel_type}.runtime.{runtime_id}",
            ),
            consumers=("dead-letter inspection/replay endpoints", "web console"),
            notes=(
                "Carries terminal observation delivery failures emitted by channel runtimes.",
            ),
        ),
    )
