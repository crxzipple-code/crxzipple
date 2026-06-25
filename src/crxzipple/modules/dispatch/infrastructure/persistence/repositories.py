from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, not_, or_, select, update
from sqlalchemy.orm import Session

from crxzipple.modules.dispatch.domain import (
    DispatchErrorPayload,
    DispatchPolicy,
    DispatchTask,
    DispatchTaskStatus,
)
from crxzipple.modules.dispatch.domain.value_objects import utcnow
from crxzipple.modules.dispatch.infrastructure.persistence.models import DispatchTaskModel


class SqlAlchemyDispatchTaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, task: DispatchTask) -> None:
        self.session.merge(
            DispatchTaskModel(
                id=task.id,
                owner_kind=task.owner_kind,
                owner_id=task.owner_id,
                lane_key=task.lane_key,
                status=task.status.value,
                policy=task.policy.value,
                priority=task.priority,
                payload_ref=task.payload_ref,
                metadata_payload=dict(task.metadata),
                waiting_reason=task.waiting_reason,
                error_payload=task.error.to_payload() if task.error is not None else None,
                claimed_by=task.claimed_by,
                claim_token=task.claim_token,
                created_at=task.created_at,
                updated_at=task.updated_at,
                queued_at=task.queued_at,
                claimed_at=task.claimed_at,
                heartbeat_at=task.heartbeat_at,
                lease_expires_at=task.lease_expires_at,
                completed_at=task.completed_at,
            ),
        )

    def get(self, task_id: str) -> DispatchTask | None:
        model = self.session.get(DispatchTaskModel, task_id)
        if model is None:
            return None
        return self._to_entity(model)

    def list(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]:
        statement = select(DispatchTaskModel)
        if status is not None:
            statement = statement.where(DispatchTaskModel.status == status.value)
        if owner_kind is not None:
            statement = statement.where(DispatchTaskModel.owner_kind == owner_kind)
        if lane_key is not None:
            statement = statement.where(DispatchTaskModel.lane_key == lane_key)
        models = self.session.scalars(
            statement.order_by(
                DispatchTaskModel.created_at.desc(),
                DispatchTaskModel.id.desc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    def claim_next_queued(
        self,
        *,
        owner_kind: str | None = None,
        worker_id: str,
        claim_token: str,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        active_lane_keys = (
            select(DispatchTaskModel.lane_key)
            .where(
                DispatchTaskModel.lane_key.is_not(None),
                DispatchTaskModel.status.in_(
                    (
                        DispatchTaskStatus.CLAIMED.value,
                        DispatchTaskStatus.WAITING.value,
                    ),
                ),
            )
        )
        lane_policy_rank = case(
            (
                DispatchTaskModel.policy == DispatchPolicy.RESUME_FIRST.value,
                0,
            ),
            (
                DispatchTaskModel.policy.in_(
                    (
                        DispatchPolicy.JUMP_QUEUE.value,
                        DispatchPolicy.LANE_JUMP_QUEUE.value,
                    ),
                ),
                1,
            ),
            else_=2,
        )
        global_policy_rank = case(
            (
                DispatchTaskModel.policy == DispatchPolicy.RESUME_FIRST.value,
                0,
            ),
            (
                DispatchTaskModel.policy == DispatchPolicy.JUMP_QUEUE.value,
                1,
            ),
            else_=2,
        )
        queued_lane_heads = (
            select(
                DispatchTaskModel.id.label("id"),
                DispatchTaskModel.priority.label("priority"),
                DispatchTaskModel.queued_at.label("queued_at"),
                DispatchTaskModel.created_at.label("created_at"),
                global_policy_rank.label("global_policy_rank"),
                func.row_number()
                .over(
                    partition_by=func.coalesce(
                        DispatchTaskModel.lane_key,
                        DispatchTaskModel.id,
                    ),
                    order_by=(
                        DispatchTaskModel.priority.asc(),
                        lane_policy_rank.asc(),
                        DispatchTaskModel.queued_at.asc(),
                        DispatchTaskModel.created_at.asc(),
                        DispatchTaskModel.id.asc(),
                    ),
                )
                .label("lane_position"),
            )
            .where(
                DispatchTaskModel.status == DispatchTaskStatus.QUEUED.value,
                *((
                    DispatchTaskModel.owner_kind == owner_kind,
                ) if owner_kind is not None else ()),
                or_(
                    DispatchTaskModel.lane_key.is_(None),
                    not_(DispatchTaskModel.lane_key.in_(active_lane_keys)),
                ),
            )
            .subquery()
        )
        candidate_id = (
            select(queued_lane_heads.c.id)
            .where(queued_lane_heads.c.lane_position == 1)
            .order_by(
                queued_lane_heads.c.priority.asc(),
                queued_lane_heads.c.global_policy_rank.asc(),
                queued_lane_heads.c.queued_at.asc(),
                queued_lane_heads.c.created_at.asc(),
                queued_lane_heads.c.id.asc(),
            )
            .limit(1)
            .scalar_subquery()
        )

        now = utcnow()
        claimed_id = self.session.scalar(
            update(DispatchTaskModel)
            .where(
                and_(
                    DispatchTaskModel.id == candidate_id,
                    DispatchTaskModel.status == DispatchTaskStatus.QUEUED.value,
                ),
            )
            .values(
                status=DispatchTaskStatus.CLAIMED.value,
                claimed_by=worker_id,
                claim_token=claim_token,
                claimed_at=now,
                heartbeat_at=now,
                lease_expires_at=(
                    now + timedelta(seconds=lease_seconds)
                    if lease_seconds is not None
                    else None
                ),
                updated_at=now,
            )
            .returning(DispatchTaskModel.id),
        )
        if claimed_id is None:
            return None

        self.session.flush()
        model = self.session.get(DispatchTaskModel, claimed_id)
        if model is None:
            return None
        return self._to_entity(model)

    def claim_queued(
        self,
        *,
        task_id: str,
        owner_kind: str | None = None,
        worker_id: str,
        claim_token: str,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        now = utcnow()
        filters = [
            DispatchTaskModel.id == task_id,
            DispatchTaskModel.status == DispatchTaskStatus.QUEUED.value,
        ]
        if owner_kind is not None:
            filters.append(DispatchTaskModel.owner_kind == owner_kind)
        updated = self.session.execute(
            update(DispatchTaskModel)
            .where(and_(*filters))
            .values(
                status=DispatchTaskStatus.CLAIMED.value,
                claimed_by=worker_id,
                claim_token=claim_token,
                claimed_at=now,
                heartbeat_at=now,
                lease_expires_at=(
                    now + timedelta(seconds=lease_seconds)
                    if lease_seconds is not None
                    else None
                ),
                updated_at=now,
            ),
        )
        if updated.rowcount != 1:
            return None

        self.session.flush()
        model = self.session.get(DispatchTaskModel, task_id)
        if model is None:
            return None
        return self._to_entity(model)

    def recover_abandoned(
        self,
        *,
        owner_kind: str | None = None,
        now: datetime | None = None,
    ) -> list[DispatchTask]:
        timestamp = now or utcnow()
        filters = [
            DispatchTaskModel.status == DispatchTaskStatus.CLAIMED.value,
            DispatchTaskModel.lease_expires_at.is_not(None),
            DispatchTaskModel.lease_expires_at < timestamp,
        ]
        if owner_kind is not None:
            filters.append(DispatchTaskModel.owner_kind == owner_kind)
        models = self.session.scalars(
            select(DispatchTaskModel)
            .where(*filters)
            .order_by(
                DispatchTaskModel.lease_expires_at.asc(),
                DispatchTaskModel.id.asc(),
            ),
        ).all()
        return [self._to_entity(model) for model in models]

    @staticmethod
    def _to_entity(model: DispatchTaskModel) -> DispatchTask:
        return DispatchTask(
            id=model.id,
            owner_kind=model.owner_kind,
            owner_id=model.owner_id,
            lane_key=model.lane_key,
            status=DispatchTaskStatus(model.status),
            policy=DispatchPolicy(model.policy),
            priority=model.priority,
            payload_ref=model.payload_ref,
            metadata=(
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            ),
            waiting_reason=model.waiting_reason,
            error=DispatchErrorPayload.from_payload(model.error_payload),
            claimed_by=model.claimed_by,
            claim_token=model.claim_token,
            created_at=model.created_at,
            updated_at=model.updated_at,
            queued_at=model.queued_at,
            claimed_at=model.claimed_at,
            heartbeat_at=model.heartbeat_at,
            lease_expires_at=model.lease_expires_at,
            completed_at=model.completed_at,
        )
