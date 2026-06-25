from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.operations.interfaces.http_action_audit_summary import (
    operations_action_error_summary,
    operations_action_result_summary,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsActionRequest,
)


def _begin_operations_action_audit(
    container: AppContainer,
    request: OperationsActionRequest,
    *,
    action_type: str,
    target_type: str,
    target_id: str | None = None,
    target: dict[str, Any] | None = None,
    default_reason: str,
    risk: str = "normal",
    reason_required: bool = False,
) -> tuple[str, str]:
    normalized_risk = _operation_action_risk(risk)
    reason = _validated_operations_action(
        request,
        default_reason=default_reason,
        risk=normalized_risk,
        reason_required=reason_required,
    )
    payload = _operations_action_audit_payload(
        request,
        reason=reason,
        risk=normalized_risk,
    )
    audit = container.require(AppKey.OPERATIONS_ACTION_AUDIT_STORE).record_attempt(
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        target=target or {},
        reason=reason,
        dangerous=bool(payload["dangerous"]),
        risk=str(payload["risk"]),
        confirmation=bool(payload["confirmation"]),
        risk_acknowledged=bool(payload["risk_acknowledged"]),
        operator=payload["operator"],
        source=str(payload["source"]),
        metadata=payload["metadata"],
    )
    return reason, audit.audit_id


def _mark_operations_action_succeeded(
    container: AppContainer,
    audit_id: str,
    result: Any,
) -> None:
    container.require(AppKey.OPERATIONS_ACTION_AUDIT_STORE).mark_succeeded(
        audit_id,
        result=operations_action_result_summary(result),
    )


def _mark_operations_action_failed(
    container: AppContainer,
    audit_id: str,
    exc: BaseException,
) -> None:
    container.require(AppKey.OPERATIONS_ACTION_AUDIT_STORE).mark_failed(
        audit_id,
        error=operations_action_error_summary(exc),
    )


def _daemon_service_action_risk(action: str) -> str:
    normalized = action.strip().lower()
    if normalized == "stop":
        return "dangerous"
    if normalized in {"ensure", "reconcile"}:
        return "controlled"
    return "normal"


def _validated_operations_action(
    request: OperationsActionRequest,
    *,
    default_reason: str,
    risk: str = "normal",
    reason_required: bool = False,
) -> str:
    normalized_risk = _operation_action_risk(risk)
    dangerous = normalized_risk == "dangerous"
    reason = _operation_reason(request.reason) or _operation_reason(default_reason)
    if (dangerous or reason_required) and _operation_reason(request.reason) is None:
        raise HTTPException(
            status_code=400,
            detail="reason is required for this operations action.",
        )
    if dangerous:
        if not _operation_confirmation(request.confirmation):
            raise HTTPException(
                status_code=400,
                detail="confirmation is required for this operations action.",
            )
        if not request.acknowledged_risk():
            raise HTTPException(
                status_code=400,
                detail="risk acknowledgement is required for this operations action.",
            )
    if reason is None:
        raise HTTPException(
            status_code=400,
            detail="reason is required for this operations action.",
        )
    return reason


def _operations_action_audit_payload(
    request: OperationsActionRequest,
    *,
    reason: str,
    risk: str,
) -> dict[str, Any]:
    normalized_risk = _operation_action_risk(risk)
    dangerous = normalized_risk == "dangerous"
    audit = request.audit
    metadata: dict[str, Any] = {}
    if audit is not None:
        metadata.update(dict(audit.metadata or {}))
    metadata.update(dict(request.metadata or {}))
    return {
        "reason": reason,
        "operator": (
            _operation_reason(request.operator)
            or _operation_reason(getattr(audit, "operator", None))
        ),
        "source": (
            _operation_reason(request.source)
            or _operation_reason(getattr(audit, "source", None))
            or "operations"
        ),
        "risk_acknowledged": request.acknowledged_risk(),
        "confirmation": _operation_confirmation(request.confirmation),
        "dangerous": dangerous,
        "risk": normalized_risk,
        "metadata": metadata,
    }


def _operation_reason(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _operation_confirmation(value: bool | str | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _operation_action_risk(value: str | None) -> str:
    if not isinstance(value, str):
        return "normal"
    normalized = value.strip().lower()
    if normalized in {"normal", "controlled", "dangerous"}:
        return normalized
    return "normal"
