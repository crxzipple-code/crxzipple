from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from crxzipple.core.db import SessionFactory
from crxzipple.modules.operations.application.action_audit import (
    OperationsActionAudit,
)
from crxzipple.modules.operations.application.observation import OperationsProjection
from crxzipple.modules.operations.infrastructure.persistence.models import (
    OperationsActionAuditModel,
    OperationsProjectionModel,
)
from crxzipple.shared.time import coerce_utc_datetime


class SqlAlchemyOperationsProjectionStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_projection(
        self,
        *,
        module: str,
        kind: str,
        payload: dict[str, Any],
        query_key: str = "default",
        updated_at: datetime | None = None,
    ) -> None:
        normalized_module = _normalize_key(module)
        normalized_kind = _normalize_key(kind)
        normalized_query_key = query_key.strip() or "default"
        projection_updated_at = coerce_utc_datetime(
            updated_at or datetime.now(timezone.utc),
        )
        with self._session_factory() as session:
            model = session.get(
                OperationsProjectionModel,
                (normalized_module, normalized_kind, normalized_query_key),
            )
            if model is None:
                model = OperationsProjectionModel(
                    module=normalized_module,
                    kind=normalized_kind,
                    query_key=normalized_query_key,
                    version=1,
                    updated_at=projection_updated_at,
                    payload=dict(payload),
                )
                session.add(model)
            else:
                model.version += 1
                model.updated_at = projection_updated_at
                model.payload = dict(payload)
            session.commit()

    def get_projection(
        self,
        *,
        module: str,
        kind: str,
        query_key: str = "default",
    ) -> OperationsProjection | None:
        with self._session_factory() as session:
            model = session.get(
                OperationsProjectionModel,
                (_normalize_key(module), _normalize_key(kind), query_key.strip() or "default"),
            )
            if model is None:
                return None
            return _to_projection(model)

    def list_projections(
        self,
        *,
        module: str | None = None,
    ) -> tuple[OperationsProjection, ...]:
        with self._session_factory() as session:
            statement = select(OperationsProjectionModel).order_by(
                OperationsProjectionModel.module.asc(),
                OperationsProjectionModel.kind.asc(),
                OperationsProjectionModel.query_key.asc(),
            )
            if module is not None:
                statement = statement.where(
                    OperationsProjectionModel.module == _normalize_key(module),
                )
            models = session.scalars(statement).all()
            return tuple(_to_projection(model) for model in models)

    def clear(
        self,
        *,
        module: str | None = None,
        kind: str | None = None,
    ) -> int:
        with self._session_factory() as session:
            statement = delete(OperationsProjectionModel)
            if module is not None:
                statement = statement.where(
                    OperationsProjectionModel.module == _normalize_key(module),
                )
            if kind is not None:
                statement = statement.where(
                    OperationsProjectionModel.kind == _normalize_key(kind),
                )
            result = session.execute(statement)
            session.commit()
            return int(result.rowcount or 0)


def _to_projection(model: OperationsProjectionModel) -> OperationsProjection:
    return OperationsProjection(
        module=model.module,
        kind=model.kind,
        query_key=model.query_key,
        updated_at=coerce_utc_datetime(model.updated_at),
        payload=dict(model.payload),
    )


def _normalize_key(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("operations projection key cannot be blank")
    return normalized


class SqlAlchemyOperationsActionAuditStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        target: dict[str, Any],
        reason: str,
        dangerous: bool,
        risk: str,
        confirmation: bool,
        risk_acknowledged: bool,
        operator: str | None,
        source: str,
        metadata: dict[str, Any],
        created_at: datetime | None = None,
    ) -> OperationsActionAudit:
        now = coerce_utc_datetime(created_at or datetime.now(timezone.utc))
        model = OperationsActionAuditModel(
            audit_id=f"opact_{uuid4().hex}",
            action_type=_normalize_text(action_type, "action type"),
            target_type=_normalize_text(target_type, "target type"),
            target_id=_optional_text(target_id),
            target=dict(target),
            reason=_normalize_text(reason, "reason"),
            dangerous=bool(dangerous),
            risk=_normalize_text(risk, "risk"),
            confirmation=bool(confirmation),
            risk_acknowledged=bool(risk_acknowledged),
            operator=_optional_text(operator),
            source=_normalize_text(source, "source"),
            metadata_=dict(metadata),
            created_at=now,
            updated_at=now,
            status="attempted",
            result=None,
            error=None,
        )
        with self._session_factory() as session:
            session.add(model)
            session.commit()
            return _to_action_audit(model)

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
        updated_at: datetime | None = None,
    ) -> OperationsActionAudit:
        return self._mark_terminal(
            audit_id,
            status="succeeded",
            result=dict(result) if result is not None else None,
            error=None,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
        updated_at: datetime | None = None,
    ) -> OperationsActionAudit:
        return self._mark_terminal(
            audit_id,
            status="failed",
            result=None,
            error=dict(error),
            updated_at=updated_at,
        )

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[OperationsActionAudit, ...]:
        safe_limit = min(max(int(limit), 1), 200)
        safe_offset = max(int(offset), 0)
        with self._session_factory() as session:
            statement = (
                select(OperationsActionAuditModel)
                .order_by(
                    OperationsActionAuditModel.created_at.desc(),
                    OperationsActionAuditModel.audit_id.desc(),
                )
                .limit(safe_limit)
                .offset(safe_offset)
            )
            return tuple(_to_action_audit(model) for model in session.scalars(statement))

    def _mark_terminal(
        self,
        audit_id: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
        updated_at: datetime | None,
    ) -> OperationsActionAudit:
        with self._session_factory() as session:
            model = session.get(OperationsActionAuditModel, audit_id)
            if model is None:
                raise LookupError(f"Operations action audit '{audit_id}' does not exist.")
            model.status = status
            model.result = result
            model.error = error
            model.updated_at = coerce_utc_datetime(
                updated_at or datetime.now(timezone.utc),
            )
            session.commit()
            return _to_action_audit(model)


def _to_action_audit(model: OperationsActionAuditModel) -> OperationsActionAudit:
    return OperationsActionAudit(
        audit_id=model.audit_id,
        action_type=model.action_type,
        target_type=model.target_type,
        target_id=model.target_id,
        target=dict(model.target),
        reason=model.reason,
        dangerous=bool(model.dangerous),
        risk=model.risk,
        confirmation=bool(model.confirmation),
        risk_acknowledged=bool(model.risk_acknowledged),
        operator=model.operator,
        source=model.source,
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
        status=model.status,
        result=dict(model.result) if model.result is not None else None,
        error=dict(model.error) if model.error is not None else None,
    )


def _normalize_text(value: str | None, label: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError(f"operations action audit {label} cannot be blank")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
