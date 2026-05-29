from __future__ import annotations

import asyncio
import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any, Mapping, get_args
from urllib.parse import urlsplit, urlunsplit

from crxzipple.modules.browser.domain import (
    BrowserControlKind,
    BrowserPageActionKind,
    BrowserValidationError,
)
from crxzipple.modules.browser.application import (
    BrowserToolApplicationError,
    BrowserToolExecutionError,
)
from crxzipple.modules.browser.interfaces.profile_payloads import build_profile_diagnostics_payload
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult
from crxzipple.shared.content_blocks import (
    file_ref_content_block,
    image_ref_content_block,
    text_content_block,
)

_CONTROL_KINDS = frozenset(get_args(BrowserControlKind))
_PAGE_ACTION_KINDS = frozenset(get_args(BrowserPageActionKind))
_NETWORK_PAGE_ACTION_KINDS = frozenset(
    {
        "network-start-capture",
        "network-stop-capture",
        "network-list-requests",
        "network-get-request",
        "network-get-response-body",
        "network-get-request-body",
        "network-fetch-as-page",
        "network-replay-request",
        "network-clear-capture",
    }
)
_DEEP_STORAGE_PAGE_ACTION_KINDS = frozenset(
    {
        "storage-indexeddb-list",
        "storage-indexeddb-get",
        "storage-indexeddb-query",
        "storage-cache-list",
        "storage-cache-get",
        "service-worker-list",
        "service-worker-inspect",
    }
)
_DOM_PAGE_ACTION_KINDS = frozenset(
    {
        "dom-inspect",
        "dom-box-model",
        "dom-computed-style",
        "dom-clickability",
        "dom-highlight",
        "dom-mutation-wait",
    }
)
_ENVIRONMENT_PAGE_ACTION_KINDS = frozenset(
    {
        "emulation-set",
        "emulation-reset",
        "permissions-grant",
        "permissions-clear",
        "geolocation-set",
        "network-conditions-set",
    }
)
_DIAGNOSTIC_PAGE_ACTION_KINDS = frozenset(
    {
        "diagnostics-collect",
        "performance-metrics",
        "trace-start",
        "trace-stop",
        "trace-export",
        "page-lifecycle",
        "page-errors",
    }
)
_LOCAL_PAGE_ACTION_KINDS = (
    (_PAGE_ACTION_KINDS - {"cdp-raw"})
    | _NETWORK_PAGE_ACTION_KINDS
    | _DEEP_STORAGE_PAGE_ACTION_KINDS
    | _DOM_PAGE_ACTION_KINDS
    | _ENVIRONMENT_PAGE_ACTION_KINDS
    | _DIAGNOSTIC_PAGE_ACTION_KINDS
)
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
        "storage-indexeddb-list",
        "storage-indexeddb-get",
        "storage-indexeddb-query",
        "storage-cache-list",
        "storage-cache-get",
        "service-worker-list",
        "service-worker-inspect",
        "dom-inspect",
        "dom-box-model",
        "dom-computed-style",
        "dom-clickability",
        "dom-highlight",
        "dom-mutation-wait",
        "emulation-set",
        "emulation-reset",
        "permissions-grant",
        "permissions-clear",
        "geolocation-set",
        "network-conditions-set",
        "diagnostics-collect",
        "performance-metrics",
        "trace-start",
        "trace-stop",
        "trace-export",
        "page-lifecycle",
        "page-errors",
        "type",
        "upload",
        "download",
        "wait-download",
        "network-inspect",
    }
)
_NETWORK_TOOL_KIND_BY_TOOL_ID = {
    "browser.network.start_capture": "network-start-capture",
    "browser.network.stop_capture": "network-stop-capture",
    "browser.network.list_requests": "network-list-requests",
    "browser.network.get_request": "network-get-request",
    "browser.network.get_response_body": "network-get-response-body",
    "browser.network.get_request_body": "network-get-request-body",
    "browser.network.fetch_as_page": "network-fetch-as-page",
    "browser.network.replay_request": "network-replay-request",
    "browser.network.clear_capture": "network-clear-capture",
}
_DOM_TOOL_KIND_BY_TOOL_ID = {
    "browser.dom.inspect": "dom-inspect",
    "browser.dom.box_model": "dom-box-model",
    "browser.dom.computed_style": "dom-computed-style",
    "browser.dom.clickability": "dom-clickability",
    "browser.dom.highlight": "dom-highlight",
    "browser.dom.mutation_wait": "dom-mutation-wait",
}
_DEEP_STORAGE_TOOL_KIND_BY_TOOL_ID = {
    "browser.storage.indexeddb.list": "storage-indexeddb-list",
    "browser.storage.indexeddb.get": "storage-indexeddb-get",
    "browser.storage.indexeddb.query": "storage-indexeddb-query",
    "browser.storage.cache.list": "storage-cache-list",
    "browser.storage.cache.get": "storage-cache-get",
    "browser.service_worker.list": "service-worker-list",
    "browser.service_worker.inspect": "service-worker-inspect",
}
_ENVIRONMENT_TOOL_KIND_BY_TOOL_ID = {
    "browser.emulation.set": "emulation-set",
    "browser.emulation.reset": "emulation-reset",
    "browser.permissions.grant": "permissions-grant",
    "browser.permissions.clear": "permissions-clear",
    "browser.geolocation.set": "geolocation-set",
    "browser.network_conditions.set": "network-conditions-set",
}
_DIAGNOSTIC_TOOL_KIND_BY_TOOL_ID = {
    "browser.diagnostics.collect": "diagnostics-collect",
    "browser.performance.metrics": "performance-metrics",
    "browser.trace.start": "trace-start",
    "browser.trace.stop": "trace-stop",
    "browser.trace.export": "trace-export",
    "browser.page.lifecycle": "page-lifecycle",
    "browser.page.errors": "page-errors",
}
_NETWORK_FILTER_ARGUMENTS = frozenset(
    {
        "resource_type",
        "domain",
        "path",
        "method",
        "status",
        "initiator",
        "mime_type",
        "keyword",
    }
)
_NETWORK_TEXT_PAYLOAD_ARGUMENTS = frozenset(
    {
        "capture_id",
        "request_id",
        "body_ref",
        "encoding",
        "since",
        "until",
    }
)
_NETWORK_INT_PAYLOAD_ARGUMENTS = {
    "limit": 1,
    "max_requests": 1,
    "max_body_bytes": 1,
    "body_preview_bytes": 0,
    "status": 0,
    "timeout_ms": 1,
}
_NETWORK_BOOL_PAYLOAD_ARGUMENTS = frozenset(
    {
        "include_headers",
        "include_request_headers",
        "include_response_headers",
        "include_timing",
        "include_initiator",
        "include_body_preview",
        "redact",
        "allow_cross_origin",
        "allow_mutating",
    }
)
_NETWORK_TOP_LEVEL_BODY_PREVIEW_LIMIT = 1200
_ACTION_TOOL_PAGE_ACTION_KINDS = frozenset(
    kind for kind in _PAGE_ACTION_KINDS if kind not in {"snapshot", "network-inspect", "cdp-raw"}
)
_OPERATION_STABILIZE_KINDS = frozenset({"none", "micro", "navigation", "overlay", "auto"})
_OPERATION_OBSERVE_AFTER_KINDS = frozenset({"none", "interactive", "role", "aria", "auto"})
_OPERATION_MICRO_STABILIZE_MS = 200
_OPERATION_OVERLAY_STABILIZE_MS = 200
_OPERATION_INHERITED_TARGET_CONTROL_KINDS = frozenset({"navigate", "focus-tab", "close-tab"})
_BROWSER_INPUT_PROFILE_KEYS = ("profile", "profile_name")
_BROWSER_INPUT_PROFILE_POOL_KEYS = ("profile_pool", "profile_pool_id")
_BROWSER_CONTEXT_PROFILE_KEYS = (
    "browser_profile",
    "browser_profile_name",
    "session_browser_profile",
    "agent_default_browser_profile",
    "default_browser_profile",
    "browser_default_profile",
)
_BROWSER_CONTEXT_PROFILE_POOL_KEYS = (
    "browser_profile_pool",
    "browser_profile_pool_id",
    "default_browser_profile_pool",
)
_BROWSER_CONTEXT_ALLOCATION_KEYS = (
    "browser_allocation_id",
    "browser_profile_allocation_id",
    "browser_context_lease_id",
)
_BROWSER_INPUT_ALLOCATION_KEYS = (
    "lease_id",
    "allocation_id",
    "browser_allocation_id",
    "browser_context_lease_id",
)


@dataclass(frozen=True, slots=True)
class BrowserToolDeps:
    browser_tool_application: Any
    browser_system_config_store: Any
    browser_profile_resolver: Any
    browser_capabilities_resolver: Any
    settings: Any | None = None
    artifact_service: Any | None = None
    browser_runtime_state_store: Any | None = None
    browser_profile_probe_service: Any | None = None
    browser_profile_allocator_service: Any | None = None

    @property
    def profile_resolver(self) -> Any:
        return self.browser_profile_resolver

    @property
    def capabilities_resolver(self) -> Any:
        return self.browser_capabilities_resolver

    @property
    def runtime_state_store(self) -> Any:
        return self.browser_runtime_state_store

    @property
    def profile_probe_service(self) -> Any:
        return self.browser_profile_probe_service

    @property
    def profile_allocator_service(self) -> Any:
        return self.browser_profile_allocator_service

    def require(self, key: Any) -> Any:
        return _browser_deps_require(self, key)


@dataclass(frozen=True, slots=True)
class BrowserProfileSelection:
    name: str
    source: str


@dataclass(frozen=True, slots=True)
class BrowserResolvedProfile:
    name: str
    source: str
    allocation_metadata: dict[str, Any]


def _browser_deps_require(deps: BrowserToolDeps, key: Any) -> Any:
    key_value = getattr(key, "value", str(key))
    if key_value == "core.settings":
        if deps.settings is None:
            raise KeyError(key)
        return deps.settings
    if key_value == "browser.system_config_store":
        return deps.browser_system_config_store
    if key_value == "browser.infrastructure":
        return deps
    raise KeyError(key)

def _coerce_tool_deps(value: BrowserToolDeps | Any) -> BrowserToolDeps | None:
    if isinstance(value, BrowserToolDeps):
        return value
    return None


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


def _normalize_number(value: object, *, label: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise BrowserValidationError(f"{label} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"{label} must be a number.") from exc


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
    if kind in _LOCAL_PAGE_ACTION_KINDS:
        return "page-action"
    raise BrowserValidationError(f"Unsupported browser kind '{kind}'.")


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
    if summary_code == "browser-legacy-bridge-retired":
        guidance = {
            "recommended_profile": name,
            "next_action": str(diagnostics.get("recommended_action") or "retry-or-check-cdp"),
            "reason": "This existing-session profile now attaches through CDP; verify the browser remote debugging endpoint.",
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
    deps: BrowserToolDeps,
    tool_id: str,
    content: Any,
    family: str | None,
    profile_name: str | None,
    kind: str | None,
    execution_context: ToolExecutionContext | None,
    profile_source: str | None = None,
    runtime_metadata: Mapping[str, Any] | None = None,
    guidance: dict[str, Any] | None = None,
) -> ToolRunResult:
    content_blocks = _browser_content_blocks(deps, content)
    browser_runtime_metadata = _coerce_browser_runtime_metadata(runtime_metadata)
    browser_audit_metadata = _browser_audit_metadata(content, content_blocks)
    return ToolRunResult.structured(
        details=_browser_result_details(content),
        content=[dict(block) for block in content_blocks],
        metadata={
            "tool": tool_id,
            "family": family,
            "profile_name": profile_name,
            "profile_source": profile_source,
            **_browser_execution_context_metadata(execution_context),
            **browser_runtime_metadata,
            "kind": kind,
            "execution_context": (
                execution_context.to_payload()
                if execution_context is not None
                else None
            ),
            "guidance": dict(guidance) if isinstance(guidance, dict) else None,
            **browser_audit_metadata,
        },
    )


def _coerce_browser_runtime_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return {str(key): item for key, item in value.items() if item is not None}


def _browser_audit_metadata(
    content: Any,
    content_blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    target_url = _browser_target_url_from_content(content)
    if target_url is not None:
        metadata.update(_safe_browser_url_metadata(target_url))

    artifact_ids = _browser_artifact_ids_from_blocks(content_blocks)
    if artifact_ids:
        metadata["browser_artifact_ids"] = list(artifact_ids)
        metadata["artifact_ids"] = list(artifact_ids)
    return metadata


def _browser_artifact_ids_from_blocks(
    content_blocks: list[dict[str, Any]],
) -> tuple[str, ...]:
    artifact_ids: list[str] = []
    for block in content_blocks:
        artifact_id = _normalize_text(block.get("artifact_id"))
        if artifact_id is not None:
            artifact_ids.append(artifact_id)
    return tuple(dict.fromkeys(artifact_ids))


def _browser_target_url_from_content(content: Any) -> str | None:
    return _browser_target_url_from_content_inner(content, seen=set())


def _browser_target_url_from_content_inner(content: Any, *, seen: set[int]) -> str | None:
    if isinstance(content, dict):
        marker = id(content)
        if marker in seen:
            return None
        seen.add(marker)
        for key in ("url", "target_url", "page_url"):
            value = _normalize_text(content.get(key))
            if value is not None and _is_safe_browser_target_url(value):
                return value
        for key in (
            "value",
            "result",
            "tab",
            "page",
            "target",
            "payload",
            "performance",
        ):
            nested = content.get(key)
            if nested is None:
                continue
            resolved = _browser_target_url_from_content_inner(nested, seen=seen)
            if resolved is not None:
                return resolved
        return None
    if isinstance(content, list):
        for item in content:
            resolved = _browser_target_url_from_content_inner(item, seen=seen)
            if resolved is not None:
                return resolved
    return None


def _safe_browser_url_metadata(value: str) -> dict[str, str]:
    parsed = urlsplit(value)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    metadata = {"browser_target_origin": origin}
    sanitized_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if sanitized_url:
        metadata["browser_target_url"] = sanitized_url
    return metadata


def _is_safe_browser_target_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc or "@" in parsed.netloc:
        return False
    return True


def _browser_execution_context_metadata(
    execution_context: ToolExecutionContext | None,
) -> dict[str, Any]:
    if execution_context is None:
        return {}
    metadata: dict[str, Any] = {}
    for metadata_key, attr_keys in (
        ("browser_context_agent_id", ("agent_id",)),
        ("browser_context_session_id", ("active_session_id", "session_id", "session_key")),
        ("browser_context_run_id", ("run_id", "orchestration_run_id")),
        ("browser_context_trace_id", ("trace_id",)),
    ):
        value = _execution_context_first_str(execution_context, attr_keys)
        if value is not None:
            metadata[metadata_key] = value

    context_profile = _profile_selection_from_context(execution_context)
    if context_profile is not None:
        metadata["browser_context_profile"] = context_profile.name
        metadata["browser_context_profile_source"] = context_profile.source
    return metadata


def _execution_context_first_str(
    execution_context: ToolExecutionContext,
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = execution_context.get_str(key)
        if value is not None:
            return value
    return None


def _browser_content_blocks(
    deps: BrowserToolDeps,
    content: Any,
) -> list[dict[str, Any]]:
    attachment_blocks = _browser_attachment_blocks(deps, content)
    if attachment_blocks:
        return attachment_blocks
    context_blocks = _browser_context_blocks(content)
    if context_blocks:
        return context_blocks
    console_blocks = _browser_console_blocks(content)
    if console_blocks:
        return console_blocks
    cookies_blocks = _browser_cookies_blocks(content)
    if cookies_blocks:
        return cookies_blocks
    storage_blocks = _browser_storage_blocks(content)
    if storage_blocks:
        return storage_blocks
    deep_storage_blocks = _browser_deep_storage_blocks(content)
    if deep_storage_blocks:
        return deep_storage_blocks
    dom_blocks = _browser_dom_blocks(content)
    if dom_blocks:
        return dom_blocks
    network_blocks = _browser_network_blocks(content)
    if network_blocks:
        return network_blocks
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
    context_summary = _browser_context_summary(content)
    if context_summary is not None:
        return context_summary
    cookies_summary = _browser_cookies_summary(content)
    if cookies_summary is not None:
        return cookies_summary
    storage_summary = _browser_storage_summary(content)
    if storage_summary is not None:
        return storage_summary
    deep_storage_summary = _browser_deep_storage_summary(content)
    if deep_storage_summary is not None:
        return deep_storage_summary
    dom_summary = _browser_dom_summary(content)
    if dom_summary is not None:
        return dom_summary
    environment_summary = _browser_environment_summary(content)
    if environment_summary is not None:
        return environment_summary
    diagnostic_summary = _browser_diagnostic_summary(content)
    if diagnostic_summary is not None:
        return diagnostic_summary
    network_summary = _browser_network_summary(content)
    if network_summary is not None:
        return network_summary
    evaluate_summary = _browser_evaluate_summary(content)
    if evaluate_summary is not None:
        return evaluate_summary
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


def _browser_context_summary(content: dict[str, Any]) -> str | None:
    context_action = _normalize_text(content.get("context_action"))
    allocation = content.get("allocation")
    if context_action is None or not isinstance(allocation, dict):
        return None
    allocation_id = _normalize_text(allocation.get("allocation_id")) or "context"
    profile_name = _normalize_text(allocation.get("profile_name")) or "profile"
    status = _normalize_text(allocation.get("status")) or "unknown"
    if context_action == "acquire":
        return f"Acquired browser context {allocation_id} for profile {profile_name}."
    if context_action == "release":
        return f"Released browser context {allocation_id}."
    if context_action == "heartbeat":
        return f"Heartbeated browser context {allocation_id}."
    if context_action == "current":
        return f"Current browser context {allocation_id} is {status}."
    if context_action == "reconcile":
        return f"Reconciled browser context {allocation_id}; status is {status}."
    return f"Browser context {allocation_id} is {status}."


def _browser_context_blocks(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, dict):
        return []
    allocation = content.get("allocation")
    if not isinstance(allocation, dict):
        allocations = content.get("allocations")
        if isinstance(allocations, list):
            lines = [
                f"Reconciled {len(allocations)} browser context lease(s).",
            ]
            for item in allocations[:10]:
                if not isinstance(item, dict):
                    continue
                allocation_id = _normalize_text(item.get("allocation_id")) or "unknown"
                profile_name = _normalize_text(item.get("profile_name")) or "unknown"
                status = _normalize_text(item.get("status")) or "unknown"
                lines.append(f"- {allocation_id}: {profile_name} / {status}")
            return [text_content_block("\n".join(lines))]
        return []
    lines = [
        _browser_context_summary(content) or "Browser context lease.",
        f"- Lease: {_normalize_text(allocation.get('allocation_id')) or '-'}",
        f"- Profile: {_normalize_text(allocation.get('profile_name')) or '-'}",
        f"- Pool: {_normalize_text(allocation.get('pool_id')) or '-'}",
        f"- Consumer: {_normalize_text(allocation.get('consumer_kind')) or '-'}:{_normalize_text(allocation.get('consumer_id')) or '-'}",
        f"- Status: {_normalize_text(allocation.get('status')) or '-'}",
        f"- Targets: {len(allocation.get('owned_target_ids') if isinstance(allocation.get('owned_target_ids'), list) else [])}",
    ]
    target_host = _normalize_text(allocation.get("target_host"))
    if target_host is not None:
        lines.append(f"- Target host: {target_host}")
    expires_at = _normalize_text(allocation.get("expires_at"))
    if expires_at is not None:
        lines.append(f"- Expires at: {expires_at}")
    return [text_content_block("\n".join(lines))]


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


def _browser_deep_storage_summary(content: dict[str, Any]) -> str | None:
    found = _find_browser_deep_storage_result(content)
    if found is None:
        return None
    kind, result = found
    if kind == "storage-indexeddb-list":
        return f"Read {int(result.get('count') or 0)} IndexedDB database(s)."
    if kind in {"storage-indexeddb-get", "storage-indexeddb-query"}:
        database = _normalize_text(result.get("database_name")) or "database"
        store = _normalize_text(result.get("object_store_name")) or "store"
        return f"Read {int(result.get('count') or 0)} IndexedDB row(s) from {database}/{store}."
    if kind == "storage-cache-list":
        return f"Read {int(result.get('count') or 0)} CacheStorage cache(s)."
    if kind == "storage-cache-get":
        return f"Read {int(result.get('count') or 0)} CacheStorage entr{'y' if int(result.get('count') or 0) == 1 else 'ies'}."
    if kind in {"service-worker-list", "service-worker-inspect"}:
        return f"Read {int(result.get('count') or 0)} service worker registration(s)."
    return f"Browser {kind} completed."


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


def _browser_deep_storage_blocks(content: Any) -> list[dict[str, Any]]:
    found = _find_browser_deep_storage_result(content)
    if found is None:
        return []
    kind, result = found
    formatted = _format_browser_deep_storage_result(kind, result)
    if formatted is None:
        return []
    return [text_content_block(formatted)]


def _browser_dom_summary(content: dict[str, Any]) -> str | None:
    found = _find_browser_dom_result_payload(content)
    if found is None:
        return None
    kind, result = found
    if kind == "dom-highlight":
        target = _normalize_text(result.get("label")) or _normalize_text(result.get("text")) or "element"
        return f"Browser DOM highlighted {target}."
    if kind == "dom-mutation-wait":
        changed = bool(result.get("changed"))
        count = _normalize_int(result.get("mutation_count"), label="mutation_count", minimum=0)
        count_text = f" ({count} mutations)" if count is not None else ""
        return f"Browser DOM mutation wait {'observed changes' if changed else 'timed out'}{count_text}."
    label = _normalize_text(result.get("label")) or _normalize_text(result.get("text"))
    tag = _normalize_text(result.get("tag")) or "element"
    clickable = bool(result.get("clickable"))
    reasons = result.get("reasons")
    reason_text = ""
    if isinstance(reasons, list) and reasons:
        reason_text = f" ({', '.join(str(item) for item in reasons[:3])})"
    state = "clickable" if clickable else "not clickable"
    suffix = f" '{label}'" if label is not None else ""
    return f"Browser DOM inspected {tag}{suffix}: {state}{reason_text}."


def _browser_dom_blocks(content: Any) -> list[dict[str, Any]]:
    found = _find_browser_dom_result_payload(content)
    if found is None:
        return []
    kind, result = found
    return [text_content_block(_format_browser_dom_result(kind, result))]


def _browser_environment_summary(content: dict[str, Any]) -> str | None:
    found = _find_browser_environment_result_payload(content)
    if found is None:
        return None
    kind, result = found
    changed = result.get("changed_controls")
    changed_text = (
        ", ".join(str(item) for item in changed if str(item).strip())
        if isinstance(changed, (list, tuple))
        else ""
    )
    if kind == "permissions-grant":
        permissions = result.get("permission_names")
        permission_text = (
            ", ".join(str(item) for item in permissions if str(item).strip())
            if isinstance(permissions, (list, tuple))
            else "permissions"
        )
        return f"Browser permissions granted: {permission_text}."
    if kind == "permissions-clear":
        return "Browser permissions cleared."
    if kind == "geolocation-set":
        geolocation = result.get("geolocation")
        if isinstance(geolocation, dict):
            return (
                "Browser geolocation set: "
                f"{geolocation.get('latitude')}, {geolocation.get('longitude')}."
            )
        return "Browser geolocation set."
    if kind == "network-conditions-set":
        conditions = result.get("network_conditions")
        if isinstance(conditions, dict):
            return (
                "Browser network conditions set: "
                f"offline={bool(conditions.get('offline'))}, "
                f"latency={conditions.get('latency_ms')}ms."
            )
        return "Browser network conditions set."
    if kind == "emulation-reset":
        return (
            "Browser emulation reset"
            + (f": {changed_text}." if changed_text else ".")
        )
    return (
        "Browser emulation set"
        + (f": {changed_text}." if changed_text else ".")
    )


def _find_browser_environment_result_payload(
    content: Any,
) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    kind = _normalize_text(result.get("kind")) or command_kind
    if kind not in _ENVIRONMENT_PAGE_ACTION_KINDS:
        return None
    return kind, result


def _browser_diagnostic_summary(content: dict[str, Any]) -> str | None:
    found = _find_browser_diagnostic_result_payload(content)
    if found is None:
        return None
    kind, result = found
    if kind == "diagnostics-collect":
        issue_count = _normalize_int(result.get("issue_count"), label="issue_count", minimum=0)
        return f"Browser diagnostics collected with {issue_count or 0} issue(s)."
    if kind == "performance-metrics":
        errors = result.get("errors")
        error_count = len(errors) if isinstance(errors, list) else 0
        return f"Browser performance metrics collected with {error_count} error(s)."
    if kind == "page-lifecycle":
        ready_state = _normalize_text(result.get("ready_state")) or "unknown"
        visibility = _normalize_text(result.get("visibility_state")) or "unknown"
        return f"Browser page lifecycle: {ready_state}, {visibility}."
    if kind == "page-errors":
        error_count = _normalize_int(result.get("error_count"), label="error_count", minimum=0)
        return f"Browser page errors returned {error_count or 0} item(s)."
    if kind == "trace-start":
        trace_id = _normalize_text(result.get("trace_id")) or "trace"
        return f"Browser trace started: {trace_id}."
    if kind in {"trace-stop", "trace-export"}:
        trace_id = _normalize_text(result.get("trace_id")) or "trace"
        size_bytes = _normalize_int(result.get("size_bytes"), label="size_bytes", minimum=0)
        suffix = f" ({size_bytes} bytes)" if size_bytes is not None else ""
        return f"Browser trace exported: {trace_id}{suffix}."
    return None


def _find_browser_diagnostic_result_payload(
    content: Any,
) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    kind = _normalize_text(result.get("kind")) or command_kind
    if kind not in _DIAGNOSTIC_PAGE_ACTION_KINDS:
        return None
    return kind, result


def _find_browser_dom_result_payload(content: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    kind = _normalize_text(result.get("kind")) or command_kind
    if kind not in _DOM_PAGE_ACTION_KINDS:
        return None
    return kind, result


def _format_browser_dom_result(kind: str, result: dict[str, Any]) -> str:
    label = _normalize_text(result.get("label")) or _normalize_text(result.get("text"))
    tag = _normalize_text(result.get("tag")) or "element"
    role = _normalize_text(result.get("role"))
    selector = _normalize_text(result.get("selector"))
    lines = [f"DOM {kind.removeprefix('dom-')}:"]
    target_parts = [tag]
    if role is not None:
        target_parts.append(f"role={role}")
    if label is not None:
        target_parts.append(f'label="{label}"')
    lines.append(f"- Target: {' '.join(target_parts)}")
    if selector is not None:
        lines.append(f"- Selector: {selector}")
    lines.append(f"- Visible: {'yes' if result.get('visible') else 'no'}")
    lines.append(f"- Clickable: {'yes' if result.get('clickable') else 'no'}")
    reasons = result.get("reasons")
    if isinstance(reasons, list) and reasons:
        lines.append(f"- Reasons: {', '.join(str(item) for item in reasons)}")
    box = result.get("box")
    if isinstance(box, dict):
        width = _coerce_non_negative_number(box.get("width"))
        height = _coerce_non_negative_number(box.get("height"))
        x = _coerce_non_negative_number(box.get("x"))
        y = _coerce_non_negative_number(box.get("y"))
        if width is not None and height is not None and x is not None and y is not None:
            lines.append(f"- Box: {width:.0f}x{height:.0f} at ({x:.0f}, {y:.0f})")
    blocked_by = result.get("blocked_by")
    if isinstance(blocked_by, dict):
        blocker = _normalize_text(blocked_by.get("selector_hint")) or _normalize_text(
            blocked_by.get("tag"),
        )
        if blocker is not None:
            lines.append(f"- Blocked by: {blocker}")
    computed_style = result.get("computed_style")
    if kind == "dom-computed-style" and isinstance(computed_style, dict):
        preview = ", ".join(
            f"{key}={value}"
            for key, value in list(computed_style.items())[:8]
        )
        if preview:
            lines.append(f"- Style: {preview}")
    if kind == "dom-highlight":
        lines.append(f"- Highlighted: {'yes' if result.get('highlighted') else 'no'}")
        duration_ms = _normalize_int(result.get("duration_ms"), label="duration_ms", minimum=0)
        if duration_ms is not None:
            lines.append(f"- Duration: {duration_ms}ms")
        color = _normalize_text(result.get("color"))
        if color is not None:
            lines.append(f"- Color: {color}")
    if kind == "dom-mutation-wait":
        lines.append(f"- Changed: {'yes' if result.get('changed') else 'no'}")
        mutation_count = _normalize_int(
            result.get("mutation_count"),
            label="mutation_count",
            minimum=0,
        )
        if mutation_count is not None:
            lines.append(f"- Mutations: {mutation_count}")
        reason = _normalize_text(result.get("reason"))
        if reason is not None:
            lines.append(f"- Reason: {reason}")
        elapsed_ms = _normalize_int(result.get("elapsed_ms"), label="elapsed_ms", minimum=0)
        if elapsed_ms is not None:
            lines.append(f"- Elapsed: {elapsed_ms}ms")
    return "\n".join(lines)


def _browser_network_summary(content: dict[str, Any]) -> str | None:
    found = _find_browser_network_result_payload(content)
    if found is None:
        return None
    kind, result = found
    if kind == "network-inspect":
        return _browser_network_inspect_summary(result)
    if kind == "network-list-requests":
        requests = _browser_network_requests(result)
        shown_count = len(requests)
        total_count = _browser_network_total_count(result, shown_count)
        capture_id = _normalize_text(result.get("capture_id"))
        capture_suffix = f" for capture '{capture_id}'" if capture_id is not None else ""
        return f"Browser network returned {shown_count} of {total_count} request(s){capture_suffix}."
    if kind == "network-get-request":
        request_id = _normalize_text(result.get("request_id")) or "unknown request"
        return f"Browser network request loaded for {request_id}."
    if kind == "network-get-response-body":
        request_id = _normalize_text(result.get("request_id")) or "unknown request"
        return f"Browser network response body loaded for {request_id}."
    if kind == "network-get-request-body":
        request_id = _normalize_text(result.get("request_id")) or "unknown request"
        return f"Browser network request body loaded for {request_id}."
    if kind == "network-fetch-as-page":
        status = _normalize_text(result.get("status")) or "unknown"
        url = _browser_network_url_label(_normalize_text(result.get("url")))
        return f"Browser page fetch returned {status} from {url}."
    if kind == "network-replay-request":
        status = _normalize_text(result.get("status")) or "unknown"
        source_request_id = _normalize_text(result.get("source_request_id")) or "captured request"
        return f"Browser network replay returned {status} for {source_request_id}."
    if kind == "network-start-capture":
        capture_id = _normalize_text(result.get("capture_id"))
        suffix = f" '{capture_id}'" if capture_id is not None else ""
        return f"Browser network capture{suffix} started."
    if kind == "network-stop-capture":
        capture_id = _normalize_text(result.get("capture_id"))
        suffix = f" '{capture_id}'" if capture_id is not None else ""
        return f"Browser network capture{suffix} stopped."
    if kind == "network-clear-capture":
        capture_id = _normalize_text(result.get("capture_id"))
        suffix = f" '{capture_id}'" if capture_id is not None else ""
        return f"Browser network capture{suffix} cleared."
    return None


def _browser_network_inspect_summary(result: dict[str, Any]) -> str | None:
    performance = result.get("performance")
    entries = performance.get("entries") if isinstance(performance, dict) else None
    entry_count = len(entries) if isinstance(entries, list) else 0
    cdp = result.get("cdp")
    resource_tree = cdp.get("resource_tree") if isinstance(cdp, dict) else None
    resources = None
    if isinstance(resource_tree, dict):
        frame_tree = resource_tree.get("frameTree")
        if isinstance(frame_tree, dict):
            raw_resources = frame_tree.get("resources")
            if isinstance(raw_resources, list):
                resources = len(raw_resources)
    cdp_suffix = f", {resources} CDP resource(s)" if resources is not None else ""
    return f"Browser network inspection returned {entry_count} performance entr{'y' if entry_count == 1 else 'ies'}{cdp_suffix}."


def _browser_network_blocks(content: Any) -> list[dict[str, Any]]:
    found = _find_browser_network_result_payload(content)
    if found is None:
        return []
    kind, result = found
    formatted = _format_browser_network_result(kind, result)
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


def _find_browser_deep_storage_result(content: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    if command_kind not in _DEEP_STORAGE_PAGE_ACTION_KINDS:
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    return command_kind, result


def _find_browser_network_result(content: Any) -> dict[str, Any] | None:
    found = _find_browser_network_result_payload(content)
    if found is None:
        return None
    return found[1]


def _find_browser_network_result_payload(content: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    if not isinstance(command, dict):
        return None
    kind = _normalize_text(command.get("kind"))
    if kind not in _NETWORK_PAGE_ACTION_KINDS and kind != "network-inspect":
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if isinstance(result, dict):
        return kind, result
    if any(key in value for key in ("capture_id", "requests", "body", "body_preview")):
        return kind, value
    return None


def _format_browser_network_result(kind: str, result: dict[str, Any]) -> str | None:
    if kind == "network-inspect":
        return _format_browser_network_inspect_result(result)
    if kind == "network-list-requests":
        return _format_browser_network_requests_result(result)
    if kind == "network-get-request":
        return _format_browser_network_request_result(result)
    if kind == "network-get-response-body":
        return _format_browser_network_body_result(result)
    if kind == "network-get-request-body":
        return _format_browser_network_body_result(result)
    if kind in {"network-fetch-as-page", "network-replay-request"}:
        return _format_browser_network_body_result(result)
    if kind in {
        "network-start-capture",
        "network-stop-capture",
        "network-clear-capture",
    }:
        return _format_browser_network_capture_result(kind, result)
    return None


def _format_browser_network_inspect_result(result: dict[str, Any]) -> str | None:
    performance = result.get("performance")
    if not isinstance(performance, dict):
        performance = {}
    entries = performance.get("entries")
    if not isinstance(entries, list):
        entries = []
    lines = ["Network inspection:"]
    url = _normalize_text(result.get("url")) or _normalize_text(performance.get("url"))
    if url is not None:
        lines.append(f"- Page: {url}")
    if not entries:
        lines.append("- Performance entries: none")
    else:
        lines.append(f"- Performance entries: {len(entries)}")
        for entry in entries[:10]:
            if not isinstance(entry, dict):
                continue
            name = _normalize_text(entry.get("name")) or "<unknown>"
            entry_type = _normalize_text(entry.get("entry_type")) or "entry"
            duration = entry.get("duration")
            duration_text = ""
            if isinstance(duration, int | float):
                duration_text = f" ({duration:.0f}ms)"
            lines.append(f"  - {entry_type}: {name}{duration_text}")
    cdp = result.get("cdp")
    if isinstance(cdp, dict) and cdp:
        if "metrics" in cdp:
            metrics = cdp.get("metrics")
            metric_count = 0
            if isinstance(metrics, dict) and isinstance(metrics.get("metrics"), list):
                metric_count = len(metrics["metrics"])
            lines.append(f"- CDP metrics: {metric_count}")
        if "resource_tree" in cdp:
            resource_tree = cdp.get("resource_tree")
            resource_count = 0
            if isinstance(resource_tree, dict):
                frame_tree = resource_tree.get("frameTree")
                if isinstance(frame_tree, dict) and isinstance(frame_tree.get("resources"), list):
                    resource_count = len(frame_tree["resources"])
            lines.append(f"- CDP resource tree: {resource_count} resource(s)")
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        lines.append(f"- Partial errors: {len(errors)}")
    return "\n".join(lines)


def _format_browser_network_capture_result(kind: str, result: dict[str, Any]) -> str:
    labels = {
        "network-start-capture": "started",
        "network-stop-capture": "stopped",
        "network-clear-capture": "cleared",
    }
    label = labels.get(kind, "updated")
    lines = [f"Network capture {label}:"]
    capture_id = _normalize_text(result.get("capture_id"))
    if capture_id is not None:
        lines.append(f"- Capture: {capture_id}")
    target_id = _normalize_text(result.get("target_id"))
    if target_id is not None:
        lines.append(f"- Target: {target_id}")
    request_count = _coerce_non_negative_int(result.get("request_count"))
    if request_count is not None:
        lines.append(f"- Requests: {request_count}")
    status = _normalize_text(result.get("status"))
    if status is not None:
        lines.append(f"- Status: {status}")
    return "\n".join(lines)


def _format_browser_network_requests_result(result: dict[str, Any]) -> str:
    requests = _browser_network_requests(result)
    total_count = _browser_network_total_count(result, len(requests))
    capture_id = _normalize_text(result.get("capture_id"))
    header = "Network requests"
    if capture_id is not None:
        header += f" ({capture_id})"
    lines = [f"{header}: {len(requests)} shown of {total_count}"]
    if not requests:
        lines.append("- No matching requests.")
        return "\n".join(lines)
    for item in requests[:20]:
        lines.append(f"- {_format_browser_network_request_line(item)}")
    hidden_count = total_count - min(total_count, 20)
    if hidden_count > 0:
        lines.append(f"... {hidden_count} more request(s) in details")
    return "\n".join(lines)


def _format_browser_network_request_line(item: dict[str, Any]) -> str:
    status = _normalize_text(item.get("status")) or "pending"
    method = (_normalize_text(item.get("method")) or "GET").upper()
    resource_type = _normalize_text(item.get("resource_type")) or _normalize_text(item.get("type"))
    mime_type = _normalize_text(item.get("mime_type"))
    request_id = _normalize_text(item.get("request_id"))
    url = _browser_network_url_label(_normalize_text(item.get("url")))
    duration_ms = _coerce_non_negative_number(item.get("duration_ms"))
    if duration_ms is None:
        timing = item.get("timing")
        if isinstance(timing, dict):
            duration_ms = _coerce_non_negative_number(timing.get("duration_ms"))
    parts = [status, method]
    if resource_type is not None:
        parts.append(resource_type)
    parts.append(url)
    suffixes: list[str] = []
    if duration_ms is not None:
        suffixes.append(f"{duration_ms:.0f}ms")
    if mime_type is not None:
        suffixes.append(mime_type)
    if request_id is not None:
        suffixes.append(f"id={request_id}")
    suffix = f" ({', '.join(suffixes)})" if suffixes else ""
    return " ".join(parts) + suffix


def _format_browser_network_request_result(result: dict[str, Any]) -> str:
    request = result.get("request")
    if not isinstance(request, dict):
        request = result
    lines = ["Network request:"]
    request_id = _normalize_text(request.get("request_id"))
    if request_id is not None:
        lines.append(f"- Request: {request_id}")
    lines.append(f"- Summary: {_format_browser_network_request_line(request)}")
    request_body_ref = _normalize_text(request.get("request_body_ref"))
    if request_body_ref is not None:
        lines.append(f"- Request body: {request_body_ref}")
    response_body_ref = _normalize_text(request.get("body_ref"))
    if response_body_ref is not None:
        lines.append(f"- Response body: {response_body_ref}")
    failure_text = _normalize_text(request.get("failure_text"))
    if failure_text is not None:
        lines.append(f"- Failure: {failure_text}")
    return "\n".join(lines)


def _format_browser_network_body_result(result: dict[str, Any]) -> str:
    body_kind = _normalize_text(result.get("body_kind")) or "response"
    label = "request" if body_kind == "request" else "response"
    request = result.get("request")
    if not isinstance(request, dict):
        request = {}
    lines = [f"Network {label} body:"]
    request_id = _normalize_text(result.get("request_id"))
    if request_id is not None:
        lines.append(f"- Request: {request_id}")
    url = _normalize_text(result.get("url")) or _normalize_text(request.get("url"))
    if url is not None:
        lines.append(f"- URL: {_browser_network_url_label(url)}")
    status = _normalize_text(result.get("status")) or _normalize_text(request.get("status"))
    if status is not None:
        lines.append(f"- Status: {status}")
    mime_type = (
        _normalize_text(result.get("mime_type"))
        or _normalize_text(result.get("content_type"))
        or _normalize_text(request.get("mime_type"))
    )
    if mime_type is not None:
        lines.append(f"- Type: {mime_type}")
    size_bytes = _coerce_non_negative_int(result.get("size_bytes"))
    if size_bytes is None:
        size_bytes = _coerce_non_negative_int(result.get("body_size"))
    if size_bytes is not None:
        lines.append(f"- Size: {size_bytes} byte{'s' if size_bytes != 1 else ''}")
    artifact_id = _normalize_text(result.get("artifact_id")) or _normalize_text(result.get("body_ref"))
    if artifact_id is not None:
        lines.append(f"- Body artifact: {artifact_id}")
    preview = _browser_network_body_preview(result)
    if preview is None:
        lines.append("- Body: omitted from top-level content; see details.")
    else:
        lines.append("- Body preview:")
        lines.append(_fenced_text(preview, mime_type=mime_type))
    if bool(result.get("truncated")):
        lines.append("- Truncated: true")
    return "\n".join(lines)


def _browser_network_requests(result: dict[str, Any]) -> list[dict[str, Any]]:
    requests = result.get("requests")
    if not isinstance(requests, list):
        requests = result.get("items")
    if not isinstance(requests, list):
        return []
    return [item for item in requests if isinstance(item, dict)]


def _browser_network_total_count(result: dict[str, Any], fallback: int) -> int:
    for key in ("total", "total_count", "request_count"):
        value = _coerce_non_negative_int(result.get(key))
        if value is not None:
            return value
    return fallback


def _browser_network_body_preview(result: dict[str, Any]) -> str | None:
    for key in ("body_preview", "preview"):
        value = _normalize_text(result.get(key))
        if value is not None:
            return _truncate_text(value, _NETWORK_TOP_LEVEL_BODY_PREVIEW_LIMIT)
    body = result.get("body")
    if isinstance(body, str):
        normalized = body.strip()
        if normalized and len(normalized) <= _NETWORK_TOP_LEVEL_BODY_PREVIEW_LIMIT:
            return normalized
        return None
    for key in ("json", "body_json"):
        value = result.get(key)
        if value is None:
            continue
        try:
            rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        except TypeError:
            rendered = str(value)
        if len(rendered) <= _NETWORK_TOP_LEVEL_BODY_PREVIEW_LIMIT:
            return rendered
        return None
    return None


def _browser_network_url_label(value: str | None) -> str:
    if value is None:
        return "<unknown>"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.netloc:
        path = parsed.path or "/"
        return f"{parsed.netloc}{path}"
    return value


def _fenced_text(value: str, *, mime_type: str | None) -> str:
    language = "json" if mime_type is not None and "json" in mime_type.lower() else "text"
    return f"```{language}\n{value}\n```"


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(limit - 3, 0)].rstrip()}..."


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric >= 0 else None


def _coerce_non_negative_number(value: object) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric >= 0 else None


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


def _format_browser_deep_storage_result(kind: str, result: dict[str, Any]) -> str | None:
    if kind == "storage-indexeddb-list":
        databases = result.get("databases")
        names = result.get("database_names")
        lines = [f"IndexedDB ({_normalize_text(result.get('origin')) or 'origin'}):"]
        if isinstance(databases, list) and databases:
            for database in databases[:20]:
                if not isinstance(database, dict):
                    continue
                name = _normalize_text(database.get("name")) or "<unnamed>"
                store_count = int(database.get("object_store_count") or 0)
                lines.append(f"- {name}: {store_count} object store(s)")
        elif isinstance(names, list) and names:
            for name in names[:20]:
                lines.append(f"- {name}")
        else:
            lines.append("- no databases")
        return "\n".join(lines)
    if kind in {"storage-indexeddb-get", "storage-indexeddb-query"}:
        database = _normalize_text(result.get("database_name")) or "database"
        store = _normalize_text(result.get("object_store_name")) or "store"
        entries = result.get("entries")
        if not isinstance(entries, list) or not entries:
            return f"IndexedDB {database}/{store}: no rows."
        lines = [f"IndexedDB {database}/{store}:"]
        for entry in entries[:10]:
            if isinstance(entry, dict):
                key = entry.get("key")
                value = entry.get("value")
                lines.append(f"- key={key!r} value={value!r}")
        if len(entries) > 10:
            lines.append(f"... {len(entries) - 10} more rows")
        return "\n".join(lines)
    if kind == "storage-cache-list":
        caches = result.get("caches")
        if not isinstance(caches, list) or not caches:
            return "CacheStorage: no caches."
        lines = ["CacheStorage:"]
        for cache in caches[:20]:
            if isinstance(cache, dict):
                cache_name = _normalize_text(cache.get("cache_name")) or "<unnamed>"
                cache_id = _normalize_text(cache.get("cache_id")) or ""
                suffix = f" ({cache_id})" if cache_id else ""
                lines.append(f"- {cache_name}{suffix}")
        return "\n".join(lines)
    if kind == "storage-cache-get":
        entries = result.get("entries")
        if not isinstance(entries, list) or not entries:
            return "CacheStorage: no matching entries."
        lines = ["CacheStorage entries:"]
        for entry in entries[:10]:
            if isinstance(entry, dict):
                url = _normalize_text(entry.get("request_url")) or "<unknown>"
                status = entry.get("response_status")
                lines.append(f"- {status or '-'} {url}")
        response = result.get("response")
        if isinstance(response, dict) and _normalize_text(response.get("body")) is not None:
            lines.append(f"- response body bytes: {response.get('body_size_bytes') or 0}")
        return "\n".join(lines)
    if kind in {"service-worker-list", "service-worker-inspect"}:
        registrations = result.get("registrations")
        if not isinstance(registrations, list) or not registrations:
            return "Service workers: no registrations."
        lines = ["Service workers:"]
        for registration in registrations[:20]:
            if not isinstance(registration, dict):
                continue
            scope = _normalize_text(registration.get("scope_url")) or "<unknown scope>"
            active = registration.get("active")
            state = "-"
            script_url = "-"
            if isinstance(active, dict):
                state = _normalize_text(active.get("state")) or "-"
                script_url = _normalize_text(active.get("script_url")) or "-"
            lines.append(f"- {scope}: active={state} script={script_url}")
        return "\n".join(lines)
    return None


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


def _browser_result_details(content: Any) -> Any:
    if not isinstance(content, dict):
        return content
    return _sanitize_browser_result_details(content)


def _sanitize_browser_result_details(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {str(key): _sanitize_browser_result_details(item) for key, item in value.items()}
        kind = _normalize_text(sanitized.get("kind"))
        content_type = _normalize_text(sanitized.get("content_type"))
        if (
            kind in {"screenshot", "pdf", "download", "trace", "trace-stop", "trace-export"}
            and content_type is not None
        ):
            data = sanitized.get("data")
            if isinstance(data, str) and data:
                sanitized.pop("data", None)
                sanitized["attachment_in_content"] = True
        return sanitized
    if isinstance(value, list):
        return [_sanitize_browser_result_details(item) for item in value]
    return value


def _browser_attachment_blocks(
    deps: BrowserToolDeps,
    content: Any,
) -> list[dict[str, Any]]:
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
                deps,
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
                deps,
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
                deps,
                kind="download",
                content_type=content_type,
                data=data,
                fallback_name=attachment_name or "browser-download.bin",
            ),
        ]
    if kind == "trace":
        return [
            text_content_block("Browser trace captured."),
            _browser_attachment_block(
                deps,
                kind="trace",
                content_type=content_type,
                data=data,
                fallback_name=attachment_name or "browser-trace.zip",
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
        if kind in {"trace", "trace-stop", "trace-export"} and content_type is not None and data is not None:
            trace_id = _normalize_text(value.get("trace_id")) or "browser-trace"
            return "trace", content_type, data, f"{trace_id}.zip"
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
    deps: BrowserToolDeps,
    *,
    kind: str,
    content_type: str,
    data: str,
    fallback_name: str,
) -> dict[str, Any]:
    artifact_service = deps.artifact_service
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
    deps: BrowserToolDeps,
    profile_name: str,
    exc: BrowserValidationError,
) -> BrowserValidationError:
    message = str(exc).strip().lower()
    if (
        "handshake status 403" in message
        or "rejected an incoming websocket connection" in message
        or "remote-allow-origins" in message
    ):
        augmented_message = (
            f"{exc} Next: reset the managed browser for profile '{profile_name}' and run-open-tab again. "
            "Reason: The running browser was launched with a mismatched remote-allow-origins policy."
        )
        if isinstance(exc, BrowserToolApplicationError):
            return exc.with_message(augmented_message)
        return BrowserValidationError(augmented_message)
    if (
        "requires ref or selector targeting" in message
        or "wait requires " in message
        or "browser operation " in message
        or "steps must be" in message
        or "must decode to an object" in message
        or "payload." in message
        or " is required." in message
        or " must be " in message
        or ("browser tab '" in message and "not available through playwright cdp" in message)
        or ("browser tab '" in message and "was not found" in message)
    ):
        return exc
    try:
        diagnostics_payload = build_profile_diagnostics_payload(
            deps,
            profile_name=profile_name,
        )
    except Exception:  # noqa: BLE001
        return exc

    guidance = _profile_diagnostics_guidance(
        diagnostics_payload,
        system_config_store=deps.browser_system_config_store,
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
    augmented_message = f"{exc} {' '.join(guidance_parts)}"
    if isinstance(exc, BrowserToolApplicationError):
        return exc.with_message(augmented_message)
    return BrowserValidationError(augmented_message)


def _resolve_profile_selection(
    arguments: dict[str, Any],
    system_config_store: Any,
    execution_context: ToolExecutionContext | None,
) -> BrowserProfileSelection:
    explicit_selection = _profile_selection_from_input_or_context(
        arguments,
        execution_context,
    )
    if explicit_selection is not None:
        return explicit_selection
    return BrowserProfileSelection(
        name=system_config_store.load().default_profile,
        source="browser.default_profile",
    )


def _resolve_browser_profile_for_execution(
    *,
    deps: BrowserToolDeps,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> BrowserResolvedProfile:
    explicit_profile = _profile_selection_from_input(arguments)
    profile_pool = _profile_pool_selection_from_input_or_context(
        arguments,
        execution_context,
    )
    allocator = deps.browser_profile_allocator_service
    if allocator is None:
        if profile_pool is not None:
            raise _browser_profile_selection_error(
                BrowserValidationError(
                    "browser profile_pool requires the Browser profile allocator service.",
                ),
                profile=explicit_profile,
                profile_pool=profile_pool,
            )
        selection = _resolve_profile_selection(
            arguments,
            deps.browser_system_config_store,
            execution_context,
        )
        return BrowserResolvedProfile(
            name=selection.name,
            source=selection.source,
            allocation_metadata={
                "profile_source": selection.source,
                "browser_profile": selection.name,
                "browser_profile_source": selection.source,
            },
        )

    target_host = _target_host_for_profile_allocation(arguments, execution_context)
    allocation_from_context = _allocation_selection_from_input_or_context(
        arguments,
        execution_context,
    )
    if explicit_profile is None and profile_pool is None and allocation_from_context is not None:
        try:
            allocation = allocator.get_allocation(
                allocation_id=allocation_from_context.name,
            )
        except BrowserValidationError as exc:
            raise _browser_profile_selection_error(
                exc,
                profile=explicit_profile,
                profile_pool=profile_pool,
                allocation=allocation_from_context,
            ) from exc
        return BrowserResolvedProfile(
            name=str(allocation.profile_name),
            source=allocation_from_context.source,
            allocation_metadata=_allocation_runtime_metadata(
                allocation,
                profile_source=allocation_from_context.source,
                profile_pool_source=None,
            ),
        )

    if explicit_profile is None and profile_pool is None:
        explicit_profile = _resolve_profile_selection(
            arguments,
            deps.browser_system_config_store,
            execution_context,
        )

    consumer_kind, consumer_id = _allocation_consumer(execution_context)
    try:
        allocation = allocator.allocate(
            consumer_kind=consumer_kind,
            consumer_id=consumer_id,
            pool_id=profile_pool.name if profile_pool is not None else None,
            profile_name=explicit_profile.name if explicit_profile is not None else None,
            target_host=target_host,
        )
    except BrowserValidationError as exc:
        raise _browser_profile_selection_error(
            exc,
            profile=explicit_profile,
            profile_pool=profile_pool,
        ) from exc
    profile_source = (
        profile_pool.source
        if explicit_profile is None and profile_pool is not None
        else explicit_profile.source if explicit_profile is not None else "browser.default_profile"
    )
    return BrowserResolvedProfile(
        name=str(allocation.profile_name),
        source=profile_source,
        allocation_metadata=_allocation_runtime_metadata(
            allocation,
            profile_source=profile_source,
            profile_pool_source=profile_pool.source if profile_pool is not None else None,
        ),
    )


def _profile_selection_from_input(
    arguments: dict[str, Any],
) -> BrowserProfileSelection | None:
    for key in _BROWSER_INPUT_PROFILE_KEYS:
        value = _normalize_text(arguments.get(key))
        if value is not None:
            return BrowserProfileSelection(name=value, source=f"input.{key}")
    return None


def _profile_selection_from_input_or_context(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> BrowserProfileSelection | None:
    input_selection = _profile_selection_from_input(arguments)
    if input_selection is not None:
        return input_selection
    return _profile_selection_from_context(execution_context)


def _profile_pool_selection_from_input_or_context(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> BrowserProfileSelection | None:
    for key in _BROWSER_INPUT_PROFILE_POOL_KEYS:
        value = _normalize_text(arguments.get(key))
        if value is not None:
            return BrowserProfileSelection(name=value, source=f"input.{key}")
    if execution_context is None:
        return None
    for key in _BROWSER_CONTEXT_PROFILE_POOL_KEYS:
        value = execution_context.get_str(key)
        if value is not None:
            return BrowserProfileSelection(name=value, source=f"context.{key}")
    return None


def _allocation_selection_from_context(
    execution_context: ToolExecutionContext | None,
) -> BrowserProfileSelection | None:
    if execution_context is None:
        return None
    for key in _BROWSER_CONTEXT_ALLOCATION_KEYS:
        value = execution_context.get_str(key)
        if value is not None:
            return BrowserProfileSelection(name=value, source=f"context.{key}")
    return None


def _allocation_selection_from_input_or_context(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> BrowserProfileSelection | None:
    for key in _BROWSER_INPUT_ALLOCATION_KEYS:
        value = _normalize_text(arguments.get(key))
        if value is not None:
            return BrowserProfileSelection(name=value, source=f"input.{key}")
    return _allocation_selection_from_context(execution_context)


def _profile_selection_from_context(
    execution_context: ToolExecutionContext | None,
) -> BrowserProfileSelection | None:
    if execution_context is None:
        return None
    for key in _BROWSER_CONTEXT_PROFILE_KEYS:
        value = execution_context.get_str(key)
        if value is not None:
            return BrowserProfileSelection(name=value, source=f"context.{key}")
    return None


def _profile_source(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> str:
    profile_pool = _profile_pool_selection_from_input_or_context(
        arguments,
        execution_context,
    )
    if profile_pool is not None and _profile_selection_from_input(arguments) is None:
        return profile_pool.source
    selection = _profile_selection_from_input_or_context(arguments, execution_context)
    return selection.source if selection is not None else "browser.default_profile"


def _allocation_consumer(
    execution_context: ToolExecutionContext | None,
) -> tuple[str, str]:
    if execution_context is not None:
        for consumer_kind, keys in (
            ("orchestration_run", ("run_id", "orchestration_run_id")),
            ("session", ("active_session_id", "session_id", "session_key")),
            ("agent", ("agent_id",)),
            ("tool_run", ("tool_run_id", "tool_run", "tool_invocation_id")),
        ):
            value = _execution_context_first_str(execution_context, keys)
            if value is not None:
                return consumer_kind, value
    return "manual", "browser-tool"


def _target_host_for_profile_allocation(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> str | None:
    for candidate in _target_url_candidates(arguments):
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            continue
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            return parsed.hostname.lower()
    if execution_context is not None:
        return execution_context.get_str("browser_target_host")
    return None


def _target_url_candidates(arguments: dict[str, Any]) -> tuple[str, ...]:
    candidates: list[str] = []
    for key in ("url", "target_url", "page_url"):
        value = _normalize_text(arguments.get(key))
        if value is not None:
            candidates.append(value)
    payload = arguments.get("payload")
    if isinstance(payload, Mapping):
        for key in ("url", "target_url", "page_url"):
            value = _normalize_text(payload.get(key))
            if value is not None:
                candidates.append(value)
    return tuple(dict.fromkeys(candidates))


def _allocation_runtime_metadata(
    allocation: Any,
    *,
    profile_source: str,
    profile_pool_source: str | None,
) -> dict[str, Any]:
    allocation_metadata = getattr(allocation, "metadata", None)
    if not isinstance(allocation_metadata, Mapping):
        allocation_metadata = {}
    metadata: dict[str, Any] = {
        "profile_source": profile_source,
        "browser_profile": getattr(allocation, "profile_name", None),
        "browser_profile_source": profile_source,
        "browser_profile_pool": getattr(allocation, "pool_id", None),
        "browser_allocation_id": getattr(allocation, "allocation_id", None),
        "browser_context_lease_id": getattr(allocation, "allocation_id", None),
        "browser_allocation_status": getattr(allocation, "status", None),
        "browser_context_lease_status": getattr(allocation, "status", None),
        "browser_allocation_consumer_kind": getattr(allocation, "consumer_kind", None),
        "browser_allocation_consumer_id": getattr(allocation, "consumer_id", None),
        "browser_profile_selection_reason": allocation_metadata.get("selection_reason"),
        "browser_profile_allocation_source": allocation_metadata.get("profile_source"),
        "browser_host_service_key": allocation_metadata.get("host_service_key"),
    }
    target_host = getattr(allocation, "target_host", None)
    if target_host is not None:
        metadata["browser_target_host"] = target_host
    if profile_pool_source is not None:
        metadata["browser_profile_pool_source"] = profile_pool_source
    return {key: value for key, value in metadata.items() if value is not None}


def _browser_profile_selection_error(
    exc: BrowserValidationError,
    *,
    profile: BrowserProfileSelection | None,
    profile_pool: BrowserProfileSelection | None,
    allocation: BrowserProfileSelection | None = None,
) -> BrowserToolApplicationError:
    message = _safe_error_message(str(exc))
    code, retryable, setup_required = _classify_profile_selection_error(message)
    details: dict[str, Any] = {"category": "browser"}
    if profile is not None:
        details["profile"] = profile.name
        details["profile_source"] = profile.source
    if profile_pool is not None:
        details["profile_pool"] = profile_pool.name
        details["profile_pool_source"] = profile_pool.source
    if allocation is not None:
        details["allocation_id"] = allocation.name
        details["allocation_source"] = allocation.source
    return BrowserToolApplicationError(
        BrowserToolExecutionError(
            code=code,
            message=message,
            details=details,
            retryable=retryable,
            setup_required=setup_required,
        ),
    )


def _classify_profile_selection_error(message: str) -> tuple[str, bool, bool]:
    normalized = message.lower()
    if "profile and profile_pool" in normalized:
        return "browser_profile_selection_conflict", False, False
    if "allocation" in normalized and "not configured" in normalized:
        return "browser_allocation_not_found", False, True
    if "pool" in normalized and "not configured" in normalized:
        return "browser_profile_pool_not_found", False, True
    if "max concurrency" in normalized:
        return "browser_profile_pool_concurrency_exceeded", True, False
    if "no eligible profile" in normalized or "disabled" in normalized:
        return "browser_profile_pool_not_ready", True, True
    if "requires an explicit profile" in normalized:
        return "browser_profile_pool_requires_profile", False, False
    if "not a member of pool" in normalized:
        return "browser_profile_selection_conflict", False, False
    if "profile" in normalized and "not configured" in normalized:
        return "browser_profile_not_found", False, True
    return "browser_profile_selection_failed", False, True


def _safe_error_message(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        return "Browser profile selection failed."
    if len(normalized) > 800:
        return f"{normalized[:797]}..."
    return normalized


def _resolve_profile_name(arguments: dict[str, Any], system_config_store: Any) -> str:
    return _resolve_profile_selection(
        arguments,
        system_config_store,
        execution_context=None,
    ).name


def _ensure_browser_enabled(settings: Any) -> None:
    if settings is not None and not getattr(settings, "browser_enabled", True):
        raise BrowserValidationError("Browser module is disabled.")


def _execute_control(
    *,
    deps: BrowserToolDeps,
    tool_id: str,
    kind: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    content, profile_name, runtime_metadata = _run_control_content(
        deps=deps,
        kind=kind,
        arguments=arguments,
        execution_context=execution_context,
    )
    return _tool_result(
        deps=deps,
        tool_id=tool_id,
        content=content,
        family="control",
        profile_name=profile_name,
        profile_source=runtime_metadata.get(
            "profile_source",
            _profile_source(arguments, execution_context),
        ),
        runtime_metadata=runtime_metadata,
        kind=kind,
        execution_context=execution_context,
    )


def _run_control_content(
    *,
    deps: BrowserToolDeps,
    kind: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> tuple[Any, str, dict[str, Any]]:
    _ensure_browser_enabled(deps.settings)
    resolved_profile = _resolve_browser_profile_for_execution(
        deps=deps,
        arguments=arguments,
        execution_context=execution_context,
    )
    profile_name = resolved_profile.name
    target_id = _normalize_browser_target_id(arguments.get("target_id"))
    timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    payload = _coerce_payload(arguments.get("payload"))
    url = _normalize_text(arguments.get("url"))
    if url is not None:
        payload.setdefault("url", url)
    try:
        result = deps.browser_tool_application.execute_control(
            profile_name=profile_name,
            kind=kind,
            target_id=target_id,
            payload=payload,
            timeout_ms=timeout_ms,
        )
    except BrowserValidationError as exc:
        raise _augment_browser_error_with_guidance(
            deps=deps,
            profile_name=profile_name,
            exc=exc,
        ) from exc
    content, runtime_metadata = _tool_application_result_payload(result)
    merged_metadata = {**resolved_profile.allocation_metadata, **runtime_metadata}
    _sync_allocation_target_after_control(
        deps=deps,
        kind=kind,
        content=content,
        runtime_metadata=merged_metadata,
    )
    return content, profile_name, merged_metadata


def _execute_page_action(
    *,
    deps: BrowserToolDeps,
    tool_id: str,
    kind: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    content, profile_name, runtime_metadata = _run_page_action_content(
        deps=deps,
        kind=kind,
        arguments=arguments,
        execution_context=execution_context,
    )
    return _tool_result(
        deps=deps,
        tool_id=tool_id,
        content=content,
        family="page-action",
        profile_name=profile_name,
        profile_source=runtime_metadata.get(
            "profile_source",
            _profile_source(arguments, execution_context),
        ),
        runtime_metadata=runtime_metadata,
        kind=kind,
        execution_context=execution_context,
    )


def _run_page_action_content(
    *,
    deps: BrowserToolDeps,
    kind: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None = None,
) -> tuple[Any, str, dict[str, Any]]:
    _ensure_browser_enabled(deps.settings)
    resolved_profile = _resolve_browser_profile_for_execution(
        deps=deps,
        arguments=arguments,
        execution_context=execution_context,
    )
    profile_name = resolved_profile.name
    target_id = _normalize_browser_target_id(arguments.get("target_id"))
    ref = _normalize_text(arguments.get("ref"))
    selector = _normalize_text(arguments.get("selector"))
    timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    payload = _coerce_payload(arguments.get("payload"))
    try:
        result = deps.browser_tool_application.execute_page_action(
            profile_name=profile_name,
            kind=kind,
            target_id=target_id,
            ref=ref,
            selector=selector,
            payload=payload,
            timeout_ms=timeout_ms,
        )
    except BrowserValidationError as exc:
        raise _augment_browser_error_with_guidance(
            deps=deps,
            profile_name=profile_name,
            exc=exc,
        ) from exc
    content, runtime_metadata = _tool_application_result_payload(result)
    return content, profile_name, {**resolved_profile.allocation_metadata, **runtime_metadata}


def _tool_application_result_payload(result: Any) -> tuple[Any, dict[str, Any]]:
    payload = getattr(result, "payload", None)
    runtime_metadata = getattr(result, "runtime_metadata", None)
    if payload is None:
        payload = result
    return payload, _coerce_browser_runtime_metadata(
        runtime_metadata if isinstance(runtime_metadata, Mapping) else None,
    )


def _sync_allocation_target_after_control(
    *,
    deps: BrowserToolDeps,
    kind: str,
    content: Any,
    runtime_metadata: Mapping[str, Any],
) -> None:
    allocator = deps.browser_profile_allocator_service
    if allocator is None:
        return
    allocation_id = _normalize_text(runtime_metadata.get("browser_allocation_id"))
    if allocation_id is None:
        return
    target_id = _normalize_text(runtime_metadata.get("browser_target_id"))
    if target_id is None:
        target_id = _extract_browser_target_id(content)
    if target_id is None:
        return
    if kind == "open-tab":
        remember = getattr(allocator, "remember_allocation_target", None)
        if callable(remember):
            try:
                remember(allocation_id=allocation_id, target_id=target_id)
            except BrowserValidationError:
                return
    elif kind == "close-tab":
        forget = getattr(allocator, "forget_allocation_target", None)
        if callable(forget):
            try:
                forget(allocation_id=allocation_id, target_id=target_id)
            except BrowserValidationError:
                return


def _execute_context(
    *,
    deps: BrowserToolDeps,
    tool_id: str,
    action: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    _ensure_browser_enabled(deps.settings)
    allocator = deps.browser_profile_allocator_service
    if allocator is None:
        raise BrowserValidationError(
            "browser.context requires the Browser profile allocator service.",
        )
    normalized_action = action.strip().lower()
    if normalized_action == "acquire":
        content, metadata = _browser_context_acquire(
            deps=deps,
            arguments=arguments,
            execution_context=execution_context,
        )
    elif normalized_action == "current":
        allocation = _current_context_allocation(
            allocator=allocator,
            arguments=arguments,
            execution_context=execution_context,
        )
        content = _browser_context_content("current", allocation)
        metadata = _allocation_runtime_metadata(
            allocation,
            profile_source="context.lease",
            profile_pool_source=None,
        )
    elif normalized_action == "heartbeat":
        allocation = _current_context_allocation(
            allocator=allocator,
            arguments=arguments,
            execution_context=execution_context,
        )
        ttl_seconds = _normalize_int(arguments.get("ttl_seconds"), label="ttl_seconds", minimum=1)
        allocation = allocator.heartbeat_allocation(
            allocation_id=allocation.allocation_id,
            ttl_seconds=ttl_seconds,
        )
        content = _browser_context_content("heartbeat", allocation)
        metadata = _allocation_runtime_metadata(
            allocation,
            profile_source="context.lease",
            profile_pool_source=None,
        )
    elif normalized_action == "release":
        allocation = _current_context_allocation(
            allocator=allocator,
            arguments=arguments,
            execution_context=execution_context,
        )
        reason = _normalize_text(arguments.get("reason")) or "released"
        close_owned_targets = _normalize_bool(
            arguments.get("close_owned_targets"),
            label="close_owned_targets",
        )
        allocation = allocator.release_allocation(
            allocation_id=allocation.allocation_id,
            reason=reason,
            recycle_targets=close_owned_targets,
        )
        content = _browser_context_content("release", allocation)
        metadata = _allocation_runtime_metadata(
            allocation,
            profile_source="context.lease",
            profile_pool_source=None,
        )
    elif normalized_action == "reconcile":
        selection = _allocation_selection_from_input_or_context(
            arguments,
            execution_context,
        )
        if selection is None:
            allocations = allocator.reconcile_allocations()
            content = {
                "ok": True,
                "context_action": "reconcile",
                "allocations": [_browser_allocation_payload(item) for item in allocations],
                "reconciled": len(allocations),
                "message": f"Reconciled {len(allocations)} browser context lease(s).",
            }
            metadata = {"browser_context_reconciled": len(allocations)}
        else:
            allocation = allocator.reconcile_allocation(allocation_id=selection.name)
            content = _browser_context_content("reconcile", allocation)
            metadata = _allocation_runtime_metadata(
                allocation,
                profile_source=selection.source,
                profile_pool_source=None,
            )
    else:
        raise BrowserValidationError(
            "browser.context action must be one of acquire, current, heartbeat, release, reconcile.",
        )
    return _tool_result(
        deps=deps,
        tool_id=tool_id,
        content=content,
        family="context",
        profile_name=_normalize_text(metadata.get("browser_profile")),
        profile_source=_normalize_text(metadata.get("profile_source")),
        runtime_metadata=metadata,
        kind=normalized_action,
        execution_context=execution_context,
    )


def _browser_context_acquire(
    *,
    deps: BrowserToolDeps,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    allocator = deps.browser_profile_allocator_service
    if allocator is None:
        raise BrowserValidationError(
            "browser.context.acquire requires the Browser profile allocator service.",
        )
    explicit_profile = _profile_selection_from_input(arguments)
    profile_pool = _profile_pool_selection_from_input_or_context(
        arguments,
        execution_context,
    )
    if explicit_profile is None and profile_pool is None:
        explicit_profile = _resolve_profile_selection(
            arguments,
            deps.browser_system_config_store,
            execution_context,
        )
    consumer_kind, consumer_id = _allocation_consumer(execution_context)
    target_host = _target_host_for_profile_allocation(arguments, execution_context)
    try:
        allocation = allocator.allocate(
            consumer_kind=consumer_kind,
            consumer_id=consumer_id,
            pool_id=profile_pool.name if profile_pool is not None else None,
            profile_name=explicit_profile.name if explicit_profile is not None else None,
            target_host=target_host,
        )
    except BrowserValidationError as exc:
        raise _browser_profile_selection_error(
            exc,
            profile=explicit_profile,
            profile_pool=profile_pool,
        ) from exc

    target_id = _normalize_text(arguments.get("target_id"))
    if target_id is not None:
        allocation = allocator.remember_allocation_target(
            allocation_id=allocation.allocation_id,
            target_id=target_id,
        )

    opened_tab: Any | None = None
    url = _normalize_text(arguments.get("url"))
    if url is not None:
        result = deps.browser_tool_application.execute_control(
            profile_name=allocation.profile_name,
            kind="open-tab",
            payload={"url": url},
        )
        opened_payload, runtime_metadata = _tool_application_result_payload(result)
        opened_tab = opened_payload
        opened_target_id = _normalize_text(runtime_metadata.get("browser_target_id"))
        if opened_target_id is None:
            opened_target_id = _extract_browser_target_id(opened_payload)
        if opened_target_id is not None:
            allocation = allocator.remember_allocation_target(
                allocation_id=allocation.allocation_id,
                target_id=opened_target_id,
            )

    profile_source = (
        profile_pool.source
        if explicit_profile is None and profile_pool is not None
        else explicit_profile.source if explicit_profile is not None else "browser.default_profile"
    )
    content = _browser_context_content("acquire", allocation)
    if opened_tab is not None:
        content["opened_tab"] = opened_tab
    return content, _allocation_runtime_metadata(
        allocation,
        profile_source=profile_source,
        profile_pool_source=profile_pool.source if profile_pool is not None else None,
    )


def _current_context_allocation(
    *,
    allocator: Any,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> Any:
    selection = _allocation_selection_from_input_or_context(arguments, execution_context)
    if selection is not None:
        return allocator.get_allocation(allocation_id=selection.name)
    consumer_kind, consumer_id = _allocation_consumer(execution_context)
    active = allocator.list_allocations(active_only=True)
    for allocation in active:
        if (
            getattr(allocation, "consumer_kind", None) == consumer_kind
            and getattr(allocation, "consumer_id", None) == consumer_id
        ):
            return allocation
    raise BrowserValidationError(
        "No active browser context lease is available for this execution context.",
    )


def _browser_context_content(action: str, allocation: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "context_action": action,
        "lease_id": getattr(allocation, "allocation_id", None),
        "allocation": _browser_allocation_payload(allocation),
        "message": _browser_context_message(action, allocation),
    }


def _browser_context_message(action: str, allocation: Any) -> str:
    allocation_id = getattr(allocation, "allocation_id", "context")
    if action == "acquire":
        return f"Acquired browser context lease '{allocation_id}'."
    if action == "release":
        return f"Released browser context lease '{allocation_id}'."
    if action == "heartbeat":
        return f"Heartbeated browser context lease '{allocation_id}'."
    if action == "reconcile":
        return f"Reconciled browser context lease '{allocation_id}'."
    return f"Loaded browser context lease '{allocation_id}'."


def _browser_allocation_payload(allocation: Any) -> dict[str, Any]:
    return {
        "allocation_id": getattr(allocation, "allocation_id", None),
        "lease_id": getattr(allocation, "allocation_id", None),
        "pool_id": getattr(allocation, "pool_id", None),
        "profile_name": getattr(allocation, "profile_name", None),
        "consumer_kind": getattr(allocation, "consumer_kind", None),
        "consumer_id": getattr(allocation, "consumer_id", None),
        "target_host": getattr(allocation, "target_host", None),
        "status": getattr(allocation, "status", None),
        "acquired_at": _datetime_iso(getattr(allocation, "acquired_at", None)),
        "expires_at": _datetime_iso(getattr(allocation, "expires_at", None)),
        "last_heartbeat_at": _datetime_iso(
            getattr(allocation, "last_heartbeat_at", None),
        ),
        "released_at": _datetime_iso(getattr(allocation, "released_at", None)),
        "release_reason": getattr(allocation, "release_reason", None),
        "owned_target_ids": list(getattr(allocation, "owned_target_ids", ()) or ()),
        "metadata": dict(getattr(allocation, "metadata", {}) or {}),
    }


def _datetime_iso(value: Any) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    if not callable(isoformat):
        return None
    return str(isoformat())


def _coerce_operation_steps(value: object) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise BrowserValidationError(
                "browser operation steps must be a JSON array or an array of step objects.",
            ) from exc
    if not isinstance(value, list):
        raise BrowserValidationError(
            "browser operation steps must be a list of step objects.",
        )
    normalized: list[dict[str, Any]] = []
    for raw_step in value:
        if isinstance(raw_step, str):
            try:
                raw_step = json.loads(raw_step)
            except ValueError as exc:
                raise BrowserValidationError(
                    "browser operation steps must be objects. Do not wrap each step in a JSON string.",
                ) from exc
        if not isinstance(raw_step, dict):
            raise BrowserValidationError(
                "browser operation steps must be objects. Do not wrap each step in a JSON string.",
            )
        normalized.append(dict(raw_step))
    if not normalized:
        raise BrowserValidationError("browser operation requires at least one step.")
    return normalized


def _operation_step_target_id(
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
    if family == "page-action" or kind in _OPERATION_INHERITED_TARGET_CONTROL_KINDS:
        normalized = dict(step_arguments)
        normalized["target_id"] = current_target_id
        return normalized
    return step_arguments


def _operation_step_defaults(
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
    x = _normalize_number(arguments.get("x"), label="x")
    if x is not None:
        payload.setdefault("x", x)
    y = _normalize_number(arguments.get("y"), label="y")
    if y is not None:
        payload.setdefault("y", y)
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


def _normalize_advanced_action_arguments(
    arguments: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    normalized_arguments = dict(arguments)
    payload = _coerce_payload(arguments.get("payload"))
    text = _normalize_text(arguments.get("text"))
    if text is not None:
        payload.setdefault("text", text)
    delay_ms = _normalize_int(arguments.get("delay_ms"), label="delay_ms", minimum=0)
    if delay_ms is not None:
        payload.setdefault("delay_ms", delay_ms)
    key = _normalize_text(arguments.get("key"))
    if key is not None and kind == "press":
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
    if image_type is not None and kind == "screenshot":
        payload.setdefault("type", image_type)
    full_page = _normalize_bool(arguments.get("full_page"), label="full_page")
    if full_page is not None and kind == "screenshot":
        payload.setdefault("full_page", full_page)
    print_background = _normalize_bool(arguments.get("print_background"), label="print_background")
    if print_background is not None and kind == "pdf":
        payload.setdefault("print_background", print_background)
    expression = _normalize_text(arguments.get("expression"))
    if expression is not None and kind == "evaluate":
        payload.setdefault("expression", expression)
    fn = _normalize_text(arguments.get("fn"))
    if fn is not None and kind == "evaluate":
        payload.setdefault("fn", fn)
    if "arg" in arguments and arguments.get("arg") is not None:
        payload.setdefault("arg", arguments.get("arg"))
    if kind in _DOM_PAGE_ACTION_KINDS:
        include_styles = _normalize_bool(arguments.get("include_styles"), label="include_styles")
        if include_styles is not None:
            payload.setdefault("include_styles", include_styles)
        for argument_key, payload_key in (
            ("style_properties", "style_properties"),
            ("properties", "style_properties"),
            ("attributes", "attributes"),
        ):
            value = arguments.get(argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
    if kind == "dom-highlight":
        duration_ms = _normalize_int(arguments.get("duration_ms"), label="duration_ms", minimum=100)
        if duration_ms is not None:
            payload.setdefault("duration_ms", duration_ms)
        color = _normalize_text(arguments.get("color"))
        if color is not None:
            payload.setdefault("color", color)
        label = _normalize_text(arguments.get("label"))
        if label is not None:
            payload.setdefault("label", label)
    if kind == "dom-mutation-wait":
        quiet_ms = _normalize_int(arguments.get("quiet_ms"), label="quiet_ms", minimum=0)
        if quiet_ms is not None:
            payload.setdefault("quiet_ms", quiet_ms)
        for argument_key, payload_key in (
            ("subtree", "subtree"),
            ("child_list", "child_list"),
            ("childList", "child_list"),
            ("attributes", "attributes"),
            ("character_data", "character_data"),
            ("characterData", "character_data"),
        ):
            value = _normalize_bool(arguments.get(argument_key), label=argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
        for argument_key, payload_key in (
            ("attribute_filter", "attribute_filter"),
            ("attributeFilter", "attribute_filter"),
        ):
            value = arguments.get(argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
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
    if level is not None and kind == "console":
        payload.setdefault("level", level)
    clear = _normalize_bool(arguments.get("clear"), label="clear")
    if clear is not None and kind == "console":
        payload.setdefault("clear", clear)
    limit = _normalize_int(arguments.get("limit"), label="limit", minimum=1)
    if limit is not None and kind in {"console", "network-inspect", "storage"} | _DEEP_STORAGE_PAGE_ACTION_KINDS:
        payload.setdefault("limit", limit)
    skip = _normalize_int(arguments.get("skip"), label="skip", minimum=0)
    if skip is not None and kind in _DEEP_STORAGE_PAGE_ACTION_KINDS:
        payload.setdefault("skip", skip)
    if kind == "network-inspect":
        for argument_key, payload_key in (
            ("include_navigation", "include_navigation"),
            ("include_resources", "include_resources"),
            ("include_cdp_tree", "include_cdp_tree"),
            ("include_performance_metrics", "include_performance_metrics"),
        ):
            resolved = _normalize_bool(arguments.get(argument_key), label=argument_key)
            if resolved is not None:
                payload.setdefault(payload_key, resolved)
    cookies_operation = _normalize_text(arguments.get("cookies_operation"))
    if cookies_operation is None:
        cookies_operation = _normalize_text(arguments.get("operation"))
    if cookies_operation is not None and kind == "cookies":
        payload.setdefault("cookies_operation", cookies_operation)
    if "cookie" in arguments and arguments.get("cookie") is not None and kind == "cookies":
        payload.setdefault("cookie", arguments.get("cookie"))
    storage_kind = _normalize_text(arguments.get("storage_kind"))
    if storage_kind is None:
        storage_kind = _normalize_text(arguments.get("storage"))
    if storage_kind is not None and kind == "storage":
        payload.setdefault("storage_kind", storage_kind)
    storage_operation = _normalize_text(arguments.get("storage_operation"))
    if storage_operation is None:
        storage_operation = _normalize_text(arguments.get("operation"))
    if storage_operation is not None and kind == "storage":
        payload.setdefault("storage_operation", storage_operation)
    storage_key = _normalize_text(arguments.get("storage_key"))
    if storage_key is None:
        storage_key = _normalize_text(arguments.get("key"))
    if storage_key is not None and kind == "storage":
        payload.setdefault("storage_key", storage_key)
    if (
        "storage_value" in arguments
        and arguments.get("storage_value") is not None
        and kind == "storage"
    ):
        payload.setdefault("storage_value", arguments.get("storage_value"))
    if kind in _DEEP_STORAGE_PAGE_ACTION_KINDS:
        for argument_key, payload_key in (
            ("security_origin", "security_origin"),
            ("origin", "origin"),
            ("database_name", "database_name"),
            ("databaseName", "database_name"),
            ("object_store_name", "object_store_name"),
            ("objectStoreName", "object_store_name"),
            ("store", "object_store_name"),
            ("index_name", "index_name"),
            ("indexName", "index_name"),
            ("cache_id", "cache_id"),
            ("cacheId", "cache_id"),
            ("cache_name", "cache_name"),
            ("cacheName", "cache_name"),
            ("cache", "cache_name"),
            ("request_url", "request_url"),
            ("requestURL", "request_url"),
            ("url", "request_url"),
            ("scope_url", "scope_url"),
            ("scopeUrl", "scope_url"),
            ("scope", "scope_url"),
            ("script_url", "script_url"),
            ("scriptUrl", "script_url"),
            ("script", "script_url"),
        ):
            text_value = _normalize_text(arguments.get(argument_key))
            if text_value is not None:
                payload.setdefault(payload_key, text_value)
        if "key" in arguments and arguments.get("key") is not None:
            payload.setdefault("key", arguments.get("key"))
        include_metadata = _normalize_bool(
            arguments.get("include_metadata"),
            label="include_metadata",
        )
        if include_metadata is not None:
            payload.setdefault("include_metadata", include_metadata)
    paths = arguments.get("paths")
    if isinstance(paths, list) and kind == "upload":
        normalized_paths = [candidate for candidate in (_normalize_text(item) for item in paths) if candidate is not None]
        if normalized_paths:
            payload.setdefault("paths", normalized_paths)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_network_action_arguments(
    arguments: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    if kind not in _NETWORK_PAGE_ACTION_KINDS:
        raise BrowserValidationError(f"Unsupported browser network kind '{kind}'.")
    normalized_arguments = dict(arguments)
    normalized_arguments.pop("kind", None)
    payload = _coerce_payload(arguments.get("payload"))
    filters = payload.get("filters")
    if not isinstance(filters, dict):
        filters = {}
    else:
        filters = dict(filters)

    for key in _NETWORK_TEXT_PAYLOAD_ARGUMENTS:
        value = _normalize_text(arguments.get(key))
        if value is not None:
            payload.setdefault(key, value)
    if kind in {"network-fetch-as-page", "network-replay-request"}:
        for key in ("url", "method"):
            value = _normalize_text(arguments.get(key))
            if value is not None:
                payload.setdefault(key, value)
    for key, minimum in _NETWORK_INT_PAYLOAD_ARGUMENTS.items():
        value = _normalize_int(arguments.get(key), label=key, minimum=minimum)
        if value is not None:
            if key in _NETWORK_FILTER_ARGUMENTS:
                filters.setdefault(key, value)
            else:
                payload.setdefault(key, value)
    for key in _NETWORK_BOOL_PAYLOAD_ARGUMENTS:
        value = _normalize_bool(arguments.get(key), label=key)
        if value is not None:
            payload.setdefault(key, value)
    if "headers" in arguments and arguments.get("headers") is not None:
        if not isinstance(arguments["headers"], dict):
            raise BrowserValidationError("headers must be an object.")
        payload.setdefault("headers", dict(arguments["headers"]))
    if "body" in arguments and arguments.get("body") is not None:
        payload.setdefault("body", arguments["body"])
    if "json" in arguments and arguments.get("json") is not None:
        payload.setdefault("json", arguments["json"])
    if kind == "network-list-requests":
        for key in _NETWORK_FILTER_ARGUMENTS:
            if key in _NETWORK_INT_PAYLOAD_ARGUMENTS:
                continue
            value = _normalize_text(arguments.get(key))
            if value is not None:
                filters.setdefault(key, value)
    if filters and kind == "network-list-requests":
        payload["filters"] = filters
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_environment_action_arguments(
    arguments: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    if kind not in _ENVIRONMENT_PAGE_ACTION_KINDS:
        raise BrowserValidationError(f"Unsupported browser environment kind '{kind}'.")
    normalized_arguments = dict(arguments)
    normalized_arguments.pop("kind", None)
    payload = _coerce_payload(arguments.get("payload"))
    text_keys = {
        "user_agent",
        "timezone_id",
        "timezone",
        "locale",
        "origin",
        "connection_type",
    }
    number_keys = {
        "width",
        "height",
        "device_scale_factor",
        "latitude",
        "longitude",
        "accuracy",
        "latency_ms",
        "download_kbps",
        "upload_kbps",
        "download_throughput_bytes_per_second",
        "upload_throughput_bytes_per_second",
    }
    bool_keys = {
        "is_mobile",
        "has_touch",
        "offline",
        "device_metrics",
        "viewport",
        "geolocation",
        "network_conditions",
        "user_agent",
        "timezone",
        "locale",
        "permissions",
    }
    for key in text_keys:
        value = _normalize_text(arguments.get(key))
        if value is not None:
            payload.setdefault(key, value)
    for key in number_keys:
        value = _normalize_number(arguments.get(key), label=key)
        if value is not None:
            payload.setdefault(key, value)
    for key in bool_keys:
        try:
            value = _normalize_bool(arguments.get(key), label=key)
        except BrowserValidationError:
            if key == "permissions":
                continue
            if key in text_keys and isinstance(arguments.get(key), str):
                continue
            raise
        if value is not None:
            payload.setdefault(key, value)
    if "permissions" in arguments and arguments.get("permissions") is not None:
        value = arguments["permissions"]
        payload.setdefault(
            "permissions",
            list(value) if isinstance(value, tuple) else value,
        )
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _normalize_diagnostic_action_arguments(
    arguments: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    if kind not in _DIAGNOSTIC_PAGE_ACTION_KINDS:
        raise BrowserValidationError(f"Unsupported browser diagnostic kind '{kind}'.")
    normalized_arguments = dict(arguments)
    normalized_arguments.pop("kind", None)
    payload = _coerce_payload(arguments.get("payload"))
    for key in ("trace_id", "title"):
        value = _normalize_text(arguments.get(key))
        if value is not None:
            payload.setdefault(key, value)
    for key in ("include_entries", "screenshots", "snapshots", "sources"):
        value = _normalize_bool(arguments.get(key), label=key)
        if value is not None:
            payload.setdefault(key, value)
    limit = _normalize_int(arguments.get("limit"), label="limit", minimum=1)
    if limit is not None:
        payload.setdefault("limit", limit)
    console_limit = _normalize_int(
        arguments.get("console_limit"),
        label="console_limit",
        minimum=1,
    )
    if console_limit is not None:
        payload.setdefault("console_limit", console_limit)
    normalized_arguments["payload"] = payload
    return normalized_arguments


def _resolve_network_tool_kind(
    *,
    tool_id: str,
    fixed_kind: str | None,
    arguments: dict[str, Any],
) -> str:
    kind = fixed_kind or _NETWORK_TOOL_KIND_BY_TOOL_ID.get(tool_id)
    argument_kind = _normalize_text(arguments.get("kind"))
    if kind is None:
        kind = argument_kind
    if kind is None or kind not in _NETWORK_PAGE_ACTION_KINDS:
        supported = ", ".join(sorted(_NETWORK_PAGE_ACTION_KINDS))
        raise BrowserValidationError(f"{tool_id}.kind must be one of {supported}.")
    if argument_kind is not None and argument_kind != kind:
        raise BrowserValidationError(
            f"{tool_id}.kind must match the configured browser network action '{kind}'.",
        )
    return kind


def _resolve_environment_tool_kind(
    *,
    tool_id: str,
    fixed_kind: str | None,
    arguments: dict[str, Any],
) -> str:
    kind = fixed_kind or _ENVIRONMENT_TOOL_KIND_BY_TOOL_ID.get(tool_id)
    argument_kind = _normalize_text(arguments.get("kind"))
    if kind is None:
        kind = argument_kind
    if kind is None or kind not in _ENVIRONMENT_PAGE_ACTION_KINDS:
        supported = ", ".join(sorted(_ENVIRONMENT_PAGE_ACTION_KINDS))
        raise BrowserValidationError(f"{tool_id}.kind must be one of {supported}.")
    if argument_kind is not None and argument_kind != kind:
        raise BrowserValidationError(
            f"{tool_id}.kind must match the configured browser environment action '{kind}'.",
        )
    return kind


def _resolve_diagnostic_tool_kind(
    *,
    tool_id: str,
    fixed_kind: str | None,
    arguments: dict[str, Any],
) -> str:
    kind = fixed_kind or _DIAGNOSTIC_TOOL_KIND_BY_TOOL_ID.get(tool_id)
    argument_kind = _normalize_text(arguments.get("kind"))
    if kind is None:
        kind = argument_kind
    if kind is None or kind not in _DIAGNOSTIC_PAGE_ACTION_KINDS:
        supported = ", ".join(sorted(_DIAGNOSTIC_PAGE_ACTION_KINDS))
        raise BrowserValidationError(f"{tool_id}.kind must be one of {supported}.")
    if argument_kind is not None and argument_kind != kind:
        raise BrowserValidationError(
            f"{tool_id}.kind must match the configured browser diagnostic action '{kind}'.",
        )
    return kind


def _normalize_operation_step_arguments(
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
    if kind in _ENVIRONMENT_PAGE_ACTION_KINDS:
        return _normalize_environment_action_arguments(normalized, kind=kind)
    if kind in _DIAGNOSTIC_PAGE_ACTION_KINDS:
        return _normalize_diagnostic_action_arguments(normalized, kind=kind)
    if kind in _ADVANCED_PAGE_ACTION_KINDS:
        return _normalize_advanced_action_arguments(normalized, kind=kind)
    return normalized


def _normalize_operation_stabilize(value: object, *, label: str) -> str | None:
    if value in (None, ""):
        return None
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    normalized = normalized.lower()
    if normalized not in _OPERATION_STABILIZE_KINDS:
        raise BrowserValidationError(
            f"{label} must be one of auto, navigation, micro, overlay, or none.",
        )
    return normalized


def _normalize_operation_observe_after(value: object, *, label: str) -> str | None:
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
    if normalized not in _OPERATION_OBSERVE_AFTER_KINDS:
        raise BrowserValidationError(
            f"{label} must be one of auto, interactive, role, aria, or none.",
        )
    return normalized


def _coerce_operation_observe_payload(value: object, *, label: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise BrowserValidationError(f"{label} must decode to an object.")
    return dict(value)


def _resolve_operation_stabilize_mode(
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


def _resolve_operation_observe_mode(raw_mode: str | None) -> str:
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


def _run_operation_stabilize(
    *,
    deps: BrowserToolDeps,
    profile_name: str,
    allocation_id: str | None = None,
    execution_context: ToolExecutionContext | None = None,
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
        wait_payload = {"time_ms": _OPERATION_OVERLAY_STABILIZE_MS}
    else:
        wait_payload = {"time_ms": _OPERATION_MICRO_STABILIZE_MS}
    followup_arguments = {
        "target_id": target_id,
        "timeout_ms": stabilize_timeout_ms,
        "payload": wait_payload,
    }
    followup_context = _execution_context_with_browser_allocation(
        execution_context,
        allocation_id,
    )
    if allocation_id is None:
        followup_arguments["profile"] = profile_name
    result, _, _ = _run_page_action_content(
        deps=deps,
        kind="wait",
        arguments=followup_arguments,
        execution_context=followup_context,
    )
    return result


def _run_operation_observe_after(
    *,
    deps: BrowserToolDeps,
    profile_name: str,
    allocation_id: str | None = None,
    execution_context: ToolExecutionContext | None = None,
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
    followup_arguments = {
        "target_id": target_id,
        "timeout_ms": timeout_ms,
        "payload": payload,
    }
    followup_context = _execution_context_with_browser_allocation(
        execution_context,
        allocation_id,
    )
    if allocation_id is None:
        followup_arguments["profile"] = profile_name
    result, _, _ = _run_page_action_content(
        deps=deps,
        kind="snapshot",
        arguments=followup_arguments,
        execution_context=followup_context,
    )
    return result


def _execution_context_with_browser_allocation(
    execution_context: ToolExecutionContext | None,
    allocation_id: str | None,
) -> ToolExecutionContext | None:
    normalized_allocation_id = _normalize_text(allocation_id)
    if normalized_allocation_id is None:
        return execution_context
    attrs = execution_context.to_payload() if execution_context is not None else {}
    attrs["browser_allocation_id"] = normalized_allocation_id
    return ToolExecutionContext(attrs=attrs)


def _merge_tool_result_post_state(
    *,
    deps: BrowserToolDeps,
    result: ToolRunResult,
    post_state_result: Any,
) -> ToolRunResult:
    post_state_blocks = _browser_content_blocks(deps, post_state_result)
    if not post_state_blocks:
        return result
    metadata = dict(result.metadata)
    metadata["post_state_summary"] = _browser_result_summary(post_state_result)
    return ToolRunResult.structured(
        content=[*result.blocks, *[dict(block) for block in post_state_blocks]],
        details=result.details,
        metadata=metadata,
    )


def _single_step_operation_defaults(*, family: str, kind: str) -> dict[str, Any]:
    return {}


def _strip_single_step_composite_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments)
    normalized.pop("stabilize", None)
    normalized.pop("stabilize_timeout_ms", None)
    normalized.pop("observe_after", None)
    normalized.pop("observe_payload", None)
    return normalized


def _single_step_operation_overrides(arguments: dict[str, Any]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    stabilize = _normalize_operation_stabilize(arguments.get("stabilize"), label="stabilize")
    if stabilize is not None:
        overrides["default_stabilize"] = stabilize
    stabilize_timeout_ms = _normalize_int(
        arguments.get("stabilize_timeout_ms"),
        label="stabilize_timeout_ms",
        minimum=1,
    )
    if stabilize_timeout_ms is not None:
        overrides["default_stabilize_timeout_ms"] = stabilize_timeout_ms
    observe_after = _normalize_operation_observe_after(
        arguments.get("observe_after"),
        label="observe_after",
    )
    if observe_after is not None:
        overrides["default_observe_after"] = observe_after
    observe_payload = _coerce_operation_observe_payload(
        arguments.get("observe_payload"),
        label="observe_payload",
    )
    if observe_payload:
        overrides["default_observe_payload"] = observe_payload
    return overrides


def _single_step_operation_arguments(
    *,
    family: str,
    kind: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    step_arguments = _strip_single_step_composite_arguments(arguments)
    return {
        **_single_step_operation_defaults(
            family=family,
            kind=kind,
        ),
        **_single_step_operation_overrides(arguments),
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


def _execute_operation(
    *,
    deps: BrowserToolDeps,
    tool_id: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    _ensure_browser_enabled(deps.settings)
    steps = _coerce_operation_steps(arguments.get("steps"))
    if len(steps) != 1:
        raise BrowserValidationError("browser operation accepts exactly one step.")
    current_target_id = _normalize_browser_target_id(arguments.get("target_id"))
    inherited_profile_name = _normalize_text(arguments.get("profile"))
    inherited_timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    default_stabilize = _normalize_operation_stabilize(
        arguments.get("default_stabilize"),
        label="default_stabilize",
    )
    default_stabilize_timeout_ms = _normalize_int(
        arguments.get("default_stabilize_timeout_ms"),
        label="default_stabilize_timeout_ms",
        minimum=1,
    )
    default_observe_after = _normalize_operation_observe_after(
        arguments.get("default_observe_after"),
        label="default_observe_after",
    )
    default_observe_payload = _coerce_operation_observe_payload(
        arguments.get("default_observe_payload"),
        label="default_observe_payload",
    )
    raw_step = steps[0]
    kind = _normalize_text(raw_step.get("kind"))
    if kind is None:
        raise BrowserValidationError("browser operation step kind is required.")
    family = _resolve_family(kind.lower(), _normalize_text(raw_step.get("family")))
    normalized_kind = kind.lower()
    step_arguments = dict(raw_step)
    step_arguments = _operation_step_defaults(
        step_arguments=step_arguments,
        profile_name=inherited_profile_name,
        timeout_ms=inherited_timeout_ms,
    )
    step_arguments = _normalize_operation_step_arguments(
        family=family,
        kind=normalized_kind,
        step_arguments=step_arguments,
    )
    step_arguments = _operation_step_target_id(
        family=family,
        kind=normalized_kind,
        step_arguments=step_arguments,
        current_target_id=current_target_id,
    )
    step_stabilize = _normalize_operation_stabilize(
        raw_step.get("stabilize"),
        label="step.stabilize",
    )
    step_stabilize_timeout_ms = _normalize_int(
        raw_step.get("stabilize_timeout_ms"),
        label="step.stabilize_timeout_ms",
        minimum=1,
    )
    step_observe_after = _normalize_operation_observe_after(
        raw_step.get("observe_after"),
        label="step.observe_after",
    )
    step_observe_payload = _coerce_operation_observe_payload(
        raw_step.get("observe_payload"),
        label="step.observe_payload",
    )
    if family == "control":
        content, resolved_profile, runtime_metadata = _run_control_content(
            deps=deps,
            kind=normalized_kind,
            arguments=step_arguments,
            execution_context=execution_context,
        )
        result = _tool_result(
            deps=deps,
            tool_id=tool_id,
            content=content,
            family="control",
            profile_name=resolved_profile,
            profile_source=runtime_metadata.get(
                "profile_source",
                _profile_source(step_arguments, execution_context),
            ),
            runtime_metadata=runtime_metadata,
            kind=normalized_kind,
            execution_context=execution_context,
        )
    else:
        content, resolved_profile, runtime_metadata = _run_page_action_content(
            deps=deps,
            kind=normalized_kind,
            arguments=step_arguments,
            execution_context=execution_context,
        )
        result = _tool_result(
            deps=deps,
            tool_id=tool_id,
            content=content,
            family="page-action",
            profile_name=resolved_profile,
            profile_source=runtime_metadata.get(
                "profile_source",
                _profile_source(step_arguments, execution_context),
            ),
            runtime_metadata=runtime_metadata,
            kind=normalized_kind,
            execution_context=execution_context,
        )
    current_target_id = _extract_browser_target_id(content) or current_target_id
    effective_stabilize = _resolve_operation_stabilize_mode(
        family=family,
        kind=normalized_kind,
        raw_mode=step_stabilize or default_stabilize,
    )
    effective_stabilize_timeout_ms = (
        step_stabilize_timeout_ms
        or default_stabilize_timeout_ms
        or inherited_timeout_ms
    )
    _run_operation_stabilize(
        deps=deps,
        profile_name=resolved_profile,
        allocation_id=_normalize_text(runtime_metadata.get("browser_allocation_id")),
        execution_context=execution_context,
        target_id=current_target_id,
        stabilize_mode=effective_stabilize,
        stabilize_timeout_ms=effective_stabilize_timeout_ms,
    )
    inherited_observe_after = default_observe_after
    if family == "control" and step_observe_after is None:
        inherited_observe_after = None
    effective_observe_after = _resolve_operation_observe_mode(
        step_observe_after or inherited_observe_after,
    )
    effective_observe_payload = (
        dict(step_observe_payload)
        if step_observe_payload
        else dict(default_observe_payload)
    )
    post_state_result = _run_operation_observe_after(
        deps=deps,
        profile_name=resolved_profile,
        allocation_id=_normalize_text(runtime_metadata.get("browser_allocation_id")),
        execution_context=execution_context,
        target_id=current_target_id,
        observe_mode=effective_observe_after,
        observe_payload=effective_observe_payload,
        timeout_ms=inherited_timeout_ms,
    )
    if post_state_result is None:
        return result
    return _merge_tool_result_post_state(
        deps=deps,
        result=result,
        post_state_result=post_state_result,
    )


def create_browser_control_handler(
    factory_deps: BrowserToolDeps | Any,
    *,
    tool_id: str = "browser.control",
):
    deps = _coerce_tool_deps(factory_deps)
    if deps is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        kind = _normalize_text(arguments.get("kind"))
        if kind is None or kind.lower() not in _CONTROL_KINDS:
            raise BrowserValidationError(
                f"{tool_id}.kind must be one of status, start, stop, open-tab, list-tabs, navigate, focus-tab, close-tab, reset.",
            )
        return await asyncio.to_thread(
            _execute_operation,
            deps=deps,
            tool_id=tool_id,
            arguments=_single_step_operation_arguments(
                family="control",
                kind=kind.lower(),
                arguments=arguments,
            ),
            execution_context=execution_context,
        )

    return _handler


def create_browser_snapshot_handler(
    factory_deps: BrowserToolDeps | Any,
    *,
    tool_id: str = "browser.snapshot",
):
    deps = _coerce_tool_deps(factory_deps)
    if deps is None:
        return None

    async def _handler(
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
            _execute_operation,
            deps=deps,
            tool_id=tool_id,
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
        )

    return _handler


def create_browser_page_action_handler(
    factory_deps: BrowserToolDeps | Any,
    *,
    tool_id: str = "browser.action",
):
    deps = _coerce_tool_deps(factory_deps)
    if deps is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        kind = _normalize_text(arguments.get("kind"))
        if kind is None or kind.lower() not in _ACTION_TOOL_PAGE_ACTION_KINDS:
            raise BrowserValidationError(
                f"{tool_id}.kind must be one of click, console, cookies, dialog, fill, upload, download, wait-download, wait, batch, type, press, hover, drag, resize, scroll-into-view, select, screenshot, pdf, evaluate, storage, browser.dom.*, browser.storage.*, browser.service_worker.*, or browser environment actions.",
            )
        normalized_arguments = _normalize_operation_step_arguments(
            family="page-action",
            kind=kind.lower(),
            step_arguments=dict(arguments),
        )
        return await asyncio.to_thread(
            _execute_operation,
            deps=deps,
            tool_id=tool_id,
            arguments=_single_step_operation_arguments(
                family="page-action",
                kind=kind.lower(),
                arguments=normalized_arguments,
            ),
            execution_context=execution_context,
        )

    return _handler


def create_browser_network_handler(
    factory_deps: BrowserToolDeps | Any,
    *,
    tool_id: str = "browser.network",
    kind: str | None = None,
):
    deps = _coerce_tool_deps(factory_deps)
    if deps is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        network_kind = _resolve_network_tool_kind(
            tool_id=tool_id,
            fixed_kind=kind,
            arguments=arguments,
        )
        normalized_arguments = _normalize_network_action_arguments(
            arguments,
            kind=network_kind,
        )
        return await asyncio.to_thread(
            _execute_operation,
            deps=deps,
            tool_id=tool_id,
            arguments=_single_step_operation_arguments(
                family="page-action",
                kind=network_kind,
                arguments=normalized_arguments,
            ),
            execution_context=execution_context,
        )

    return _handler


def create_browser_context_handler(
    factory_deps: BrowserToolDeps | Any,
    *,
    tool_id: str = "browser.context",
    action: str | None = None,
):
    deps = _coerce_tool_deps(factory_deps)
    if deps is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        context_action = _normalize_text(arguments.get("action")) or action
        if context_action is None:
            raise BrowserValidationError(
                "browser.context action must be one of acquire, current, heartbeat, release, reconcile.",
            )
        return await asyncio.to_thread(
            _execute_context,
            deps=deps,
            tool_id=tool_id,
            action=context_action,
            arguments=dict(arguments),
            execution_context=execution_context,
        )

    return _handler
