from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LlmProfileSettings:
    id: str
    provider: str
    api_family: str
    model_name: str
    context_window_tokens: int | None = None
    model_family: str = "general"
    capabilities: tuple[str, ...] = ()
    default_params: dict[str, Any] = field(default_factory=dict)
    base_url: str | None = None
    credential_binding_id: str | None = None
    timeout_seconds: int = 60
    max_concurrency: int | None = None
    concurrency_key: str | None = None
    source_kind: str = "imported"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class LlmRequestDefaultsSettings:
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    prompt_cache_enabled: bool | None = None
    parallel_tool_calls: bool | None = None
    trace_raw_provider_payload: bool = False
    reasoning_summary_default_visibility: str = "model_and_user_visible"
    extra_body: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.service_tier is not None:
            payload["service_tier"] = self.service_tier
        if self.prompt_cache_enabled is not None:
            payload["prompt_cache_enabled"] = self.prompt_cache_enabled
        if self.parallel_tool_calls is not None:
            payload["parallel_tool_calls"] = self.parallel_tool_calls
        if self.trace_raw_provider_payload:
            payload["trace_raw_provider_payload"] = self.trace_raw_provider_payload
        if self.reasoning_summary_default_visibility != "model_and_user_visible":
            payload["reasoning_summary_default_visibility"] = (
                self.reasoning_summary_default_visibility
            )
        if self.extra_body:
            payload["extra_body"] = dict(self.extra_body)
        return payload
