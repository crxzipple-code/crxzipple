from __future__ import annotations

import hashlib
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.channels.application.bindings import (
    ChannelCredentialResolutionError,
    resolve_channel_metadata_binding,
)
from crxzipple.modules.channels.domain import ChannelProfile
from crxzipple.modules.channels.interfaces.http_channel_helpers import (
    access_not_ready_http_exception,
    channel_access_consumer,
    ensure_profile_accepts_account,
    resolve_channel_account_profile,
)
from crxzipple.modules.channels.interfaces.http_models import (
    WebhookInboundAcceptedResponse,
    WebhookInboundRequest,
)
from crxzipple.shared.access import CredentialProvider


router = APIRouter()


def _webhook_signature_config(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
    credential_provider: CredentialProvider | None = None,
) -> tuple[str, str] | None:
    account = resolve_channel_account_profile(
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
        consumer=channel_access_consumer(
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


@router.post("/webhook/inbound/{channel_account_id}")
async def submit_webhook_inbound(
    channel_account_id: str,
    request: Request,
    payload: WebhookInboundRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WebhookInboundAcceptedResponse:
    webhook_profile = container.require(AppKey.CHANNEL_PROFILE_SERVICE).get_profile("webhook")
    ensure_profile_accepts_account(
        webhook_profile,
        channel_type="webhook",
        channel_account_id=channel_account_id,
    )
    try:
        signature_config = _webhook_signature_config(
            webhook_profile,
            channel_account_id=channel_account_id,
            credential_provider=container.require(AppKey.ACCESS_SERVICE),
        )
    except ChannelCredentialResolutionError as exc:
        raise access_not_ready_http_exception(exc) from exc
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
        result = container.require(AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE).submit_inbound(
            channel_account_id,
            content=payload.content,
            callback_url=payload.callback_url,
            idempotency_key=payload.idempotency_key,
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
