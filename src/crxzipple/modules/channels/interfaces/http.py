from __future__ import annotations

import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import hashlib
import hmac
import json
import re
import time
from uuid import uuid4
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.channels.domain import (
    ChannelAccountProfile,
    ChannelProfile,
    ChannelValidationError,
    channel_broadcast_topic,
    channel_connection_control_topic,
    channel_dead_letter_topic,
)
from crxzipple.modules.channels.application.bindings import (
    resolve_channel_metadata_binding,
)
from crxzipple.modules.events import Event, EventAddress, EventTopicWatch
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)
from crxzipple.shared.access import AccessConsumerRef, CredentialProvider


router = APIRouter()


class WebChannelConnectedEventResponse(BaseModel):
    runtime_id: str
    service_key: str | None = None
    channel_account_id: str
    connection_id: str
    conversation_id: str | None = None
    supports_streaming: bool
    stream_role: str = "primary"
    observe_mode: str = "preferred"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebChannelSubscriptionUpdateRequest(BaseModel):
    conversation_id: str | None = None
    channel_account_id: str | None = None


class WebChannelSubscriptionResponse(BaseModel):
    runtime_id: str
    channel_account_id: str | None = None
    connection_id: str
    conversation_id: str | None = None
    supports_streaming: bool
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebChannelBroadcastEventResponse(BaseModel):
    event_id: str
    topic: str
    payload: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WebChannelObserveEventResponse(BaseModel):
    event_id: str
    event_name: str
    topic: str
    source_topic: str | None = None
    source_cursor: str | None = None
    fact: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WebChannelLiveEventResponse(BaseModel):
    event_id: str
    event_name: str
    topic: str
    source_topic: str | None = None
    source_cursor: str | None = None
    live: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ChannelRuntimeSummaryResponse(BaseModel):
    runtime_id: str
    channel_type: str
    service_key: str | None = None
    status: str
    registered_at: str
    last_heartbeat_at: str
    account_count: int
    connection_count: int


class ChannelAccountBindingResponse(BaseModel):
    channel_type: str
    channel_account_id: str
    runtime_id: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelConnectionBindingResponse(BaseModel):
    channel_type: str
    connection_id: str
    runtime_id: str
    channel_account_id: str | None = None
    conversation_id: str | None = None
    supports_streaming: bool
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelRuntimeDetailResponse(BaseModel):
    runtime_id: str
    channel_type: str
    service_key: str | None = None
    status: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    registered_at: str
    last_heartbeat_at: str
    account_bindings: list[ChannelAccountBindingResponse] = Field(default_factory=list)
    connection_bindings: list[ChannelConnectionBindingResponse] = Field(default_factory=list)


class ChannelDeadLetterRecordResponse(BaseModel):
    cursor: str
    topic: str
    event_id: str
    kind: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] = Field(default_factory=dict)


class ChannelDeadLetterReplayRequest(BaseModel):
    runtime_id: str | None = None
    cursor: str | None = None
    event_id: str | None = None


class ChannelDeadLetterReplayResponse(BaseModel):
    replayed: bool
    dead_letter_topic: str
    dead_letter_cursor: str
    dead_letter_event_id: str
    outbound_id: str
    replay_mode: str
    callback_status: str | None = None


class WebhookInboundRequest(BaseModel):
    content: Any
    callback_url: str
    agent_id: str | None = None
    llm_id: str | None = None
    chat_type: str = "direct"
    peer_id: str | None = None
    conversation_id: str
    thread_id: str | None = None
    main_key: str = "main"
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    source: str = "webhook"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int = Field(default=100, ge=0)
    max_steps: int | None = Field(default=None, ge=1)
    callback_metadata: dict[str, Any] = Field(default_factory=dict)


class WebhookInboundAcceptedResponse(BaseModel):
    run_id: str
    status: str
    session_key: str | None = None
    active_session_id: str | None = None
    callback_url: str


class LarkEventAcceptedResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    challenge: str | None = None
    run_id: str | None = None
    status: str | None = None
    session_key: str | None = None
    active_session_id: str | None = None


class ChannelProfileUpsertRequest(BaseModel):
    channel_type: str | None = None
    enabled: bool = True
    capabilities: dict[str, Any] = Field(default_factory=dict)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelProfileResponse(BaseModel):
    channel_type: str
    enabled: bool
    capabilities: dict[str, Any] = Field(default_factory=dict)
    accounts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _format_sse_event(event_name: str, payload: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_direct_live_event_response(
    *,
    record: Any,
    runtime_id: str,
    service_key: str | None,
    web_channel_account_id: str,
    web_connection_id: str,
    conversation_id: str | None,
) -> WebChannelLiveEventResponse | None:
    live_payload = dict(record.envelope.payload or {})
    event_name = record.envelope.event_name or ""
    if not event_name:
        return None
    target = EventAddress(
        address=web_connection_id,
        address_kind="connection",
        runtime=runtime_id,
        transport="web",
        account=web_channel_account_id,
        conversation=conversation_id,
        connection=web_connection_id,
        metadata={
            "path": "direct_source",
            "service_key": service_key,
            "source_topic": record.envelope.topic,
            "source_cursor": record.cursor,
        },
    )
    return WebChannelLiveEventResponse(
        event_id=record.envelope.id,
        event_name=event_name,
        topic=record.envelope.topic,
        source_topic=record.envelope.topic,
        source_cursor=record.cursor,
        live=live_payload,
        target=target.to_payload(),
        created_at=record.envelope.created_at.isoformat(),
    )


def _build_direct_observe_event_response(
    *,
    record: Any,
    runtime_id: str,
    service_key: str | None,
    web_channel_account_id: str,
    web_connection_id: str,
    conversation_id: str | None,
) -> WebChannelObserveEventResponse | None:
    fact_payload = dict(record.envelope.payload or {})
    event_name = record.envelope.event_name or ""
    if not event_name:
        return None
    target = EventAddress(
        address=web_connection_id,
        address_kind="connection",
        runtime=runtime_id,
        transport="web",
        account=web_channel_account_id,
        conversation=conversation_id,
        connection=web_connection_id,
        metadata={
            "path": "direct_source",
            "service_key": service_key,
            "source_topic": record.envelope.topic,
            "source_cursor": record.cursor,
        },
    )
    return WebChannelObserveEventResponse(
        event_id=record.envelope.id,
        event_name=event_name,
        topic=record.envelope.topic,
        source_topic=record.envelope.topic,
        source_cursor=record.cursor,
        fact=fact_payload,
        target=target.to_payload(),
        created_at=record.envelope.created_at.isoformat(),
    )


def _resolve_channel_account_profile(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
) -> ChannelAccountProfile | None:
    if profile is None:
        return None
    normalized_account = channel_account_id.strip()
    if not normalized_account:
        return None
    for item in profile.accounts:
        if item.account_id.strip() == normalized_account:
            return item
    return None


def _channel_access_consumer(
    *,
    channel_type: str,
    component: str,
    channel_account_id: str,
    field: str,
) -> AccessConsumerRef:
    normalized_channel = channel_type.strip().lower()
    normalized_account = channel_account_id.strip()
    return AccessConsumerRef(
        consumer_id=(
            f"channels.{normalized_channel}.account:{normalized_account}.{field.strip()}"
        ),
        module="channels",
        component=component,
        runtime_ref=normalized_channel,
        metadata={
            "channel_type": normalized_channel,
            "channel_account_id": normalized_account,
            "field": field,
        },
    )


def _webhook_signature_config(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
    credential_provider: CredentialProvider | None = None,
) -> tuple[str, str] | None:
    account = _resolve_channel_account_profile(
        profile,
        channel_account_id=channel_account_id,
    )
    account_metadata = dict(account.metadata) if account is not None else {}
    profile_metadata = dict(profile.metadata) if profile is not None else {}
    secret = resolve_channel_metadata_binding(
        account_metadata,
        key="webhook_signing_secret",
        description="Webhook signing secret",
        required=False,
        credential_provider=credential_provider,
        consumer=_channel_access_consumer(
            channel_type="webhook",
            component="inbound_signature",
            channel_account_id=channel_account_id,
            field="webhook_signing_secret",
        ),
    )
    if not secret:
        secret = resolve_channel_metadata_binding(
            profile_metadata,
            key="webhook_signing_secret",
            description="Webhook signing secret",
            required=False,
            credential_provider=credential_provider,
            consumer=_channel_access_consumer(
                channel_type="webhook",
                component="inbound_signature",
                channel_account_id=channel_account_id,
                field="webhook_signing_secret",
            ),
        )
    if not secret:
        return None
    raw_header = account_metadata.get("webhook_signature_header")
    if not isinstance(raw_header, str) or not raw_header.strip():
        raw_header = profile_metadata.get("webhook_signature_header")
    header_name = (
        raw_header.strip()
        if isinstance(raw_header, str) and raw_header.strip()
        else "X-Crx-Webhook-Signature"
    )
    return secret.strip(), header_name


def _normalize_webhook_signature(value: str) -> str:
    normalized = value.strip()
    if "=" in normalized:
        _, _, normalized = normalized.partition("=")
    return normalized.strip().lower()


def _verify_webhook_signature(
    *,
    body: bytes,
    provided_signature: str,
    secret: str,
) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(
        _normalize_webhook_signature(provided_signature),
        expected.lower(),
    )


def _normalize_lark_signature(value: str) -> str:
    return value.strip().lower()


def _verify_lark_signature(
    *,
    body: bytes,
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    provided_signature: str,
) -> bool:
    raw = f"{timestamp}{nonce}{encrypt_key}{body.decode('utf-8')}"
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hmac.compare_digest(
        _normalize_lark_signature(provided_signature),
        expected.lower(),
    )


def _decrypt_lark_event(encrypt: str, encrypt_key: str) -> dict[str, Any]:
    encrypted = base64.b64decode(encrypt)
    if len(encrypted) < 16:
        raise ValueError("Encrypted Lark event is too short.")
    iv = encrypted[:16]
    ciphertext = encrypted[16:]
    if len(ciphertext) % 16 != 0:
        raise ValueError("Encrypted Lark event has invalid block length.")
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()
    decoded = decrypted.decode("utf-8", errors="ignore")
    start = decoded.find("{")
    end = decoded.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Decrypted Lark event does not contain JSON payload.")
    payload = json.loads(decoded[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Decrypted Lark event payload must be an object.")
    return payload


def _channel_account_metadata(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
) -> dict[str, Any]:
    account = _resolve_channel_account_profile(
        profile,
        channel_account_id=channel_account_id,
    )
    if account is None:
        return dict(profile.metadata) if profile is not None else {}
    return {
        **(dict(profile.metadata) if profile is not None else {}),
        **dict(account.metadata),
    }


def _ensure_profile_accepts_account(
    profile: ChannelProfile | None,
    *,
    channel_type: str,
    channel_account_id: str,
) -> None:
    if profile is None:
        return
    if not profile.enabled:
        raise HTTPException(
            status_code=409,
            detail=f"Channel profile '{channel_type}' is disabled.",
        )
    account = _resolve_channel_account_profile(
        profile,
        channel_account_id=channel_account_id,
    )
    if account is not None and not account.enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Channel account '{channel_account_id}' is disabled for "
                f"profile '{channel_type}'."
            ),
        )


def _channel_profile_response(profile: ChannelProfile) -> ChannelProfileResponse:
    return ChannelProfileResponse(
        channel_type=profile.channel_type,
        enabled=profile.enabled,
        capabilities=profile.capabilities.to_payload(),
        accounts=[account.to_payload() for account in profile.accounts],
        metadata=dict(profile.metadata),
    )


def _normalize_lark_chat_type(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"p2p", "private", "direct"}:
        return "direct"
    return "group"


def _parse_lark_message_content(message: dict[str, Any]) -> tuple[str, Any]:
    message_type = str(message.get("message_type") or "").strip().lower()
    raw_content = message.get("content")
    parsed_content: Any = raw_content
    if isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed_content = json.loads(raw_content)
        except json.JSONDecodeError:
            parsed_content = raw_content
    return message_type, parsed_content


def _extract_lark_mentions(
    *,
    message: dict[str, Any],
    parsed_content: Any,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    def _append_mention(open_id: object, *, name: object = None, key: object = None) -> None:
        normalized_open_id = str(open_id or "").strip()
        normalized_key = str(key or "").strip()
        dedupe_key = (
            "open_id",
            normalized_open_id or normalized_key,
        )
        if not dedupe_key[1] or dedupe_key in seen_keys:
            return
        seen_keys.add(dedupe_key)
        mention_payload: dict[str, Any] = {}
        if normalized_open_id:
            mention_payload["open_id"] = normalized_open_id
        if normalized_key:
            mention_payload["key"] = normalized_key
        normalized_name = str(name or "").strip()
        if normalized_name:
            mention_payload["name"] = normalized_name
        mentions.append(mention_payload)

    raw_mentions = message.get("mentions")
    if isinstance(raw_mentions, list):
        for item in raw_mentions:
            if not isinstance(item, dict):
                continue
            mention_id = item.get("id")
            mention_id_payload = mention_id if isinstance(mention_id, dict) else {}
            _append_mention(
                mention_id_payload.get("open_id") or item.get("open_id"),
                name=item.get("name"),
                key=item.get("key"),
            )

    text = ""
    if isinstance(parsed_content, dict):
        raw_text = parsed_content.get("text")
        if isinstance(raw_text, str):
            text = raw_text
    elif isinstance(parsed_content, str):
        text = parsed_content
    for match in re.finditer(r'<at\b[^>]*\buser_id="([^"]+)"[^>]*>(.*?)</at>', text):
        _append_mention(match.group(1), name=match.group(2))
    return mentions


def _extract_lark_post_lines(parsed_content: Any) -> list[str]:
    if not isinstance(parsed_content, dict):
        return []
    title_fragments: list[str] = []
    line_fragments: list[str] = []

    for locale_payload in parsed_content.values():
        if not isinstance(locale_payload, dict):
            continue
        raw_title = locale_payload.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            title_fragments.append(raw_title.strip())
        raw_content = locale_payload.get("content")
        if not isinstance(raw_content, list):
            continue
        for row in raw_content:
            if not isinstance(row, list):
                continue
            parts: list[str] = []
            for item in row:
                if not isinstance(item, dict):
                    continue
                item_text = str(item.get("text") or "").strip()
                item_tag = str(item.get("tag") or "").strip().lower()
                if item_text:
                    parts.append(item_text)
                elif item_tag == "img":
                    image_key = str(item.get("image_key") or "").strip()
                    parts.append(f"[image:{image_key}]" if image_key else "[image]")
                elif item_tag == "a":
                    href = str(item.get("href") or "").strip()
                    if href:
                        parts.append(href)
            line = "".join(parts).strip()
            if line:
                line_fragments.append(line)

    normalized_lines: list[str] = []
    seen: set[str] = set()
    for fragment in [*title_fragments, *line_fragments]:
        if fragment not in seen:
            seen.add(fragment)
            normalized_lines.append(fragment)
    return normalized_lines


def _describe_lark_non_text_message(
    *,
    message_type: str,
    parsed_content: Any,
) -> tuple[str, dict[str, Any]]:
    normalized_type = message_type or "unknown"
    details: dict[str, Any] = {
        "message_type": normalized_type,
        "raw_content": parsed_content,
    }
    if normalized_type == "image":
        image_key = (
            str(parsed_content.get("image_key") or "").strip()
            if isinstance(parsed_content, dict)
            else ""
        )
        if image_key:
            details["image_key"] = image_key
        return "[Lark image message]", details
    if normalized_type == "file":
        file_key = (
            str(parsed_content.get("file_key") or "").strip()
            if isinstance(parsed_content, dict)
            else ""
        )
        file_name = (
            str(parsed_content.get("file_name") or "").strip()
            if isinstance(parsed_content, dict)
            else ""
        )
        if file_key:
            details["file_key"] = file_key
        if file_name:
            details["file_name"] = file_name
            return f"[Lark file: {file_name}]", details
        return "[Lark file message]", details
    if normalized_type == "post":
        lines = _extract_lark_post_lines(parsed_content)
        if lines:
            details["post_lines"] = list(lines)
            return "\n".join(lines), details
        return "[Lark post message]", details
    if normalized_type == "audio":
        return "[Lark audio message]", details
    if normalized_type == "media":
        return "[Lark media message]", details
    if normalized_type == "sticker":
        return "[Lark sticker message]", details
    return f"[Lark {normalized_type} message]", details


def _normalize_lark_message_content(
    message: dict[str, Any],
    *,
    mentions: list[dict[str, Any]] | None = None,
) -> Any:
    message_type, parsed_content = _parse_lark_message_content(message)
    resolved_mentions = list(mentions or [])
    if message_type == "text":
        text = ""
        if isinstance(parsed_content, dict):
            raw_text = parsed_content.get("text")
            if isinstance(raw_text, str):
                text = raw_text
        elif isinstance(parsed_content, str):
            text = parsed_content
        payload: dict[str, Any] = {
            "blocks": [{"type": "text", "text": text}],
            "text": text,
        }
        if resolved_mentions:
            payload["metadata"] = {"mentions": resolved_mentions}
        return payload
    placeholder_text, details = _describe_lark_non_text_message(
        message_type=message_type,
        parsed_content=parsed_content,
    )
    details["mentions"] = resolved_mentions
    return {
        "blocks": [{"type": "text", "text": placeholder_text}],
        "text": placeholder_text,
        "metadata": details,
    }


def _runtime_summary_response(
    *,
    container: AppContainer,
    runtime,
) -> ChannelRuntimeSummaryResponse:
    account_bindings = container.channel_runtime_manager.list_account_bindings(
        runtime_id=runtime.runtime_id,
    )
    connection_bindings = container.channel_runtime_manager.list_connection_bindings(
        runtime_id=runtime.runtime_id,
    )
    return ChannelRuntimeSummaryResponse(
        runtime_id=runtime.runtime_id,
        channel_type=runtime.channel_type,
        service_key=runtime.service_key,
        status=runtime.status,
        registered_at=runtime.registered_at.isoformat(),
        last_heartbeat_at=runtime.last_heartbeat_at.isoformat(),
        account_count=len(account_bindings),
        connection_count=len(connection_bindings),
    )


@router.get("/profiles")
def list_channel_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ChannelProfileResponse]:
    return [
        _channel_profile_response(profile)
        for profile in container.channel_profile_service.list_profiles()
    ]


@router.get("/profiles/{channel_type}")
def get_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    profile = container.channel_profile_service.get_profile(channel_type)
    if profile is None:
        raise HTTPException(status_code=404, detail="Channel profile not found.")
    return _channel_profile_response(profile)


@router.put("/profiles/{channel_type}")
def upsert_channel_profile(
    channel_type: str,
    payload: ChannelProfileUpsertRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise HTTPException(status_code=400, detail="channel_type is required.")
    payload_channel = (
        payload.channel_type.strip().lower()
        if isinstance(payload.channel_type, str) and payload.channel_type.strip()
        else normalized_channel
    )
    if payload_channel != normalized_channel:
        raise HTTPException(
            status_code=400,
            detail="channel_type in path and payload must match.",
        )
    try:
        profile = ChannelProfile.from_payload(
            {
                "channel_type": normalized_channel,
                "enabled": payload.enabled,
                "capabilities": dict(payload.capabilities),
                "accounts": [dict(item) for item in payload.accounts],
                "metadata": dict(payload.metadata),
            },
        )
        saved = container.channel_profile_service.upsert_profile(profile)
    except (ChannelValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _channel_profile_response(saved)


@router.post("/profiles/{channel_type}/enable")
def enable_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    try:
        profile = container.channel_profile_service.enable_profile(channel_type)
    except ChannelValidationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "channel_profile_not_found" else 400,
            detail=exc.to_payload() if exc.has_payload else str(exc),
        ) from exc
    return _channel_profile_response(profile)


@router.post("/profiles/{channel_type}/disable")
def disable_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelProfileResponse:
    try:
        profile = container.channel_profile_service.disable_profile(channel_type)
    except ChannelValidationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "channel_profile_not_found" else 400,
            detail=exc.to_payload() if exc.has_payload else str(exc),
        ) from exc
    return _channel_profile_response(profile)


@router.delete("/profiles/{channel_type}")
def remove_channel_profile(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ChannelProfileResponse]:
    config = container.channel_profile_service.remove_profile(channel_type)
    return [_channel_profile_response(profile) for profile in config.profiles]


@router.get("/runtimes")
def list_channel_runtimes(
    container: Annotated[AppContainer, Depends(get_container)],
    channel_type: str | None = Query(default=None),
) -> list[ChannelRuntimeSummaryResponse]:
    runtimes = container.channel_runtime_manager.list_runtimes(
        channel_type=channel_type,
    )
    return [
        _runtime_summary_response(container=container, runtime=runtime)
        for runtime in runtimes
    ]


@router.get("/runtimes/{runtime_id}")
def get_channel_runtime(
    runtime_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelRuntimeDetailResponse:
    runtime = container.channel_runtime_manager.get_runtime(runtime_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Channel runtime not found.")
    account_bindings = container.channel_runtime_manager.list_account_bindings(
        runtime_id=runtime.runtime_id,
    )
    connection_bindings = container.channel_runtime_manager.list_connection_bindings(
        runtime_id=runtime.runtime_id,
    )
    return ChannelRuntimeDetailResponse(
        runtime_id=runtime.runtime_id,
        channel_type=runtime.channel_type,
        service_key=runtime.service_key,
        status=runtime.status,
        capabilities=runtime.capabilities.to_payload(),
        metadata=dict(runtime.metadata),
        registered_at=runtime.registered_at.isoformat(),
        last_heartbeat_at=runtime.last_heartbeat_at.isoformat(),
        account_bindings=[
            ChannelAccountBindingResponse(
                channel_type=item.channel_type,
                channel_account_id=item.channel_account_id,
                runtime_id=item.runtime_id,
                updated_at=item.updated_at.isoformat(),
                metadata=dict(item.metadata),
            )
            for item in account_bindings
        ],
        connection_bindings=[
            ChannelConnectionBindingResponse(
                channel_type=item.channel_type,
                connection_id=item.connection_id,
                runtime_id=item.runtime_id,
                channel_account_id=item.channel_account_id,
                conversation_id=item.conversation_id,
                supports_streaming=item.supports_streaming,
                updated_at=item.updated_at.isoformat(),
                metadata=dict(item.metadata),
            )
            for item in connection_bindings
        ],
    )


@router.get("/dead-letters/{channel_type}")
def list_channel_dead_letters(
    channel_type: str,
    container: Annotated[AppContainer, Depends(get_container)],
    runtime_id: str | None = Query(default=None),
    after_cursor: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ChannelDeadLetterRecordResponse]:
    events_service = container.events_service
    if events_service is None:
        raise HTTPException(
            status_code=503,
            detail="Event service is not available for dead-letter queries.",
        )
    topic = channel_dead_letter_topic(channel_type, runtime_id=runtime_id)
    records = events_service.read_event_topic(
        topic,
        after_cursor=after_cursor.strip() if isinstance(after_cursor, str) and after_cursor.strip() else None,
        limit=limit,
    )
    return [
        ChannelDeadLetterRecordResponse(
            cursor=record.cursor,
            topic=record.envelope.topic,
            event_id=record.envelope.id,
            kind=record.envelope.kind,
            created_at=record.envelope.created_at.isoformat(),
            payload=dict(record.envelope.payload),
            target=(
                record.envelope.target.to_payload()
                if record.envelope.target is not None
                else {}
            ),
        )
        for record in records
    ]


@router.post("/dead-letters/{channel_type}/replay")
def replay_channel_dead_letter(
    channel_type: str,
    payload: ChannelDeadLetterReplayRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ChannelDeadLetterReplayResponse:
    if channel_type.strip().lower() == "webhook":
        try:
            result = container.webhook_channel_runtime_service.replay_dead_letter_record(
                runtime_id=payload.runtime_id,
                cursor=payload.cursor,
                event_id=payload.event_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ChannelDeadLetterReplayResponse(
            replayed=bool(result["replayed"]),
            dead_letter_topic=str(result["dead_letter_topic"]),
            dead_letter_cursor=str(result["dead_letter_cursor"]),
            dead_letter_event_id=str(result["dead_letter_event_id"]),
            outbound_id=str(result["outbound_id"]),
            replay_mode=str(result["replay_mode"]),
            callback_status=(
                str(result["callback_status"])
                if result.get("callback_status") is not None
                else None
            ),
        )
    raise HTTPException(
        status_code=409,
        detail=(
            "Dead-letter replay no longer requeues generic legacy outbound events. "
            "Use the owning channel runtime replay path."
        ),
    )


@router.post("/lark/events/{channel_account_id}")
async def submit_lark_event(
    channel_account_id: str,
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LarkEventAcceptedResponse:
    normalized_account = channel_account_id.strip()
    if not normalized_account:
        raise HTTPException(status_code=400, detail="channel_account_id is required.")
    raw_body = await request.body()
    try:
        raw_payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Lark event payload.") from exc
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=400, detail="Lark event payload must be an object.")
    lark_profile = container.channel_profile_service.get_profile("lark")
    _ensure_profile_accepts_account(
        lark_profile,
        channel_type="lark",
        channel_account_id=normalized_account,
    )
    account_metadata = _channel_account_metadata(
        lark_profile,
        channel_account_id=normalized_account,
    )
    encrypt_key = resolve_channel_metadata_binding(
        account_metadata,
        key="lark_encrypt_key",
        description="Lark encrypt key",
        required=False,
        credential_provider=container.access_service,
        consumer=_channel_access_consumer(
            channel_type="lark",
            component="event_signature",
            channel_account_id=normalized_account,
            field="lark_encrypt_key",
        ),
    ) or ""
    raw_encrypt = raw_payload.get("encrypt")
    if isinstance(raw_encrypt, str) and raw_encrypt.strip():
        if not encrypt_key:
            raise HTTPException(
                status_code=401,
                detail="Encrypted Lark event received but no lark_encrypt_key is configured.",
            )
        timestamp = str(request.headers.get("X-Lark-Request-Timestamp") or "").strip()
        nonce = str(request.headers.get("X-Lark-Request-Nonce") or "").strip()
        signature = str(request.headers.get("X-Lark-Signature") or "").strip()
        if not timestamp or not nonce or not signature:
            raise HTTPException(
                status_code=401,
                detail="Missing required Lark signature headers.",
            )
        if not _verify_lark_signature(
            body=raw_body,
            timestamp=timestamp,
            nonce=nonce,
            encrypt_key=encrypt_key,
            provided_signature=signature,
        ):
            raise HTTPException(status_code=401, detail="Invalid Lark request signature.")
        try:
            raw_payload = _decrypt_lark_event(raw_encrypt.strip(), encrypt_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    verification_token = resolve_channel_metadata_binding(
        account_metadata,
        key="lark_verification_token",
        description="Lark verification token",
        required=False,
        credential_provider=container.access_service,
        consumer=_channel_access_consumer(
            channel_type="lark",
            component="event_verification",
            channel_account_id=normalized_account,
            field="lark_verification_token",
        ),
    ) or ""
    payload_header = raw_payload.get("header")
    header_payload = payload_header if isinstance(payload_header, dict) else {}
    payload_token = str(raw_payload.get("token") or header_payload.get("token") or "").strip()
    if verification_token and payload_token and payload_token != verification_token:
        raise HTTPException(status_code=401, detail="Invalid Lark verification token.")
    challenge = raw_payload.get("challenge")
    if isinstance(challenge, str) and challenge.strip():
        return LarkEventAcceptedResponse(challenge=challenge.strip())

    event_type = str(header_payload.get("event_type") or raw_payload.get("type") or "").strip()
    if event_type != "im.message.receive_v1":
        return LarkEventAcceptedResponse(msg="ignored")

    event = raw_payload.get("event")
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Missing Lark event payload.")
    message = event.get("message")
    sender = event.get("sender")
    if not isinstance(message, dict):
        raise HTTPException(status_code=400, detail="Missing Lark message payload.")
    sender_payload = sender if isinstance(sender, dict) else {}
    sender_id_payload = sender_payload.get("sender_id")
    sender_ids = sender_id_payload if isinstance(sender_id_payload, dict) else {}
    try:
        result = container.lark_channel_runtime_service.submit_message_event(
            normalized_account,
            event_id=str(header_payload.get("event_id") or "").strip() or None,
            sender_open_id=str(sender_ids.get("open_id") or "").strip() or None,
            message=dict(message),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return LarkEventAcceptedResponse(**result)


@router.post("/webhook/inbound/{channel_account_id}")
async def submit_webhook_inbound(
    channel_account_id: str,
    request: Request,
    payload: WebhookInboundRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WebhookInboundAcceptedResponse:
    webhook_profile = container.channel_profile_service.get_profile("webhook")
    _ensure_profile_accepts_account(
        webhook_profile,
        channel_type="webhook",
        channel_account_id=channel_account_id,
    )
    signature_config = _webhook_signature_config(
        webhook_profile,
        channel_account_id=channel_account_id,
        credential_provider=container.access_service,
    )
    if signature_config is not None:
        secret, header_name = signature_config
        provided_signature = request.headers.get(header_name)
        if not isinstance(provided_signature, str) or not provided_signature.strip():
            raise HTTPException(
                status_code=401,
                detail=f"Missing webhook signature header: {header_name}",
            )
        raw_body = await request.body()
        if not _verify_webhook_signature(
            body=raw_body,
            provided_signature=provided_signature,
            secret=secret,
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook signature.")
    try:
        result = container.webhook_channel_runtime_service.submit_inbound(
            channel_account_id,
            content=payload.content,
            callback_url=payload.callback_url,
            agent_id=payload.agent_id,
            llm_id=payload.llm_id,
            chat_type=payload.chat_type,
            peer_id=payload.peer_id,
            conversation_id=payload.conversation_id,
            thread_id=payload.thread_id,
            main_key=payload.main_key,
            direct_scope=payload.direct_scope,
            source=payload.source,
            queue_policy=payload.queue_policy,
            priority=payload.priority,
            max_steps=payload.max_steps,
            callback_metadata=dict(payload.callback_metadata),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return WebhookInboundAcceptedResponse(
        run_id=str(result["run_id"]),
        status=str(result["status"]),
        session_key=(
            str(result["session_key"])
            if result.get("session_key") is not None
            else None
        ),
        active_session_id=(
            str(result["active_session_id"])
            if result.get("active_session_id") is not None
            else None
        ),
        callback_url=str(result["callback_url"]),
    )


def _broadcast_target_matches_connection(
    *,
    target: EventAddress | None,
    connection_id: str,
    channel_account_id: str,
    conversation_id: str | None,
) -> bool:
    if target is None:
        return True
    if target.channel_type not in {None, "web"}:
        return False
    if target.connection_id:
        return target.connection_id == connection_id
    if target.channel_account_id and target.channel_account_id != channel_account_id:
        return False
    if target.conversation_id:
        return target.conversation_id == conversation_id
    return True


@router.post("/web/connections/{connection_id}/subscription")
def update_web_channel_subscription(
    connection_id: str,
    payload: WebChannelSubscriptionUpdateRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WebChannelSubscriptionResponse:
    normalized_connection_id = connection_id.strip()
    if not normalized_connection_id:
        raise HTTPException(status_code=400, detail="connection_id is required.")
    normalized_conversation_id = (
        payload.conversation_id.strip()
        if isinstance(payload.conversation_id, str) and payload.conversation_id.strip()
        else None
    )
    normalized_channel_account_id = (
        payload.channel_account_id.strip()
        if isinstance(payload.channel_account_id, str) and payload.channel_account_id.strip()
        else "default"
    )
    existing_binding = container.channel_runtime_manager.resolve_connection_binding(
        channel_type="web",
        connection_id=normalized_connection_id,
    )
    previous_conversation_id = (
        existing_binding.conversation_id
        if existing_binding is not None
        else None
    )
    binding = container.channel_runtime_manager.update_connection_subscription(
        channel_type="web",
        connection_id=normalized_connection_id,
        conversation_id=normalized_conversation_id,
    )
    if binding is None:
        runtime = container.channel_runtime_manager.resolve_account_runtime(
            channel_type="web",
            channel_account_id=normalized_channel_account_id,
        )
        binding = container.web_channel_runtime_service.bind_connection(
            connection_id=normalized_connection_id,
            channel_account_id=normalized_channel_account_id,
            conversation_id=normalized_conversation_id,
            supports_streaming=True,
            runtime_id=runtime.runtime_id if runtime is not None else "web-runtime-1",
            metadata={},
        )
    conversation_changed = (
        (previous_conversation_id or None) != (binding.conversation_id or None)
    )
    if conversation_changed and binding.conversation_id:
        binding = (
            container.web_channel_runtime_service.ensure_connection_source_cursors(
                connection_id=binding.connection_id,
                conversation_id=binding.conversation_id,
            )
            or binding
        )
    if conversation_changed or existing_binding is None:
        container.events_service.publish(
            Event(
                topic=channel_connection_control_topic(
                    "web",
                    connection_id=binding.connection_id,
                ),
                kind="control",
                ordering_key=binding.connection_id,
                payload={
                    "event_name": "channel.connection.subscription_updated",
                    "channel_type": "web",
                    "channel_account_id": binding.channel_account_id,
                    "connection_id": binding.connection_id,
                    "conversation_id": binding.conversation_id,
                    "runtime_id": binding.runtime_id,
                },
            )
        )
    return WebChannelSubscriptionResponse(
        runtime_id=binding.runtime_id,
        channel_account_id=binding.channel_account_id,
        connection_id=binding.connection_id,
        conversation_id=binding.conversation_id,
        supports_streaming=binding.supports_streaming,
        updated_at=binding.updated_at.isoformat(),
        metadata=dict(binding.metadata),
    )


@router.get("/web/events")
def stream_web_channel_events(
    container: Annotated[AppContainer, Depends(get_container)],
    timeout_seconds: Annotated[float, Query(ge=1.0)] = 30.0,
    channel_account_id: str | None = Query(default=None),
    connection_id: str | None = Query(default=None),
    conversation_id: str | None = Query(default=None),
) -> StreamingResponse:
    events_service = container.events_service
    web_channel_account_id = (
        channel_account_id.strip()
        if isinstance(channel_account_id, str) and channel_account_id.strip()
        else "default"
    )
    web_connection_id = (
        connection_id.strip()
        if isinstance(connection_id, str) and connection_id.strip()
        else f"web-channel-{uuid4().hex}"
    )
    normalized_conversation_id = (
        conversation_id.strip()
        if isinstance(conversation_id, str) and conversation_id.strip()
        else None
    )
    existing_binding = container.channel_runtime_manager.resolve_connection_binding(
        channel_type="web",
        connection_id=web_connection_id,
    )
    connection_binding = container.web_channel_runtime_service.bind_connection(
        connection_id=web_connection_id,
        channel_account_id=(
            existing_binding.channel_account_id
            if existing_binding is not None
            else web_channel_account_id
        ),
        conversation_id=(
            existing_binding.conversation_id
            if existing_binding is not None
            else normalized_conversation_id
        ),
        supports_streaming=True,
        runtime_id=(
            existing_binding.runtime_id
            if existing_binding is not None
            else "web-runtime-1"
        ),
        metadata={
            **(
                dict(existing_binding.metadata)
                if existing_binding is not None
                else {}
            ),
        },
    )
    if connection_binding.conversation_id:
        connection_binding = (
            container.web_channel_runtime_service.ensure_connection_source_cursors(
                connection_id=connection_binding.connection_id,
                conversation_id=connection_binding.conversation_id,
            )
            or connection_binding
        )
    runtime = container.channel_runtime_manager.get_runtime(connection_binding.runtime_id)
    broadcast_topics = tuple(
        dict.fromkeys(
            (
                channel_broadcast_topic("web"),
                channel_broadcast_topic(
                    "web",
                    channel_account_id=web_channel_account_id,
                ),
            ),
        ),
    )
    control_topic = channel_connection_control_topic(
        "web",
        connection_id=web_connection_id,
    )

    def event_stream():
        try:
            deadline = time.monotonic() + timeout_seconds
            broadcast_cursors = {
                topic: events_service.snapshot_event_topic(topic)
                for topic in broadcast_topics
            }
            control_cursor = events_service.snapshot_event_topic(control_topic)

            connected_event = WebChannelConnectedEventResponse(
                runtime_id=connection_binding.runtime_id,
                service_key=runtime.service_key if runtime is not None else None,
                channel_account_id=web_channel_account_id,
                connection_id=web_connection_id,
                conversation_id=connection_binding.conversation_id,
                supports_streaming=connection_binding.supports_streaming,
                metadata=dict(connection_binding.metadata),
            )
            yield _format_sse_event(
                "connected",
                connected_event.model_dump(mode="json"),
            )

            while time.monotonic() < deadline:
                latest_binding = container.channel_runtime_manager.resolve_connection_binding(
                    channel_type="web",
                    connection_id=web_connection_id,
                )
                if latest_binding is not None:
                    connection_binding_ref = latest_binding
                else:
                    connection_binding_ref = connection_binding
                control_records = events_service.read_event_topic(
                    control_topic,
                    after_cursor=control_cursor,
                    limit=20,
                )
                if control_records:
                    control_cursor = control_records[-1].cursor
                direct_live_conversation_id = (
                    connection_binding_ref.conversation_id.strip()
                    if isinstance(connection_binding_ref.conversation_id, str)
                    and connection_binding_ref.conversation_id.strip()
                    else None
                )
                direct_live_topic = (
                    turn_session_live_topic(direct_live_conversation_id)
                    if direct_live_conversation_id is not None
                    else None
                )
                direct_observe_topic = (
                    turn_session_topic(direct_live_conversation_id)
                    if direct_live_conversation_id is not None
                    else None
                )
                if direct_observe_topic is not None:
                    direct_observe_records = (
                        container.web_channel_runtime_service.read_connection_observe_records(
                            connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                            limit=100,
                        )
                    )
                    for record in direct_observe_records:
                        observe_event = _build_direct_observe_event_response(
                            record=record,
                            runtime_id=connection_binding_ref.runtime_id,
                            service_key=runtime.service_key if runtime is not None else None,
                            web_channel_account_id=web_channel_account_id,
                            web_connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                        )
                        if observe_event is None:
                            continue
                        yield _format_sse_event(
                            "observe",
                            observe_event.model_dump(mode="json"),
                        )
                if direct_live_topic is not None:
                    direct_live_records = (
                        container.web_channel_runtime_service.read_connection_live_records(
                            connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                            limit=1,
                        )
                    )
                    for record in direct_live_records:
                        live_event = _build_direct_live_event_response(
                            record=record,
                            runtime_id=connection_binding_ref.runtime_id,
                            service_key=runtime.service_key if runtime is not None else None,
                            web_channel_account_id=web_channel_account_id,
                            web_connection_id=web_connection_id,
                            conversation_id=direct_live_conversation_id,
                        )
                        if live_event is None:
                            continue
                        yield _format_sse_event(
                            "live",
                            live_event.model_dump(mode="json"),
                        )
                for topic in broadcast_topics:
                    records = events_service.read_event_topic(
                        topic,
                        after_cursor=broadcast_cursors.get(topic),
                        limit=100,
                    )
                    if records:
                        broadcast_cursors[topic] = records[-1].cursor
                    for record in records:
                        if not _broadcast_target_matches_connection(
                            target=record.envelope.target,
                            connection_id=web_connection_id,
                            channel_account_id=web_channel_account_id,
                            conversation_id=connection_binding_ref.conversation_id,
                        ):
                            continue
                        broadcast_event = WebChannelBroadcastEventResponse(
                            event_id=record.envelope.id,
                            topic=record.envelope.topic,
                            payload=dict(record.envelope.payload),
                            target=(
                                record.envelope.target.to_payload()
                                if record.envelope.target is not None
                                else {}
                            ),
                            created_at=record.envelope.created_at.isoformat(),
                        )
                        yield _format_sse_event(
                            "broadcast",
                            broadcast_event.model_dump(mode="json"),
                        )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                wait_timeout = remaining
                wait_binding = (
                    container.channel_runtime_manager.resolve_connection_binding(
                        channel_type="web",
                        connection_id=web_connection_id,
                    )
                    or connection_binding_ref
                )
                wait_items: list[EventTopicWatch] = []
                wait_conversation_id = (
                    wait_binding.conversation_id.strip()
                    if isinstance(wait_binding.conversation_id, str)
                    and wait_binding.conversation_id.strip()
                    else None
                )
                wait_items.extend(
                    container.web_channel_runtime_service.build_connection_wait_watches(
                        connection_id=web_connection_id,
                        conversation_id=wait_conversation_id,
                        broadcast_topics=broadcast_topics,
                        broadcast_cursors=broadcast_cursors,
                    )
                )
                wait_items.append(
                    EventTopicWatch(
                        topic=control_topic,
                        after_cursor=control_cursor,
                    )
                )
                events_service.wait_for_event_topics(
                    tuple(wait_items),
                    timeout_seconds=wait_timeout,
                )

            yield _format_sse_event(
                "timeout",
                {
                    "connection_id": web_connection_id,
                    "channel_account_id": web_channel_account_id,
                },
            )
        finally:
            container.web_channel_runtime_service.unbind_connection(web_connection_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Crx-Stream-Role": "primary",
            "X-Crx-Stream-Scope": "channel",
        },
    )
