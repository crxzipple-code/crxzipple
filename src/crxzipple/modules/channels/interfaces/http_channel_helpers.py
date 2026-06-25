from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from crxzipple.modules.channels.application.bindings import (
    ChannelCredentialResolutionError,
)
from crxzipple.modules.channels.domain import ChannelAccountProfile, ChannelProfile
from crxzipple.shared.access import AccessConsumerRef


def resolve_channel_account_profile(
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


def channel_access_consumer(
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


def access_not_ready_http_exception(
    exc: ChannelCredentialResolutionError,
) -> HTTPException:
    return HTTPException(status_code=503, detail=exc.to_payload())


def channel_account_metadata(
    profile: ChannelProfile | None,
    *,
    channel_account_id: str,
) -> dict[str, Any]:
    account = resolve_channel_account_profile(
        profile,
        channel_account_id=channel_account_id,
    )
    if account is None:
        return dict(profile.metadata) if profile is not None else {}
    return {
        **(dict(profile.metadata) if profile is not None else {}),
        **dict(account.metadata),
    }


def ensure_profile_accepts_account(
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
    account = resolve_channel_account_profile(
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
