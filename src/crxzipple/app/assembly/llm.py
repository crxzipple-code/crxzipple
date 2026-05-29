"""LLM module app assembly."""

from __future__ import annotations

from crxzipple.app.keys import AppKey
from crxzipple.app.plan import ApplicationFactory
from crxzipple.modules.llm.application import LlmApplicationService
from crxzipple.modules.llm.domain import LlmApiFamily
from crxzipple.modules.llm.infrastructure import (
    AnthropicMessagesAdapter,
    GeminiGenerateContentAdapter,
    LlmAdapterRegistry,
    OpenAIChatCompatibleAdapter,
    OpenAICodexResponsesAdapter,
    OpenAIResponsesAdapter,
)


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
    registry.register(
        LlmApiFamily.OPENAI_RESPONSES,
        OpenAIResponsesAdapter(),
    )
    registry.register(
        LlmApiFamily.OPENAI_CODEX_RESPONSES,
        OpenAICodexResponsesAdapter(),
    )
    registry.register(
        LlmApiFamily.OPENAI_CHAT_COMPATIBLE,
        OpenAIChatCompatibleAdapter(),
    )
    registry.register(
        LlmApiFamily.ANTHROPIC_MESSAGES,
        AnthropicMessagesAdapter(),
    )
    registry.register(
        LlmApiFamily.GEMINI_GENERATE_CONTENT,
        GeminiGenerateContentAdapter(),
    )
    return registry


__all__ = [
    "build_llm_adapter_registry",
    "llm_adapter_registry_factories",
    "llm_factories",
]
