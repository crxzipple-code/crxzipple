from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import ExecutionStepItemKind
from crxzipple.modules.workbench.application.execution_projection import (
    execution_item_summary,
    execution_item_view_status,
    request_render_snapshot_id as execution_request_render_snapshot_id,
    summary_text,
    summary_text_list,
)
from crxzipple.modules.workbench.application.step_view_factory import make_step_view
from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    extract_text_content,
)


def assistant_progress_step_views(
    session_query: Any | None,
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
) -> tuple[Any, ...]:
    views: list[Any] = []
    for index, item in enumerate(bundle.items):
        if item.kind is not ExecutionStepItemKind.SESSION_MESSAGE:
            continue
        summary = execution_item_summary(item)
        request_render_snapshot_id = execution_request_render_snapshot_id(
            run,
            summary=summary,
        )
        if summary_text(summary, "message_kind") != "assistant_progress":
            continue
        progress_text = summary_text(summary, "assistant_progress_text")
        session_item_ids = summary_text_list(summary, "session_item_ids")
        session_item_id = (
            summary_text(summary, "session_item_id")
            or (session_item_ids[0] if session_item_ids else None)
        )
        if progress_text is None:
            progress_text = _session_item_text(
                session_query,
                session_item_id,
            )
        if progress_text is None:
            continue
        views.append(
            make_step_view(
                run=run,
                turn_id=turn_id,
                step_id=f"execution:{bundle.step.id}:progress:{index}",
                step_type="agent_progress",
                status=execution_item_view_status(item),
                title="Agent Progress",
                summary=progress_text,
                markdown=progress_text,
                started_at=bundle.step.started_at or item.created_at,
                completed_at=item.completed_at or bundle.step.completed_at,
                badges=(models.StatusBadgeModel(label="Assistant", tone="info"),),
                llm_invocation_id=summary_text(
                    summary,
                    "llm_invocation_id",
                ),
                request_render_snapshot_id=request_render_snapshot_id,
                session_item_id=session_item_id,
                trace_step_id=bundle.step.id,
                source_owner="session_item",
                source_event_id=session_item_id,
                source_event_name="assistant_progress",
            ),
        )
    return tuple(views)


def _session_item_text(
    session_query: Any | None,
    item_id: str | None,
) -> str | None:
    if session_query is None or not item_id:
        return None
    try:
        item = session_query.get_item(item_id)
    except Exception:
        return None
    content_payload = getattr(item, "content_payload", None)
    text = extract_text_content(content_blocks_from_payload(content_payload))
    if isinstance(text, str) and text.strip():
        return text.strip()
    if isinstance(content_payload, dict):
        raw_text = content_payload.get("text")
        if isinstance(raw_text, str) and raw_text.strip():
            return raw_text.strip()
    return None
