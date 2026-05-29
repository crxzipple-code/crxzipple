from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

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
                _browser_tool_error_from_exception(exc, command=command),
            ) from exc
        return BrowserToolExecutionResult(
            payload=self._serialize_result(result),
            runtime_metadata=self._runtime_metadata(
                profile_name=command.profile_name,
                target_id=result.target_id or _command_target_id(command),
            ),
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
        return {
            "ok": result.ok,
            "target_id": result.target_id,
            "message": result.message,
            "command": self._serialize_command(result.command),
            "value": self._serialize_value(result.value),
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


def _browser_tool_error_from_exception(
    exc: BrowserValidationError,
    *,
    command: BrowserControlCommand | BrowserPageActionCommand,
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
    if "tab '" in normalized and "was not found" in normalized:
        return "browser_target_not_found", False, False
    if "tab '" in normalized and "not available through playwright cdp" in normalized:
        return "browser_target_not_found", True, False
    if "no browser tabs are available" in normalized:
        return "browser_target_not_found", False, False
    if "unsupported" in normalized:
        return "browser_unsupported_action", False, False
    return "browser_execution_failed", False, False


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
