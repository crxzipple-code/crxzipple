"""Provider adapter exports.

Provider implementations are intentionally exported lazily so importing a small
adapter utility, such as the registry, does not import every provider stack.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "AnthropicMessagesAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters.anthropic_messages",
        "AnthropicMessagesAdapter",
    ),
    "GeminiGenerateContentAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters.gemini_generate_content",
        "GeminiGenerateContentAdapter",
    ),
    "LlmAdapterRegistry": (
        "crxzipple.modules.llm.infrastructure.adapters.registry",
        "LlmAdapterRegistry",
    ),
    "OpenAIChatCompatibleAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters.openai_chat_compatible",
        "OpenAIChatCompatibleAdapter",
    ),
    "OpenAICodexResponsesAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses",
        "OpenAICodexResponsesAdapter",
    ),
    "OpenAIResponsesAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters.openai_responses",
        "OpenAIResponsesAdapter",
    ),
    "ProviderProtocolRenderRouter": (
        "crxzipple.modules.llm.infrastructure.adapters.provider_router",
        "ProviderProtocolRenderRouter",
    ),
    "ProviderRenderInput": (
        "crxzipple.modules.llm.infrastructure.adapters.provider_protocol",
        "ProviderRenderInput",
    ),
    "ProviderWireRequest": (
        "crxzipple.modules.llm.infrastructure.adapters.provider_protocol",
        "ProviderWireRequest",
    ),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
