from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from crxzipple.modules.channels.application.lark_messages import (
    extract_lark_mentions,
    is_truthy,
    normalize_lark_chat_type,
    normalize_lark_message_content,
    parse_lark_message_content,
    should_accept_lark_message,
)
from crxzipple.modules.channels.application.ports import (
    ChannelAgentProfilePort,
    ChannelEventStreamPort,
)
from crxzipple.modules.channels.application.services import (
    ChannelInteractionService,
)
from crxzipple.modules.channels.domain import ChannelInteraction
from crxzipple.modules.orchestration.application import turn_session_topic
from crxzipple.modules.orchestration.application.turn_submission import (
    build_submission_options,
    resolve_profile,
    submit_turn,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationValidationError,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.shared import ReplyAddress
from crxzipple.shared.access import AccessConsumerRef, CredentialProvider


class LarkAccountProfileResolver(Protocol):
    def __call__(self, channel_account_id: str) -> Any:
        ...


class LarkMetadataCredentialResolver(Protocol):
    def __call__(
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
        ...


class LarkBotOpenIdResolver(Protocol):
    def __call__(
        self,
        channel_account_id: str,
        *,
        force_refresh: bool = False,
    ) -> str | None:
        ...


class LarkAccessConsumerResolver(Protocol):
    def __call__(
        self,
        *,
        channel_type: str,
        component: str,
        channel_account_id: str | None = None,
        field: str | None = None,
        runtime_ref: str | None = None,
    ) -> AccessConsumerRef:
        ...


class LarkMessageSubmissionRuntime:
    def __init__(
        self,
        *,
        agent_service: ChannelAgentProfilePort,
        orchestration_submission_port: Any,
        orchestration_run_lookup: Any,
        interaction_service: ChannelInteractionService,
        events_service: ChannelEventStreamPort,
        account_profile_resolver: LarkAccountProfileResolver,
        metadata_credential_resolver: LarkMetadataCredentialResolver,
        bot_open_id_resolver: LarkBotOpenIdResolver,
        access_consumer_resolver: LarkAccessConsumerResolver,
    ) -> None:
        self._agent_service = agent_service
        self._orchestration_submission_port = orchestration_submission_port
        self._orchestration_run_lookup = orchestration_run_lookup
        self._interaction_service = interaction_service
        self._events_service = events_service
        self._account_profile_resolver = account_profile_resolver
        self._metadata_credential_resolver = metadata_credential_resolver
        self._bot_open_id_resolver = bot_open_id_resolver
        self._access_consumer_resolver = access_consumer_resolver

    def submit_message_event(
        self,
        channel_account_id: str,
        *,
        event_id: str | None,
        sender_open_id: str | None,
        message: dict[str, Any],
        credential_provider: CredentialProvider | None,
    ) -> dict[str, Any]:
        normalized_account = channel_account_id.strip()
        if not normalized_account:
            raise ValueError("channel_account_id is required")
        account_profile = self._account_profile_resolver(normalized_account)
        account_metadata = dict(account_profile.metadata)
        agent_id = str(account_metadata.get("agent_id") or "").strip() or None
        llm_id = str(account_metadata.get("llm_id") or "").strip() or None
        profile, error = resolve_profile(
            self._agent_service,
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
            and not self._metadata_credential_resolver(
                account_metadata,
                key="lark_bot_open_id",
                description="Lark bot open id",
                required=False,
                channel_type="lark",
                component="message_ingress",
                channel_account_id=normalized_account,
            )
        ):
            resolved_bot_open_id = self._bot_open_id_resolver(
                normalized_account,
            )
            if resolved_bot_open_id:
                effective_account_metadata["lark_bot_open_id"] = resolved_bot_open_id
        if not should_accept_lark_message(
            account_metadata=effective_account_metadata,
            chat_type=normalized_chat_type,
            mentions=mentions,
            credential_provider=credential_provider,
            consumer=self._access_consumer_resolver(
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
        interaction_id = build_lark_interaction_id(
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
        interaction = self._interaction_service.upsert_interaction(
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
                self._orchestration_submission_port,
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


def build_lark_interaction_id(
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
