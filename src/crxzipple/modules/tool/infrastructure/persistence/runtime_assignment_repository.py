from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.domain.entities import ToolRunAssignment
from crxzipple.modules.tool.domain.value_objects import ToolRunAssignmentStatus
from crxzipple.modules.tool.infrastructure.persistence.models import (
    ToolRunAssignmentModel,
)
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
)


class SqlAlchemyToolRunAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolRunAssignmentModel] = {}

    def add(self, assignment: ToolRunAssignment) -> None:
        model = self._loaded_models.get(assignment.id)
        if model is None:
            model = self.session.get(ToolRunAssignmentModel, assignment.id)
        if model is None:
            self.add_new(assignment)
            return
        self._apply_to_model(model, assignment)
        self._loaded_models[assignment.id] = model

    def add_new(self, assignment: ToolRunAssignment) -> None:
        model = self._to_model(assignment)
        self.session.add(model)
        self._loaded_models[assignment.id] = model

    def get(self, assignment_id: str) -> ToolRunAssignment | None:
        model = self.session.get(ToolRunAssignmentModel, assignment_id)
        if model is None:
            return None
        self._loaded_models[assignment_id] = model
        return self._to_entity(model)

    def get_latest_for_run(self, run_id: str) -> ToolRunAssignment | None:
        model = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(ToolRunAssignmentModel.run_id == run_id)
            .order_by(ToolRunAssignmentModel.assigned_at.desc())
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.id] = model
        return self._to_entity(model)

    def get_latest_for_run_and_worker(
        self,
        run_id: str,
        worker_id: str,
    ) -> ToolRunAssignment | None:
        model = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(
                ToolRunAssignmentModel.run_id == run_id,
                ToolRunAssignmentModel.worker_id == worker_id,
            )
            .order_by(ToolRunAssignmentModel.assigned_at.desc())
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.id] = model
        return self._to_entity(model)

    def list_for_run(self, run_id: str) -> list[ToolRunAssignment]:
        models = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(ToolRunAssignmentModel.run_id == run_id)
            .order_by(ToolRunAssignmentModel.assigned_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def get_next_for_worker(self, worker_id: str) -> ToolRunAssignment | None:
        model = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(
                ToolRunAssignmentModel.worker_id == worker_id,
                ToolRunAssignmentModel.status.in_(
                    (
                        ToolRunAssignmentStatus.ASSIGNED.value,
                        ToolRunAssignmentStatus.RUNNING.value,
                    ),
                ),
            )
            .order_by(ToolRunAssignmentModel.assigned_at.asc())
            .limit(1),
        ).first()
        if model is None:
            return None
        self._loaded_models[model.id] = model
        return self._to_entity(model)

    def list_for_worker(self, worker_id: str) -> list[ToolRunAssignment]:
        models = self.session.scalars(
            select(ToolRunAssignmentModel)
            .where(ToolRunAssignmentModel.worker_id == worker_id)
            .order_by(ToolRunAssignmentModel.assigned_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def list(self) -> list[ToolRunAssignment]:
        models = self.session.scalars(
            select(ToolRunAssignmentModel).order_by(
                ToolRunAssignmentModel.assigned_at.desc(),
            ),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(assignment: ToolRunAssignment) -> ToolRunAssignmentModel:
        return ToolRunAssignmentModel(
            **SqlAlchemyToolRunAssignmentRepository._to_mapping(assignment),
        )

    @staticmethod
    def _to_mapping(assignment: ToolRunAssignment) -> dict[str, object]:
        return {
            "id": assignment.id,
            "run_id": assignment.run_id,
            "tool_id": assignment.tool_id,
            "worker_id": assignment.worker_id,
            "status": assignment.status.value,
            "attempt_count": assignment.attempt_count,
            "assigned_at": assignment.assigned_at,
            "started_at": assignment.started_at,
            "heartbeat_at": assignment.heartbeat_at,
            "lease_expires_at": assignment.lease_expires_at,
            "completed_at": assignment.completed_at,
            "terminal_reason": assignment.terminal_reason,
        }

    @staticmethod
    def _apply_to_model(
        model: ToolRunAssignmentModel,
        assignment: ToolRunAssignment,
    ) -> None:
        model.run_id = assignment.run_id
        model.tool_id = assignment.tool_id
        model.worker_id = assignment.worker_id
        model.status = assignment.status.value
        model.attempt_count = assignment.attempt_count
        model.assigned_at = assignment.assigned_at
        model.started_at = assignment.started_at
        model.heartbeat_at = assignment.heartbeat_at
        model.lease_expires_at = assignment.lease_expires_at
        model.completed_at = assignment.completed_at
        model.terminal_reason = assignment.terminal_reason

    @staticmethod
    def _to_entity(model: ToolRunAssignmentModel) -> ToolRunAssignment:
        return ToolRunAssignment(
            id=model.id,
            run_id=model.run_id,
            tool_id=model.tool_id,
            worker_id=model.worker_id,
            status=ToolRunAssignmentStatus(model.status),
            attempt_count=model.attempt_count,
            assigned_at=coerce_utc_datetime(model.assigned_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            heartbeat_at=coerce_optional_utc_datetime(model.heartbeat_at),
            lease_expires_at=coerce_optional_utc_datetime(model.lease_expires_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            terminal_reason=model.terminal_reason,
        )
