"""Projected provider input item merge helpers."""

from __future__ import annotations

from .draft_input_current_inbound import (
    is_current_inbound_projected,
    projected_identity,
)


def merge_projected_input_items(
    *groups: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    merged: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for item in group:
            if _duplicates_current_inbound(item, merged):
                continue
            key = projected_identity(item)
            if key in seen:
                continue
            seen.add(key)
            insert_at = _current_inbound_insert_index(item, merged)
            if insert_at is not None:
                merged.insert(insert_at, dict(item))
                continue
            merged.append(dict(item))
    return tuple(merged)


def _duplicates_current_inbound(
    item: dict[str, object],
    existing_items: list[dict[str, object]],
) -> bool:
    if not is_current_inbound_projected(item):
        return False
    metadata = item.get("metadata")
    source_id = (
        str(metadata.get("source_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    payload = item.get("payload")
    payload_map = payload if isinstance(payload, dict) else {}
    for existing in existing_items:
        existing_payload = existing.get("payload")
        existing_payload_map = (
            existing_payload if isinstance(existing_payload, dict) else {}
        )
        existing_metadata = existing.get("metadata")
        existing_source_id = (
            str(existing_metadata.get("source_id") or "").strip()
            if isinstance(existing_metadata, dict)
            else ""
        )
        if source_id and existing_source_id == source_id:
            return True
        if (
            payload_map.get("role") == existing_payload_map.get("role")
            and payload_map.get("content") == existing_payload_map.get("content")
        ):
            return True
    return False


def _current_inbound_insert_index(
    item: dict[str, object],
    existing_items: list[dict[str, object]],
) -> int | None:
    if not is_current_inbound_projected(item):
        return None
    for index, existing in enumerate(existing_items):
        if existing.get("kind") in {"function_call", "function_call_output"}:
            return index
    return None
