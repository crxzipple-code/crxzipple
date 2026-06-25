from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.llm.application.session_runtime_transcript import (
    RuntimeTranscript,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RuntimeRequestReport,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
)
from crxzipple.modules.session.domain import SessionItem, SessionItemKind


class ExecutionContinuationQueryPort(Protocol):
    def list_execution_chains(self, turn_id: str) -> list[object]:
        ...

    def list_execution_steps(self, chain_id: str) -> list[object]:
        ...

    def list_execution_step_items(self, step_id: str) -> list[object]:
        ...


@dataclass(frozen=True, slots=True)
class RuntimeRequestReportBuilder:
    context_block_max_tokens: int = 30_000
    context_block_context_window_ratio: float = 0.15

    def resolve_context_block_budget(
        self,
        context_window_tokens: int | None,
    ) -> tuple[int, str]:
        if context_window_tokens is None or context_window_tokens <= 0:
            return self.context_block_max_tokens, "fixed"
        dynamic_budget = max(
            256,
            int(context_window_tokens * self.context_block_context_window_ratio),
        )
        effective_budget = min(
            self.context_block_max_tokens,
            dynamic_budget,
            context_window_tokens,
        )
        budget_source = (
            "context_window_scaled"
            if effective_budget < self.context_block_max_tokens
            else "fixed"
        )
        return effective_budget, budget_source

    def build(
        self,
        *,
        mode: RuntimeRequestMode,
        transcript: RuntimeTranscript,
        session_items: tuple[SessionItem, ...],
        context_budget_source: str,
        context_budget_chars: int,
        context_budget_estimated_tokens: int,
        llm_context_window_tokens: int | None,
        execution_query: ExecutionContinuationQueryPort | None,
        turn_id: str,
    ) -> RuntimeRequestReport:
        base_transcript_budget = transcript_budget_with_lightweight_item_refs(
            dict(transcript.report.budget),
            session_items=session_items,
            mode=mode,
        )
        transcript_budget = transcript_budget_with_execution_chain_refs(
            base_transcript_budget,
            execution_query=execution_query,
            turn_id=turn_id,
        )
        return RuntimeRequestReport(
            mode=mode,
            context_budget_source=context_budget_source,
            context_budget_chars=context_budget_chars,
            context_budget_estimated_tokens=context_budget_estimated_tokens,
            llm_context_window_tokens=llm_context_window_tokens,
            context_chars=0,
            context_estimated_tokens=0,
            transcript_message_count=transcript.report.message_count,
            transcript_chars=transcript.report.chars,
            transcript_estimated_tokens=transcript.report.estimated_tokens,
            transcript_tool_result_stats=dict(transcript.report.tool_result_stats),
            transcript_budget=transcript_budget,
        )


def transcript_budget_with_lightweight_item_refs(
    budget: dict[str, object],
    *,
    session_items: tuple[SessionItem, ...],
    mode: RuntimeRequestMode,
) -> dict[str, object]:
    if mode not in {RuntimeRequestMode.NORMAL_TURN, RuntimeRequestMode.SESSION_START}:
        return budget
    refs = _session_item_required_refs(session_items)
    if not refs:
        return budget
    existing_refs = tuple(
        dict(ref)
        for ref in budget.get("protocol_required_refs", ())
        if isinstance(ref, dict)
    )
    merged = dict(budget)
    merged["protocol_required_refs"] = [
        dict(ref) for ref in dedupe_protocol_required_refs((*existing_refs, *refs))
    ]
    return merged


def transcript_budget_with_execution_chain_refs(
    budget: dict[str, object],
    *,
    execution_query: ExecutionContinuationQueryPort | None,
    turn_id: str,
) -> dict[str, object]:
    execution_refs = execution_chain_protocol_required_refs(
        execution_query,
        turn_id,
    )
    if not execution_refs:
        return budget
    merged = dict(budget)
    existing_refs = tuple(
        dict(ref)
        for ref in merged.get("protocol_required_refs", ())
        if isinstance(ref, dict)
    )
    merged_refs = dedupe_protocol_required_refs(
        (*existing_refs, *execution_refs),
    )
    merged["protocol_required_refs"] = [dict(ref) for ref in merged_refs]
    merged["execution_chain_protocol_required_refs"] = [
        dict(ref) for ref in execution_refs
    ]
    merged["execution_chain_protocol_required_ref_count"] = len(execution_refs)
    if "protocol_required_preserved" not in merged:
        merged["protocol_required_preserved"] = True
    return {
        key: value
        for key, value in merged.items()
        if value not in (None, [], {})
    }


def execution_chain_protocol_required_refs(
    execution_query: ExecutionContinuationQueryPort | None,
    turn_id: str,
) -> tuple[dict[str, object], ...]:
    if execution_query is None:
        return ()
    refs: list[dict[str, object]] = []
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = getattr(chain, "id", None)
        if not isinstance(chain_id, str) or not chain_id.strip():
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = getattr(step, "id", None)
            if not isinstance(step_id, str) or not step_id.strip():
                continue
            for item in execution_query.list_execution_step_items(step_id):
                refs.extend(_execution_step_item_protocol_required_refs(item))
    return dedupe_protocol_required_refs(tuple(refs))


def dedupe_protocol_required_refs(
    refs: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, object, object, object]] = set()
    for ref in refs:
        identity = (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("tool_call_id"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(dict(ref))
    return tuple(deduped)


def execution_step_item_summaries(
    execution_query: ExecutionContinuationQueryPort,
    turn_id: str,
) -> tuple[dict[str, object], ...]:
    summaries: list[dict[str, object]] = []
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = getattr(chain, "id", None)
        if not isinstance(chain_id, str) or not chain_id.strip():
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = getattr(step, "id", None)
            if not isinstance(step_id, str) or not step_id.strip():
                continue
            for item in execution_query.list_execution_step_items(step_id):
                summary = getattr(item, "summary_payload", None)
                if isinstance(summary, dict):
                    summaries.append(summary)
    return tuple(summaries)


def _session_item_required_refs(
    session_items: tuple[SessionItem, ...],
) -> tuple[dict[str, object], ...]:
    refs: list[dict[str, object]] = []
    for item in session_items:
        if item.role != "user" or item.kind is not SessionItemKind.USER_MESSAGE:
            continue
        if item.source_module != "orchestration" or item.source_kind != "orchestration_run":
            continue
        ref: dict[str, object] = {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": item.id,
            "item_id": item.id,
            "session_id": item.session_id,
            "sequence_no": item.sequence_no,
            "role": item.role,
            "kind": item.kind.value,
            "render_mode": "full",
            "render_scope": "provider_replay",
            "budget_class": "current_inbound",
        }
        for key, value in {
            "source_module": item.source_module,
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "provider_item_id": item.provider_item_id,
            "tool_call_id": item.call_id,
            "tool_name": item.tool_name,
        }.items():
            text = _optional_text(value)
            if text is not None:
                ref[key] = text
        refs.append(ref)
    return tuple(refs)


def _execution_step_item_protocol_required_refs(
    item: object,
) -> tuple[dict[str, object], ...]:
    refs = [
        _assistant_progress_protocol_required_ref(item, item_id)
        for item_id in _assistant_progress_item_ids(item)
    ]
    tool_ref = _execution_step_item_tool_protocol_required_ref(item)
    if tool_ref is not None:
        refs.append(tool_ref)
    return tuple(ref for ref in refs if ref)


def _execution_step_item_tool_protocol_required_ref(
    item: object,
) -> dict[str, object] | None:
    kind = getattr(item, "kind", None)
    if kind not in {
        ExecutionStepItemKind.TOOL_CALL,
        ExecutionStepItemKind.TOOL_RESULT,
    }:
        return None
    summary = getattr(item, "summary_payload", None)
    if not isinstance(summary, dict):
        return None
    tool_call_id = _optional_text(summary.get("tool_call_id"))
    if tool_call_id is None:
        return None
    session_item_id = _protocol_session_item_id_for_execution_item(
        kind=kind,
        summary=summary,
    )
    if session_item_id is None:
        return None
    status = getattr(item, "status", None)
    owner = getattr(item, "owner", None)
    owner_kind = getattr(owner, "owner_kind", None)
    owner_id = getattr(owner, "owner_id", None)
    ref: dict[str, object] = {
        "owner_module": "session",
        "owner_kind": "session_item",
        "owner_id": session_item_id,
        "item_id": session_item_id,
        "session_item_id": session_item_id,
        "execution_step_item_id": getattr(item, "id", ""),
        "execution_step_id": getattr(item, "step_id", ""),
        "execution_chain_id": getattr(item, "chain_id", ""),
        "turn_id": getattr(item, "turn_id", ""),
        "kind": kind.value if isinstance(kind, ExecutionStepItemKind) else str(kind),
        "role": _tool_protocol_role_for_kind(kind),
        "tool_call_id": tool_call_id,
        "protocol_required": True,
        "budget_class": "protocol_required",
        "render_mode": "full",
        "render_scope": "provider_replay",
    }
    if isinstance(status, ExecutionStepItemStatus):
        ref["status"] = status.value
    elif isinstance(status, str) and status.strip():
        ref["status"] = status.strip()
    if isinstance(owner_kind, str) and owner_kind.strip():
        ref["source_owner_kind"] = owner_kind.strip()
    if isinstance(owner_id, str) and owner_id.strip():
        ref["source_owner_id"] = owner_id.strip()
    for key in (
        "tool_name",
        "tool_id",
        "tool_run_id",
        "call_session_item_id",
        "result_session_item_id",
    ):
        value = _optional_text(summary.get(key))
        if value is not None:
            ref[key] = value
    tool_execution_plan = summary.get("tool_execution_plan")
    if isinstance(tool_execution_plan, dict):
        ref["tool_execution_plan"] = dict(tool_execution_plan)
    tool_lifecycle = summary.get("tool_lifecycle")
    if isinstance(tool_lifecycle, dict):
        ref["tool_lifecycle"] = dict(tool_lifecycle)
    return {
        key: value
        for key, value in ref.items()
        if value not in (None, "", {}, [])
    }


def _protocol_session_item_id_for_execution_item(
    *,
    kind: object,
    summary: dict[str, object],
) -> str | None:
    if kind is ExecutionStepItemKind.TOOL_CALL:
        return _optional_text(summary.get("call_session_item_id"))
    if kind is ExecutionStepItemKind.TOOL_RESULT:
        return _optional_text(summary.get("result_session_item_id"))
    return None


def _tool_protocol_role_for_kind(kind: object) -> str:
    if kind is ExecutionStepItemKind.TOOL_RESULT:
        return "tool"
    return "assistant"


def _assistant_progress_item_ids(item: object) -> tuple[str, ...]:
    summary = getattr(item, "summary_payload", None)
    if not isinstance(summary, dict):
        return ()
    raw_ids = summary.get("assistant_progress_item_ids")
    if not isinstance(raw_ids, (list, tuple)):
        return ()
    item_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        item_id = _optional_text(raw_id)
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        item_ids.append(item_id)
    return tuple(item_ids)


def _assistant_progress_protocol_required_ref(
    item: object,
    item_id: str,
) -> dict[str, object]:
    status = getattr(item, "status", None)
    ref: dict[str, object] = {
        "owner_module": "session",
        "owner_kind": "session_item",
        "owner_id": item_id,
        "item_id": item_id,
        "session_item_id": item_id,
        "execution_step_item_id": getattr(item, "id", ""),
        "execution_step_id": getattr(item, "step_id", ""),
        "execution_chain_id": getattr(item, "chain_id", ""),
        "turn_id": getattr(item, "turn_id", ""),
        "kind": "agent_progress",
        "role": "assistant",
        "protocol_required": True,
        "budget_class": "protocol_required",
        "render_mode": "full",
        "render_scope": "provider_replay",
    }
    if isinstance(status, ExecutionStepItemStatus):
        ref["status"] = status.value
    elif isinstance(status, str) and status.strip():
        ref["status"] = status.strip()
    return {
        key: value
        for key, value in ref.items()
        if value not in (None, "", {}, [])
    }


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
