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


class SqlAlchemyToolRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, tool_run: ToolRun) -> None:
        self.session.merge(
            ToolRunModel(
                id=tool_run.id,
                tool_id=tool_run.tool_id,
                mode=tool_run.target.mode.value,
                strategy=tool_run.target.strategy.value,
                environment=tool_run.target.environment.value,
                status=tool_run.status.value,
                input_payload=tool_run.input_payload,
                invocation_context_payload=tool_run.invocation_context_payload,
                output_payload=tool_run.stored_output_payload,
                error_message=tool_run.stored_error_payload,
                created_at=tool_run.created_at,
                started_at=tool_run.started_at,
                completed_at=tool_run.completed_at,
                attempt_count=tool_run.attempt_count,
                max_attempts=tool_run.max_attempts,
                worker_id=tool_run.worker_id,
                heartbeat_at=tool_run.heartbeat_at,
                lease_expires_at=tool_run.lease_expires_at,
                cancel_requested_at=tool_run.cancel_requested_at,
            ),
        )

    def get(self, run_id: str) -> ToolRun | None:
        model = self.session.get(ToolRunModel, run_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self) -> list[ToolRun]:
        models = self.session.scalars(
            select(ToolRunModel).order_by(ToolRunModel.created_at.desc()),
        ).all()
        return [self._to_entity(model) for model in models]

    def list_for_tool(self, tool_id: str) -> list[ToolRun]:
        models = self.session.scalars(
            select(ToolRunModel)
            .where(ToolRunModel.tool_id == tool_id)
            .order_by(ToolRunModel.created_at.desc()),
        ).all()
        return [self._to_entity(model) for model in models]

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
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            attempt_count=model.attempt_count,
            max_attempts=model.max_attempts,
            worker_id=model.worker_id,
            heartbeat_at=model.heartbeat_at,
            lease_expires_at=model.lease_expires_at,
            cancel_requested_at=model.cancel_requested_at,
        )
