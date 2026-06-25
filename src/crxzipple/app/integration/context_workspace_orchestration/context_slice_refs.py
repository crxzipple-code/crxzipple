"""Reference and report projections from context slices."""

from __future__ import annotations


def control_slice_selected_node_ids(control_slice: object | None) -> tuple[str, ...]:
    if control_slice is None:
        return ()
    report = getattr(control_slice, "report", None)
    selected_node_ids = getattr(report, "selected_node_ids", ()) if report else ()
    if isinstance(selected_node_ids, (list, tuple)):
        return tuple(
            str(node_id)
            for node_id in selected_node_ids
            if str(node_id).strip()
        )
    return tuple(
        str(node_id)
        for ref in (getattr(control_slice, "selected_refs", ()) or ())
        for node_id in (getattr(ref, "node_id", ""),)
        if str(node_id).strip()
    )


def context_slice_included_node_ids(context_slice: object | None) -> tuple[str, ...]:
    if context_slice is None:
        return ()
    report = getattr(context_slice, "report", None)
    included_node_ids = getattr(report, "included_node_ids", ()) if report else ()
    if not isinstance(included_node_ids, (list, tuple)):
        return ()
    return tuple(
        str(node_id)
        for node_id in included_node_ids
        if str(node_id).strip()
    )


def context_slice_omitted_node_ids(context_slice: object | None) -> tuple[str, ...]:
    if context_slice is None:
        return ()
    report = getattr(context_slice, "report", None)
    omitted_node_ids = getattr(report, "omitted_node_ids", ()) if report else ()
    if not isinstance(omitted_node_ids, (list, tuple)):
        return ()
    return tuple(
        str(node_id)
        for node_id in omitted_node_ids
        if str(node_id).strip()
    )


def context_slice_session_refs(
    context_slice: object | None,
) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in getattr(context_slice, "items", ()) or ():
        if getattr(item, "owner", None) != "session":
            continue
        item_metadata = getattr(item, "metadata", None)
        if (
            isinstance(item_metadata, dict)
            and item_metadata.get("owner_resolution") == "owner_unresolved"
        ):
            continue
        owner_ref = getattr(item, "owner_ref", None)
        if not isinstance(owner_ref, dict):
            continue
        item_id = metadata_text_value(
            owner_ref.get("session_item_id"),
            owner_ref.get("item_id"),
            owner_ref.get("owner_id"),
            owner_ref.get("call_session_item_id"),
            owner_ref.get("result_session_item_id"),
            owner_ref.get("tool_call_id"),
        )
        if item_id is None or item_id in seen:
            continue
        ref = dict(owner_ref)
        ref.setdefault("item_id", item_id)
        ref.setdefault("session_item_id", item_id)
        ref.setdefault(
            "node_id",
            getattr(item, "node_id", None) or getattr(item, "item_id", ""),
        )
        ref.setdefault("owner_module", "session")
        ref.setdefault("owner_kind", getattr(item, "kind", "session_item"))
        ref.setdefault("owner_id", item_id)
        refs.append(ref)
        seen.add(item_id)
    return tuple(refs)


def context_slice_collapsed_refs(
    context_slice: object | None,
) -> tuple[dict[str, object], ...]:
    if context_slice is None:
        return ()
    report = getattr(context_slice, "report", None)
    collapsed_refs = getattr(report, "collapsed_refs", ()) if report else ()
    if not isinstance(collapsed_refs, (list, tuple)):
        return ()
    return tuple(dict(ref) for ref in collapsed_refs if isinstance(ref, dict))


def context_slice_report_refs(
    context_slice: object | None,
) -> dict[str, tuple[dict[str, object], ...]]:
    report = getattr(context_slice, "report", None) if context_slice is not None else None
    return {
        "archived_refs": context_slice_report_ref_tuple(report, "archived_refs"),
        "redacted_refs": context_slice_report_ref_tuple(report, "redacted_refs"),
        "unresolved_refs": context_slice_report_ref_tuple(report, "unresolved_refs"),
    }


def context_slice_loss(context_slice: object | None) -> dict[str, object]:
    report = getattr(context_slice, "report", None) if context_slice is not None else None
    loss = getattr(report, "loss", {}) if report is not None else {}
    if not isinstance(loss, dict):
        return {}
    return {
        str(key): value
        for key, value in loss.items()
        if value not in (None, "", {}, [])
    }


def context_slice_report_ref_tuple(
    report: object | None,
    attribute: str,
) -> tuple[dict[str, object], ...]:
    refs = getattr(report, attribute, ()) if report is not None else ()
    if not isinstance(refs, (list, tuple)):
        return ()
    return tuple(dict(ref) for ref in refs if isinstance(ref, dict))


def metadata_text_value(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
