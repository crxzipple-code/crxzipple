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
    if _is_credential_binding(normalized):
        return _resolve_binding_string(
            normalized,
            description=description,
            required=required,
            credential_provider=credential_provider,
            consumer=consumer,
            trace_context=trace_context,
        )
    if not normalized:
        if required:
            raise RuntimeError(f"{description} is required.")
        return None
    return normalized


def collect_channel_binding_env_vars(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    resolved: list[str] = []
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if key.endswith("_binding") and isinstance(value, str):
            env_name = _credential_binding_env_name(value)
            if env_name is not None and env_name not in resolved:
                resolved.append(env_name)
            continue
        if isinstance(value, str):
            env_name = _credential_binding_env_name(value)
            if env_name is not None and env_name not in resolved:
                resolved.append(env_name)
    return tuple(resolved)


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
        raw_value = metadata.get(key)
        if isinstance(raw_value, str) and _is_credential_binding(raw_value):
            _append_unique_requirement(resolved, raw_value)
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
        if isinstance(value, str) and _is_credential_binding(value):
            public_metadata[f"{key}_binding"] = value.strip()
            public_metadata[f"{key}_masked_preview"] = _masked_preview(value)
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
    if credential_provider is None:
        raise RuntimeError(f"{description} requires an injected credential provider.")
    if consumer is None:
        raise RuntimeError(f"{description} requires an access consumer.")
    credential_ref = CredentialBindingRef(
        binding_id=normalized,
        source_type=_credential_source_type(normalized),
        source_ref=normalized,
        masked_preview=_masked_preview(normalized),
    )
    try:
        return credential_provider.resolve_credential(
            credential_ref,
            consumer=consumer,
            trace_context=trace_context,
        )
    except Exception as exc:
        raise RuntimeError(f"{description} {exc}") from exc


def _credential_source_type(binding: str) -> str:
    normalized = binding.strip()
    if normalized.startswith("env:"):
        return "env"
    if normalized.startswith("file:"):
        return "file"
    if _is_codex_auth_json_binding(normalized):
        return "codex_auth_json"
    return "binding"


def _credential_binding_env_name(binding: str) -> str | None:
    normalized = binding.strip()
    if not normalized.startswith("env:"):
        return None
    env_name = normalized.removeprefix("env:").strip()
    return env_name or None


def _is_credential_binding(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(("env:", "file:")) or _is_codex_auth_json_binding(
        normalized,
    )


def _is_codex_auth_json_binding(value: str) -> bool:
    normalized = value.strip()
    return normalized in {
        "codex_auth_json",
        "codex-auth-json",
        "codex_cli",
        "codex-cli",
    } or normalized.startswith(
        (
            "codex_auth_json:",
            "codex-auth-json:",
            "codex_cli:",
            "codex-cli:",
        ),
    )


def _metadata_key_carries_secret(key: str) -> bool:
    normalized = key.strip().lower()
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)


def _masked_preview(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "***"
    if _is_credential_binding(normalized):
        return normalized
    if len(normalized) <= 4:
        return "***"
    if len(normalized) <= 8:
        return f"{normalized[:1]}***{normalized[-1:]}"
    return f"{normalized[:2]}***{normalized[-2:]}"
