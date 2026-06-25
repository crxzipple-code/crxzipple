from __future__ import annotations

from typing import Any, Mapping

from crxzipple.shared.access import AccessConsumerRef


def safe_source_ref(source_kind: object, source_ref: object) -> str | None:
    normalized_kind = str(source_kind or "").strip().lower()
    normalized_ref = str(source_ref or "").strip()
    if not normalized_ref:
        return None
    if normalized_kind == "oauth_account":
        return normalized_ref
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    return "***"


def source_metadata(source_kind: object, source_ref: object) -> dict[str, object]:
    normalized_kind = str(source_kind or "").strip().lower()
    normalized_ref = str(source_ref or "").strip()
    metadata: dict[str, object] = {
        "source_kind": normalized_kind or None,
        "configured": bool(normalized_ref),
        "source_ref_redacted": bool(normalized_ref),
    }
    if normalized_kind == "env" and normalized_ref:
        metadata["reference_kind"] = "environment_variable"
    elif normalized_kind == "file" and normalized_ref:
        metadata["reference_kind"] = "file_path"
    elif normalized_kind == "oauth_account" and normalized_ref:
        metadata["source_ref_redacted"] = False
    return metadata


def safe_masked_preview(source_kind: object, masked_preview: object) -> str | None:
    normalized_preview = str(masked_preview or "").strip()
    if not normalized_preview:
        return None
    normalized_kind = str(source_kind or "").strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return normalized_preview


def credential_record_audit_context(
    record: object,
    *,
    binding_id: str,
    consumer: AccessConsumerRef | None,
    trace_context: Mapping[str, object] | None,
) -> dict[str, Any]:
    source_kind = getattr(record, "source_kind", None)
    source_ref = getattr(record, "source_ref", None)
    context: dict[str, Any] = {
        "credential_binding_id": binding_id.strip(),
        "binding_kind": getattr(record, "binding_kind", None),
        "source_kind": source_kind,
        "asset_id": getattr(record, "asset_id", None),
        "status": getattr(record, "status", None),
        "masked_preview": safe_masked_preview(
            source_kind,
            getattr(record, "masked_preview", None),
        ),
        "source_ref": safe_source_ref(source_kind, source_ref),
        "source_metadata": source_metadata(source_kind, source_ref),
    }
    if consumer is not None:
        context["consumer"] = consumer_audit_context(consumer)
    safe_trace = safe_trace_context(trace_context)
    if safe_trace:
        context["trace_context"] = safe_trace
    return context


def direct_credential_audit_context(
    binding_value: str,
    *,
    consumer: AccessConsumerRef | None,
    trace_context: Mapping[str, object] | None,
    allow_literal: bool,
) -> dict[str, Any]:
    source_kind, source_ref = source_kind_and_ref(
        binding_value,
        allow_literal=allow_literal,
    )
    context: dict[str, Any] = {
        "credential_binding_id": None,
        "source_kind": source_kind,
        "source_ref": safe_source_ref(source_kind, source_ref),
        "source_metadata": source_metadata(source_kind, source_ref),
    }
    if consumer is not None:
        context["consumer"] = consumer_audit_context(consumer)
    safe_trace = safe_trace_context(trace_context)
    if safe_trace:
        context["trace_context"] = safe_trace
    return context


def source_kind_and_ref(
    binding_value: str,
    *,
    allow_literal: bool,
) -> tuple[str, str]:
    normalized = binding_value.strip()
    if normalized.startswith("env:"):
        return "env", normalized.removeprefix("env:")
    if normalized.startswith("file:"):
        return "file", normalized.removeprefix("file:")
    if normalized.startswith("oauth_account:"):
        return "oauth_account", normalized.removeprefix("oauth_account:")
    if normalized.startswith("app_credential:"):
        return "app_credential", normalized.removeprefix("app_credential:")
    if allow_literal:
        return "literal", normalized
    return "binding", normalized


def consumer_audit_context(consumer: AccessConsumerRef) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "consumer_id": consumer.consumer_id,
        "module": consumer.module,
    }
    if consumer.component:
        payload["component"] = consumer.component
    if consumer.runtime_ref:
        payload["runtime_ref"] = consumer.runtime_ref
    if consumer.metadata:
        payload["metadata"] = safe_audit_value(consumer.metadata)
    return payload


def event_binding_id(binding_value: object) -> str:
    return str(binding_value or "").strip()


def credential_resolution_event_payload(
    *,
    binding_id: str,
    expected_kind: str | None,
    consumer: AccessConsumerRef | None,
    allow_literal: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "binding_id": binding_id,
        "credential_binding_id": binding_id,
        "expected_kind": expected_kind,
        "allow_literal": allow_literal,
    }
    if consumer is not None:
        payload["consumer"] = consumer_audit_context(consumer)
        payload["consumer_module"] = consumer.module
        payload["consumer_id"] = consumer.consumer_id
    return payload


def safe_trace_context(
    trace_context: Mapping[str, object] | None,
) -> dict[str, Any]:
    if not trace_context:
        return {}
    return {
        str(key): safe_audit_value(value, key=str(key))
        for key, value in trace_context.items()
    }


def safe_audit_value(value: object, *, key: str | None = None) -> Any:
    if key is not None and is_sensitive_audit_key(key):
        return "***"
    if isinstance(value, Mapping):
        return {
            str(nested_key): safe_audit_value(nested_value, key=str(nested_key))
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [safe_audit_value(item) for item in value]
    if isinstance(value, str):
        return truncate_audit_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return truncate_audit_text(str(value))


def is_sensitive_audit_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "authorization",
            "client_secret",
            "password",
            "raw",
            "secret",
            "token",
        )
    )


def truncate_audit_text(value: str, *, limit: int = 240) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"
