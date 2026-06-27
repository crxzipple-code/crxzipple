from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolProviderCapability

from .provider_backend_models import (
    PROVIDER_BACKEND_METADATA_KEY,
    PROVIDER_BACKEND_POLICY_METADATA_KEY,
    ToolProviderBackendPolicy,
)


def provider_backend_policy_from_metadata(
    metadata: Mapping[str, Any],
) -> ToolProviderBackendPolicy | None:
    raw_policy = metadata.get(PROVIDER_BACKEND_POLICY_METADATA_KEY)
    if raw_policy in (None, ""):
        return None
    if not isinstance(raw_policy, Mapping):
        raise ToolValidationError("Tool provider backend policy must be a mapping.")
    raw_capability = str(raw_policy.get("capability") or "").strip()
    if not raw_capability:
        raise ToolValidationError(
            "Tool provider backend policy must declare a capability.",
        )
    try:
        capability = ToolProviderCapability(raw_capability)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool provider backend policy capability '{raw_capability}' is unsupported.",
        ) from exc
    default_backend_id = _optional_text(raw_policy.get("default_backend_id"))
    fallback_backend_ids = _text_tuple(raw_policy.get("fallback_backend_ids"))
    allowed_backend_ids = tuple(
        dict.fromkeys(
            (
                *_text_tuple(raw_policy.get("allowed_backend_ids")),
                *((default_backend_id,) if default_backend_id is not None else ()),
                *fallback_backend_ids,
            ),
        ),
    )
    return ToolProviderBackendPolicy(
        capability=capability,
        default_backend_id=default_backend_id,
        fallback_backend_ids=fallback_backend_ids,
        allowed_backend_ids=allowed_backend_ids,
    )


def provider_backend_execution_context_payload(
    context_payload: Mapping[str, Any] | None,
    provider_backend_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not provider_backend_payload:
        return dict(context_payload) if context_payload is not None else None
    payload = dict(context_payload or {})
    payload[PROVIDER_BACKEND_METADATA_KEY] = dict(provider_backend_payload)
    payload["provider_backend_id"] = str(
        provider_backend_payload.get("backend_id") or "",
    ).strip()
    return payload


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple | list):
        return tuple(value)
    if value is None:
        return ()
    return (value,)


def _text_tuple(value: object) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item
            for item in (_optional_text(raw_item) for raw_item in _sequence(value))
            if item
        ),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = [
    "provider_backend_execution_context_payload",
    "provider_backend_policy_from_metadata",
]
