from __future__ import annotations

from threading import Event as ThreadEvent
from typing import Any

from crxzipple.modules.channels.application.ports import (
    ChannelAccessReadinessPort,
    ChannelEventStreamPort,
)
from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.application.services import (
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountRuntimeBinding,
    ChannelConnectionBinding,
    ChannelRuntimeRegistration,
    ChannelRuntimeRegistry,
)
from crxzipple.modules.events import EventCursor, EventTopicRecord, EventTopicWatch
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.shared.access import CredentialProvider


class WebChannelRuntimeService(ChannelRuntimeBootstrapService):
    def __init__(
        self,
        *,
        profile_service: ChannelProfileApplicationService,
        runtime_manager: ChannelRuntimeManager,
        events_service: ChannelEventStreamPort,
        access_service: ChannelAccessReadinessPort | None = None,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        super().__init__(
            profile_service=profile_service,
            runtime_manager=runtime_manager,
            access_service=access_service,
            credential_provider=credential_provider,
        )
        self.events_service = events_service

    def ensure_registered(
        self,
        *,
        runtime_id: str = "web-runtime-1",
        service_key: str = "channel:web",
        status: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        return super().ensure_registered(
            "web",
            runtime_id=runtime_id,
            service_key=service_key,
            status=status,
            metadata=metadata,
        )

    def run_runtime_loop(
        self,
        channel_type: str,
        *,
        runtime_id: str | None = None,
        service_key: str | None = None,
        poll_interval_seconds: float,
        max_cycles: int | None = None,
        stop_event: ThreadEvent | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        del channel_type
        stopper = stop_event or ThreadEvent()
        registration = self.ensure_registered(
            runtime_id=runtime_id or "web-runtime-1",
            service_key=service_key or "channel:web",
            metadata=metadata,
        )
        completed_cycles = 0
        while not stopper.is_set():
            self.wait_for_runtime_activity(
                registration.runtime_id,
                timeout_seconds=max(float(poll_interval_seconds), 0.05),
                stop_event=stopper,
            )
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            if stopper.is_set():
                break
            refreshed = self.runtime_manager.heartbeat_runtime(
                registration.runtime_id,
            )
            if refreshed is not None:
                registration = refreshed
        return registration

    def bind_connection(
        self,
        *,
        connection_id: str,
        channel_account_id: str | None = None,
        conversation_id: str | None = None,
        supports_streaming: bool = True,
        runtime_id: str = "web-runtime-1",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelConnectionBinding:
        registration = self.ensure_registered(runtime_id=runtime_id)
        if channel_account_id:
            self.runtime_manager.bind_account(
                ChannelAccountRuntimeBinding(
                    channel_type="web",
                    channel_account_id=channel_account_id,
                    runtime_id=registration.runtime_id,
                ),
            )
        return self.runtime_manager.bind_connection(
            ChannelConnectionBinding(
                channel_type="web",
                connection_id=connection_id,
                runtime_id=registration.runtime_id,
                channel_account_id=channel_account_id,
                conversation_id=conversation_id,
                supports_streaming=supports_streaming,
                metadata=dict(metadata or {}),
            ),
        )

    def unbind_connection(self, connection_id: str) -> ChannelRuntimeRegistry:
        return self.runtime_manager.unbind_connection(
            channel_type="web",
            connection_id=connection_id,
        )

    def wait_for_runtime_activity(
        self,
        runtime_id: str,
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        watches: list[EventTopicWatch] = []
        for binding in self.runtime_manager.list_connection_bindings(
            runtime_id=runtime_id,
            channel_type="web",
        ):
            session_key = (
                binding.conversation_id.strip()
                if isinstance(binding.conversation_id, str)
                and binding.conversation_id.strip()
                else None
            )
            watches.extend(
                self.build_connection_wait_watches(
                    connection_id=binding.connection_id,
                    conversation_id=session_key,
                )
            )

        if not watches:
            if stop_event is not None:
                stop_event.wait(timeout_seconds)
            return False
        return (
            self.events_service.wait_for_event_topics(
                tuple(watches),
                timeout_seconds=timeout_seconds,
                stop_event=stop_event,
            )
            is not None
        )

    def snapshot_observe_source_cursor(
        self,
        conversation_id: str | None,
    ) -> EventCursor | None:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return None
        return self.events_service.snapshot_event_topic(
            turn_session_topic(normalized_conversation_id),
        )

    def snapshot_live_source_cursor(
        self,
        conversation_id: str | None,
    ) -> EventCursor | None:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return None
        return self.events_service.snapshot_event_topic(
            turn_session_live_topic(normalized_conversation_id),
        )

    def seed_connection_source_cursors(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
        observe_cursor: EventCursor | None = None,
        live_cursor: EventCursor | None = None,
    ) -> dict[str, EventCursor]:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return {}
        observe_topic = turn_session_topic(normalized_conversation_id)
        live_topic = turn_session_live_topic(normalized_conversation_id)
        resolved_observe_cursor = (
            observe_cursor
            if observe_cursor is not None
            else self.events_service.snapshot_event_topic(observe_topic)
        )
        resolved_live_cursor = (
            live_cursor
            if live_cursor is not None
            else self.events_service.snapshot_event_topic(live_topic)
        )
        self.runtime_manager.merge_connection_metadata(
            channel_type="web",
            connection_id=connection_id,
            metadata={
                "observe_cursor": resolved_observe_cursor,
                "live_cursor": resolved_live_cursor,
            },
        )
        return {
            "observe_cursor": resolved_observe_cursor,
            "live_cursor": resolved_live_cursor,
        }

    def ensure_connection_source_cursors(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
        observe_cursor: EventCursor | None = None,
        live_cursor: EventCursor | None = None,
    ) -> ChannelConnectionBinding | None:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        binding = self.runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id=connection_id,
        )
        if binding is None or normalized_conversation_id is None:
            return binding
        metadata_updates: dict[str, Any] = {}
        if not (
            isinstance(binding.metadata.get("observe_cursor"), str)
            and str(binding.metadata.get("observe_cursor") or "").strip()
        ):
            metadata_updates["observe_cursor"] = (
                observe_cursor
                if observe_cursor is not None
                else self.snapshot_observe_source_cursor(normalized_conversation_id)
            )
        if not (
            isinstance(binding.metadata.get("live_cursor"), str)
            and str(binding.metadata.get("live_cursor") or "").strip()
        ):
            metadata_updates["live_cursor"] = (
                live_cursor
                if live_cursor is not None
                else self.snapshot_live_source_cursor(normalized_conversation_id)
            )
        if not metadata_updates:
            return binding
        return (
            self.runtime_manager.merge_connection_metadata(
                channel_type="web",
                connection_id=connection_id,
                metadata=metadata_updates,
            )
            or binding
        )

    def advance_connection_source_cursors(
        self,
        *,
        connection_id: str,
        observe_cursor: EventCursor | None = None,
        observe_event_name: str | None = None,
        live_cursor: EventCursor | None = None,
        live_event_name: str | None = None,
    ) -> ChannelConnectionBinding | None:
        metadata_updates: dict[str, Any] = {}
        if observe_cursor is not None:
            metadata_updates["observe_cursor"] = observe_cursor
        if live_cursor is not None:
            metadata_updates["live_cursor"] = live_cursor
        if not metadata_updates:
            return self.runtime_manager.resolve_connection_binding(
                channel_type="web",
                connection_id=connection_id,
            )
        return self.runtime_manager.merge_connection_metadata(
            channel_type="web",
            connection_id=connection_id,
            metadata=metadata_updates,
        )

    def get_connection_observe_source_cursor(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
    ) -> EventCursor | None:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return None
        binding = self.runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id=connection_id,
        )
        if binding is None:
            return None
        raw_cursor = binding.metadata.get("observe_cursor")
        if isinstance(raw_cursor, str) and raw_cursor.strip():
            return raw_cursor.strip()
        return None

    def get_connection_live_source_cursor(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
    ) -> EventCursor | None:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return None
        binding = self.runtime_manager.resolve_connection_binding(
            channel_type="web",
            connection_id=connection_id,
        )
        if binding is not None:
            raw_cursor = binding.metadata.get("live_cursor")
            if isinstance(raw_cursor, str) and raw_cursor.strip():
                return raw_cursor.strip()
        return None

    def read_connection_observe_records(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
        limit: int = 100,
    ) -> tuple[EventTopicRecord, ...]:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return ()
        self.ensure_connection_source_cursors(
            connection_id=connection_id,
            conversation_id=normalized_conversation_id,
        )
        records = self.events_service.read_event_topic(
            turn_session_topic(normalized_conversation_id),
            after_cursor=self.get_connection_observe_source_cursor(
                connection_id=connection_id,
                conversation_id=normalized_conversation_id,
            ),
            limit=limit,
        )
        if records:
            self.advance_connection_source_cursors(
                connection_id=connection_id,
                observe_cursor=records[-1].cursor,
                observe_event_name=records[-1].envelope.event_name,
            )
        return records

    def read_connection_live_records(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
        limit: int = 1,
    ) -> tuple[EventTopicRecord, ...]:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        if normalized_conversation_id is None:
            return ()
        self.ensure_connection_source_cursors(
            connection_id=connection_id,
            conversation_id=normalized_conversation_id,
        )
        records = self.events_service.read_event_topic(
            turn_session_live_topic(normalized_conversation_id),
            after_cursor=self.get_connection_live_source_cursor(
                connection_id=connection_id,
                conversation_id=normalized_conversation_id,
            ),
            limit=limit,
        )
        if records:
            self.advance_connection_source_cursors(
                connection_id=connection_id,
                live_cursor=records[-1].cursor,
                live_event_name=records[-1].envelope.event_name,
            )
        return records

    def build_connection_wait_watches(
        self,
        *,
        connection_id: str,
        conversation_id: str | None,
        broadcast_topics: tuple[str, ...] = (),
        broadcast_cursors: dict[str, EventCursor | None] | None = None,
    ) -> tuple[EventTopicWatch, ...]:
        normalized_conversation_id = (
            conversation_id.strip()
            if isinstance(conversation_id, str) and conversation_id.strip()
            else None
        )
        watches: list[EventTopicWatch] = []
        if normalized_conversation_id is not None:
            self.ensure_connection_source_cursors(
                connection_id=connection_id,
                conversation_id=normalized_conversation_id,
            )
            watches.append(
                EventTopicWatch(
                    topic=turn_session_live_topic(normalized_conversation_id),
                    after_cursor=self.get_connection_live_source_cursor(
                        connection_id=connection_id,
                        conversation_id=normalized_conversation_id,
                    ),
                )
            )
            watches.append(
                EventTopicWatch(
                    topic=turn_session_topic(normalized_conversation_id),
                    after_cursor=self.get_connection_observe_source_cursor(
                        connection_id=connection_id,
                        conversation_id=normalized_conversation_id,
                    ),
                )
            )
        if broadcast_cursors is not None:
            for topic in broadcast_topics:
                watches.append(
                    EventTopicWatch(
                        topic=topic,
                        after_cursor=broadcast_cursors.get(topic),
                    )
                )
        return tuple(watches)
