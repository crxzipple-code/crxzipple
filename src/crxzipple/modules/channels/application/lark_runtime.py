from __future__ import annotations

from dataclasses import replace
import logging
from threading import Event as ThreadEvent
from typing import TYPE_CHECKING, Any

import requests

from crxzipple.modules.artifacts.domain import ArtifactError
from crxzipple.modules.channels.application.bindings import (
    collect_channel_access_requirements,
)
from crxzipple.modules.channels.application.ports import (
    ChannelAccessReadinessPort,
    ChannelAgentProfilePort,
    ChannelArtifactReadPort,
    ChannelEventStreamPort,
)
from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.application.runtime_helpers import (
    resolve_channel_account_profile,
    utcnow,
)
from crxzipple.modules.channels.application.lark_runtime_delivery import (
    lark_deliver_observe_record_to_channel,
)
from crxzipple.modules.channels.application.lark_runtime_identity import (
    LarkIdentityRuntime,
)
from crxzipple.modules.channels.application.lark_runtime_long_connection import (
    LarkLongConnectionIngressRuntime,
)
from crxzipple.modules.channels.application.lark_runtime_submission import (
    LarkMessageSubmissionRuntime,
)
from crxzipple.modules.channels.application.lark_runtime_observation import (
    lark_observe_session_message_fact,
)
from crxzipple.modules.channels.application.runtime_observation import (
    interaction_observe_cursor,
    interaction_observe_settled,
    interaction_status_from_observe_fact,
)
from crxzipple.modules.channels.application.services import (
    ChannelInteractionService,
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.domain import (
    ChannelInteraction,
    ChannelProfile,
    ChannelRuntimeRegistration,
)
from crxzipple.modules.events import EventTopicRecord, EventTopicWatch
from crxzipple.modules.orchestration.application import turn_session_topic
from crxzipple.shared import (
    ORCHESTRATION_RUN_TOOL_UPDATED_EVENT,
    SESSION_ITEM_APPENDED_SOURCE_EVENT,
)
from crxzipple.shared.access import CredentialProvider

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.ports import (
        OrchestrationRunLookupPort,
        OrchestrationSubmissionPort,
    )


logger = logging.getLogger(__name__)


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
        self._identity_runtime = LarkIdentityRuntime(
            account_profile_resolver=self._require_account_profile,
            metadata_credential_resolver=self._resolve_metadata_credential,
            bot_identity_ttl_seconds=self.bot_identity_ttl_seconds,
        )
        self._long_connection_ingress = LarkLongConnectionIngressRuntime(
            profile_service=self.profile_service,
            runtime_manager=self.runtime_manager,
            account_profile_resolver=self._require_account_profile,
            metadata_credential_resolver=self._resolve_metadata_credential,
            message_submitter=self.submit_message_event,
        )
        self._message_submission = LarkMessageSubmissionRuntime(
            agent_service=self.agent_service,
            orchestration_submission_port=self.orchestration_submission_port,
            orchestration_run_lookup=self.orchestration_run_lookup,
            interaction_service=self.interaction_service,
            events_service=self.events_service,
            account_profile_resolver=self._require_account_profile,
            metadata_credential_resolver=self._resolve_metadata_credential,
            bot_open_id_resolver=self.resolve_bot_open_id_for_account,
            access_consumer_resolver=self._access_consumer,
        )

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
        self._long_connection_ingress.ensure_started(
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
        last_event_name: str | None = None
        last_interaction_id: str | None = None
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
                    delivered = lark_deliver_observe_record_to_channel(
                        candidate,
                        record=record,
                        artifact_service=self.artifact_service,
                        account_profile_resolver=self._require_account_profile,
                        tenant_access_token_resolver=self._tenant_access_token_for_account,
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
                            "last_delivery_failed_at": utcnow().isoformat(),
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
            observation = lark_observe_session_message_fact(payload)
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

    def submit_message_event(
        self,
        channel_account_id: str,
        *,
        event_id: str | None,
        sender_open_id: str | None,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        return self._message_submission.submit_message_event(
            channel_account_id,
            event_id=event_id,
            sender_open_id=sender_open_id,
            message=message,
            credential_provider=self.credential_provider,
        )

    def resolve_bot_open_id_for_account(
        self,
        channel_account_id: str,
        *,
        force_refresh: bool = False,
    ) -> str | None:
        return self._identity_runtime.resolve_bot_open_id_for_account(
            channel_account_id,
            force_refresh=force_refresh,
        )

    def _tenant_access_token_for_account(
        self,
        channel_account_id: str,
        *,
        base_url: str,
    ) -> str:
        return self._identity_runtime.tenant_access_token_for_account(
            channel_account_id,
            base_url=base_url,
        )

    def _require_account_profile(self, channel_account_id: str):
        profile = self.profile_service.get_profile("lark")
        if profile is not None and not profile.enabled:
            raise ValueError("lark_channel_profile_disabled")
        account = resolve_channel_account_profile(
            profile,
            channel_account_id=channel_account_id,
        )
        if account is None:
            raise ValueError("missing_lark_account_profile")
        if not account.enabled:
            raise ValueError("lark_channel_account_disabled")
        return account
