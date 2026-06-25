from __future__ import annotations

from crxzipple.modules.orchestration.application.execution_chain_common import (
    TERMINAL_ITEM_STATUSES,
    TERMINAL_STEP_STATUSES,
    complete_step_if_all_items_terminal,
    is_late_tool_result_target,
    next_item_index,
    next_step_index_after_pending,
    normalized_optional_text,
    optional_text,
)
from crxzipple.modules.orchestration.application.execution_chain_contracts import (
    ExecutionChainLifecycleUnitOfWork,
)
from crxzipple.modules.orchestration.application.execution_chain_ids import (
    execution_step_id,
    execution_step_item_id,
    tool_batch_correlation_key,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    OrchestrationRun,
)


def materialize_tool_batch_execution_step(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    llm_invocation_id: str,
    tool_run_links: tuple[dict[str, object], ...],
) -> ExecutionStep | None:
    normalized_invocation_id = llm_invocation_id.strip()
    if not normalized_invocation_id or not tool_run_links:
        return None
    chain = uow.execution_chains.get_active_for_turn(run.id)
    if chain is None:
        return None
    correlation_key = tool_batch_correlation_key(
        turn_id=run.id,
        llm_invocation_id=normalized_invocation_id,
    )
    step = uow.execution_steps.get_by_correlation_key(correlation_key)
    if step is None:
        step_index = next_step_index_after_pending(uow, chain)
        step = ExecutionStep.create(
            step_id=execution_step_id(
                turn_id=run.id,
                step_index=step_index,
                kind=ExecutionStepKind.TOOL_BATCH,
            ),
            chain_id=chain.id,
            turn_id=run.id,
            step_index=step_index,
            kind=ExecutionStepKind.TOOL_BATCH,
            correlation_key=correlation_key,
        )
        step.link_owner(
            ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=normalized_invocation_id,
            ),
        )
        chain.increment_step_count()
        uow.execution_steps.add(step)

    has_waiting_runs = False
    item_index_cursor = next_item_index(uow, step.id)
    for link in tool_run_links:
        normalized = _normalize_tool_run_link(link)
        if normalized is None:
            continue
        _, created = _ensure_tool_call_item(
            uow,
            step=step,
            link=normalized,
            item_index=item_index_cursor,
        )
        if created:
            item_index_cursor += 1
        tool_run_item, created = _ensure_tool_run_item(
            uow,
            step=step,
            link=normalized,
            item_index=item_index_cursor,
        )
        if created:
            item_index_cursor += 1
        _, created = _ensure_tool_result_item(
            uow,
            step=step,
            link=normalized,
            item_index=item_index_cursor,
        )
        if created:
            item_index_cursor += 1
        has_waiting_runs = has_waiting_runs or (
            tool_run_item.status is ExecutionStepItemStatus.WAITING
        )

    if has_waiting_runs:
        step.wait()
        chain.wait(active_step_id=step.id)
    elif step.status not in TERMINAL_STEP_STATUSES:
        step.complete()
        chain.set_active_step(step.id)
    uow.execution_steps.add(step)
    uow.execution_chains.add(chain)
    uow.collect(step)
    uow.collect(chain)
    return step


def materialize_tool_result_session_item_items(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    run: OrchestrationRun,
    tool_result_item_links: tuple[tuple[str, str], ...],
) -> tuple[ExecutionStepItem, ...]:
    created_or_existing: list[ExecutionStepItem] = []
    for tool_run_id, session_item_id in tool_result_item_links:
        normalized_tool_run_id = tool_run_id.strip()
        normalized_session_item_id = session_item_id.strip()
        if not normalized_tool_run_id or not normalized_session_item_id:
            continue
        tool_run_items = uow.execution_step_items.find_by_owner_reference(
            ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id=normalized_tool_run_id,
            ),
        )
        tool_run_item = next(
            (
                item
                for item in reversed(tool_run_items)
                if item.turn_id == run.id
            ),
            None,
        )
        if tool_run_item is None:
            continue
        step = uow.execution_steps.get(tool_run_item.step_id)
        if step is None:
            continue
        summary = (
            dict(tool_run_item.summary_payload)
            if isinstance(tool_run_item.summary_payload, dict)
            else {}
        )
        link = {
            **summary,
            "tool_run_id": normalized_tool_run_id,
            "result_session_item_id": normalized_session_item_id,
        }
        if _normalize_tool_run_link(link) is None:
            continue
        item, _ = _ensure_tool_result_item(
            uow,
            step=step,
            link=link,
            item_index=next_item_index(uow, step.id),
        )
        if item is not None:
            created_or_existing.append(item)
    return tuple(created_or_existing)


def mark_tool_run_step_item_terminal(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    tool_run_id: str,
    status: str,
    summary_payload: dict[str, object] | None = None,
    error_message: str | None = None,
) -> ExecutionStepItem | None:
    normalized_tool_run_id = tool_run_id.strip()
    if not normalized_tool_run_id:
        return None
    owner = ExecutionOwnerReference(
        owner_kind="tool_run",
        owner_id=normalized_tool_run_id,
    )
    items = uow.execution_step_items.find_by_owner_reference(owner)
    if not items:
        return None
    item = items[-1]
    if item.status not in TERMINAL_ITEM_STATUSES:
        normalized_status = status.strip().lower()
        payload = {
            **(item.summary_payload or {}),
            "tool_run_id": normalized_tool_run_id,
            "status": normalized_status,
            **(summary_payload or {}),
        }
        step = uow.execution_steps.get(item.step_id)
        chain = uow.execution_chains.get(item.chain_id)
        if is_late_tool_result_target(step=step, chain=chain):
            item.summary_payload = payload
            item.mark_late_observed()
            uow.execution_step_items.add(item)
            uow.collect(item)
            return item
        if normalized_status == "succeeded":
            item.complete(summary_payload=payload)
        else:
            item.fail(
                message=(
                    error_message.strip()
                    if error_message is not None and error_message.strip()
                    else f"Tool run ended with status '{normalized_status}'."
                ),
                code=f"tool_run_{normalized_status or 'terminal'}",
                details=payload,
            )
            item.summary_payload = payload
        uow.execution_step_items.add(item)
        uow.collect(item)
    complete_step_if_all_items_terminal(uow, step_id=item.step_id)
    return item


def _ensure_tool_call_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    link: dict[str, object],
    item_index: int,
) -> tuple[ExecutionStepItem, bool]:
    tool_call_id = str(link["tool_call_id"])
    owner = ExecutionOwnerReference(owner_kind="tool_call", owner_id=tool_call_id)
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id:
            return item, False
    item = ExecutionStepItem.create(
        item_id=execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.TOOL_CALL,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.TOOL_CALL,
        owner=owner,
        correlation_key=tool_call_id,
    )
    item.complete(summary_payload=_tool_call_summary(link))
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


def _ensure_tool_run_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    link: dict[str, object],
    item_index: int,
) -> tuple[ExecutionStepItem, bool]:
    tool_run_id = str(link["tool_run_id"])
    owner = ExecutionOwnerReference(owner_kind="tool_run", owner_id=tool_run_id)
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id:
            return item, False
    item = ExecutionStepItem.create(
        item_id=execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.TOOL_RUN,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.TOOL_RUN,
        owner=owner,
        correlation_key=str(link["tool_call_id"]),
    )
    if bool(link.get("background")):
        item.wait()
    else:
        item.complete(summary_payload=_tool_run_summary(link))
    if item.status is ExecutionStepItemStatus.WAITING:
        item.summary_payload = _tool_run_summary(link)
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


def _ensure_tool_result_item(
    uow: ExecutionChainLifecycleUnitOfWork,
    *,
    step: ExecutionStep,
    link: dict[str, object],
    item_index: int,
) -> tuple[ExecutionStepItem | None, bool]:
    result_session_item_id = normalized_optional_text(
        optional_text(link.get("result_session_item_id")),
    )
    if result_session_item_id is None:
        return None, False
    owner = ExecutionOwnerReference(
        owner_kind="session_item",
        owner_id=result_session_item_id,
    )
    existing = uow.execution_step_items.find_by_owner_reference(owner)
    for item in existing:
        if item.step_id == step.id and item.kind is ExecutionStepItemKind.TOOL_RESULT:
            return item, False
    item = ExecutionStepItem.create(
        item_id=execution_step_item_id(
            step_id=step.id,
            item_index=item_index,
            kind=ExecutionStepItemKind.TOOL_RESULT,
        ),
        step_id=step.id,
        chain_id=step.chain_id,
        turn_id=step.turn_id,
        item_index=item_index,
        kind=ExecutionStepItemKind.TOOL_RESULT,
        owner=owner,
        correlation_key=str(link["tool_call_id"]),
    )
    item.payload_ref = {
        "kind": "session_item",
        "tool_run_id": str(link["tool_run_id"]),
        "session_item_id": result_session_item_id,
    }
    item.complete(
        summary_payload=_tool_result_summary(
            link,
            result_session_item_id=result_session_item_id,
        ),
    )
    uow.execution_step_items.add(item)
    uow.collect(item)
    return item, True


def _normalize_tool_run_link(
    link: dict[str, object],
) -> dict[str, object] | None:
    tool_call_id = normalized_optional_text(optional_text(link.get("tool_call_id")))
    tool_run_id = normalized_optional_text(optional_text(link.get("tool_run_id")))
    tool_name = normalized_optional_text(optional_text(link.get("tool_name")))
    if tool_call_id is None or tool_run_id is None or tool_name is None:
        return None
    normalized = dict(link)
    normalized["tool_call_id"] = tool_call_id
    normalized["tool_run_id"] = tool_run_id
    normalized["tool_name"] = tool_name
    return normalized


def _tool_call_summary(link: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "tool_call_id": link.get("tool_call_id"),
            "tool_name": link.get("tool_name"),
            "tool_id": link.get("tool_id"),
            "call_session_item_id": link.get("call_session_item_id"),
            "mode": link.get("mode"),
            "strategy": link.get("strategy"),
            "environment": link.get("environment"),
        }.items()
        if value is not None
    }


def _tool_run_summary(link: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "tool_run_id": link.get("tool_run_id"),
            "tool_call_id": link.get("tool_call_id"),
            "tool_name": link.get("tool_name"),
            "tool_id": link.get("tool_id"),
            "status": link.get("status"),
            "result_session_item_id": link.get("result_session_item_id"),
            "background": bool(link.get("background")),
            "mode": link.get("mode"),
            "strategy": link.get("strategy"),
            "environment": link.get("environment"),
            "tool_execution_plan": _tool_execution_plan_summary(link),
            "tool_lifecycle": _tool_lifecycle_summary(link),
        }.items()
        if value is not None
    }


def _tool_result_summary(
    link: dict[str, object],
    *,
    result_session_item_id: str | None,
) -> dict[str, object]:
    return {
        key: value
        for key, value in {
            "tool_run_id": link.get("tool_run_id"),
            "tool_call_id": link.get("tool_call_id"),
            "tool_name": link.get("tool_name"),
            "tool_id": link.get("tool_id"),
            "result_session_item_id": result_session_item_id,
            "tool_execution_plan": _tool_execution_plan_summary(link),
            "tool_lifecycle": _tool_lifecycle_summary(link),
        }.items()
        if value is not None
    }


def _tool_execution_plan_summary(link: dict[str, object]) -> dict[str, object] | None:
    raw = link.get("tool_execution_plan")
    if not isinstance(raw, dict):
        return None
    payload = {
        key: raw[key]
        for key in (
            "tool_call_id",
            "tool_name",
            "tool_id",
            "mode",
            "strategy",
            "environment",
            "resource_policy",
            "arguments_digest",
        )
        if key in raw
    }
    return payload or None


def _tool_lifecycle_summary(link: dict[str, object]) -> dict[str, object] | None:
    raw = link.get("tool_lifecycle")
    if not isinstance(raw, dict):
        return None
    payload = {
        key: raw[key]
        for key in (
            "superseded",
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
            "supersedes_tool_call_id",
            "supersedes_tool_run_id",
            "supersedes_result_session_item_id",
            "lifecycle_status",
            "evidence_lifecycle_status",
            "evidence_lifecycle",
        )
        if key in raw
    }
    return payload or None
