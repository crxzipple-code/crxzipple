from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.domain.entities import (
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolRunAssignmentStatus,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRunStatus,
    ToolWorkerStatus,
)
from crxzipple.modules.tool.infrastructure.persistence.models import (
    ToolRunAssignmentModel,
    ToolRunModel,
    ToolWorkerModel,
)
from crxzipple.shared.time import (
    coerce_utc_datetime,
    coerce_optional_utc_datetime,
)


class SqlAlchemyToolRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._loaded_models: dict[str, ToolRunModel] = {}

    def add(self, tool_run: ToolRun) -> None:
        model = self._loaded_models.get(tool_run.id)
        if model is None:
            model = self.session.get(ToolRunModel, tool_run.id)
        if model is None:
            self.add_new(tool_run)
            return
        self._apply_to_model(model, tool_run)
        self._loaded_models[tool_run.id] = model

    def add_new(self, tool_run: ToolRun) -> None:
        model = self._to_model(tool_run)
        self.session.add(model)
        self._loaded_models[tool_run.id] = model

    def add_many_new(self, tool_runs: tuple[ToolRun, ...]) -> None:
        if not tool_runs:
            return
        if len(tool_runs) == 1:
            self.add_new(tool_runs[0])
            return
        self.session.bulk_insert_mappings(
            ToolRunModel,
            [self._to_mapping(tool_run) for tool_run in tool_runs],
        )

    def get(self, run_id: str) -> ToolRun | None:
        model = self.session.get(ToolRunModel, run_id)
        if model is None:
            return None
        self._loaded_models[run_id] = model
        return self._to_entity(model)

    def get_many(self, run_ids: tuple[str, ...]) -> dict[str, ToolRun]:
        if not run_ids:
            return {}
        ordered_ids = tuple(dict.fromkeys(run_ids))
        models = self.session.scalars(
            select(ToolRunModel).where(ToolRunModel.id.in_(ordered_ids)),
        ).all()
        entities: dict[str, ToolRun] = {}
        for model in models:
            self._loaded_models[model.id] = model
            entities[model.id] = self._to_entity(model)
        return entities

    def list(self) -> list[ToolRun]:
        models = self.session.scalars(
            select(ToolRunModel).order_by(ToolRunModel.created_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        models = self.session.scalars(
            select(ToolRunModel)
            .where(ToolRunModel.tool_id == tool_id)
            .order_by(ToolRunModel.created_at.desc()),
        ).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_model(tool_run: ToolRun) -> ToolRunModel:
        return ToolRunModel(
            **SqlAlchemyToolRunRepository._to_mapping(tool_run),
        )

    @staticmethod
    def _to_mapping(tool_run: ToolRun) -> dict[str, object]:
        return {
            "id": tool_run.id,
            "tool_id": tool_run.tool_id,
            "mode": tool_run.target.mode.value,
            "strategy": tool_run.target.strategy.value,
            "environment": tool_run.target.environment.value,
            "status": tool_run.status.value,
            "input_payload": tool_run.input_payload,
            "invocation_context_payload": tool_run.invocation_context_payload,
            "output_payload": tool_run.stored_output_payload,
            "error_message": tool_run.stored_error_payload,
            "created_at": tool_run.created_at,
            "started_at": tool_run.started_at,
            "completed_at": tool_run.completed_at,
            "attempt_count": tool_run.attempt_count,
            "max_attempts": tool_run.max_attempts,
            "worker_id": tool_run.worker_id,
            "heartbeat_at": tool_run.heartbeat_at,
            "lease_expires_at": tool_run.lease_expires_at,
            "cancel_requested_at": tool_run.cancel_requested_at,
        }

    @staticmethod
    def _apply_to_model(model: ToolRunModel, tool_run: ToolRun) -> None:
        model.tool_id = tool_run.tool_id
        model.mode = tool_run.target.mode.value
        model.strategy = tool_run.target.strategy.value
        model.environment = tool_run.target.environment.value
        model.status = tool_run.status.value
        model.input_payload = tool_run.input_payload
        model.invocation_context_payload = tool_run.invocation_context_payload
        model.output_payload = tool_run.stored_output_payload
        model.error_message = tool_run.stored_error_payload
        model.created_at = tool_run.created_at
        model.started_at = tool_run.started_at
        model.completed_at = tool_run.completed_at
        model.attempt_count = tool_run.attempt_count
        model.max_attempts = tool_run.max_attempts
        model.worker_id = tool_run.worker_id
        model.heartbeat_at = tool_run.heartbeat_at
        model.lease_expires_at = tool_run.lease_expires_at
        model.cancel_requested_at = tool_run.cancel_requested_at

    @staticmethod
    def _to_entity(model: ToolRunModel) -> ToolRun:
        return ToolRun(
            id=model.id,
            tool_id=model.tool_id,
            target=ToolExecutionTarget(
                mode=ToolMode(model.mode),
                strategy=ToolExecutionStrategy(model.strategy),
                environment=ToolEnvironment(model.environment),
            ),
            status=ToolRunStatus(model.status),
            input_payload=dict(model.input_payload),
            invocation_context_payload=(
                dict(model.invocation_context_payload)
                if model.invocation_context_payload is not None
                else None
            ),
            result_payload=model.output_payload,
            error_payload=model.error_message,
            created_at=coerce_utc_datetime(model.created_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            attempt_count=model.attempt_count,
            max_attempts=model.max_attempts,
            worker_id=model.worker_id,
            heartbeat_at=coerce_optional_utc_datetime(model.heartbeat_at),
            lease_expires_at=coerce_optional_utc_datetime(model.lease_expires_at),
            cancel_requested_at=coerce_optional_utc_datetime(
                model.cancel_requested_at,
            ),
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
