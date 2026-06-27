from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRunStatus,
)
from crxzipple.modules.tool.infrastructure.persistence.models import ToolRunModel
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
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

    def list(self, *, limit: int | None = None) -> list[ToolRun]:
        statement = select(ToolRunModel).order_by(ToolRunModel.created_at.desc())
        if limit is not None:
            statement = statement.limit(limit)
        models = self.session.scalars(statement).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def list_for_tool(self, tool_id: str, *, limit: int | None = None) -> list[ToolRun]:
        statement = (
            select(ToolRunModel)
            .where(ToolRunModel.tool_id == tool_id)
            .order_by(ToolRunModel.created_at.desc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        models = self.session.scalars(statement).all()
        for model in models:
            self._loaded_models[model.id] = model
        return [self._to_entity(model) for model in models]

    def list_for_orchestration_runs(self, run_ids: tuple[str, ...]) -> list[ToolRun]:
        ordered_ids = tuple(
            dict.fromkeys(run_id.strip() for run_id in run_ids if run_id.strip()),
        )
        if not ordered_ids:
            return []
        models = self.session.scalars(
            select(ToolRunModel)
            .where(
                ToolRunModel.metadata_payload.op("->>")("orchestration_run_id").in_(
                    ordered_ids,
                )
            )
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
            "call_id": tool_run.call_id,
            "tool_surface_id": tool_run.tool_surface_id,
            "function_id": tool_run.function_id,
            "function_revision": tool_run.function_revision,
            "source_id": tool_run.source_id,
            "source_revision": tool_run.source_revision,
            "schema_hash": tool_run.schema_hash,
            "mode": tool_run.target.mode.value,
            "strategy": tool_run.target.strategy.value,
            "environment": tool_run.target.environment.value,
            "status": tool_run.status.value,
            "input_payload": tool_run.input_payload,
            "metadata_payload": tool_run.metadata,
            "invocation_context_payload": tool_run.invocation_context_payload,
            "output_payload": tool_run.stored_output_payload,
            "result_envelope_payload": tool_run.result_envelope_payload,
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
        model.call_id = tool_run.call_id
        model.tool_surface_id = tool_run.tool_surface_id
        model.function_id = tool_run.function_id
        model.function_revision = tool_run.function_revision
        model.source_id = tool_run.source_id
        model.source_revision = tool_run.source_revision
        model.schema_hash = tool_run.schema_hash
        model.mode = tool_run.target.mode.value
        model.strategy = tool_run.target.strategy.value
        model.environment = tool_run.target.environment.value
        model.status = tool_run.status.value
        model.input_payload = tool_run.input_payload
        model.metadata_payload = tool_run.metadata
        model.invocation_context_payload = tool_run.invocation_context_payload
        model.output_payload = tool_run.stored_output_payload
        model.result_envelope_payload = tool_run.result_envelope_payload
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
            call_id=model.call_id,
            tool_surface_id=model.tool_surface_id,
            function_id=model.function_id,
            function_revision=model.function_revision,
            source_id=model.source_id,
            source_revision=model.source_revision,
            schema_hash=model.schema_hash,
            target=ToolExecutionTarget(
                mode=ToolMode(model.mode),
                strategy=ToolExecutionStrategy(model.strategy),
                environment=ToolEnvironment(model.environment),
            ),
            status=ToolRunStatus(model.status),
            input_payload=dict(model.input_payload),
            metadata=dict(model.metadata_payload or {}),
            invocation_context_payload=(
                dict(model.invocation_context_payload)
                if model.invocation_context_payload is not None
                else None
            ),
            result_payload=model.output_payload,
            result_envelope_payload=(
                dict(model.result_envelope_payload)
                if model.result_envelope_payload is not None
                else None
            ),
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
