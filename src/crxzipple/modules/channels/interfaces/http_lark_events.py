from __future__ import annotations

import base64
from typing import Annotated, Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Depends, HTTPException, Request
import hashlib
import hmac
import json

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.channels.application.bindings import (
    ChannelCredentialResolutionError,
    resolve_channel_metadata_binding,
)
from crxzipple.modules.channels.interfaces.http_channel_helpers import (
    access_not_ready_http_exception,
    channel_access_consumer,
    channel_account_metadata,
    ensure_profile_accepts_account,
)
from crxzipple.modules.channels.interfaces.http_models import LarkEventAcceptedResponse


router = APIRouter()


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
    lark_profile = container.require(AppKey.CHANNEL_PROFILE_SERVICE).get_profile("lark")
    ensure_profile_accepts_account(
        lark_profile,
        channel_type="lark",
        channel_account_id=normalized_account,
    )
    account_metadata = channel_account_metadata(
        lark_profile,
        channel_account_id=normalized_account,
    )
    try:
        encrypt_key = resolve_channel_metadata_binding(
            account_metadata,
            key="lark_encrypt_key",
            description="Lark encrypt key",
            required=False,
            credential_provider=container.require(AppKey.ACCESS_SERVICE),
            consumer=channel_access_consumer(
                channel_type="lark",
                component="event_signature",
                channel_account_id=normalized_account,
                field="lark_encrypt_key",
            ),
        ) or ""
    except ChannelCredentialResolutionError as exc:
        raise access_not_ready_http_exception(exc) from exc
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
    try:
        verification_token = resolve_channel_metadata_binding(
            account_metadata,
            key="lark_verification_token",
            description="Lark verification token",
            required=False,
            credential_provider=container.require(AppKey.ACCESS_SERVICE),
            consumer=channel_access_consumer(
                channel_type="lark",
                component="event_verification",
                channel_account_id=normalized_account,
                field="lark_verification_token",
            ),
        ) or ""
    except ChannelCredentialResolutionError as exc:
        raise access_not_ready_http_exception(exc) from exc
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
        result = container.require(AppKey.LARK_CHANNEL_RUNTIME_SERVICE).submit_message_event(
            normalized_account,
            event_id=str(header_payload.get("event_id") or "").strip() or None,
            sender_open_id=str(sender_ids.get("open_id") or "").strip() or None,
            message=dict(message),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return LarkEventAcceptedResponse(**result)
