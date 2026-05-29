from __future__ import annotations

from typing import Any, Mapping

from crxzipple.shared.access import (
    AccessConsumerRef,
    CredentialBindingRef,
    CredentialProvider,
)


_SECRET_KEY_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "credential",
    "api_key",
    "private_key",
    "encrypt_key",
)
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


class ChannelCredentialResolutionError(RuntimeError):
    def __init__(
        self,
        *,
        description: str,
        binding_id: str,
        reason: str,
    ) -> None:
        self.description = description.strip() or "Channel credential"
        self.binding_id = binding_id.strip()
        self.reason = reason.strip() or "credential binding is not ready"
        super().__init__(f"{self.description} is not ready: {self.reason}")

    @property
    def code(self) -> str:
        return "access_not_ready"

    def to_payload(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": str(self),
            "description": self.description,
            "binding_id": self.binding_id,
            "reason": self.reason,
        }


def resolve_channel_metadata_binding(
    metadata: Mapping[str, Any],
    *,
    key: str,
    description: str,
    required: bool = False,
    credential_provider: CredentialProvider | None = None,
    consumer: AccessConsumerRef | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> str | None:
    binding_key = f"{key}_binding"
    raw_binding = metadata.get(binding_key)
    if raw_binding is not None:
        if not isinstance(raw_binding, str):
            raise RuntimeError(f"{description} binding must be a string.")
        return _resolve_binding_string(
            raw_binding,
            description=description,
            required=required,
            credential_provider=credential_provider,
            consumer=consumer,
            trace_context=trace_context,
        )
    raw_value = metadata.get(key)
    if raw_value is None:
        if required:
            raise RuntimeError(f"{description} is required.")
        return None
    normalized = str(raw_value).strip()
    if _metadata_key_carries_secret(key):
        raise RuntimeError(
            f"{description} must use an Access credential binding id in "
            f"'{binding_key}', not an inline metadata value.",
        )
    if not normalized:
        if required:
            raise RuntimeError(f"{description} is required.")
        return None
    return normalized


def collect_channel_access_requirements(
    metadata: Mapping[str, Any],
    *,
    binding_keys: tuple[str, ...] = (),
) -> tuple[str, ...]:
    resolved: list[str] = []
    raw_requirements = metadata.get("access_requirements")
    if isinstance(raw_requirements, list):
        for item in raw_requirements:
            _append_unique_requirement(resolved, item)
    for key in binding_keys:
        raw_binding = metadata.get(f"{key}_binding")
        if raw_binding is not None:
            _append_unique_requirement(resolved, raw_binding)
            continue
    return tuple(resolved)


def mask_channel_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    public_metadata: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if key.endswith("_binding"):
            public_metadata[key] = value
            base_key = key.removesuffix("_binding")
            if isinstance(value, str) and value.strip():
                public_metadata.setdefault(
                    f"{base_key}_masked_preview",
                    _masked_preview(value),
                )
            continue
        if _metadata_key_carries_secret(key):
            if isinstance(value, str) and value.strip():
                public_metadata[f"{key}_masked_preview"] = _masked_preview(value)
            elif value is not None:
                public_metadata[f"{key}_masked_preview"] = "***"
            continue
        public_metadata[key] = value
    return public_metadata


def _append_unique_requirement(resolved: list[str], value: object) -> None:
    if not isinstance(value, str):
        return
    normalized = value.strip()
    _reject_direct_credential_source(normalized, description="Channel access requirement")
    if normalized and normalized not in resolved:
        resolved.append(normalized)


def _resolve_binding_string(
    binding: str,
    *,
    description: str,
    required: bool,
    credential_provider: CredentialProvider | None,
    consumer: AccessConsumerRef | None,
    trace_context: Mapping[str, Any] | None,
) -> str | None:
    normalized = binding.strip()
    if not normalized:
        if required:
            raise RuntimeError(f"{description} has an empty credential binding.")
        return None
    _reject_direct_credential_source(normalized, description=description)
    if credential_provider is None:
        raise RuntimeError(f"{description} requires an injected credential provider.")
    if consumer is None:
        raise RuntimeError(f"{description} requires an access consumer.")
    credential_ref = CredentialBindingRef(
        binding_id=normalized,
        source_type="binding",
        source_ref=normalized,
        masked_preview=_masked_preview(normalized),
    )
    try:
        return credential_provider.resolve_credential(
            credential_ref,
            consumer=consumer,
            trace_context=trace_context,
        )
    except ChannelCredentialResolutionError:
        raise
    except Exception as exc:
        raise ChannelCredentialResolutionError(
            description=description,
            binding_id=normalized,
            reason=str(exc).strip() or exc.__class__.__name__,
        ) from exc


def _is_forbidden_codex_auth_json_binding(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized in _forbidden_credential_binding_ids
        or normalized.startswith(
            _forbidden_credential_binding_id_prefixes,
        )
    )


def _reject_direct_credential_source(value: str, *, description: str) -> None:
    normalized = value.strip()
    if normalized.startswith(
        _forbidden_credential_binding_prefixes,
    ) or _is_forbidden_codex_auth_json_binding(
        normalized,
    ):
        raise RuntimeError(
            f"{description} must reference an Access credential binding id, "
            "not a direct credential source.",
        )


def _metadata_key_carries_secret(key: str) -> bool:
    normalized = key.strip().lower()
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)


def _masked_preview(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "***"
    if len(normalized) <= 4:
        return "***"
    if len(normalized) <= 8:
        return f"{normalized[:1]}***{normalized[-1:]}"
    return f"{normalized[:2]}***{normalized[-2:]}"
