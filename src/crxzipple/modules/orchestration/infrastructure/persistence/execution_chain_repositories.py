from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crxzipple.modules.orchestration.domain.entities import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionOwnerReference,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    OrchestrationErrorPayload,
)
from crxzipple.modules.orchestration.infrastructure.persistence.models import (
    OrchestrationExecutionChainModel,
    OrchestrationExecutionStepItemModel,
    OrchestrationExecutionStepModel,
)
from crxzipple.shared.time import (
    coerce_optional_utc_datetime,
    coerce_utc_datetime,
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

    def list_for_steps(
        self,
        step_ids: tuple[str, ...],
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        normalized_step_ids = tuple(step_id for step_id in step_ids if step_id.strip())
        if not normalized_step_ids:
            return []
        statement = select(OrchestrationExecutionStepItemModel).where(
            OrchestrationExecutionStepItemModel.step_id.in_(normalized_step_ids),
        )
        if status is not None:
            statement = statement.where(
                OrchestrationExecutionStepItemModel.status == status.value,
            )
        models = list(
            self.session.scalars(
                statement.order_by(
                    OrchestrationExecutionStepItemModel.step_id.asc(),
                    OrchestrationExecutionStepItemModel.item_index.asc(),
                    OrchestrationExecutionStepItemModel.id.asc(),
                ),
            ).all(),
        )
        known_ids = {model.id for model in models}
        requested_step_ids = set(normalized_step_ids)
        for model in self._pending_models.values():
            if model.id in known_ids or model.step_id not in requested_step_ids:
                continue
            if status is not None and model.status != status.value:
                continue
            models.append(model)
        models.sort(key=lambda model: (model.step_id, model.item_index, model.id))
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
