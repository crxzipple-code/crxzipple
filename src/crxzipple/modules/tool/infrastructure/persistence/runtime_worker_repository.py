from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.domain.entities import ToolWorkerRegistration
from crxzipple.modules.tool.domain.value_objects import ToolWorkerStatus
from crxzipple.modules.tool.infrastructure.persistence.models import ToolWorkerModel
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
)


class SqlAlchemyToolWorkerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolWorkerModel] = {}

    def add(self, worker: ToolWorkerRegistration) -> None:
        model = self._loaded_models.get(worker.id)
        if model is None:
            model = self.session.get(ToolWorkerModel, worker.id)
        if model is None:
            self.add_new(worker)
            return
        self._apply_to_model(model, worker)
        self._loaded_models[worker.id] = model

    def add_new(self, worker: ToolWorkerRegistration) -> None:
        model = self._to_model(worker)
        self.session.add(model)
        self._loaded_models[worker.id] = model

    def get(self, worker_id: str) -> ToolWorkerRegistration | None:
        model = self.session.get(ToolWorkerModel, worker_id)
        if model is None:
            return None
        self._loaded_models[worker_id] = model
        return self._to_entity(model)

    def list(self) -> list[ToolWorkerRegistration]:
        models = self.session.scalars(
            select(ToolWorkerModel).order_by(ToolWorkerModel.registered_at.asc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def delete(self, worker_id: str) -> None:
        model = self._loaded_models.pop(worker_id, None)
        if model is None:
            model = self.session.get(ToolWorkerModel, worker_id)
        if model is not None:
            self.session.delete(model)

    @staticmethod
    def _to_model(worker: ToolWorkerRegistration) -> ToolWorkerModel:
        return ToolWorkerModel(
            **SqlAlchemyToolWorkerRepository._to_mapping(worker),
        )

    @staticmethod
    def _to_mapping(worker: ToolWorkerRegistration) -> dict[str, object]:
        return {
            "id": worker.id,
            "status": worker.status.value,
            "max_in_flight": worker.max_in_flight,
            "current_in_flight": worker.current_in_flight,
            "capabilities_payload": dict(worker.capabilities_payload),
            "registered_at": worker.registered_at,
            "heartbeat_at": worker.heartbeat_at,
            "lease_expires_at": worker.lease_expires_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolWorkerModel, worker: ToolWorkerRegistration) -> None:
        model.status = worker.status.value
        model.max_in_flight = worker.max_in_flight
        model.current_in_flight = worker.current_in_flight
        model.capabilities_payload = dict(worker.capabilities_payload)
        model.registered_at = worker.registered_at
        model.heartbeat_at = worker.heartbeat_at
        model.lease_expires_at = worker.lease_expires_at

    @staticmethod
    def _to_entity(model: ToolWorkerModel) -> ToolWorkerRegistration:
        return ToolWorkerRegistration(
            id=model.id,
            status=ToolWorkerStatus(model.status),
            max_in_flight=model.max_in_flight,
            current_in_flight=model.current_in_flight,
            capabilities_payload=dict(model.capabilities_payload),
            registered_at=coerce_utc_datetime(model.registered_at),
            heartbeat_at=coerce_utc_datetime(model.heartbeat_at),
            lease_expires_at=coerce_optional_utc_datetime(model.lease_expires_at),
        )
