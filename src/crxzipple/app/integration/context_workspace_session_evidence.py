from __future__ import annotations

def evidence_facts(
    *,
    tool_name: str,
    payload: dict[str, object],
    details: object,
    metadata: object,
) -> dict[str, object]:
    facts: dict[str, object] = {}
    for source in (details, metadata):
        if not isinstance(source, dict):
            continue
        for fact_key, source_keys in (
            ("kind", ("kind", "action", "operation")),
            ("url", ("url", "page_url", "current_url", "href")),
            ("title", ("title", "page_title")),
            ("target_id", ("target_id", "targetId")),
            ("profile", ("profile", "profile_name")),
            ("profile_source", ("profile_source",)),
            ("allocation_id", ("allocation_id", "context_lease_id")),
            ("host_service_key", ("host_service_key",)),
            ("origin", ("origin", "target_origin")),
            ("endpoint", ("endpoint", "api_endpoint", "request_url", "path")),
            ("method", ("method", "request_method")),
            ("http_status", ("status_code", "http_status", "response_status")),
            ("request_id", ("request_id", "requestId")),
            ("body_ref", ("body_ref", "response_body_ref")),
            ("request_body_ref", ("request_body_ref",)),
            ("selector", ("verified_selector", "selector", "matched_selector")),
            ("ref", ("verified_ref", "ref", "target_ref", "element_ref")),
        ):
            if fact_key in facts:
                continue
            value = find_first_text(source, source_keys)
            if value is not None:
                facts[fact_key] = _truncate(value, 180)
        merge_artifact_evidence_facts(facts, source)
        merge_structured_tool_facts(facts, source)
    for fact_key, source_keys in (
        ("tool_run_id", ("tool_run_id",)),
        ("status", ("status",)),
    ):
        value = find_first_text(payload, source_keys)
        if value is not None:
            facts[fact_key] = _truncate(value, 180)
    if tool_name.startswith("browser.") and "kind" not in facts:
        facts["kind"] = tool_name.removeprefix("browser.")
    return facts


def merge_artifact_evidence_facts(
    facts: dict[str, object],
    source: dict[str, object],
) -> None:
    if "artifact_ids" in facts:
        return
    artifact_ids = source.get("artifact_ids")
    if not isinstance(artifact_ids, list):
        return
    normalized: list[str] = []
    for item in artifact_ids:
        value = _optional_text(item)
        if value is not None:
            normalized.append(_truncate(value, 180))
        if len(normalized) >= 8:
            break
    if normalized:
        facts["artifact_ids"] = list(dict.fromkeys(normalized))


def merge_structured_tool_facts(
    facts: dict[str, object],
    source: dict[str, object],
) -> None:
    for key, alias in (
        ("payload_shape", None),
        ("result_shape", None),
        ("runtime_globals", None),
        ("verified_ref", "ref"),
        ("verified_selector", "selector"),
    ):
        if key in facts or (alias is not None and alias in facts):
            continue
        value = small_structured_evidence_fact(source.get(key))
        if value is not None:
            facts[key] = value


def small_structured_evidence_fact(value: object, *, depth: int = 0) -> object | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return _truncate(value, 240)
    if isinstance(value, list):
        items: list[object] = []
        for item in value[:12]:
            normalized = small_structured_evidence_fact(item, depth=depth + 1)
            if normalized is not None:
                items.append(normalized)
        return items or None
    if isinstance(value, dict):
        if depth >= 4:
            return {"type": "object", "keys": len(value)}
        normalized: dict[str, object] = {}
        for index, (item_key, item_value) in enumerate(value.items()):
            if index >= 16:
                normalized["_truncated_keys"] = max(len(value) - 16, 0)
                break
            item = small_structured_evidence_fact(item_value, depth=depth + 1)
            if item is not None:
                normalized[str(item_key)] = item
        return normalized or None
    return _truncate(str(value), 240)


def evidence_type(
    *,
    tool_name: str,
    status: str,
    facts: dict[str, object],
) -> str:
    if status.lower() not in {"succeeded", "completed", "success"}:
        return "failed_attempt"
    kind = _optional_text(facts.get("kind")) or ""
    if "hypothesis" in facts:
        return "hypothesis"
    if "endpoint" in facts or kind.startswith("network"):
        return "api_endpoint"
    if "result_shape" in facts:
        return "result_shape"
    if "payload_shape" in facts:
        return "payload_shape"
    if tool_name.startswith("browser.") and (
        "selector" in facts or "ref" in facts
    ):
        return "observation"
    if tool_name.startswith("browser."):
        return "observation"
    return "user_visible_result"


def find_first_text(value: object, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        normalized = {str(key): item for key, item in value.items()}
        for key in keys:
            if key in normalized:
                candidate = scalar_text(normalized[key])
                if candidate is not None:
                    return candidate
        for item in normalized.values():
            found = find_first_text(item, keys)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_first_text(item, keys)
            if found is not None:
                return found
    return None


def scalar_text(value: object) -> str | None:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."
