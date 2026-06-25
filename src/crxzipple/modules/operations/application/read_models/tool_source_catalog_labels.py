from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.tool_source_common import (
    record_text,
    record_value,
)


def source_health_tone(status: str, discovery_status: str | None) -> str:
    if status in {"error", "deleted"} or discovery_status == "failed":
        return "danger"
    if status == "disabled":
        return "warning"
    return "success" if status == "active" else "neutral"


def source_endpoint_label(source: Any) -> str:
    provider = _source_provider_config(source)
    for key in ("endpoint_url", "base_url", "spec_location"):
        endpoint = _optional_mapping_text(provider, key)
        if endpoint:
            return truncate_text(endpoint, 72)
    command = provider.get("command")
    if isinstance(command, tuple | list) and command:
        return truncate_text(" ".join(str(item) for item in command), 72)
    return "-"


def source_runtime_dependency_label(source: Any) -> str:
    if _is_browser_source(source):
        return "Browser profile context"
    runtime_requirements = tuple(
        str(item).strip()
        for item in getattr(source, "runtime_requirements", ())
        if str(item).strip()
    )
    return (
        truncate_text(", ".join(runtime_requirements), 72)
        if runtime_requirements
        else "-"
    )


def source_tools_list_label(source: Any, discovery_status: str | None) -> str:
    if record_value(source, "kind") != "mcp":
        return "-"
    if discovery_status == "completed":
        return "Listed"
    if discovery_status == "failed":
        return "Failed"
    return "Not Run"


def _is_browser_source(source: Any) -> bool:
    if record_text(source, "source_id") == "bundled.local_package.browser":
        return True
    config = getattr(source, "config", None)
    return (
        isinstance(config, Mapping)
        and config.get("namespace") == "browser"
        and config.get("package_kind") == "local_package"
    )


def _source_provider_config(source: Any) -> Mapping[str, Any]:
    config = getattr(source, "config", None)
    if not isinstance(config, Mapping):
        return {}
    provider = config.get("provider")
    return provider if isinstance(provider, Mapping) else {}


def _optional_mapping_text(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
