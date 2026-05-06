from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from crxzipple.modules.orchestration.domain.entities import (
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
    OrchestrationSchedulerSignal,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    InboundInstruction,
    OrchestrationBoundSessionTarget,
    OrchestrationErrorPayload,
    OrchestrationExecutorLeaseStatus,
    OrchestrationIngressRequestKind,
    OrchestrationIngressStatus,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    OrchestrationSchedulerSignalKind,
    OrchestrationSchedulerSignalStatus,
    ReplyTarget,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.infrastructure.persistence.models import (
    OrchestrationExecutorLeaseModel,
    OrchestrationIngressRequestModel,
    OrchestrationRunModel,
    OrchestrationSchedulerSignalModel,
    OrchestrationRunWaitModel,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.shared.time import (
    coerce_utc_datetime,
    coerce_optional_utc_datetime,
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

    def claim_next(self, *, worker_id: str) -> OrchestrationIngressRequest | None:
        candidate_id = self.session.scalar(
            select(OrchestrationIngressRequestModel.id)
            .where(
                OrchestrationIngressRequestModel.status
                == OrchestrationIngressStatus.QUEUED.value,
            )
            .order_by(
                OrchestrationIngressRequestModel.created_at.asc(),
                OrchestrationIngressRequestModel.id.asc(),
            )
            .limit(1),
        )
        if candidate_id is None:
            return None
        timestamp = datetime.now(timezone.utc)
        updated = self.session.execute(
            update(OrchestrationIngressRequestModel)
            .where(
                OrchestrationIngressRequestModel.id == candidate_id,
                OrchestrationIngressRequestModel.status
                == OrchestrationIngressStatus.QUEUED.value,
            )
            .values(
                status=OrchestrationIngressStatus.PROCESSING.value,
                worker_id=worker_id,
                claimed_at=timestamp,
                updated_at=timestamp,
            ),
        )
        if updated.rowcount != 1:
            return None
        self.session.flush()
        model = self.session.get(OrchestrationIngressRequestModel, candidate_id)
        if model is None:
            return None
        request = self._to_entity(model)
        request.claim(worker_id=worker_id, claimed_at=timestamp)
        self.add(request)
        return request

    def claim_for_run(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationIngressRequest | None:
        candidate_id = self.session.scalar(
            select(OrchestrationIngressRequestModel.id)
            .where(
                OrchestrationIngressRequestModel.run_id == run_id,
                OrchestrationIngressRequestModel.status
                == OrchestrationIngressStatus.QUEUED.value,
            )
            .order_by(OrchestrationIngressRequestModel.created_at.asc())
            .limit(1),
        )
        if candidate_id is None:
            return None
        timestamp = datetime.now(timezone.utc)
        updated = self.session.execute(
            update(OrchestrationIngressRequestModel)
            .where(
                OrchestrationIngressRequestModel.id == candidate_id,
                OrchestrationIngressRequestModel.status
                == OrchestrationIngressStatus.QUEUED.value,
            )
            .values(
                status=OrchestrationIngressStatus.PROCESSING.value,
                worker_id=worker_id,
                claimed_at=timestamp,
                updated_at=timestamp,
            ),
        )
        if updated.rowcount != 1:
            return None
        self.session.flush()
        model = self.session.get(OrchestrationIngressRequestModel, candidate_id)
        if model is None:
            return None
        request = self._to_entity(model)
        request.claim(worker_id=worker_id, claimed_at=timestamp)
        self.add(request)
        return request

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


class SqlAlchemyOrchestrationSchedulerSignalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, signal: OrchestrationSchedulerSignal) -> None:
        self.session.merge(
            OrchestrationSchedulerSignalModel(
                id=signal.id,
                signal_kind=signal.signal_kind.value,
                signal_payload=dict(signal.signal_payload),
                status=signal.status.value,
                worker_id=signal.worker_id,
                error_payload=(
                    signal.error.to_payload()
                    if signal.error is not None
                    else None
                ),
                created_at=signal.created_at,
                updated_at=signal.updated_at,
                claimed_at=signal.claimed_at,
                completed_at=signal.completed_at,
            ),
        )

    def get(self, signal_id: str) -> OrchestrationSchedulerSignal | None:
        model = self.session.get(OrchestrationSchedulerSignalModel, signal_id)
        if model is None:
            return None
        return self._to_entity(model)

    def claim_next(self, *, worker_id: str) -> OrchestrationSchedulerSignal | None:
        model = self.session.scalars(
            select(OrchestrationSchedulerSignalModel)
            .where(
                OrchestrationSchedulerSignalModel.status
                == OrchestrationSchedulerSignalStatus.QUEUED.value,
            )
            .order_by(
                OrchestrationSchedulerSignalModel.created_at.asc(),
                OrchestrationSchedulerSignalModel.id.asc(),
            )
        ).first()
        if model is None:
            return None
        signal = self._to_entity(model)
        signal.claim(worker_id=worker_id)
        self.add(signal)
        return signal

    def list(
        self,
        *,
        status: OrchestrationSchedulerSignalStatus | None = None,
    ) -> list[OrchestrationSchedulerSignal]:
        statement = select(OrchestrationSchedulerSignalModel)
        if status is not None:
            statement = statement.where(
                OrchestrationSchedulerSignalModel.status == status.value,
            )
        models = self.session.scalars(
            statement.order_by(
                OrchestrationSchedulerSignalModel.created_at.desc(),
                OrchestrationSchedulerSignalModel.id.desc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(
        model: OrchestrationSchedulerSignalModel,
    ) -> OrchestrationSchedulerSignal:
        return OrchestrationSchedulerSignal(
            id=model.id,
            signal_kind=OrchestrationSchedulerSignalKind(model.signal_kind),
            signal_payload=(
                dict(model.signal_payload)
                if isinstance(model.signal_payload, dict)
                else {}
            ),
            status=OrchestrationSchedulerSignalStatus(model.status),
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
