from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.tool.domain.entities import Tool, ToolRun
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunStatus,
    ToolSourceKind,
)
from crxzipple.modules.tool.infrastructure.persistence.models import ToolModel, ToolRunModel


class SqlAlchemyToolRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, tool: Tool) -> None:
        self.session.merge(
            ToolModel(
                id=tool.id,
                name=tool.name,
                description=tool.description,
                kind=tool.kind.value,
                parameters=[
                    {
                        "name": parameter.name,
                        "data_type": parameter.data_type,
                        "description": parameter.description,
                        "required": parameter.required,
                    }
                    for parameter in tool.parameters
                ],
                tags=list(tool.tags),
                required_effect_ids=list(tool.required_effect_ids),
                requires_confirmation=tool.execution_policy.requires_confirmation,
                mutates_state=tool.execution_policy.mutates_state,
                timeout_seconds=tool.execution_policy.timeout_seconds,
                supported_modes=[
                    mode.value for mode in tool.execution_support.supported_modes
                ],
                supported_strategies=[
                    strategy.value
                    for strategy in tool.execution_support.supported_strategies
                ],
                supported_environments=[
                    environment.value
                    for environment in tool.execution_support.supported_environments
                ],
                source_kind=tool.source_kind.value,
                runtime_key=tool.runtime_key,
                enabled=tool.enabled,
            ),
        )

    def get(self, tool_id: str) -> Tool | None:
        model = self.session.get(ToolModel, tool_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(self) -> list[Tool]:
        models = self.session.scalars(select(ToolModel).order_by(ToolModel.id)).all()
        return [self._to_entity(model) for model in models]

    def list_enabled(self) -> list[Tool]:
        models = self.session.scalars(
            select(ToolModel).where(ToolModel.enabled.is_(True)).order_by(ToolModel.id),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: ToolModel) -> Tool:
        return Tool(
            id=model.id,
            name=model.name,
            description=model.description,
            kind=ToolKind(model.kind),
            parameters=tuple(
                ToolParameter(
                    name=str(parameter["name"]),
                    data_type=str(parameter["data_type"]),
                    description=str(parameter.get("description", "")),
                    required=bool(parameter.get("required", True)),
                )
                for parameter in model.parameters
            ),
            tags=tuple(model.tags),
            required_effect_ids=tuple(model.required_effect_ids),
            execution_policy=ToolExecutionPolicy(
                timeout_seconds=model.timeout_seconds,
                requires_confirmation=model.requires_confirmation,
                mutates_state=model.mutates_state,
            ),
            execution_support=ToolExecutionSupport(
                supported_modes=tuple(ToolMode(mode) for mode in model.supported_modes),
                supported_strategies=tuple(
                    ToolExecutionStrategy(strategy)
                    for strategy in model.supported_strategies
                ),
                supported_environments=tuple(
                    ToolEnvironment(environment)
                    for environment in model.supported_environments
                ),
            ),
            source_kind=ToolSourceKind(model.source_kind),
            runtime_key=model.runtime_key,
            enabled=model.enabled,
        )


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
