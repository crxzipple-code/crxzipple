from __future__ import annotations

from typing import Any, Mapping

from .observation_values import _payload_text


def _tabs_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("value")
    if not isinstance(value, list):
        return None
    tabs = tuple(item for item in value if isinstance(item, dict))
    return {
        "count": len(tabs),
        "items": tabs[:12],
    }


def _page_payload(
    snapshot: dict[str, Any],
    *,
    tabs: dict[str, Any] | None,
    target_id: str | None,
) -> dict[str, Any]:
    value = snapshot.get("value")
    tab = value.get("tab") if isinstance(value, dict) else None
    if isinstance(tab, dict):
        return {
            "target_id": _payload_text(tab.get("target_id")) or target_id,
            "title": _payload_text(tab.get("title")),
            "url": _payload_text(tab.get("url")),
            "type": _payload_text(tab.get("type")),
        }
    tab_payload = _tab_by_target_id(tabs, target_id=target_id)
    if tab_payload is not None:
        return tab_payload
    return {"target_id": target_id, "title": None, "url": None, "type": None}


def _tab_by_target_id(
    tabs: dict[str, Any] | None,
    *,
    target_id: str | None,
) -> dict[str, Any] | None:
    tab_list = _tabs_payload(tabs)
    if tab_list is None:
        return None
    items = tab_list.get("items")
    if not isinstance(items, tuple | list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if target_id is None or _payload_text(item.get("target_id")) == target_id:
            return {
                "target_id": _payload_text(item.get("target_id")) or target_id,
                "title": _payload_text(item.get("title")),
                "url": _payload_text(item.get("url")),
                "type": _payload_text(item.get("type")),
            }
    return None


def _snapshot_refs(snapshot_result: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    value = snapshot_result.get("value")
    if not isinstance(value, Mapping):
        return ()
    refs = value.get("refs")
    if not isinstance(refs, list | tuple):
        return ()
    normalized: list[dict[str, Any]] = []
    for item in refs[:40]:
        if isinstance(item, Mapping):
            normalized.append({str(key): value for key, value in item.items()})
    return tuple(normalized)


def _snapshot_frames(snapshot_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = snapshot_result.get("value")
    if not isinstance(value, Mapping):
        return []
    frames = value.get("frames")
    if not isinstance(frames, list | tuple):
        return []
    normalized: list[dict[str, Any]] = []
    for frame in frames[:20]:
        if not isinstance(frame, Mapping):
            continue
        refs = frame.get("refs")
        normalized.append(
            {
                "frame_path": frame.get("frame_path"),
                "snapshot_chars": len(str(frame.get("snapshot") or "")),
                "ref_count": len(refs) if isinstance(refs, list | tuple) else None,
            }
        )
    return normalized


def _evidence_summary(refs: tuple[dict[str, Any], ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in refs:
        evidence = item.get("evidence")
        if not isinstance(evidence, tuple | list):
            continue
        for entry in evidence:
            normalized = _payload_text(entry)
            if normalized is None:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    return counts


def _observation_message(
    *, page: Mapping[str, Any], refs: tuple[dict[str, Any], ...]
) -> str:
    title = _payload_text(page.get("title"))
    url = _payload_text(page.get("url"))
    label = title or url or "current page"
    return f"Observed {label} with {len(refs)} interactive ref(s)."
