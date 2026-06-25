from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.operations.application.observation_models import OperationsProjection
from crxzipple.modules.operations.infrastructure.persistence.models import (
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
        normalized_module = normalize_key(module)
        normalized_kind = normalize_key(kind)
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
                (normalize_key(module), normalize_key(kind), query_key.strip() or "default"),
            )
            if model is None:
                return None
            return to_projection(model)

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
                    OperationsProjectionModel.module == normalize_key(module),
                )
            models = session.scalars(statement).all()
            return tuple(to_projection(model) for model in models)

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
                    OperationsProjectionModel.module == normalize_key(module),
                )
            if kind is not None:
                statement = statement.where(
                    OperationsProjectionModel.kind == normalize_key(kind),
                )
            result = session.execute(statement)
            session.commit()
            return int(result.rowcount or 0)


def to_projection(model: OperationsProjectionModel) -> OperationsProjection:
    return OperationsProjection(
        module=model.module,
        kind=model.kind,
        query_key=model.query_key,
        updated_at=coerce_utc_datetime(model.updated_at),
        payload=dict(model.payload),
    )


def normalize_key(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("operations projection key cannot be blank")
    return normalized
