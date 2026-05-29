from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import logging
from threading import Event as ThreadEvent, Lock, Thread
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import requests

from crxzipple.modules.artifacts.domain import (
    ArtifactError,
    ArtifactKind,
    ArtifactVariant,
)
from crxzipple.modules.channels.application.services import (
    ChannelInteractionService,
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.application.bindings import (
    ChannelCredentialResolutionError,
    collect_channel_access_requirements,
    mask_channel_metadata,
    resolve_channel_metadata_binding,
)
from crxzipple.modules.channels.application.ports import (
    ChannelAccessReadinessPort,
    ChannelAgentProfilePort,
    ChannelArtifactReadPort,
    ChannelEventStreamPort,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountRuntimeBinding,
    ChannelCapabilities,
    ChannelConnectionBinding,
    ChannelInteraction,
    ChannelProfile,
    ChannelRuntimeRegistration,
    ChannelRuntimeRegistry,
    ChannelValidationError,
    channel_dead_letter_topic,
)
from crxzipple.modules.events import (
    EventAddress,
    EventCursor,
    Event,
    EventTopicRecord,
    EventTopicWatch,
)
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.shared import (
    ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT,
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    ReplyAddress,
)
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
)
from crxzipple.shared.http import request_url
from crxzipple.shared.access import AccessConsumerRef, CredentialProvider

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.ports import (
        OrchestrationRunLookupPort,
        OrchestrationSubmissionPort,
    )


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LarkTenantAccessToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LarkBotIdentity:
    open_id: str
    expires_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_channel_account_profile(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
):
    if profile is None:
        return None
    normalized_account = channel_account_id.strip()
    if not normalized_account:
        return None
    for item in profile.accounts:
        if item.account_id.strip() == normalized_account:
            return item
    return None


def _extract_text_message(message: dict[str, Any]) -> str:
    raw_text = message.get("text")
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text
    raw_content = message.get("content")
    if isinstance(raw_content, str) and raw_content.strip():
        return raw_content.strip()
    content_payload = message.get("content_payload")
    if isinstance(content_payload, dict):
        raw_payload_text = content_payload.get("text")
        if isinstance(raw_payload_text, str) and raw_payload_text.strip():
            return raw_payload_text
        raw_blocks = content_payload.get("blocks")
        if isinstance(raw_blocks, list):
            parts: list[str] = []
            for item in raw_blocks:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").strip().lower() != "text":
                    continue
                raw_block_text = item.get("text")
                if isinstance(raw_block_text, str) and raw_block_text.strip():
                    parts.append(raw_block_text)
            if parts:
                return "".join(parts)
    serialized = json.dumps(message, ensure_ascii=False)
    return serialized if serialized != "{}" else ""


class ChannelRuntimeBootstrapService:
    def __init__(
        self,
        *,
        profile_service: ChannelProfileApplicationService,
        runtime_manager: ChannelRuntimeManager,
        access_service: ChannelAccessReadinessPort | None = None,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        self.profile_service = profile_service
        self.runtime_manager = runtime_manager
        self.access_service = access_service
        self.credential_provider = credential_provider or access_service

    def ensure_registered(
        self,
        channel_type: str,
        *,
        runtime_id: str | None = None,
        service_key: str | None = None,
        status: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        normalized_channel = channel_type.strip().lower()
        resolved_runtime_id = runtime_id or f"{normalized_channel}-runtime-1"
        resolved_service_key = service_key or f"channel:{normalized_channel}"
        profile = self.profile_service.get_profile(normalized_channel)
        if profile is not None and not profile.enabled:
            raise ChannelValidationError(
                f"Channel '{normalized_channel}' profile is disabled.",
                code="channel_profile_disabled",
                details={"channel_type": normalized_channel},
            )
        self._ensure_profile_access_ready(normalized_channel, profile)
        existing = self.runtime_manager.get_runtime(resolved_runtime_id)
        capabilities = (
            profile.capabilities
            if profile is not None
            else ChannelCapabilities()
        )
        resolved_metadata = {
            **(dict(existing.metadata) if existing is not None else {}),
            **dict(metadata or {}),
        }
        registration = self.runtime_manager.register_runtime(
            ChannelRuntimeRegistration(
                runtime_id=resolved_runtime_id,
                channel_type=normalized_channel,
                service_key=resolved_service_key,
                status=status,
                capabilities=capabilities,
                metadata=resolved_metadata,
            ),
        )
        self._sync_profile_accounts(runtime_id=registration.runtime_id, profile=profile)
        return registration

    def heartbeat(self, runtime_id: str) -> ChannelRuntimeRegistration | None:
        return self.runtime_manager.heartbeat_runtime(runtime_id)

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
        stopper = stop_event or ThreadEvent()
        registration = self.ensure_registered(
            channel_type,
            runtime_id=runtime_id,
            service_key=service_key,
            metadata=metadata,
        )
        completed_cycles = 0
        while not stopper.is_set():
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            stopper.wait(max(float(poll_interval_seconds), 0.05))
            refreshed = self.heartbeat(registration.runtime_id)
            if refreshed is not None:
                registration = refreshed
        return registration

    def unregister_runtime(self, runtime_id: str) -> ChannelRuntimeRegistry:
        return self.runtime_manager.unregister_runtime(runtime_id)

    def _sync_profile_accounts(
        self,
        *,
        runtime_id: str,
        profile: ChannelProfile | None,
    ) -> None:
        if profile is None:
            return
        for account in profile.accounts:
            if not account.enabled:
                continue
            self.runtime_manager.bind_account(
                ChannelAccountRuntimeBinding(
                    channel_type=profile.channel_type,
                    channel_account_id=account.account_id,
                    runtime_id=runtime_id,
                    metadata={
                        "transport_mode": account.transport_mode,
                        **mask_channel_metadata(account.metadata),
                    },
                ),
            )

    def _ensure_profile_access_ready(
        self,
        channel_type: str,
        profile: ChannelProfile | None,
    ) -> None:
        if self.access_service is None or profile is None:
            return
        requirements = self._profile_access_requirements(profile)
        if not requirements:
            return
        readiness = self.access_service.check_requirements(requirements)
        missing = tuple(item for item in readiness if not item.ready)
        if not missing:
            return
        reason = "; ".join(
            f"{item.requirement.raw}: {item.reason}" for item in missing
        )
        raise ChannelValidationError(
            f"Channel '{channel_type}' access is not ready. {reason}",
            code="access_not_ready",
            details={
                "resource_type": "channel_runtime",
                "resource_id": channel_type,
                "access": [item.to_payload() for item in missing],
            },
        )

    def profile_access_requirements(
        self,
        profile: ChannelProfile,
    ) -> tuple[str, ...]:
        return self._profile_access_requirements(profile)

    def _profile_access_requirements(
        self,
        profile: ChannelProfile,
    ) -> tuple[str, ...]:
        resolved: list[str] = []
        for requirement in collect_channel_access_requirements(profile.metadata):
            if requirement not in resolved:
                resolved.append(requirement)
        for account in profile.accounts:
            if not account.enabled:
                continue
            for binding_id in account.credential_bindings.values():
                if isinstance(binding_id, str) and binding_id.strip():
                    normalized_binding = binding_id.strip()
                    if normalized_binding not in resolved:
                        resolved.append(normalized_binding)
            for requirement in collect_channel_access_requirements(account.metadata):
                if requirement not in resolved:
                    resolved.append(requirement)
        return tuple(resolved)

    def _access_consumer(
        self,
        *,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        field: str | None = None,
        runtime_ref: str | None = None,
    ) -> AccessConsumerRef:
        normalized_channel = channel_type.strip().lower()
        account = (
            channel_account_id.strip()
            if isinstance(channel_account_id, str) and channel_account_id.strip()
            else None
        )
        consumer_id = f"channels.{normalized_channel}"
        if account is not None:
            consumer_id = f"{consumer_id}.account:{account}"
        if field is not None and field.strip():
            consumer_id = f"{consumer_id}.{field.strip()}"
        return AccessConsumerRef(
            consumer_id=consumer_id,
            module="channels",
            component=component,
            runtime_ref=runtime_ref or normalized_channel,
            metadata={
                "channel_type": normalized_channel,
                "channel_account_id": account,
                "field": field,
            },
        )

    def _resolve_metadata_credential(
        self,
        metadata: dict[str, Any],
        *,
        key: str,
        description: str,
        required: bool,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        runtime_ref: str | None = None,
    ) -> str | None:
        return resolve_channel_metadata_binding(
            metadata,
            key=key,
            description=description,
            required=required,
            credential_provider=self.credential_provider,
            consumer=self._access_consumer(
                channel_type=channel_type,
                component=component,
                channel_account_id=channel_account_id,
                field=key,
                runtime_ref=runtime_ref,
            ),
        )


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


class LarkChannelRuntimeService(ChannelRuntimeBootstrapService):
    max_delivery_attempts: int = 3
    bot_identity_ttl_seconds: int = 3600

    def __init__(
        self,
        *,
        agent_service: ChannelAgentProfilePort,
        orchestration_submission_port: "OrchestrationSubmissionPort",
        orchestration_run_lookup: "OrchestrationRunLookupPort",
        artifact_service: ChannelArtifactReadPort,
        interaction_service: ChannelInteractionService,
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
        self.agent_service = agent_service
        self.orchestration_submission_port = orchestration_submission_port
        self.orchestration_run_lookup = orchestration_run_lookup
        self.artifact_service = artifact_service
        self.interaction_service = interaction_service
        self.events_service = events_service
        self._tenant_access_tokens: dict[str, LarkTenantAccessToken] = {}
        self._token_lock = Lock()
        self._bot_identities: dict[str, LarkBotIdentity] = {}
        self._bot_identity_lock = Lock()
        self._ingress_threads: dict[str, Thread] = {}
        self._ingress_lock = Lock()

    def _profile_access_requirements(
        self,
        profile: ChannelProfile,
    ) -> tuple[str, ...]:
        resolved = list(super()._profile_access_requirements(profile))
        for account in profile.accounts:
            if not account.enabled:
                continue
            for requirement in collect_channel_access_requirements(
                account.metadata,
                binding_keys=("lark_app_id", "lark_app_secret"),
            ):
                if requirement not in resolved:
                    resolved.append(requirement)
        return tuple(resolved)

    def ensure_registered(
        self,
        *,
        runtime_id: str = "lark-runtime-1",
        service_key: str = "channel:lark",
        status: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        return super().ensure_registered(
            "lark",
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
            runtime_id=runtime_id or "lark-runtime-1",
            service_key=service_key or "channel:lark",
            metadata=metadata,
        )
        self._ensure_long_connection_ingress(
            registration.runtime_id,
            stop_event=stopper,
        )
        completed_cycles = 0
        while not stopper.is_set():
            observed_count = self.observe_pending_interactions(
                registration.runtime_id,
                limit=100,
            )
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            if not observed_count:
                self.wait_for_runtime_activity(
                    registration.runtime_id,
                    timeout_seconds=max(float(poll_interval_seconds), 0.05),
                    stop_event=stopper,
                )
        return registration

    def wait_for_runtime_activity(
        self,
        runtime_id: str,
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        watches: list[EventTopicWatch] = []
        for interaction in self._active_observe_interactions(runtime_id):
            if interaction.session_key is None:
                continue
            watches.append(
                EventTopicWatch(
                    topic=turn_session_topic(interaction.session_key),
                    after_cursor=self._interaction_observe_cursor(interaction),
                ),
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

    def observe_pending_interactions(
        self,
        runtime_id: str,
        *,
        limit: int = 100,
    ) -> int:
        registration = self.runtime_manager.get_runtime(runtime_id)
        if registration is None:
            return 0
        observed_count = 0
        transitioned_count = 0
        last_event_name: str | None = None
        last_interaction_id: str | None = None
        for interaction in self._active_observe_interactions(runtime_id):
            if interaction.session_key is None:
                continue
            seeded_cursor = self._interaction_observe_cursor(interaction)
            records = self.events_service.read_event_topic(
                turn_session_topic(interaction.session_key),
                after_cursor=seeded_cursor,
                limit=limit,
            )
            if not records:
                continue
            updated_interaction = interaction
            interaction_changed = False
            acked_records: list[EventTopicRecord] = []
            for record in records:
                candidate = self._apply_observe_record_to_interaction(
                    updated_interaction,
                    record=record,
                )
                if candidate.status != updated_interaction.status:
                    transitioned_count += 1
                current_event_name = record.envelope.event_name or ""
                try:
                    delivered = self._deliver_observe_record_to_channel(
                        candidate,
                        record=record,
                    )
                except (
                    ArtifactError,
                    requests.RequestException,
                    ValueError,
                    RuntimeError,
                ) as exc:
                    updated_interaction = replace(
                        candidate,
                        metadata={
                            **dict(candidate.metadata),
                            "last_delivery_error": str(exc).strip()
                            or exc.__class__.__name__,
                            "last_delivery_failed_event_name": current_event_name or None,
                            "last_delivery_failed_at": _utcnow().isoformat(),
                        },
                    )
                    interaction_changed = True
                    last_interaction_id = updated_interaction.interaction_id
                    last_event_name = current_event_name or last_event_name
                    break
                if delivered is not updated_interaction:
                    interaction_changed = True
                updated_interaction = delivered
                acked_records.append(record)
                observed_count += 1
                last_interaction_id = delivered.interaction_id
                last_event_name = current_event_name or last_event_name
            if not interaction_changed and not acked_records:
                continue
            final_metadata = {
                **dict(updated_interaction.metadata),
                "observe_cursor": (
                    acked_records[-1].cursor
                    if acked_records
                    else seeded_cursor
                ),
                "last_observed_cursor": (
                    acked_records[-1].cursor
                    if acked_records
                    else updated_interaction.metadata.get("last_observed_cursor")
                ),
                "last_observed_event_name": (
                    last_event_name
                    or updated_interaction.metadata.get("last_observed_event_name")
                ),
                "last_observed_at": (
                    acked_records[-1].envelope.created_at.isoformat()
                    if acked_records
                    else updated_interaction.metadata.get("last_observed_at")
                ),
            }
            persisted = self.interaction_service.upsert_interaction(
                replace(
                    updated_interaction,
                    metadata=final_metadata,
                ),
            )
            if persisted.status != interaction.status:
                interaction_changed = True
            if interaction_changed:
                last_interaction_id = persisted.interaction_id
        if observed_count:
            current_observed_total = registration.metadata.get("observe_observed_count", 0)
            current_transition_total = registration.metadata.get("observe_transition_count", 0)
            try:
                observed_total = int(current_observed_total)
            except (TypeError, ValueError):
                observed_total = 0
            try:
                transition_total = int(current_transition_total)
            except (TypeError, ValueError):
                transition_total = 0
            self.runtime_manager.merge_runtime_metadata(
                runtime_id,
                metadata={
                    "observe_observed_count": observed_total + observed_count,
                    "observe_transition_count": transition_total + transitioned_count,
                    "last_observe_event_name": last_event_name,
                    "last_observe_interaction_id": last_interaction_id,
                },
                touch_heartbeat=True,
            )
        return observed_count

    def _active_observe_interactions(
        self,
        runtime_id: str,
    ) -> tuple[ChannelInteraction, ...]:
        account_ids = {
            binding.channel_account_id
            for binding in self.runtime_manager.list_account_bindings(
                runtime_id=runtime_id,
                channel_type="lark",
            )
        }
        interactions = self.interaction_service.list_interactions(channel_type="lark")
        return tuple(
            item
            for item in interactions
            if (
                item.channel_account_id in account_ids
                and isinstance(item.run_id, str)
                and item.run_id.strip()
                and isinstance(item.session_key, str)
                and item.session_key.strip()
                and not self._interaction_observe_settled(item)
            )
        )

    @staticmethod
    def _interaction_observe_settled(
        interaction: ChannelInteraction,
    ) -> bool:
        normalized_status = str(interaction.status or "").strip().lower()
        if normalized_status in {"failed", "cancelled"}:
            return True
        if normalized_status != "completed":
            return False
        metadata = dict(interaction.metadata)
        last_message_id = str(metadata.get("last_message_id") or "").strip()
        last_delivered_message_id = str(
            metadata.get("last_delivered_message_id") or "",
        ).strip()
        delivery_status = str(metadata.get("last_delivery_status") or "").strip().lower()
        if last_message_id:
            return (
                last_delivered_message_id == last_message_id
                and delivery_status == "ok"
            )
        return False

    @staticmethod
    def _interaction_observe_cursor(
        interaction: ChannelInteraction,
    ) -> EventCursor | None:
        raw_cursor = interaction.metadata.get("observe_cursor")
        if isinstance(raw_cursor, str) and raw_cursor.strip():
            return raw_cursor.strip()
        return None

    def _apply_observe_record_to_interaction(
        self,
        interaction: ChannelInteraction,
        *,
        record: EventTopicRecord,
    ) -> ChannelInteraction:
        payload = dict(record.envelope.payload or {})
        event_name = record.envelope.event_name or ""
        if not event_name:
            return interaction
        if event_name == ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT:
            observation = self._observe_session_message_fact(payload)
            return replace(
                interaction,
                metadata={
                    **dict(interaction.metadata),
                    **observation,
                },
            )
        if event_name == ORCHESTRATION_RUN_TOOL_UPDATED_EVENT:
            return replace(
                interaction,
                metadata={
                    **dict(interaction.metadata),
                    "last_tool_event_name": event_name,
                    "last_tool_source_event_name": payload.get("source_event_name"),
                    "last_tool_run_id": payload.get("tool_run_id"),
                    "last_tool_id": payload.get("tool_id"),
                    "last_tool_name": payload.get("tool_name"),
                    "last_tool_status": payload.get("tool_status"),
                    "last_tool_updated_at": (
                        payload.get("completed_at")
                        or payload.get("started_at")
                        or payload.get("created_at")
                    ),
                },
            )
        run_id = str(payload.get("run_id") or "").strip()
        if run_id and run_id != str(interaction.run_id or "").strip():
            return interaction
        resolved_status = self._interaction_status_from_observe_fact(
            current_status=interaction.status,
            event_name=event_name,
            payload=payload,
        )
        return replace(
            interaction,
            status=resolved_status,
            metadata={
                **dict(interaction.metadata),
                "last_run_event_name": event_name,
                "stage": payload.get("stage"),
                "current_step": payload.get("current_step"),
                "waiting_reason": payload.get("waiting_reason"),
                "pending_tool_run_ids": list(payload.get("pending_tool_run_ids") or []),
                "active_session_id": payload.get("active_session_id"),
            },
        )

    @staticmethod
    def _interaction_status_from_observe_fact(
        *,
        current_status: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> str:
        raw_status = str(payload.get("status") or "").strip().lower()
        if raw_status:
            return raw_status
        normalized_event_name = event_name.strip().lower()
        if normalized_event_name.endswith(".completed"):
            return "completed"
        if normalized_event_name.endswith(".failed"):
            return "failed"
        if normalized_event_name.endswith(".cancelled"):
            return "cancelled"
        if ".waiting" in normalized_event_name:
            return "waiting"
        if normalized_event_name.endswith(".queued"):
            return "queued"
        return current_status

    def _observe_session_message_fact(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        message = dict(payload.get("message") or {})
        content_payload = dict(message.get("content_payload") or {})
        blocks = content_blocks_from_payload(content_payload)
        artifact_refs = self._extract_artifact_refs_from_blocks(blocks)
        block_types = [
            str(block.get("type") or "").strip()
            for block in blocks
            if str(block.get("type") or "").strip()
        ]
        text_fragments = [
            str(block.get("text") or "")
            for block in blocks
            if str(block.get("type") or "").strip() == "text"
            and str(block.get("text") or "").strip()
        ]
        summary_text = "\n".join(text_fragments) if text_fragments else None
        if summary_text is None and content_payload:
            summary_text = describe_content_for_text_fallback(content_payload)
        observation: dict[str, Any] = {
            "last_message_id": str(payload.get("message_id") or "").strip() or None,
            "last_message_role": str(payload.get("role") or "").strip() or None,
            "last_message_kind": str(payload.get("kind") or "").strip() or None,
            "last_message_source_kind": (
                str(payload.get("source_kind") or "").strip() or None
            ),
            "last_message_source_id": (
                str(payload.get("source_id") or "").strip() or None
            ),
            "last_message_created_at": message.get("created_at"),
            "last_message_summary": summary_text,
            "last_message_block_types": block_types,
            "last_message_artifact_refs": artifact_refs,
            "last_message_has_image_artifacts": any(
                block_type in {"image", "image_ref"}
                for block_type in block_types
            ),
            "last_message_has_file_artifacts": any(
                block_type in {"file", "file_ref"}
                for block_type in block_types
            ),
        }
        if observation["last_message_kind"] == "tool_result":
            observation["last_tool_result"] = {
                "tool_name": (
                    str(content_payload.get("tool_name") or "").strip() or None
                ),
                "tool_call_id": (
                    str(content_payload.get("tool_call_id") or "").strip() or None
                ),
                "tool_run_id": (
                    str(content_payload.get("tool_run_id") or "").strip() or None
                ),
                "status": str(content_payload.get("status") or "").strip() or None,
                "summary": summary_text,
                "artifact_refs": artifact_refs,
            }
        if observation["last_message_role"] == "assistant":
            observation["last_assistant_message_summary"] = summary_text
            observation["last_assistant_message_artifact_refs"] = artifact_refs
        return observation

    @staticmethod
    def _extract_artifact_refs_from_blocks(
        blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        artifact_refs: list[dict[str, Any]] = []
        for block in blocks:
            artifact_id = str(block.get("artifact_id") or "").strip()
            if not artifact_id:
                continue
            artifact_refs.append(
                {
                    "type": str(block.get("type") or "").strip() or None,
                    "artifact_id": artifact_id,
                    "mime_type": str(block.get("mime_type") or "").strip() or None,
                    "name": str(block.get("name") or "").strip() or None,
                    "preview_url": str(block.get("preview_url") or "").strip() or None,
                    "original_url": str(block.get("original_url") or "").strip() or None,
                    "download_url": str(block.get("download_url") or "").strip() or None,
                }
            )
        return artifact_refs

    def _deliver_observe_record_to_channel(
        self,
        interaction: ChannelInteraction,
        *,
        record: EventTopicRecord,
    ) -> ChannelInteraction:
        payload = dict(record.envelope.payload or {})
        event_name = record.envelope.event_name or ""
        if event_name != ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT:
            return interaction
        role = str(payload.get("role") or "").strip().lower()
        kind = str(payload.get("kind") or "").strip().lower()
        if role != "assistant" and kind != "tool_result":
            return interaction
        message_id = str(payload.get("message_id") or "").strip()
        if not message_id:
            return interaction
        current_metadata = dict(interaction.metadata)
        if (
            str(current_metadata.get("last_delivered_message_id") or "").strip()
            == message_id
            and str(current_metadata.get("last_delivery_status") or "").strip().lower()
            == "ok"
        ):
            return interaction
        reply_address = dict(interaction.reply_address or {})
        account_id, base_url, receive_id_type, receive_id = self._resolve_reply_target_payload(
            reply_address,
            fallback_channel_account_id=interaction.channel_account_id,
        )
        token = self._tenant_access_token_for_account(
            account_id,
            base_url=base_url,
        )
        payloads, artifact_ids = self._build_observe_message_payloads(
            interaction,
            payload=payload,
            receive_id=receive_id,
            reply_address=reply_address,
            base_id=message_id,
            base_url=base_url,
            token=token,
        )
        if not payloads:
            return interaction
        message_types = self._send_lark_payloads(
            base_url=base_url,
            token=token,
            receive_id_type=receive_id_type,
            payloads=payloads,
        )
        delivered_artifact_ids = [
            str(item).strip()
            for item in current_metadata.get("delivered_artifact_ids", [])
            if str(item).strip()
        ]
        for artifact_id in artifact_ids:
            normalized_artifact_id = str(artifact_id).strip()
            if normalized_artifact_id and normalized_artifact_id not in delivered_artifact_ids:
                delivered_artifact_ids.append(normalized_artifact_id)
        return replace(
            interaction,
            metadata={
                **current_metadata,
                "last_delivered_message_id": message_id,
                "last_delivered_message_role": role or None,
                "last_delivered_message_kind": kind or None,
                "last_delivery_status": "ok",
                "last_delivery_message_types": message_types,
                "delivered_artifact_ids": delivered_artifact_ids,
                "last_delivery_error": None,
                "last_delivered_at": _utcnow().isoformat(),
            },
        )

    def _upload_lark_image(
        self,
        *,
        account_id: str,
        base_url: str,
        token: str,
        artifact_id: str,
    ) -> str:
        del account_id
        resolved = self.artifact_service.resolve_variant(
            artifact_id,
            variant=ArtifactVariant.PREVIEW,
        )
        with resolved.path.open("rb") as handle:
            response = request_url(
                "POST",
                f"{base_url}/open-apis/im/v1/images",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                data={
                    "image_type": "message",
                },
                files={
                    "image": (
                        resolved.artifact.name or resolved.path.name,
                        handle,
                        resolved.artifact.mime_type,
                    ),
                },
                timeout=30,
            )
        response_payload = response.json()
        code = response_payload.get("code")
        image_key = str(
            dict(response_payload.get("data") or {}).get("image_key") or "",
        ).strip()
        if response.status_code != 200 or code not in {0, "0", None} or not image_key:
            raise RuntimeError(
                f"lark_image_upload_failed:{response.status_code}:code_{code}",
            )
        return image_key

    def _upload_lark_file(
        self,
        *,
        account_id: str,
        base_url: str,
        token: str,
        artifact_id: str,
    ) -> str:
        del account_id
        resolved = self.artifact_service.resolve_variant(
            artifact_id,
            variant=ArtifactVariant.ORIGINAL,
        )
        with resolved.path.open("rb") as handle:
            response = request_url(
                "POST",
                f"{base_url}/open-apis/im/v1/files",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                data={
                    "file_type": "stream",
                    "file_name": resolved.artifact.name or resolved.path.name,
                },
                files={
                    "file": (
                        resolved.artifact.name or resolved.path.name,
                        handle,
                        resolved.artifact.mime_type,
                    ),
                },
                timeout=30,
            )
        response_payload = response.json()
        code = response_payload.get("code")
        file_key = str(
            dict(response_payload.get("data") or {}).get("file_key") or "",
        ).strip()
        if response.status_code != 200 or code not in {0, "0", None} or not file_key:
            raise RuntimeError(
                f"lark_file_upload_failed:{response.status_code}:code_{code}",
            )
        return file_key

    @staticmethod
    def _interaction_reply_artifact_refs(
        interaction: ChannelInteraction | None,
    ) -> tuple[dict[str, Any], ...]:
        if interaction is None:
            return ()
        metadata = dict(interaction.metadata)
        candidates: list[dict[str, Any]] = []
        tool_result = metadata.get("last_tool_result")
        if isinstance(tool_result, dict):
            raw_refs = tool_result.get("artifact_refs")
            if isinstance(raw_refs, list):
                candidates.extend(
                    item
                    for item in raw_refs
                    if isinstance(item, dict)
                )
        for key in (
            "last_assistant_message_artifact_refs",
            "last_message_artifact_refs",
        ):
            raw_refs = metadata.get(key)
            if isinstance(raw_refs, list):
                candidates.extend(
                    item
                    for item in raw_refs
                    if isinstance(item, dict)
                )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            artifact_id = str(item.get("artifact_id") or "").strip()
            if not artifact_id or artifact_id in seen:
                continue
            seen.add(artifact_id)
            deduped.append(dict(item))
        return tuple(deduped)

    def _resolve_reply_target_payload(
        self,
        reply_address: dict[str, Any],
        *,
        fallback_channel_account_id: str | None = None,
    ) -> tuple[str, str, str, str]:
        account_id = str(reply_address.get("channel_account_id") or "").strip()
        if not account_id:
            account_id = str(fallback_channel_account_id or "").strip()
        if not account_id:
            raise ValueError("missing_channel_account_id")
        account_profile = self._require_account_profile(account_id)
        metadata = dict(account_profile.metadata)
        reply_metadata = (
            dict(reply_address.get("metadata") or {})
            if isinstance(reply_address.get("metadata"), dict)
            else {}
        )
        explicit_receive_id_type = str(metadata.get("lark_receive_id_type") or "").strip()
        receive_id_type = explicit_receive_id_type or str(
            reply_metadata.get("receive_id_type") or "",
        ).strip() or str(metadata.get("lark_default_receive_id_type") or "").strip()
        if not receive_id_type:
            chat_type = str(reply_metadata.get("chat_type") or "").strip().lower()
            receive_id_type = "open_id" if chat_type == "direct" else "chat_id"
        if not receive_id_type:
            receive_id_type = "chat_id"
        if receive_id_type == "chat_id":
            receive_id = str(reply_address.get("external_conversation_id") or "").strip()
        elif receive_id_type == "open_id":
            receive_id = str(reply_address.get("external_user_id") or "").strip()
        else:
            raise ValueError("unsupported_receive_id_type")
        if not receive_id:
            raise ValueError("missing_receive_id")
        base_url = str(metadata.get("lark_base_url") or "https://open.feishu.cn").strip()
        if not base_url:
            base_url = "https://open.feishu.cn"
        return account_id, base_url.rstrip("/"), receive_id_type, receive_id

    def _build_observe_message_payloads(
        self,
        interaction: ChannelInteraction,
        *,
        payload: dict[str, Any],
        receive_id: str,
        reply_address: dict[str, Any],
        base_id: str,
        base_url: str,
        token: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        metadata = dict(interaction.metadata)
        summary_text = str(metadata.get("last_message_summary") or "").strip()
        payloads: list[dict[str, Any]] = []
        if summary_text:
            payloads.append(
                self._build_lark_message_payload(
                    receive_id=receive_id,
                    reply_address=reply_address,
                    msg_type="text",
                    content={"text": summary_text},
                    base_id=base_id,
                    message_key="text",
                ),
            )
        delivered_artifact_ids = {
            str(item).strip()
            for item in metadata.get("delivered_artifact_ids", [])
            if str(item).strip()
        }
        artifact_ids: list[str] = []
        for artifact_ref in self._interaction_reply_artifact_refs(interaction):
            artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
            if not artifact_id or artifact_id in delivered_artifact_ids:
                continue
            payload = self._build_observe_artifact_payload(
                receive_id=receive_id,
                reply_address=reply_address,
                artifact_ref=artifact_ref,
                base_id=base_id,
                base_url=base_url,
                token=token,
            )
            if payload is None:
                continue
            payloads.append(payload)
            artifact_ids.append(artifact_id)
        return payloads, artifact_ids

    def _build_observe_artifact_payload(
        self,
        *,
        receive_id: str,
        reply_address: dict[str, Any],
        artifact_ref: dict[str, Any],
        base_id: str,
        base_url: str,
        token: str,
    ) -> dict[str, Any] | None:
        artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
        if not artifact_id:
            return None
        artifact = self.artifact_service.get_artifact(artifact_id)
        if artifact.kind is ArtifactKind.IMAGE:
            image_key = self._upload_lark_image(
                account_id="",
                base_url=base_url,
                token=token,
                artifact_id=artifact_id,
            )
            return self._build_lark_message_payload(
                receive_id=receive_id,
                reply_address=reply_address,
                msg_type="image",
                content={"image_key": image_key},
                base_id=base_id,
                message_key=f"image:{artifact_id}",
            )
        file_key = self._upload_lark_file(
            account_id="",
            base_url=base_url,
            token=token,
            artifact_id=artifact_id,
        )
        return self._build_lark_message_payload(
            receive_id=receive_id,
            reply_address=reply_address,
            msg_type="file",
            content={"file_key": file_key},
            base_id=base_id,
            message_key=f"file:{artifact_id}",
        )

    def _send_lark_payloads(
        self,
        *,
        base_url: str,
        token: str,
        receive_id_type: str,
        payloads: list[dict[str, Any]],
    ) -> list[str]:
        delivered_message_types: list[str] = []
        for payload in payloads:
            response = request_url(
                "POST",
                f"{base_url}/open-apis/im/v1/messages",
                params={"receive_id_type": receive_id_type},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
                timeout=10,
            )
            response_payload = response.json()
            code = response_payload.get("code")
            if response.status_code != 200 or code not in {0, "0", None}:
                raise RuntimeError(f"http_{response.status_code}:code_{code}")
            delivered_message_types.append(
                str(payload.get("msg_type") or "").strip() or "text",
            )
        return delivered_message_types

    def _build_lark_message_payload(
        self,
        *,
        receive_id: str,
        reply_address: dict[str, Any],
        msg_type: str,
        content: dict[str, Any],
        base_id: str,
        message_key: str,
    ) -> dict[str, Any]:
        reply_metadata = (
            dict(reply_address.get("metadata") or {})
            if isinstance(reply_address.get("metadata"), dict)
            else {}
        )
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
            "uuid": (
                base_id
                if base_id and message_key == "text"
                else f"{base_id}:{message_key}"
                if base_id
                else None
            ),
        }
        reply_in_thread = bool(reply_metadata.get("reply_in_thread"))
        thread_id = str(reply_address.get("external_thread_id") or "").strip()
        message_id = str(reply_metadata.get("message_id") or "").strip()
        if reply_in_thread and thread_id:
            payload["reply_in_thread"] = True
            payload["thread_id"] = thread_id
        if message_id:
            payload["reply_message_id"] = message_id
        return payload

    def submit_message_event(
        self,
        channel_account_id: str,
        *,
        event_id: str | None,
        sender_open_id: str | None,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        from crxzipple.modules.orchestration.application.turn_submission import (
            build_submission_options,
            resolve_profile,
            submit_turn,
        )
        from crxzipple.modules.channels.application.lark_messages import (
            extract_lark_mentions,
            is_truthy,
            normalize_lark_chat_type,
            normalize_lark_message_content,
            parse_lark_message_content,
            should_accept_lark_message,
        )
        from crxzipple.modules.orchestration.domain import (
            OrchestrationQueuePolicy,
            OrchestrationValidationError,
        )
        from crxzipple.modules.session.domain import DirectSessionScope
        normalized_account = channel_account_id.strip()
        if not normalized_account:
            raise ValueError("channel_account_id is required")
        account_profile = self._require_account_profile(normalized_account)
        account_metadata = dict(account_profile.metadata)
        agent_id = str(account_metadata.get("agent_id") or "").strip() or None
        llm_id = str(account_metadata.get("llm_id") or "").strip() or None
        profile, error = resolve_profile(
            self.agent_service,
            agent_id=agent_id,
        )
        if profile is None:
            raise ValueError(error or "Agent profile was not found.")
        chat_id = str(message.get("chat_id") or "").strip()
        if not chat_id:
            raise ValueError("Lark message is missing chat_id.")
        normalized_chat_type = normalize_lark_chat_type(message.get("chat_type"))
        _, parsed_content = parse_lark_message_content(message)
        mentions = extract_lark_mentions(
            message=message,
            parsed_content=parsed_content,
        )
        effective_account_metadata = dict(account_metadata)
        if (
            normalized_chat_type == "group"
            and is_truthy(account_metadata.get("lark_group_require_bot_mention"))
            and not self._resolve_metadata_credential(
                account_metadata,
                key="lark_bot_open_id",
                description="Lark bot open id",
                required=False,
                channel_type="lark",
                component="message_ingress",
                channel_account_id=normalized_account,
            )
        ):
            resolved_bot_open_id = self.resolve_bot_open_id_for_account(
                normalized_account,
            )
            if resolved_bot_open_id:
                effective_account_metadata["lark_bot_open_id"] = resolved_bot_open_id
        if not should_accept_lark_message(
            account_metadata=effective_account_metadata,
            chat_type=normalized_chat_type,
            mentions=mentions,
            credential_provider=self.credential_provider,
            consumer=self._access_consumer(
                channel_type="lark",
                component="message_ingress",
                channel_account_id=normalized_account,
                field="lark_bot_open_id",
            ),
        ):
            return {
                "code": 0,
                "msg": "ignored",
                "challenge": None,
                "run_id": None,
                "status": None,
                "session_key": None,
                "active_session_id": None,
            }
        thread_id = (
            str(message.get("thread_id") or "").strip()
            or str(message.get("root_id") or "").strip()
            or None
        )
        open_id = str(sender_open_id or "").strip() or None
        interaction_id = self._build_lark_interaction_id(
            channel_account_id=normalized_account,
            event_id=event_id,
            message_id=str(message.get("message_id") or "").strip() or None,
            chat_id=chat_id,
        )
        reply_address = ReplyAddress(
            channel_type="lark",
            channel_account_id=normalized_account,
            external_conversation_id=chat_id,
            external_thread_id=thread_id,
            external_user_id=open_id,
            metadata={
                "receive_id_type": (
                    "open_id"
                    if normalized_chat_type == "direct"
                    else "chat_id"
                ),
                "chat_type": normalized_chat_type,
                "message_id": str(message.get("message_id") or "").strip() or None,
                "event_id": str(event_id or "").strip() or None,
                "reply_in_thread": bool(thread_id),
                "mentions": mentions,
            },
        )
        interaction = self.interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id=interaction_id,
                channel_type="lark",
                channel_account_id=normalized_account,
                external_event_id=str(event_id or "").strip() or None,
                external_message_id=str(message.get("message_id") or "").strip() or None,
                external_conversation_id=chat_id,
                external_user_id=open_id,
                reply_address=reply_address.to_payload(),
                agent_id=profile.id,
                run_id=uuid4().hex,
                status="received",
                metadata={
                    "chat_type": normalized_chat_type,
                    "thread_id": thread_id,
                    "mentions": mentions,
                    "source": "lark_event",
                },
            ),
        )
        options = build_submission_options(
            profile=profile,
            llm_id=llm_id,
            channel="lark",
            chat_type=normalized_chat_type,
            peer_id=open_id,
            conversation_id=chat_id,
            thread_id=thread_id,
            account_id=normalized_account,
            main_key="main",
            direct_scope=(
                DirectSessionScope.PER_CHANNEL_PEER
                if normalized_chat_type == "direct"
                else DirectSessionScope.MAIN
            ),
            source="lark_event",
            queue_policy=OrchestrationQueuePolicy.JUMP_QUEUE,
            priority=100,
            max_steps=None,
        )
        try:
            run = submit_turn(
                self.orchestration_submission_port,
                content=normalize_lark_message_content(message, mentions=mentions),
                options=options,
                run_id=interaction.run_id,
                inline_worker_id=None,
                reply_interface="lark",
                reply_address=chat_id,
                reply_to=str(message.get("message_id") or "").strip() or None,
                reply_metadata={
                    "reply_address": reply_address.to_payload(),
                },
            )
        except OrchestrationValidationError as exc:
            self.interaction_service.mark_status(
                interaction.interaction_id,
                status="failed",
                last_error=str(exc),
                metadata={"submit_failed": True},
            )
            raise ValueError(str(exc)) from None
        latest_run = self.orchestration_run_lookup.get_run(run.id)
        bound = self.interaction_service.bind_run(
            interaction.interaction_id,
            run_id=latest_run.id,
            session_key=latest_run.session_key,
            agent_id=profile.id,
            status=latest_run.status.value,
            metadata={
                "active_session_id": latest_run.active_session_id,
                "observe_cursor": (
                    self.events_service.snapshot_event_topic(
                        turn_session_topic(latest_run.session_key),
                    )
                    if isinstance(latest_run.session_key, str)
                    and latest_run.session_key.strip()
                    else None
                ),
            },
        )
        return {
            "code": 0,
            "msg": "ok",
            "challenge": None,
            "interaction_id": interaction.interaction_id,
            "run_id": latest_run.id,
            "status": latest_run.status.value,
            "session_key": latest_run.session_key,
            "active_session_id": latest_run.active_session_id,
            "interaction_status": bound.status if bound is not None else interaction.status,
        }

    @staticmethod
    def _build_lark_interaction_id(
        *,
        channel_account_id: str,
        event_id: str | None,
        message_id: str | None,
        chat_id: str,
    ) -> str:
        normalized_account = channel_account_id.strip()
        normalized_event_id = str(event_id or "").strip()
        if normalized_event_id:
            return f"lark:{normalized_account}:event:{normalized_event_id}"
        normalized_message_id = str(message_id or "").strip()
        if normalized_message_id:
            return f"lark:{normalized_account}:message:{normalized_message_id}"
        normalized_chat_id = chat_id.strip()
        return f"lark:{normalized_account}:chat:{normalized_chat_id}"

    def _ensure_long_connection_ingress(
        self,
        runtime_id: str,
        *,
        stop_event: ThreadEvent | None,
    ) -> None:
        accounts = self._long_connection_accounts()
        if not accounts:
            return
        if len(accounts) > 1:
            logger.warning(
                "lark long connection currently starts only the first enabled account on a runtime: %s",
                accounts,
            )
        account_id = accounts[0]
        thread_key = f"{runtime_id}:{account_id}"
        with self._ingress_lock:
            existing = self._ingress_threads.get(thread_key)
            if existing is not None and existing.is_alive():
                return
            thread = Thread(
                target=self._run_long_connection_ingress,
                kwargs={
                    "runtime_id": runtime_id,
                    "channel_account_id": account_id,
                    "stop_event": stop_event,
                },
                name=f"lark-long-connection-{account_id}",
                daemon=True,
            )
            self._ingress_threads[thread_key] = thread
            thread.start()

    def _long_connection_accounts(self) -> tuple[str, ...]:
        profile = self.profile_service.get_profile("lark")
        if profile is None or not profile.enabled:
            return ()
        resolved: list[str] = []
        for account in profile.accounts:
            if not account.enabled:
                continue
            mode = str(account.transport_mode or "").strip().lower()
            if mode in {"long_connection", "long-connection", "long"}:
                resolved.append(account.account_id)
        return tuple(resolved)

    def _run_long_connection_ingress(
        self,
        *,
        runtime_id: str,
        channel_account_id: str,
        stop_event: ThreadEvent | None,
    ) -> None:
        try:
            import lark_oapi
            from lark_oapi import EventDispatcherHandler
            from lark_oapi.ws import Client as LarkWsClient
        except Exception as exc:  # pragma: no cover - import guard
            logger.exception("failed to import lark long connection sdk: %s", exc)
            return

        try:
            account_profile = self._require_account_profile(channel_account_id)
            metadata = dict(account_profile.metadata)
            app_id = self._resolve_metadata_credential(
                metadata,
                key="lark_app_id",
                description="Lark app id",
                required=True,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            )
            app_secret = self._resolve_metadata_credential(
                metadata,
                key="lark_app_secret",
                description="Lark app secret",
                required=True,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            )
            verification_token = self._resolve_metadata_credential(
                metadata,
                key="lark_verification_token",
                description="Lark verification token",
                required=False,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            ) or ""
            encrypt_key = self._resolve_metadata_credential(
                metadata,
                key="lark_encrypt_key",
                description="Lark encrypt key",
                required=False,
                channel_type="lark",
                component="long_connection",
                channel_account_id=channel_account_id,
                runtime_ref=runtime_id,
            ) or ""
            base_url = str(metadata.get("lark_base_url") or "https://open.feishu.cn").strip()
            if not base_url:
                base_url = "https://open.feishu.cn"

            def _handle_message(data) -> None:  # noqa: ANN001
                try:
                    event = getattr(data, "event", None)
                    message = getattr(event, "message", None)
                    sender = getattr(event, "sender", None)
                    if message is None:
                        return
                    sender_id = getattr(sender, "sender_id", None)
                    mentions = []
                    raw_mentions = getattr(message, "mentions", None) or []
                    for item in raw_mentions:
                        item_id = getattr(item, "id", None)
                        mentions.append(
                            {
                                "key": getattr(item, "key", None),
                                "name": getattr(item, "name", None),
                                "open_id": getattr(item_id, "open_id", None),
                                "user_id": getattr(item_id, "user_id", None),
                                "union_id": getattr(item_id, "union_id", None),
                            },
                        )
                    result = self.submit_message_event(
                        channel_account_id,
                        event_id=getattr(getattr(data, "header", None), "event_id", None),
                        sender_open_id=getattr(sender_id, "open_id", None),
                        message={
                            "message_id": getattr(message, "message_id", None),
                            "chat_id": getattr(message, "chat_id", None),
                            "chat_type": getattr(message, "chat_type", None),
                            "message_type": getattr(message, "message_type", None),
                            "content": getattr(message, "content", None),
                            "thread_id": getattr(message, "thread_id", None),
                            "root_id": getattr(message, "root_id", None),
                            "parent_id": getattr(message, "parent_id", None),
                            "mentions": [
                                {
                                    "key": item.get("key"),
                                    "name": item.get("name"),
                                    "id": {
                                        "open_id": item.get("open_id"),
                                        "user_id": item.get("user_id"),
                                        "union_id": item.get("union_id"),
                                    },
                                }
                                for item in mentions
                            ],
                        },
                    )
                    self.runtime_manager.merge_runtime_metadata(
                        runtime_id,
                        metadata={
                            "lark_ingress_mode": "long_connection",
                            "lark_last_ingress_event_id": getattr(
                                getattr(data, "header", None),
                                "event_id",
                                None,
                            ),
                            "lark_last_ingress_status": result.get("status") or result.get("msg"),
                        },
                        touch_heartbeat=True,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("failed to handle lark long connection event: %s", exc)

            event_handler = (
                EventDispatcherHandler
                .builder(encrypt_key, verification_token)
                .register_p2_im_message_receive_v1(_handle_message)
                .build()
            )
            client = LarkWsClient(
                app_id=app_id,
                app_secret=app_secret,
                log_level=lark_oapi.LogLevel.INFO,
                event_handler=event_handler,
                domain=base_url.rstrip("/"),
                auto_reconnect=True,
            )
            self.runtime_manager.merge_runtime_metadata(
                runtime_id,
                metadata={
                    "lark_ingress_mode": "long_connection",
                    "lark_ingress_account_id": channel_account_id,
                    "lark_ingress_status": "connecting",
                },
                touch_heartbeat=True,
            )
            del stop_event
            client.start()
        except Exception as exc:  # pragma: no cover - network/sdk behavior
            logger.exception("lark long connection ingress failed: %s", exc)
            self.runtime_manager.merge_runtime_metadata(
                runtime_id,
                metadata={
                    "lark_ingress_mode": "long_connection",
                    "lark_ingress_account_id": channel_account_id,
                    "lark_ingress_status": "failed",
                    "lark_ingress_error": f"{type(exc).__name__}:{exc}",
                },
                touch_heartbeat=True,
            )

    def resolve_bot_open_id_for_account(
        self,
        channel_account_id: str,
        *,
        force_refresh: bool = False,
    ) -> str | None:
        account_profile = self._require_account_profile(channel_account_id)
        metadata = dict(account_profile.metadata)
        configured_open_id = self._resolve_metadata_credential(
            metadata,
            key="lark_bot_open_id",
            description="Lark bot open id",
            required=False,
            channel_type="lark",
            component="bot_identity",
            channel_account_id=channel_account_id,
        )
        if configured_open_id:
            return configured_open_id
        now = _utcnow()
        with self._bot_identity_lock:
            cached = None if force_refresh else self._bot_identities.get(channel_account_id)
            if cached is not None and cached.expires_at > now:
                return cached.open_id
        base_url = str(metadata.get("lark_base_url") or "https://open.feishu.cn").strip()
        if not base_url:
            base_url = "https://open.feishu.cn"
        try:
            token = self._tenant_access_token_for_account(
                channel_account_id,
                base_url=base_url.rstrip("/"),
            )
            response = request_url(
                "GET",
                f"{base_url.rstrip('/')}/open-apis/bot/v3/info",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                timeout=10,
            )
            payload = response.json()
        except ChannelCredentialResolutionError:
            raise
        except (requests.RequestException, ValueError, RuntimeError):
            return None
        code = payload.get("code")
        if response.status_code != 200 or code not in {0, "0", None}:
            return None
        bot_open_id = self._extract_bot_open_id(payload)
        if not bot_open_id:
            return None
        with self._bot_identity_lock:
            self._bot_identities[channel_account_id] = LarkBotIdentity(
                open_id=bot_open_id,
                expires_at=_utcnow() + timedelta(seconds=self.bot_identity_ttl_seconds),
            )
        return bot_open_id

    def _tenant_access_token_for_account(
        self,
        channel_account_id: str,
        *,
        base_url: str,
    ) -> str:
        now = _utcnow()
        with self._token_lock:
            cached = self._tenant_access_tokens.get(channel_account_id)
            if cached is not None and cached.expires_at > now + timedelta(seconds=60):
                return cached.token
        account_profile = self._require_account_profile(channel_account_id)
        metadata = dict(account_profile.metadata)
        app_id = self._resolve_metadata_credential(
            metadata,
            key="lark_app_id",
            description="Lark app id",
            required=True,
            channel_type="lark",
            component="tenant_access_token",
            channel_account_id=channel_account_id,
        )
        app_secret = self._resolve_metadata_credential(
            metadata,
            key="lark_app_secret",
            description="Lark app secret",
            required=True,
            channel_type="lark",
            component="tenant_access_token",
            channel_account_id=channel_account_id,
        )
        response = request_url(
            "POST",
            f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        payload = response.json()
        token = str(payload.get("tenant_access_token") or "").strip()
        if response.status_code != 200 or not token:
            code = payload.get("code")
            raise RuntimeError(f"lark_access_token_failed:{response.status_code}:{code}")
        raw_expire = payload.get("expire")
        try:
            expire_seconds = max(int(raw_expire), 1)
        except (TypeError, ValueError):
            expire_seconds = 7200
        cached_token = LarkTenantAccessToken(
            token=token,
            expires_at=_utcnow() + timedelta(seconds=expire_seconds),
        )
        with self._token_lock:
            self._tenant_access_tokens[channel_account_id] = cached_token
        return token

    def _extract_bot_open_id(self, payload: dict[str, Any]) -> str | None:
        candidates: list[dict[str, Any]] = [payload]
        bot_payload = payload.get("bot")
        if isinstance(bot_payload, dict):
            candidates.append(bot_payload)
        data_payload = payload.get("data")
        if isinstance(data_payload, dict):
            candidates.append(data_payload)
            nested_bot_payload = data_payload.get("bot")
            if isinstance(nested_bot_payload, dict):
                candidates.append(nested_bot_payload)
        for candidate in candidates:
            open_id = str(candidate.get("open_id") or "").strip()
            if open_id:
                return open_id
        return None

    def _require_account_profile(self, channel_account_id: str):
        profile = self.profile_service.get_profile("lark")
        if profile is not None and not profile.enabled:
            raise ValueError("lark_channel_profile_disabled")
        account = _resolve_channel_account_profile(
            profile,
            channel_account_id=channel_account_id,
        )
        if account is None:
            raise ValueError("missing_lark_account_profile")
        if not account.enabled:
            raise ValueError("lark_channel_account_disabled")
        return account


class WebhookChannelRuntimeService(ChannelRuntimeBootstrapService):
    max_delivery_attempts: int = 3

    def __init__(
        self,
        *,
        agent_service: ChannelAgentProfilePort,
        orchestration_submission_port: "OrchestrationSubmissionPort",
        orchestration_run_lookup: "OrchestrationRunLookupPort",
        interaction_service: ChannelInteractionService,
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
        self.agent_service = agent_service
        self.orchestration_submission_port = orchestration_submission_port
        self.orchestration_run_lookup = orchestration_run_lookup
        self.interaction_service = interaction_service
        self.events_service = events_service

    def ensure_registered(
        self,
        *,
        runtime_id: str = "webhook-runtime-1",
        service_key: str = "channel:webhook",
        status: str = "online",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelRuntimeRegistration:
        return super().ensure_registered(
            "webhook",
            runtime_id=runtime_id,
            service_key=service_key,
            status=status,
            metadata=metadata,
        )

    def submit_inbound(
        self,
        channel_account_id: str,
        *,
        content: Any,
        callback_url: str,
        agent_id: str | None,
        llm_id: str | None,
        chat_type: str,
        peer_id: str | None,
        conversation_id: str,
        thread_id: str | None,
        main_key: str,
        direct_scope: Any,
        source: str,
        queue_policy: Any,
        priority: int,
        max_steps: int | None,
        callback_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        from crxzipple.modules.orchestration.application.turn_submission import (
            build_submission_options,
            resolve_profile,
            submit_turn,
        )
        from crxzipple.modules.orchestration.domain import (
            OrchestrationValidationError,
        )

        normalized_account = channel_account_id.strip() or "default"
        normalized_callback_url = callback_url.strip()
        if not normalized_callback_url:
            raise ValueError("callback_url is required.")
        self._ensure_account_enabled(normalized_account)
        profile, error = resolve_profile(
            self.agent_service,
            agent_id=agent_id,
        )
        if profile is None:
            raise LookupError(error or "Agent profile was not found.")
        reply_address = ReplyAddress(
            channel_type="webhook",
            channel_account_id=normalized_account,
            webhook_callback_url=normalized_callback_url,
            external_conversation_id=conversation_id,
            external_thread_id=thread_id,
            external_user_id=peer_id,
            metadata={
                **dict(callback_metadata),
                "observation_enabled": True,
            },
        )
        planned_run_id = uuid4().hex
        interaction_id = f"webhook:{normalized_account}:run:{planned_run_id}"
        interaction = self.interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id=interaction_id,
                channel_type="webhook",
                channel_account_id=normalized_account,
                external_conversation_id=conversation_id,
                external_user_id=peer_id,
                reply_address=reply_address.to_payload(),
                agent_id=profile.id,
                run_id=planned_run_id,
                status="received",
                metadata={
                    "thread_id": thread_id,
                    "source": source,
                },
            ),
        )
        options = build_submission_options(
            profile=profile,
            llm_id=llm_id,
            channel="webhook",
            chat_type=chat_type,
            peer_id=peer_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            account_id=normalized_account,
            main_key=main_key,
            direct_scope=direct_scope,
            source=source,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
        )
        try:
            run = submit_turn(
                self.orchestration_submission_port,
                content=content,
                options=options,
                run_id=planned_run_id,
                inline_worker_id=None,
                reply_interface="webhook",
                reply_address=normalized_callback_url,
                reply_to=conversation_id,
                reply_metadata={
                    "reply_address": reply_address.to_payload(),
                },
            )
        except OrchestrationValidationError as exc:
            self.interaction_service.mark_status(
                interaction.interaction_id,
                status="failed",
                last_error=str(exc),
                metadata={"submit_failed": True},
            )
            raise ValueError(str(exc)) from None
        latest_run = self.orchestration_run_lookup.get_run(run.id)
        bound = self.interaction_service.bind_run(
            interaction.interaction_id,
            run_id=latest_run.id,
            session_key=latest_run.session_key,
            agent_id=profile.id,
            status=latest_run.status.value,
            metadata={
                "active_session_id": latest_run.active_session_id,
                "observe_cursor": (
                    self.events_service.snapshot_event_topic(
                        turn_session_topic(latest_run.session_key),
                    )
                    if isinstance(latest_run.session_key, str)
                    and latest_run.session_key.strip()
                    else None
                ),
            },
        )
        return {
            "interaction_id": interaction.interaction_id,
            "run_id": latest_run.id,
            "status": latest_run.status.value,
            "session_key": latest_run.session_key,
            "active_session_id": latest_run.active_session_id,
            "callback_url": normalized_callback_url,
            "interaction_status": bound.status if bound is not None else interaction.status,
        }

    def _ensure_account_enabled(self, channel_account_id: str) -> None:
        profile = self.profile_service.get_profile("webhook")
        if profile is None:
            return
        if not profile.enabled:
            raise ValueError("webhook_channel_profile_disabled")
        account = _resolve_channel_account_profile(
            profile,
            channel_account_id=channel_account_id,
        )
        if account is not None and not account.enabled:
            raise ValueError("webhook_channel_account_disabled")

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
            runtime_id=runtime_id or "webhook-runtime-1",
            service_key=service_key or "channel:webhook",
            metadata=metadata,
        )
        completed_cycles = 0
        while not stopper.is_set():
            observed_count = self.observe_pending_interactions(
                registration.runtime_id,
                limit=100,
            )
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            if not observed_count:
                self.wait_for_runtime_activity(
                    registration.runtime_id,
                    timeout_seconds=max(float(poll_interval_seconds), 0.05),
                    stop_event=stopper,
                )
            refreshed = self.runtime_manager.heartbeat_runtime(registration.runtime_id)
            if refreshed is not None:
                registration = refreshed
        return registration

    def wait_for_runtime_activity(
        self,
        runtime_id: str,
        *,
        timeout_seconds: float,
        stop_event: ThreadEvent | None = None,
    ) -> bool:
        watches: list[EventTopicWatch] = []
        for interaction in self._active_observe_interactions(runtime_id):
            if interaction.session_key is None:
                continue
            watches.append(
                EventTopicWatch(
                    topic=turn_session_topic(interaction.session_key),
                    after_cursor=self._interaction_observe_cursor(interaction),
                ),
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

    def observe_pending_interactions(
        self,
        runtime_id: str,
        *,
        limit: int = 100,
    ) -> int:
        registration = self.runtime_manager.get_runtime(runtime_id)
        if registration is None:
            return 0
        observed_count = 0
        transitioned_count = 0
        delivered_count = 0
        last_event_name: str | None = None
        last_interaction_id: str | None = None
        last_callback_status: str | None = None
        for interaction in self._active_observe_interactions(runtime_id):
            if interaction.session_key is None:
                continue
            seeded_cursor = self._interaction_observe_cursor(interaction)
            records = self.events_service.read_event_topic(
                turn_session_topic(interaction.session_key),
                after_cursor=seeded_cursor,
                limit=limit,
            )
            if not records:
                continue
            updated_interaction = interaction
            acked_records: list[EventTopicRecord] = []
            interaction_changed = False
            for record in records:
                candidate = self._apply_observe_record_to_interaction(
                    updated_interaction,
                    record=record,
                )
                if candidate.status != updated_interaction.status:
                    transitioned_count += 1
                delivered = self._deliver_observe_record_to_channel(
                    candidate,
                    record=record,
                )
                if delivered is not updated_interaction:
                    interaction_changed = True
                updated_interaction = delivered
                acked_records.append(record)
                observed_count += 1
                current_event_name = record.envelope.event_name or ""
                last_event_name = current_event_name or last_event_name
                last_interaction_id = delivered.interaction_id
                delivery_status = str(
                    delivered.metadata.get("last_delivery_status") or "",
                ).strip()
                if delivery_status:
                    last_callback_status = delivery_status
                    if delivery_status == "ok":
                        delivered_count += 1
            if not interaction_changed and not acked_records:
                continue
            final_metadata = {
                **dict(updated_interaction.metadata),
                "observe_cursor": (
                    acked_records[-1].cursor
                    if acked_records
                    else seeded_cursor
                ),
                "last_observed_cursor": (
                    acked_records[-1].cursor
                    if acked_records
                    else updated_interaction.metadata.get("last_observed_cursor")
                ),
                "last_observed_event_name": (
                    last_event_name
                    or updated_interaction.metadata.get("last_observed_event_name")
                ),
                "last_observed_at": (
                    acked_records[-1].envelope.created_at.isoformat()
                    if acked_records
                    else updated_interaction.metadata.get("last_observed_at")
                ),
            }
            persisted = self.interaction_service.upsert_interaction(
                replace(updated_interaction, metadata=final_metadata),
            )
            if persisted.status != interaction.status:
                interaction_changed = True
            if interaction_changed:
                last_interaction_id = persisted.interaction_id
        if observed_count:
            self.runtime_manager.merge_runtime_metadata(
                runtime_id,
                metadata={
                    "observe_observed_count": int(
                        registration.metadata.get("observe_observed_count", 0) or 0,
                    )
                    + observed_count,
                    "observe_transition_count": int(
                        registration.metadata.get("observe_transition_count", 0) or 0,
                    )
                    + transitioned_count,
                    "observe_delivery_count": int(
                        registration.metadata.get("observe_delivery_count", 0) or 0,
                    )
                    + delivered_count,
                    "last_observe_event_name": last_event_name,
                    "last_observe_interaction_id": last_interaction_id,
                    "last_delivery_callback_status": last_callback_status,
                },
                touch_heartbeat=True,
            )
        return observed_count

    def _active_observe_interactions(
        self,
        runtime_id: str,
    ) -> tuple[ChannelInteraction, ...]:
        account_ids = {
            binding.channel_account_id
            for binding in self.runtime_manager.list_account_bindings(
                runtime_id=runtime_id,
                channel_type="webhook",
            )
        }
        interactions = self.interaction_service.list_interactions(channel_type="webhook")
        return tuple(
            item
            for item in interactions
            if (
                item.channel_account_id in account_ids
                and isinstance(item.run_id, str)
                and item.run_id.strip()
                and isinstance(item.session_key, str)
                and item.session_key.strip()
                and not self._interaction_observe_settled(item)
            )
        )

    @staticmethod
    def _interaction_observe_settled(
        interaction: ChannelInteraction,
    ) -> bool:
        normalized_status = str(interaction.status or "").strip().lower()
        if normalized_status in {"failed", "cancelled"}:
            return True
        if normalized_status != "completed":
            return False
        metadata = dict(interaction.metadata)
        last_message_id = str(metadata.get("last_message_id") or "").strip()
        last_delivered_message_id = str(
            metadata.get("last_delivered_message_id") or "",
        ).strip()
        delivery_status = str(metadata.get("last_delivery_status") or "").strip().lower()
        if last_message_id:
            return (
                last_delivered_message_id == last_message_id
                and delivery_status == "ok"
            )
        return False

    @staticmethod
    def _interaction_observe_cursor(
        interaction: ChannelInteraction,
    ) -> EventCursor | None:
        raw_cursor = interaction.metadata.get("observe_cursor")
        if isinstance(raw_cursor, str) and raw_cursor.strip():
            return raw_cursor.strip()
        return None

    def _apply_observe_record_to_interaction(
        self,
        interaction: ChannelInteraction,
        *,
        record: EventTopicRecord,
    ) -> ChannelInteraction:
        payload = dict(record.envelope.payload or {})
        event_name = record.envelope.event_name or ""
        if not event_name:
            return interaction
        if event_name == ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT:
            message = dict(payload.get("message") or {})
            return replace(
                interaction,
                metadata={
                    **dict(interaction.metadata),
                    "last_message_id": str(payload.get("message_id") or "").strip() or None,
                    "last_message_role": str(payload.get("role") or "").strip() or None,
                    "last_message_kind": str(payload.get("kind") or "").strip() or None,
                    "last_message_created_at": message.get("created_at"),
                    "last_message_summary": _extract_text_message(message).strip() or None,
                },
            )
        if event_name == ORCHESTRATION_RUN_TOOL_UPDATED_EVENT:
            return replace(
                interaction,
                metadata={
                    **dict(interaction.metadata),
                    "last_tool_event_name": event_name,
                    "last_tool_source_event_name": payload.get("source_event_name"),
                    "last_tool_run_id": payload.get("tool_run_id"),
                    "last_tool_id": payload.get("tool_id"),
                    "last_tool_name": payload.get("tool_name"),
                    "last_tool_status": payload.get("tool_status"),
                    "last_tool_updated_at": (
                        payload.get("completed_at")
                        or payload.get("started_at")
                        or payload.get("created_at")
                    ),
                },
            )
        run_id = str(payload.get("run_id") or "").strip()
        if run_id and run_id != str(interaction.run_id or "").strip():
            return interaction
        resolved_status = self._interaction_status_from_observe_fact(
            current_status=interaction.status,
            event_name=event_name,
            payload=payload,
        )
        return replace(
            interaction,
            status=resolved_status,
            metadata={
                **dict(interaction.metadata),
                "last_run_event_name": event_name,
                "stage": payload.get("stage"),
                "current_step": payload.get("current_step"),
                "waiting_reason": payload.get("waiting_reason"),
                "pending_tool_run_ids": list(payload.get("pending_tool_run_ids") or []),
                "active_session_id": payload.get("active_session_id"),
            },
        )

    @staticmethod
    def _interaction_status_from_observe_fact(
        *,
        current_status: str,
        event_name: str,
        payload: dict[str, Any],
    ) -> str:
        raw_status = str(payload.get("status") or "").strip().lower()
        if raw_status:
            return raw_status
        normalized_event_name = event_name.strip().lower()
        if normalized_event_name.endswith(".completed"):
            return "completed"
        if normalized_event_name.endswith(".failed"):
            return "failed"
        if normalized_event_name.endswith(".cancelled"):
            return "cancelled"
        if ".waiting" in normalized_event_name:
            return "waiting"
        if normalized_event_name.endswith(".queued"):
            return "queued"
        return current_status

    def _deliver_observe_record_to_channel(
        self,
        interaction: ChannelInteraction,
        *,
        record: EventTopicRecord,
    ) -> ChannelInteraction:
        payload = dict(record.envelope.payload or {})
        event_name = record.envelope.event_name or ""
        if event_name != ORCHESTRATION_RUN_MESSAGE_APPENDED_EVENT:
            return interaction
        role = str(payload.get("role") or "").strip().lower()
        kind = str(payload.get("kind") or "").strip().lower()
        if role != "assistant" and kind != "tool_result":
            return interaction
        message_id = str(payload.get("message_id") or "").strip()
        if not message_id:
            return interaction
        current_metadata = dict(interaction.metadata)
        if (
            str(current_metadata.get("last_delivered_message_id") or "").strip()
            == message_id
            and str(current_metadata.get("last_delivery_status") or "").strip().lower()
            == "ok"
        ):
            return interaction
        callback_url = self._callback_url_for_interaction(interaction)
        callback_payload = self._observe_callback_payload(
            interaction,
            payload=payload,
        )
        if callback_url is None:
            dead_letter_outbound_id = self._publish_observe_dead_letter(
                runtime_id=self._runtime_id_for_interaction(interaction),
                interaction=interaction,
                callback_url=None,
                callback_payload=callback_payload,
                status="missing_callback_url",
                attempt_count=1,
            )
            return replace(
                interaction,
                metadata={
                    **current_metadata,
                    "last_delivered_message_id": message_id,
                    "last_delivery_status": "missing_callback_url",
                    "last_delivery_error": "missing_callback_url",
                    "last_delivery_dead_letter_outbound_id": dead_letter_outbound_id,
                    "last_delivered_at": _utcnow().isoformat(),
                },
            )
        delivered, last_status, attempt_count = self._post_callback_payload(
            callback_url=callback_url,
            callback_payload=callback_payload,
        )
        if delivered:
            return replace(
                interaction,
                metadata={
                    **current_metadata,
                    "last_delivered_message_id": message_id,
                    "last_delivery_status": "ok",
                    "last_delivery_callback_status": last_status,
                    "last_delivery_error": None,
                    "last_delivered_at": _utcnow().isoformat(),
                },
            )
        dead_letter_outbound_id = self._publish_observe_dead_letter(
            runtime_id=self._runtime_id_for_interaction(interaction),
            interaction=interaction,
            callback_url=callback_url,
            callback_payload=callback_payload,
            status=last_status,
            attempt_count=attempt_count,
        )
        return replace(
            interaction,
            metadata={
                **current_metadata,
                "last_delivered_message_id": message_id,
                "last_delivery_status": last_status,
                "last_delivery_callback_status": last_status,
                "last_delivery_error": last_status,
                "last_delivery_dead_letter_outbound_id": dead_letter_outbound_id,
                "last_delivered_at": _utcnow().isoformat(),
            },
        )

    def replay_dead_letter_payload(
        self,
        *,
        callback_payload: dict[str, Any],
        callback_url: str | None = None,
    ) -> str:
        resolved_callback_url = (
            callback_url.strip()
            if isinstance(callback_url, str) and callback_url.strip()
            else None
        )
        if resolved_callback_url is None:
            reply_address = dict(callback_payload.get("reply_address") or {})
            raw_callback_url = reply_address.get("webhook_callback_url")
            if isinstance(raw_callback_url, str) and raw_callback_url.strip():
                resolved_callback_url = raw_callback_url.strip()
        if resolved_callback_url is None:
            raise ValueError("Webhook dead-letter replay requires a callback URL.")
        delivered, last_status, _ = self._post_callback_payload(
            callback_url=resolved_callback_url,
            callback_payload=callback_payload,
        )
        if not delivered:
            raise RuntimeError(f"webhook_dead_letter_replay_failed:{last_status}")
        return last_status

    def replay_dead_letter_record(
        self,
        *,
        runtime_id: str | None = None,
        cursor: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        topic = channel_dead_letter_topic("webhook", runtime_id=runtime_id)
        records = self.events_service.read_event_topic(topic, limit=1000)
        matched: EventTopicRecord | None = None
        for record in records:
            if cursor is not None and record.cursor == cursor:
                matched = record
                break
            if event_id is not None and record.envelope.id == event_id:
                matched = record
                break
        if matched is None:
            raise LookupError("Dead-letter record not found.")
        outbound_payload = matched.envelope.payload.get("outbound")
        if not isinstance(outbound_payload, dict):
            raise ValueError(
                "Dead-letter record does not include replayable outbound payload.",
            )
        reply_payload = outbound_payload.get("reply_address")
        if not isinstance(reply_payload, dict):
            raise ValueError("Dead-letter record is missing reply_address.")
        callback_url = matched.envelope.payload.get("callback_url")
        callback_status = self.replay_dead_letter_payload(
            callback_payload=dict(outbound_payload),
            callback_url=(
                str(callback_url).strip()
                if callback_url is not None and str(callback_url).strip()
                else None
            ),
        )
        return {
            "replayed": True,
            "dead_letter_topic": topic,
            "dead_letter_cursor": matched.cursor,
            "dead_letter_event_id": matched.envelope.id,
            "outbound_id": str(outbound_payload.get("outbound_id") or ""),
            "replay_mode": "direct_callback",
            "callback_status": callback_status,
        }

    def _post_callback_payload(
        self,
        *,
        callback_url: str,
        callback_payload: dict[str, Any],
    ) -> tuple[bool, str, int]:
        last_status = "skipped"
        attempt_count = 0
        while attempt_count < self.max_delivery_attempts:
            attempt_count += 1
            try:
                response = request_url(
                    "POST",
                    callback_url,
                    json=callback_payload,
                    timeout=10,
                )
                last_status = f"http_{response.status_code}"
                if 200 <= response.status_code < 300:
                    return True, last_status, attempt_count
            except requests.RequestException as exc:
                last_status = exc.__class__.__name__
            if attempt_count >= self.max_delivery_attempts:
                break
        return False, last_status, attempt_count

    def _runtime_id_for_interaction(self, interaction: ChannelInteraction) -> str:
        resolved = self.runtime_manager.resolve_account_runtime(
            channel_type="webhook",
            channel_account_id=interaction.channel_account_id,
        )
        return resolved.runtime_id if resolved is not None else "webhook-runtime-1"

    @staticmethod
    def _callback_url_for_interaction(
        interaction: ChannelInteraction,
    ) -> str | None:
        reply_address = dict(interaction.reply_address or {})
        raw = reply_address.get("webhook_callback_url")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    @staticmethod
    def _observe_callback_payload(
        interaction: ChannelInteraction,
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        message_id = str(payload.get("message_id") or "").strip()
        return {
            "outbound_id": message_id,
            "mode": "event",
            "event_name": str(payload.get("event_name") or "").strip() or None,
            "conversation_id": interaction.external_conversation_id,
            "session_key": interaction.session_key,
            "message": dict(payload.get("message") or {}),
            "reply_address": dict(interaction.reply_address or {}),
            "metadata": {
                "run_id": interaction.run_id,
                "interaction_id": interaction.interaction_id,
                "channel_account_id": interaction.channel_account_id,
                "source_kind": payload.get("source_kind"),
                "source_id": payload.get("source_id"),
            },
            "created_at": (
                dict(payload.get("message") or {}).get("created_at")
                or _utcnow().isoformat()
            ),
        }

    def _publish_observe_dead_letter(
        self,
        *,
        runtime_id: str,
        interaction: ChannelInteraction,
        callback_url: str | None,
        callback_payload: dict[str, Any],
        status: str,
        attempt_count: int,
    ) -> str:
        outbound_id = str(callback_payload.get("outbound_id") or "").strip()
        self.events_service.publish(
            Event(
                topic=channel_dead_letter_topic("webhook", runtime_id=runtime_id),
                kind="fact",
                target=EventAddress(
                    address=interaction.channel_account_id or runtime_id,
                    address_kind=(
                        "account"
                        if interaction.channel_account_id
                        else "runtime"
                    ),
                    runtime=runtime_id,
                    transport="webhook",
                    account=interaction.channel_account_id or None,
                ),
                payload={
                    "event_name": "channel.observation.dead_lettered",
                    "outbound_id": outbound_id,
                    "outbound": dict(callback_payload),
                    "conversation_id": callback_payload.get("conversation_id"),
                    "session_key": callback_payload.get("session_key"),
                    "message": dict(callback_payload.get("message") or {}),
                    "reply_address": dict(callback_payload.get("reply_address") or {}),
                    "callback_url": callback_url,
                    "status": status,
                    "attempt_count": attempt_count,
                    "created_at": callback_payload.get("created_at"),
                },
            ),
        )
        return outbound_id
