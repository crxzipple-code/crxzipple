from __future__ import annotations

from dataclasses import replace
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, Any

import requests

from crxzipple.modules.channels.application.ports import (
    ChannelAccessReadinessPort,
    ChannelAgentProfilePort,
    ChannelEventStreamPort,
)
from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.application.runtime_helpers import (
    extract_text_message,
    resolve_channel_account_profile,
    session_item_fact_as_message_payload,
    utcnow,
)
from crxzipple.modules.channels.application.runtime_observation import (
    interaction_observe_cursor,
    interaction_observe_settled,
    interaction_status_from_observe_fact,
)
from crxzipple.modules.channels.application.webhook_runtime_submission import (
    WebhookInboundSubmissionRuntime,
)
from crxzipple.modules.channels.application.services import (
    ChannelInteractionService,
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.domain import (
    ChannelInteraction,
    ChannelRuntimeRegistration,
    channel_dead_letter_topic,
)
from crxzipple.modules.events import (
    Event,
    EventAddress,
    EventTopicRecord,
    EventTopicWatch,
)
from crxzipple.modules.orchestration.application import turn_session_topic
from crxzipple.shared import (
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    SESSION_ITEM_APPENDED_SOURCE_EVENT,
)
from crxzipple.shared.access import CredentialProvider
from crxzipple.shared.http import request_url

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.ports import (
        OrchestrationRunLookupPort,
        OrchestrationSubmissionPort,
    )


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
        self._inbound_submission = WebhookInboundSubmissionRuntime(
            agent_service=self.agent_service,
            orchestration_submission_port=self.orchestration_submission_port,
            orchestration_run_lookup=self.orchestration_run_lookup,
            interaction_service=self.interaction_service,
            events_service=self.events_service,
            account_enabled_checker=self._ensure_account_enabled,
        )

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
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._inbound_submission.submit_inbound(
            channel_account_id,
            content=content,
            callback_url=callback_url,
            agent_id=agent_id,
            llm_id=llm_id,
            chat_type=chat_type,
            peer_id=peer_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            main_key=main_key,
            direct_scope=direct_scope,
            source=source,
            queue_policy=queue_policy,
            priority=priority,
            max_steps=max_steps,
            callback_metadata=callback_metadata,
            idempotency_key=idempotency_key,
        )

    def _ensure_account_enabled(self, channel_account_id: str) -> None:
        profile = self.profile_service.get_profile("webhook")
        if profile is None:
            return
        if not profile.enabled:
            raise ValueError("webhook_channel_profile_disabled")
        account = resolve_channel_account_profile(
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
                    after_cursor=interaction_observe_cursor(interaction),
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
            seeded_cursor = interaction_observe_cursor(interaction)
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
                and not interaction_observe_settled(item)
            )
        )

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
        if event_name == SESSION_ITEM_APPENDED_SOURCE_EVENT:
            payload = session_item_fact_as_message_payload(payload)
            message = dict(payload.get("message") or {})
            return replace(
                interaction,
                metadata={
                    **dict(interaction.metadata),
                    "last_message_id": str(payload.get("message_id") or "").strip() or None,
                    "last_message_role": str(payload.get("role") or "").strip() or None,
                    "last_message_kind": str(payload.get("kind") or "").strip() or None,
                    "last_message_created_at": message.get("created_at"),
                    "last_message_summary": extract_text_message(message).strip() or None,
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
        resolved_status = interaction_status_from_observe_fact(
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

    def _deliver_observe_record_to_channel(
        self,
        interaction: ChannelInteraction,
        *,
        record: EventTopicRecord,
    ) -> ChannelInteraction:
        payload = dict(record.envelope.payload or {})
        event_name = record.envelope.event_name or ""
        if event_name != SESSION_ITEM_APPENDED_SOURCE_EVENT:
            return interaction
        payload = session_item_fact_as_message_payload(payload)
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
                    "last_delivered_at": utcnow().isoformat(),
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
                    "last_delivered_at": utcnow().isoformat(),
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
                "last_delivered_at": utcnow().isoformat(),
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
                or utcnow().isoformat()
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
