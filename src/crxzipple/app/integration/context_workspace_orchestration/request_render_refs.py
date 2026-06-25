from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)


def snapshot_ref_tuple(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(dict(ref) for ref in value if isinstance(ref, dict))


def metadata_string_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple | set | frozenset):
        return ()
    values: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
    return tuple(values)


def request_session_item_max_chars(draft: RuntimeLlmRequestDraft) -> int | None:
    mode = getattr(getattr(draft, "mode", None), "value", None)
    if mode not in {"memory_flush", "compaction"}:
        return None
    report = getattr(draft, "report", None)
    if report is None:
        return None
    budget = getattr(report, "transcript_budget", None)
    if not isinstance(budget, dict):
        return None
    value = budget.get("max_chars")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def request_input_refs(
    draft_input_session_item_refs: list[dict[str, object]],
    protocol_required_refs: tuple[dict[str, object], ...],
    *,
    run_id: str,
) -> tuple[dict[str, object], ...]:
    refs: list[dict[str, object]] = [dict(ref) for ref in draft_input_session_item_refs]
    seen = {
        (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("item_id"),
        )
        for ref in refs
    }
    for ref in protocol_required_refs:
        if not is_current_inbound_ref(ref, run_id=run_id):
            continue
        identity = (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("item_id"),
        )
        if identity in seen:
            continue
        refs.append(dict(ref))
        seen.add(identity)
    return tuple(refs)


def merge_current_inbound_budget_refs(
    draft_input_session_item_refs: list[dict[str, object]],
    transcript_budget: dict[str, object],
    *,
    run_id: str,
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = [dict(ref) for ref in draft_input_session_item_refs]
    seen = {
        (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("item_id"),
        )
        for ref in refs
    }
    included_refs = transcript_budget.get("included_refs")
    if not isinstance(included_refs, list | tuple):
        return refs
    for raw_ref in included_refs:
        if not isinstance(raw_ref, dict):
            continue
        if not is_current_inbound_ref(raw_ref, run_id=run_id):
            continue
        identity = (
            raw_ref.get("owner_module"),
            raw_ref.get("owner_kind"),
            raw_ref.get("owner_id"),
            raw_ref.get("item_id"),
        )
        if identity in seen:
            continue
        refs.append(dict(raw_ref))
        seen.add(identity)
    return refs


def is_current_inbound_ref(ref: dict[str, object], *, run_id: str) -> bool:
    if ref.get("budget_class") == "current_inbound":
        return True
    return (
        ref.get("owner_module") == "session"
        and ref.get("owner_kind") == "session_item"
        and ref.get("kind") == "user_message"
        and ref.get("source_module") == "orchestration"
        and ref.get("source_kind") == "orchestration_run"
        and ref.get("source_id") == run_id
    )
