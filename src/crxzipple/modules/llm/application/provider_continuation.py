"""Provider-native continuation state helpers owned by the LLM module."""

from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmProviderContinuation,
)
from crxzipple.modules.llm.domain.entities import LlmProfile


def build_provider_continuation_state_from_invocation(
    invocation: Any,
) -> dict[str, object]:
    """Extract provider-native continuation state from an LLM invocation."""

    previous_response_id = _optional_text(
        getattr(invocation, "provider_request_id", None),
    )
    if previous_response_id is None:
        return {}
    preview = getattr(invocation, "provider_request_payload_preview", None)
    if not isinstance(preview, dict):
        return {}
    api_family = _optional_text(preview.get("api_family"))
    transport = _optional_text(preview.get("transport")) or "http"
    if not _supports_provider_native_continuation(
        api_family=api_family,
        transport=transport,
    ):
        return {}
    if api_family == LlmApiFamily.OPENAI_CODEX_RESPONSES.value:
        return {}
    state: dict[str, object] = {
        "mode": "provider_native",
        "provider_family": api_family,
        "transport": transport,
        "previous_response_id": previous_response_id,
        "previous_invocation_id": getattr(invocation, "id", ""),
        "last_request_had_previous_response_id": bool(
            preview.get("has_previous_response_id"),
        ),
    }
    input_fingerprints = _fingerprint_tuple(
        preview.get("input_baseline_fingerprints"),
    ) or _fingerprint_tuple(preview.get("input_item_fingerprints"))
    if input_fingerprints:
        state["input_item_fingerprints"] = list(input_fingerprints)
        state["input_item_count"] = len(input_fingerprints)
    instructions_fingerprint = _optional_text(preview.get("instructions_fingerprint"))
    if instructions_fingerprint is not None:
        state["instructions_fingerprint"] = instructions_fingerprint
    tool_fingerprints = _fingerprint_tuple(preview.get("tool_fingerprints"))
    if tool_fingerprints:
        state["tool_fingerprints"] = list(tool_fingerprints)
    result = getattr(invocation, "result", None)
    result_metadata = getattr(result, "metadata", None)
    if isinstance(result_metadata, dict):
        fallback = result_metadata.get("provider_continuation_fallback")
        fallback_reason = _optional_text(
            result_metadata.get("provider_continuation_fallback_reason"),
        )
        if fallback is not None:
            state["fallback"] = bool(fallback)
        if fallback_reason is not None:
            state["fallback_reason"] = fallback_reason
    return state


def profile_supports_provider_continuation(
    *,
    profile: LlmProfile,
    continuation: LlmProviderContinuation,
    provider_options: dict[str, object] | None = None,
) -> bool:
    capabilities = set(profile.capabilities)
    if LlmCapability.PROVIDER_NATIVE_CONTINUATION not in capabilities:
        return False
    transport = (
        continuation.transport
        or _provider_transport_from_options(provider_options)
        or "http"
    )
    if not _supports_provider_native_continuation(
        api_family=profile.api_family.value,
        transport=transport,
    ):
        return False
    if profile.api_family is LlmApiFamily.OPENAI_CODEX_RESPONSES:
        return False
    return True


def provider_continuation_from_state(
    state: dict[str, object] | None,
) -> LlmProviderContinuation | None:
    if not isinstance(state, dict):
        return None
    if state.get("mode") != "provider_native":
        return None
    if state.get("fallback") is True:
        return None
    previous_response_id = _optional_text(state.get("previous_response_id"))
    if previous_response_id is None:
        return None
    return LlmProviderContinuation(
        mode="provider_native",
        previous_response_id=previous_response_id,
        previous_invocation_id=_optional_text(state.get("previous_invocation_id")),
        provider_family=_optional_text(state.get("provider_family")),
        transport=_optional_text(state.get("transport")),
        input_item_fingerprints=_fingerprint_tuple(
            state.get("input_item_fingerprints"),
        ),
        input_item_count=_optional_int(state.get("input_item_count")),
        instructions_fingerprint=_optional_text(
            state.get("instructions_fingerprint"),
        ),
        tool_fingerprints=_fingerprint_tuple(state.get("tool_fingerprints")),
    )


def _supports_provider_native_continuation(
    *,
    api_family: str | None,
    transport: str,
) -> bool:
    if api_family == LlmApiFamily.OPENAI_RESPONSES.value:
        return True
    return (
        api_family == LlmApiFamily.OPENAI_CODEX_RESPONSES.value
        and transport == "websocket"
    )


def _fingerprint_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _provider_transport_from_options(
    provider_options: dict[str, object] | None,
) -> str | None:
    if not isinstance(provider_options, dict):
        return None
    value = provider_options.get("provider_transport")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None
