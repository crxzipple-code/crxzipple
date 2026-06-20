"""LLM infrastructure exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "AnthropicMessagesAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters",
        "AnthropicMessagesAdapter",
    ),
    "GeminiGenerateContentAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters",
        "GeminiGenerateContentAdapter",
    ),
    "InMemoryLlmInvocationRepository": (
        "crxzipple.modules.llm.infrastructure.in_memory_repository",
        "InMemoryLlmInvocationRepository",
    ),
    "InMemoryLlmProfileRepository": (
        "crxzipple.modules.llm.infrastructure.in_memory_repository",
        "InMemoryLlmProfileRepository",
    ),
    "LlmAdapterRegistry": (
        "crxzipple.modules.llm.infrastructure.adapters",
        "LlmAdapterRegistry",
    ),
    "OpenAIChatCompatibleAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters",
        "OpenAIChatCompatibleAdapter",
    ),
    "OpenAICodexResponsesAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters",
        "OpenAICodexResponsesAdapter",
    ),
    "OpenAIResponsesAdapter": (
        "crxzipple.modules.llm.infrastructure.adapters",
        "OpenAIResponsesAdapter",
    ),
    "SqlAlchemyLlmInvocationRepository": (
        "crxzipple.modules.llm.infrastructure.persistence",
        "SqlAlchemyLlmInvocationRepository",
    ),
    "SqlAlchemyLlmProfileRepository": (
        "crxzipple.modules.llm.infrastructure.persistence",
        "SqlAlchemyLlmProfileRepository",
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
