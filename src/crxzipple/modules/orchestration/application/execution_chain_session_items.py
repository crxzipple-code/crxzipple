from __future__ import annotations

from crxzipple.modules.orchestration.application.execution_chain_common import (
    next_item_index,
)
from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ExecutionChainLifecycleUnitOfWork,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    execution_step_item_id,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
)


def ensure_session_item_execution_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    session_item_id: str,
    item_index: int | None = None,
    summary_payload: dict[str, object] | None = None,
) -> tuple[ExecutionStepItem, bool]:
    normalized_item_id = session_item_id.strip()
    owner = ExecutionOwnerReference(
        owner_kind="session_item",
        owner_id=normalized_item_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id and item.kind is ExecutionStepItemKind.SESSION_MESSAGE:
            return item, False
    resolved_item_index = (
        next_item_index(uow, step.id)
        if item_index is None
        else item_index
    )
    item = ExecutionStepItem.create(
        item_id=execution_step_item_id(
            step_id=step.id,
            item_index=resolved_item_index,
            kind=ExecutionStepItemKind.SESSION_MESSAGE,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=resolved_item_index,
        kind=ExecutionStepItemKind.SESSION_MESSAGE,
        owner=owner,
        correlation_key=normalized_item_id,
    )
    item.payload_ref = {
        "kind": "session_item",
        "session_item_id": normalized_item_id,
    }
    item.complete(
        summary_payload={
            "session_item_id": normalized_item_id,
            **(summary_payload or {}),
        },
    )
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True
