"""LLM module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.llm.domain import LlmApiFamily
from crxzipple.modules.llm.infrastructure.adapters.registry import LlmAdapterRegistry


def llm_factories() -> tuple[ApplicationFactory, ...]:
    """Build LLM adapter registry and application service."""

    return llm_adapter_registry_factories() + (
        ApplicationFactory(
            key="llm.service",
            provides=(AppKey.LLM_SERVICE,),
            requires=(
                AppKey.UNIT_OF_WORK_FACTORY,
                AppKey.LLM_ADAPTER_REGISTRY,
                AppKey.ACCESS_SERVICE,
            ),
            build=lambda ctx: LlmApplicationService(
                ctx.require(AppKey.UNIT_OF_WORK_FACTORY),
                ctx.require(AppKey.LLM_ADAPTER_REGISTRY),
                credential_provider=ctx.require(AppKey.ACCESS_SERVICE),
            ),
        ),
    )


def llm_adapter_registry_factories() -> tuple[ApplicationFactory, ...]:
    """Build only the module-local LLM adapter registry."""

    return (
        ApplicationFactory(
            key="llm.adapter_registry",
            provides=(AppKey.LLM_ADAPTER_REGISTRY,),
            build=lambda _ctx: build_llm_adapter_registry(),
        ),
    )


def build_llm_adapter_registry() -> LlmAdapterRegistry:
    registry = LlmAdapterRegistry()
    registry.register_factory(
        LlmApiFamily.OPENAI_RESPONSES,
        _build_openai_responses_adapter,
    )
    registry.register_factory(
        LlmApiFamily.OPENAI_CODEX_RESPONSES,
        _build_openai_codex_responses_adapter,
    )
    registry.register_factory(
        LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
        _build_openai_chat_compatible_adapter,
    )
    registry.register_factory(
        LlmApiFamily.ANTHROPIC_MESSAGES,
        _build_anthropic_messages_adapter,
    )
    registry.register_factory(
        LlmApiFamily.GEMINI_GENERATE_CONTENT,
        _build_gemini_generate_content_adapter,
    )
    return registry


def _build_openai_responses_adapter():
    from crxzipple.modules.llm.infrastructure.adapters.openai_responses import (
        OpenAIResponsesAdapter,
    )

    return OpenAIResponsesAdapter()


def _build_openai_codex_responses_adapter():
    from crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses import (
        OpenAICodexResponsesAdapter,
    )

    return OpenAICodexResponsesAdapter()


def _build_openai_chat_compatible_adapter():
    from crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible import (
        OpenAIChatCompatibleAdapter,
    )

    return OpenAIChatCompatibleAdapter()


def _build_anthropic_messages_adapter():
    from crxzipple.modules.llm.infrastructure.adapters.anthropic_messages import (
        AnthropicMessagesAdapter,
    )

    return AnthropicMessagesAdapter()


def _build_gemini_generate_content_adapter():
    from crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content import (
        GeminiGenerateContentAdapter,
    )

    return GeminiGenerateContentAdapter()


__all__ = [
    "build_llm_adapter_registry",
    "llm_adapter_registry_factories",
    "llm_factories",
]
