from __future__ import annotations

import json
import os

from crxzipple.core.config_env import optional_positive_int
from crxzipple.core.config_tool_provider_models import McpProviderSettings


def load_mcp_provider_settings() -> tuple[McpProviderSettings, ...]:
    raw = os.getenv("APP_TOOL_MCP_PROVIDERS")
    if raw is None or not raw.strip():
        return ()

    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("APP_TOOL_MCP_PROVIDERS must decode to a JSON list.")

    providers: list[McpProviderSettings] = []
    for item in payload:
        providers.append(_mcp_provider_from_item(item))
    return tuple(providers)


def _mcp_provider_from_item(item: object) -> McpProviderSettings:
    if not isinstance(item, dict):
        raise ValueError(
            "APP_TOOL_MCP_PROVIDERS items must decode to JSON objects.",
        )

    name = str(item.get("name", "")).strip()
    if not name:
        raise ValueError("MCP provider name cannot be empty.")

    transport = str(item.get("transport") or "stdio").strip().lower()
    endpoint_url = item.get("endpoint_url")
    if endpoint_url is not None and not isinstance(endpoint_url, str):
        raise ValueError(
            f"MCP provider '{name}' endpoint_url must be a string when provided.",
        )

    return McpProviderSettings(
        name=name,
        command=_mcp_command_parts(item, provider_name=name, transport=transport),
        transport=transport,
        endpoint_url=endpoint_url,
        description=str(item.get("description", "")).strip(),
        timeout_seconds=max(int(item.get("timeout_seconds", 30)), 1),
        max_concurrency=optional_positive_int(
            item.get("max_concurrency"),
            label=f"MCP provider '{name}' max_concurrency",
        ),
        default_effect_ids=_string_tuple(item.get("default_effect_ids", []) or []),
        runtime_requirements=_string_tuple(item.get("runtime_requirements", []) or []),
    )


def _mcp_command_parts(
    item: dict[str, object],
    *,
    provider_name: str,
    transport: str,
) -> tuple[str, ...]:
    command = item.get("command")
    args = item.get("args", [])
    if isinstance(command, list):
        return tuple(str(part).strip() for part in command if str(part).strip())
    if isinstance(command, str) and command.strip():
        if not isinstance(args, list):
            raise ValueError(
                f"MCP provider '{provider_name}' args must decode to a JSON list.",
            )
        return (
            command.strip(),
            *(str(part).strip() for part in args if str(part).strip()),
        )
    if transport == "http":
        return ()
    raise ValueError(
        f"MCP provider '{provider_name}' must define command as a string or list.",
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(part).strip() for part in value if str(part).strip())
