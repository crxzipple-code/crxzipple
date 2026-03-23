from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    DeliveryTarget,
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.orchestration.infrastructure.persistence.models import (
    OrchestrationRunModel,
    OrchestrationRunWaitModel,
)


class SqlAlchemyOrchestrationRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, run: OrchestrationRun) -> None:
        self.session.merge(
            OrchestrationRunModel(
                id=run.id,
                status=run.status.value,
                stage=run.stage.value,
                bulk_key=run.bulk_key,
                active_session_id=run.active_session_id,
                agent_id=run.agent_id,
                lane_key=run.lane_key,
                queue_policy=run.queue_policy.value,
                priority=run.priority,
                current_step=run.current_step,
                max_steps=run.max_steps,
                pending_tool_run_ids=list(run.pending_tool_run_ids),
                waiting_reason=run.waiting_reason,
                inbound_instruction_payload=run.inbound_instruction.to_payload(),
                delivery_target_payload=(
                    run.delivery_target.to_payload()
                    if run.delivery_target is not None
                    else None
                ),
                result_payload=(
                    dict(run.result_payload)
                    if run.result_payload is not None
                    else None
                ),
                error_payload=(
                    run.error.to_payload()
                    if run.error is not None
                    else None
                ),
                metadata_payload=dict(run.metadata),
                worker_id=run.worker_id,
                created_at=run.created_at,
                updated_at=run.updated_at,
                queued_at=run.queued_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
            ),
        )

    def get(self, run_id: str) -> OrchestrationRun | None:
        model = self.session.get(OrchestrationRunModel, run_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
    ) -> list[OrchestrationRun]:
        statement = select(OrchestrationRunModel)
        if status is not None:
            statement = statement.where(OrchestrationRunModel.status == status.value)
        models = self.session.scalars(
            statement.order_by(
                OrchestrationRunModel.created_at.desc(),
                OrchestrationRunModel.id.desc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: OrchestrationRunModel) -> OrchestrationRun:
        return OrchestrationRun(
            id=model.id,
            status=OrchestrationRunStatus(model.status),
            stage=OrchestrationRunStage(model.stage),
            bulk_key=model.bulk_key,
            active_session_id=model.active_session_id,
            agent_id=model.agent_id,
            lane_key=model.lane_key,
            queue_policy=OrchestrationQueuePolicy(model.queue_policy),
            priority=model.priority,
            current_step=model.current_step,
            max_steps=model.max_steps,
            pending_tool_run_ids=tuple(model.pending_tool_run_ids or []),
            waiting_reason=model.waiting_reason,
            inbound_instruction=InboundInstruction.from_payload(
                model.inbound_instruction_payload,
            ),
            delivery_target=DeliveryTarget.from_payload(model.delivery_target_payload),
            result_payload=(
                dict(model.result_payload)
                if isinstance(model.result_payload, dict)
                else None
            ),
            error=OrchestrationErrorPayload.from_payload(model.error_payload),
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
            worker_id=model.worker_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
            queued_at=model.queued_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )


class SqlAlchemyOrchestrationRunWaitRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_tool_waits(self, run_id: str, tool_run_ids: tuple[str, ...]) -> None:
        self.session.execute(
            delete(OrchestrationRunWaitModel).where(
                OrchestrationRunWaitModel.run_id == run_id,
            ),
        )
        timestamp = datetime.now(timezone.utc)
        for tool_run_id in dict.fromkeys(tool_run_ids):
            self.session.merge(
                OrchestrationRunWaitModel(
                    run_id=run_id,
                    tool_run_id=tool_run_id,
                    created_at=timestamp,
                ),
            )

    def delete_for_run(self, run_id: str) -> None:
        self.session.execute(
            delete(OrchestrationRunWaitModel).where(
                OrchestrationRunWaitModel.run_id == run_id,
            ),
        )

    def list_run_ids_for_tool_run(self, tool_run_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(OrchestrationRunWaitModel.run_id)
                .where(OrchestrationRunWaitModel.tool_run_id == tool_run_id)
                .order_by(OrchestrationRunWaitModel.run_id.asc()),
            ).all(),
        )
