from __future__ import annotations

from crxzipple.modules.session.domain import SessionItem, SessionItemKind


def is_protocol_required_item(item: SessionItem) -> bool:
    return item.kind in {
        SessionItemKind.TOOL_CALL,
        SessionItemKind.TOOL_RESULT,
        SessionItemKind.PROVIDER_EXTERNAL_ACTIVITY,
    }


def session_item_budget_ref(item: SessionItem) -> dict[str, object]:
    ref: dict[str, object] = {
        "owner_module": "session",
        "owner_kind": "session_item",
        "owner_id": item.id,
        "item_id": item.id,
        "session_id": item.session_id,
        "sequence_no": item.sequence_no,
        "kind": item.kind.value,
        "role": item.role or "",
        "render_mode": "full",
        "render_scope": "provider_replay",
    }
    if item.source_module:
        ref["source_module"] = item.source_module
    if item.source_kind:
        ref["source_kind"] = item.source_kind
    if item.source_id:
        ref["source_id"] = item.source_id
    if item.provider_item_id:
        ref["provider_item_id"] = item.provider_item_id
    if item.provider_item_type:
        ref["provider_item_type"] = item.provider_item_type
    if item.call_id:
        ref["tool_call_id"] = item.call_id
    if item.tool_name:
        ref["tool_name"] = item.tool_name
    if is_protocol_required_item(item):
        ref["protocol_required"] = True
        ref["budget_class"] = "protocol_required"
    return ref


def tool_protocol_normalization_diagnostics(
    source: dict[str, object],
    replay: dict[str, object],
) -> dict[str, object]:
    source_orphans = _int_value(source.get("orphan_tool_output_count"))
    replay_orphans = _int_value(replay.get("orphan_tool_output_count"))
    source_missing = _int_value(source.get("missing_tool_output_count"))
    replay_missing = _int_value(replay.get("missing_tool_output_count"))
    source_duplicate_calls = _int_value(source.get("duplicate_tool_call_id_count"))
    replay_duplicate_calls = _int_value(replay.get("duplicate_tool_call_id_count"))
    source_duplicate_outputs = _int_value(source.get("duplicate_tool_output_id_count"))
    replay_duplicate_outputs = _int_value(replay.get("duplicate_tool_output_id_count"))
    diagnostics: dict[str, object] = {
        "schema_version": "2026-06-15.tool_protocol_normalization.v1",
        "dropped_orphan_tool_output_count": max(0, source_orphans - replay_orphans),
        "dropped_missing_tool_output_count": max(0, source_missing - replay_missing),
        "dropped_duplicate_tool_call_id_count": max(
            0,
            source_duplicate_calls - replay_duplicate_calls,
        ),
        "dropped_duplicate_tool_output_id_count": max(
            0,
            source_duplicate_outputs - replay_duplicate_outputs,
        ),
        "source_had_protocol_breaks": any(
            count > 0
            for count in (
                source_orphans,
                source_missing,
                source_duplicate_calls,
                source_duplicate_outputs,
            )
        ),
        "replay_has_protocol_breaks": any(
            count > 0
            for count in (
                replay_orphans,
                replay_missing,
                replay_duplicate_calls,
                replay_duplicate_outputs,
            )
        ),
    }
    return {
        key: value
        for key, value in diagnostics.items()
        if value not in (None, [], {}, 0, False)
        or key
        in {
            "dropped_orphan_tool_output_count",
            "dropped_missing_tool_output_count",
            "dropped_duplicate_tool_call_id_count",
            "dropped_duplicate_tool_output_id_count",
            "source_had_protocol_breaks",
            "replay_has_protocol_breaks",
        }
    }


def tool_protocol_diagnostics(items: tuple[SessionItem, ...]) -> dict[str, object]:
    calls_by_id: dict[str, list[SessionItem]] = {}
    outputs_by_id: dict[str, list[SessionItem]] = {}
    orphan_outputs: list[SessionItem] = []
    for item in items:
        if item.kind is SessionItemKind.TOOL_CALL:
            if item.call_id is None or not item.call_id.strip():
                continue
            calls_by_id.setdefault(item.call_id, []).append(item)
            continue
        if item.kind is not SessionItemKind.TOOL_RESULT:
            continue
        if item.call_id is None or not item.call_id.strip():
            orphan_outputs.append(item)
            continue
        outputs_by_id.setdefault(item.call_id, []).append(item)
    for call_id, outputs in outputs_by_id.items():
        calls = calls_by_id.get(call_id, [])
        if not calls:
            orphan_outputs.extend(outputs)
            continue
        first_call_sequence = min(item.sequence_no for item in calls)
        orphan_outputs.extend(
            item for item in outputs if item.sequence_no < first_call_sequence
        )
    missing_output_calls = tuple(
        calls[0]
        for call_id, calls in calls_by_id.items()
        if call_id not in outputs_by_id
    )
    duplicate_call_ids = tuple(
        call_id for call_id, calls in calls_by_id.items() if len(calls) > 1
    )
    duplicate_output_ids = tuple(
        call_id for call_id, outputs in outputs_by_id.items() if len(outputs) > 1
    )
    diagnostics: dict[str, object] = {
        "schema_version": "2026-06-15.tool_protocol_diagnostics.v1",
        "tool_call_count": sum(len(call_items) for call_items in calls_by_id.values()),
        "tool_output_count": sum(
            len(output_items) for output_items in outputs_by_id.values()
        )
        + len(
            tuple(
                item
                for item in orphan_outputs
                if item.call_id is None or not item.call_id.strip()
            ),
        ),
        "orphan_tool_output_count": len(orphan_outputs),
        "missing_tool_output_count": len(missing_output_calls),
        "duplicate_tool_call_id_count": len(duplicate_call_ids),
        "duplicate_tool_output_id_count": len(duplicate_output_ids),
        "orphan_tool_outputs": [
            session_item_budget_ref(item) for item in tuple(orphan_outputs)[:12]
        ],
        "missing_tool_outputs": [
            session_item_budget_ref(item) for item in missing_output_calls[:12]
        ],
        "duplicate_tool_call_ids": list(duplicate_call_ids[:12]),
        "duplicate_tool_output_ids": list(duplicate_output_ids[:12]),
    }
    return {
        key: value
        for key, value in diagnostics.items()
        if value not in (None, [], {}, 0)
        or key
        in {
            "tool_call_count",
            "tool_output_count",
            "orphan_tool_output_count",
            "missing_tool_output_count",
            "duplicate_tool_call_id_count",
            "duplicate_tool_output_id_count",
        }
    }


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "is_protocol_required_item",
    "session_item_budget_ref",
    "tool_protocol_diagnostics",
    "tool_protocol_normalization_diagnostics",
]
