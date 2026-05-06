from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.access import (
    CredentialResolutionError,
    CredentialResolver,
    credential_binding_env_name,
    is_credential_binding,
)

_CREDENTIAL_RESOLVER = CredentialResolver()


def resolve_channel_metadata_binding(
    metadata: Mapping[str, Any],
    *,
    key: str,
    description: str,
    required: bool = False,
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
        )
    raw_value = metadata.get(key)
    if raw_value is None:
        if required:
            raise RuntimeError(f"{description} is required.")
        return None
    normalized = str(raw_value).strip()
    if is_credential_binding(normalized):
        return _resolve_binding_string(
            normalized,
            description=description,
            required=required,
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
            env_name = credential_binding_env_name(value)
            if env_name is not None and env_name not in resolved:
                resolved.append(env_name)
            continue
        if isinstance(value, str):
            env_name = credential_binding_env_name(value)
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
        if isinstance(raw_value, str) and is_credential_binding(raw_value):
            _append_unique_requirement(resolved, raw_value)
    return tuple(resolved)


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
) -> str | None:
    normalized = binding.strip()
    if not normalized:
        if required:
            raise RuntimeError(f"{description} has an empty credential binding.")
        return None
    try:
        return _CREDENTIAL_RESOLVER.resolve(normalized, allow_literal=True)
    except CredentialResolutionError as exc:
        raise RuntimeError(f"{description} {exc}") from exc
