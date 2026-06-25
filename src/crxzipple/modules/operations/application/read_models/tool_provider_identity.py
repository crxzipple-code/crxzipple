from __future__ import annotations

from crxzipple.modules.operations.application.read_models.presenters import title_label
from crxzipple.modules.tool.domain import (
    Tool,
    ToolDefinitionOrigin,
)

_KNOWN_PROVIDER_TAGS = frozenset(
    {
        "anthropic",
        "azure",
        "browserbase",
        "gemini",
        "google",
        "mcp",
        "ollama",
        "openai",
        "openapi",
        "vllm",
    },
)


def tool_provider_key(tool: Tool | None) -> str:
    if tool is None:
        return "unknown"
    runtime_key = tool.resolved_runtime_key().strip()
    runtime_key_lower = runtime_key.lower()
    for prefix in ("openapi.", "mcp."):
        if runtime_key_lower.startswith(prefix):
            parts = runtime_key.split(".")
            if len(parts) >= 2 and parts[1].strip():
                return f"{prefix.removesuffix('.')}:{parts[1].strip().lower()}"
    for tag in tool.tags:
        if tag.startswith("provider:") and tag.removeprefix("provider:").strip():
            return f"provider:{tag.removeprefix('provider:').strip().lower()}"
    provider_tag = next((tag for tag in tool.tags if tag in _KNOWN_PROVIDER_TAGS), None)
    if provider_tag is not None:
        return f"provider:{provider_tag}"
    if runtime_key_lower.startswith("openai_") or tool.id.lower().startswith("openai_"):
        return "provider:openai"
    if tool.definition_origin is ToolDefinitionOrigin.LOCAL_DISCOVERY:
        return "local"
    if tool.definition_origin is ToolDefinitionOrigin.REMOTE_DISCOVERY:
        return "remote"
    return tool.definition_origin.value or "unknown"


def provider_history_label(provider_key: str) -> str:
    if provider_key.startswith("provider:"):
        return provider_key.removeprefix("provider:")
    if provider_key.startswith("openapi:"):
        return f"openapi / {provider_key.removeprefix('openapi:')}"
    if provider_key.startswith("mcp:"):
        return f"mcp / {provider_key.removeprefix('mcp:')}"
    if provider_key in {"local", "remote", "unknown"}:
        return title_label(provider_key)
    return provider_key
