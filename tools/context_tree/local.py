from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextNodeUpsertInput,
    ContextRenderService,
    ContextTreeService,
    RenderContextDeltaInput,
    RenderContextPromptInput,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextActor,
    ContextActorKind,
    ContextEstimate,
    ContextNode,
    ContextNodeSeed,
    ContextNodeState,
    ContextWorkspace,
)
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRunResult

CONTEXT_TREE_LIST_TOOL_ID = "context_tree.list"
CONTEXT_TREE_EXPAND_TOOL_ID = "context_tree.expand"
CONTEXT_TREE_COLLAPSE_TOOL_ID = "context_tree.collapse"
CONTEXT_TREE_PIN_TOOL_ID = "context_tree.pin"
CONTEXT_TREE_UNPIN_TOOL_ID = "context_tree.unpin"
CONTEXT_TREE_ESTIMATE_TOOL_ID = "context_tree.estimate"
CONTEXT_TREE_RENDER_CURRENT_TOOL_ID = "context_tree.render_current"
CONTEXT_TREE_READ_SNAPSHOT_TOOL_ID = "context_tree.read_snapshot"
CONTEXT_TREE_DIFF_SINCE_TOOL_ID = "context_tree.diff_since"
CONTEXT_TREE_UPDATE_PLAN_TOOL_ID = "context_tree.update_plan"
CONTEXT_TREE_ENABLE_TOOL_SCHEMA_TOOL_ID = "context_tree.enable_tool_schema"
CONTEXT_TREE_DISABLE_TOOL_SCHEMA_TOOL_ID = "context_tree.disable_tool_schema"

_SESSION_KEY_ATTR = "session_key"
_AGENT_ID_ATTR = "agent_id"
_RUN_ID_ATTR = "run_id"


@dataclass(frozen=True, slots=True)
class ContextTreeToolDeps:
    context_tree_service: ContextTreeService | None = field(
        default=None,
        metadata={"dependency_id": "context_tree_service"},
    )
    context_render_service: ContextRenderService | None = field(
        default=None,
        metadata={"dependency_id": "context_render_service"},
    )


def _coerce_deps(value: ContextTreeToolDeps | Any) -> ContextTreeToolDeps | None:
    if isinstance(value, ContextTreeToolDeps):
        return value
    context_tree_service = getattr(value, "context_tree_service", None)
    context_render_service = getattr(value, "context_render_service", None)
    if context_tree_service is None or context_render_service is None:
        return None
    return ContextTreeToolDeps(
        context_tree_service=context_tree_service,
        context_render_service=context_render_service,
    )


def context_tree_list(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        view = resolved.context_tree_service.list_tree(session_key)
        nodes = tuple(_node_list_payload(node) for node in _sorted_nodes(view.nodes))
        return ToolRunResult.text(
            _render_tree_list(nodes),
            details={
                "session_key": view.workspace.session_key,
                "workspace_id": view.workspace.id,
                "revision": view.workspace.active_revision,
                "estimate": view.estimate.to_payload(),
                "nodes": nodes,
            },
            metadata={
                "tool": CONTEXT_TREE_LIST_TOOL_ID,
                "session_key": view.workspace.session_key,
                "node_count": len(nodes),
            },
        )

    return handler


def context_tree_estimate(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        estimate = rendered.estimate.to_payload()
        return ToolRunResult.text(
            _render_estimate(estimate),
            details={
                "session_key": rendered.workspace.session_key,
                "workspace_id": rendered.workspace.id,
                "revision": rendered.workspace.active_revision,
                "estimate": estimate,
                "included_node_ids": list(rendered.included_node_ids),
                "mirrored_node_ids": list(rendered.mirrored_node_ids),
                "tool_schema_mirror_available": rendered.tool_schema_mirror_available,
                "provider_attachment_keys": sorted(rendered.provider_attachments),
            },
            metadata={
                "tool": CONTEXT_TREE_ESTIMATE_TOOL_ID,
                "session_key": rendered.workspace.session_key,
                "included_node_count": len(rendered.included_node_ids),
            },
        )

    return handler


def context_tree_render_current(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        max_chars = _bounded_int(arguments.get("max_chars"), default=16000)
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        prompt_body = _truncate_text(rendered.prompt_body, max_chars)
        truncated = len(prompt_body) < len(rendered.prompt_body)
        text = _render_current_prompt_text(
            session_key=rendered.workspace.session_key,
            revision=rendered.workspace.active_revision,
            prompt_body=prompt_body,
            truncated=truncated,
        )
        return ToolRunResult.text(
            text,
            details={
                "session_key": rendered.workspace.session_key,
                "workspace_id": rendered.workspace.id,
                "revision": rendered.workspace.active_revision,
                "estimate": rendered.estimate.to_payload(),
                "included_node_ids": list(rendered.included_node_ids),
                "mirrored_node_ids": list(rendered.mirrored_node_ids),
                "tool_schema_mirror_available": rendered.tool_schema_mirror_available,
                "provider_attachment_keys": sorted(rendered.provider_attachments),
                "prompt_body": rendered.prompt_body,
                "truncated": truncated,
                "max_chars": max_chars,
            },
            metadata={
                "tool": CONTEXT_TREE_RENDER_CURRENT_TOOL_ID,
                "session_key": rendered.workspace.session_key,
                "revision": rendered.workspace.active_revision,
                "included_node_count": len(rendered.included_node_ids),
                "truncated": truncated,
            },
        )

    return handler


def context_tree_read_snapshot(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        snapshot_id = _required_text(arguments.get("snapshot_id"), "snapshot_id")
        max_chars = _bounded_int(arguments.get("max_chars"), default=16000)
        snapshot = resolved.context_render_service.get_snapshot(snapshot_id)
        prompt_body = _truncate_text(snapshot.prompt_body, max_chars)
        truncated = len(prompt_body) < len(snapshot.prompt_body)
        return ToolRunResult.text(
            _render_snapshot_text(
                snapshot_id=snapshot.id,
                session_key=snapshot.session_key,
                revision=snapshot.tree_revision,
                prompt_body=prompt_body,
                truncated=truncated,
            ),
            details=_snapshot_payload(
                snapshot,
                prompt_body=snapshot.prompt_body,
                truncated=truncated,
                max_chars=max_chars,
            ),
            metadata={
                "tool": CONTEXT_TREE_READ_SNAPSHOT_TOOL_ID,
                "session_key": snapshot.session_key,
                "snapshot_id": snapshot.id,
                "revision": snapshot.tree_revision,
                "included_node_count": len(snapshot.included_node_ids),
                "truncated": truncated,
            },
        )

    return handler


def context_tree_diff_since(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        snapshot_id = _optional_text(arguments.get("snapshot_id"))
        since_revision = _optional_int(arguments.get("revision"))
        baseline_revision = since_revision
        baseline_snapshot_payload: dict[str, object] | None = None
        delta = None
        if snapshot_id is not None:
            snapshot = resolved.context_render_service.get_snapshot(snapshot_id)
            baseline_snapshot_payload = _snapshot_payload(
                snapshot,
                prompt_body="",
                truncated=False,
                max_chars=0,
            )
            delta = resolved.context_render_service.render_delta(
                RenderContextDeltaInput(
                    session_key=session_key,
                    baseline_snapshot_id=snapshot_id,
                ),
            )
            baseline_revision = delta.baseline_revision
        else:
            current = resolved.context_render_service.render_prompt_body(
                RenderContextPromptInput(session_key=session_key),
            )
            current_node_ids = tuple(current.included_node_ids)
            baseline_node_ids: tuple[str, ...] = ()
            added = current_node_ids
            removed: tuple[str, ...] = ()
            changed_revision = (
                baseline_revision is None
                or current.workspace.active_revision != baseline_revision
            )
            delta_details = {
                "session_key": current.workspace.session_key,
                "workspace_id": current.workspace.id,
                "current_revision": current.workspace.active_revision,
                "baseline_revision": baseline_revision,
                "changed_revision": changed_revision,
                "current_estimate": current.estimate.to_payload(),
                "current_included_node_ids": list(current_node_ids),
                "baseline_included_node_ids": list(baseline_node_ids),
                "added_node_ids": list(added),
                "removed_node_ids": list(removed),
                "added_tool_schema_names": [],
                "removed_tool_schema_names": [],
                "current_tool_schema_names": [],
                "baseline_tool_schema_names": [],
            }
            current_revision = current.workspace.active_revision
            added_schema_names: tuple[str, ...] = ()
            removed_schema_names: tuple[str, ...] = ()
        if delta is not None:
            current_node_ids = delta.current_included_node_ids
            baseline_node_ids = delta.baseline_included_node_ids
            added = delta.added_node_ids
            removed = delta.removed_node_ids
            changed_revision = delta.changed_revision
            workspace_id = delta.workspace.id
            current_revision = delta.current_revision
            current_estimate = delta.estimate.to_payload()
            current_schema_names = delta.current_tool_schema_names
            baseline_schema_names = delta.baseline_tool_schema_names
            added_schema_names = delta.added_tool_schema_names
            removed_schema_names = delta.removed_tool_schema_names
            delta_details = {
                "session_key": delta.workspace.session_key,
                "workspace_id": workspace_id,
                "current_revision": current_revision,
                "baseline_revision": baseline_revision,
                "changed_revision": changed_revision,
                "current_estimate": current_estimate,
                "current_included_node_ids": list(current_node_ids),
                "baseline_included_node_ids": list(baseline_node_ids),
                "added_node_ids": list(added),
                "removed_node_ids": list(removed),
                "added_tool_schema_names": list(added_schema_names),
                "removed_tool_schema_names": list(removed_schema_names),
                "current_tool_schema_names": list(current_schema_names),
                "baseline_tool_schema_names": list(baseline_schema_names),
                "delta_prompt_body": delta.prompt_body,
            }
        text = _render_diff_text(
            session_key=session_key,
            current_revision=current_revision,
            baseline_revision=baseline_revision,
            snapshot_id=snapshot_id,
            added=added,
            removed=removed,
            added_tool_schema_names=added_schema_names,
            removed_tool_schema_names=removed_schema_names,
            changed_revision=changed_revision,
        )
        return ToolRunResult.text(
            text,
            details={
                **delta_details,
                "baseline_snapshot_id": snapshot_id,
                "baseline_revision": baseline_revision,
                "baseline_snapshot": baseline_snapshot_payload,
                "note": (
                    "Diff compares rendered node membership, tool schema mirror "
                    "membership, and tree revision. "
                    "Use context_tree.render_current when full current prompt text is needed."
                ),
            },
            metadata={
                "tool": CONTEXT_TREE_DIFF_SINCE_TOOL_ID,
                "session_key": session_key,
                "current_revision": current_revision,
                "baseline_revision": baseline_revision,
                "baseline_snapshot_id": snapshot_id,
                "changed_revision": changed_revision,
                "added_node_count": len(added),
                "removed_node_count": len(removed),
                "added_tool_schema_count": len(added_schema_names),
                "removed_tool_schema_count": len(removed_schema_names),
            },
        )

    return handler


def context_tree_update_plan(deps: ContextTreeToolDeps | Any):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        objective = _required_text(arguments.get("objective"), "objective")
        status = _optional_text(arguments.get("status")) or "in_progress"
        current_step = _optional_text(arguments.get("current_step"))
        completed_steps = _text_list(arguments.get("completed_steps"))
        verified_facts = _text_list(arguments.get("verified_facts"))
        assumptions = _text_list(arguments.get("assumptions"))
        blockers = _text_list(arguments.get("blockers"))
        next_steps = _text_list(arguments.get("next_steps"))
        update_reason = _optional_text(arguments.get("update_reason")) or "phase_update"
        plan_payload = _working_plan_payload(
            objective=objective,
            status=status,
            current_step=current_step,
            completed_steps=completed_steps,
            verified_facts=verified_facts,
            assumptions=assumptions,
            blockers=blockers,
            next_steps=next_steps,
            update_reason=update_reason,
        )
        plan_signature = _working_plan_signature(plan_payload)
        phase_payload = _working_plan_phase_payload(
            objective=objective,
            status=status,
            current_step=current_step,
        )
        plan_phase = _working_plan_phase_label(phase_payload)
        phase_signature = _working_plan_signature(phase_payload)
        content = _render_working_plan_content(
            objective=objective,
            status=status,
            current_step=current_step,
            completed_steps=completed_steps,
            verified_facts=verified_facts,
            assumptions=assumptions,
            blockers=blockers,
            next_steps=next_steps,
        )
        summary = _working_plan_summary(
            objective=objective,
            status=status,
            current_step=current_step,
            blockers=blockers,
        )
        tree_view = resolved.context_tree_service.list_tree(session_key)
        existing_plan = _node_by_id(tree_view.nodes, "work.plan")
        existing_objective = (
            _optional_text(existing_plan.metadata.get("objective"))
            if existing_plan is not None
            else None
        )
        existing_status = (
            _optional_text(existing_plan.metadata.get("status"))
            if existing_plan is not None
            else None
        )
        existing_terminal_plan = (
            existing_plan is not None
            and existing_objective == objective
            and existing_status is not None
            and _is_terminal_plan_status(existing_status)
        )
        if existing_terminal_plan and not _is_terminal_plan_status(status):
            return ToolRunResult.text(
                (
                    "Working plan is already complete for this objective; no tree revision "
                    "was created. Produce the final user-facing answer now. Do not reopen "
                    "the same plan unless the objective changed or a concrete blocker was found."
                ),
                details=_working_plan_result_details(
                    workspace=tree_view.workspace,
                    operation_id=None,
                    node=existing_plan,
                    no_op=True,
                    no_op_reason="terminal_plan_locked",
                ),
                metadata={
                    "tool": CONTEXT_TREE_UPDATE_PLAN_TOOL_ID,
                    "session_key": session_key,
                    "node_id": "work.plan",
                    "status": status,
                    "update_reason": update_reason,
                    "no_op": True,
                    "no_op_reason": "terminal_plan_locked",
                    "terminal_plan": True,
                },
            )
        previous_phase_signature = (
            str(existing_plan.metadata.get("plan_phase_signature") or "")
            if existing_plan is not None
            else ""
        )
        previous_update_count = (
            _optional_int(existing_plan.metadata.get("plan_update_count"))
            if existing_plan is not None
            else None
        )
        phase_changed = previous_phase_signature != phase_signature
        if (
            existing_plan is not None
            and existing_plan.metadata.get("plan_signature") == plan_signature
        ):
            return ToolRunResult.text(
                (
                    "Working plan unchanged; no tree revision was created. "
                    "Use context_tree.update_plan only for meaningful phase, "
                    "verification, blocker, or objective changes."
                ),
                details=_working_plan_result_details(
                    workspace=tree_view.workspace,
                    operation_id=None,
                    node=existing_plan,
                    no_op=True,
                    no_op_reason="same_plan",
                ),
                metadata={
                    "tool": CONTEXT_TREE_UPDATE_PLAN_TOOL_ID,
                    "session_key": session_key,
                    "node_id": "work.plan",
                    "status": status,
                    "update_reason": update_reason,
                    "no_op": True,
                    "no_op_reason": "same_plan",
                    "plan_signature": plan_signature,
                    "plan_phase": plan_phase,
                    "plan_phase_signature": phase_signature,
                    "previous_plan_phase_signature": previous_phase_signature,
                    "phase_changed": False,
                },
            )
        if (
            existing_plan is not None
            and not phase_changed
            and _is_redundant_phase_update_reason(update_reason)
        ):
            return ToolRunResult.text(
                (
                    "Working plan phase unchanged; no tree revision was created. "
                    "Use update_reason=verified_fact, blocker, recovery, or "
                    "final_summary when new evidence or state must be recorded "
                    "inside the same phase."
                ),
                details=_working_plan_result_details(
                    workspace=tree_view.workspace,
                    operation_id=None,
                    node=existing_plan,
                    no_op=True,
                    no_op_reason="same_phase",
                ),
                metadata={
                    "tool": CONTEXT_TREE_UPDATE_PLAN_TOOL_ID,
                    "session_key": session_key,
                    "node_id": "work.plan",
                    "status": status,
                    "update_reason": update_reason,
                    "no_op": True,
                    "no_op_reason": "same_phase",
                    "plan_signature": plan_signature,
                    "plan_phase": plan_phase,
                    "plan_phase_signature": phase_signature,
                    "previous_plan_phase_signature": previous_phase_signature,
                    "phase_changed": False,
                },
            )
        plan_update_count = (previous_update_count or 0) + 1
        result = resolved.context_tree_service.upsert_nodes(
            ContextNodeUpsertInput(
                session_key=session_key,
                nodes=(
                    ContextNodeSeed(
                        node_id="work.plan",
                        parent_id="execution.current",
                        owner="context_workspace",
                        kind="working_plan",
                        title="Working Plan",
                        summary=summary,
                        content=content,
                        state=ContextNodeState(
                            collapsed=False,
                            loaded=True,
                            pinned=True,
                        ),
                        actions=(
                            ContextAction.PIN,
                            ContextAction.UNPIN,
                            ContextAction.ESTIMATE,
                        ),
                        owner_ref={
                            "session_key": session_key,
                            "objective": objective,
                            "status": status,
                            "plan_phase": plan_phase,
                            "public_plan": True,
                        },
                        estimate=_text_estimate(f"{summary}\n{content}"),
                        display_order=18,
                        metadata={
                            "tool": CONTEXT_TREE_UPDATE_PLAN_TOOL_ID,
                            "objective": objective,
                            "status": status,
                            "current_step": current_step,
                            "completed_step_count": len(completed_steps),
                            "verified_fact_count": len(verified_facts),
                            "assumption_count": len(assumptions),
                            "blocker_count": len(blockers),
                            "next_step_count": len(next_steps),
                            "update_reason": update_reason,
                            "plan_signature": plan_signature,
                            "plan_phase": plan_phase,
                            "plan_phase_signature": phase_signature,
                            "previous_plan_phase_signature": previous_phase_signature,
                            "phase_changed": phase_changed,
                            "plan_update_count": plan_update_count,
                            "public_plan": True,
                        },
                    ),
                ),
                action=ContextAction.UPSERT,
                actor=_actor_from_context(execution_context),
                parent_node_id="execution.current",
                run_id=_context_str(execution_context, _RUN_ID_ATTR),
                payload={"tool": CONTEXT_TREE_UPDATE_PLAN_TOOL_ID},
            ),
        )
        result_message = (
            "Updated visible working plan at node 'work.plan'. "
            f"Tree revision is now {result.workspace.active_revision}."
        )
        if _is_terminal_plan_status(status):
            result_message += (
                " Plan status is complete; produce the final user-facing answer now. "
                "Do not call more tools unless a required fact is still missing or a blocker was recorded."
            )
        return ToolRunResult.text(
            result_message,
            details=_working_plan_result_details(
                workspace=result.workspace,
                operation_id=result.operation_id,
                node=result.nodes[0],
                no_op=False,
            ),
            metadata={
                "tool": CONTEXT_TREE_UPDATE_PLAN_TOOL_ID,
                "session_key": result.workspace.session_key,
                "node_id": "work.plan",
                "operation_id": result.operation_id,
                "status": status,
                "update_reason": update_reason,
                "no_op": False,
                "plan_signature": plan_signature,
                "plan_phase": plan_phase,
                "plan_phase_signature": phase_signature,
                "previous_plan_phase_signature": previous_phase_signature,
                "phase_changed": phase_changed,
                "plan_update_count": plan_update_count,
                "terminal_plan": _is_terminal_plan_status(status),
            },
        )

    return handler


def context_tree_expand(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_EXPAND_TOOL_ID,
        action=ContextAction.EXPAND,
    )


def context_tree_collapse(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_COLLAPSE_TOOL_ID,
        action=ContextAction.COLLAPSE,
    )


def context_tree_pin(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_PIN_TOOL_ID,
        action=ContextAction.PIN,
    )


def context_tree_unpin(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_UNPIN_TOOL_ID,
        action=ContextAction.UNPIN,
    )


def context_tree_enable_tool_schema(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_ENABLE_TOOL_SCHEMA_TOOL_ID,
        action=ContextAction.ENABLE_TOOL_SCHEMA,
    )


def context_tree_disable_tool_schema(deps: ContextTreeToolDeps | Any):
    return _context_tree_action_tool(
        deps,
        tool_id=CONTEXT_TREE_DISABLE_TOOL_SCHEMA_TOOL_ID,
        action=ContextAction.DISABLE_TOOL_SCHEMA,
    )


def _context_tree_action_tool(
    deps: ContextTreeToolDeps | Any,
    *,
    tool_id: str,
    action: ContextAction,
):
    resolved = _coerce_deps(deps)
    if resolved is None:
        return None

    async def handler(
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        session_key = _resolve_session_key(arguments, execution_context)
        node_id = _required_text(arguments.get("node_id"), "node_id")
        result = resolved.context_tree_service.apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=action,
                actor=_actor_from_context(execution_context),
                run_id=_context_str(execution_context, _RUN_ID_ATTR),
                payload={"tool": tool_id},
            ),
        )
        rendered = resolved.context_render_service.render_prompt_body(
            RenderContextPromptInput(session_key=session_key),
        )
        mirrored_schema_names = _mirrored_tool_schema_names(
            rendered.provider_attachments,
        )
        tree_after = resolved.context_tree_service.list_tree(session_key)
        current_plan = _node_by_id(tree_after.nodes, "work.plan")
        terminal_plan = (
            current_plan is not None
            and _is_terminal_plan_status(
                _optional_text(current_plan.metadata.get("status")) or "",
            )
        )
        child_handles = (
            _child_handles_for_node(
                tree_after.nodes,
                parent_id=node_id,
            )
            if action is ContextAction.EXPAND
            else ()
        )
        return ToolRunResult.text(
            _render_action_result_text(
                action=action,
                node_id=node_id,
                revision=result.workspace.active_revision,
                mirrored_schema_names=mirrored_schema_names,
                child_handles=child_handles,
                terminal_plan=terminal_plan,
            ),
            details={
                "session_key": result.workspace.session_key,
                "workspace_id": result.workspace.id,
                "revision": result.workspace.active_revision,
                "operation_id": result.operation_id,
                "node": _node_payload(result.node),
                "loaded_child_handles": [dict(item) for item in child_handles],
                "included_node_ids": list(rendered.included_node_ids),
                "mirrored_node_ids": list(rendered.mirrored_node_ids),
                "mirrored_tool_schema_names": list(mirrored_schema_names),
                "tool_schema_mirror_available": rendered.tool_schema_mirror_available,
                "estimate": rendered.estimate.to_payload(),
            },
            metadata={
                "tool": tool_id,
                "session_key": result.workspace.session_key,
                "node_id": result.node.id,
                "action": action.value,
                "operation_id": result.operation_id,
                "terminal_plan": terminal_plan,
            },
        )

    return handler


def _render_action_result_text(
    *,
    action: ContextAction,
    node_id: str,
    revision: int,
    mirrored_schema_names: tuple[str, ...],
    child_handles: tuple[dict[str, object], ...] = (),
    terminal_plan: bool = False,
) -> str:
    lines = [
        (
            f"Applied context tree action '{action.value}' to '{node_id}'. "
            f"Tree revision is now {revision}."
        ),
    ]
    if child_handles:
        lines.append("Loaded child handles:")
        for child in child_handles[:12]:
            lines.append(
                "- "
                f"{child['id']} ({child['kind']}, {child['state']}): "
                f"{child['title']}",
            )
        if len(child_handles) > 12:
            lines.append(f"- ... and {len(child_handles) - 12} more child handle(s).")
    if mirrored_schema_names:
        lines.append(
            "Mirrored tool schemas now callable on the next prompt: "
            + ", ".join(mirrored_schema_names)
            + ".",
        )
    if terminal_plan:
        lines.append(
            "Current working plan is complete; use the expanded context only to write "
            "the final user-facing answer now."
        )
    return "\n".join(lines)


def _child_handles_for_node(
    nodes: tuple[ContextNode, ...],
    *,
    parent_id: str,
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "state": _node_state_text(node),
        }
        for node in _sorted_nodes(
            tuple(node for node in nodes if node.parent_id == parent_id),
        )
    )


def _node_state_text(node: ContextNode) -> str:
    if node.state.opened:
        return "opened"
    if node.state.collapsed:
        return "collapsed"
    return "expanded"


def _working_plan_summary(
    *,
    objective: str,
    status: str,
    current_step: str | None,
    blockers: tuple[str, ...],
) -> str:
    parts = [f"{status}: {objective}"]
    if current_step:
        parts.append(f"Current: {current_step}")
    if blockers:
        parts.append(f"Blockers: {len(blockers)}")
    return " ".join(parts)


def _is_terminal_plan_status(status: str) -> bool:
    normalized = status.strip().lower().replace("-", "_")
    return normalized in {
        "done",
        "complete",
        "completed",
        "success",
        "succeeded",
        "final",
    }


def _working_plan_payload(
    *,
    objective: str,
    status: str,
    current_step: str | None,
    completed_steps: tuple[str, ...],
    verified_facts: tuple[str, ...],
    assumptions: tuple[str, ...],
    blockers: tuple[str, ...],
    next_steps: tuple[str, ...],
    update_reason: str,
) -> dict[str, object]:
    return {
        "objective": objective,
        "status": status,
        "current_step": current_step or "",
        "completed_steps": list(completed_steps),
        "verified_facts": list(verified_facts),
        "assumptions": list(assumptions),
        "blockers": list(blockers),
        "next_steps": list(next_steps),
        "update_reason": update_reason,
    }


def _working_plan_phase_payload(
    *,
    objective: str,
    status: str,
    current_step: str | None,
) -> dict[str, object]:
    return {
        "objective": objective,
        "status": status,
        "current_step": current_step or "",
    }


def _working_plan_phase_label(payload: dict[str, object]) -> str:
    status = str(payload.get("status") or "").strip() or "in_progress"
    current_step = str(payload.get("current_step") or "").strip()
    if current_step:
        return f"{status}:{current_step}"
    objective = str(payload.get("objective") or "").strip()
    if objective:
        return f"{status}:{objective}"
    return status


def _is_redundant_phase_update_reason(update_reason: str) -> bool:
    normalized = update_reason.strip().lower()
    return normalized in {
        "phase_update",
        "phase_change",
        "progress",
        "step_update",
        "status_update",
    }


def _working_plan_signature(payload: dict[str, object]) -> str:
    serialized = repr(sorted(payload.items())).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _render_working_plan_content(
    *,
    objective: str,
    status: str,
    current_step: str | None,
    completed_steps: tuple[str, ...],
    verified_facts: tuple[str, ...],
    assumptions: tuple[str, ...],
    blockers: tuple[str, ...],
    next_steps: tuple[str, ...],
) -> str:
    lines = [
        "working_plan:",
        f"  objective: {objective}",
        f"  status: {status}",
    ]
    if current_step:
        lines.append(f"  current_step: {current_step}")
    _append_plan_list(lines, "completed_steps", completed_steps)
    _append_plan_list(lines, "verified_facts", verified_facts)
    _append_plan_list(lines, "assumptions", assumptions)
    _append_plan_list(lines, "blockers", blockers)
    _append_plan_list(lines, "next_steps", next_steps)
    lines.append(
        "  note: This is public working state, not hidden reasoning. Keep it factual and update it as progress changes.",
    )
    return "\n".join(lines)


def _append_plan_list(lines: list[str], label: str, items: tuple[str, ...]) -> None:
    if not items:
        return
    lines.append(f"  {label}:")
    for item in items:
        lines.append(f"    - {item}")


def _text_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if not isinstance(value, (list, tuple)):
        normalized = str(value).strip()
        return (normalized,) if normalized else ()
    items: list[str] = []
    for item in value:
        normalized = str(item).strip()
        if normalized:
            items.append(normalized)
    return tuple(items)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _bounded_int(value: object, *, default: int, minimum: int = 1000, maximum: int = 50000) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        return default
    return max(minimum, min(parsed, maximum))


def _text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def _mirrored_tool_schema_names(provider_attachments: dict[str, object]) -> tuple[str, ...]:
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, (list, tuple)):
        return ()
    names: list[str] = []
    for item in raw_schemas:
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()
        if name:
            names.append(name)
    return tuple(names)


def _resolve_session_key(
    arguments: dict[str, Any],
    execution_context: ToolExecutionContext | None,
) -> str:
    raw = arguments.get("session_key")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    session_key = _context_str(execution_context, _SESSION_KEY_ATTR)
    if session_key is None:
        raise ValueError("context_tree tool requires a session_key.")
    return session_key


def _actor_from_context(
    execution_context: ToolExecutionContext | None,
) -> ContextActor:
    actor_id = _context_str(execution_context, _AGENT_ID_ATTR)
    if actor_id is not None:
        return ContextActor(kind=ContextActorKind.AGENT, actor_id=actor_id)
    return ContextActor(kind=ContextActorKind.SYSTEM)


def _context_str(
    execution_context: ToolExecutionContext | None,
    key: str,
) -> str | None:
    if execution_context is None:
        return None
    return execution_context.get_str(key)


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"context_tree tool requires {field_name}.")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"context_tree tool requires {field_name}.")
    return normalized


def _sorted_nodes(nodes: tuple[ContextNode, ...]) -> tuple[ContextNode, ...]:
    return tuple(sorted(nodes, key=lambda item: (item.display_order, item.id)))


def _node_by_id(nodes: tuple[ContextNode, ...], node_id: str) -> ContextNode | None:
    for node in nodes:
        if node.id == node_id:
            return node
    return None


def _node_payload(node: ContextNode) -> dict[str, object]:
    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
        "summary": node.summary,
        "state": node.state.to_payload(),
        "actions": [action.value for action in node.actions],
        "estimate": node.estimate.to_payload(),
        "display_order": node.display_order,
        "owner_ref": dict(node.owner_ref),
        "metadata": {
            key: value
            for key, value in node.metadata.items()
            if key != "provider_schema"
        },
    }


def _snapshot_payload(
    snapshot: Any,
    *,
    prompt_body: str,
    truncated: bool,
    max_chars: int,
) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "workspace_id": snapshot.workspace_id,
        "session_key": snapshot.session_key,
        "run_id": snapshot.run_id,
        "tree_revision": snapshot.tree_revision,
        "prompt_body": prompt_body,
        "provider_attachment_keys": sorted(snapshot.provider_attachments),
        "estimate": snapshot.estimate.to_payload(),
        "included_node_ids": list(snapshot.included_node_ids),
        "mirrored_node_ids": list(snapshot.mirrored_node_ids),
        "included_refs": [dict(ref) for ref in snapshot.included_refs],
        "collapsed_refs": [dict(ref) for ref in snapshot.collapsed_refs],
        "protocol_required_refs": [
            dict(ref) for ref in snapshot.protocol_required_refs
        ],
        "parent_snapshot_id": getattr(snapshot, "parent_snapshot_id", None),
        "parent_tree_revision": getattr(snapshot, "parent_tree_revision", None),
        "metadata": dict(snapshot.metadata),
        "created_at": snapshot.created_at.isoformat(),
        "truncated": truncated,
        "max_chars": max_chars,
    }


def _working_plan_result_details(
    *,
    workspace: ContextWorkspace,
    operation_id: str | None,
    node: ContextNode,
    no_op: bool,
    no_op_reason: str | None = None,
) -> dict[str, object]:
    details: dict[str, object] = {
        "session_key": workspace.session_key,
        "workspace_id": workspace.id,
        "revision": workspace.active_revision,
        "operation_id": operation_id,
        "no_op": no_op,
        "node": _working_plan_node_payload(node),
    }
    if no_op_reason is not None:
        details["no_op_reason"] = no_op_reason
    return details


def _working_plan_node_payload(node: ContextNode) -> dict[str, object]:
    metadata = node.metadata
    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "kind": node.kind,
        "title": node.title,
        "summary": node.summary,
        "state": {
            "collapsed": node.state.collapsed,
            "loaded": node.state.loaded,
            "pinned": node.state.pinned,
            "prompt_visible": node.state.prompt_visible,
        },
        "metadata": {
            "objective": metadata.get("objective"),
            "status": metadata.get("status"),
            "current_step": metadata.get("current_step"),
            "plan_phase": metadata.get("plan_phase"),
            "phase_changed": metadata.get("phase_changed"),
            "update_reason": metadata.get("update_reason"),
            "plan_update_count": metadata.get("plan_update_count"),
            "completed_step_count": metadata.get("completed_step_count"),
            "verified_fact_count": metadata.get("verified_fact_count"),
            "assumption_count": metadata.get("assumption_count"),
            "blocker_count": metadata.get("blocker_count"),
            "next_step_count": metadata.get("next_step_count"),
        },
    }


def _node_list_payload(node: ContextNode) -> dict[str, object]:
    state = node.state.to_payload()
    return {
        "id": node.id,
        "parent_id": node.parent_id,
        "owner": node.owner,
        "kind": node.kind,
        "title": node.title,
        "summary": _truncate_text(node.summary, 360),
        "state": {
            "collapsed": bool(state.get("collapsed")),
            "loaded": bool(state.get("loaded")),
            "pinned": bool(state.get("pinned")),
            "prompt_visible": bool(state.get("prompt_visible")),
            "schema_enabled": bool(state.get("schema_enabled")),
        },
        "actions": [action.value for action in node.actions],
        "estimate": node.estimate.to_payload(),
        "display_order": node.display_order,
    }


def _render_tree_list(nodes: tuple[dict[str, object], ...]) -> str:
    if not nodes:
        return "Context tree is empty."
    lines = ["Context tree nodes:"]
    for node in nodes:
        state = node.get("state")
        state_payload = state if isinstance(state, dict) else {}
        collapsed = "collapsed" if state_payload.get("collapsed") else "expanded"
        loaded = "loaded" if state_payload.get("loaded") else "unloaded"
        parent_id = node.get("parent_id") or "root"
        lines.append(
            f"- {node['id']} ({node['kind']}, {collapsed}, {loaded}, parent: {parent_id})",
        )
    return "\n".join(lines)


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3]}..."


def _render_estimate(estimate: dict[str, object]) -> str:
    return (
        "Context tree estimate: "
        f"{estimate.get('text_tokens', 0)} text tokens, "
        f"{estimate.get('tool_schema_tokens', 0)} tool schema tokens, "
        f"{estimate.get('provider_attachment_count', 0)} provider attachments."
    )


def _render_current_prompt_text(
    *,
    session_key: str,
    revision: int,
    prompt_body: str,
    truncated: bool,
) -> str:
    header = (
        f"Current context tree render for {session_key} at revision {revision}."
    )
    if truncated:
        header += " Output was truncated by max_chars."
    return f"{header}\n\n{prompt_body}"


def _render_snapshot_text(
    *,
    snapshot_id: str,
    session_key: str,
    revision: int,
    prompt_body: str,
    truncated: bool,
) -> str:
    header = (
        f"Context render snapshot {snapshot_id} for {session_key} "
        f"at tree revision {revision}."
    )
    if truncated:
        header += " Output was truncated by max_chars."
    return f"{header}\n\n{prompt_body}"


def _render_diff_text(
    *,
    session_key: str,
    current_revision: int,
    baseline_revision: int | None,
    snapshot_id: str | None,
    added: tuple[str, ...],
    removed: tuple[str, ...],
    added_tool_schema_names: tuple[str, ...],
    removed_tool_schema_names: tuple[str, ...],
    changed_revision: bool,
) -> str:
    baseline = (
        f"snapshot {snapshot_id} / revision {baseline_revision}"
        if snapshot_id is not None
        else f"revision {baseline_revision}" if baseline_revision is not None else "unknown baseline"
    )
    lines = [
        (
            f"Context tree diff for {session_key}: {baseline} -> "
            f"current revision {current_revision}."
        ),
        f"- revision_changed: {str(changed_revision).lower()}",
        f"- added_rendered_nodes: {len(added)}",
        f"- removed_rendered_nodes: {len(removed)}",
        f"- added_tool_schemas: {len(added_tool_schema_names)}",
        f"- removed_tool_schemas: {len(removed_tool_schema_names)}",
    ]
    if added:
        lines.append("Added rendered node ids:")
        lines.extend(f"- {node_id}" for node_id in added[:20])
        if len(added) > 20:
            lines.append(f"- ... and {len(added) - 20} more")
    if removed:
        lines.append("Removed rendered node ids:")
        lines.extend(f"- {node_id}" for node_id in removed[:20])
        if len(removed) > 20:
            lines.append(f"- ... and {len(removed) - 20} more")
    if added_tool_schema_names:
        lines.append("Added provider tool schemas:")
        lines.extend(f"- {name}" for name in added_tool_schema_names[:20])
        if len(added_tool_schema_names) > 20:
            lines.append(f"- ... and {len(added_tool_schema_names) - 20} more")
    if removed_tool_schema_names:
        lines.append("Removed provider tool schemas:")
        lines.extend(f"- {name}" for name in removed_tool_schema_names[:20])
        if len(removed_tool_schema_names) > 20:
            lines.append(f"- ... and {len(removed_tool_schema_names) - 20} more")
    lines.append(
        "This diff reports rendered node membership, provider tool schema "
        "membership, and revision movement; "
        "call context_tree.render_current for the full current render."
    )
    return "\n".join(lines)
