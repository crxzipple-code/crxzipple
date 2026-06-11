from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.domain import Tool


BROWSER_TOOL_SOURCE_ID = "bundled.local_package.browser"


def tool_invocation_authorization_context_attrs(
    tool: Tool,
    *,
    base_attrs: Mapping[str, Any] | None = None,
    arguments: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    attrs = dict(base_attrs or {})
    if not _is_browser_tool(tool):
        return attrs

    profile = _optional_text(arguments.get("profile") if arguments else None)
    if profile is not None:
        attrs["browser_profile"] = profile
        attrs["requested_browser_profile"] = profile
        attrs["browser_profile_source"] = "input.profile"
    profile_pool = _optional_text(arguments.get("profile_pool") if arguments else None)
    if profile_pool is not None:
        attrs["browser_profile_pool"] = profile_pool
        attrs["requested_browser_profile_pool"] = profile_pool
        attrs["browser_profile_pool_source"] = "input.profile_pool"
    return attrs


def _is_browser_tool(tool: Tool) -> bool:
    return tool.source_id == BROWSER_TOOL_SOURCE_ID or tool.id.startswith("browser.")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
