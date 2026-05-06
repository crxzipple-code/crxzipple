from __future__ import annotations

import asyncio
import base64
import binascii
import json
from typing import Any, get_args

from crxzipple.modules.browser.domain import (
    BrowserControlKind,
    BrowserPageActionKind,
    BrowserValidationError,
)
from crxzipple.modules.browser.interfaces import (
    BrowserControlRequest,
    BrowserPageActionRequest,
)
from crxzipple.modules.browser.interfaces.profile_payloads import build_profile_diagnostics_payload
from crxzipple.modules.browser.interfaces.profile_payloads import build_profiles_payload
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.shared.content_blocks import (
    file_ref_content_block,
    image_ref_content_block,
    text_content_block,
)

_CONTROL_KINDS = frozenset(get_args(BrowserControlKind))
_PAGE_ACTION_KINDS = frozenset(get_args(BrowserPageActionKind))
_ADVANCED_PAGE_ACTION_KINDS = frozenset(
    {
        "batch",
        "console",
        "cookies",
        "dialog",
        "hover",
        "drag",
        "resize",
        "scroll-into-view",
        "select",
        "press",
        "screenshot",
        "pdf",
        "evaluate",
        "storage",
        "type",
        "upload",
        "download",
        "wait-download",
    }
)
_ACTION_TOOL_PAGE_ACTION_KINDS = frozenset(
    kind for kind in _PAGE_ACTION_KINDS if kind != "snapshot"
)
_SCRIPT_STABILIZE_KINDS = frozenset({"none", "micro", "navigation", "overlay", "auto"})
_SCRIPT_OBSERVE_AFTER_KINDS = frozenset({"none", "interactive", "role", "aria", "auto"})
_SCRIPT_MICRO_STABILIZE_MS = 200
_SCRIPT_OVERLAY_STABILIZE_MS = 200
_SCRIPT_FINAL_OBSERVE_CONTROL_KINDS = frozenset({"open-tab", "navigate"})
_SCRIPT_INHERITED_TARGET_CONTROL_KINDS = frozenset({"navigate", "focus-tab", "close-tab"})

def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_browser_target_id(
    value: object,
    *,
    current_target_id: str | None = None,
) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if normalized.lower() != "current":
        return normalized
    return current_target_id


def _normalize_timeout(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError("timeout_ms must be an integer.") from exc
    if numeric < 1:
        raise BrowserValidationError("timeout_ms must be greater than or equal to 1.")
    return numeric


def _normalize_int(value: object, *, label: str, minimum: int = 0) -> int | None:
    if value in (None, ""):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"{label} must be an integer.") from exc
    if numeric < minimum:
        raise BrowserValidationError(f"{label} must be greater than or equal to {minimum}.")
    return numeric


def _normalize_bool(value: object, *, label: str) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise BrowserValidationError(f"{label} must be a boolean.")


def _coerce_payload(value: object) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise BrowserValidationError("payload must decode to an object.")
    return dict(value)


def _resolve_family(kind: str, family: str | None) -> str:
    if family is not None:
        normalized_family = family.strip().lower()
        if normalized_family in {"control", "page-action"}:
            return normalized_family
        raise BrowserValidationError(
            "family must be either 'control' or 'page-action'.",
        )

    if kind in _CONTROL_KINDS:
        return "control"
    if kind in _PAGE_ACTION_KINDS:
        return "page-action"
    raise BrowserValidationError(f"Unsupported browser kind '{kind}'.")


def _browser_runtime(container: Any) -> tuple[Any, Any, Any, Any]:
    facade = getattr(container, "browser_facade", None)
    serializer = getattr(container, "browser_result_serializer", None)
    system_config_store = getattr(container, "browser_system_config_store", None)
    settings = getattr(container, "settings", None)
    if facade is None or serializer is None or system_config_store is None:
        raise RuntimeError("Browser tool runtime is not available.")
    return facade, serializer, system_config_store, settings


def _profile_listing_runtime(container: Any) -> tuple[Any, Any, Any, Any, Any]:
    system_config_store = getattr(container, "browser_system_config_store", None)
    profile_resolver = getattr(container, "browser_profile_resolver", None)
    capabilities_resolver = getattr(container, "browser_capabilities_resolver", None)
    settings = getattr(container, "settings", None)
    if (
        system_config_store is None
        or profile_resolver is None
        or capabilities_resolver is None
    ):
        raise RuntimeError("Browser profile listing runtime is not available.")
    return system_config_store, profile_resolver, capabilities_resolver, settings, container


def _profiles_payload(container: Any) -> dict[str, Any]:
    return build_profiles_payload(container)


def _entry_summary_code(entry: dict[str, Any]) -> str:
    diagnostics = entry.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return ""
    summary = diagnostics.get("summary")
    if not isinstance(summary, dict):
        return ""
    return str(summary.get("code", "")).strip().lower()


def _entry_can_reuse_personal_state(entry: dict[str, Any]) -> bool:
    diagnostics = entry.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return False
    return bool(diagnostics.get("can_reuse_personal_login_state"))


def _find_launchable_managed_profile(entries: list[dict[str, Any]]) -> str | None:
    for entry in entries:
        if entry.get("driver") != "managed":
            continue
        if _entry_summary_code(entry) in {"ready", "launchable"}:
            return _normalize_text(entry.get("name"))
    return None


def _guidance_for_profile_entry(
    entry: dict[str, Any],
    *,
    fallback_profile_name: str | None = None,
) -> dict[str, Any]:
    name = _normalize_text(entry.get("name")) or "unknown"
    summary_code = _entry_summary_code(entry)
    diagnostics = entry.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    if summary_code == "ready":
        if _entry_can_reuse_personal_state(entry):
            return {
                "recommended_profile": name,
                "next_action": "use-profile",
                "reason": "This profile is ready and can reuse your existing signed-in browser state.",
            }
        return {
            "recommended_profile": name,
            "next_action": "use-profile",
            "reason": "This profile is ready to use now.",
        }
    if summary_code == "launchable":
        return {
            "recommended_profile": name,
            "next_action": "run-open-tab",
            "reason": "This managed profile can launch an isolated browser window on first use.",
        }
    if summary_code == "waiting-browser":
        guidance = {
            "recommended_profile": name,
            "next_action": "open-signed-in-browser-and-retry",
            "reason": "This profile needs your existing signed-in Chromium browser to be open before it can attach.",
        }
        if fallback_profile_name is not None and fallback_profile_name != name:
            guidance["fallback_profile"] = fallback_profile_name
            guidance["fallback_next_action"] = "run-open-tab"
        return guidance
    if summary_code == "bad-mcp-command":
        guidance = {
            "recommended_profile": name,
            "next_action": str(diagnostics.get("recommended_action") or "install-or-configure-chrome-mcp"),
            "reason": "This existing-session profile cannot attach until the Chrome MCP command is fixed.",
        }
        if fallback_profile_name is not None and fallback_profile_name != name:
            guidance["fallback_profile"] = fallback_profile_name
            guidance["fallback_next_action"] = "run-open-tab"
        return guidance
    if summary_code == "waiting-remote-cdp":
        return {
            "recommended_profile": name,
            "next_action": "verify-remote-cdp-url",
            "reason": "This profile depends on an existing remote CDP endpoint that is not reachable yet.",
        }
    if summary_code == "error":
        guidance = {
            "recommended_profile": name,
            "next_action": str(diagnostics.get("recommended_action") or "inspect-profile"),
            "reason": "This profile is not ready and needs attention before browser actions can succeed.",
        }
        if fallback_profile_name is not None and fallback_profile_name != name:
            guidance["fallback_profile"] = fallback_profile_name
            guidance["fallback_next_action"] = "run-open-tab"
        return guidance
    return {
        "recommended_profile": name,
        "next_action": str(diagnostics.get("recommended_action") or "inspect-profile"),
        "reason": str(diagnostics.get("summary_line") or "Inspect this profile before use."),
    }


def _profiles_guidance(payload: dict[str, Any]) -> dict[str, Any]:
    profiles = payload.get("profiles")
    entries = [entry for entry in profiles if isinstance(entry, dict)] if isinstance(profiles, list) else []
    default_profile = _normalize_text(payload.get("default_profile"))
    fallback_profile = _find_launchable_managed_profile(entries)
    default_entry = next(
        (entry for entry in entries if _normalize_text(entry.get("name")) == default_profile),
        None,
    )
    if default_entry is not None:
        guidance = _guidance_for_profile_entry(
            default_entry,
            fallback_profile_name=fallback_profile,
        )
        guidance["applies_to"] = "default-profile"
        return guidance

    if fallback_profile is not None:
        return {
            "recommended_profile": fallback_profile,
            "next_action": "run-open-tab",
            "reason": "A managed browser profile is available as the safest default fallback.",
            "applies_to": "fallback-profile",
        }
    return {
        "next_action": "inspect-profiles",
        "reason": "Review the listed browser profiles before choosing one for the task.",
        "applies_to": "all-profiles",
    }


def _profile_diagnostics_guidance(
    payload: dict[str, Any],
    *,
    system_config_store: Any,
) -> dict[str, Any]:
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        return {
            "next_action": "inspect-profile",
            "reason": "The profile diagnostics payload did not include a resolved profile entry.",
        }

    system = system_config_store.load()
    entries: list[dict[str, Any]] = []
    for configured in getattr(system, "profiles", ()):
        entries.append(
            {
                "name": getattr(configured, "name", None),
                "driver": getattr(configured, "driver", None),
            },
        )
    fallback_profile = None
    for entry in entries:
        if entry.get("driver") == "managed":
            fallback_profile = _normalize_text(entry.get("name"))
            if fallback_profile:
                break
    return _guidance_for_profile_entry(profile, fallback_profile_name=fallback_profile)


def _tool_result(
    *,
    container: Any,
    tool_id: str,
    content: Any,
    family: str | None,
    profile_name: str | None,
    kind: str | None,
    execution_context: ToolExecutionContext | None,
    guidance: dict[str, Any] | None = None,
) -> ToolRunResult:
    content_blocks = _browser_content_blocks(container, content)
    return ToolRunResult.structured(
        details=_browser_result_details(content),
        content=[dict(block) for block in content_blocks],
        metadata={
            "tool": tool_id,
            "family": family,
            "profile_name": profile_name,
            "kind": kind,
            "execution_context": (
                execution_context.to_payload()
                if execution_context is not None
                else None
            ),
            "guidance": dict(guidance) if isinstance(guidance, dict) else None,
        },
    )


def _browser_content_blocks(container: Any, content: Any) -> list[dict[str, Any]]:
    script_blocks = _browser_script_blocks(container, content)
    if script_blocks:
        return script_blocks
    attachment_blocks = _browser_attachment_blocks(container, content)
    if attachment_blocks:
        return attachment_blocks
    console_blocks = _browser_console_blocks(content)
    if console_blocks:
        return console_blocks
    cookies_blocks = _browser_cookies_blocks(content)
    if cookies_blocks:
        return cookies_blocks
    storage_blocks = _browser_storage_blocks(content)
    if storage_blocks:
        return storage_blocks
    snapshot_blocks = _browser_snapshot_blocks(content)
    if snapshot_blocks:
        return snapshot_blocks
    tabs_blocks = _browser_tabs_blocks(content)
    if tabs_blocks:
        return tabs_blocks
    summary = _browser_result_summary(content)
    if summary is None:
        return []
    return [text_content_block(summary)]


def _browser_result_summary(content: Any) -> str | None:
    return _browser_result_summary_inner(content, seen=set())


def _browser_result_summary_inner(content: Any, *, seen: set[int]) -> str | None:
    if not isinstance(content, dict):
        return _normalize_text(content)
    marker = id(content)
    if marker in seen:
        return None
    seen.add(marker)
    console_summary = _browser_console_summary(content)
    if console_summary is not None:
        return console_summary
    cookies_summary = _browser_cookies_summary(content)
    if cookies_summary is not None:
        return cookies_summary
    storage_summary = _browser_storage_summary(content)
    if storage_summary is not None:
        return storage_summary
    evaluate_summary = _browser_evaluate_summary(content)
    if evaluate_summary is not None:
        return evaluate_summary
    if "profile" in content:
        summary = _browser_profile_diagnose_summary(content)
        if summary is not None:
            return summary
    if "profiles" in content:
        summary = _browser_profiles_summary(content)
        if summary is not None:
            return summary
    message = _normalize_text(content.get("message"))
    if message is not None:
        return message
    ok = content.get("ok")
    if ok is True:
        command = content.get("command")
        if isinstance(command, dict):
            kind = _normalize_text(command.get("kind"))
            if kind is not None:
                return f"Browser {kind} completed."
        return "Browser action completed."
    for key in ("result", "value"):
        nested = content.get(key)
        if nested is None:
            continue
        summary = _browser_result_summary_inner(nested, seen=seen)
        if summary is not None:
            return summary
    return None


def _browser_evaluate_summary(content: dict[str, Any]) -> str | None:
    command = content.get("command")
    if not isinstance(command, dict):
        return None
    if _normalize_text(command.get("kind")) != "evaluate":
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    result = _unwrap_browser_evaluate_result(result)
    return _format_browser_evaluate_result(result)


def _browser_console_summary(content: dict[str, Any]) -> str | None:
    command = content.get("command")
    if not isinstance(command, dict):
        return None
    if _normalize_text(command.get("kind")) != "console":
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    count = result.get("count")
    try:
        numeric_count = max(int(count), 0)
    except (TypeError, ValueError):
        numeric_count = 0
    level = _normalize_text(result.get("level"))
    if numeric_count == 0:
        if level is not None:
            return f"Browser console has no {level} messages."
        return "Browser console has no messages."
    if level is not None:
        return f"Browser console returned {numeric_count} {level} message(s)."
    return f"Browser console returned {numeric_count} message(s)."


def _browser_console_blocks(content: Any) -> list[dict[str, Any]]:
    result = _find_browser_console_result(content)
    if result is None:
        return []
    formatted = _format_browser_console_result(result)
    if formatted is None:
        return []
    return [text_content_block(formatted)]


def _browser_storage_summary(content: dict[str, Any]) -> str | None:
    command = content.get("command")
    if not isinstance(command, dict):
        return None
    if _normalize_text(command.get("kind")) != "storage":
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    storage_kind = _normalize_text(result.get("storage_kind")) or "local"
    operation = _normalize_text(result.get("operation")) or "get"
    values = result.get("values")
    value_count = len(values) if isinstance(values, dict) else 0
    if operation == "clear":
        return f"Cleared {storage_kind} storage."
    if operation == "set":
        key = _normalize_text(result.get("key"))
        if key is not None:
            return f"Updated {storage_kind} storage key '{key}'."
        return f"Updated {storage_kind} storage."
    return f"Read {value_count} {storage_kind} storage entr{'y' if value_count == 1 else 'ies'}."


def _browser_cookies_summary(content: dict[str, Any]) -> str | None:
    command = content.get("command")
    if not isinstance(command, dict):
        return None
    if _normalize_text(command.get("kind")) != "cookies":
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    operation = _normalize_text(result.get("operation")) or "get"
    cookies = result.get("cookies")
    cookie_count = len(cookies) if isinstance(cookies, list) else 0
    if operation == "clear":
        return "Cleared browser cookies."
    if operation == "set":
        return "Updated browser cookies."
    return f"Read {cookie_count} browser cookie{'s' if cookie_count != 1 else ''}."


def _browser_cookies_blocks(content: Any) -> list[dict[str, Any]]:
    result = _find_browser_cookies_result(content)
    if result is None:
        return []
    formatted = _format_browser_cookies_result(result)
    if formatted is None:
        return []
    return [text_content_block(formatted)]


def _browser_storage_blocks(content: Any) -> list[dict[str, Any]]:
    result = _find_browser_storage_result(content)
    if result is None:
        return []
    formatted = _format_browser_storage_result(result)
    if formatted is None:
        return []
    return [text_content_block(formatted)]


def _find_browser_cookies_result(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    if isinstance(command, dict) and _normalize_text(command.get("kind")) == "cookies":
        value = content.get("value")
        if isinstance(value, dict):
            result = value.get("result")
            if isinstance(result, dict):
                return result
    return None


def _find_browser_storage_result(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    if isinstance(command, dict) and _normalize_text(command.get("kind")) == "storage":
        value = content.get("value")
        if isinstance(value, dict):
            result = value.get("result")
            if isinstance(result, dict):
                return result
    return None


def _format_browser_storage_result(result: dict[str, Any]) -> str | None:
    storage_kind = _normalize_text(result.get("storage_kind")) or "local"
    operation = _normalize_text(result.get("operation")) or "get"
    values = result.get("values")
    if not isinstance(values, dict):
        values = {}
    if operation == "clear":
        return f"Storage ({storage_kind}): cleared."
    if operation == "set":
        key = _normalize_text(result.get("key"))
        value = values.get(key) if key is not None else None
        if key is not None:
            return f"Storage ({storage_kind}) set:\n- {key} = {value!r}"
        return f"Storage ({storage_kind}) updated."
    if not values:
        return f"Storage ({storage_kind}): no entries."
    lines = [f"Storage ({storage_kind}):"]
    for key, value in list(values.items())[:20]:
        lines.append(f"- {key} = {value!r}")
    hidden_count = len(values) - min(len(values), 20)
    if hidden_count > 0:
        lines.append(f"... {hidden_count} more entr{'y' if hidden_count == 1 else 'ies'}")
    return "\n".join(lines)


def _format_browser_cookies_result(result: dict[str, Any]) -> str | None:
    operation = _normalize_text(result.get("operation")) or "get"
    cookies = result.get("cookies")
    if not isinstance(cookies, list):
        cookies = []
    if operation == "clear":
        return "Cookies: cleared."
    if operation == "set":
        if not cookies:
            return "Cookies: updated."
        lines = ["Cookies set:"]
        for cookie in cookies[:20]:
            if not isinstance(cookie, dict):
                continue
            name = _normalize_text(cookie.get("name")) or "<unnamed>"
            value = _normalize_text(cookie.get("value")) or ""
            scope = _normalize_text(cookie.get("url")) or _normalize_text(cookie.get("domain")) or ""
            suffix = f" ({scope})" if scope else ""
            lines.append(f"- {name} = {value!r}{suffix}")
        return "\n".join(lines)
    if not cookies:
        return "Cookies: no cookies."
    lines = ["Cookies:"]
    for cookie in cookies[:20]:
        if not isinstance(cookie, dict):
            continue
        name = _normalize_text(cookie.get("name")) or "<unnamed>"
        value = _normalize_text(cookie.get("value")) or ""
        scope = _normalize_text(cookie.get("domain")) or _normalize_text(cookie.get("url")) or ""
        suffix = f" ({scope})" if scope else ""
        lines.append(f"- {name} = {value!r}{suffix}")
    hidden_count = len(cookies) - min(len(cookies), 20)
    if hidden_count > 0:
        lines.append(f"... {hidden_count} more cookie{'s' if hidden_count != 1 else ''}")
    return "\n".join(lines)


def _find_browser_console_result(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    if isinstance(command, dict) and _normalize_text(command.get("kind")) == "console":
        value = content.get("value")
        if isinstance(value, dict):
            result = value.get("result")
            if isinstance(result, dict):
                return result
    return None


def _format_browser_console_result(result: dict[str, Any]) -> str | None:
    messages = result.get("messages")
    if not isinstance(messages, list):
        return None
    lines: list[str] = []
    level = _normalize_text(result.get("level"))
    if not messages:
        if level is not None:
            return f"Console ({level}): no messages."
        return "Console: no messages."
    header = f"Console ({level})" if level is not None else "Console"
    lines.append(f"{header}:")
    for message in messages[:20]:
        if not isinstance(message, dict):
            continue
        message_level = _normalize_text(message.get("level")) or "log"
        text = _normalize_text(message.get("text")) or ""
        location = message.get("location")
        location_text = None
        if isinstance(location, dict):
            url = _normalize_text(location.get("url"))
            line_number = location.get("line_number")
            column_number = location.get("column_number")
            if url is not None:
                suffix = ""
                if isinstance(line_number, int):
                    suffix = f":{line_number}"
                    if isinstance(column_number, int):
                        suffix += f":{column_number}"
                location_text = f"{url}{suffix}"
        line = f"- [{message_level}] {text}"
        if location_text is not None:
            line += f" ({location_text})"
        lines.append(line)
    hidden_count = len(messages) - min(len(messages), 20)
    if hidden_count > 0:
        lines.append(f"... {hidden_count} more message(s)")
    return "\n".join(lines)


def _browser_snapshot_blocks(content: Any) -> list[dict[str, Any]]:
    result = _find_browser_snapshot_result(content)
    if result is None:
        return []
    formatted = _format_browser_snapshot_result(result)
    if formatted is None:
        return []
    return [text_content_block(formatted)]


def _find_browser_snapshot_result(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    if isinstance(command, dict) and _normalize_text(command.get("kind")) == "snapshot":
        value = content.get("value")
        if isinstance(value, dict):
            result = value.get("result")
            if isinstance(result, dict):
                return result
    return None


def _format_browser_snapshot_result(result: dict[str, Any]) -> str | None:
    snapshot_format = _normalize_text(result.get("format")) or "snapshot"
    value = result.get("value")
    if snapshot_format in {"html", "text", "title", "url"}:
        if isinstance(value, str):
            if snapshot_format == "html":
                return f"Snapshot (html):\n```html\n{value}\n```"
            if snapshot_format == "text":
                return f"Snapshot (text):\n{value}"
            return f"Snapshot ({snapshot_format}): {value}"
    if snapshot_format in {"interactive", "role", "aria"} and isinstance(value, dict):
        snapshot_text = value.get("snapshot")
        if isinstance(snapshot_text, str):
            return f"Snapshot ({snapshot_format}):\n```text\n{snapshot_text}\n```"
    try:
        rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        rendered = str(value)
    if not rendered.strip():
        return None
    return f"Snapshot ({snapshot_format}):\n```json\n{rendered}\n```"


def _browser_tabs_blocks(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, dict):
        return []
    command = content.get("command")
    if not isinstance(command, dict) or _normalize_text(command.get("kind")) != "list-tabs":
        return []
    value = content.get("value")
    if not isinstance(value, list):
        return []
    tab_lines: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        target_id = _normalize_text(item.get("target_id")) or "unknown"
        tab_type = _normalize_text(item.get("type")) or "unknown"
        title = _normalize_text(item.get("title")) or "(untitled)"
        url = _normalize_text(item.get("url")) or "(no url)"
        tab_lines.append(
            f"{index}. [{target_id}] ({tab_type}) {title}\n   {url}",
        )
    if not tab_lines:
        return []
    return [text_content_block("Browser tabs:\n" + "\n".join(tab_lines))]


def _unwrap_browser_evaluate_result(result: Any) -> Any:
    while isinstance(result, dict):
        if _normalize_text(result.get("kind")) == "evaluate" and "value" in result:
            result = result.get("value")
            continue
        if tuple(result.keys()) == ("value",):
            result = result.get("value")
            continue
        return result
    return result


def _format_browser_evaluate_result(result: Any) -> str:
    if result is None:
        return "Evaluate result: null"
    if isinstance(result, str):
        text = result.strip()
        return f"Evaluate result:\n{text}" if text else "Evaluate result: \"\""
    if isinstance(result, bool):
        return f"Evaluate result: {'true' if result else 'false'}"
    if isinstance(result, (int, float)):
        return f"Evaluate result: {result}"
    try:
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        rendered = str(result)
    if len(rendered) > 4000:
        rendered = f"{rendered[:3997].rstrip()}..."
    return f"Evaluate result:\n```json\n{rendered}\n```"


def _browser_profiles_summary(content: dict[str, Any]) -> str | None:
    profiles = content.get("profiles")
    entries = [entry for entry in profiles if isinstance(entry, dict)] if isinstance(profiles, list) else []
    default_profile = _normalize_text(content.get("default_profile"))
    names = [
        _normalize_text(entry.get("name"))
        for entry in entries
        if _normalize_text(entry.get("name")) is not None
    ]
    guidance = content.get("guidance")
    if not names and not isinstance(guidance, dict):
        return None
    parts: list[str] = []
    if names:
        parts.append(f"Browser profiles available: {', '.join(names)}.")
    if default_profile is not None:
        parts.append(f"Default profile: {default_profile}.")
    if isinstance(guidance, dict):
        reason = _normalize_text(guidance.get("reason"))
        if reason is not None:
            parts.append(reason)
    return " ".join(parts).strip() or None


def _browser_profile_diagnose_summary(content: dict[str, Any]) -> str | None:
    profile = content.get("profile")
    if not isinstance(profile, dict):
        return None
    name = _normalize_text(profile.get("name")) or "unknown"
    diagnostics = profile.get("diagnostics")
    if isinstance(diagnostics, dict):
        summary_line = _normalize_text(diagnostics.get("summary_line"))
        if summary_line is not None:
            return f"Profile {name}: {summary_line}"
    guidance = content.get("guidance")
    if isinstance(guidance, dict):
        reason = _normalize_text(guidance.get("reason"))
        if reason is not None:
            return f"Profile {name}: {reason}"
    return f"Profile {name} diagnostics loaded."


def _browser_result_details(content: Any) -> Any:
    if not isinstance(content, dict):
        return content
    return _sanitize_browser_result_details(content)


def _sanitize_browser_result_details(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {str(key): _sanitize_browser_result_details(item) for key, item in value.items()}
        kind = _normalize_text(sanitized.get("kind"))
        content_type = _normalize_text(sanitized.get("content_type"))
        if kind in {"screenshot", "pdf", "download"} and content_type is not None:
            data = sanitized.get("data")
            if isinstance(data, str) and data:
                sanitized.pop("data", None)
                sanitized["attachment_in_content"] = True
        return sanitized
    if isinstance(value, list):
        return [_sanitize_browser_result_details(item) for item in value]
    return value


def _browser_attachment_blocks(container: Any, content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, dict):
        return []
    attachment = _find_browser_attachment_payload(content)
    if attachment is None:
        return []
    kind, content_type, data, attachment_name = attachment
    if kind == "screenshot":
        return [
            text_content_block("Browser screenshot captured."),
            _browser_attachment_block(
                container,
                kind="screenshot",
                content_type=content_type,
                data=data,
                fallback_name=_default_browser_attachment_name(
                    kind="screenshot",
                    content_type=content_type,
                ),
            ),
        ]
    if kind == "pdf":
        return [
            text_content_block("Browser PDF captured."),
            _browser_attachment_block(
                container,
                kind="pdf",
                content_type=content_type,
                data=data,
                fallback_name="browser-output.pdf",
            ),
        ]
    if kind == "download":
        return [
            text_content_block("Browser download captured."),
            _browser_attachment_block(
                container,
                kind="download",
                content_type=content_type,
                data=data,
                fallback_name=attachment_name or "browser-download.bin",
            ),
        ]
    return []


def _find_browser_attachment_payload(
    value: Any,
) -> tuple[str, str, str, str | None] | None:
    if isinstance(value, dict):
        kind = _normalize_text(value.get("kind"))
        content_type = _normalize_text(value.get("content_type"))
        data = _normalize_text(value.get("data"))
        if kind in {"screenshot", "pdf"} and content_type is not None and data is not None:
            return kind, content_type, data, _normalize_text(value.get("name"))
        if kind == "download" and content_type is not None and data is not None:
            return kind, content_type, data, _normalize_text(value.get("name"))
        for item in value.values():
            resolved = _find_browser_attachment_payload(item)
            if resolved is not None:
                return resolved
        return None
    if isinstance(value, list):
        for item in value:
            resolved = _find_browser_attachment_payload(item)
            if resolved is not None:
                return resolved
    return None


def _browser_attachment_block(
    container: Any,
    *,
    kind: str,
    content_type: str,
    data: str,
    fallback_name: str,
) -> dict[str, Any]:
    artifact_service = getattr(container, "artifact_service", None)
    decoded = _decode_browser_attachment_data(data)
    if artifact_service is None or decoded is None:
        return _inline_browser_attachment_block(
            kind=kind,
            content_type=content_type,
            data=data,
            fallback_name=fallback_name,
        )
    artifact = artifact_service.create_artifact(
        data=decoded,
        mime_type=content_type,
        name=fallback_name,
        metadata={
            "source": "browser",
            "attachment_kind": kind,
        },
    )
    if kind == "screenshot":
        return image_ref_content_block(
            artifact_id=artifact.id,
            mime_type=artifact.mime_type,
            name=artifact.name,
            width=artifact.width,
            height=artifact.height,
            preview_url=f"/artifacts/{artifact.id}/preview",
            original_url=f"/artifacts/{artifact.id}/original",
        )
    return file_ref_content_block(
        artifact_id=artifact.id,
        mime_type=artifact.mime_type,
        name=artifact.name,
        download_url=f"/artifacts/{artifact.id}/download",
    )


def _inline_browser_attachment_block(
    *,
    kind: str,
    content_type: str,
    data: str,
    fallback_name: str,
) -> dict[str, Any]:
    if kind == "screenshot":
        return {
            "type": "image",
            "mime_type": content_type,
            "data": data,
        }
    return {
        "type": "file",
        "mime_type": content_type,
        "data": data,
        "name": fallback_name,
    }


def _decode_browser_attachment_data(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None


def _default_browser_attachment_name(*, kind: str, content_type: str) -> str:
    if kind == "pdf":
        return "browser-output.pdf"
    if content_type == "image/jpeg":
        return "browser-screenshot.jpg"
    return "browser-screenshot.png"


def _augment_browser_error_with_guidance(
    *,
    container: Any,
    profile_name: str,
    exc: BrowserValidationError,
) -> BrowserValidationError:
    message = str(exc).strip().lower()
    if (
        "handshake status 403" in message
        or "rejected an incoming websocket connection" in message
        or "remote-allow-origins" in message
    ):
        return BrowserValidationError(
            f"{exc} Next: reset the managed browser for profile '{profile_name}' and run-open-tab again. "
            "Reason: The running browser was launched with a mismatched remote-allow-origins policy."
        )
    if (
        "requires ref or selector targeting" in message
        or "wait requires " in message
        or "browser script " in message
        or "steps must be" in message
        or "must decode to an object" in message
        or "payload." in message
        or " is required." in message
        or " must be " in message
    ):
        return exc
    try:
        diagnostics_payload = build_profile_diagnostics_payload(
            container,
            profile_name=profile_name,
        )
    except Exception:  # noqa: BLE001
        return exc

    guidance = _profile_diagnostics_guidance(
        diagnostics_payload,
        system_config_store=container.browser_system_config_store,
    )

    next_action = _normalize_text(guidance.get("next_action"))
    reason = _normalize_text(guidance.get("reason"))
    recommended_profile = _normalize_text(guidance.get("recommended_profile"))
    fallback_profile = _normalize_text(guidance.get("fallback_profile"))
    fallback_next_action = _normalize_text(guidance.get("fallback_next_action"))

    guidance_parts: list[str] = []
    if next_action is not None:
        if recommended_profile is not None:
            guidance_parts.append(
                f"Next: {next_action} with profile '{recommended_profile}'.",
            )
        else:
            guidance_parts.append(f"Next: {next_action}.")
    if fallback_profile is not None and fallback_next_action is not None:
        guidance_parts.append(
            f"Fallback: use profile '{fallback_profile}' and {fallback_next_action}.",
        )
    if reason is not None:
        guidance_parts.append(f"Reason: {reason}")
    if not guidance_parts:
        return exc
    return BrowserValidationError(f"{exc} {' '.join(guidance_parts)}")


def _resolve_profile_name(arguments: dict[str, Any], system_config_store: Any) -> str:
    return (
        _normalize_text(arguments.get("profile"))
        or _normalize_text(arguments.get("profile_name"))
        or system_config_store.load().default_profile
    )


def _ensure_browser_enabled(settings: Any) -> None:
    if settings is not None and not getattr(settings, "browser_enabled", True):
        raise BrowserValidationError("Browser module is disabled.")


def _execute_control(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    tool_id: str,
    kind: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    content, profile_name = _run_control_content(
        container=container,
        facade=facade,
        serializer=serializer,
        system_config_store=system_config_store,
        settings=settings,
        kind=kind,
        arguments=arguments,
    )
    return _tool_result(
        container=container,
        tool_id=tool_id,
        content=content,
        family="control",
        profile_name=profile_name,
        kind=kind,
        execution_context=execution_context,
    )


def _run_control_content(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    kind: str,
    arguments: dict[str, Any],
) -> tuple[Any, str]:
    _ensure_browser_enabled(settings)
    profile_name = _resolve_profile_name(arguments, system_config_store)
    target_id = _normalize_browser_target_id(arguments.get("target_id"))
    timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    payload = _coerce_payload(arguments.get("payload"))
    url = _normalize_text(arguments.get("url"))
    if url is not None:
        payload.setdefault("url", url)
    try:
        result = facade.execute(
            BrowserControlRequest(
                profile_name=profile_name,
                kind=kind,
                target_id=target_id,
                payload=payload,
                timeout_ms=timeout_ms,
            ),
        )
    except BrowserValidationError as exc:
        raise _augment_browser_error_with_guidance(
            container=container,
            profile_name=profile_name,
            exc=exc,
        ) from exc
    return serializer.serialize(result), profile_name


def _execute_page_action(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    tool_id: str,
    kind: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    content, profile_name = _run_page_action_content(
        container=container,
        facade=facade,
        serializer=serializer,
        system_config_store=system_config_store,
        settings=settings,
        kind=kind,
        arguments=arguments,
    )
    return _tool_result(
        container=container,
        tool_id=tool_id,
        content=content,
        family="page-action",
        profile_name=profile_name,
        kind=kind,
        execution_context=execution_context,
    )


def _run_page_action_content(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    kind: str,
    arguments: dict[str, Any],
) -> tuple[Any, str]:
    _ensure_browser_enabled(settings)
    profile_name = _resolve_profile_name(arguments, system_config_store)
    target_id = _normalize_browser_target_id(arguments.get("target_id"))
    ref = _normalize_text(arguments.get("ref"))
    selector = _normalize_text(arguments.get("selector"))
    timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    payload = _coerce_payload(arguments.get("payload"))
    try:
        result = facade.execute(
            BrowserPageActionRequest(
                profile_name=profile_name,
                kind=kind,
                target_id=target_id,
                ref=ref,
                selector=selector,
                payload=payload,
                timeout_ms=timeout_ms,
            ),
        )
    except BrowserValidationError as exc:
        raise _augment_browser_error_with_guidance(
            container=container,
            profile_name=profile_name,
            exc=exc,
        ) from exc
    return serializer.serialize(result), profile_name


def _coerce_script_steps(value: object) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise BrowserValidationError(
                "browser script steps must be a JSON array or an array of step objects.",
            ) from exc
    if not isinstance(value, list):
        raise BrowserValidationError(
            "browser script steps must be a list of step objects.",
        )
    normalized: list[dict[str, Any]] = []
    for raw_step in value:
        if isinstance(raw_step, str):
            try:
                raw_step = json.loads(raw_step)
            except ValueError as exc:
                raise BrowserValidationError(
                    "browser script steps must be objects. Do not wrap each step in a JSON string.",
                ) from exc
        if not isinstance(raw_step, dict):
            raise BrowserValidationError(
                "browser script steps must be objects. Do not wrap each step in a JSON string.",
            )
        normalized.append(dict(raw_step))
    if not normalized:
        raise BrowserValidationError("browser script requires at least one step.")
    return normalized


def _script_step_target_id(
    *,
    family: str,
    kind: str,
    step_arguments: dict[str, Any],
    current_target_id: str | None,
) -> dict[str, Any]:
    explicit_target_id = _normalize_text(step_arguments.get("target_id"))
    if explicit_target_id is not None:
        normalized = dict(step_arguments)
        resolved_target_id = _normalize_browser_target_id(
            explicit_target_id,
            current_target_id=current_target_id,
        )
        if resolved_target_id is None:
            normalized.pop("target_id", None)
        else:
            normalized["target_id"] = resolved_target_id
        return normalized
    if current_target_id is None:
        return step_arguments
    if family == "page-action" or kind in _SCRIPT_INHERITED_TARGET_CONTROL_KINDS:
        normalized = dict(step_arguments)
        normalized["target_id"] = current_target_id
        return normalized
    return step_arguments


def _script_step_defaults(
    *,
    step_arguments: dict[str, Any],
    profile_name: str | None,
    timeout_ms: int | None,
) -> dict[str, Any]:
    normalized = dict(step_arguments)
    if profile_name is not None and _normalize_text(normalized.get("profile")) is None:
        normalized["profile"] = profile_name
    if timeout_ms is not None and normalized.get("timeout_ms") in (None, ""):
        normalized["timeout_ms"] = timeout_ms
    return normalized


def _normalize_snapshot_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    snapshot_format = _normalize_text(arguments.get("format"))
    if snapshot_format is not None:
        payload.setdefault("format", snapshot_format)
    refs_mode = _normalize_text(arguments.get("refs_mode"))
    if refs_mode is not None:
        payload.setdefault("refs_mode", refs_mode.lower())
    snapshot_mode = _normalize_text(arguments.get("mode"))
    if snapshot_mode is not None:
        payload.setdefault("mode", snapshot_mode.lower())
    compact = _normalize_bool(arguments.get("compact"), label="compact")
    if compact is not None:
        payload.setdefault("compact", compact)
    depth = _normalize_int(arguments.get("depth"), label="depth", minimum=0)
    if depth is not None:
        payload.setdefault("depth", depth)
    frame_selector = _normalize_text(arguments.get("frame_selector"))
    if frame_selector is not None:
        payload.setdefault("frame_selector", frame_selector)
    overlay_source_ref = _normalize_text(arguments.get("overlay_source_ref"))
    if overlay_source_ref is not None:
        payload.setdefault("overlay_source_ref", overlay_source_ref)
    overlay_source_selector = _normalize_text(arguments.get("overlay_source_selector"))
    if overlay_source_selector is not None:
        payload.setdefault("overlay_source_selector", overlay_source_selector)
    active_overlay = _normalize_bool(arguments.get("active_overlay"), label="active_overlay")
    if active_overlay is not None:
        payload.setdefault("active_overlay", active_overlay)
    limit = _normalize_int(arguments.get("limit"), label="limit", minimum=1)
    if limit is not None:
        payload.setdefault("limit", limit)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_click_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    scope_ref = _normalize_text(arguments.get("scope_ref"))
    if scope_ref is not None:
        payload.setdefault("scope_ref", scope_ref)
    scope_selector = _normalize_text(arguments.get("scope_selector"))
    if scope_selector is not None:
        payload.setdefault("scope_selector", scope_selector)
    ordinal = _normalize_int(arguments.get("ordinal"), label="ordinal", minimum=0)
    if ordinal is not None:
        payload.setdefault("ordinal", ordinal)
    double_click = _normalize_bool(arguments.get("double_click"), label="double_click")
    if double_click is not None:
        payload.setdefault("double_click", double_click)
    button = _normalize_text(arguments.get("button"))
    if button is not None:
        payload.setdefault("button", button)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_fill_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    fields = arguments.get("fields")
    if isinstance(fields, list):
        payload.setdefault("fields", list(fields))
    scope_ref = _normalize_text(arguments.get("scope_ref"))
    if scope_ref is not None:
        payload.setdefault("scope_ref", scope_ref)
    scope_selector = _normalize_text(arguments.get("scope_selector"))
    if scope_selector is not None:
        payload.setdefault("scope_selector", scope_selector)
    ordinal = _normalize_int(arguments.get("ordinal"), label="ordinal", minimum=0)
    if ordinal is not None:
        payload.setdefault("ordinal", ordinal)
    text = _normalize_text(arguments.get("text"))
    if text is not None:
        payload.setdefault("text", text)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_download_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    scope_ref = _normalize_text(arguments.get("scope_ref"))
    if scope_ref is not None:
        payload.setdefault("scope_ref", scope_ref)
    scope_selector = _normalize_text(arguments.get("scope_selector"))
    if scope_selector is not None:
        payload.setdefault("scope_selector", scope_selector)
    ordinal = _normalize_int(arguments.get("ordinal"), label="ordinal", minimum=0)
    if ordinal is not None:
        payload.setdefault("ordinal", ordinal)
    double_click = _normalize_bool(arguments.get("double_click"), label="double_click")
    if double_click is not None:
        payload.setdefault("double_click", double_click)
    button = _normalize_text(arguments.get("button"))
    if button is not None:
        payload.setdefault("button", button)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_wait_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    scope_ref = _normalize_text(arguments.get("scope_ref"))
    if scope_ref is not None:
        payload.setdefault("scope_ref", scope_ref)
    scope_selector = _normalize_text(arguments.get("scope_selector"))
    if scope_selector is not None:
        payload.setdefault("scope_selector", scope_selector)
    exact = _normalize_bool(arguments.get("exact"), label="exact")
    if exact is not None:
        payload.setdefault("exact", exact)
    ordinal = _normalize_int(arguments.get("ordinal"), label="ordinal", minimum=0)
    if ordinal is not None:
        payload.setdefault("ordinal", ordinal)
    text = _normalize_text(arguments.get("text"))
    if text is not None:
        payload.setdefault("text", text)
    text_gone = _normalize_text(arguments.get("text_gone"))
    if text_gone is not None:
        payload.setdefault("text_gone", text_gone)
    overlay_source_ref = _normalize_text(arguments.get("overlay_source_ref"))
    if overlay_source_ref is not None:
        payload.setdefault("overlay_source_ref", overlay_source_ref)
    overlay_source_selector = _normalize_text(arguments.get("overlay_source_selector"))
    if overlay_source_selector is not None:
        payload.setdefault("overlay_source_selector", overlay_source_selector)
    url = _normalize_text(arguments.get("url"))
    if url is not None:
        payload.setdefault("url", url)
    load_state = _normalize_text(arguments.get("load_state"))
    if load_state is not None:
        payload.setdefault("load_state", load_state)
    fn = _normalize_text(arguments.get("fn"))
    if fn is not None:
        payload.setdefault("fn", fn)
    expression = _normalize_text(arguments.get("expression"))
    if expression is not None:
        payload.setdefault("expression", expression)
    state = _normalize_text(arguments.get("state"))
    if state is not None:
        payload.setdefault("state", state)
    delay_ms = _normalize_int(arguments.get("delay_ms"), label="delay_ms", minimum=0)
    if delay_ms is not None:
        payload.setdefault("delay_ms", delay_ms)
    time_ms = _normalize_int(arguments.get("time_ms"), label="time_ms", minimum=0)
    if time_ms is not None:
        payload.setdefault("time_ms", time_ms)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_advanced_action_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    text = _normalize_text(arguments.get("text"))
    if text is not None:
        payload.setdefault("text", text)
    delay_ms = _normalize_int(arguments.get("delay_ms"), label="delay_ms", minimum=0)
    if delay_ms is not None:
        payload.setdefault("delay_ms", delay_ms)
    key = _normalize_text(arguments.get("key"))
    if key is not None:
        payload.setdefault("key", key)
    start_ref = _normalize_text(arguments.get("start_ref"))
    if start_ref is not None:
        payload.setdefault("start_ref", start_ref)
    start_selector = _normalize_text(arguments.get("start_selector"))
    if start_selector is not None:
        payload.setdefault("start_selector", start_selector)
    end_ref = _normalize_text(arguments.get("end_ref"))
    if end_ref is not None:
        payload.setdefault("end_ref", end_ref)
    end_selector = _normalize_text(arguments.get("end_selector"))
    if end_selector is not None:
        payload.setdefault("end_selector", end_selector)
    target_ref = _normalize_text(arguments.get("target_ref"))
    if target_ref is not None:
        payload.setdefault("target_ref", target_ref)
    target_selector = _normalize_text(arguments.get("target_selector"))
    if target_selector is not None:
        payload.setdefault("target_selector", target_selector)
    value = _normalize_text(arguments.get("value"))
    if value is not None:
        payload.setdefault("value", value)
    width = _normalize_int(arguments.get("width"), label="width", minimum=1)
    if width is not None:
        payload.setdefault("width", width)
    height = _normalize_int(arguments.get("height"), label="height", minimum=1)
    if height is not None:
        payload.setdefault("height", height)
    actions = arguments.get("actions")
    if isinstance(actions, list):
        payload.setdefault("actions", list(actions))
    stop_on_error = _normalize_bool(arguments.get("stop_on_error"), label="stop_on_error")
    if stop_on_error is None:
        stop_on_error = _normalize_bool(arguments.get("stopOnError"), label="stopOnError")
    if stop_on_error is not None:
        payload.setdefault("stop_on_error", stop_on_error)
    scope_ref = _normalize_text(arguments.get("scope_ref"))
    if scope_ref is not None:
        payload.setdefault("scope_ref", scope_ref)
    scope_selector = _normalize_text(arguments.get("scope_selector"))
    if scope_selector is not None:
        payload.setdefault("scope_selector", scope_selector)
    exact = _normalize_bool(arguments.get("exact"), label="exact")
    if exact is not None:
        payload.setdefault("exact", exact)
    clear_existing = _normalize_bool(arguments.get("clear_existing"), label="clear_existing")
    if clear_existing is not None:
        payload.setdefault("clear_existing", clear_existing)
    ordinal = _normalize_int(arguments.get("ordinal"), label="ordinal", minimum=0)
    if ordinal is not None:
        payload.setdefault("ordinal", ordinal)
    image_type = _normalize_text(arguments.get("type"))
    if image_type is not None:
        payload.setdefault("type", image_type)
    full_page = _normalize_bool(arguments.get("full_page"), label="full_page")
    if full_page is not None:
        payload.setdefault("full_page", full_page)
    print_background = _normalize_bool(arguments.get("print_background"), label="print_background")
    if print_background is not None:
        payload.setdefault("print_background", print_background)
    expression = _normalize_text(arguments.get("expression"))
    if expression is not None:
        payload.setdefault("expression", expression)
    fn = _normalize_text(arguments.get("fn"))
    if fn is not None:
        payload.setdefault("fn", fn)
    if "arg" in arguments and arguments.get("arg") is not None:
        payload.setdefault("arg", arguments.get("arg"))
    path = _normalize_text(arguments.get("path"))
    if path is not None:
        payload.setdefault("path", path)
    accept = _normalize_bool(arguments.get("accept"), label="accept")
    if accept is not None:
        payload.setdefault("accept", accept)
    prompt_text = _normalize_text(arguments.get("prompt_text"))
    if prompt_text is None:
        prompt_text = _normalize_text(arguments.get("promptText"))
    if prompt_text is not None:
        payload.setdefault("prompt_text", prompt_text)
    level = _normalize_text(arguments.get("level"))
    if level is not None:
        payload.setdefault("level", level)
    clear = _normalize_bool(arguments.get("clear"), label="clear")
    if clear is not None:
        payload.setdefault("clear", clear)
    limit = _normalize_int(arguments.get("limit"), label="limit", minimum=1)
    if limit is not None:
        payload.setdefault("limit", limit)
    cookies_operation = _normalize_text(arguments.get("cookies_operation"))
    if cookies_operation is None:
        cookies_operation = _normalize_text(arguments.get("operation"))
    if cookies_operation is not None:
        payload.setdefault("cookies_operation", cookies_operation)
    if "cookie" in arguments and arguments.get("cookie") is not None:
        payload.setdefault("cookie", arguments.get("cookie"))
    storage_kind = _normalize_text(arguments.get("storage_kind"))
    if storage_kind is None:
        storage_kind = _normalize_text(arguments.get("storage"))
    if storage_kind is not None:
        payload.setdefault("storage_kind", storage_kind)
    storage_operation = _normalize_text(arguments.get("storage_operation"))
    if storage_operation is None:
        storage_operation = _normalize_text(arguments.get("operation"))
    if storage_operation is not None:
        payload.setdefault("storage_operation", storage_operation)
    storage_key = _normalize_text(arguments.get("storage_key"))
    if storage_key is None:
        storage_key = _normalize_text(arguments.get("key"))
    if storage_key is not None:
        payload.setdefault("storage_key", storage_key)
    if "storage_value" in arguments and arguments.get("storage_value") is not None:
        payload.setdefault("storage_value", arguments.get("storage_value"))
    paths = arguments.get("paths")
    if isinstance(paths, list):
        normalized_paths = [candidate for candidate in (_normalize_text(item) for item in paths) if candidate is not None]
        if normalized_paths:
            payload.setdefault("paths", normalized_paths)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_script_step_arguments(
    *,
    family: str,
    kind: str,
    step_arguments: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(step_arguments)
    if family == "control":
        return normalized
    if kind == "snapshot":
        return _normalize_snapshot_arguments(normalized)
    if kind == "click":
        return _normalize_click_arguments(normalized)
    if kind == "fill":
        return _normalize_fill_arguments(normalized)
    if kind == "download":
        return _normalize_download_arguments(normalized)
    if kind == "wait":
        return _normalize_wait_arguments(normalized)
    if kind in _ADVANCED_PAGE_ACTION_KINDS:
        return _normalize_advanced_action_arguments(normalized)
    return normalized


def _normalize_script_stabilize(value: object, *, label: str) -> str | None:
    if value in (None, ""):
        return None
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized not in _SCRIPT_STABILIZE_KINDS:
        raise BrowserValidationError(
            f"{label} must be one of auto, navigation, micro, overlay, or none.",
        )
    return normalized


def _normalize_script_observe_after(value: object, *, label: str) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return "interactive" if value else "none"
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized in {"true", "yes", "on", "1"}:
        return "interactive"
    if normalized in {"false", "no", "off", "0"}:
        return "none"
    if normalized not in _SCRIPT_OBSERVE_AFTER_KINDS:
        raise BrowserValidationError(
            f"{label} must be one of auto, interactive, role, aria, or none.",
        )
    return normalized


def _coerce_script_observe_payload(value: object, *, label: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise BrowserValidationError(f"{label} must decode to an object.")
    return dict(value)


def _resolve_script_stabilize_mode(
    *,
    family: str,
    kind: str,
    raw_mode: str | None,
) -> str:
    mode = raw_mode or "none"
    if mode != "auto":
        return mode
    if family == "control":
        if kind in {"open-tab", "navigate"}:
            return "navigation"
        return "none"
    if kind == "wait":
        return "none"
    if kind in {"click", "press", "select", "fill", "type"}:
        return "micro"
    return "none"


def _resolve_script_observe_mode(raw_mode: str | None) -> str:
    mode = raw_mode or "none"
    if mode == "auto":
        return "interactive"
    return mode


def _default_observe_payload_for_mode(mode: str) -> dict[str, Any]:
    if mode == "interactive":
        return {
            "format": "interactive",
            "mode": "focused",
        }
    if mode in {"role", "aria"}:
        return {"format": mode}
    return {}


def _run_script_stabilize(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    profile_name: str,
    target_id: str | None,
    stabilize_mode: str,
    stabilize_timeout_ms: int | None,
) -> Any | None:
    if target_id is None or stabilize_mode == "none":
        return None
    wait_payload: dict[str, Any]
    if stabilize_mode == "navigation":
        wait_payload = {"load_state": "load"}
    elif stabilize_mode == "overlay":
        wait_payload = {"time_ms": _SCRIPT_OVERLAY_STABILIZE_MS}
    else:
        wait_payload = {"time_ms": _SCRIPT_MICRO_STABILIZE_MS}
    result, _ = _run_page_action_content(
        container=container,
        facade=facade,
        serializer=serializer,
        system_config_store=system_config_store,
        settings=settings,
        kind="wait",
        arguments={
            "profile": profile_name,
            "target_id": target_id,
            "timeout_ms": stabilize_timeout_ms,
            "payload": wait_payload,
        },
    )
    return result


def _run_script_observe_after(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    profile_name: str,
    target_id: str | None,
    observe_mode: str,
    observe_payload: dict[str, Any],
    timeout_ms: int | None,
) -> Any | None:
    if target_id is None or observe_mode == "none":
        return None
    payload = dict(observe_payload)
    if not payload:
        payload = _default_observe_payload_for_mode(observe_mode)
    else:
        payload.setdefault("format", observe_mode)
        if observe_mode == "interactive":
            payload.setdefault("mode", "focused")
    result, _ = _run_page_action_content(
        container=container,
        facade=facade,
        serializer=serializer,
        system_config_store=system_config_store,
        settings=settings,
        kind="snapshot",
        arguments={
            "profile": profile_name,
            "target_id": target_id,
            "timeout_ms": timeout_ms,
            "payload": payload,
        },
    )
    return result


def _merge_tool_result_post_state(
    *,
    container: Any,
    result: ToolRunResult,
    post_state_result: Any,
) -> ToolRunResult:
    post_state_blocks = _browser_content_blocks(container, post_state_result)
    if not post_state_blocks:
        return result
    metadata = dict(result.metadata)
    metadata["post_state_summary"] = _browser_result_summary(post_state_result)
    return ToolRunResult.structured(
        content=[*result.blocks, *[dict(block) for block in post_state_blocks]],
        details=result.details,
        metadata=metadata,
    )


def _single_step_script_defaults(*, family: str, kind: str) -> dict[str, Any]:
    return {}


def _strip_single_step_composite_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments)
    normalized.pop("stabilize", None)
    normalized.pop("stabilize_timeout_ms", None)
    normalized.pop("observe_after", None)
    normalized.pop("observe_payload", None)
    return normalized


def _single_step_script_overrides(arguments: dict[str, Any]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    stabilize = _normalize_script_stabilize(arguments.get("stabilize"), label="stabilize")
    if stabilize is not None:
        overrides["default_stabilize"] = stabilize
    stabilize_timeout_ms = _normalize_int(
        arguments.get("stabilize_timeout_ms"),
        label="stabilize_timeout_ms",
        minimum=1,
    )
    if stabilize_timeout_ms is not None:
        overrides["default_stabilize_timeout_ms"] = stabilize_timeout_ms
    observe_after = _normalize_script_observe_after(
        arguments.get("observe_after"),
        label="observe_after",
    )
    if observe_after is not None:
        overrides["default_observe_after"] = observe_after
    observe_payload = _coerce_script_observe_payload(
        arguments.get("observe_payload"),
        label="observe_payload",
    )
    if observe_payload:
        overrides["default_observe_payload"] = observe_payload
    return overrides


def _single_step_script_arguments(
    *,
    family: str,
    kind: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    step_arguments = _strip_single_step_composite_arguments(arguments)
    return {
        **_single_step_script_defaults(
            family=family,
            kind=kind,
        ),
        **_single_step_script_overrides(arguments),
        "steps": [
            {
                **step_arguments,
                "family": family,
                "kind": kind,
            }
        ],
    }


def _extract_browser_target_id(content: Any) -> str | None:
    if not isinstance(content, dict):
        return None
    direct = _normalize_text(content.get("target_id"))
    if direct is not None:
        return direct
    tab = content.get("tab")
    if isinstance(tab, dict):
        target_id = _normalize_text(tab.get("target_id"))
        if target_id is not None:
            return target_id
    value = content.get("value")
    if isinstance(value, dict):
        target_id = _normalize_text(value.get("target_id"))
        if target_id is not None:
            return target_id
    return None


def _browser_script_blocks(container: Any, content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, dict):
        return []
    if content.get("kind") != "script":
        return []
    blocks: list[dict[str, Any]] = []
    summary = _normalize_text(content.get("message"))
    if summary is not None:
        blocks.append(text_content_block(summary))
    post_state = content.get("post_state")
    if post_state is not None:
        blocks.extend(_browser_content_blocks(container, post_state))
    return blocks


def _script_result(
    *,
    container: Any,
    tool_id: str,
    profile_name: str | None,
    execution_context: ToolExecutionContext | None,
    step_results: list[dict[str, Any]],
    post_state_result: Any | None,
    current_target_id: str | None,
) -> ToolRunResult:
    message = f"Browser script completed {len(step_results)} step"
    if len(step_results) != 1:
        message += "s"
    message += "."
    content: dict[str, Any] = {
        "kind": "script",
        "message": message,
        "steps": [
            {
                "index": item["index"],
                "family": item["family"],
                "kind": item["kind"],
                "summary": item["summary"],
                "target_id": item["target_id"],
                "stabilize": item.get("stabilize"),
                "stabilize_summary": item.get("stabilize_summary"),
                "observe_after": item.get("observe_after"),
                "post_state_summary": item.get("post_state_summary"),
            }
            for item in step_results
        ],
    }
    if post_state_result is not None:
        content["post_state"] = post_state_result
    details: dict[str, Any] = {
        "ok": True,
        "step_count": len(step_results),
        "target_id": current_target_id,
        "steps": content["steps"],
    }
    if post_state_result is not None:
        details["post_state_summary"] = _browser_result_summary(post_state_result)
    blocks = _browser_script_blocks(container, content)
    return ToolRunResult.structured(
        content=blocks,
        details=details,
        metadata={
            "tool": tool_id,
            "family": "script",
            "profile_name": profile_name,
            "kind": "script",
            "execution_context": (
                execution_context.to_payload()
                if execution_context is not None
                else None
            ),
        },
    )


def _execute_script(
    *,
    container: Any,
    facade: Any,
    serializer: Any,
    system_config_store: Any,
    settings: Any,
    tool_id: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
    preserve_single_step_result: bool = False,
) -> ToolRunResult:
    _ensure_browser_enabled(settings)
    steps = _coerce_script_steps(arguments.get("steps"))
    current_target_id = _normalize_browser_target_id(arguments.get("target_id"))
    inherited_profile_name = _normalize_text(arguments.get("profile"))
    inherited_timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    stop_on_error = _normalize_bool(arguments.get("stop_on_error"), label="stop_on_error")
    stop_on_error = True if stop_on_error is None else stop_on_error
    default_stabilize = _normalize_script_stabilize(
        arguments.get("default_stabilize"),
        label="default_stabilize",
    )
    default_stabilize_timeout_ms = _normalize_int(
        arguments.get("default_stabilize_timeout_ms"),
        label="default_stabilize_timeout_ms",
        minimum=1,
    )
    default_observe_after = _normalize_script_observe_after(
        arguments.get("default_observe_after"),
        label="default_observe_after",
    )
    default_observe_payload = _coerce_script_observe_payload(
        arguments.get("default_observe_payload"),
        label="default_observe_payload",
    )
    final_observe = _coerce_payload(arguments.get("final_observe"))
    final_observe_enabled = bool(final_observe)
    step_results: list[dict[str, Any]] = []
    profile_name: str | None = None
    last_single_step_result: ToolRunResult | None = None
    last_post_state_result: Any | None = None
    suppress_default_step_observe_for_final_open = (
        final_observe_enabled and len(steps) == 1
    )

    for index, raw_step in enumerate(steps, start=1):
        kind = _normalize_text(raw_step.get("kind"))
        if kind is None:
            raise BrowserValidationError("browser script step kind is required.")
        family = _resolve_family(kind.lower(), _normalize_text(raw_step.get("family")))
        normalized_kind = kind.lower()
        step_arguments = dict(raw_step)
        step_arguments = _script_step_defaults(
            step_arguments=step_arguments,
            profile_name=inherited_profile_name,
            timeout_ms=inherited_timeout_ms,
        )
        step_arguments = _normalize_script_step_arguments(
            family=family,
            kind=normalized_kind,
            step_arguments=step_arguments,
        )
        step_arguments = _script_step_target_id(
            family=family,
            kind=normalized_kind,
            step_arguments=step_arguments,
            current_target_id=current_target_id,
        )
        step_stabilize = _normalize_script_stabilize(
            raw_step.get("stabilize"),
            label=f"steps[{index}].stabilize",
        )
        step_stabilize_timeout_ms = _normalize_int(
            raw_step.get("stabilize_timeout_ms"),
            label=f"steps[{index}].stabilize_timeout_ms",
            minimum=1,
        )
        step_observe_after = _normalize_script_observe_after(
            raw_step.get("observe_after"),
            label=f"steps[{index}].observe_after",
        )
        step_observe_payload = _coerce_script_observe_payload(
            raw_step.get("observe_payload"),
            label=f"steps[{index}].observe_payload",
        )
        try:
            if family == "control":
                content, resolved_profile = _run_control_content(
                    container=container,
                    facade=facade,
                    serializer=serializer,
                    system_config_store=system_config_store,
                    settings=settings,
                    kind=normalized_kind,
                    arguments=step_arguments,
                )
                result = _tool_result(
                    container=container,
                    tool_id=tool_id,
                    content=content,
                    family="control",
                    profile_name=resolved_profile,
                    kind=normalized_kind,
                    execution_context=execution_context,
                )
            else:
                content, resolved_profile = _run_page_action_content(
                    container=container,
                    facade=facade,
                    serializer=serializer,
                    system_config_store=system_config_store,
                    settings=settings,
                    kind=normalized_kind,
                    arguments=step_arguments,
                )
                result = _tool_result(
                    container=container,
                    tool_id=tool_id,
                    content=content,
                    family="page-action",
                    profile_name=resolved_profile,
                    kind=normalized_kind,
                    execution_context=execution_context,
                )
        except Exception:
            if stop_on_error:
                raise
            continue
        profile_name = resolved_profile
        current_target_id = _extract_browser_target_id(content) or current_target_id
        effective_stabilize = _resolve_script_stabilize_mode(
            family=family,
            kind=normalized_kind,
            raw_mode=step_stabilize or default_stabilize,
        )
        effective_stabilize_timeout_ms = (
            step_stabilize_timeout_ms
            or default_stabilize_timeout_ms
            or inherited_timeout_ms
        )
        stabilize_result = _run_script_stabilize(
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            profile_name=profile_name,
            target_id=current_target_id,
            stabilize_mode=effective_stabilize,
            stabilize_timeout_ms=effective_stabilize_timeout_ms,
        )
        inherited_observe_after = default_observe_after
        if family == "control" and step_observe_after is None:
            inherited_observe_after = None
        elif (
            suppress_default_step_observe_for_final_open
            and family == "control"
            and normalized_kind in _SCRIPT_FINAL_OBSERVE_CONTROL_KINDS
            and step_observe_after is None
        ):
            inherited_observe_after = None
        effective_observe_after = _resolve_script_observe_mode(
            step_observe_after or inherited_observe_after,
        )
        effective_observe_payload = (
            dict(step_observe_payload)
            if step_observe_payload
            else dict(default_observe_payload)
        )
        post_state_result = _run_script_observe_after(
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            profile_name=profile_name,
            target_id=current_target_id,
            observe_mode=effective_observe_after,
            observe_payload=effective_observe_payload,
            timeout_ms=inherited_timeout_ms,
        )
        if post_state_result is not None:
            result = _merge_tool_result_post_state(
                container=container,
                result=result,
                post_state_result=post_state_result,
            )
            last_post_state_result = post_state_result
        last_single_step_result = result
        step_results.append(
            {
                "index": index,
                "family": family,
                "kind": normalized_kind,
                "summary": _browser_result_summary(content),
                "target_id": current_target_id,
                "stabilize": effective_stabilize,
                "stabilize_summary": _browser_result_summary(stabilize_result),
                "observe_after": effective_observe_after,
                "post_state_summary": _browser_result_summary(post_state_result),
            }
        )

    if not step_results:
        raise BrowserValidationError("browser script completed without any successful steps.")
    if preserve_single_step_result and len(step_results) == 1 and not final_observe_enabled:
        assert last_single_step_result is not None
        return last_single_step_result

    post_state_result = last_post_state_result
    if final_observe_enabled:
        if current_target_id is None:
            raise BrowserValidationError(
                "browser script final_observe requires a target_id or a prior step that resolves one.",
            )
        observe_arguments: dict[str, Any] = {
            "profile": profile_name,
            "target_id": current_target_id,
            "payload": dict(final_observe),
        }
        final_observe_result, _ = _run_page_action_content(
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            kind="snapshot",
            arguments=observe_arguments,
        )
        post_state_result = final_observe_result

    return _script_result(
        container=container,
        tool_id=tool_id,
        profile_name=profile_name,
        execution_context=execution_context,
        step_results=step_results,
        post_state_result=post_state_result,
        current_target_id=current_target_id,
    )

def browser_profile(container: Any):
    try:
        _, _, _, settings, _ = _profile_listing_runtime(container)
    except RuntimeError:
        return None

    async def _browser_profile_handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        _ensure_browser_enabled(settings)
        kind = (_normalize_text(arguments.get("kind")) or "list").lower()
        if kind == "list":
            payload = await asyncio.to_thread(_profiles_payload, container)
            guidance = _profiles_guidance(payload)
            payload = {
                **payload,
                "guidance": guidance,
            }
            return _tool_result(
                container=container,
                tool_id="browser_profile",
                content=payload,
                family=None,
                profile_name=None,
                kind="list",
                execution_context=execution_context,
                guidance=guidance,
            )
        if kind == "diagnose":
            profile_name = _normalize_text(arguments.get("profile")) or _normalize_text(
                arguments.get("profile_name"),
            )
            if profile_name is None:
                raise BrowserValidationError("profile is required for browser_profile kind=diagnose.")
            payload = await asyncio.to_thread(
                build_profile_diagnostics_payload,
                container,
                profile_name=profile_name,
            )
            guidance = _profile_diagnostics_guidance(
                payload,
                system_config_store=container.browser_system_config_store,
            )
            payload = {
                **payload,
                "guidance": guidance,
            }
            return _tool_result(
                container=container,
                tool_id="browser_profile",
                content=payload,
                family=None,
                profile_name=profile_name,
                kind="diagnose",
                execution_context=execution_context,
                guidance=guidance,
            )
        raise BrowserValidationError("browser_profile.kind must be either list or diagnose.")

    return _browser_profile_handler

def browser_control(container: Any):
    try:
        facade, serializer, system_config_store, settings = _browser_runtime(container)
    except RuntimeError:
        return None

    async def _browser_control_handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        kind = _normalize_text(arguments.get("kind"))
        if kind is None or kind.lower() not in _CONTROL_KINDS:
            raise BrowserValidationError(
                "browser_control.kind must be one of status, start, stop, open-tab, list-tabs, navigate, focus-tab, close-tab, reset.",
            )
        return await asyncio.to_thread(
            _execute_script,
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            tool_id="browser_control",
            arguments=_single_step_script_arguments(
                family="control",
                kind=kind.lower(),
                arguments=arguments,
            ),
            execution_context=execution_context,
            preserve_single_step_result=True,
        )

    return _browser_control_handler


def browser_snapshot(container: Any):
    try:
        facade, serializer, system_config_store, settings = _browser_runtime(container)
    except RuntimeError:
        return None

    async def _browser_snapshot_handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        normalized_arguments = dict(arguments)
        payload = _coerce_payload(arguments.get("payload"))
        snapshot_format = _normalize_text(arguments.get("format"))
        if snapshot_format is not None:
            payload.setdefault("format", snapshot_format)
        refs_mode = _normalize_text(arguments.get("refs_mode"))
        if refs_mode is not None:
            payload.setdefault("refs_mode", refs_mode.lower())
        snapshot_mode = _normalize_text(arguments.get("mode"))
        if snapshot_mode is not None:
            payload.setdefault("mode", snapshot_mode.lower())
        compact = _normalize_bool(arguments.get("compact"), label="compact")
        if compact is not None:
            payload.setdefault("compact", compact)
        depth = _normalize_int(arguments.get("depth"), label="depth", minimum=0)
        if depth is not None:
            payload.setdefault("depth", depth)
        frame_selector = _normalize_text(arguments.get("frame_selector"))
        if frame_selector is not None:
            payload.setdefault("frame_selector", frame_selector)
        overlay_source_ref = _normalize_text(arguments.get("overlay_source_ref"))
        if overlay_source_ref is not None:
            payload.setdefault("overlay_source_ref", overlay_source_ref)
        overlay_source_selector = _normalize_text(arguments.get("overlay_source_selector"))
        if overlay_source_selector is not None:
            payload.setdefault("overlay_source_selector", overlay_source_selector)
        active_overlay = _normalize_bool(arguments.get("active_overlay"), label="active_overlay")
        if active_overlay is not None:
            payload.setdefault("active_overlay", active_overlay)
        limit = _normalize_int(arguments.get("limit"), label="limit", minimum=1)
        if limit is not None:
            payload.setdefault("limit", limit)
        normalized_arguments["payload"] = payload
        return await asyncio.to_thread(
            _execute_script,
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            tool_id="browser_snapshot",
            arguments={
                "steps": [
                    {
                        **normalized_arguments,
                        "family": "page-action",
                        "kind": "snapshot",
                    }
                ]
            },
            execution_context=execution_context,
            preserve_single_step_result=True,
        )

    return _browser_snapshot_handler

def browser_action(container: Any):
    try:
        facade, serializer, system_config_store, settings = _browser_runtime(container)
    except RuntimeError:
        return None

    async def _browser_action_handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        kind = _normalize_text(arguments.get("kind"))
        if kind is None or kind.lower() not in _ACTION_TOOL_PAGE_ACTION_KINDS:
            raise BrowserValidationError(
                "browser_action.kind must be one of click, console, cookies, dialog, fill, upload, download, wait-download, wait, batch, type, press, hover, drag, resize, scroll-into-view, select, screenshot, pdf, evaluate, or storage.",
            )
        normalized_arguments = _normalize_script_step_arguments(
            family="page-action",
            kind=kind.lower(),
            step_arguments=dict(arguments),
        )
        return await asyncio.to_thread(
            _execute_script,
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            tool_id="browser_action",
            arguments=_single_step_script_arguments(
                family="page-action",
                kind=kind.lower(),
                arguments=normalized_arguments,
            ),
            execution_context=execution_context,
            preserve_single_step_result=True,
        )

    return _browser_action_handler


def browser_script(container: Any):
    try:
        facade, serializer, system_config_store, settings = _browser_runtime(container)
    except RuntimeError:
        return None

    async def _browser_script_handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        normalized_arguments = dict(arguments)
        if "steps" not in normalized_arguments:
            normalized_arguments["steps"] = arguments.get("steps")
        final_observe = _coerce_payload(arguments.get("final_observe"))
        if not final_observe:
            observe_after = _normalize_bool(arguments.get("observe_after"), label="observe_after")
            if observe_after:
                final_observe = {
                    "format": "interactive",
                    "mode": "focused",
                }
        if final_observe:
            normalized_arguments["final_observe"] = final_observe
        return await asyncio.to_thread(
            _execute_script,
            container=container,
            facade=facade,
            serializer=serializer,
            system_config_store=system_config_store,
            settings=settings,
            tool_id="browser_script",
            arguments=normalized_arguments,
            execution_context=execution_context,
        )

    return _browser_script_handler
