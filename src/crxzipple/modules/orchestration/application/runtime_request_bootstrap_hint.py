from __future__ import annotations


def runtime_request_bootstrap_hint_from_metadata(
    metadata: dict[str, object],
) -> dict[str, object]:
    policy = _metadata_mapping(metadata.get("runtime_request_bootstrap_policy"))
    runtime_task_policy = _metadata_mapping(metadata.get("runtime_task_policy"))
    runtime_request_bootstrap = _metadata_mapping(
        runtime_task_policy.get("runtime_request_bootstrap"),
    )
    if runtime_request_bootstrap:
        policy = {**runtime_request_bootstrap, **policy}
    if not policy:
        return {}
    payload: dict[str, object] = {}
    schema_ids = _metadata_string_list(policy.get("default_tool_schema_ids"))
    if schema_ids:
        payload["default_tool_schema_ids"] = schema_ids
    group_refs = _metadata_tool_schema_group_refs(
        policy.get("default_tool_schema_group_refs")
        or policy.get("tool_schema_group_refs"),
    )
    if group_refs:
        payload["default_tool_schema_group_refs"] = group_refs
    source = _metadata_text(policy.get("default_tool_schema_source"))
    if source is not None:
        payload["default_tool_schema_source"] = source
    elif payload:
        payload["default_tool_schema_source"] = "runtime_request_bootstrap_policy"
    return payload


def _metadata_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        return []
    items: list[str] = []
    for item in candidates:
        text = _metadata_text(item)
        if text is not None and text not in items:
            items.append(text)
    return items


def _metadata_tool_schema_group_refs(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, str):
        candidates = (value,)
    elif isinstance(value, (list, tuple)):
        candidates = tuple(value)
    else:
        return []
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        ref = _metadata_tool_schema_group_ref(item)
        if ref is None:
            continue
        key = (
            ref.get("node_id", ""),
            ref.get("source_id", ""),
            ref.get("group_key", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _metadata_tool_schema_group_ref(value: object) -> dict[str, str] | None:
    if isinstance(value, dict):
        node_id = _metadata_text(value.get("node_id"))
        source_id = _metadata_text(value.get("source_id"))
        group_key = _metadata_text(value.get("group_key"))
        reason = _metadata_text(value.get("reason"))
        if node_id is not None:
            payload = {"node_id": node_id}
            if source_id is not None:
                payload["source_id"] = source_id
            if group_key is not None:
                payload["group_key"] = group_key
            if reason is not None:
                payload["reason"] = reason
            return payload
        if source_id is None or group_key is None:
            return None
        payload = {"source_id": source_id, "group_key": group_key}
        if reason is not None:
            payload["reason"] = reason
        return payload
    text = _metadata_text(value)
    if text is None:
        return None
    if text.startswith("tools."):
        return {"node_id": text}
    for separator in (":", "#", "/"):
        if separator not in text:
            continue
        source_id, group_key = text.rsplit(separator, 1)
        source_id = source_id.strip()
        group_key = group_key.strip()
        if source_id and group_key:
            return {"source_id": source_id, "group_key": group_key}
    return None

