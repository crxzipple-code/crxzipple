from __future__ import annotations

import hashlib
from typing import Any, Callable
from uuid import uuid4

from crxzipple.modules.channels.application.ports import (
    ChannelAgentProfilePort,
    ChannelEventStreamPort,
)
from crxzipple.modules.channels.application.services import ChannelInteractionService
from crxzipple.modules.channels.domain import ChannelInteraction
from crxzipple.modules.orchestration.application import turn_session_topic
from crxzipple.modules.orchestration.application.turn_submission import (
    build_submission_options,
    resolve_profile,
    submit_turn,
)
from crxzipple.modules.orchestration.domain import OrchestrationValidationError
from crxzipple.shared import ReplyAddress


class WebhookInboundSubmissionRuntime:
    def __init__(
        self,
        *,
        agent_service: ChannelAgentProfilePort,
        orchestration_submission_port: Any,
        orchestration_run_lookup: Any,
        interaction_service: ChannelInteractionService,
        events_service: ChannelEventStreamPort,
        account_enabled_checker: Callable[[str], None],
    ) -> None:
        self._agent_service = agent_service
        self._orchestration_submission_port = orchestration_submission_port
        self._orchestration_run_lookup = orchestration_run_lookup
        self._interaction_service = interaction_service
        self._events_service = events_service
        self._account_enabled_checker = account_enabled_checker

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
        normalized_account = channel_account_id.strip() or "default"
        normalized_callback_url = callback_url.strip()
        if not normalized_callback_url:
            raise ValueError("callback_url is required.")
        self._account_enabled_checker(normalized_account)
        normalized_idempotency_key = str(idempotency_key or "").strip()
        if normalized_idempotency_key:
            existing = self._interaction_service.get_interaction(
                _webhook_idempotency_interaction_id(
                    channel_account_id=normalized_account,
                    idempotency_key=normalized_idempotency_key,
                ),
            )
            if existing is not None and existing.run_id:
                latest_run = self._orchestration_run_lookup.get_run(existing.run_id)
                existing_reply_address = dict(existing.reply_address or {})
                return {
                    "interaction_id": existing.interaction_id,
                    "run_id": latest_run.id,
                    "status": latest_run.status.value,
                    "session_key": latest_run.session_key,
                    "active_session_id": latest_run.active_session_id,
                    "callback_url": str(
                        existing_reply_address.get("webhook_callback_url")
                        or normalized_callback_url,
                    ),
                    "interaction_status": existing.status,
                }
        profile, error = resolve_profile(
            self._agent_service,
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
        interaction_id = (
            _webhook_idempotency_interaction_id(
                channel_account_id=normalized_account,
                idempotency_key=normalized_idempotency_key,
            )
            if normalized_idempotency_key
            else f"webhook:{normalized_account}:run:{planned_run_id}"
        )
        interaction = self._interaction_service.upsert_interaction(
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
                    "idempotency_key": normalized_idempotency_key or None,
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
                self._orchestration_submission_port,
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
            self._interaction_service.mark_status(
                interaction.interaction_id,
                status="failed",
                last_error=str(exc),
                metadata={"submit_failed": True},
            )
            raise ValueError(str(exc)) from None
        latest_run = self._orchestration_run_lookup.get_run(run.id)
        bound = self._interaction_service.bind_run(
            interaction.interaction_id,
            run_id=latest_run.id,
            session_key=latest_run.session_key,
            agent_id=profile.id,
            status=latest_run.status.value,
            metadata={
                "active_session_id": latest_run.active_session_id,
                "observe_cursor": (
                    self._events_service.snapshot_event_topic(
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


def _webhook_idempotency_interaction_id(
    *,
    channel_account_id: str,
    idempotency_key: str,
) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"webhook:{channel_account_id}:idempotency:{digest}"
