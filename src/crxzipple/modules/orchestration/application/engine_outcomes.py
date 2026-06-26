from __future__ import annotations

from typing import Any, Callable

from crxzipple.modules.llm.application import (
    build_provider_continuation_state_from_invocation,
)
from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine_models import (
    AdvanceContext,
    EngineAdvanceOutcome,
)
from crxzipple.modules.orchestration.application.engine_runtime_helpers import (
    continuation_end_turn,
    continuation_reason,
    llm_request_metadata,
    llm_response_item_ids,
    optional_text,
    terminal_loop_diagnostic,
)
from crxzipple.modules.orchestration.application.engine_tool_executor import (
    ToolExecutionBatchOutcome,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.tool.domain import ToolRun


def build_tool_execution_advance_outcome(
    *,
    context: AdvanceContext,
    invocation: Any,
    session_item_ids: tuple[str, ...],
    assistant_progress_item_ids: tuple[str, ...],
    tool_call_session_item_ids: tuple[str, ...],
    tool_result_session_item_ids: tuple[str, ...],
    tool_call_names: tuple[str, ...],
    execution_outcome: ToolExecutionBatchOutcome,
) -> EngineAdvanceOutcome:
    return build_engine_advance_outcome(
        context=context,
        invocation=invocation,
        session_item_ids=session_item_ids,
        assistant_progress_item_ids=assistant_progress_item_ids,
        tool_call_session_item_ids=tool_call_session_item_ids,
        tool_result_session_item_ids=tool_result_session_item_ids,
        completed_inline_tool_run_ids=tuple(
            tool_run.id for tool_run in execution_outcome.inline_runs
        ),
        tool_call_names=tool_call_names,
        tool_run_links=tuple(
            dict(link.to_payload()) for link in execution_outcome.tool_run_links
        ),
        pending_tool_run_ids=tuple(
            tool_run.id for _, tool_run in execution_outcome.background_runs
        ),
        pending_approval_request=execution_outcome.pending_approval_request,
        yield_requested=execution_outcome.yield_requested,
        yield_reason=execution_outcome.yield_reason,
        continue_loop=(
            context.draft.surface_policy.auto_continue_inline_tools
            and execution_outcome.pending_approval_request is None
            and not execution_outcome.background_runs
            and not execution_outcome.yield_requested
        ),
    )


def build_engine_advance_outcome(
    *,
    context: AdvanceContext,
    invocation: Any,
    session_item_ids: tuple[str, ...] = (),
    assistant_progress_item_ids: tuple[str, ...] | list[str] = (),
    tool_call_session_item_ids: tuple[str, ...] | list[str] = (),
    tool_result_session_item_ids: tuple[str, ...] | list[str] = (),
    completed_inline_tool_run_ids: tuple[str, ...] = (),
    tool_call_names: tuple[str, ...] = (),
    tool_run_links: tuple[dict[str, object], ...] = (),
    pending_tool_run_ids: tuple[str, ...] = (),
    pending_approval_request: PendingApprovalRequest | None = None,
    yield_requested: bool = False,
    yield_reason: str | None = None,
    continue_loop: bool = False,
) -> EngineAdvanceOutcome:
    assert invocation.result is not None
    return EngineAdvanceOutcome(
        llm_id=context.draft.llm_id,
        llm_invocation_id=invocation.id,
        llm_response_item_ids=llm_response_item_ids(invocation),
        response_text=invocation.result.text,
        user_session_item_id=context.user_session_item_id,
        session_item_ids=tuple(session_item_ids),
        assistant_progress_item_ids=tuple(assistant_progress_item_ids),
        tool_call_session_item_ids=tuple(tool_call_session_item_ids),
        tool_result_session_item_ids=tuple(tool_result_session_item_ids),
        completed_inline_tool_run_ids=completed_inline_tool_run_ids,
        tool_call_names=tool_call_names,
        tool_run_links=tool_run_links,
        pending_tool_run_ids=pending_tool_run_ids,
        pending_approval_request=pending_approval_request,
        runtime_request_report=context.draft.report,
        request_render_snapshot_id=context.request_render_snapshot_id,
        llm_request_metadata=llm_request_metadata(context),
        yield_requested=yield_requested,
        yield_reason=yield_reason,
        continue_loop=continue_loop,
        continuation_reason=continuation_reason(invocation),
        continuation_end_turn=continuation_end_turn(invocation),
        provider_continuation_state=build_provider_continuation_state_from_invocation(
            invocation,
        ),
        loop_diagnostic=terminal_loop_diagnostic(invocation),
    )


def tool_execution_context_attrs(context: AdvanceContext) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for key in (
        "tool_surface_id",
        "tool_surface_snapshot_id",
        "request_render_snapshot_id",
    ):
        value = context.request_envelope.metadata.get(key)
        if isinstance(value, str) and value.strip():
            attrs[key] = value.strip()
    tool_surface_functions = [
        {
            "tool_id": function.tool_id,
            "name": function.name,
            "source_id": function.source_id,
            "group_key": function.group_key,
        }
        for function in context.request_envelope.tool_surface.functions
    ]
    if tool_surface_functions:
        attrs["tool_surface_functions"] = tool_surface_functions
    return attrs


def tool_call_intent_for_background_run(
    *,
    run: OrchestrationRun,
    tool_run: ToolRun,
    background_tool_result_reference: Callable[..., dict[str, str]],
) -> ToolCallIntent:
    if isinstance(tool_run.metadata, dict):
        tool_call_id = optional_text(tool_run.metadata.get("tool_call_id"))
        tool_name = optional_text(tool_run.metadata.get("tool_name"))
        if tool_call_id is not None and tool_name is not None:
            return ToolCallIntent(id=tool_call_id, name=tool_name, arguments={})
    try:
        reference = background_tool_result_reference(run=run, tool_run=tool_run)
    except OrchestrationValidationError:
        return ToolCallIntent(
            id=tool_run.call_id or tool_run.id,
            name=tool_run.tool_id,
            arguments={},
        )
    tool_call_id = optional_text(reference.get("tool_call_id"))
    tool_name = optional_text(reference.get("tool_name"))
    if tool_call_id is None or tool_name is None:
        return ToolCallIntent(
            id=tool_run.call_id or tool_run.id,
            name=tool_run.tool_id,
            arguments={},
        )
    return ToolCallIntent(id=tool_call_id, name=tool_name, arguments={})
