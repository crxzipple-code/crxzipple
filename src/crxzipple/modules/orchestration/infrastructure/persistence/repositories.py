from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from crxzipple.modules.orchestration.domain.entities import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionOwnerReference,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    InboundInstruction,
    OrchestrationBoundSessionTarget,
    OrchestrationErrorPayload,
    OrchestrationExecutorLeaseStatus,
    OrchestrationIngressRequestKind,
    OrchestrationIngressStatus,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    ReplyTarget,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.infrastructure.persistence.models import (
    OrchestrationExecutionChainModel,
    OrchestrationExecutionStepItemModel,
    OrchestrationExecutionStepModel,
    OrchestrationExecutorLeaseModel,
    OrchestrationIngressRequestModel,
    OrchestrationRunModel,
    OrchestrationRunWaitModel,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.shared.time import (
    coerce_utc_datetime,
    coerce_optional_utc_datetime,
)


def _owner_from_model(
    owner_kind: str | None,
    owner_id: str | None,
) -> ExecutionOwnerReference | None:
    if owner_kind is None or owner_id is None:
        return None
    return ExecutionOwnerReference(owner_kind=owner_kind, owner_id=owner_id)


class SqlAlchemyExecutionChainRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._pending_models: dict[str, OrchestrationExecutionChainModel] = {}

    def add(self, chain: ExecutionChain) -> None:
        model = self._pending_models.get(chain.id)
        if model is None:
            with self.session.no_autoflush:
                model = self.session.get(OrchestrationExecutionChainModel, chain.id)
            if model is None:
                model = OrchestrationExecutionChainModel(
                    id=chain.id,
                    turn_id=chain.turn_id,
                    status=chain.status.value,
                    active_step_id=chain.active_step_id,
                    step_count=chain.step_count,
                    error_payload=None,
                    created_at=chain.created_at,
                    started_at=chain.started_at,
                    completed_at=chain.completed_at,
                    updated_at=chain.updated_at,
                )
                self.session.add(model)
            self._pending_models[chain.id] = model
        model.turn_id = chain.turn_id
        model.status = chain.status.value
        model.active_step_id = chain.active_step_id
        model.step_count = chain.step_count
        model.error_payload = (
            chain.error_payload.to_payload()
            if chain.error_payload is not None
            else None
        )
        model.created_at = chain.created_at
        model.started_at = chain.started_at
        model.completed_at = chain.completed_at
        model.updated_at = chain.updated_at

    def get(self, chain_id: str) -> ExecutionChain | None:
        model = self._pending_models.get(chain_id)
        if model is None:
            model = self.session.get(OrchestrationExecutionChainModel, chain_id)
        return self._to_entity(model) if model is not None else None

    def get_active_for_turn(self, turn_id: str) -> ExecutionChain | None:
        pending = [
            model
            for model in self._pending_models.values()
            if model.turn_id == turn_id
            and model.status
            in {
                ExecutionChainStatus.CREATED.value,
                ExecutionChainStatus.RUNNING.value,
                ExecutionChainStatus.WAITING.value,
            }
        ]
        if pending:
            pending.sort(key=lambda model: (model.created_at, model.id), reverse=True)
            return self._to_entity(pending[0])
        model = self.session.scalars(
            select(OrchestrationExecutionChainModel)
            .where(
                OrchestrationExecutionChainModel.turn_id == turn_id,
                OrchestrationExecutionChainModel.status.in_(
                    (
                        ExecutionChainStatus.CREATED.value,
                        ExecutionChainStatus.RUNNING.value,
                        ExecutionChainStatus.WAITING.value,
                    ),
                ),
            )
            .order_by(
                OrchestrationExecutionChainModel.created_at.desc(),
                OrchestrationExecutionChainModel.id.desc(),
            )
            .limit(1),
        ).first()
        return self._to_entity(model) if model is not None else None

    def list_for_turn(
        self,
        turn_id: str,
        *,
        status: ExecutionChainStatus | None = None,
    ) -> list[ExecutionChain]:
        statement = select(OrchestrationExecutionChainModel).where(
            OrchestrationExecutionChainModel.turn_id == turn_id,
        )
        if status is not None:
            statement = statement.where(
                OrchestrationExecutionChainModel.status == status.value,
            )
        models = list(
            self.session.scalars(
                statement.order_by(
                    OrchestrationExecutionChainModel.created_at.asc(),
                    OrchestrationExecutionChainModel.id.asc(),
                ),
            ).all(),
        )
        known_ids = {model.id for model in models}
        for model in self._pending_models.values():
            if model.id in known_ids or model.turn_id != turn_id:
                continue
            if status is not None and model.status != status.value:
                continue
            models.append(model)
        models.sort(key=lambda model: (model.created_at, model.id))
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: OrchestrationExecutionChainModel) -> ExecutionChain:
        return ExecutionChain(
            id=model.id,
            turn_id=model.turn_id,
            status=ExecutionChainStatus(model.status),
            active_step_id=model.active_step_id,
            step_count=model.step_count,
            error_payload=OrchestrationErrorPayload.from_payload(model.error_payload),
            created_at=coerce_utc_datetime(model.created_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            updated_at=coerce_utc_datetime(model.updated_at),
        )


class SqlAlchemyExecutionStepRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._pending_models: dict[str, OrchestrationExecutionStepModel] = {}

    def add(self, step: ExecutionStep) -> None:
        model = self._pending_models.get(step.id)
        if model is None:
            with self.session.no_autoflush:
                model = self.session.get(OrchestrationExecutionStepModel, step.id)
            if model is None:
                model = OrchestrationExecutionStepModel(
                    id=step.id,
                    chain_id=step.chain_id,
                    turn_id=step.turn_id,
                    step_index=step.step_index,
                    kind=step.kind.value,
                    status=step.status.value,
                    created_at=step.created_at,
                    updated_at=step.updated_at,
                )
                self.session.add(model)
            self._pending_models[step.id] = model
        model.chain_id = step.chain_id
        model.turn_id = step.turn_id
        model.step_index = step.step_index
        model.kind = step.kind.value
        model.status = step.status.value
        model.dispatch_task_id = step.dispatch_task_id
        model.owner_kind = step.owner.owner_kind if step.owner is not None else None
        model.owner_id = step.owner.owner_id if step.owner is not None else None
        model.correlation_key = step.correlation_key
        model.error_payload = (
            step.error_payload.to_payload()
            if step.error_payload is not None
            else None
        )
        model.created_at = step.created_at
        model.started_at = step.started_at
        model.completed_at = step.completed_at
        model.updated_at = step.updated_at

    def get(self, step_id: str) -> ExecutionStep | None:
        model = self._pending_models.get(step_id)
        if model is None:
            model = self.session.get(OrchestrationExecutionStepModel, step_id)
        return self._to_entity(model) if model is not None else None

    def get_by_correlation_key(self, correlation_key: str) -> ExecutionStep | None:
        normalized = correlation_key.strip()
        if not normalized:
            return None
        for model in self._pending_models.values():
            if model.correlation_key == normalized:
                return self._to_entity(model)
        model = self.session.scalars(
            select(OrchestrationExecutionStepModel)
            .where(OrchestrationExecutionStepModel.correlation_key == normalized)
            .limit(1),
        ).first()
        return self._to_entity(model) if model is not None else None

    def list_for_chain(
        self,
        chain_id: str,
        *,
        status: ExecutionStepStatus | None = None,
    ) -> list[ExecutionStep]:
        statement = select(OrchestrationExecutionStepModel).where(
            OrchestrationExecutionStepModel.chain_id == chain_id,
        )
        if status is not None:
            statement = statement.where(
                OrchestrationExecutionStepModel.status == status.value,
            )
        models = list(
            self.session.scalars(
                statement.order_by(
                    OrchestrationExecutionStepModel.step_index.asc(),
                    OrchestrationExecutionStepModel.id.asc(),
                ),
            ).all(),
        )
        known_ids = {model.id for model in models}
        for model in self._pending_models.values():
            if model.id in known_ids or model.chain_id != chain_id:
                continue
            if status is not None and model.status != status.value:
                continue
            models.append(model)
        models.sort(key=lambda model: (model.step_index, model.id))
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: OrchestrationExecutionStepModel) -> ExecutionStep:
        return ExecutionStep(
            id=model.id,
            chain_id=model.chain_id,
            turn_id=model.turn_id,
            step_index=model.step_index,
            kind=ExecutionStepKind(model.kind),
            status=ExecutionStepStatus(model.status),
            dispatch_task_id=model.dispatch_task_id,
            owner=_owner_from_model(model.owner_kind, model.owner_id),
            correlation_key=model.correlation_key,
            error_payload=OrchestrationErrorPayload.from_payload(model.error_payload),
            created_at=coerce_utc_datetime(model.created_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            updated_at=coerce_utc_datetime(model.updated_at),
        )


class SqlAlchemyExecutionStepItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._pending_models: dict[str, OrchestrationExecutionStepItemModel] = {}

    def add(self, item: ExecutionStepItem) -> None:
        model = self._pending_models.get(item.id)
        if model is None:
            with self.session.no_autoflush:
                model = self.session.get(OrchestrationExecutionStepItemModel, item.id)
            if model is None:
                with self.session.no_autoflush:
                    parent_step = self.session.get(
                        OrchestrationExecutionStepModel,
                        item.step_id,
                    )
                if parent_step is None:
                    self.session.flush()
                model = OrchestrationExecutionStepItemModel(
                    id=item.id,
                    step_id=item.step_id,
                    chain_id=item.chain_id,
                    turn_id=item.turn_id,
                    item_index=item.item_index,
                    kind=item.kind.value,
                    status=item.status.value,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                self.session.add(model)
            self._pending_models[item.id] = model
        model.step_id = item.step_id
        model.chain_id = item.chain_id
        model.turn_id = item.turn_id
        model.item_index = item.item_index
        model.kind = item.kind.value
        model.status = item.status.value
        model.owner_kind = item.owner.owner_kind if item.owner is not None else None
        model.owner_id = item.owner.owner_id if item.owner is not None else None
        model.correlation_key = item.correlation_key
        model.source_event_id = item.source_event_id
        model.payload_ref = (
            dict(item.payload_ref)
            if item.payload_ref is not None
            else None
        )
        model.summary_payload = (
            dict(item.summary_payload)
            if item.summary_payload is not None
            else None
        )
        model.error_payload = (
            item.error_payload.to_payload()
            if item.error_payload is not None
            else None
        )
        model.created_at = item.created_at
        model.completed_at = item.completed_at
        model.updated_at = item.updated_at

    def get(self, item_id: str) -> ExecutionStepItem | None:
        model = self._pending_models.get(item_id)
        if model is None:
            model = self.session.get(OrchestrationExecutionStepItemModel, item_id)
        return self._to_entity(model) if model is not None else None

    def find_by_owner_reference(
        self,
        owner: ExecutionOwnerReference,
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        statement = select(OrchestrationExecutionStepItemModel).where(
            OrchestrationExecutionStepItemModel.owner_kind == owner.owner_kind,
            OrchestrationExecutionStepItemModel.owner_id == owner.owner_id,
        )
        if status is not None:
            statement = statement.where(
                OrchestrationExecutionStepItemModel.status == status.value,
            )
        models = list(
            self.session.scalars(
                statement.order_by(
                    OrchestrationExecutionStepItemModel.created_at.asc(),
                    OrchestrationExecutionStepItemModel.id.asc(),
                ),
            ).all(),
        )
        known_ids = {model.id for model in models}
        for model in self._pending_models.values():
            if model.id in known_ids:
                continue
            if model.owner_kind != owner.owner_kind or model.owner_id != owner.owner_id:
                continue
            if status is not None and model.status != status.value:
                continue
            models.append(model)
        models.sort(key=lambda model: (model.created_at, model.id))
        return [self._to_entity(model) for model in models]

    def list_for_step(
        self,
        step_id: str,
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        statement = select(OrchestrationExecutionStepItemModel).where(
            OrchestrationExecutionStepItemModel.step_id == step_id,
        )
        if status is not None:
            statement = statement.where(
                OrchestrationExecutionStepItemModel.status == status.value,
            )
        models = list(
            self.session.scalars(
                statement.order_by(
                    OrchestrationExecutionStepItemModel.item_index.asc(),
                    OrchestrationExecutionStepItemModel.id.asc(),
                ),
            ).all(),
        )
        known_ids = {model.id for model in models}
        for model in self._pending_models.values():
            if model.id in known_ids or model.step_id != step_id:
                continue
            if status is not None and model.status != status.value:
                continue
            models.append(model)
        models.sort(key=lambda model: (model.item_index, model.id))
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: OrchestrationExecutionStepItemModel) -> ExecutionStepItem:
        return ExecutionStepItem(
            id=model.id,
            step_id=model.step_id,
            chain_id=model.chain_id,
            turn_id=model.turn_id,
            item_index=model.item_index,
            kind=ExecutionStepItemKind(model.kind),
            status=ExecutionStepItemStatus(model.status),
            owner=_owner_from_model(model.owner_kind, model.owner_id),
            correlation_key=model.correlation_key,
            source_event_id=model.source_event_id,
            payload_ref=(
                dict(model.payload_ref)
                if isinstance(model.payload_ref, dict)
                else None
            ),
            summary_payload=(
                dict(model.summary_payload)
                if isinstance(model.summary_payload, dict)
                else None
            ),
            error_payload=OrchestrationErrorPayload.from_payload(model.error_payload),
            created_at=coerce_utc_datetime(model.created_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
            updated_at=coerce_utc_datetime(model.updated_at),
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
                active_session_id=run.active_session_id,
                agent_id=run.agent_id,
                lane_key=run.lane_key,
                lane_lock_key=run.lane_lock_key,
                queue_policy=run.queue_policy.value,
                priority=run.priority,
                current_step=run.current_step,
                max_steps=run.max_steps,
                pending_tool_run_ids=list(run.pending_tool_run_ids),
                waiting_reason=run.waiting_reason,
                pending_approval_request_payload=(
                    dict(run.pending_approval_request_payload)
                    if run.pending_approval_request_payload is not None
                    else None
                ),
                last_approval_resolution_payload=(
                    dict(run.last_approval_resolution_payload)
                    if run.last_approval_resolution_payload is not None
                    else None
                ),
                recovery_contract_payload=(
                    dict(run.recovery_contract_payload)
                    if run.recovery_contract_payload is not None
                    else None
                ),
                inbound_instruction_payload=run.inbound_instruction.to_payload(),
                reply_target_payload=(
                    run.reply_target.to_payload()
                    if run.reply_target is not None
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
        session_key: str | None = None,
    ) -> list[OrchestrationRun]:
        statement = select(OrchestrationRunModel)
        if status is not None:
            statement = statement.where(OrchestrationRunModel.status == status.value)
        normalized_session_key = (session_key or "").strip()
        if normalized_session_key:
            statement = statement.where(
                OrchestrationRunModel.metadata_payload["session_key"].as_string()
                == normalized_session_key,
            )
        models = self.session.scalars(
            statement.order_by(
                OrchestrationRunModel.created_at.desc(),
                OrchestrationRunModel.id.desc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    def find_next_assigned(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None
        statement = select(OrchestrationRunModel).where(
            OrchestrationRunModel.status == OrchestrationRunStatus.RUNNING.value,
            OrchestrationRunModel.worker_id == normalized_worker_id,
        )
        if exclude_run_ids:
            statement = statement.where(
                OrchestrationRunModel.id.notin_(tuple(exclude_run_ids)),
            )
        model = self.session.scalars(
            statement
            .order_by(
                OrchestrationRunModel.started_at.asc(),
                OrchestrationRunModel.updated_at.asc(),
                OrchestrationRunModel.id.asc(),
            )
            .limit(1),
        ).first()
        return self._to_entity(model) if model is not None else None

    def claim_queued_for_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        claimed_at: datetime | None = None,
    ) -> OrchestrationRun | None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            return None
        timestamp = claimed_at or datetime.now(timezone.utc)
        active_run = aliased(OrchestrationRunModel)
        active_same_lane = (
            select(active_run.id)
            .where(
                active_run.id != OrchestrationRunModel.id,
                active_run.lane_lock_key == OrchestrationRunModel.lane_key,
                active_run.status.in_(
                    (
                        OrchestrationRunStatus.RUNNING.value,
                        OrchestrationRunStatus.WAITING.value,
                    ),
                ),
            )
            .exists()
        )
        try:
            updated = self.session.execute(
                update(OrchestrationRunModel)
                .where(
                    OrchestrationRunModel.id == run_id,
                    OrchestrationRunModel.status == OrchestrationRunStatus.QUEUED.value,
                    or_(
                        OrchestrationRunModel.lane_key.is_(None),
                        ~active_same_lane,
                    ),
                )
                .values(
                    status=OrchestrationRunStatus.RUNNING.value,
                stage=OrchestrationRunStage.RUNNING.value,
                worker_id=normalized_worker_id,
                lane_lock_key=OrchestrationRunModel.lane_key,
                started_at=timestamp,
                    updated_at=timestamp,
                ),
            )
        except IntegrityError:
            self.session.rollback()
            return None
        if updated.rowcount != 1:
            return None
        self.session.flush()
        model = self.session.get(OrchestrationRunModel, run_id)
        if model is None:
            return None
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: OrchestrationRunModel) -> OrchestrationRun:
        return OrchestrationRun(
            id=model.id,
            status=OrchestrationRunStatus(model.status),
            stage=OrchestrationRunStage(model.stage),
            active_session_id=model.active_session_id,
            agent_id=model.agent_id,
            lane_key=model.lane_key,
            lane_lock_key=model.lane_lock_key,
            queue_policy=OrchestrationQueuePolicy(model.queue_policy),
            priority=model.priority,
            current_step=model.current_step,
            max_steps=model.max_steps,
            pending_tool_run_ids=tuple(model.pending_tool_run_ids or []),
            waiting_reason=model.waiting_reason,
            pending_approval_request_payload=(
                dict(model.pending_approval_request_payload)
                if isinstance(model.pending_approval_request_payload, dict)
                else None
            ),
            last_approval_resolution_payload=(
                dict(model.last_approval_resolution_payload)
                if isinstance(model.last_approval_resolution_payload, dict)
                else None
            ),
            recovery_contract_payload=(
                dict(model.recovery_contract_payload)
                if isinstance(model.recovery_contract_payload, dict)
                else None
            ),
            inbound_instruction=InboundInstruction.from_payload(
                model.inbound_instruction_payload,
            ),
            reply_target=ReplyTarget.from_payload(model.reply_target_payload),
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
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
            queued_at=coerce_optional_utc_datetime(model.queued_at),
            started_at=coerce_optional_utc_datetime(model.started_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
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


class SqlAlchemyOrchestrationIngressRequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, request: OrchestrationIngressRequest) -> None:
        self.session.merge(
            OrchestrationIngressRequestModel(
                id=request.id,
                run_id=request.run_id,
                status=request.status.value,
                kind=request.kind.value,
                route_context_payload=dict(request.route_context_payload),
                bound_session_payload=dict(request.bound_session_payload),
                requested_llm_id=request.requested_llm_id,
                ensure_session=request.ensure_session,
                touch_activity=request.touch_activity,
                reset_policy_payload=dict(request.reset_policy_payload),
                prepare_metadata_payload=dict(request.prepare_metadata),
                queue_policy=request.queue_policy.value,
                priority=request.priority,
                worker_id=request.worker_id,
                error_payload=(
                    request.error.to_payload()
                    if request.error is not None
                    else None
                ),
                created_at=request.created_at,
                updated_at=request.updated_at,
                claimed_at=request.claimed_at,
                completed_at=request.completed_at,
            ),
        )

    def get(self, request_id: str) -> OrchestrationIngressRequest | None:
        model = self.session.get(OrchestrationIngressRequestModel, request_id)
        if model is None:
            return None
        return self._to_entity(model)

    def get_by_run_id(self, run_id: str) -> OrchestrationIngressRequest | None:
        model = self.session.scalars(
            select(OrchestrationIngressRequestModel)
            .where(OrchestrationIngressRequestModel.run_id == run_id)
            .order_by(OrchestrationIngressRequestModel.created_at.desc())
        ).first()
        if model is None:
            return None
        return self._to_entity(model)

    def list(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]:
        statement = select(OrchestrationIngressRequestModel)
        if status is not None:
            statement = statement.where(
                OrchestrationIngressRequestModel.status == status.value,
            )
        models = self.session.scalars(
            statement.order_by(
                OrchestrationIngressRequestModel.created_at.desc(),
                OrchestrationIngressRequestModel.id.desc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: OrchestrationIngressRequestModel) -> OrchestrationIngressRequest:
        route_context_payload = (
            dict(model.route_context_payload)
            if isinstance(model.route_context_payload, dict)
            else {}
        )
        if "direct_scope" in route_context_payload:
            direct_scope = route_context_payload.get("direct_scope")
            route_context_payload["direct_scope"] = (
                direct_scope
                if isinstance(direct_scope, DirectSessionScope)
                else DirectSessionScope(str(direct_scope))
            )
        bound_session_payload = (
            dict(model.bound_session_payload)
            if isinstance(model.bound_session_payload, dict)
            else {}
        )
        bound_target = OrchestrationBoundSessionTarget.from_payload(bound_session_payload)
        return OrchestrationIngressRequest(
            id=model.id,
            run_id=model.run_id,
            kind=OrchestrationIngressRequestKind(model.kind),
            route_context_payload=route_context_payload,
            bound_session_payload=(
                bound_target.to_payload() if bound_target is not None else {}
            ),
            requested_llm_id=model.requested_llm_id,
            ensure_session=model.ensure_session,
            touch_activity=model.touch_activity,
            reset_policy_payload=(
                dict(model.reset_policy_payload)
                if isinstance(model.reset_policy_payload, dict)
                else {}
            ),
            prepare_metadata=(
                dict(model.prepare_metadata_payload)
                if isinstance(model.prepare_metadata_payload, dict)
                else {}
            ),
            queue_policy=OrchestrationQueuePolicy(model.queue_policy),
            priority=model.priority,
            status=OrchestrationIngressStatus(model.status),
            worker_id=model.worker_id,
            error=OrchestrationErrorPayload.from_payload(model.error_payload),
            created_at=coerce_utc_datetime(model.created_at),
            updated_at=coerce_utc_datetime(model.updated_at),
            claimed_at=coerce_optional_utc_datetime(model.claimed_at),
            completed_at=coerce_optional_utc_datetime(model.completed_at),
        )


class SqlAlchemyOrchestrationExecutorLeaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, lease: OrchestrationExecutorLease) -> None:
        self.session.merge(
            OrchestrationExecutorLeaseModel(
                worker_id=lease.worker_id,
                status=lease.status.value,
                max_inflight_assignments=lease.max_inflight_assignments,
                inflight_assignment_count=lease.inflight_assignment_count,
                metadata_payload=dict(lease.metadata),
                created_at=lease.created_at,
                updated_at=lease.updated_at,
                last_heartbeat_at=lease.last_heartbeat_at,
                lease_expires_at=lease.lease_expires_at,
            ),
        )

    def get(self, worker_id: str) -> OrchestrationExecutorLease | None:
        model = self.session.get(OrchestrationExecutorLeaseModel, worker_id)
        if model is None:
            return None
        return self._to_entity(model)

    def heartbeat(
        self,
        *,
        worker_id: str,
        max_inflight_assignments: int | None = None,
        inflight_assignment_count: int | None = None,
        draining: bool | None = None,
        metadata: dict[str, object] | None = None,
        lease_seconds: int | None = None,
    ) -> OrchestrationExecutorLease | None:
        model = self.session.get(OrchestrationExecutorLeaseModel, worker_id)
        if model is None:
            return None
        next_max = (
            max_inflight_assignments
            if max_inflight_assignments is not None
            else model.max_inflight_assignments
        )
        next_inflight = (
            inflight_assignment_count
            if inflight_assignment_count is not None
            else model.inflight_assignment_count
        )
        if next_max <= 0:
            raise OrchestrationValidationError(
                "Orchestration executor max_inflight_assignments must be positive.",
            )
        if next_inflight < 0:
            raise OrchestrationValidationError(
                "Orchestration executor inflight_assignment_count cannot be negative.",
            )
        if next_inflight > next_max:
            raise OrchestrationValidationError(
                "Orchestration executor inflight_assignment_count cannot exceed max capacity.",
            )

        timestamp = datetime.now(timezone.utc)
        if draining is not None:
            model.status = (
                OrchestrationExecutorLeaseStatus.DRAINING.value
                if draining
                else OrchestrationExecutorLeaseStatus.ONLINE.value
            )
        elif model.status == OrchestrationExecutorLeaseStatus.OFFLINE.value:
            model.status = OrchestrationExecutorLeaseStatus.ONLINE.value
        if max_inflight_assignments is not None:
            model.max_inflight_assignments = next_max
        if inflight_assignment_count is not None:
            model.inflight_assignment_count = next_inflight
        if metadata:
            current_metadata = (
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            )
            current_metadata.update(metadata)
            model.metadata_payload = current_metadata
        model.last_heartbeat_at = timestamp
        model.updated_at = timestamp
        if lease_seconds is not None:
            model.lease_expires_at = timestamp + timedelta(seconds=lease_seconds)
        self.session.flush()
        self.session.refresh(model)
        return self._to_entity(model)

    def release_assignment_capacity(self, *, worker_id: str, count: int = 1) -> None:
        if count <= 0:
            raise ValueError("release count must be positive")
        next_count = OrchestrationExecutorLeaseModel.inflight_assignment_count - count
        self.session.execute(
            update(OrchestrationExecutorLeaseModel)
            .where(OrchestrationExecutorLeaseModel.worker_id == worker_id)
            .values(
                inflight_assignment_count=case(
                    (next_count < 0, 0),
                    else_=next_count,
                ),
                updated_at=datetime.now(timezone.utc),
            ),
        )

    def claim_assignment_capacity(
        self,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> OrchestrationExecutorLease | None:
        timestamp = datetime.now(timezone.utc)
        updated = self.session.execute(
            update(OrchestrationExecutorLeaseModel)
            .where(
                OrchestrationExecutorLeaseModel.worker_id == worker_id,
                OrchestrationExecutorLeaseModel.status
                == OrchestrationExecutorLeaseStatus.ONLINE.value,
                OrchestrationExecutorLeaseModel.inflight_assignment_count
                < OrchestrationExecutorLeaseModel.max_inflight_assignments,
                or_(
                    OrchestrationExecutorLeaseModel.lease_expires_at.is_(None),
                    OrchestrationExecutorLeaseModel.lease_expires_at > timestamp,
                ),
            )
            .values(
                inflight_assignment_count=(
                    OrchestrationExecutorLeaseModel.inflight_assignment_count + 1
                ),
                last_heartbeat_at=timestamp,
                updated_at=timestamp,
                lease_expires_at=(
                    timestamp + timedelta(seconds=lease_seconds)
                    if lease_seconds is not None
                    else OrchestrationExecutorLeaseModel.lease_expires_at
                ),
            ),
        )
        if updated.rowcount != 1:
            return None
        self.session.flush()
        model = self.session.get(OrchestrationExecutorLeaseModel, worker_id)
        if model is None:
            return None
        lease = self._to_entity(model)
        lease.record_assignment_capacity_claimed()
        return lease

    def list(
        self,
        *,
        status: OrchestrationExecutorLeaseStatus | None = None,
    ) -> list[OrchestrationExecutorLease]:
        statement = select(OrchestrationExecutorLeaseModel)
        if status is not None:
            statement = statement.where(
                OrchestrationExecutorLeaseModel.status == status.value,
            )
        models = self.session.scalars(
            statement.order_by(
                OrchestrationExecutorLeaseModel.updated_at.desc(),
                OrchestrationExecutorLeaseModel.worker_id.asc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(
        model: OrchestrationExecutorLeaseModel,
    ) -> OrchestrationExecutorLease:
        return OrchestrationExecutorLease(
            id=model.worker_id,
            status=OrchestrationExecutorLeaseStatus(model.status),
            max_inflight_assignments=model.max_inflight_assignments,
            inflight_assignment_count=model.inflight_assignment_count,
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
            created_at=SqlAlchemyOrchestrationExecutorLeaseRepository._aware_datetime(
                model.created_at,
            ),
            updated_at=SqlAlchemyOrchestrationExecutorLeaseRepository._aware_datetime(
                model.updated_at,
            ),
            last_heartbeat_at=SqlAlchemyOrchestrationExecutorLeaseRepository._aware_datetime(
                model.last_heartbeat_at,
            ),
            lease_expires_at=SqlAlchemyOrchestrationExecutorLeaseRepository._aware_datetime(
                model.lease_expires_at,
            ),
        )

    @staticmethod
    def _aware_datetime(value: datetime | None) -> datetime | None:
        return coerce_optional_utc_datetime(value)
