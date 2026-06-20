from __future__ import annotations

from types import SimpleNamespace

import pytest

from crxzipple.modules.llm.domain.exceptions import LlmNotFoundError
from crxzipple.modules.orchestration.infrastructure.adapters.llm import LlmServiceAdapter


class _MissingProfileService:
    get_profile_calls = 0

    def get_profile(self, llm_id: str):
        self.get_profile_calls += 1
        raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")


class _OptionalMissingProfileService(_MissingProfileService):
    def get_profile_optional(self, llm_id: str):
        return None


def test_llm_service_adapter_uses_configured_profile_as_read_only_fallback() -> None:
    service = _OptionalMissingProfileService()
    adapter = LlmServiceAdapter(
        service,  # type: ignore[arg-type]
        configured_profiles=(
            SimpleNamespace(
                id="openai_codex.gpt-5.4-mini",
                provider="openai_codex",
                api_family="openai_codex_responses",
                model_name="gpt-5.4-mini",
                context_window_tokens=400000,
                model_family="reasoning",
                capabilities=("tool_calling", "reasoning"),
                default_params={"reasoning_effort": "low"},
                credential_binding_id="codex-oauth-default",
                timeout_seconds=90,
                source_kind="imported",
                enabled=True,
            ),
        ),
    )

    profile = adapter.get_profile("openai_codex.gpt-5.4-mini")

    assert profile.id == "openai_codex.gpt-5.4-mini"
    assert profile.model_name == "gpt-5.4-mini"
    assert profile.credential_binding_id == "codex-oauth-default"
    assert service.get_profile_calls == 0


def test_llm_service_adapter_preserves_not_found_when_config_has_no_match() -> None:
    adapter = LlmServiceAdapter(
        _MissingProfileService(),  # type: ignore[arg-type]
        configured_profiles=(),
    )

    with pytest.raises(LlmNotFoundError):
        adapter.get_profile("missing.profile")
