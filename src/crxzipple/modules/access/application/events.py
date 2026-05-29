from __future__ import annotations

from typing import Any, Mapping, Protocol

from crxzipple.shared.domain.events import Event

ACCESS_ACTION_REQUESTED_EVENT = "access.action.requested"
ACCESS_ACTION_SUCCEEDED_EVENT = "access.action.succeeded"
ACCESS_ACTION_FAILED_EVENT = "access.action.failed"
ACCESS_SETUP_STARTED_EVENT = "access.setup.started"
ACCESS_SETUP_COMPLETED_EVENT = "access.setup.completed"
ACCESS_SETUP_FAILED_EVENT = "access.setup.failed"
ACCESS_CREDENTIAL_CONFIGURED_EVENT = "access.credential.configured"
ACCESS_CREDENTIAL_DISABLED_EVENT = "access.credential.disabled"
ACCESS_CREDENTIAL_REVOKED_EVENT = "access.credential.revoked"
ACCESS_CREDENTIAL_ROTATED_EVENT = "access.credential.rotated"
ACCESS_CREDENTIAL_FAILED_EVENT = "access.credential.failed"
ACCESS_CREDENTIAL_RESOLVE_REQUESTED_EVENT = "access.credential.resolve.requested"
ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT = "access.credential.resolve.succeeded"
ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT = "access.credential.resolve.failed"
ACCESS_CREDENTIAL_LEASE_GRANTED_EVENT = "access.credential.lease.granted"
ACCESS_CREDENTIAL_LEASE_DENIED_EVENT = "access.credential.lease.denied"

ACCESS_OPERATION_EVENT_NAMES: tuple[str, ...] = (
    ACCESS_ACTION_REQUESTED_EVENT,
    ACCESS_ACTION_SUCCEEDED_EVENT,
    ACCESS_ACTION_FAILED_EVENT,
    ACCESS_SETUP_STARTED_EVENT,
    ACCESS_SETUP_COMPLETED_EVENT,
    ACCESS_SETUP_FAILED_EVENT,
    ACCESS_CREDENTIAL_CONFIGURED_EVENT,
    ACCESS_CREDENTIAL_DISABLED_EVENT,
    ACCESS_CREDENTIAL_REVOKED_EVENT,
    ACCESS_CREDENTIAL_ROTATED_EVENT,
    ACCESS_CREDENTIAL_FAILED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_REQUESTED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT,
    ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
    ACCESS_CREDENTIAL_LEASE_GRANTED_EVENT,
    ACCESS_CREDENTIAL_LEASE_DENIED_EVENT,
)


class AccessEventPublisher(Protocol):
    def publish(self, event: Event) -> None: ...


SENSITIVE_ACCESS_EVENT_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "client_secret",
        "credential",
        "credential_value",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "source_ref",
        "storage_key",
        "token",
    },
)


def publish_access_event(
    event_publisher: AccessEventPublisher | None,
    event_name: str,
    *,
    status: str,
    level: str = "info",
    target_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    trace_context: Mapping[str, Any] | None = None,
) -> None:
    if event_publisher is None:
        return
    normalized_name = event_name.strip()
    if not normalized_name:
        return
    normalized_target = (target_id or "").strip()
    event_payload: dict[str, Any] = {
        "event_name": normalized_name,
        "status": status,
        "level": level,
        **dict(payload or {}),
    }
    if normalized_target:
        event_payload.setdefault("resource_id", normalized_target)
        event_payload.setdefault("target_id", normalized_target)
    safe_trace = _safe_trace(trace_context)
    if safe_trace:
        event_payload.setdefault("trace_context", safe_trace)
    try:
        event_publisher.publish(
            Event(
                name=normalized_name,
                kind="fact",
                payload=_redact_payload(event_payload),
                trace=safe_trace,
                ordering_key=normalized_target or None,
            ),
        )
    except Exception:
        return


def _safe_trace(trace_context: Mapping[str, Any] | None) -> dict[str, Any]:
    if not trace_context:
        return {}
    safe: dict[str, Any] = {}
    for key in ("trace_id", "correlation_id", "request_id", "run_id", "tool_run_id", "invocation_id"):
        value = trace_context.get(key)
        if isinstance(value, str) and value.strip():
            safe[key] = value.strip()
    return safe


def _redact_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                result[key_text] = "***"
            else:
                result[key_text] = _redact_payload(item)
        return result
    if isinstance(value, tuple):
        return tuple(_redact_payload(item) for item in value)
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    if normalized in SENSITIVE_ACCESS_EVENT_KEYS:
        return True
    return any(
        normalized.endswith(f"_{suffix}")
        for suffix in SENSITIVE_ACCESS_EVENT_KEYS
    )


__all__ = [
    "ACCESS_ACTION_FAILED_EVENT",
    "ACCESS_ACTION_REQUESTED_EVENT",
    "ACCESS_ACTION_SUCCEEDED_EVENT",
    "ACCESS_CREDENTIAL_CONFIGURED_EVENT",
    "ACCESS_CREDENTIAL_DISABLED_EVENT",
    "ACCESS_CREDENTIAL_FAILED_EVENT",
    "ACCESS_CREDENTIAL_LEASE_DENIED_EVENT",
    "ACCESS_CREDENTIAL_LEASE_GRANTED_EVENT",
    "ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT",
    "ACCESS_CREDENTIAL_RESOLVE_REQUESTED_EVENT",
    "ACCESS_CREDENTIAL_RESOLVE_SUCCEEDED_EVENT",
    "ACCESS_CREDENTIAL_REVOKED_EVENT",
    "ACCESS_CREDENTIAL_ROTATED_EVENT",
    "ACCESS_OPERATION_EVENT_NAMES",
    "ACCESS_SETUP_COMPLETED_EVENT",
    "ACCESS_SETUP_FAILED_EVENT",
    "ACCESS_SETUP_STARTED_EVENT",
    "AccessEventPublisher",
    "publish_access_event",
]
