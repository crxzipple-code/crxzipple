from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserControlCommand,
    BrowserPageActionCommand,
    BrowserTab,
    BrowserValidationError,
)

from .ports import (
    BrowserControlCommandAssembler,
    BrowserExecutionCoordinator,
    BrowserPageActionAssembler,
    BrowserRuntimeStateStore,
)


@dataclass(frozen=True, slots=True)
class BrowserToolExecutionResult:
    payload: dict[str, Any]
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "runtime_metadata", dict(self.runtime_metadata))


@dataclass(frozen=True, slots=True)
class BrowserToolExecutionError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    setup_required: bool = False

    def __post_init__(self) -> None:
        normalized_code = _optional_text(self.code) or "browser_execution_failed"
        normalized_message = _optional_text(self.message) or "Browser tool execution failed."
        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "message", normalized_message)
        object.__setattr__(self, "details", _safe_details(self.details))
        object.__setattr__(self, "retryable", bool(self.retryable))
        object.__setattr__(self, "setup_required", bool(self.setup_required))

    def to_payload(self) -> dict[str, Any]:
        return {
            **dict(self.details),
            "message": self.message,
            "code": self.code,
            "category": "browser",
            "retryable": self.retryable,
            "setup_required": self.setup_required,
        }


class BrowserToolApplicationError(BrowserValidationError):
    """Display-safe browser tool error returned by the browser application port."""

    def __init__(self, error: BrowserToolExecutionError) -> None:
        super().__init__(error.message)
        self.error = error

    def with_message(self, message: str) -> "BrowserToolApplicationError":
        return BrowserToolApplicationError(replace(self.error, message=message))

    def to_payload(self) -> dict[str, Any]:
        return self.error.to_payload()


@dataclass(slots=True)
class BrowserToolApplicationService:
    control_command_assembler: BrowserControlCommandAssembler
    page_action_assembler: BrowserPageActionAssembler
    execution_coordinator: BrowserExecutionCoordinator
    runtime_state_store: BrowserRuntimeStateStore

    def execute_control(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserToolExecutionResult:
        command = self.control_command_assembler.assemble(
            profile_name=profile_name,
            kind=kind,
            target_id=target_id,
            payload=payload,
            timeout_ms=timeout_ms,
        )
        return self._execute(command)

    def execute_page_action(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        ref: str | None = None,
        selector: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserToolExecutionResult:
        command = self.page_action_assembler.assemble(
            profile_name=profile_name,
            kind=kind,
            target_id=target_id,
            ref=ref,
            selector=selector,
            payload=payload,
            timeout_ms=timeout_ms,
        )
        return self._execute(command)

    def _execute(
        self,
        command: BrowserControlCommand | BrowserPageActionCommand,
    ) -> BrowserToolExecutionResult:
        try:
            result = self.execution_coordinator.execute(command)
        except BrowserToolApplicationError:
            raise
        except BrowserValidationError as exc:
            raise BrowserToolApplicationError(
                self._browser_tool_error_from_exception(exc, command=command),
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise BrowserToolApplicationError(
                self._browser_tool_error_from_exception(exc, command=command),
            ) from exc
        return BrowserToolExecutionResult(
            payload=self._serialize_result(result),
            runtime_metadata=self._runtime_metadata(
                profile_name=command.profile_name,
                target_id=result.target_id or _command_target_id(command),
            ),
        )

    def _browser_tool_error_from_exception(
        self,
        exc: Exception,
        *,
        command: BrowserControlCommand | BrowserPageActionCommand,
    ) -> BrowserToolExecutionError:
        try:
            runtime_state = self.runtime_state_store.get(
                profile_name=command.profile_name.strip().lower(),
            )
        except Exception:  # noqa: BLE001
            runtime_state = None
        return _browser_tool_error_from_exception(
            exc,
            command=command,
            runtime_state=runtime_state,
        )

    def _runtime_metadata(
        self,
        *,
        profile_name: str,
        target_id: str | None,
    ) -> dict[str, Any]:
        normalized_profile = profile_name.strip().lower()
        metadata: dict[str, Any] = {
            "browser_host_service_key": f"host:browser:{normalized_profile}",
        }
        runtime_state = self.runtime_state_store.get(profile_name=normalized_profile)
        if runtime_state is None:
            return metadata
        host_generation = runtime_state.host_generation()
        if host_generation is not None:
            metadata["browser_host_generation"] = host_generation
        resolved_target_id = _optional_text(target_id) or runtime_state.last_target_id
        if resolved_target_id is None:
            return metadata
        metadata["browser_target_id"] = resolved_target_id
        page_state = runtime_state.page_state(target_id=resolved_target_id)
        if not isinstance(page_state, dict):
            return metadata
        for metadata_key, state_key in (
            ("browser_page_generation", "page_generation"),
            ("browser_snapshot_generation", "snapshot_generation"),
            ("browser_current_ref_generation", "current_ref_generation"),
        ):
            value = _positive_int(page_state.get(state_key))
            if value is not None:
                metadata[metadata_key] = value
        page_reason = _optional_text(page_state.get("page_generation_reason"))
        if page_reason is not None:
            metadata["browser_page_generation_reason"] = page_reason
        return metadata

    def _serialize_result(self, result: BrowserActionResult) -> dict[str, Any]:
        value = self._serialize_value(result.value)
        if isinstance(result.command, BrowserControlCommand):
            value = _attach_control_action_envelope(
                command=result.command,
                target_id=result.target_id,
                value=value,
                tool_ok=result.ok,
            )
        return {
            "ok": result.ok,
            "target_id": result.target_id,
            "message": result.message,
            "command": self._serialize_command(result.command),
            "value": value,
        }

    def _serialize_command(
        self,
        command: BrowserControlCommand | BrowserPageActionCommand,
    ) -> dict[str, Any]:
        if isinstance(command, BrowserControlCommand):
            return {
                "family": "control",
                "profile_name": command.profile_name,
                "kind": command.kind,
                "target_id": command.target_id,
                "payload": dict(command.payload),
                "timeout_ms": command.timeout_ms,
            }
        return {
            "family": "page-action",
            "profile_name": command.profile_name,
            "kind": command.kind,
            "target": {
                "target_id": command.target.target_id,
                "ref": command.target.ref,
                "selector": command.target.selector,
            },
            "payload": dict(command.payload),
            "timeout_ms": command.timeout_ms,
        }

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, BrowserTab):
            return {
                "target_id": value.target_id,
                "url": value.url,
                "title": value.title,
                "type": value.type,
                "ws_url": value.ws_url,
                "json_endpoints": dict(value.json_endpoints) if value.json_endpoints else None,
            }
        if isinstance(value, tuple | list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        return value


def _command_target_id(command: BrowserControlCommand | BrowserPageActionCommand) -> str | None:
    if isinstance(command, BrowserControlCommand):
        return command.target_id
    return command.target.target_id


def _attach_control_action_envelope(
    *,
    command: BrowserControlCommand,
    target_id: str | None,
    value: Any,
    tool_ok: bool,
) -> Any:
    if command.kind not in {"open-tab", "navigate-tab"}:
        return value
    if not isinstance(value, dict):
        return value
    after = {
        key: value.get(key)
        for key in ("target_id", "url", "title", "type")
        if value.get(key) is not None
    }
    if target_id is not None:
        after.setdefault("target_id", target_id)
    page_effect_ok = bool(after.get("url"))
    value["action_envelope"] = {
        "kind": command.kind,
        "tool_ok": bool(tool_ok),
        "page_effect_ok": page_effect_ok,
        "page_effect_status": (
            "observed_change" if page_effect_ok else "no_observable_change"
        ),
        "before": {
            "target_id": command.target_id,
        }
        if command.target_id is not None
        else {},
        "after": after,
        "changes": {
            "url": {
                "before": None,
                "after": after.get("url"),
            },
        }
        if after.get("url") is not None
        else {},
        "result": {
            "target_id": after.get("target_id"),
            "url": after.get("url"),
        },
        "next_action": (
            "observe-current-state"
            if page_effect_ok
            else "use-action-trace-or-observe"
        ),
        "errors": [],
    }
    return value


def _browser_tool_error_from_exception(
    exc: Exception,
    *,
    command: BrowserControlCommand | BrowserPageActionCommand,
    runtime_state: Any | None = None,
) -> BrowserToolExecutionError:
    message = _safe_error_message(str(exc))
    code, retryable, setup_required = _classify_browser_error(message)
    details: dict[str, Any] = {
        "profile": command.profile_name,
        "family": "control" if isinstance(command, BrowserControlCommand) else "page-action",
        "kind": command.kind,
    }
    target_id = _command_target_id(command)
    if target_id is not None:
        details["target_id"] = target_id
    recovery = _browser_recovery_details(
        command=command,
        runtime_state=runtime_state,
        message=message,
        code=code,
    )
    if recovery:
        details["browser_recovery"] = recovery
    return BrowserToolExecutionError(
        code=code,
        message=message,
        details=details,
        retryable=retryable,
        setup_required=setup_required,
    )


def _classify_browser_error(message: str) -> tuple[str, bool, bool]:
    normalized = message.lower()
    if "not configured" in normalized:
        return "browser_profile_not_configured", False, True
    if "module is disabled" in normalized:
        return "browser_disabled", False, True
    if (
        "requires runtime setup" in normalized
        or "no ready instance" in normalized
        or "host:browser:" in normalized
        or "does not define a cdp url" in normalized
        or "connection refused" in normalized
        or "failed to connect" in normalized
        or "not running" in normalized
        or "has not started" in normalized
    ):
        return "browser_runtime_not_ready", True, True
    if "timeout" in normalized or "timed out" in normalized:
        return "browser_timeout", True, False
    if (
        "requires ref or selector targeting" in normalized
        or ("browser ref '" in normalized and "was not found" in normalized)
        or ("browser ref '" in normalized and "is stale" in normalized)
    ):
        return "browser_ref_not_available", True, False
    if "tab '" in normalized and "was not found" in normalized:
        return "browser_target_not_found", False, False
    if "tab '" in normalized and "not available through playwright cdp" in normalized:
        return "browser_target_not_found", True, False
    if "no browser tabs are available" in normalized:
        return "browser_target_not_found", False, False
    if "unsupported" in normalized:
        return "browser_unsupported_action", False, False
    return "browser_execution_failed", False, False


def _browser_recovery_details(
    *,
    command: BrowserControlCommand | BrowserPageActionCommand,
    runtime_state: Any | None,
    message: str,
    code: str,
) -> dict[str, Any]:
    if runtime_state is None:
        return {}

    target_id = _command_target_id(command)
    ref = command.target.ref if isinstance(command, BrowserPageActionCommand) else None
    requested_ref = _optional_text(ref) or _extract_browser_ref(message)
    if code == "browser_ref_not_available":
        return _browser_ref_recovery_details(
            command=command,
            runtime_state=runtime_state,
            target_id=target_id,
            requested_ref=requested_ref,
        )
    if code == "browser_target_not_found":
        return _browser_target_recovery_details(
            runtime_state=runtime_state,
            requested_target_id=target_id,
        )
    return {}


def _browser_target_recovery_details(
    *,
    runtime_state: Any,
    requested_target_id: str | None,
) -> dict[str, Any]:
    active_target_id = _optional_text(_runtime_metadata_value(runtime_state, "active_target_id"))
    last_target_id = _optional_text(getattr(runtime_state, "last_target_id", None))
    tabs = _runtime_page_tabs(runtime_state)
    details: dict[str, Any] = {
        "next_action": "refresh-browser-observation",
        "reason": (
            "Browser target ids are runtime handles. Refresh the tab list or observe the "
            "active page before retrying with a stale target_id."
        ),
        "recommended_tools": ["browser.tabs.list", "browser.observe"],
        "retry_without_target_id": active_target_id is not None or bool(tabs.get("items")),
        "available_tabs": tabs,
    }
    if requested_target_id is not None:
        details["requested_target_id"] = requested_target_id
    if active_target_id is not None:
        details["active_target_id"] = active_target_id
        details["retry_target_id"] = active_target_id
    if last_target_id is not None:
        details["last_target_id"] = last_target_id
    return details


def _browser_ref_recovery_details(
    *,
    command: BrowserControlCommand | BrowserPageActionCommand,
    runtime_state: Any,
    target_id: str | None,
    requested_ref: str | None,
) -> dict[str, Any]:
    resolved_target_id = (
        _optional_text(target_id)
        or _optional_text(_runtime_metadata_value(runtime_state, "active_target_id"))
        or _optional_text(getattr(runtime_state, "last_target_id", None))
    )
    page_state = _runtime_page_state(runtime_state, target_id=resolved_target_id)
    details: dict[str, Any] = {
        "next_action": "refresh-interactive-refs",
        "reason": (
            "Browser refs belong to the latest interactive observation for a page. "
            "Run browser.observe before retrying a ref-based action."
        ),
        "recommended_tools": ["browser.observe", "browser.dom.clickability"],
        "retry_with_selector": (
            isinstance(command, BrowserPageActionCommand)
            and _optional_text(command.target.selector) is not None
        ),
        "available_tabs": _runtime_page_tabs(runtime_state),
    }
    if requested_ref is not None:
        details["requested_ref"] = requested_ref
    if resolved_target_id is not None:
        details["target_id"] = resolved_target_id
    generation = _positive_int(page_state.get("current_ref_generation")) if page_state else None
    if generation is not None:
        details["current_ref_generation"] = generation
    snapshot_generation = _positive_int(page_state.get("snapshot_generation")) if page_state else None
    if snapshot_generation is not None:
        details["snapshot_generation"] = snapshot_generation
    return details


def _runtime_page_tabs(runtime_state: Any) -> dict[str, Any]:
    raw_tabs = _runtime_metadata_value(runtime_state, "tabs")
    if not isinstance(raw_tabs, list):
        return {"count": 0, "items": [], "has_more": False}
    active_target_id = _optional_text(_runtime_metadata_value(runtime_state, "active_target_id"))
    last_target_id = _optional_text(getattr(runtime_state, "last_target_id", None))
    tabs = []
    for item in raw_tabs:
        if not isinstance(item, Mapping):
            continue
        target_id = _optional_text(item.get("target_id"))
        if target_id is None:
            continue
        tab_type = _optional_text(item.get("type")) or "page"
        if tab_type != "page":
            continue
        payload = {
            "target_id": target_id,
            "type": tab_type,
            "title": _truncate_text(_optional_text(item.get("title")), 80),
            "url": _safe_tab_url(item.get("url")),
            "is_active": target_id == active_target_id,
            "is_last": target_id == last_target_id,
        }
        tabs.append({key: value for key, value in payload.items() if value is not None})
    limit = 8
    return {
        "count": len(tabs),
        "items": tabs[:limit],
        "has_more": len(tabs) > limit,
    }


def _runtime_page_state(runtime_state: Any, *, target_id: str | None) -> dict[str, Any] | None:
    normalized_target = _optional_text(target_id)
    if normalized_target is None or not hasattr(runtime_state, "page_state"):
        return None
    try:
        page_state = runtime_state.page_state(target_id=normalized_target)
    except Exception:  # noqa: BLE001
        return None
    return dict(page_state) if isinstance(page_state, Mapping) else None


def _runtime_metadata_value(runtime_state: Any, key: str) -> Any:
    metadata = getattr(runtime_state, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    return metadata.get(key)


def _extract_browser_ref(message: str) -> str | None:
    match = re.search(r"Browser ref '([^']+)'", message)
    return _optional_text(match.group(1)) if match else None


def _safe_tab_url(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return _truncate_text(text, 180)
    if parsed.scheme and parsed.netloc:
        hostname = parsed.hostname or parsed.netloc
        netloc = hostname
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port is not None:
            netloc = f"{netloc}:{port}"
        path = _truncate_text(parsed.path or "/", 140) or "/"
        return urlunsplit((parsed.scheme, netloc, path, "", ""))
    return _truncate_text(text, 180)


def _truncate_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return f"{value[: max(limit - 1, 0)]}..."


def _safe_error_message(value: str) -> str:
    normalized = " ".join(str(value).split())
    return normalized[:600] or "Browser tool execution failed."


def _safe_details(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _safe_detail_value(item) for key, item in value.items()}


def _safe_detail_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return _safe_details(value)
    if isinstance(value, tuple | list):
        return [_safe_detail_value(item) for item in value]
    return str(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _positive_int(value: Any) -> int | None:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None
