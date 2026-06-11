from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from crxzipple.core.db import SessionFactory
from crxzipple.modules.memory.domain import MemoryPolicy, MemorySpace
from crxzipple.modules.memory.infrastructure.persistence.models import (
    MemoryPolicyModel,
    MemorySpaceModel,
)
from crxzipple.shared.time import coerce_utc_datetime


class SqlAlchemyMemorySpaceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, scope_ref: str) -> MemorySpace | None:
        with self._session_factory() as session:
            model = session.get(MemorySpaceModel, scope_ref)
            return _space_record(model) if model is not None else None

    def list(self, *, include_disabled: bool = False) -> tuple[MemorySpace, ...]:
        with self._session_factory() as session:
            statement = select(MemorySpaceModel)
            if not include_disabled:
                statement = statement.where(MemorySpaceModel.status == "active")
            models = session.scalars(
                statement.order_by(
                    MemorySpaceModel.owner_kind.asc(),
                    MemorySpaceModel.owner_id.asc(),
                    MemorySpaceModel.scope_ref.asc(),
                ),
            ).all()
            return tuple(_space_record(model) for model in models)

    def upsert(self, space: MemorySpace) -> MemorySpace:
        with self._session_factory() as session:
            existing = session.get(MemorySpaceModel, space.scope_ref)
            stored = replace(
                space,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else coerce_utc_datetime(space.created_at)
                ),
                updated_at=coerce_utc_datetime(space.updated_at),
            )
            if existing is None:
                session.add(_space_model(stored))
            else:
                _apply_space(existing, stored)
            try:
                session.commit()
                return stored
            except IntegrityError:
                session.rollback()
                if existing is not None:
                    raise

        with self._session_factory() as session:
            existing = session.get(MemorySpaceModel, space.scope_ref)
            if existing is None:
                raise RuntimeError(
                    f"Memory space '{space.scope_ref}' conflicted during upsert but could not be reloaded.",
                )
            stored = replace(
                space,
                created_at=coerce_utc_datetime(existing.created_at),
                updated_at=coerce_utc_datetime(space.updated_at),
            )
            _apply_space(existing, stored)
            session.commit()
            return stored

    def delete(self, scope_ref: str) -> None:
        with self._session_factory() as session:
            model = session.get(MemorySpaceModel, scope_ref)
            if model is not None:
                session.delete(model)
                session.commit()


class SqlAlchemyMemoryPolicyRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, policy_id: str) -> MemoryPolicy | None:
        with self._session_factory() as session:
            model = session.get(MemoryPolicyModel, policy_id)
            return _policy_record(model) if model is not None else None

    def list(self, *, include_disabled: bool = False) -> tuple[MemoryPolicy, ...]:
        with self._session_factory() as session:
            statement = select(MemoryPolicyModel)
            if not include_disabled:
                statement = statement.where(MemoryPolicyModel.status == "active")
            models = session.scalars(
                statement.order_by(
                    MemoryPolicyModel.target_kind.asc(),
                    MemoryPolicyModel.target_id.asc(),
                    MemoryPolicyModel.policy_id.asc(),
                ),
            ).all()
            return tuple(_policy_record(model) for model in models)

    def upsert(self, policy: MemoryPolicy) -> MemoryPolicy:
        with self._session_factory() as session:
            existing = session.get(MemoryPolicyModel, policy.policy_id)
            stored = replace(
                policy,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else coerce_utc_datetime(policy.created_at)
                ),
                updated_at=coerce_utc_datetime(policy.updated_at),
            )
            if existing is None:
                session.add(_policy_model(stored))
            else:
                _apply_policy(existing, stored)
            session.commit()
            return stored

    def delete(self, policy_id: str) -> None:
        with self._session_factory() as session:
            model = session.get(MemoryPolicyModel, policy_id)
            if model is not None:
                session.delete(model)
                session.commit()


def _space_model(space: MemorySpace) -> MemorySpaceModel:
    return MemorySpaceModel(
        scope_ref=space.scope_ref,
        owner_kind=space.owner_kind,
        owner_id=space.owner_id,
        engine_id=space.engine_id,
        storage_root=space.storage_root,
        retrieval_backend=space.retrieval_backend,
        status=space.status,
        metadata_payload=dict(space.metadata),
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


def _apply_space(model: MemorySpaceModel, space: MemorySpace) -> None:
    model.owner_kind = space.owner_kind
    model.owner_id = space.owner_id
    model.engine_id = space.engine_id
    model.storage_root = space.storage_root
    model.retrieval_backend = space.retrieval_backend
    model.status = space.status
    model.metadata_payload = dict(space.metadata)
    model.updated_at = space.updated_at


def _space_record(model: MemorySpaceModel) -> MemorySpace:
    return MemorySpace(
        scope_ref=model.scope_ref,
        owner_kind=model.owner_kind,  # type: ignore[arg-type]
        owner_id=model.owner_id,
        engine_id=model.engine_id,
        storage_root=model.storage_root,
        retrieval_backend=model.retrieval_backend,
        status=model.status,  # type: ignore[arg-type]
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _policy_model(policy: MemoryPolicy) -> MemoryPolicyModel:
    return MemoryPolicyModel(
        policy_id=policy.policy_id,
        target_kind=policy.target_kind,
        target_id=policy.target_id,
        recall_enabled=policy.recall_enabled,
        remember_enabled=policy.remember_enabled,
        max_recall_items=policy.max_recall_items,
        retention=policy.retention,
        status=policy.status,
        metadata_payload=dict(policy.metadata),
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _apply_policy(model: MemoryPolicyModel, policy: MemoryPolicy) -> None:
    model.target_kind = policy.target_kind
    model.target_id = policy.target_id
    model.recall_enabled = policy.recall_enabled
    model.remember_enabled = policy.remember_enabled
    model.max_recall_items = policy.max_recall_items
    model.retention = policy.retention
    model.status = policy.status
    model.metadata_payload = dict(policy.metadata)
    model.updated_at = policy.updated_at


def _policy_record(model: MemoryPolicyModel) -> MemoryPolicy:
    return MemoryPolicy(
        policy_id=model.policy_id,
        target_kind=model.target_kind,  # type: ignore[arg-type]
        target_id=model.target_id,
        recall_enabled=model.recall_enabled,
        remember_enabled=model.remember_enabled,
        max_recall_items=model.max_recall_items,
        retention=model.retention,
        status=model.status,  # type: ignore[arg-type]
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )
