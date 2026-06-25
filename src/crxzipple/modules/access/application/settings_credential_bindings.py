from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.access.application.credential_requirement_rules import (
    canonical_credential_binding,
)
from crxzipple.modules.access.application.repositories import (
    AccessCredentialBindingRecord,
)
from crxzipple.modules.access.application.settings_action_contracts import (
    AccessSettingsActionRequest,
    JsonObject,
)
from crxzipple.modules.access.application.settings_payloads import (
    _change_optional_text,
    _change_text,
)


def _credential_binding_from_update_request(
    request: AccessSettingsActionRequest,
    *,
    existing: AccessCredentialBindingRecord,
) -> AccessCredentialBindingRecord:
    requested_source_kind = _change_optional_text(request.changes, "source_kind")
    source_kind = (
        _normalize_credential_binding_source_kind(requested_source_kind)
        if requested_source_kind is not None
        else existing.source_kind
    )
    existing_source_kind = existing.source_kind.strip().lower()
    source_kind_changed = source_kind.strip().lower() != existing_source_kind
    source_ref_changed = _binding_source_ref_change_requested(
        request.changes,
        source_kind,
    )
    source_ref = existing.source_ref
    if source_kind_changed or source_ref_changed:
        if source_kind not in {"env", "file", "app_credential", "oauth_account"}:
            raise ValueError(
                "source_ref updates are only supported for env, file, "
                "app_credential, and oauth_account credential binding sources.",
            )
        source_ref = _binding_source_ref(request, source_kind)
    status = _credential_binding_status_from_changes(request.changes, existing)
    metadata = {
        **dict(existing.metadata),
        "action_id": request.action_id,
        "reason": request.reason,
        "trace_context": dict(request.trace_context),
        "previous_fields": _credential_binding_redacted_metadata(existing),
    }
    return AccessCredentialBindingRecord(
        binding_id=existing.binding_id,
        asset_id=_optional_field_update(
            request.changes,
            "asset_id",
            existing.asset_id,
        ),
        binding_kind=_change_text(
            request.changes,
            "binding_kind",
            default=existing.binding_kind,
        ),
        source_kind=source_kind,
        source_ref=source_ref,
        masked_preview=_optional_field_update(
            request.changes,
            "masked_preview",
            existing.masked_preview,
        ),
        status=status,
        redaction_policy=dict(existing.redaction_policy),
        metadata=metadata,
    )


def _credential_binding_status_from_changes(
    changes: Mapping[str, Any],
    existing: AccessCredentialBindingRecord,
) -> str:
    if "status" not in changes:
        return existing.status
    status = _change_text(changes, "status").strip().lower()
    if status not in {"active", "disabled", "revoked"}:
        raise ValueError(
            "credential binding status must be active, disabled, or revoked.",
        )
    existing_status = existing.status.strip().lower()
    if existing_status == "revoked" and status != "revoked":
        raise ValueError(
            f"credential binding '{existing.binding_id}' is revoked and cannot be re-enabled.",
        )
    return status


def _optional_field_update(
    changes: Mapping[str, Any],
    key: str,
    current: str | None,
) -> str | None:
    if key not in changes:
        return current
    value = changes.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_credential_binding_source_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"env", "file", "app_credential", "oauth_account"}:
        raise ValueError(
            "credential binding source_kind must be env, file, app_credential, or oauth_account.",
        )
    return normalized


def _binding_source_ref_change_requested(
    changes: Mapping[str, Any],
    source_kind: str,
) -> bool:
    keys = ["source_ref"]
    if source_kind == "env":
        keys.append("env_name")
    elif source_kind == "file":
        keys.append("path")
    elif source_kind == "oauth_account":
        keys.append("account_id")
    elif source_kind == "app_credential":
        keys.append("app_credential_id")
    return any(key in changes for key in keys)


def _credential_binding_redacted_metadata(
    record: AccessCredentialBindingRecord,
) -> JsonObject:
    return {
        "binding_id": record.binding_id,
        "asset_id": record.asset_id,
        "binding_kind": record.binding_kind,
        "source_kind": record.source_kind,
        "source_ref": _credential_binding_public_source_ref(record),
        "masked_preview": record.masked_preview,
        "status": record.status,
    }


def _credential_binding_public_source_ref(
    record: AccessCredentialBindingRecord,
) -> str:
    source_kind = record.source_kind.strip().lower()
    if source_kind in {"env", "file"}:
        return canonical_credential_binding(f"{source_kind}:{record.source_ref}")
    if source_kind == "oauth_account":
        return record.source_ref
    if source_kind == "app_credential":
        return record.source_ref
    return "***"


def _changed_credential_binding_fields(
    *,
    before_redacted: Mapping[str, Any],
    after_redacted: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    fields = (
        "binding_kind",
        "source_kind",
        "source_ref",
        "asset_id",
        "masked_preview",
        "status",
    )
    return {
        field: {
            "before": before_redacted.get(field),
            "after": after_redacted.get(field),
        }
        for field in fields
        if before_redacted.get(field) != after_redacted.get(field)
    }


def _credential_binding_update_validation_metadata(
    *,
    binding_id: str,
    before_redacted: Mapping[str, Any],
    after_redacted: Mapping[str, Any],
    changed: Mapping[str, Mapping[str, Any]],
) -> JsonObject:
    return {
        "binding_id": binding_id,
        "previous_status": before_redacted.get("status"),
        "status": after_redacted.get("status"),
        "previous_fields": {
            field: values.get("before") for field, values in changed.items()
        },
        "updated_fields": {
            field: values.get("after") for field, values in changed.items()
        },
        "before_redacted": dict(before_redacted),
        "after_redacted": dict(after_redacted),
    }


def _binding_source_ref(
    request: AccessSettingsActionRequest,
    source_kind: str,
) -> str:
    if source_kind == "oauth_account":
        return _normalize_binding_source_ref(
            source_kind,
            _change_text(request.changes, "source_ref", "account_id"),
        )
    if source_kind == "app_credential":
        return _normalize_binding_source_ref(
            source_kind,
            _change_text(request.changes, "source_ref", "app_credential_id"),
        )
    return _normalize_binding_source_ref(
        source_kind,
        _change_text(
            request.changes,
            "source_ref",
            "env_name" if source_kind == "env" else "path",
        ),
    )


def _normalize_binding_source_ref(source_kind: str, source_ref: str) -> str:
    normalized_kind = source_kind.strip().lower()
    normalized_ref = source_ref.strip()
    if normalized_kind == "env":
        if normalized_ref.startswith("env:"):
            normalized_ref = canonical_credential_binding(normalized_ref).removeprefix(
                "env:",
            )
    elif normalized_kind == "file":
        if normalized_ref.startswith("file:"):
            normalized_ref = canonical_credential_binding(normalized_ref).removeprefix(
                "file:",
            )
    elif normalized_kind == "oauth_account" and normalized_ref.startswith(
        "oauth_account:",
    ):
        normalized_ref = normalized_ref.removeprefix("oauth_account:").strip()
    elif normalized_kind == "app_credential" and normalized_ref.startswith(
        "app_credential:",
    ):
        normalized_ref = normalized_ref.removeprefix("app_credential:").strip()
    if not normalized_ref:
        raise ValueError("credential binding source_ref is required.")
    return normalized_ref


def _default_binding_kind(source_kind: str) -> str:
    if source_kind == "app_credential":
        return "app_secret"
    if source_kind == "oauth_account":
        return "oauth2_account"
    return "api_key"
