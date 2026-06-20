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
        "network-inspect",
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
_CODE_PAGE_ACTION_KINDS = frozenset(
    {
        "runtime-inspect",
        "script-list",
        "script-find-request",
        "code-search",
        "script-inspect",
        "script-extract-request",
    }
)
_LOCAL_PAGE_ACTION_KINDS = (
    (_PAGE_ACTION_KINDS - {"cdp-raw"})
    | _NETWORK_PAGE_ACTION_KINDS
    | _DEEP_STORAGE_PAGE_ACTION_KINDS
    | _DOM_PAGE_ACTION_KINDS
    | _ENVIRONMENT_PAGE_ACTION_KINDS
    | _DIAGNOSTIC_PAGE_ACTION_KINDS
    | _CODE_PAGE_ACTION_KINDS
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
        "action-trace",
        "runtime-inspect",
        "script-list",
        "script-find-request",
        "code-search",
        "script-inspect",
        "script-extract-request",
    }
)
_NETWORK_TOOL_KIND_BY_TOOL_ID = {
    "browser.network.inspect": "network-inspect",
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
        "include_body",
        "redact",
        "allow_cross_origin",
        "allow_mutating",
    }
)
_NETWORK_TOP_LEVEL_BODY_PREVIEW_LIMIT = 1200
_SCRIPT_TOP_LEVEL_PREVIEW_LIMIT = 4000
_BROWSER_DETAILS_MAX_CHARS = 120_000
_BROWSER_DETAILS_COMPACT_STRING_LIMIT = 2000
_BROWSER_DETAILS_COMPACT_LIST_LIMIT = 40
_BROWSER_DETAILS_COMPACT_DICT_LIMIT = 80
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
    browser_observation_service: Any | None = None
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
    details = _browser_result_details(content)
    browser_runtime_metadata = _coerce_browser_runtime_metadata(runtime_metadata)
    browser_audit_metadata = _browser_audit_metadata(content, content_blocks)
    browser_evidence = _browser_evidence_metadata(
        tool_id=tool_id,
        family=family,
        kind=kind,
        profile_name=profile_name,
        profile_source=profile_source,
        content=content,
        details=details,
        runtime_metadata=browser_runtime_metadata,
    )
    metadata = {
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
    }
    if browser_evidence:
        metadata["browser_evidence"] = browser_evidence
    return ToolRunResult.structured(
        details=details,
        content=[dict(block) for block in content_blocks],
        metadata=metadata,
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


def _browser_evidence_metadata(
    *,
    tool_id: str,
    family: str | None,
    kind: str | None,
    profile_name: str | None,
    profile_source: str | None,
    content: Any,
    details: Any,
    runtime_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"tool": tool_id}
    for key, value in (
        ("family", family),
        ("kind", kind),
        ("profile", profile_name),
        ("profile_source", profile_source),
    ):
        normalized = _normalize_text(value)
        if normalized is not None:
            evidence[key] = normalized

    target_url = _browser_target_url_from_content(content)
    if target_url is not None:
        safe_url = _safe_browser_url_metadata(target_url)
        url = _normalize_text(safe_url.get("browser_target_url"))
        origin = _normalize_text(safe_url.get("browser_target_origin"))
        if url is not None:
            evidence["url"] = url
        if origin is not None:
            evidence["origin"] = origin

    scalar_sources = (details, content, runtime_metadata)
    for fact_key, source_keys in (
        ("title", ("title", "page_title")),
        ("target_id", ("target_id", "targetId", "browser_target_id")),
        ("allocation_id", ("browser_allocation_id", "browser_context_lease_id")),
        ("host_service_key", ("browser_host_service_key",)),
        ("endpoint", ("endpoint", "api_endpoint", "request_url", "path")),
        ("method", ("method", "request_method")),
        ("http_status", ("status_code", "http_status", "response_status")),
        ("request_id", ("request_id", "requestId")),
        ("body_ref", ("body_ref", "response_body_ref")),
        ("request_body_ref", ("request_body_ref",)),
        ("verified_selector", ("verified_selector", "matched_selector", "selector")),
        ("verified_ref", ("verified_ref", "target_ref", "element_ref", "ref")),
    ):
        if fact_key in evidence:
            continue
        value = _browser_evidence_first_scalar(scalar_sources, source_keys)
        if value is not None:
            evidence[fact_key] = _truncate_text(value, 180)

    if "target_id" not in evidence:
        target_id = _extract_browser_target_id(content)
        if target_id is not None:
            evidence["target_id"] = target_id

    payload_shape_source = _browser_evidence_first_value(
        (details, content),
        (
            "request_payload",
            "requestPayload",
            "request_body",
            "requestBody",
            "post_data",
            "postData",
            "payload",
            "arguments",
        ),
    )
    payload_shape = _browser_evidence_shape(payload_shape_source)
    if payload_shape is not None:
        evidence["payload_shape"] = payload_shape

    result_shape_source = _browser_evidence_first_value(
        (details, content),
        (
            "result_shape",
            "response_shape",
            "result",
            "response",
            "data",
            "value",
            "body",
        ),
    )
    result_shape = _browser_evidence_shape(result_shape_source)
    if result_shape is not None:
        evidence["result_shape"] = result_shape

    runtime_globals = _browser_evidence_runtime_globals((details, content))
    if runtime_globals:
        evidence["runtime_globals"] = runtime_globals

    evidence.update(
        _browser_action_evidence(
            content=content,
            details=details,
            kind=kind,
        ),
    )
    evidence.update(
        _browser_network_replay_evidence(
            content=content,
            details=details,
        ),
    )
    evidence.update(
        _browser_script_insight_evidence(
            content=content,
            details=details,
        ),
    )

    return {
        key: value
        for key, value in evidence.items()
        if value is not None and value != "" and value != [] and value != {}
    }

def _browser_action_evidence(
    *,
    content: Any,
    details: Any,
    kind: str | None,
) -> dict[str, Any]:
    action = _browser_evidence_first_mapping((details, content), ("action",))
    command = _browser_evidence_first_mapping((content, details), ("command",))
    result = _browser_evidence_first_mapping((details, content), ("result",))
    target = _browser_evidence_first_mapping((command, action, result), ("target",))
    action_kind = (
        _browser_evidence_first_scalar((action,), ("kind", "action_kind"))
        or _browser_evidence_first_scalar((command,), ("kind",))
        or _normalize_text(kind)
    )
    if action_kind is None:
        return {}
    if not _is_browser_interaction_kind(action_kind):
        return {}
    evidence: dict[str, Any] = {"action_kind": _truncate_text(action_kind, 80)}
    action_ok = _browser_evidence_first_value((action, result), ("ok", "success"))
    if isinstance(action_ok, bool):
        evidence["action_ok"] = action_ok
    for fact_key, sources, source_keys in (
        (
            "verified_selector",
            (action, result, target, command),
            ("resolved_selector", "verified_selector", "matched_selector", "selector"),
        ),
        (
            "verified_ref",
            (action, result, target, command),
            ("resolved_ref", "verified_ref", "target_ref", "element_ref", "ref"),
        ),
        (
            "field_name",
            (action, result, target, command),
            ("field_name", "field", "name", "input_name"),
        ),
        (
            "field_label",
            (action, result, target, command),
            ("field_label", "label", "aria_label"),
        ),
    ):
        if fact_key in evidence:
            continue
        value = _browser_evidence_first_scalar(sources, source_keys)
        if value is not None:
            evidence[fact_key] = _truncate_text(value, 180)
    return evidence


def _browser_network_replay_evidence(
    *,
    content: Any,
    details: Any,
) -> dict[str, Any]:
    result = _browser_network_like_result(content, details)
    if not result:
        return {}
    kind = _normalize_text(result.get("kind"))
    if kind != "network-replay-request" and "request_diff" not in result:
        return {}
    evidence: dict[str, Any] = {}
    for fact_key, source_keys in (
        ("source_request_id", ("source_request_id",)),
        ("source_capture_id", ("source_capture_id",)),
    ):
        value = _browser_evidence_first_scalar((result,), source_keys)
        if value is not None:
            evidence[fact_key] = _truncate_text(value, 180)
    diff = result.get("request_diff")
    if isinstance(diff, dict):
        changed_fields = diff.get("changed_fields")
        if isinstance(changed_fields, list):
            fields = [
                _truncate_text(value, 80)
                for value in (_normalize_text(item) for item in changed_fields)
                if value is not None
            ]
            if fields:
                evidence["request_diff_changed_fields"] = list(dict.fromkeys(fields))[:12]
        body_source = _normalize_text(diff.get("body_source"))
        if body_source is not None:
            evidence["request_diff_body_source"] = _truncate_text(body_source, 80)
        source = diff.get("source")
        if isinstance(source, dict):
            body = source.get("body")
            if isinstance(body, dict):
                state = _normalize_text(body.get("state"))
                if state is not None:
                    evidence["source_body_state"] = _truncate_text(state, 80)
    response = result.get("response_summary")
    if isinstance(response, dict):
        evidence["response_summary"] = _small_browser_summary(
            response,
            keys=("ok", "status", "mime_type", "size_bytes", "truncated", "redacted"),
        )
    return evidence


def _browser_script_insight_evidence(
    *,
    content: Any,
    details: Any,
) -> dict[str, Any]:
    causality = _browser_evidence_first_mapping(
        (details, content),
        ("causality", "network_causality"),
    )
    evidence: dict[str, Any] = {}
    if causality:
        script_frames = _script_frame_evidence(causality.get("script_frames"))
        if script_frames:
            evidence["script_frames"] = script_frames
        api_candidates = _api_candidate_evidence(causality.get("api_candidates"))
        if api_candidates:
            evidence["api_candidates"] = api_candidates
    client_path = _browser_evidence_first_scalar(
        (details, content),
        ("api_client_path", "client_path", "script_path", "discovered_client_path"),
    )
    if client_path is not None:
        evidence["api_client_path"] = _truncate_text(client_path, 180)
    return evidence


def _browser_evidence_first_mapping(
    sources: tuple[Any, ...],
    keys: tuple[str, ...],
) -> dict[str, Any]:
    value = _browser_evidence_first_value(sources, keys)
    return value if isinstance(value, dict) else {}


def _browser_network_like_result(content: Any, details: Any) -> dict[str, Any]:
    for source in (details, content):
        if not isinstance(source, dict):
            continue
        kind = _normalize_text(source.get("kind"))
        if kind and kind.startswith("network-"):
            return source
        result = _browser_evidence_first_mapping((source,), ("result",))
        result_kind = _normalize_text(result.get("kind"))
        if result_kind and result_kind.startswith("network-"):
            return result
        if "request_diff" in source:
            return source
        if "request_diff" in result:
            return result
    return {}


def _is_browser_interaction_kind(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {
        "action-trace",
        "click",
        "type",
        "press",
        "select",
        "hover",
        "drag",
        "upload",
        "download",
        "scroll-into-view",
        "dom-clickability",
        "dom-highlight",
        "dom-mutation-wait",
    }


def _script_frame_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    frames: list[dict[str, Any]] = []
    for item in value[:6]:
        if not isinstance(item, dict):
            continue
        frame = _small_browser_summary(
            item,
            keys=("request_id", "function_name", "line_number", "column_number"),
        )
        script_url = _safe_evidence_url(_normalize_text(item.get("script_url")))
        if script_url is not None:
            frame["script_url"] = script_url
        request_url = _safe_evidence_url(_normalize_text(item.get("url")))
        if request_url is not None:
            frame["url"] = request_url
        if frame:
            frames.append(frame)
    return frames


def _api_candidate_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        candidate = _small_browser_summary(
            item,
            keys=("request_id", "method", "status", "resource_type"),
        )
        url = _safe_evidence_url(_normalize_text(item.get("url")))
        if url is not None:
            candidate["url"] = url
        initiator = item.get("initiator")
        if isinstance(initiator, dict):
            initiator_type = _normalize_text(initiator.get("type"))
            if initiator_type is not None:
                candidate["initiator_type"] = _truncate_text(initiator_type, 80)
            script_url = _safe_evidence_url(_normalize_text(initiator.get("script_url")))
            if script_url is not None:
                candidate["initiator_script_url"] = script_url
        if candidate:
            candidates.append(candidate)
    return candidates


def _small_browser_summary(
    value: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in keys:
        item = value.get(key)
        if isinstance(item, bool):
            summary[key] = item
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            summary[key] = item
        else:
            normalized = _normalize_text(item)
            if normalized is not None:
                summary[key] = _truncate_text(normalized, 180)
    return summary


def _safe_evidence_url(value: str | None) -> str | None:
    if value is None:
        return None
    safe = _safe_browser_url_metadata(value)
    return _normalize_text(safe.get("browser_target_url"))


def _browser_evidence_first_scalar(
    sources: tuple[Any, ...],
    keys: tuple[str, ...],
) -> str | None:
    for source in sources:
        value = _browser_evidence_find_first_value(source, keys, seen=set())
        if not isinstance(value, (str, int, float, bool)):
            continue
        normalized = _normalize_text(value)
        if normalized is not None:
            return normalized
    return None


def _browser_evidence_first_value(
    sources: tuple[Any, ...],
    keys: tuple[str, ...],
) -> Any:
    for source in sources:
        value = _browser_evidence_find_first_value(source, keys, seen=set())
        if value is not None:
            return value
    return None


def _browser_evidence_find_first_value(
    value: Any,
    keys: tuple[str, ...],
    *,
    seen: set[int],
) -> Any:
    if isinstance(value, dict):
        marker = id(value)
        if marker in seen:
            return None
        seen.add(marker)
        normalized = {str(key): item for key, item in value.items()}
        for key in keys:
            if key in normalized:
                return normalized[key]
        for item in normalized.values():
            found = _browser_evidence_find_first_value(item, keys, seen=seen)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        marker = id(value)
        if marker in seen:
            return None
        seen.add(marker)
        for item in value:
            found = _browser_evidence_find_first_value(item, keys, seen=seen)
            if found is not None:
                return found
    return None


def _browser_evidence_shape(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> Any:
    if value is None:
        return None
    if seen is None:
        seen = set()
    if isinstance(value, str):
        parsed = _browser_evidence_parse_json_preview(value)
        if parsed is not None:
            return _browser_evidence_shape(parsed, depth=depth, seen=seen)
        return f"str({len(value)})" if len(value) > 80 else "str"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, dict):
        marker = id(value)
        if marker in seen:
            return {"type": "object", "cycle": True}
        seen.add(marker)
        if depth >= 3:
            return {"type": "object", "keys": len(value)}
        shaped: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 12:
                shaped["_truncated_keys"] = max(len(value) - 12, 0)
                break
            shaped[str(key)] = _browser_evidence_shape(
                item,
                depth=depth + 1,
                seen=seen,
            )
        return shaped
    if isinstance(value, list):
        marker = id(value)
        if marker in seen:
            return {"type": "list", "cycle": True}
        seen.add(marker)
        item_shape = None
        for item in value:
            if item is not None:
                item_shape = _browser_evidence_shape(item, depth=depth + 1, seen=seen)
                break
        return {"type": "list", "count": len(value), "item": item_shape}
    return type(value).__name__


def _browser_evidence_parse_json_preview(value: str) -> Any:
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    if len(text.encode("utf-8")) > 200_000:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _browser_evidence_runtime_globals(sources: tuple[Any, ...]) -> list[str]:
    value = _browser_evidence_first_value(
        sources,
        (
            "runtime_globals",
            "global_names",
            "globals",
            "window_keys",
            "windowGlobals",
        ),
    )
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        normalized = _normalize_text(item)
        if normalized is None:
            continue
        names.append(_truncate_text(normalized, 80))
        if len(names) >= 16:
            break
    return list(dict.fromkeys(names))


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
    observe_blocks = _browser_observe_blocks(content)
    if observe_blocks:
        return observe_blocks
    batch_blocks = _browser_batch_blocks(content)
    if batch_blocks:
        return batch_blocks
    action_trace_blocks = _browser_action_trace_blocks(deps, content)
    if action_trace_blocks:
        return action_trace_blocks
    action_envelope_blocks = _browser_action_envelope_blocks(content)
    if action_envelope_blocks:
        return action_envelope_blocks
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
    network_blocks = _browser_network_blocks(deps, content)
    if network_blocks:
        return network_blocks
    code_blocks = _browser_code_blocks(deps, content)
    if code_blocks:
        return code_blocks
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


def _browser_batch_summary(content: Any) -> str | None:
    result = _find_browser_batch_result_payload(content)
    if result is None:
        return None
    raw_results = result.get("results")
    actions = raw_results if isinstance(raw_results, list) else []
    total = len(actions)
    failed = sum(
        1
        for item in actions
        if isinstance(item, dict) and item.get("ok") is False
    )
    if total == 0:
        return "Browser native run completed with no reported step results."
    if failed:
        return f"Browser native run completed {total} step(s) with {failed} failure(s)."
    return f"Browser native run completed {total} step(s)."


def _browser_batch_blocks(content: Any) -> list[dict[str, Any]]:
    result = _find_browser_batch_result_payload(content)
    if result is None:
        return []
    lines = [_browser_batch_summary(content) or "Browser native run completed."]
    stop_on_error = result.get("stop_on_error")
    if isinstance(stop_on_error, bool):
        lines.append(f"- Stop on error: {str(stop_on_error).lower()}")
    raw_results = result.get("results")
    if isinstance(raw_results, list) and raw_results:
        lines.append("- Steps:")
        for index, item in enumerate(raw_results[:20], start=1):
            if not isinstance(item, dict):
                continue
            kind = _normalize_text(item.get("kind")) or "action"
            ok = item.get("ok")
            status = "ok" if ok is not False else "failed"
            line = f"  {index}. {kind}: {status}"
            error = _normalize_text(item.get("error"))
            if error is not None:
                line = f"{line} ({error})"
            lines.append(line)
        if len(raw_results) > 20:
            lines.append(f"  ... {len(raw_results) - 20} more step(s)")
    return [text_content_block("\n".join(lines))]


def _find_browser_batch_result_payload(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    value = content.get("value")
    if isinstance(value, dict):
        if _normalize_text(value.get("kind")) == "batch":
            return value
        result = value.get("result")
        if isinstance(result, dict) and _normalize_text(result.get("kind")) == "batch":
            return result
    if command_kind == "batch":
        result = content.get("result")
        if isinstance(result, dict) and _normalize_text(result.get("kind")) == "batch":
            return result
    return None


def _browser_result_summary(content: Any) -> str | None:
    return _browser_result_summary_inner(content, seen=set())


def _browser_result_summary_inner(content: Any, *, seen: set[int]) -> str | None:
    if not isinstance(content, dict):
        return _normalize_text(content)
    marker = id(content)
    if marker in seen:
        return None
    seen.add(marker)
    observe_summary = _browser_observe_summary(content)
    if observe_summary is not None:
        return observe_summary
    batch_summary = _browser_batch_summary(content)
    if batch_summary is not None:
        return batch_summary
    action_trace_summary = _browser_action_trace_summary(content)
    if action_trace_summary is not None:
        return action_trace_summary
    action_envelope_summary = _browser_action_envelope_summary(content)
    if action_envelope_summary is not None:
        return action_envelope_summary
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
    code_summary = _browser_code_summary(content)
    if code_summary is not None:
        return code_summary
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


def _browser_action_envelope_summary(content: Any) -> str | None:
    envelope = _find_browser_action_envelope(content)
    if envelope is None:
        return None
    kind = _normalize_text(envelope.get("kind")) or "action"
    return f"Browser {kind} completed; {_browser_action_effect_label(envelope)}."


def _browser_action_envelope_blocks(content: Any) -> list[dict[str, Any]]:
    envelope = _find_browser_action_envelope(content)
    if envelope is None:
        return []
    return [text_content_block(_format_browser_action_envelope(envelope))]


def _find_browser_action_envelope(content: Any) -> dict[str, Any] | None:
    return _find_browser_action_envelope_inner(content, seen=set())


def _find_browser_action_envelope_inner(
    content: Any,
    *,
    seen: set[int],
) -> dict[str, Any] | None:
    if isinstance(content, dict):
        marker = id(content)
        if marker in seen:
            return None
        seen.add(marker)
        envelope = content.get("action_envelope")
        if isinstance(envelope, dict):
            return envelope
        for key in ("value", "result", "output_payload"):
            nested = content.get(key)
            found = _find_browser_action_envelope_inner(nested, seen=seen)
            if found is not None:
                return found
        return None
    if isinstance(content, list):
        marker = id(content)
        if marker in seen:
            return None
        seen.add(marker)
        for item in content:
            found = _find_browser_action_envelope_inner(item, seen=seen)
            if found is not None:
                return found
    return None


def _format_browser_action_envelope(envelope: dict[str, Any]) -> str:
    kind = _normalize_text(envelope.get("kind")) or "action"
    lines = [f"Browser {kind} completed."]
    tool_ok = envelope.get("tool_ok")
    if isinstance(tool_ok, bool):
        lines.append(f"- Tool: {'ok' if tool_ok else 'failed'}")
    else:
        lines.append("- Tool: unknown")
    lines.append(f"- Page effect: {_browser_action_effect_label(envelope)}")

    before_text = _format_browser_action_state(envelope.get("before"))
    if before_text is not None:
        lines.append(f"- Before: {before_text}")
    after_text = _format_browser_action_state(envelope.get("after"))
    if after_text is not None:
        lines.append(f"- After: {after_text}")

    changes = envelope.get("changes")
    if isinstance(changes, dict) and changes:
        changed_keys = ", ".join(str(key) for key in list(changes)[:6])
        if changed_keys:
            lines.append(f"- Changes: {changed_keys}")

    errors = envelope.get("errors")
    if isinstance(errors, list) and errors:
        error_text = "; ".join(str(item) for item in errors[:3])
        lines.append(f"- Errors: {error_text}")

    next_action = _format_browser_action_next(envelope.get("next_action"))
    if next_action is not None:
        lines.append(f"- Next: {next_action}")
    if kind == "evaluate" and "result" in envelope:
        lines.append("")
        lines.append(_format_browser_evaluate_result(envelope.get("result")))
    return "\n".join(lines)


def _browser_action_effect_label(envelope: dict[str, Any]) -> str:
    status = _normalize_text(envelope.get("page_effect_status"))
    if status == "action_failed_with_observed_effect":
        return "observed change (action reported failure)"
    page_effect_ok = envelope.get("page_effect_ok")
    if page_effect_ok is True:
        return "observed change"
    if page_effect_ok is False:
        return "no observable change"
    return status.replace("_", " ") if status is not None else "unknown"


def _format_browser_action_state(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    for label, key in (
        ("target", "target_id"),
        ("url", "url"),
        ("title", "title"),
        ("type", "type"),
    ):
        text = _normalize_text(value.get(key))
        if text is not None:
            parts.append(f"{label}={text}")
    if not parts:
        return None
    return ", ".join(parts)


def _format_browser_action_next(value: Any) -> str | None:
    next_action = _normalize_text(value)
    if next_action is None:
        return None
    if next_action == "observe-current-state":
        return "use browser.observe or browser.snapshot to inspect the current page state"
    if next_action == "use-action-trace-or-observe":
        return "use browser.action.trace or browser.observe to verify the next step"
    return next_action.replace("_", " ")


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
    event_line = _format_browser_event_summary(result.get("event_summary"))
    if event_line is not None:
        lines.append(f"- Event handlers: {event_line}")
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


def _format_browser_event_summary(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    parts: list[str] = []
    for label, key in (
        ("inline", "inline_handlers"),
        ("property", "property_handlers"),
        ("listener", "listener_types"),
    ):
        raw_items = value.get(key)
        if not isinstance(raw_items, list):
            continue
        items = [
            item
            for item in (_normalize_text(entry) for entry in raw_items[:8])
            if item is not None
        ]
        if items:
            parts.append(f"{label}: {', '.join(items)}")
    if not parts:
        return None
    return "; ".join(parts)


def _browser_code_summary(content: dict[str, Any]) -> str | None:
    found = _find_browser_code_result_payload(content)
    if found is None:
        return None
    kind, result = found
    if kind == "runtime-inspect":
        title = _normalize_text(result.get("title")) or "page"
        frameworks = result.get("frameworks")
        detected = frameworks.get("detected") if isinstance(frameworks, dict) else None
        detected_count = len(detected) if isinstance(detected, list) else 0
        return f"Browser runtime inspected {title}; detected {detected_count} framework signal(s)."
    if kind == "script-list":
        returned_scripts = (
            _normalize_int(result.get("returned_scripts"), label="returned_scripts", minimum=0)
            or 0
        )
        matched_scripts = (
            _normalize_int(result.get("matched_scripts"), label="matched_scripts", minimum=0)
            or returned_scripts
        )
        return (
            "Browser script list returned "
            f"{returned_scripts} of {matched_scripts} matching script(s)."
        )
    if kind == "script-find-request":
        match_count = _normalize_int(result.get("match_count"), label="match_count", minimum=0) or 0
        candidate_count = (
            _normalize_int(result.get("candidate_count"), label="candidate_count", minimum=0)
            or 0
        )
        return (
            "Browser script request finder found "
            f"{match_count} match(es) across {candidate_count} candidate script(s)."
        )
    if kind == "code-search":
        match_count = _normalize_int(result.get("match_count"), label="match_count", minimum=0) or 0
        matched_scripts = (
            _normalize_int(result.get("matched_scripts"), label="matched_scripts", minimum=0)
            or 0
        )
        return (
            "Browser code search found "
            f"{match_count} match(es) across {matched_scripts} script(s)."
        )
    if kind == "script-inspect":
        script_id = _normalize_text(result.get("script_id")) or "script"
        source_chars = _normalize_int(result.get("source_chars"), label="source_chars", minimum=0)
        suffix = f" ({source_chars} chars)" if source_chars is not None else ""
        return f"Browser script inspected {script_id}{suffix}."
    if kind == "script-extract-request":
        candidate_count = (
            _normalize_int(result.get("candidate_count"), label="candidate_count", minimum=0)
            or 0
        )
        script_id = _normalize_text(result.get("script_id")) or "script"
        return (
            "Browser script request extractor found "
            f"{candidate_count} endpoint candidate(s) in {script_id}."
        )
    return None


def _browser_code_blocks(deps: BrowserToolDeps, content: Any) -> list[dict[str, Any]]:
    found = _find_browser_code_result_payload(content)
    if found is None:
        return []
    kind, result = found
    formatted = _format_browser_code_result(kind, result)
    if formatted is None:
        return []
    blocks = [text_content_block(formatted)]
    artifact_block = _browser_script_preview_artifact_block(
        deps,
        kind=kind,
        result=result,
    )
    if artifact_block is not None:
        blocks.append(artifact_block)
    return blocks


def _browser_script_preview_artifact_block(
    deps: BrowserToolDeps,
    *,
    kind: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    if kind != "script-inspect":
        return None
    artifact_service = deps.artifact_service
    preview = result.get("source_preview")
    if artifact_service is None or not isinstance(preview, str) or not preview:
        return None
    data = preview.encode("utf-8")
    if len(data) <= _SCRIPT_TOP_LEVEL_PREVIEW_LIMIT:
        return None
    script = result.get("script")
    script = script if isinstance(script, dict) else {}
    script_id = _normalize_text(result.get("script_id")) or _normalize_text(
        script.get("script_id"),
    )
    url = _normalize_text(script.get("url"))
    label = url or script_id or "browser-script-preview"
    artifact = artifact_service.create_artifact(
        data=data,
        mime_type="application/javascript",
        name=f"{_safe_browser_artifact_name(label)}.js",
        metadata={
            "source": "browser",
            "attachment_kind": "script-preview",
            "browser_code_kind": kind,
            "script_id": script_id,
            "url": url,
        },
    )
    return file_ref_content_block(
        artifact_id=artifact.id,
        mime_type=artifact.mime_type,
        name=artifact.name,
        download_url=f"/artifacts/{artifact.id}/download",
    )


def _find_browser_code_result_payload(content: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    if command_kind not in _CODE_PAGE_ACTION_KINDS:
        return None
    value = content.get("value")
    if not isinstance(value, dict):
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return None
    kind = _normalize_text(result.get("kind")) or command_kind
    if kind not in _CODE_PAGE_ACTION_KINDS:
        return None
    return kind, result


def _format_browser_code_result(kind: str, result: dict[str, Any]) -> str | None:
    if kind == "runtime-inspect":
        return _format_browser_runtime_inspect_result(result)
    if kind == "script-list":
        return _format_browser_script_list_result(result)
    if kind == "script-find-request":
        return _format_browser_script_find_request_result(result)
    if kind == "code-search":
        return _format_browser_code_search_result(result)
    if kind == "script-inspect":
        return _format_browser_script_inspect_result(result)
    if kind == "script-extract-request":
        return _format_browser_script_extract_request_result(result)
    return None


def _format_browser_runtime_inspect_result(result: dict[str, Any]) -> str:
    lines = ["Browser runtime inspect:"]
    title = _normalize_text(result.get("title"))
    url = _normalize_text(result.get("url"))
    if title is not None:
        lines.append(f"- Title: {title}")
    if url is not None:
        lines.append(f"- URL: {url}")
    page_state = result.get("page_state")
    if isinstance(page_state, dict):
        ready_state = _normalize_text(page_state.get("ready_state"))
        visibility_state = _normalize_text(page_state.get("visibility_state"))
        focused = page_state.get("focused")
        online = page_state.get("online")
        state_parts: list[str] = []
        if ready_state is not None:
            state_parts.append(f"ready={ready_state}")
        if visibility_state is not None:
            state_parts.append(f"visible={visibility_state}")
        if isinstance(focused, bool):
            state_parts.append(f"focused={'yes' if focused else 'no'}")
        if isinstance(online, bool):
            state_parts.append(f"online={'yes' if online else 'no'}")
        history_length = _normalize_int(
            page_state.get("history_length"),
            label="history_length",
            minimum=0,
        )
        if history_length is not None:
            state_parts.append(f"history={history_length}")
        if state_parts:
            lines.append(f"- Page state: {', '.join(state_parts)}")
    frameworks = result.get("frameworks")
    if isinstance(frameworks, dict):
        detected = frameworks.get("detected")
        detected_labels = [
            item
            for item in (_normalize_text(entry) for entry in detected)
            if item is not None
        ] if isinstance(detected, list) else []
        lines.append(
            "- Framework signals: "
            + (", ".join(detected_labels) if detected_labels else "none")
        )
    route_hint_lines = _format_browser_route_hints(result.get("route_hints"))
    if route_hint_lines:
        lines.append("- Route hints:")
        lines.extend(f"  - {line}" for line in route_hint_lines)
    globals_list = result.get("globals")
    if isinstance(globals_list, list):
        existing = [
            item
            for item in globals_list
            if isinstance(item, dict) and item.get("exists") is True
        ]
        lines.append(f"- Globals: {len(existing)} present")
        for item in existing[:8]:
            name = _normalize_text(item.get("name")) or "<global>"
            value_type = _normalize_text(item.get("type")) or "unknown"
            constructor_name = _normalize_text(item.get("constructor_name"))
            keys = item.get("keys")
            key_suffix = ""
            if isinstance(keys, list) and keys:
                rendered_keys = ", ".join(
                    key
                    for key in (_normalize_text(entry) for entry in keys[:5])
                    if key is not None
                )
                if rendered_keys:
                    key_suffix = f"; keys={rendered_keys}"
            constructor_suffix = f"/{constructor_name}" if constructor_name is not None else ""
            lines.append(f"  - {name}: {value_type}{constructor_suffix}{key_suffix}")
    client_modules = result.get("client_modules")
    if isinstance(client_modules, list):
        module_lines: list[str] = []
        for item in client_modules[:10]:
            if not isinstance(item, dict):
                continue
            path = _normalize_text(item.get("path"))
            if path is None:
                continue
            keys = item.get("keys")
            rendered_keys = ""
            if isinstance(keys, list) and keys:
                rendered = ", ".join(
                    key
                    for key in (_normalize_text(entry) for entry in keys[:16])
                    if key is not None
                )
                if rendered:
                    key_count = _normalize_int(
                        item.get("key_count"),
                        label="key_count",
                        minimum=0,
                    )
                    suffix = f" of {key_count}" if key_count is not None else ""
                    rendered_keys = f"; keys={rendered}{suffix}"
            methods = item.get("methods")
            rendered_methods = ""
            if isinstance(methods, list) and methods:
                method_items: list[str] = []
                for method in methods[:12]:
                    if not isinstance(method, dict):
                        continue
                    method_name = _normalize_text(method.get("name"))
                    arity = _normalize_int(method.get("arity"), label="arity", minimum=0)
                    if method_name is None:
                        continue
                    method_items.append(f"{method_name}({arity if arity is not None else '?'})")
                if method_items:
                    method_count = _normalize_int(
                        item.get("method_count"),
                        label="method_count",
                        minimum=0,
                    )
                    suffix = f" of {method_count}" if method_count is not None else ""
                    rendered_methods = f"; methods={', '.join(method_items)}{suffix}"
            module_lines.append(f"  - {path}{rendered_keys}{rendered_methods}")
        if module_lines:
            lines.append("- Client modules:")
            lines.extend(module_lines)
            lines.append(
                "- Next: choose the most task-relevant client module/method shown "
                "above, then use browser.evaluate for a compact custom summary "
                "or verify behavior with network capture/replay. Avoid repeating "
                "broad code search when a relevant method is visible."
            )
    storage = result.get("storage")
    if isinstance(storage, dict):
        storage_parts: list[str] = []
        for label, key in (("local", "local"), ("session", "session")):
            store = storage.get(key)
            if not isinstance(store, dict):
                continue
            count = _normalize_int(store.get("count"), label=f"{key}_count", minimum=0)
            if count is not None:
                storage_parts.append(f"{label}={count}")
        if storage_parts:
            lines.append(f"- Storage keys: {', '.join(storage_parts)}")
    performance = result.get("performance")
    if isinstance(performance, dict):
        resource_count = _normalize_int(
            performance.get("resource_count"),
            label="resource_count",
            minimum=0,
        )
        navigation_count = _normalize_int(
            performance.get("navigation_count"),
            label="navigation_count",
            minimum=0,
        )
        perf_parts: list[str] = []
        if navigation_count is not None:
            perf_parts.append(f"navigation={navigation_count}")
        if resource_count is not None:
            perf_parts.append(f"resources={resource_count}")
        if perf_parts:
            lines.append(f"- Performance: {', '.join(perf_parts)}")
    return "\n".join(lines)


def _format_browser_route_hints(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for raw_item in value[:8]:
        if not isinstance(raw_item, dict):
            continue
        source = _normalize_text(raw_item.get("source")) or "route"
        path = _normalize_text(raw_item.get("path"))
        search = _normalize_text(raw_item.get("search"))
        hash_value = _normalize_text(raw_item.get("hash"))
        if path is not None:
            route = path
            if search is not None:
                route += search
            if hash_value is not None:
                route += hash_value
            lines.append(f"{source}: {route or '/'}")
            continue
        page = _normalize_text(raw_item.get("page"))
        query = _normalize_text(raw_item.get("query"))
        if page is not None or query is not None:
            suffix = f" query={query}" if query is not None else ""
            lines.append(f"{source}: {page or '<page>'}{suffix}")
            continue
        preview = _normalize_text(raw_item.get("preview"))
        if preview is not None:
            lines.append(f"{source}: {preview}")
            continue
        keys = raw_item.get("keys")
        if isinstance(keys, list) and keys:
            rendered_keys: list[str] = []
            for entry in keys[:5]:
                if not isinstance(entry, dict):
                    continue
                key = _normalize_text(entry.get("key"))
                value_text = _normalize_text(entry.get("value"))
                if key is None:
                    continue
                rendered_keys.append(f"{key}={value_text or '<object>'}")
            if rendered_keys:
                lines.append(f"{source}: {', '.join(rendered_keys)}")
    return lines


def _format_browser_script_list_result(result: dict[str, Any]) -> str:
    scripts = result.get("scripts")
    if not isinstance(scripts, list):
        scripts = []
    scripts_count = _normalize_int(result.get("scripts_count"), label="scripts_count", minimum=0) or 0
    matched_scripts = (
        _normalize_int(result.get("matched_scripts"), label="matched_scripts", minimum=0)
        or len(scripts)
    )
    returned_scripts = (
        _normalize_int(result.get("returned_scripts"), label="returned_scripts", minimum=0)
        or len(scripts)
    )
    lines = [
        "Browser script list:",
        f"- Scripts: {returned_scripts} returned, {matched_scripts} matched, {scripts_count} total",
    ]
    if not scripts:
        lines.append("- Results: none")
        lines.extend(_format_browser_code_errors(result.get("errors")))
        return "\n".join(lines)
    for item in scripts[:20]:
        if not isinstance(item, dict):
            continue
        script_id = _normalize_text(item.get("script_id")) or "unknown"
        url = _normalize_text(item.get("url")) or "<anonymous>"
        line_count = _normalize_int(item.get("line_count"), label="line_count", minimum=0)
        context_id = _normalize_int(
            item.get("execution_context_id"),
            label="execution_context_id",
            minimum=0,
        )
        suffixes: list[str] = [f"id={script_id}"]
        if line_count is not None:
            suffixes.append(f"{line_count} line{'s' if line_count != 1 else ''}")
        if context_id is not None:
            suffixes.append(f"context={context_id}")
        if bool(item.get("is_module")):
            suffixes.append("module")
        source_map_url = _normalize_text(item.get("source_map_url"))
        if source_map_url is not None:
            suffixes.append("source-map")
        lines.append(f"- {url} ({', '.join(suffixes)})")
    hidden_count = max(0, matched_scripts - min(matched_scripts, len(scripts), 20))
    if hidden_count > 0:
        lines.append(f"... {hidden_count} more script(s) in details")
    lines.extend(_format_browser_code_errors(result.get("errors")))
    return "\n".join(lines)


def _format_browser_script_find_request_result(result: dict[str, Any]) -> str:
    request = result.get("request")
    request = request if isinstance(request, dict) else {}
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
    match_count = _normalize_int(result.get("match_count"), label="match_count", minimum=0) or 0
    candidate_count = (
        _normalize_int(result.get("candidate_count"), label="candidate_count", minimum=0)
        or len(candidates)
    )
    request_url = _normalize_text(request.get("url"))
    path = _normalize_text(request.get("path"))
    label = request_url or path or ", ".join(
        term
        for term in (
            _normalize_text(item)
            for item in (
                request.get("search_terms") if isinstance(request.get("search_terms"), list) else []
            )
        )
        if term is not None
    )
    lines = [
        "Browser script request finder:",
        f"- Request: {label or '<unspecified>'}",
        f"- Matches: {match_count} across {candidate_count} candidate script(s)",
    ]
    if not candidates:
        lines.append("- Results: none")
        lines.extend(_format_browser_code_errors(result.get("errors")))
        return "\n".join(lines)
    for item in candidates[:5]:
        if not isinstance(item, dict):
            continue
        script = item.get("script")
        script = script if isinstance(script, dict) else {}
        script_id = _normalize_text(item.get("script_id")) or _normalize_text(script.get("script_id"))
        url = _normalize_text(item.get("url")) or _normalize_text(script.get("url")) or "<anonymous>"
        score = _normalize_int(item.get("score"), label="score", minimum=0)
        source_chars = _normalize_int(item.get("source_chars"), label="source_chars", minimum=0)
        suffixes: list[str] = []
        if script_id is not None:
            suffixes.append(f"id={script_id}")
        if score is not None:
            suffixes.append(f"score={score}")
        if source_chars is not None:
            suffixes.append(f"{source_chars} chars")
        suffix = f" ({', '.join(suffixes)})" if suffixes else ""
        lines.append(f"- Script: {url}{suffix}")
        matches = item.get("matches")
        if not isinstance(matches, list):
            continue
        for match in matches[:2]:
            if not isinstance(match, dict):
                continue
            field = _normalize_text(match.get("field")) or "source"
            term = _normalize_text(match.get("term"))
            line_number = _normalize_int(match.get("line_number"), label="line_number", minimum=1)
            column = _normalize_int(match.get("column"), label="column", minimum=1)
            location = ""
            if line_number is not None:
                location = f" line {line_number}"
                if column is not None:
                    location += f", column {column}"
            term_suffix = f" term={term}" if term is not None else ""
            snippet = _normalize_text(match.get("snippet")) or ""
            lines.append(f"  - {field}{location}{term_suffix}:")
            if snippet:
                for snippet_line in _bounded_browser_code_lines(snippet, line_limit=2):
                    lines.append(f"    {snippet_line}")
        if len(matches) > 2:
            lines.append(
                "  ... more matches in details; inspect the script_id or use page-context evaluate next."
            )
    if len(candidates) > 5:
        lines.append(f"... {len(candidates) - 5} more candidate script(s) in details")
    lines.append(
        "- Next: if a candidate script is listed, stop broad searching and inspect "
        "its script_id with start_line plus column, or run a focused "
        "browser.evaluate probe."
    )
    lines.extend(_format_browser_code_errors(result.get("errors")))
    return "\n".join(lines)


def _format_browser_code_search_result(result: dict[str, Any]) -> str:
    query = _normalize_text(result.get("query")) or ""
    match_count = _normalize_int(result.get("match_count"), label="match_count", minimum=0) or 0
    matched_scripts = (
        _normalize_int(result.get("matched_scripts"), label="matched_scripts", minimum=0)
        or 0
    )
    lines = [
        "Browser code search:",
        f"- Query: {query}",
        f"- Matches: {match_count} across {matched_scripts} script(s)",
    ]
    matches = result.get("matches")
    if not isinstance(matches, list) or not matches:
        lines.append("- Results: none")
        lines.extend(_format_browser_code_errors(result.get("errors")))
        return "\n".join(lines)
    for item in matches[:4]:
        if not isinstance(item, dict):
            continue
        script = item.get("script")
        script = script if isinstance(script, dict) else {}
        script_id = _normalize_text(item.get("script_id")) or _normalize_text(script.get("script_id"))
        url = _normalize_text(item.get("url")) or _normalize_text(script.get("url")) or "<anonymous>"
        source_chars = _normalize_int(item.get("source_chars"), label="source_chars", minimum=0)
        suffixes = [f"script_id={script_id or 'unknown'}"]
        if source_chars is not None:
            suffixes.append(f"{source_chars} chars")
        lines.append(f"- Script: {url} ({', '.join(suffixes)})")
        script_matches = item.get("matches")
        if not isinstance(script_matches, list):
            continue
        for match in script_matches[:2]:
            if not isinstance(match, dict):
                continue
            field = _normalize_text(match.get("field")) or "source"
            line_number = _normalize_int(match.get("line_number"), label="line_number", minimum=1)
            column = _normalize_int(match.get("column"), label="column", minimum=1)
            location = ""
            if line_number is not None:
                location = f" line {line_number}"
                if column is not None:
                    location += f", column {column}"
            snippet = _normalize_text(match.get("snippet")) or ""
            lines.append(f"  - {field}{location}:")
            if snippet:
                for snippet_line in _bounded_browser_code_lines(snippet, line_limit=2):
                    lines.append(f"    {snippet_line}")
        if len(script_matches) > 2:
            lines.append(
                "  ... more matches in details; inspect this script_id or use browser.evaluate next."
            )
    if len(matches) > 4:
        lines.append(f"... {len(matches) - 4} more matched script(s) in details")
    lines.append(
        "- Next: if a candidate script is listed, stop broad searching and inspect "
        "its script_id with start_line plus column, or run a focused "
        "browser.evaluate probe."
    )
    lines.extend(_format_browser_code_errors(result.get("errors")))
    return "\n".join(lines)


def _bounded_browser_code_lines(value: str, *, line_limit: int) -> list[str]:
    lines: list[str] = []
    for raw_line in value.splitlines()[:line_limit]:
        line = raw_line.strip()
        if len(line) > 220:
            line = f"{line[:217].rstrip()}..."
        lines.append(line)
    return lines


def _format_browser_script_inspect_result(result: dict[str, Any]) -> str:
    script = result.get("script")
    script = script if isinstance(script, dict) else {}
    script_id = _normalize_text(result.get("script_id")) or _normalize_text(script.get("script_id"))
    url = _normalize_text(script.get("url")) or "<anonymous>"
    source_chars = _normalize_int(result.get("source_chars"), label="source_chars", minimum=0)
    start_line = _normalize_int(result.get("start_line"), label="start_line", minimum=1)
    end_line = _normalize_int(result.get("end_line"), label="end_line", minimum=1)
    start_column = _normalize_int(
        result.get("start_column"),
        label="start_column",
        minimum=1,
    )
    end_column = _normalize_int(
        result.get("end_column"),
        label="end_column",
        minimum=1,
    )
    lines = [
        "Browser script inspect:",
        f"- Script: {url} [{script_id or 'unknown'}]",
    ]
    if source_chars is not None:
        lines.append(f"- Source chars: {source_chars}")
    if start_line is not None and end_line is not None:
        lines.append(f"- Preview lines: {start_line}-{end_line}")
    if start_column is not None and end_column is not None:
        lines.append(f"- Preview columns: {start_column}-{end_column}")
    if result.get("truncated"):
        lines.append("- Truncated: yes")
    preview = _normalize_text(result.get("source_preview"))
    if preview is not None and len(preview.encode("utf-8")) > _SCRIPT_TOP_LEVEL_PREVIEW_LIMIT:
        lines.append("- Source preview: omitted from top-level content; see artifact.")
    elif preview is not None:
        lines.append("```js")
        lines.append(preview)
        lines.append("```")
    lines.extend(_format_browser_code_errors(result.get("errors")))
    return "\n".join(lines)


def _normalized_text_items(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    items = [
        item
        for item in (_normalize_text(entry) for entry in value)
        if item is not None
    ]
    return items[:limit]


def _format_browser_script_extract_request_result(result: dict[str, Any]) -> str:
    script = result.get("script")
    script = script if isinstance(script, dict) else {}
    script_id = _normalize_text(result.get("script_id")) or _normalize_text(script.get("script_id"))
    url = _normalize_text(script.get("url")) or "<anonymous>"
    source_chars = _normalize_int(result.get("source_chars"), label="source_chars", minimum=0)
    start_line = _normalize_int(result.get("start_line"), label="start_line", minimum=1)
    end_line = _normalize_int(result.get("end_line"), label="end_line", minimum=1)
    start_column = _normalize_int(
        result.get("start_column"),
        label="start_column",
        minimum=1,
    )
    end_column = _normalize_int(
        result.get("end_column"),
        label="end_column",
        minimum=1,
    )
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
    lines = [
        "Browser script request extract:",
        f"- Script: {url} [{script_id or 'unknown'}]",
        f"- Endpoint candidates: {len(candidates)}",
    ]
    if source_chars is not None:
        lines.append(f"- Source chars: {source_chars}")
    if start_line is not None and end_line is not None:
        lines.append(f"- Window lines: {start_line}-{end_line}")
    if start_column is not None and end_column is not None:
        lines.append(f"- Window columns: {start_column}-{end_column}")
    focus_terms = result.get("focus_terms")
    focus_labels = [
        item
        for item in (_normalize_text(entry) for entry in focus_terms)
        if item is not None
    ] if isinstance(focus_terms, list) else []
    if focus_labels:
        lines.append(f"- Focus terms: {', '.join(focus_labels[:6])}")
    if not candidates:
        payload_keys = _normalized_text_items(result.get("payload_key_candidates"), limit=10)
        client_methods = _normalized_text_items(result.get("client_method_candidates"), limit=8)
        if payload_keys:
            lines.append(f"- Payload keys nearby: {', '.join(payload_keys)}")
        if client_methods:
            lines.append(f"- Client methods nearby: {', '.join(client_methods)}")
        lines.append(
            "- Next: no endpoint literal was extracted; if a client method is visible, "
            "use browser.evaluate for a compact custom summary or verify behavior "
            "with network capture/replay."
        )
        lines.extend(_format_browser_code_errors(result.get("errors")))
        return "\n".join(lines)
    for item in candidates[:5]:
        if not isinstance(item, dict):
            continue
        endpoint = _normalize_text(item.get("endpoint")) or "<endpoint>"
        endpoint_kind = _normalize_text(item.get("endpoint_kind"))
        line_number = _normalize_int(item.get("line_number"), label="line_number", minimum=1)
        column = _normalize_int(item.get("column"), label="column", minimum=1)
        confidence = _normalize_text(item.get("confidence"))
        suffixes: list[str] = []
        if endpoint_kind is not None:
            suffixes.append(endpoint_kind)
        if confidence is not None:
            suffixes.append(f"confidence={confidence}")
        if line_number is not None:
            location = f"line {line_number}"
            if column is not None:
                location += f", column {column}"
            suffixes.append(location)
        lines.append(f"- {endpoint}" + (f" ({'; '.join(suffixes)})" if suffixes else ""))
        method_candidates = _normalized_text_items(item.get("method_candidates"), limit=6)
        client_methods = _normalized_text_items(item.get("client_method_candidates"), limit=6)
        payload_keys = _normalized_text_items(item.get("payload_key_candidates"), limit=12)
        if method_candidates:
            lines.append(f"  - Method hints: {', '.join(method_candidates)}")
        if client_methods:
            lines.append(f"  - Client/function hints: {', '.join(client_methods)}")
        if payload_keys:
            lines.append(f"  - Payload keys: {', '.join(payload_keys)}")
            lines.append(
                "  - Call hint: pass these keys as one JSON object argument when "
                "using a page client method."
            )
        preview = _normalize_text(item.get("evidence_preview"))
        if preview:
            lines.append("  - Evidence:")
            for preview_line in _bounded_browser_code_lines(preview, line_limit=2):
                lines.append(f"    {preview_line}")
    if len(candidates) > 5:
        lines.append(f"... {len(candidates) - 5} more endpoint candidate(s) in details")
    lines.append(
        "- Next: verify the endpoint with network capture/fetch/replay, or use "
        "browser.evaluate for a compact page-context summary instead of repeating broad code search."
    )
    lines.extend(_format_browser_code_errors(result.get("errors")))
    return "\n".join(lines)


def _format_browser_code_errors(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    lines = [f"- Tool warnings: {len(value)}"]
    for item in value[:3]:
        if not isinstance(item, dict):
            lines.append(f"  - {item}")
            continue
        script_id = _normalize_text(item.get("script_id"))
        message = _normalize_text(item.get("message")) or str(item)
        prefix = f"script {script_id}: " if script_id is not None else ""
        lines.append(f"  - {prefix}{message}")
    if len(value) > 3:
        lines.append(f"  - ... {len(value) - 3} more warning(s) in details")
    return lines


def _browser_action_trace_summary(content: dict[str, Any]) -> str | None:
    result = _find_browser_action_trace_result_payload(content)
    if result is None:
        return None
    action = result.get("action")
    action = action if isinstance(action, dict) else {}
    action_kind = _normalize_text(action.get("kind")) or "action"
    ok = action.get("ok")
    status = "completed" if ok is not False else "failed"
    diff = result.get("diff")
    diff = diff if isinstance(diff, dict) else {}
    changed = diff.get("snapshot_changed")
    changed_text = "changed" if changed is True else "unchanged" if changed is False else "unknown"
    network = result.get("network")
    network = network if isinstance(network, dict) else {}
    request_count = _coerce_non_negative_int(network.get("request_count")) or 0
    return (
        f"Browser action trace {status}: {action_kind}; "
        f"snapshot {changed_text}; {request_count} network request(s)."
    )


def _browser_action_trace_blocks(
    deps: BrowserToolDeps,
    content: Any,
) -> list[dict[str, Any]]:
    result = _find_browser_action_trace_result_payload(content)
    if result is None:
        return []
    blocks = [text_content_block(_format_browser_action_trace_result(result))]
    artifact_block = _browser_action_trace_artifact_block(deps, result)
    if artifact_block is not None:
        blocks.append(artifact_block)
    return blocks


def _browser_action_trace_artifact_block(
    deps: BrowserToolDeps,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    artifact_service = deps.artifact_service
    if artifact_service is None:
        return None
    trace_id = _normalize_text(result.get("trace_id")) or "browser-action-trace"
    try:
        data = json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    except (TypeError, ValueError):
        data = str(result).encode("utf-8")
    artifact = artifact_service.create_artifact(
        data=data,
        mime_type="application/json",
        name=f"{_safe_browser_artifact_name(trace_id)}.json",
        metadata={
            "source": "browser",
            "attachment_kind": "action-trace",
            "trace_id": trace_id,
        },
    )
    return file_ref_content_block(
        artifact_id=artifact.id,
        mime_type=artifact.mime_type,
        name=artifact.name,
        download_url=f"/artifacts/{artifact.id}/download",
    )


def _find_browser_action_trace_result_payload(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, dict):
        return None
    command = content.get("command")
    command_kind = _normalize_text(command.get("kind")) if isinstance(command, dict) else None
    value = content.get("value")
    if isinstance(value, dict):
        result = value.get("result")
        if isinstance(result, dict) and _normalize_text(result.get("kind")) == "action-trace":
            return result
    if command_kind == "action-trace":
        result = content.get("result")
        if isinstance(result, dict) and _normalize_text(result.get("kind")) == "action-trace":
            return result
    return None


def _format_browser_action_trace_result(result: dict[str, Any]) -> str:
    trace_id = _normalize_text(result.get("trace_id")) or "trace"
    profile_name = _normalize_text(result.get("profile_name")) or "-"
    target_id = _normalize_text(result.get("target_id")) or "-"
    action = result.get("action")
    action = action if isinstance(action, dict) else {}
    action_kind = _normalize_text(action.get("kind")) or "action"
    action_ok = action.get("ok") is not False
    lines = [
        "Browser action trace:",
        f"- Trace: {trace_id}",
        f"- Profile/Target: {profile_name} / {target_id}",
        f"- Action: {action_kind} ({'ok' if action_ok else 'failed'})",
    ]
    envelope = result.get("action_envelope")
    if isinstance(envelope, dict):
        lines.append(f"- Page effect: {_browser_action_effect_label(envelope)}")
    resolved_selector = _normalize_text(action.get("resolved_selector"))
    if resolved_selector is not None:
        lines.append(f"- Resolved selector: {resolved_selector}")
    action_error = action.get("error")
    if isinstance(action_error, dict):
        error_message = _normalize_text(action_error.get("message"))
        if error_message is not None:
            lines.append(f"- Action error: {error_message}")
    diff = result.get("diff")
    if isinstance(diff, dict):
        changed = diff.get("snapshot_changed")
        changed_text = "yes" if changed is True else "no" if changed is False else "unknown"
        ref_delta = _normalize_int(
            diff.get("ref_count_delta"),
            label="ref_count_delta",
            minimum=-100000,
        )
        before_chars = _coerce_non_negative_int(diff.get("before_chars"))
        after_chars = _coerce_non_negative_int(diff.get("after_chars"))
        lines.append(f"- Snapshot changed: {changed_text}")
        if ref_delta is not None:
            lines.append(f"- Ref delta: {ref_delta:+d}")
        if before_chars is not None and after_chars is not None:
            lines.append(f"- Snapshot chars: {before_chars} -> {after_chars}")
    recommendation = _browser_action_trace_recommendation(result)
    if isinstance(recommendation, dict):
        next_action = _normalize_text(recommendation.get("next_action"))
        reason = _normalize_text(recommendation.get("reason"))
        if next_action is not None:
            recommendation_line = f"- Next: {next_action}"
            if reason is not None:
                recommendation_line += f" ({reason})"
            lines.append(recommendation_line)
            suggested_tools = _browser_action_trace_suggested_tools(next_action)
            if suggested_tools:
                lines.append("- Suggested tools: " + ", ".join(suggested_tools))
    console = result.get("console")
    if isinstance(console, dict):
        new_console = _trace_preview_items(console.get("new"), limit=3)
        lines.append(
            "- Console delta: "
            f"{len(new_console)} new message{'s' if len(new_console) != 1 else ''}"
        )
        for item in new_console:
            level = _normalize_text(item.get("level")) or "log"
            text = _normalize_text(item.get("text")) or ""
            lines.append(f"  - [{level}] {text}")
    page_errors = result.get("page_errors")
    if isinstance(page_errors, dict):
        new_errors = _trace_preview_items(page_errors.get("new"), limit=3)
        lines.append(
            "- Page error delta: "
            f"{len(new_errors)} new error{'s' if len(new_errors) != 1 else ''}"
        )
        for item in new_errors:
            text = _normalize_text(item.get("text")) or _normalize_text(item.get("message")) or ""
            name = _normalize_text(item.get("name"))
            prefix = f"{name}: " if name is not None else ""
            lines.append(f"  - {prefix}{text}")
    network = result.get("network")
    if isinstance(network, dict):
        capture_id = _normalize_text(network.get("capture_id")) or "-"
        request_count = _coerce_non_negative_int(network.get("request_count")) or 0
        lines.append(f"- Network: {request_count} request(s), capture {capture_id}")
        causality = network.get("causality")
        if isinstance(causality, dict):
            initiator_counts = causality.get("initiator_counts")
            if isinstance(initiator_counts, dict) and initiator_counts:
                rendered_counts = ", ".join(
                    f"{key}:{value}"
                    for key, value in sorted(initiator_counts.items())
                )
                if rendered_counts:
                    lines.append(f"  - Initiators: {rendered_counts}")
            script_frames = _trace_preview_items(causality.get("script_frames"), limit=3)
            for frame in script_frames:
                script_url = _browser_network_url_label(_normalize_text(frame.get("script_url")))
                function_name = _normalize_text(frame.get("function_name")) or "<anonymous>"
                line_number = _coerce_non_negative_int(frame.get("line_number"))
                column_number = _coerce_non_negative_int(frame.get("column_number"))
                location = ""
                if line_number is not None:
                    location = f":{line_number}"
                    if column_number is not None:
                        location += f":{column_number}"
                request_id = _normalize_text(frame.get("request_id")) or "-"
                lines.append(
                    f"  - Script initiator: {function_name} @ {script_url}{location} ({request_id})"
                )
        requests = _trace_preview_items(network.get("requests"), limit=5)
        for item in requests:
            method = _normalize_text(item.get("method")) or "-"
            status = _normalize_text(item.get("status")) or "-"
            url = _browser_network_url_label(_normalize_text(item.get("url")))
            initiator = item.get("initiator_summary")
            initiator = initiator if isinstance(initiator, dict) else {}
            initiator_type = _normalize_text(initiator.get("type"))
            initiator_suffix = f" via {initiator_type}" if initiator_type is not None else ""
            lines.append(f"  - {method} {status} {url}{initiator_suffix}")
    lifecycle = result.get("lifecycle")
    if isinstance(lifecycle, dict):
        changed_fields = lifecycle.get("changed_fields")
        changed_count = len(changed_fields) if isinstance(changed_fields, dict) else 0
        lines.append(f"- Lifecycle delta: {changed_count} changed field(s)")
        if isinstance(changed_fields, dict):
            for field_name, field_delta in list(changed_fields.items())[:5]:
                if not isinstance(field_delta, dict):
                    continue
                before_value = _normalize_text(field_delta.get("before")) or "-"
                after_value = _normalize_text(field_delta.get("after")) or "-"
                lines.append(f"  - {field_name}: {before_value} -> {after_value}")
    storage = result.get("storage")
    if isinstance(storage, dict):
        storage_parts: list[str] = []
        for label in ("local", "session"):
            bucket = storage.get(label)
            if not isinstance(bucket, dict):
                continue
            added = bucket.get("added_keys")
            removed = bucket.get("removed_keys")
            added_count = len(added) if isinstance(added, list) else 0
            removed_count = len(removed) if isinstance(removed, list) else 0
            count_delta = _normalize_int(
                bucket.get("count_delta"),
                label=f"{label}_count_delta",
                minimum=-100000,
            )
            storage_parts.append(
                f"{label}: {added_count} added, {removed_count} removed, {count_delta or 0:+d} count"
            )
        if storage_parts:
            lines.append("- Storage delta: " + "; ".join(storage_parts))
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        lines.append(f"- Trace warnings: {len(errors)}")
        for item in errors[:3]:
            if not isinstance(item, dict):
                continue
            source = _normalize_text(item.get("source")) or "trace"
            message = _normalize_text(item.get("message")) or ""
            lines.append(f"  - {source}: {message}")
    before = result.get("before")
    before_summary = _trace_snapshot_summary(before)
    after = result.get("after")
    after_summary = _trace_snapshot_summary(after)
    if before_summary is not None:
        lines.append(f"- Before snapshot: {before_summary}")
    if after_summary is not None:
        lines.append(f"- After snapshot: {after_summary}")
    return "\n".join(lines)


def _browser_action_trace_recommendation(result: dict[str, Any]) -> dict[str, Any] | None:
    recommendation = result.get("recommendation")
    if isinstance(recommendation, dict):
        return recommendation
    envelope = result.get("action_envelope")
    if not isinstance(envelope, dict):
        return None
    nested_result = envelope.get("result")
    if isinstance(nested_result, dict):
        nested_recommendation = nested_result.get("recommendation")
        if isinstance(nested_recommendation, dict):
            return nested_recommendation
    next_action = _normalize_text(envelope.get("next_action"))
    if next_action is None:
        return None
    return {"next_action": next_action}


def _trace_preview_items(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value[:limit] if isinstance(item, dict)]


def _browser_action_trace_suggested_tools(next_action: str) -> list[str]:
    if next_action == "inspect-target":
        return ["browser.dom.clickability", "browser.dom.inspect", "browser.observe"]
    if next_action == "inspect-page-errors":
        return ["browser.page.errors", "browser.runtime.inspect", "browser.observe"]
    if next_action == "inspect-script-initiator":
        return [
            "browser.script.extract_request",
            "browser.script.inspect",
            "browser.network.get_response_body",
            "browser.network.replay_request",
            "browser.evaluate",
        ]
    if next_action == "inspect-network-delta":
        return [
            "browser.network.list_requests",
            "browser.network.get_response_body",
            "browser.script.find_request",
            "browser.script.extract_request",
            "browser.evaluate",
        ]
    if next_action == "inspect-page-lifecycle":
        return ["browser.page.lifecycle", "browser.observe", "browser.snapshot"]
    if next_action == "inspect-storage-delta":
        return [
            "browser.storage.indexeddb.list",
            "browser.storage.cache.list",
            "browser.observe",
        ]
    if next_action == "continue-from-after-snapshot":
        return ["browser.observe", "browser.snapshot", "browser.action.trace"]
    if next_action == "inspect-console-delta":
        return ["browser.runtime.inspect", "browser.page.errors", "browser.observe"]
    if next_action == "observe-or-inspect-clickability":
        return ["browser.observe", "browser.dom.clickability", "browser.dom.inspect"]
    return []


def _trace_snapshot_summary(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    ref_count = _coerce_non_negative_int(value.get("ref_count"))
    frame_count = _coerce_non_negative_int(value.get("frame_count"))
    preview = _normalize_text(value.get("snapshot_preview"))
    if preview is not None:
        return _trace_snapshot_summary_text(
            chars=len(preview),
            ref_count=ref_count,
            frame_count=frame_count,
        )
    nested = value.get("value")
    if isinstance(nested, dict):
        refs = nested.get("refs")
        nested_ref_count = len(refs) if isinstance(refs, list) else ref_count
        snapshot = _normalize_text(nested.get("snapshot"))
        if snapshot is not None:
            return _trace_snapshot_summary_text(
                chars=len(snapshot),
                ref_count=nested_ref_count,
                frame_count=frame_count,
            )
    if isinstance(nested, str):
        return _trace_snapshot_summary_text(
            chars=len(nested),
            ref_count=ref_count,
            frame_count=frame_count,
        )
    return None


def _trace_snapshot_summary_text(
    *,
    chars: int,
    ref_count: int | None,
    frame_count: int | None,
) -> str:
    parts = [f"{chars} chars omitted from text result"]
    if ref_count is not None:
        parts.append(f"{ref_count} ref(s)")
    if frame_count is not None:
        parts.append(f"{frame_count} frame(s)")
    parts.append("see action trace artifact/details for full snapshot")
    return ", ".join(parts)


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
        suitability = result.get("replay_suitability")
        level = _normalize_text(suitability.get("level")) if isinstance(suitability, dict) else None
        suffix = f" ({level})" if level is not None else ""
        return f"Browser network replay returned {status} for {source_request_id}{suffix}."
    if kind == "network-start-capture":
        capture_id = _browser_network_capture_id(result)
        suffix = f" '{capture_id}'" if capture_id is not None else ""
        return f"Browser network capture{suffix} started."
    if kind == "network-stop-capture":
        capture_id = _browser_network_capture_id(result)
        suffix = f" '{capture_id}'" if capture_id is not None else ""
        return f"Browser network capture{suffix} stopped."
    if kind == "network-clear-capture":
        capture_id = _browser_network_capture_id(result)
        suffix = f" '{capture_id}'" if capture_id is not None else ""
        return f"Browser network capture{suffix} cleared."
    return None


def _browser_network_inspect_summary(result: dict[str, Any]) -> str | None:
    performance = result.get("performance")
    entries = performance.get("entries") if isinstance(performance, dict) else None
    entry_count = len(entries) if isinstance(entries, list) else 0
    cdp = result.get("cdp")
    resource_tree = cdp.get("resource_tree") if isinstance(cdp, dict) else None
    resources = _cdp_resource_tree_count(resource_tree)
    if resources is None:
        resources = _legacy_cdp_resource_tree_count(resource_tree)
    cdp_suffix = f", {resources} CDP resource(s)" if resources is not None else ""
    return f"Browser network inspection returned {entry_count} performance entr{'y' if entry_count == 1 else 'ies'}{cdp_suffix}."


def _cdp_resource_tree_count(resource_tree: Any) -> int | None:
    if isinstance(resource_tree, dict):
        return _normalize_int(
            resource_tree.get("resource_count"),
            label="resource_count",
            minimum=0,
        )
    return None


def _legacy_cdp_resource_tree_count(resource_tree: Any) -> int | None:
    if not isinstance(resource_tree, dict):
        return None
    frame_tree = resource_tree.get("frameTree")
    if not isinstance(frame_tree, dict):
        return None
    resources = _legacy_cdp_resource_tree_resources(frame_tree)
    return len(resources)


def _legacy_cdp_resource_tree_resources(frame_tree: dict[str, Any]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    raw_resources = frame_tree.get("resources")
    if isinstance(raw_resources, list):
        resources.extend(item for item in raw_resources if isinstance(item, dict))
    children = frame_tree.get("childFrames")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                resources.extend(_legacy_cdp_resource_tree_resources(child))
    return resources


def _browser_network_blocks(deps: BrowserToolDeps, content: Any) -> list[dict[str, Any]]:
    found = _find_browser_network_result_payload(content)
    if found is None:
        return []
    kind, result = found
    formatted = _format_browser_network_result(kind, result)
    if formatted is None:
        return []
    blocks = [text_content_block(formatted)]
    artifact_block = _browser_network_body_artifact_block(
        deps,
        kind=kind,
        result=result,
    )
    if artifact_block is not None:
        blocks.append(artifact_block)
    return blocks


def _browser_network_body_artifact_block(
    deps: BrowserToolDeps,
    *,
    kind: str,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    if kind not in {
        "network-fetch-as-page",
        "network-replay-request",
        "network-get-response-body",
        "network-get-request-body",
    }:
        return None
    artifact_service = deps.artifact_service
    body = result.get("body")
    if artifact_service is None or not isinstance(body, str) or not body:
        return None
    data = body.encode("utf-8")
    if len(data) <= _NETWORK_TOP_LEVEL_BODY_PREVIEW_LIMIT:
        return None
    mime_type = (
        _normalize_text(result.get("mime_type"))
        or _normalize_text(result.get("content_type"))
        or "text/plain"
    )
    request = result.get("request")
    request = request if isinstance(request, dict) else {}
    request_id = _normalize_text(result.get("request_id")) or _normalize_text(
        request.get("request_id"),
    )
    url = _normalize_text(result.get("url")) or _normalize_text(request.get("url"))
    label = request_id or url or kind
    artifact = artifact_service.create_artifact(
        data=data,
        mime_type=mime_type,
        name=f"{_safe_browser_artifact_name(label)}{_browser_body_extension(mime_type)}",
        metadata={
            "source": "browser",
            "attachment_kind": "network-body",
            "browser_network_kind": kind,
            "request_id": request_id,
            "url": url,
        },
    )
    return file_ref_content_block(
        artifact_id=artifact.id,
        mime_type=artifact.mime_type,
        name=artifact.name,
        download_url=f"/artifacts/{artifact.id}/download",
    )


def _browser_body_extension(mime_type: str) -> str:
    normalized = mime_type.lower()
    if "json" in normalized:
        return ".json"
    if "html" in normalized:
        return ".html"
    if "xml" in normalized:
        return ".xml"
    if "javascript" in normalized or "ecmascript" in normalized:
        return ".js"
    return ".txt"


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
        lines.append(f"- Page: {_browser_network_url_label(url)}")
    if not entries:
        lines.append("- Performance entries: none")
    else:
        lines.append(f"- Performance entries: {len(entries)}")
        for entry in entries[:10]:
            if not isinstance(entry, dict):
                continue
            name = _browser_network_url_label(_normalize_text(entry.get("name")))
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
            resource_count = _cdp_resource_tree_count(resource_tree)
            if resource_count is None:
                resource_count = _legacy_cdp_resource_tree_count(resource_tree) or 0
            lines.append(f"- CDP resource tree: {resource_count} resource(s)")
            if isinstance(resource_tree, dict):
                frame_count = _normalize_int(
                    resource_tree.get("frame_count"),
                    label="frame_count",
                    minimum=0,
                )
                if frame_count is not None:
                    lines.append(f"  - Frames: {frame_count}")
                resource_types = resource_tree.get("types")
                if isinstance(resource_types, dict) and resource_types:
                    type_parts = [
                        f"{key}={value}"
                        for key, value in resource_types.items()
                        if isinstance(key, str) and isinstance(value, int)
                    ]
                    if type_parts:
                        lines.append(f"  - Types: {', '.join(type_parts[:8])}")
                resources = resource_tree.get("resources")
                if isinstance(resources, list) and resources:
                    for resource in resources[:5]:
                        if not isinstance(resource, dict):
                            continue
                        resource_url = _browser_network_url_label(
                            _normalize_text(resource.get("url")),
                        )
                        resource_type = _normalize_text(resource.get("type")) or "resource"
                        lines.append(f"  - {resource_type}: {resource_url}")
                if bool(resource_tree.get("truncated")):
                    lines.append("  - Raw CDP resource tree omitted; samples truncated.")
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
    capture_id = _browser_network_capture_id(result)
    if capture_id is not None:
        lines.append(f"- Capture: {capture_id}")
        if kind == "network-start-capture":
            lines.append(f"- Use capture_id: {capture_id}")
            lines.append(
                "- Next: trigger the page action or runtime probe, then pass this "
                "capture_id to browser.network.list_requests"
            )
    target_id = _normalize_text(result.get("target_id"))
    if target_id is None:
        capture = result.get("capture")
        if isinstance(capture, dict):
            target_id = _normalize_text(capture.get("target_id"))
    if target_id is not None:
        lines.append(f"- Target: {target_id}")
    request_count = _coerce_non_negative_int(result.get("request_count"))
    if request_count is not None:
        lines.append(f"- Requests: {request_count}")
    status = _normalize_text(result.get("status"))
    if status is not None:
        lines.append(f"- Status: {status}")
    return "\n".join(lines)


def _browser_network_capture_id(result: dict[str, Any]) -> str | None:
    capture_id = _normalize_text(result.get("capture_id"))
    if capture_id is not None:
        return capture_id
    capture = result.get("capture")
    if isinstance(capture, dict):
        return _normalize_text(capture.get("capture_id"))
    return None


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
    result_kind = _normalize_text(result.get("kind"))
    if result_kind == "network-replay-request":
        lines.extend(_format_browser_network_replay_diagnostics(result))
    if result_kind == "network-fetch-as-page":
        lines.extend(_format_browser_network_fetch_diagnostics(result))
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


def _format_browser_network_replay_diagnostics(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    suitability = result.get("replay_suitability")
    if isinstance(suitability, dict):
        level = _normalize_text(suitability.get("level")) or "unknown"
        lines.append(f"- Replay suitability: {level}")
        gates = suitability.get("gates")
        if isinstance(gates, dict):
            gate_parts: list[str] = []
            cross_origin = gates.get("cross_origin")
            if isinstance(cross_origin, dict) and bool(cross_origin.get("required")):
                allowed = "allowed" if bool(cross_origin.get("allowed")) else "not allowed"
                gate_parts.append(f"cross-origin {allowed}")
            mutating = gates.get("mutating_method")
            if isinstance(mutating, dict) and bool(mutating.get("required")):
                method = _normalize_text(mutating.get("method")) or "mutating"
                allowed = "allowed" if bool(mutating.get("allowed")) else "not allowed"
                gate_parts.append(f"{method} {allowed}")
            captured_body = gates.get("captured_body")
            if isinstance(captured_body, dict):
                source = _normalize_text(captured_body.get("source"))
                if source is not None:
                    gate_parts.append(f"body={source}")
            if gate_parts:
                lines.append(f"  - Gates: {', '.join(gate_parts)}")
        warnings = suitability.get("warnings")
        if isinstance(warnings, list) and warnings:
            for item in warnings[:3]:
                warning = _normalize_text(item)
                if warning is not None:
                    lines.append(f"  - Warning: {warning}")

    diff = result.get("request_diff")
    if isinstance(diff, dict):
        changed_fields = diff.get("changed_fields")
        if isinstance(changed_fields, list):
            fields = [
                field
                for field in (_normalize_text(item) for item in changed_fields)
                if field is not None
            ]
        else:
            fields = []
        label = ", ".join(fields) if fields else "none"
        body_source = _normalize_text(diff.get("body_source"))
        suffix = f"; body={body_source}" if body_source is not None else ""
        lines.append(f"- Request diff: {label}{suffix}")

    response = result.get("response_summary")
    if isinstance(response, dict):
        ok_label = "ok" if bool(response.get("ok")) else "not ok"
        status = _normalize_text(response.get("status")) or "-"
        mime_type = _normalize_text(response.get("mime_type"))
        size_bytes = _coerce_non_negative_int(response.get("size_bytes"))
        details = [ok_label, f"status={status}"]
        if mime_type is not None:
            details.append(f"type={mime_type}")
        if size_bytes is not None:
            details.append(f"size={size_bytes} bytes")
        if bool(response.get("truncated")):
            details.append("truncated")
        if bool(response.get("redacted")):
            details.append("redacted")
        lines.append(f"- Response summary: {', '.join(details)}")
    return lines


def _format_browser_network_fetch_diagnostics(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    safety = result.get("fetch_safety")
    if isinstance(safety, dict):
        level = _normalize_text(safety.get("level")) or "unknown"
        lines.append(f"- Fetch safety: {level}")
        gates = safety.get("gates")
        if isinstance(gates, dict):
            gate_parts: list[str] = []
            cross_origin = gates.get("cross_origin")
            if isinstance(cross_origin, dict) and bool(cross_origin.get("required")):
                allowed = "allowed" if bool(cross_origin.get("allowed")) else "not allowed"
                gate_parts.append(f"cross-origin {allowed}")
            mutating = gates.get("mutating_method")
            if isinstance(mutating, dict) and bool(mutating.get("required")):
                method = _normalize_text(mutating.get("method")) or "mutating"
                allowed = "allowed" if bool(mutating.get("allowed")) else "not allowed"
                gate_parts.append(f"{method} {allowed}")
            body = gates.get("body")
            if isinstance(body, dict) and bool(body.get("present")):
                size_bytes = _coerce_non_negative_int(body.get("size_bytes"))
                gate_parts.append(
                    f"body={size_bytes} bytes" if size_bytes is not None else "body=present",
                )
            credentials = gates.get("credentials")
            if isinstance(credentials, dict) and bool(credentials.get("included")):
                gate_parts.append("credentials=browser-page")
            if gate_parts:
                lines.append(f"  - Gates: {', '.join(gate_parts)}")
        warnings = safety.get("warnings")
        if isinstance(warnings, list) and warnings:
            for item in warnings[:3]:
                warning = _normalize_text(item)
                if warning is not None:
                    lines.append(f"  - Warning: {warning}")
    response = result.get("response_summary")
    if isinstance(response, dict):
        ok = response.get("ok")
        status = _normalize_text(response.get("status"))
        mime_type = _normalize_text(response.get("mime_type"))
        summary_parts = []
        if status is not None:
            summary_parts.append(f"status={status}")
        if mime_type is not None:
            summary_parts.append(f"type={mime_type}")
        if ok is not None:
            summary_parts.append(f"ok={bool(ok)}")
        if summary_parts:
            lines.append(f"- Response summary: {', '.join(summary_parts)}")
    return lines


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
    if value.startswith("data:"):
        header, separator, payload = value.partition(",")
        if separator:
            if payload.startswith("[omitted "):
                return value
            return f"{header},[omitted {len(payload)} chars]"
        return "data:[omitted]"
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


def _browser_observe_blocks(content: Any) -> list[dict[str, Any]]:
    if not isinstance(content, dict) or _normalize_text(content.get("kind")) != "observe":
        return []
    lines: list[str] = []
    summary = _browser_observe_summary(content)
    if summary is not None:
        lines.append(summary)
    page = content.get("page")
    if isinstance(page, dict):
        title = _normalize_text(page.get("title")) or "(untitled)"
        url = _normalize_text(page.get("url")) or "(no url)"
        target_id = _normalize_text(page.get("target_id")) or "current"
        lines.append(f"Page: [{target_id}] {title}\n{url}")
    tabs = content.get("tabs")
    if isinstance(tabs, dict):
        tab_count = tabs.get("count")
        if isinstance(tab_count, int):
            lines.append(f"Tabs: {tab_count}")
    frames = content.get("frames")
    if isinstance(frames, dict):
        frame_count = frames.get("count")
        if isinstance(frame_count, int):
            lines.append(f"Frames: {frame_count}")
    interaction = content.get("interaction")
    if isinstance(interaction, dict):
        ref_count = interaction.get("ref_count")
        frame_count = interaction.get("frame_count")
        lines.append(f"Interaction: {ref_count or 0} refs across {frame_count or 0} frame(s)")
        evidence = interaction.get("evidence")
        if isinstance(evidence, dict) and evidence:
            rendered_evidence = ", ".join(
                f"{key}:{value}"
                for key, value in sorted(evidence.items())
                if isinstance(value, int)
            )
            if rendered_evidence:
                lines.append(f"Evidence: {rendered_evidence}")
    form = content.get("form")
    if isinstance(form, dict):
        form_line = _format_browser_observe_form(form)
        if form_line is not None:
            lines.append(form_line)
    overlay = content.get("overlay")
    if isinstance(overlay, dict):
        overlay_line = _format_browser_observe_overlay(overlay)
        if overlay_line is not None:
            lines.append(overlay_line)
    guidance = content.get("guidance")
    if isinstance(guidance, dict):
        guidance_line = _format_browser_observe_guidance(guidance)
        if guidance_line is not None:
            lines.append(guidance_line)
    runtime = content.get("runtime")
    if isinstance(runtime, dict):
        runtime_line = _format_browser_observe_runtime(runtime)
        if runtime_line is not None:
            lines.append(runtime_line)
    network = content.get("network")
    if isinstance(network, dict):
        network_line = _format_browser_observe_network(network)
        if network_line is not None:
            lines.append(network_line)
    code = content.get("code")
    if isinstance(code, dict):
        code_line = _format_browser_observe_code(code)
        if code_line is not None:
            lines.append(code_line)
    snapshot = content.get("snapshot")
    formatted_snapshot = (
        _format_browser_snapshot_result(snapshot)
        if isinstance(snapshot, dict)
        else None
    )
    if formatted_snapshot is not None:
        lines.append(formatted_snapshot)
    console = content.get("console")
    if isinstance(console, dict):
        formatted_console = _format_browser_console_result(console)
        if formatted_console:
            lines.append("Console:\n" + formatted_console)
    errors = content.get("errors")
    if isinstance(errors, list | tuple) and errors:
        lines.append(f"Observation warnings: {len(errors)} section(s) failed.")
    if not lines:
        return []
    return [text_content_block("\n\n".join(lines))]


def _format_browser_observe_form(form: dict[str, Any]) -> str | None:
    field_count = _normalize_int(form.get("field_count"), label="field_count", minimum=0) or 0
    action_count = _normalize_int(form.get("action_count"), label="action_count", minimum=0) or 0
    candidate_count = (
        _normalize_int(form.get("candidate_count"), label="candidate_count", minimum=0)
        or 0
    )
    if field_count == 0 and action_count == 0 and candidate_count == 0:
        return None
    lines = [
        "Form:",
        f"- Fields/actions/candidates: {field_count}/{action_count}/{candidate_count}",
    ]
    fields = form.get("fields")
    if isinstance(fields, list) and fields:
        lines.append("- Fields:")
        for item in fields[:8]:
            if isinstance(item, dict):
                lines.append(f"  - {_browser_ref_label(item)}")
    actions = form.get("actions")
    if isinstance(actions, list) and actions:
        lines.append("- Actions:")
        for item in actions[:6]:
            if isinstance(item, dict):
                lines.append(f"  - {_browser_ref_label(item)}")
    guidance = form.get("guidance")
    if isinstance(guidance, dict):
        next_action = _normalize_text(guidance.get("next_action"))
        if next_action is not None:
            lines.append(f"- Next: {next_action}")
        tool_line = _format_browser_suggested_tools(guidance.get("suggested_tools"), limit=3)
        if tool_line is not None:
            lines.append(f"- {tool_line}")
    return "\n".join(lines)


def _format_browser_observe_overlay(overlay: dict[str, Any]) -> str | None:
    active = overlay.get("active") is True
    selector = _normalize_text(overlay.get("selector"))
    candidate_count = (
        _normalize_int(overlay.get("candidate_count"), label="candidate_count", minimum=0)
        or 0
    )
    if not active and candidate_count == 0:
        return None
    lines = [
        "Overlay:",
        f"- Active: {'yes' if active else 'no'}",
    ]
    if selector is not None:
        lines.append(f"- Selector: {selector}")
    candidates = overlay.get("candidates")
    if isinstance(candidates, list) and candidates:
        lines.append(f"- Candidates ({candidate_count}):")
        for item in candidates[:10]:
            if isinstance(item, dict):
                lines.append(f"  - {_browser_ref_label(item)}")
    guidance = overlay.get("guidance")
    if isinstance(guidance, dict):
        next_action = _normalize_text(guidance.get("next_action"))
        if next_action is not None:
            lines.append(f"- Next: {next_action}")
        tool_line = _format_browser_suggested_tools(guidance.get("suggested_tools"), limit=3)
        if tool_line is not None:
            lines.append(f"- {tool_line}")
    return "\n".join(lines)


def _browser_ref_label(item: dict[str, Any]) -> str:
    ref = _normalize_text(item.get("ref")) or "-"
    label = _normalize_text(item.get("label")) or _normalize_text(item.get("text")) or "-"
    role = _normalize_text(item.get("role")) or _normalize_text(item.get("tag")) or "element"
    selector = _normalize_text(item.get("selector"))
    suffix = f" ({selector})" if selector is not None else ""
    return f"{ref}: {role} \"{label}\"{suffix}"


def _format_browser_observe_guidance(guidance: dict[str, Any]) -> str | None:
    next_action = _normalize_text(guidance.get("next_action"))
    reason = _normalize_text(guidance.get("reason"))
    tools = guidance.get("suggested_tools")
    tool_labels = [
        item
        for item in (_normalize_text(entry) for entry in (tools if isinstance(tools, list) else []))
        if item is not None
    ][:4]
    if next_action is None and reason is None and not tool_labels:
        return None
    lines: list[str] = []
    if next_action is not None:
        line = f"Next: {next_action}"
        if reason is not None:
            line += f" ({reason})"
        lines.append(line)
    elif reason is not None:
        lines.append(f"Next: {reason}")
    if tool_labels:
        lines.append("Suggested tools: " + ", ".join(tool_labels))
    return "\n".join(lines)


def _format_browser_suggested_tools(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, list):
        return None
    tool_labels = [
        item
        for item in (_normalize_text(entry) for entry in value)
        if item is not None
    ][:limit]
    if not tool_labels:
        return None
    return "Suggested tools: " + ", ".join(tool_labels)


def _format_browser_observe_runtime(runtime: dict[str, Any]) -> str | None:
    page_state = runtime.get("page_state")
    frameworks = runtime.get("frameworks")
    resources = runtime.get("resources")
    performance = runtime.get("performance")
    errors = runtime.get("errors")
    parts: list[str] = []
    if isinstance(page_state, dict):
        state_parts: list[str] = []
        ready_state = _normalize_text(page_state.get("ready_state"))
        visibility_state = _normalize_text(page_state.get("visibility_state"))
        if ready_state is not None:
            state_parts.append(f"ready={ready_state}")
        if visibility_state is not None:
            state_parts.append(f"visible={visibility_state}")
        if isinstance(page_state.get("focused"), bool):
            state_parts.append(f"focused={'yes' if page_state.get('focused') else 'no'}")
        if state_parts:
            parts.append("page " + ", ".join(state_parts))
    if isinstance(frameworks, dict):
        detected = frameworks.get("detected")
        detected_labels = [
            item
            for item in (_normalize_text(entry) for entry in detected)
            if item is not None
        ] if isinstance(detected, list) else []
        if detected_labels:
            parts.append("frameworks=" + ", ".join(detected_labels))
    route_lines = _format_browser_route_hints(runtime.get("route_hints"))
    if route_lines:
        parts.append("routes=" + " | ".join(route_lines[:3]))
    globals_list = runtime.get("globals")
    if isinstance(globals_list, list):
        present_count = sum(
            1
            for item in globals_list
            if isinstance(item, dict) and item.get("exists") is True
        )
        if present_count:
            parts.append(f"{present_count} runtime global(s)")
    if isinstance(resources, dict):
        resource_count = _normalize_int(
            resources.get("resource_count"),
            label="resource_count",
            minimum=0,
        )
        frame_count = _normalize_int(
            resources.get("frame_count"),
            label="frame_count",
            minimum=0,
        )
        parts.append(f"{resource_count or 0} resource(s), {frame_count or 0} runtime frame(s)")
    if isinstance(performance, dict):
        metric_count = _normalize_int(
            performance.get("metric_count"),
            label="metric_count",
            minimum=0,
        )
        parts.append(f"{metric_count or 0} performance metric(s)")
    if isinstance(errors, list) and errors:
        parts.append(f"{len(errors)} runtime warning(s)")
    if not parts:
        return None
    return "Runtime: " + "; ".join(parts)


def _format_browser_observe_network(network: dict[str, Any]) -> str | None:
    performance = network.get("performance")
    capture = network.get("capture")
    parts: list[str] = []
    if isinstance(performance, dict):
        resource_count = _normalize_int(
            performance.get("resource_count"),
            label="resource_count",
            minimum=0,
        )
        navigation_count = _normalize_int(
            performance.get("navigation_count"),
            label="navigation_count",
            minimum=0,
        )
        parts.append(f"{navigation_count or 0} navigation entry, {resource_count or 0} resource entry")
    if isinstance(capture, dict) and capture.get("enabled") is True:
        request_count = _normalize_int(
            capture.get("request_count"),
            label="request_count",
            minimum=0,
        )
        total_count = _normalize_int(
            capture.get("total_count"),
            label="total_count",
            minimum=0,
        )
        parts.append(f"{request_count or 0}/{total_count or 0} captured request(s)")
    if not parts:
        return None
    return "Network: " + "; ".join(parts)


def _format_browser_observe_code(code: dict[str, Any]) -> str | None:
    scripts = code.get("scripts")
    search = code.get("search")
    request_matches = code.get("request_matches")
    parts: list[str] = []
    if isinstance(scripts, dict):
        returned_scripts = _normalize_int(
            scripts.get("returned_scripts"),
            label="returned_scripts",
            minimum=0,
        )
        scripts_count = _normalize_int(
            scripts.get("scripts_count"),
            label="scripts_count",
            minimum=0,
        )
        if returned_scripts is not None or scripts_count is not None:
            parts.append(f"{returned_scripts or 0}/{scripts_count or 0} script(s)")
        script_items = scripts.get("scripts")
        if isinstance(script_items, list) and script_items:
            labels = [
                label
                for label in (
                    _browser_script_label(item)
                    for item in script_items[:4]
                    if isinstance(item, dict)
                )
                if label is not None
            ]
            if labels:
                parts.append("top=" + ", ".join(labels))
    if isinstance(search, dict):
        query = _normalize_text(search.get("query"))
        match_count = _normalize_int(
            search.get("match_count"),
            label="match_count",
            minimum=0,
        )
        if query is not None or match_count is not None:
            parts.append(f"search {query or '<query>'}: {match_count or 0} match(es)")
    if isinstance(request_matches, dict):
        match_count = _normalize_int(
            request_matches.get("match_count"),
            label="request_match_count",
            minimum=0,
        )
        candidate_count = _normalize_int(
            request_matches.get("candidate_count"),
            label="candidate_count",
            minimum=0,
        )
        parts.append(f"request refs: {match_count or 0} match(es), {candidate_count or 0} candidate(s)")
    if not parts:
        return None
    return "Code: " + "; ".join(parts)


def _browser_script_label(item: dict[str, Any]) -> str | None:
    url = _normalize_text(item.get("url"))
    script_id = _normalize_text(item.get("script_id"))
    if url is not None:
        try:
            parsed = urlsplit(url)
            path = parsed.path.rsplit("/", 1)[-1] if parsed.path else parsed.netloc
            return path or url
        except ValueError:
            return url
    return script_id


def _browser_observe_summary(content: dict[str, Any]) -> str | None:
    if _normalize_text(content.get("kind")) != "observe":
        return None
    message = _normalize_text(content.get("message"))
    if message is not None:
        return message
    page = content.get("page")
    if not isinstance(page, dict):
        return "Observed browser page."
    title = _normalize_text(page.get("title"))
    url = _normalize_text(page.get("url"))
    label = title or url or "current page"
    return f"Observed {label}."


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
    sanitized = _sanitize_browser_result_details(content)
    if _browser_details_char_count(sanitized) <= _BROWSER_DETAILS_MAX_CHARS:
        return sanitized
    compacted = _compact_browser_result_details(sanitized)
    if _browser_details_char_count(compacted) <= _BROWSER_DETAILS_MAX_CHARS:
        if isinstance(compacted, dict):
            compacted = {
                **compacted,
                "details_compacted": True,
            }
        return compacted
    return _fallback_browser_result_details(sanitized)


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
        if kind in {"network-fetch-as-page", "network-replay-request"}:
            body = sanitized.get("body")
            if isinstance(body, str) and body:
                sanitized.pop("body", None)
                sanitized["body_removed_from_details"] = True
                sanitized["body_removed_size_bytes"] = len(body.encode("utf-8"))
        if kind == "script-inspect":
            source_preview = sanitized.get("source_preview")
            if (
                isinstance(source_preview, str)
                and len(source_preview.encode("utf-8")) > _SCRIPT_TOP_LEVEL_PREVIEW_LIMIT
            ):
                sanitized.pop("source_preview", None)
                sanitized["source_preview_removed_from_details"] = True
                sanitized["source_preview_removed_size_bytes"] = len(
                    source_preview.encode("utf-8"),
                )
        return sanitized
    if isinstance(value, list):
        return [_sanitize_browser_result_details(item) for item in value]
    return value


def _browser_details_char_count(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    except TypeError:
        return len(str(value))


def _compact_browser_result_details(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, _BROWSER_DETAILS_COMPACT_STRING_LIMIT)
    if isinstance(value, list):
        compacted = [
            _compact_browser_result_details(item)
            for item in value[:_BROWSER_DETAILS_COMPACT_LIST_LIMIT]
        ]
        hidden_count = len(value) - len(compacted)
        if hidden_count > 0:
            compacted.append({"items_omitted_from_details": hidden_count})
        return compacted
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _BROWSER_DETAILS_COMPACT_DICT_LIMIT:
                compacted["keys_omitted_from_details"] = len(value) - index
                break
            compacted[str(key)] = _compact_browser_result_details(item)
        return compacted
    return value


def _fallback_browser_result_details(value: dict[str, Any]) -> dict[str, Any]:
    summary = _browser_result_summary(value)
    fallback: dict[str, Any] = {
        "details_compacted": True,
        "details_truncated": True,
    }
    kind = _normalize_text(value.get("kind"))
    if kind is not None:
        fallback["kind"] = kind
    target_id = _extract_browser_target_id(value)
    if target_id is not None:
        fallback["target_id"] = target_id
    target_url = _browser_target_url_from_content(value)
    if target_url is not None:
        fallback.update(_safe_browser_url_metadata(target_url))
    if summary is not None:
        fallback["summary"] = _truncate_text(summary, 4000)
    fallback["top_level_keys"] = list(value.keys())[:_BROWSER_DETAILS_COMPACT_DICT_LIMIT]
    fallback["original_details_chars"] = _browser_details_char_count(value)
    return fallback


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


def _safe_browser_artifact_name(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in value.strip()
    ).strip("-.")
    return normalized[:120] or "browser-artifact"


def _augment_browser_error_with_guidance(
    *,
    deps: BrowserToolDeps,
    profile_name: str,
    exc: BrowserValidationError,
) -> BrowserValidationError:
    message = str(exc).strip().lower()
    if _is_browser_ref_resolution_error(message):
        augmented_message = (
            f"{exc} Next: run browser.observe for the current tab to refresh "
            "interactive refs, then retry browser.action.trace with a fresh ref. "
            "If the target is still missing, use browser.dom.clickability or "
            "browser.dom.inspect before guessing. Reason: browser refs are "
            "ephemeral and scoped to the latest observed tab snapshot."
        )
        if isinstance(exc, BrowserToolApplicationError):
            return exc.with_message(augmented_message)
        return BrowserValidationError(augmented_message)
    if "profile" in message and "not configured" in message:
        missing_profile_guidance = _missing_browser_profile_guidance(
            deps=deps,
            profile_name=profile_name,
        )
        if missing_profile_guidance is not None:
            augmented_message = f"{exc} {missing_profile_guidance}"
            if isinstance(exc, BrowserToolApplicationError):
                return exc.with_message(augmented_message)
            return BrowserValidationError(augmented_message)
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


def _is_browser_ref_resolution_error(message: str) -> bool:
    return (
        "browser ref" in message
        and (
            "was not found" in message
            or "is stale" in message
            or "does not expose a supported locator" in message
            or "frame path" in message
            or "requires nth" in message
        )
    )


def _missing_browser_profile_guidance(
    *,
    deps: BrowserToolDeps,
    profile_name: str,
) -> str | None:
    try:
        system_config = deps.browser_system_config_store.load()
    except Exception:  # noqa: BLE001
        system_config = None
    default_profile = _normalize_text(getattr(system_config, "default_profile", None))
    configured_profiles = _configured_browser_profile_names(system_config)
    if default_profile is not None and default_profile not in configured_profiles:
        configured_profiles = (default_profile, *configured_profiles)
    configured_text = ""
    if configured_profiles:
        configured_text = " Configured profiles: " + ", ".join(configured_profiles[:8]) + "."
    if profile_name.strip().lower() == "default":
        if default_profile is None:
            return (
                "Next: omit the profile argument for normal browser work or choose a "
                "configured profile name. Reason: 'default' is not a Browser profile name."
                f"{configured_text}"
            )
        return (
            "Next: omit the profile argument for normal browser work so the configured "
            f"browser default profile '{default_profile}' is used, or pass a concrete "
            "configured profile name. Reason: 'default' is not a Browser profile name."
            f"{configured_text}"
        )
    if default_profile is not None:
        return (
            "Next: omit the profile argument to use the configured browser default "
            f"profile '{default_profile}', or pass one of the configured profile names."
            f"{configured_text}"
        )
    if configured_profiles:
        return (
            "Next: pass one of the configured browser profile names."
            f"{configured_text}"
        )
    return None


def _configured_browser_profile_names(system_config: Any) -> tuple[str, ...]:
    profiles = getattr(system_config, "profiles", None)
    if profiles is None:
        return ()
    names: list[str] = []
    for profile in profiles:
        name = _normalize_text(getattr(profile, "name", None))
        if name is not None:
            names.append(name)
    return tuple(dict.fromkeys(names))


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


def _execute_observe(
    *,
    deps: BrowserToolDeps,
    tool_id: str,
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> ToolRunResult:
    _ensure_browser_enabled(deps.settings)
    observation_service = deps.browser_observation_service
    if observation_service is None:
        raise BrowserValidationError(
            "browser.observe requires the Browser observation service.",
        )
    resolved_profile = _resolve_browser_profile_for_execution(
        deps=deps,
        arguments=arguments,
        execution_context=execution_context,
    )
    profile_name = resolved_profile.name
    target_id = _normalize_browser_target_id(arguments.get("target_id"))
    timeout_ms = _normalize_timeout(arguments.get("timeout_ms"))
    payload = _normalize_observe_payload(arguments)
    try:
        result = observation_service.observe(
            profile_name=profile_name,
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
    return _tool_result(
        deps=deps,
        tool_id=tool_id,
        content=result.payload,
        family="page-observation",
        profile_name=profile_name,
        profile_source=resolved_profile.allocation_metadata.get(
            "profile_source",
            _profile_source(arguments, execution_context),
        ),
        runtime_metadata={
            **resolved_profile.allocation_metadata,
            **dict(result.runtime_metadata),
        },
        kind="observe",
        execution_context=execution_context,
    )


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


def _normalize_observe_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_snapshot_arguments(arguments)
    payload = dict(normalized.get("payload") or {})
    selector = _normalize_text(arguments.get("selector"))
    if selector is not None:
        payload["selector"] = selector
    for key in (
        "include_tabs",
        "include_console",
        "include_page_errors",
        "include_runtime",
        "include_scripts",
        "include_code_search",
        "include_script_request_matches",
        "include_resource_tree",
        "include_performance_metrics",
        "include_network_capture",
    ):
        value = _normalize_bool(arguments.get(key), label=key)
        if value is not None:
            payload[key] = value
    for key in (
        "console_limit",
        "page_error_limit",
        "console_error_limit",
        "page_exception_limit",
        "runtime_limit",
        "network_limit",
        "script_limit",
        "script_wait_ms",
        "code_search_limit",
        "code_search_max_scripts",
        "code_search_context_lines",
        "script_request_limit",
        "script_request_max_scripts",
        "script_request_context_lines",
    ):
        value = _normalize_int(arguments.get(key), label=key, minimum=1)
        if value is not None:
            payload[key] = value
    for key in (
        "script_url_contains",
        "code_search_query",
        "code_search_url_contains",
        "script_request_query",
        "script_request_url",
        "script_request_path",
    ):
        value = _normalize_text(arguments.get(key))
        if value is not None:
            payload[key] = value
    for key in (
        "code_search_case_sensitive",
        "code_search_regex",
        "script_request_case_sensitive",
    ):
        value = _normalize_bool(arguments.get(key), label=key)
        if value is not None:
            payload[key] = value
    capture_id = _normalize_text(arguments.get("capture_id"))
    if capture_id is not None:
        payload["capture_id"] = capture_id
    return payload


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
    if expression is None:
        expression = _normalize_text(arguments.get("script"))
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
    if kind in _CODE_PAGE_ACTION_KINDS:
        for argument_key, payload_key in (
            ("query", "query"),
            ("text", "query"),
            ("keyword", "query"),
            ("request_url", "request_url"),
            ("requestUrl", "request_url"),
            ("endpoint", "endpoint"),
            ("object_path", "object_path"),
            ("objectPath", "object_path"),
            ("client_path", "object_path"),
            ("clientPath", "object_path"),
            ("method_name", "method_name"),
            ("methodName", "method_name"),
            ("path", "path"),
            ("request_path", "request_path"),
            ("requestPath", "request_path"),
            ("script_id", "script_id"),
            ("scriptId", "script_id"),
            ("url_contains", "url_contains"),
            ("urlContains", "url_contains"),
            ("url", "url_contains"),
        ):
            value = _normalize_text(arguments.get(argument_key))
            if value is not None:
                payload.setdefault(payload_key, value)
        for argument_key, payload_key in (
            ("global_names", "global_names"),
            ("globalNames", "global_names"),
        ):
            raw_value = arguments.get(argument_key)
            if raw_value is not None:
                payload.setdefault(payload_key, raw_value)
        for argument_key, payload_key in (
            ("case_sensitive", "case_sensitive"),
            ("caseSensitive", "case_sensitive"),
            ("regex", "regex"),
            ("use_regex", "regex"),
            ("useRegex", "regex"),
            ("include_storage", "include_storage"),
            ("includeStorage", "include_storage"),
            ("include_performance", "include_performance"),
            ("includePerformance", "include_performance"),
            ("include_source_preview", "include_source_preview"),
            ("includeSourcePreview", "include_source_preview"),
        ):
            value = _normalize_bool(arguments.get(argument_key), label=argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
        for argument_key, payload_key, minimum in (
            ("limit", "limit", 1),
            ("max_scripts", "max_scripts", 1),
            ("maxScripts", "max_scripts", 1),
            ("context_lines", "context_lines", 0),
            ("contextLines", "context_lines", 0),
            ("wait_ms", "wait_ms", 0),
            ("waitMs", "wait_ms", 0),
            ("max_chars", "max_chars", 1),
            ("maxChars", "max_chars", 1),
            ("start_line", "start_line", 1),
            ("startLine", "start_line", 1),
            ("line_count", "line_count", 1),
            ("lineCount", "line_count", 1),
            ("start_column", "start_column", 1),
            ("startColumn", "start_column", 1),
            ("column", "column", 1),
            ("match_column", "match_column", 1),
            ("matchColumn", "match_column", 1),
            ("column_window", "column_window", 80),
            ("columnWindow", "column_window", 80),
            ("preview_chars", "preview_chars", 120),
            ("previewChars", "preview_chars", 120),
            ("max_result_chars", "max_result_chars", 1000),
            ("maxResultChars", "max_result_chars", 1000),
        ):
            value = _normalize_int(arguments.get(argument_key), label=argument_key, minimum=minimum)
            if value is not None:
                payload.setdefault(payload_key, value)
    if kind == "action-trace":
        for argument_key, payload_key in (
            ("action", "action"),
            ("action_kind", "action_kind"),
            ("actionKind", "action_kind"),
            ("action_ref", "action_ref"),
            ("actionRef", "action_ref"),
            ("action_selector", "action_selector"),
            ("actionSelector", "action_selector"),
            ("trace_id", "trace_id"),
            ("traceId", "trace_id"),
            ("capture_id", "capture_id"),
            ("captureId", "capture_id"),
            ("snapshot_format", "snapshot_format"),
            ("snapshotFormat", "snapshot_format"),
            ("snapshot_mode", "snapshot_mode"),
            ("snapshotMode", "snapshot_mode"),
            ("key", "key"),
            ("button", "button"),
            ("load_state", "load_state"),
            ("loadState", "load_state"),
            ("state", "state"),
            ("url", "url"),
            ("expression", "expression"),
            ("fn", "fn"),
        ):
            value = _normalize_text(arguments.get(argument_key))
            if value is not None:
                payload.setdefault(payload_key, value)
        for argument_key, payload_key in (
            ("action_payload", "action_payload"),
            ("actionPayload", "action_payload"),
        ):
            if argument_key not in arguments or arguments.get(argument_key) is None:
                continue
            raw_value = arguments.get(argument_key)
            if not isinstance(raw_value, dict):
                raise BrowserValidationError(f"{argument_key} must be an object.")
            payload.setdefault(payload_key, dict(raw_value))
        if "fields" in arguments and isinstance(arguments.get("fields"), list):
            payload.setdefault("fields", list(arguments["fields"]))
        if "arg" in arguments and arguments.get("arg") is not None:
            payload.setdefault("arg", arguments.get("arg"))
        for argument_key, payload_key in (
            ("include_network", "include_network"),
            ("includeNetwork", "include_network"),
            ("include_storage_diff", "include_storage_diff"),
            ("includeStorageDiff", "include_storage_diff"),
            ("include_lifecycle_diff", "include_lifecycle_diff"),
            ("includeLifecycleDiff", "include_lifecycle_diff"),
            ("active_overlay", "active_overlay"),
            ("activeOverlay", "active_overlay"),
            ("double_click", "double_click"),
            ("doubleClick", "double_click"),
        ):
            value = _normalize_bool(arguments.get(argument_key), label=argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
        for argument_key, payload_key, minimum in (
            ("action_timeout_ms", "action_timeout_ms", 1),
            ("actionTimeoutMs", "action_timeout_ms", 1),
            ("max_requests", "max_requests", 1),
            ("maxRequests", "max_requests", 1),
            ("max_body_bytes", "max_body_bytes", 0),
            ("maxBodyBytes", "max_body_bytes", 0),
            ("network_limit", "network_limit", 1),
            ("networkLimit", "network_limit", 1),
            ("snapshot_limit", "snapshot_limit", 1),
            ("snapshotLimit", "snapshot_limit", 1),
            ("console_limit", "console_limit", 1),
            ("consoleLimit", "console_limit", 1),
            ("page_error_limit", "page_error_limit", 1),
            ("pageErrorLimit", "page_error_limit", 1),
            ("stabilize_ms", "stabilize_ms", 0),
            ("stabilizeMs", "stabilize_ms", 0),
            ("time_ms", "time_ms", 0),
            ("timeMs", "time_ms", 0),
        ):
            value = _normalize_int(arguments.get(argument_key), label=argument_key, minimum=minimum)
            if value is not None:
                payload.setdefault(payload_key, value)
        for argument_key, payload_key in (("x", "x"), ("y", "y")):
            value = _normalize_number(arguments.get(argument_key), label=argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
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
    include_body = _normalize_bool(arguments.get("includeBody"), label="includeBody")
    if include_body is not None:
        payload.setdefault("include_body", include_body)
    if kind == "network-inspect":
        for argument_key, payload_key in (
            ("include_navigation", "include_navigation"),
            ("includeNavigation", "include_navigation"),
            ("include_resources", "include_resources"),
            ("includeResources", "include_resources"),
            ("include_cdp_tree", "include_cdp_tree"),
            ("includeCdpTree", "include_cdp_tree"),
            ("include_performance_metrics", "include_performance_metrics"),
            ("includePerformanceMetrics", "include_performance_metrics"),
        ):
            value = _normalize_bool(arguments.get(argument_key), label=argument_key)
            if value is not None:
                payload.setdefault(payload_key, value)
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


def create_browser_observe_handler(
    factory_deps: BrowserToolDeps | Any,
    *,
    tool_id: str = "browser.observe",
    defaults: Mapping[str, Any] | None = None,
):
    deps = _coerce_tool_deps(factory_deps)
    if deps is None or deps.browser_observation_service is None:
        return None
    default_arguments = dict(defaults or {})

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        merged_arguments = {**default_arguments, **dict(arguments)}
        return await asyncio.to_thread(
            _execute_observe,
            deps=deps,
            tool_id=tool_id,
            arguments=merged_arguments,
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


def create_browser_manifest_handler(factory_deps: Any):
    """Build the handler declared by tools/browser/tool.yaml."""

    deps = _browser_tool_deps_from_factory_deps(factory_deps)
    if deps is None:
        return None
    tool_id = factory_deps.tool_id
    if tool_id == "browser.observe":
        return create_browser_observe_handler(deps, tool_id=tool_id)
    if tool_id == "browser.form.inspect":
        return create_browser_observe_handler(
            deps,
            tool_id=tool_id,
            defaults={
                "format": "interactive",
                "mode": "wide",
                "include_tabs": False,
                "include_console": False,
                "include_runtime": False,
                "include_scripts": False,
                "limit": 40,
            },
        )
    if tool_id == "browser.overlay.observe":
        return create_browser_observe_handler(
            deps,
            tool_id=tool_id,
            defaults={
                "format": "interactive",
                "mode": "wide",
                "active_overlay": True,
                "include_tabs": False,
                "include_console": False,
                "include_runtime": False,
                "include_scripts": False,
                "limit": 40,
            },
        )
    if tool_id == "browser.snapshot":
        return create_browser_snapshot_handler(deps, tool_id=tool_id)
    if tool_id in _BROWSER_MANIFEST_CONTROL_KINDS:
        handler = create_browser_control_handler(deps, tool_id=tool_id)
        return _browser_with_kind(handler, _BROWSER_MANIFEST_CONTROL_KINDS[tool_id])
    if tool_id in _BROWSER_MANIFEST_CONTEXT_ACTIONS:
        return create_browser_context_handler(
            deps,
            tool_id=tool_id,
            action=_BROWSER_MANIFEST_CONTEXT_ACTIONS[tool_id],
        )
    if tool_id.startswith("browser.network."):
        return create_browser_network_handler(deps, tool_id=tool_id)
    if tool_id == "browser.form.fill":
        return _browser_form_fill_handler(
            create_browser_page_action_handler(deps, tool_id=tool_id),
        )
    if tool_id == "browser.overlay.select":
        return _browser_overlay_select_handler(
            create_browser_page_action_handler(deps, tool_id=tool_id),
        )
    if tool_id == "browser.native.run":
        return _browser_native_run_handler(
            create_browser_page_action_handler(deps, tool_id=tool_id),
        )
    if tool_id in _BROWSER_MANIFEST_PAGE_ACTION_KINDS:
        handler = create_browser_page_action_handler(deps, tool_id=tool_id)
        return _browser_with_kind(handler, _BROWSER_MANIFEST_PAGE_ACTION_KINDS[tool_id])
    raise BrowserValidationError(f"Unsupported Browser manifest tool id: {tool_id}")


_BROWSER_MANIFEST_CONTROL_KINDS = {
    "browser.navigate": "navigate",
    "browser.tabs.list": "list-tabs",
    "browser.tabs.select": "focus-tab",
    "browser.tabs.close": "close-tab",
}

_BROWSER_MANIFEST_CONTEXT_ACTIONS = {
    "browser.context.acquire": "acquire",
    "browser.context.current": "current",
    "browser.context.heartbeat": "heartbeat",
    "browser.context.release": "release",
    "browser.context.reconcile": "reconcile",
}

_BROWSER_MANIFEST_PAGE_ACTION_KINDS = {
    "browser.action.trace": "action-trace",
    "browser.click": "click",
    "browser.type": "type",
    "browser.evaluate": "evaluate",
    "browser.screenshot": "screenshot",
    "browser.dom.inspect": "dom-inspect",
    "browser.dom.box_model": "dom-box-model",
    "browser.dom.computed_style": "dom-computed-style",
    "browser.dom.clickability": "dom-clickability",
    "browser.dom.highlight": "dom-highlight",
    "browser.dom.mutation_wait": "dom-mutation-wait",
    "browser.storage.indexeddb.list": "storage-indexeddb-list",
    "browser.storage.indexeddb.get": "storage-indexeddb-get",
    "browser.storage.indexeddb.query": "storage-indexeddb-query",
    "browser.storage.cache.list": "storage-cache-list",
    "browser.storage.cache.get": "storage-cache-get",
    "browser.service_worker.list": "service-worker-list",
    "browser.service_worker.inspect": "service-worker-inspect",
    "browser.emulation.set": "emulation-set",
    "browser.emulation.reset": "emulation-reset",
    "browser.permissions.grant": "permissions-grant",
    "browser.permissions.clear": "permissions-clear",
    "browser.geolocation.set": "geolocation-set",
    "browser.network_conditions.set": "network-conditions-set",
    "browser.diagnostics.collect": "diagnostics-collect",
    "browser.performance.metrics": "performance-metrics",
    "browser.trace.start": "trace-start",
    "browser.trace.stop": "trace-stop",
    "browser.trace.export": "trace-export",
    "browser.page.lifecycle": "page-lifecycle",
    "browser.page.errors": "page-errors",
    "browser.runtime.inspect": "runtime-inspect",
    "browser.script.list": "script-list",
    "browser.script.find_request": "script-find-request",
    "browser.code.search": "code-search",
    "browser.script.extract_request": "script-extract-request",
    "browser.script.inspect": "script-inspect",
}


def _browser_tool_deps_from_factory_deps(
    factory_deps: Any,
) -> BrowserToolDeps | None:
    services = factory_deps.services
    required = (
        "browser_tool_application",
        "browser_system_config_store",
        "browser_profile_resolver",
        "browser_capabilities_resolver",
    )
    if any(services.get(key) is None for key in required):
        return None
    return BrowserToolDeps(
        browser_tool_application=services["browser_tool_application"],
        browser_system_config_store=services["browser_system_config_store"],
        browser_profile_resolver=services["browser_profile_resolver"],
        browser_capabilities_resolver=services["browser_capabilities_resolver"],
        browser_observation_service=services.get("browser_observation_service"),
        settings=services.get("settings"),
        artifact_service=services.get("artifact_service"),
        browser_runtime_state_store=services.get("browser_runtime_state_store"),
        browser_profile_probe_service=services.get("browser_profile_probe_service"),
        browser_profile_allocator_service=services.get(
            "browser_profile_allocator_service",
        ),
    )


def _browser_with_kind(handler, kind: str):
    if handler is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ):
        payload = dict(arguments)
        payload["kind"] = kind
        return await handler(payload, execution_context)

    return _handler


def _browser_native_run_handler(handler):
    if handler is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ):
        payload = dict(arguments)
        batch_payload = payload.get("payload")
        if not isinstance(batch_payload, dict):
            batch_payload = {}
        else:
            batch_payload = dict(batch_payload)
        if "actions" in payload and payload["actions"] is not None:
            batch_payload.setdefault("actions", payload["actions"])
        if "stop_on_error" in payload and payload["stop_on_error"] is not None:
            batch_payload.setdefault("stop_on_error", payload["stop_on_error"])
        payload["payload"] = batch_payload
        payload["kind"] = "batch"
        return await handler(payload, execution_context)

    return _handler


def _browser_form_fill_handler(handler):
    if handler is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ):
        payload = dict(arguments)
        payload["kind"] = "action-trace"
        payload.setdefault("action", "fill")
        payload.setdefault("include_network", True)
        payload.setdefault("include_lifecycle_diff", True)
        payload.setdefault("include_storage_diff", True)
        payload.setdefault("snapshot_limit", 30)
        payload.setdefault("stabilize_ms", 200)
        return await handler(payload, execution_context)

    return _handler


def _browser_overlay_select_handler(handler):
    if handler is None:
        return None

    async def _handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ):
        payload = dict(arguments)
        payload["kind"] = "action-trace"
        payload.setdefault("action", "click")
        payload.setdefault("active_overlay", True)
        payload.setdefault("include_network", True)
        payload.setdefault("include_lifecycle_diff", True)
        payload.setdefault("include_storage_diff", True)
        payload.setdefault("snapshot_limit", 30)
        payload.setdefault("stabilize_ms", 200)
        _merge_overlay_select_action_payload(payload)
        return await handler(payload, execution_context)

    return _handler


def _merge_overlay_select_action_payload(payload: dict[str, Any]) -> None:
    raw_action_payload = payload.get("action_payload")
    if raw_action_payload is None:
        raw_action_payload = payload.get("actionPayload")
    if raw_action_payload is not None and not isinstance(raw_action_payload, dict):
        return

    action_payload = dict(raw_action_payload or {})
    action_payload.setdefault("active_overlay", True)
    for key in (
        "overlay_source_ref",
        "overlay_source_selector",
        "overlay_source_scope_selector",
        "exact",
        "ordinal",
        "button",
        "double_click",
    ):
        if key in payload and payload[key] is not None:
            action_payload[key] = payload[key]
    payload["action_payload"] = action_payload
