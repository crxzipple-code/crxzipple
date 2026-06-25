from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.llm.application.adapters import LlmAdapterRequest
from crxzipple.modules.llm.application.runtime_request_snapshot import (
    runtime_request_context_from_metadata,
)
from crxzipple.modules.llm.domain.entities import LlmInvocation, LlmProfile
from crxzipple.modules.llm.domain import LlmProviderContinuation
from crxzipple.shared.access import (
    AccessConsumerRef,
    CredentialBindingRef,
    CredentialProvider,
)


@dataclass(slots=True)
class LlmAdapterRequestBuilder:
    credential_provider: CredentialProvider | None = None

    def build(
        self,
        profile: LlmProfile,
        invocation: LlmInvocation,
        *,
        continuation: LlmProviderContinuation | None = None,
        runtime_context: Mapping[str, Any] | None = None,
        runtime_route: Mapping[str, Any] | None = None,
        runtime_policy: Mapping[str, Any] | None = None,
    ) -> LlmAdapterRequest:
        effective_runtime_context = (
            dict(runtime_context)
            if isinstance(runtime_context, Mapping) and runtime_context
            else runtime_request_context_from_metadata(invocation.request_metadata)
        )
        provider_transport = provider_transport_for_request(
            invocation.request_overrides,
            continuation,
        )
        effective_runtime_route = (
            dict(runtime_route)
            if isinstance(runtime_route, Mapping) and runtime_route
            else runtime_route_from_invocation(invocation, provider_transport)
        )
        effective_runtime_policy = (
            dict(runtime_policy)
            if isinstance(runtime_policy, Mapping) and runtime_policy
            else runtime_policy_from_invocation(invocation)
        )
        return LlmAdapterRequest(
            invocation_id=invocation.id,
            messages=invocation.messages,
            input_items=invocation.input_items,
            provider_context_messages=invocation.provider_context_messages,
            tool_schemas=invocation.tool_schemas,
            response_format=invocation.response_format,
            request_policy=invocation.request_policy,
            overrides=invocation.request_overrides,
            request_metadata=invocation.request_metadata,
            runtime_context=effective_runtime_context,
            runtime_route=effective_runtime_route,
            runtime_policy=effective_runtime_policy,
            resolved_credential=self.resolve_profile_credential(profile),
            continuation=continuation,
            provider_transport=provider_transport,
        )

    def resolve_profile_credential(self, profile: LlmProfile) -> str | None:
        if self.credential_provider is None:
            return None
        binding_ref = credential_binding_ref_for_profile(profile)
        if binding_ref is None:
            return None
        return self.credential_provider.resolve_credential(
            binding_ref,
            consumer=AccessConsumerRef(
                consumer_id=f"llm.profile:{profile.id}",
                module="llm",
                component="adapter",
                runtime_ref=profile.api_family.value,
                metadata={
                    "provider": profile.provider.value,
                    "model_name": profile.model_name,
                },
            ),
        )


def provider_transport_for_request(
    overrides: Mapping[str, Any],
    continuation: LlmProviderContinuation | None,
) -> str:
    if continuation is not None and continuation.transport is not None:
        return continuation.transport
    value = overrides.get("provider_transport")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "auto"


def runtime_route_from_invocation(
    invocation: LlmInvocation,
    provider_transport: str,
) -> dict[str, Any]:
    route: dict[str, Any] = {
        "llm_id": invocation.llm_id,
        "provider_transport": provider_transport or "auto",
    }
    metadata = invocation.request_metadata
    for key in ("session_key", "active_session_id"):
        value = metadata.get(key) if isinstance(metadata, Mapping) else None
        if value not in (None, "", {}, []):
            route[key] = value
    return route


def runtime_policy_from_invocation(
    invocation: LlmInvocation,
) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    if invocation.request_policy:
        policy["transcript_policy"] = dict(invocation.request_policy)
    reasoning = invocation.request_overrides.get("reasoning")
    if isinstance(reasoning, Mapping) and reasoning:
        policy["reasoning"] = dict(reasoning)
    if invocation.response_format:
        policy["response_format"] = dict(invocation.response_format)
    if invocation.request_overrides:
        policy["provider_option_keys"] = sorted(
            str(key) for key in invocation.request_overrides
        )
    return policy


def credential_binding_ref_for_profile(
    profile: LlmProfile,
) -> CredentialBindingRef | None:
    binding_id = _optional_string_config_value(profile.credential_binding_id)
    if binding_id is None:
        return None
    return CredentialBindingRef(
        binding_id=binding_id,
        source_type="access_credential_binding",
        source_ref=binding_id,
        metadata={
            "module": "llm",
            "profile_id": profile.id,
            "provider": profile.provider.value,
            "api_family": profile.api_family.value,
        },
    )


def _optional_string_config_value(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
