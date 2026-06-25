from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, Protocol

from crxzipple.modules.artifacts.domain import ArtifactKind, ArtifactVariant
from crxzipple.modules.channels.application.ports import ChannelArtifactReadPort
from crxzipple.modules.channels.application.runtime_helpers import (
    session_item_fact_as_message_payload,
    utcnow,
)
from crxzipple.modules.channels.domain import ChannelInteraction
from crxzipple.modules.events import EventTopicRecord
from crxzipple.shared import SESSION_ITEM_APPENDED_SOURCE_EVENT
from crxzipple.shared.http import request_url


class LarkAccountProfileResolver(Protocol):
    def __call__(self, channel_account_id: str) -> Any:
        ...


class LarkTenantAccessTokenResolver(Protocol):
    def __call__(
        self,
        channel_account_id: str,
        *,
        base_url: str,
    ) -> str:
        ...


def lark_deliver_observe_record_to_channel(
    interaction: ChannelInteraction,
    *,
    record: EventTopicRecord,
    artifact_service: ChannelArtifactReadPort,
    account_profile_resolver: LarkAccountProfileResolver,
    tenant_access_token_resolver: LarkTenantAccessTokenResolver,
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
    reply_address = dict(interaction.reply_address or {})
    account_id, base_url, receive_id_type, receive_id = resolve_reply_target_payload(
        reply_address,
        fallback_channel_account_id=interaction.channel_account_id,
        account_profile_resolver=account_profile_resolver,
    )
    token = tenant_access_token_resolver(
        account_id,
        base_url=base_url,
    )
    payloads, artifact_ids = build_observe_message_payloads(
        interaction,
        receive_id=receive_id,
        reply_address=reply_address,
        base_id=message_id,
        base_url=base_url,
        token=token,
        artifact_service=artifact_service,
    )
    if not payloads:
        return interaction
    message_types = send_lark_payloads(
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
            "last_delivered_at": utcnow().isoformat(),
        },
    )


def resolve_reply_target_payload(
    reply_address: dict[str, Any],
    *,
    fallback_channel_account_id: str | None = None,
    account_profile_resolver: LarkAccountProfileResolver,
) -> tuple[str, str, str, str]:
    account_id = str(reply_address.get("channel_account_id") or "").strip()
    if not account_id:
        account_id = str(fallback_channel_account_id or "").strip()
    if not account_id:
        raise ValueError("missing_channel_account_id")
    account_profile = account_profile_resolver(account_id)
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


def build_observe_message_payloads(
    interaction: ChannelInteraction,
    *,
    receive_id: str,
    reply_address: dict[str, Any],
    base_id: str,
    base_url: str,
    token: str,
    artifact_service: ChannelArtifactReadPort,
) -> tuple[list[dict[str, Any]], list[str]]:
    metadata = dict(interaction.metadata)
    summary_text = str(metadata.get("last_message_summary") or "").strip()
    payloads: list[dict[str, Any]] = []
    if summary_text:
        payloads.append(
            build_lark_message_payload(
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
    for artifact_ref in interaction_reply_artifact_refs(interaction):
        artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
        if not artifact_id or artifact_id in delivered_artifact_ids:
            continue
        payload = build_observe_artifact_payload(
            receive_id=receive_id,
            reply_address=reply_address,
            artifact_ref=artifact_ref,
            base_id=base_id,
            base_url=base_url,
            token=token,
            artifact_service=artifact_service,
        )
        if payload is None:
            continue
        payloads.append(payload)
        artifact_ids.append(artifact_id)
    return payloads, artifact_ids


def build_observe_artifact_payload(
    *,
    receive_id: str,
    reply_address: dict[str, Any],
    artifact_ref: dict[str, Any],
    base_id: str,
    base_url: str,
    token: str,
    artifact_service: ChannelArtifactReadPort,
) -> dict[str, Any] | None:
    artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
    if not artifact_id:
        return None
    artifact = artifact_service.get_artifact(artifact_id)
    if artifact.kind is ArtifactKind.IMAGE:
        image_key = upload_lark_image(
            base_url=base_url,
            token=token,
            artifact_id=artifact_id,
            artifact_service=artifact_service,
        )
        return build_lark_message_payload(
            receive_id=receive_id,
            reply_address=reply_address,
            msg_type="image",
            content={"image_key": image_key},
            base_id=base_id,
            message_key=f"image:{artifact_id}",
        )
    file_key = upload_lark_file(
        base_url=base_url,
        token=token,
        artifact_id=artifact_id,
        artifact_service=artifact_service,
    )
    return build_lark_message_payload(
        receive_id=receive_id,
        reply_address=reply_address,
        msg_type="file",
        content={"file_key": file_key},
        base_id=base_id,
        message_key=f"file:{artifact_id}",
    )


def upload_lark_image(
    *,
    base_url: str,
    token: str,
    artifact_id: str,
    artifact_service: ChannelArtifactReadPort,
) -> str:
    resolved = artifact_service.resolve_variant(
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


def upload_lark_file(
    *,
    base_url: str,
    token: str,
    artifact_id: str,
    artifact_service: ChannelArtifactReadPort,
) -> str:
    resolved = artifact_service.resolve_variant(
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


def interaction_reply_artifact_refs(
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


def send_lark_payloads(
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


def build_lark_message_payload(
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
