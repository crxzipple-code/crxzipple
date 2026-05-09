from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.channels.domain.value_objects import (
    ChannelAccountProfile,
    ChannelCapabilities,
    ChannelProfile,
)


def channel_profile_from_settings(
    config: Mapping[str, Any],
) -> ChannelProfile:
    payload = _payload_from_config(config)
    channel_type = _required_text(
        payload.get("channel_type")
        or payload.get("channel_kind")
        or payload.get("kind"),
        field_name="channel_type",
    )

    capabilities = _capabilities_from_payload(payload.get("capabilities"))
    accounts = _accounts_from_payload(payload, channel_type=channel_type)
    metadata = _metadata_from_payload(payload)

    return ChannelProfile(
        channel_type=channel_type,
        enabled=bool(payload.get("enabled", True)),
        capabilities=capabilities,
        accounts=accounts,
        metadata=metadata,
    )


def _payload_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config, Mapping):
        return dict(config)
    raise TypeError("Channel settings import config must be a mapping.")


def _capabilities_from_payload(raw: object) -> ChannelCapabilities:
    if raw is None:
        return ChannelCapabilities()
    if isinstance(raw, Mapping):
        return ChannelCapabilities.from_payload(dict(raw))
    raise ValueError("channel capabilities must be an object.")


def _accounts_from_payload(
    payload: Mapping[str, Any],
    *,
    channel_type: str,
) -> tuple[ChannelAccountProfile, ...]:
    raw_accounts = payload.get("accounts")
    accounts: list[ChannelAccountProfile] = []
    if raw_accounts is not None:
        if not isinstance(raw_accounts, list | tuple):
            raise ValueError(
                f"channel profile '{channel_type}' accounts must be a list."
            )
        for index, raw_account in enumerate(raw_accounts):
            if not isinstance(raw_account, Mapping):
                raise ValueError(
                    f"channel profile '{channel_type}' accounts[{index}] must be an object.",
                )
            accounts.append(ChannelAccountProfile.from_payload(dict(raw_account)))

    account_id = _optional_text(payload.get("account_id"))
    if account_id and not any(account.account_id == account_id for account in accounts):
        account_metadata = {}
        raw_transport = payload.get("transport")
        if isinstance(raw_transport, Mapping):
            account_metadata["transport"] = dict(raw_transport)
        accounts.append(
            ChannelAccountProfile(
                account_id=account_id,
                metadata=account_metadata,
            ),
        )

    return tuple(accounts)


def _metadata_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_metadata = payload.get("metadata")
    if raw_metadata is None:
        metadata: dict[str, Any] = {}
    elif isinstance(raw_metadata, Mapping):
        metadata = dict(raw_metadata)
    else:
        raise ValueError("channel metadata must be an object.")

    for key in ("profile_id", "id", "display_name", "transport", "routing"):
        value = payload.get(key)
        if value is None or key in metadata:
            continue
        metadata[key] = dict(value) if isinstance(value, Mapping) else value
    return metadata


def _required_text(value: object, *, field_name: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = ["channel_profile_from_settings"]
