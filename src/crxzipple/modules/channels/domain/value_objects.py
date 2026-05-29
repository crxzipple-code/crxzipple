from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


_LARK_CREDENTIAL_SLOT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "lark_app_id": {
        "display_name": "Lark app ID",
        "expected_kind": AccessCredentialKind.API_KEY,
        "required": True,
    },
    "lark_app_secret": {
        "display_name": "Lark app secret",
        "expected_kind": AccessCredentialKind.APP_SECRET,
        "required": True,
    },
    "lark_verification_token": {
        "display_name": "Lark verification token",
        "expected_kind": AccessCredentialKind.WEBHOOK_SECRET,
        "required": False,
    },
    "lark_encrypt_key": {
        "display_name": "Lark encrypt key",
        "expected_kind": AccessCredentialKind.WEBHOOK_SECRET,
        "required": False,
    },
    "lark_bot_open_id": {
        "display_name": "Lark bot open ID",
        "expected_kind": AccessCredentialKind.API_KEY,
        "required": False,
    },
}

_LARK_BINDING_METADATA_KEYS = {
    slot: f"{slot}_binding" for slot in _LARK_CREDENTIAL_SLOT_DEFINITIONS
}

_WEBHOOK_CREDENTIAL_SLOT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "webhook_signing_secret": {
        "display_name": "Webhook signing secret",
        "expected_kind": AccessCredentialKind.WEBHOOK_SECRET,
        "required": False,
    },
}

_WECOM_CREDENTIAL_SLOT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "wecom_corp_id": {
        "display_name": "WeCom corp ID",
        "expected_kind": AccessCredentialKind.API_KEY,
        "required": True,
    },
    "wecom_agent_id": {
        "display_name": "WeCom agent ID",
        "expected_kind": AccessCredentialKind.API_KEY,
        "required": True,
    },
    "wecom_corp_secret": {
        "display_name": "WeCom corp secret",
        "expected_kind": AccessCredentialKind.APP_SECRET,
        "required": True,
    },
    "wecom_token": {
        "display_name": "WeCom callback token",
        "expected_kind": AccessCredentialKind.WEBHOOK_SECRET,
        "required": False,
    },
    "wecom_encoding_aes_key": {
        "display_name": "WeCom encoding AES key",
        "expected_kind": AccessCredentialKind.WEBHOOK_SECRET,
        "required": False,
    },
}

_CHANNEL_CREDENTIAL_SLOT_DEFINITIONS: dict[str, dict[str, dict[str, Any]]] = {
    "lark": _LARK_CREDENTIAL_SLOT_DEFINITIONS,
    "webhook": _WEBHOOK_CREDENTIAL_SLOT_DEFINITIONS,
    "wecom": _WECOM_CREDENTIAL_SLOT_DEFINITIONS,
}

_CHANNEL_BINDING_METADATA_KEYS: dict[str, dict[str, str]] = {
    "lark": _LARK_BINDING_METADATA_KEYS,
    "webhook": {
        slot: f"{slot}_binding" for slot in _WEBHOOK_CREDENTIAL_SLOT_DEFINITIONS
    },
    "wecom": {
        slot: f"{slot}_binding" for slot in _WECOM_CREDENTIAL_SLOT_DEFINITIONS
    },
}
_forbidden_credential_binding_prefixes = ("env:", "file:")
_forbidden_credential_binding_ids = {
    "codex_auth_json",  # forbidden direct source
    "codex-auth-json",  # forbidden direct source
    "codex_cli",  # forbidden direct source
    "codex-cli",  # forbidden direct source
    "auth_ref",  # forbidden legacy credential field
}
_forbidden_credential_binding_id_prefixes = (
    "codex_auth_json:",  # forbidden direct source
    "codex-auth-json:",  # forbidden direct source
    "codex_cli:",  # forbidden direct source
    "codex-cli:",  # forbidden direct source
    "auth_ref:",  # forbidden legacy credential field
)
_forbidden_auth_ref_field = "auth_ref"


def channel_broadcast_topic(
    channel_type: str,
    *,
    channel_account_id: str | None = None,
) -> str:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise ValueError("channel_type is required to build a broadcast topic.")
    normalized_account = (
        channel_account_id.strip()
        if isinstance(channel_account_id, str) and channel_account_id.strip()
        else None
    )
    if normalized_account is not None:
        return f"channel.broadcast.{normalized_channel}.account.{normalized_account}"
    return f"channel.broadcast.{normalized_channel}"

def channel_dead_letter_topic(
    channel_type: str,
    *,
    runtime_id: str | None = None,
) -> str:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise ValueError("channel_type is required to build a dead-letter topic.")
    normalized_runtime = (
        runtime_id.strip()
        if isinstance(runtime_id, str) and runtime_id.strip()
        else None
    )
    if normalized_runtime is not None:
        return f"channel.dead_letter.{normalized_channel}.runtime.{normalized_runtime}"
    return f"channel.dead_letter.{normalized_channel}"


def channel_connection_control_topic(
    channel_type: str,
    *,
    connection_id: str,
) -> str:
    normalized_channel = channel_type.strip().lower()
    if not normalized_channel:
        raise ValueError("channel_type is required to build a connection control topic.")
    normalized_connection = (
        connection_id.strip()
        if isinstance(connection_id, str) and connection_id.strip()
        else None
    )
    if normalized_connection is None:
        raise ValueError("connection_id is required to build a connection control topic.")
    return (
        f"channel.connection.{normalized_channel}.connection."
        f"{normalized_connection}.control"
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return _utcnow()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _credential_bindings_from_payload(
    payload: dict[str, Any],
    *,
    channel_type: str,
) -> dict[str, str]:
    raw_bindings = payload.get("credential_bindings")
    credential_bindings: dict[str, str] = {}
    if raw_bindings is not None:
        if not isinstance(raw_bindings, dict):
            raise ValueError("credential_bindings must be an object.")
        for raw_slot, raw_binding in raw_bindings.items():
            slot = _optional_text(raw_slot)
            binding_id = _optional_text(raw_binding)
            if slot and binding_id:
                _reject_direct_credential_binding(
                    binding_id,
                    context=f"channel profile '{channel_type}' credential_bindings.{slot}",
                )
                credential_bindings[slot] = binding_id

    return credential_bindings


def _reject_direct_credential_binding(binding_id: str, *, context: str) -> None:
    normalized = binding_id.strip()
    if (
        normalized.startswith(_forbidden_credential_binding_prefixes)
        or normalized in _forbidden_credential_binding_ids
        or normalized.startswith(_forbidden_credential_binding_id_prefixes)
    ):
        raise ValueError(
            f"{context} must reference an Access credential binding id, "
            "not a direct credential source.",
        )


def _metadata_with_credential_bindings(
    metadata: dict[str, Any],
    *,
    channel_type: str,
    credential_bindings: dict[str, str],
) -> dict[str, Any]:
    resolved = dict(metadata)
    metadata_keys = _CHANNEL_BINDING_METADATA_KEYS.get(channel_type.strip().lower(), {})
    for slot, metadata_key in metadata_keys.items():
        binding_id = credential_bindings.get(slot)
        if binding_id and metadata_key not in resolved:
            resolved[metadata_key] = binding_id
    return resolved


def _metadata_without_materialized_credential_bindings(
    metadata: dict[str, Any],
    *,
    channel_type: str,
) -> dict[str, Any]:
    cleaned = dict(metadata)
    for metadata_key in _CHANNEL_BINDING_METADATA_KEYS.get(
        channel_type.strip().lower(),
        {},
    ).values():
        cleaned.pop(metadata_key, None)
    return cleaned


def _credential_slot_metadata_keys(channel_type: str) -> set[str]:
    normalized_channel = channel_type.strip().lower()
    return set(_CHANNEL_CREDENTIAL_SLOT_DEFINITIONS.get(normalized_channel, {}))


def channel_account_credential_requirement_set(
    *,
    channel_type: str,
    account_id: str,
    credential_bindings: dict[str, str] | None = None,
) -> AccessCredentialRequirementSet:
    normalized_channel = channel_type.strip().lower()
    normalized_account = account_id.strip()
    consumer = AccessConsumerRef(
        consumer_id=f"channels.{normalized_channel}.account:{normalized_account}",
        module="channels",
        component="account_profile",
        runtime_ref=normalized_channel,
        metadata={
            "channel_type": normalized_channel,
            "channel_account_id": normalized_account,
        },
    )
    bindings = credential_bindings or {}
    declarations: list[AccessCredentialRequirementDeclaration] = []
    for slot, definition in _CHANNEL_CREDENTIAL_SLOT_DEFINITIONS.get(
        normalized_channel,
        {},
    ).items():
        declarations.append(
            AccessCredentialRequirementDeclaration(
                requirement_id=(
                    f"channels.{normalized_channel}."
                    f"account:{normalized_account}.{slot}"
                ),
                consumer=consumer,
                slot=AccessCredentialSlotRef(
                    slot=slot,
                    expected_kind=definition["expected_kind"],
                    binding_id=bindings.get(slot),
                    required=bool(definition["required"]),
                    display_name=definition["display_name"],
                ),
                provider=normalized_channel,
                transport=AccessCredentialTransport.RUNTIME_CONTEXT,
                setup_flow_hint=AccessSetupFlowHint(
                    flow_kind=AccessSetupFlowKind.MANUAL,
                    provider=normalized_channel,
                ),
                metadata={"channel_type": normalized_channel},
            ),
        )
    return AccessCredentialRequirementSet(
        requirement_set_id=(
            f"channels.{normalized_channel}.account:{normalized_account}."
            "credential_requirements"
        ),
        consumer=consumer,
        requirements=tuple(declarations),
    )


def _requirement_set_to_payload(
    requirement_set: AccessCredentialRequirementSet,
) -> dict[str, Any]:
    return {
        "requirement_set_id": requirement_set.requirement_set_id,
        "consumer": _consumer_to_payload(requirement_set.consumer),
        "alternative": requirement_set.alternative,
        "metadata": dict(requirement_set.metadata),
        "requirements": [
            _requirement_to_payload(requirement)
            for requirement in requirement_set.requirements
        ],
    }


def _requirement_to_payload(
    requirement: AccessCredentialRequirementDeclaration,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement.requirement_id,
        "consumer": _consumer_to_payload(requirement.consumer),
        "slot": {
            "slot": requirement.slot.slot,
            "expected_kind": requirement.slot.expected_kind.value,
            "binding_id": requirement.slot.binding_id,
            "required": requirement.slot.required,
            "display_name": requirement.slot.display_name,
            "scopes": list(requirement.slot.scopes),
            "metadata": dict(requirement.slot.metadata),
        },
        "provider": requirement.provider,
        "transport": requirement.transport.value,
        "parameter_name": requirement.parameter_name,
        "setup_flow_hint": {
            "flow_kind": requirement.setup_flow_hint.flow_kind.value,
            "provider": requirement.setup_flow_hint.provider,
            "authorization_url": requirement.setup_flow_hint.authorization_url,
            "token_url": requirement.setup_flow_hint.token_url,
            "device_code_url": requirement.setup_flow_hint.device_code_url,
            "callback_url": requirement.setup_flow_hint.callback_url,
            "metadata": dict(requirement.setup_flow_hint.metadata),
        },
        "metadata": dict(requirement.metadata),
    }


def _consumer_to_payload(consumer: AccessConsumerRef) -> dict[str, Any]:
    return {
        "consumer_id": consumer.consumer_id,
        "module": consumer.module,
        "component": consumer.component,
        "runtime_ref": consumer.runtime_ref,
        "metadata": dict(consumer.metadata),
    }


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    supports_streaming: bool = False
    supports_binary: bool = False
    supports_threading: bool = False
    supports_edit: bool = False
    supports_ack: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "supports_streaming": self.supports_streaming,
            "supports_binary": self.supports_binary,
            "supports_threading": self.supports_threading,
            "supports_edit": self.supports_edit,
            "supports_ack": self.supports_ack,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelCapabilities":
        return cls(
            supports_streaming=bool(payload.get("supports_streaming", False)),
            supports_binary=bool(payload.get("supports_binary", False)),
            supports_threading=bool(payload.get("supports_threading", False)),
            supports_edit=bool(payload.get("supports_edit", False)),
            supports_ack=bool(payload.get("supports_ack", False)),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelAccountProfile:
    account_id: str
    enabled: bool = True
    transport_mode: str = "push"
    credential_bindings: dict[str, str] = field(default_factory=dict)
    credential_requirements: AccessCredentialRequirementSet | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "enabled": self.enabled,
            "transport_mode": self.transport_mode,
            "credential_bindings": dict(self.credential_bindings),
            "credential_requirements": (
                _requirement_set_to_payload(self.credential_requirements)
                if self.credential_requirements is not None
                else None
            ),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        channel_type: str = "",
    ) -> "ChannelAccountProfile":
        account_id = str(payload.get("account_id") or "")
        metadata = dict(payload.get("metadata") or {})
        if payload.get(_forbidden_auth_ref_field) is not None:
            raise ValueError(
                "channel account forbidden auth_ref has been retired; use credential_bindings.",
            )
        credential_bindings = _credential_bindings_from_payload(
            payload,
            channel_type=channel_type,
        )
        metadata_keys = _CHANNEL_BINDING_METADATA_KEYS.get(channel_type.strip().lower(), {})
        if any(metadata.get(key) is not None for key in metadata_keys.values()):
            raise ValueError(
                "channel credential bindings must be declared in "
                "credential_bindings, not metadata *_binding fields.",
            )
        credential_requirements = channel_account_credential_requirement_set(
            channel_type=channel_type,
            account_id=account_id,
            credential_bindings=credential_bindings,
        )
        return cls(
            account_id=account_id,
            enabled=bool(payload.get("enabled", True)),
            transport_mode=str(payload.get("transport_mode") or "push"),
            credential_bindings=credential_bindings,
            credential_requirements=credential_requirements,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class ChannelProfile:
    channel_type: str
    enabled: bool = True
    capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)
    accounts: tuple[ChannelAccountProfile, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        profile_metadata_keys = _CHANNEL_BINDING_METADATA_KEYS.get(
            self.channel_type.strip().lower(),
            {},
        )
        if any(self.metadata.get(key) is not None for key in profile_metadata_keys.values()):
            raise ValueError(
                "channel credential bindings must be declared on account "
                "credential_bindings, not profile metadata *_binding fields.",
            )
        profile_slot_keys = _credential_slot_metadata_keys(self.channel_type)
        if any(self.metadata.get(key) is not None for key in profile_slot_keys):
            raise ValueError(
                "channel credentials must be declared on account credential_bindings, "
                "not profile metadata credential fields.",
            )
        normalized_accounts: list[ChannelAccountProfile] = []
        for account in self.accounts:
            account_metadata_keys = _CHANNEL_BINDING_METADATA_KEYS.get(
                self.channel_type.strip().lower(),
                {},
            )
            if any(
                account.metadata.get(key) is not None
                for key in account_metadata_keys.values()
            ):
                raise ValueError(
                    "channel credential bindings must be declared in "
                    "credential_bindings, not metadata *_binding fields.",
                )
            for slot, binding_id in account.credential_bindings.items():
                _reject_direct_credential_binding(
                    str(binding_id),
                    context=(
                        f"channel profile '{self.channel_type}' "
                        f"credential_bindings.{slot}"
                    ),
                )
            metadata = _metadata_with_credential_bindings(
                dict(account.metadata),
                channel_type=self.channel_type,
                credential_bindings=dict(account.credential_bindings),
            )
            credential_requirements = account.credential_requirements
            if credential_requirements is None:
                credential_requirements = channel_account_credential_requirement_set(
                    channel_type=self.channel_type,
                    account_id=account.account_id,
                    credential_bindings=account.credential_bindings,
                )
            normalized_accounts.append(
                replace(
                    account,
                    metadata=metadata,
                    credential_requirements=credential_requirements,
                ),
            )
        object.__setattr__(self, "accounts", tuple(normalized_accounts))

    def to_payload(self) -> dict[str, Any]:
        account_payloads: list[dict[str, Any]] = []
        for account in self.accounts:
            account_payload = account.to_payload()
            account_payload["metadata"] = _metadata_without_materialized_credential_bindings(
                dict(account_payload.get("metadata") or {}),
                channel_type=self.channel_type,
            )
            if account.credential_requirements is None:
                account_payload["credential_requirements"] = _requirement_set_to_payload(
                    channel_account_credential_requirement_set(
                        channel_type=self.channel_type,
                        account_id=account.account_id,
                        credential_bindings=account.credential_bindings,
                    ),
                )
            account_payloads.append(account_payload)
        return {
            "channel_type": self.channel_type,
            "enabled": self.enabled,
            "capabilities": self.capabilities.to_payload(),
            "accounts": account_payloads,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelProfile":
        raw_accounts = payload.get("accounts")
        account_payloads = raw_accounts if isinstance(raw_accounts, list) else []
        return cls(
            channel_type=str(payload.get("channel_type") or ""),
            enabled=bool(payload.get("enabled", True)),
            capabilities=ChannelCapabilities.from_payload(
                dict(payload.get("capabilities") or {}),
            ),
            accounts=tuple(
                ChannelAccountProfile.from_payload(
                    item,
                    channel_type=str(payload.get("channel_type") or ""),
                )
                for item in account_payloads
                if isinstance(item, dict)
            ),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class ChannelSystemConfig:
    profiles: tuple[ChannelProfile, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "profiles": [profile.to_payload() for profile in self.profiles],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ChannelSystemConfig":
        raw_profiles = payload.get("profiles")
        profile_payloads = raw_profiles if isinstance(raw_profiles, list) else []
        return cls(
            profiles=tuple(
                ChannelProfile.from_payload(item)
                for item in profile_payloads
                if isinstance(item, dict)
            ),
            metadata=dict(payload.get("metadata") or {}),
        )
