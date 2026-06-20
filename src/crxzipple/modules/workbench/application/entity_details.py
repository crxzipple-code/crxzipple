from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WorkbenchLinkedEntityDetail:
    type: str
    id: str
    owner: str
    label: str
    summary: str
    payload: dict[str, object] = field(default_factory=dict)


def llm_response_item_detail(item: object) -> WorkbenchLinkedEntityDetail:
    payload = item.to_payload()
    kind = _enum_or_text(getattr(item, "kind", None)) or "llm_response_item"
    sequence_no = getattr(item, "sequence_no", None)
    label = f"{kind} #{sequence_no}" if sequence_no is not None else kind
    return WorkbenchLinkedEntityDetail(
        type="llm_response_item",
        id=str(getattr(item, "id")),
        owner="llm",
        label=label,
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def llm_invocation_detail(
    invocation: object,
    *,
    fallback_id: str,
) -> WorkbenchLinkedEntityDetail:
    payload = _llm_invocation_detail_payload(invocation)
    return WorkbenchLinkedEntityDetail(
        type="llm_invocation",
        id=str(getattr(invocation, "id", fallback_id)),
        owner="llm",
        label=str(getattr(invocation, "llm_id", "LLM invocation")),
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def session_item_detail(item: object) -> WorkbenchLinkedEntityDetail:
    payload = item.to_payload()
    kind = _enum_or_text(getattr(item, "kind", None)) or "session_item"
    sequence_no = getattr(item, "sequence_no", None)
    label = f"{kind} #{sequence_no}" if sequence_no is not None else kind
    return WorkbenchLinkedEntityDetail(
        type="session_item",
        id=str(getattr(item, "id")),
        owner="session",
        label=label,
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def tool_run_detail(tool_run: object) -> WorkbenchLinkedEntityDetail:
    payload = _tool_run_detail_payload(tool_run)
    return WorkbenchLinkedEntityDetail(
        type="tool_run",
        id=str(getattr(tool_run, "id")),
        owner="tool",
        label=str(getattr(tool_run, "tool_id", "tool_run")),
        summary=_entity_detail_summary(payload),
        payload=payload,
    )


def _entity_detail_summary(payload: dict[str, object]) -> str:
    runtime_observations = payload.get("runtime_observations")
    if isinstance(runtime_observations, dict):
        summary = runtime_observations.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()[:240]
    result_summary = payload.get("result_summary")
    if isinstance(result_summary, str) and result_summary.strip():
        return result_summary.strip()[:240]
    content = payload.get("content_payload")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()[:240]
        blocks = content.get("blocks")
        if isinstance(blocks, list):
            texts = [
                block.get("text", "").strip()
                for block in blocks
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ]
            joined = " ".join(text for text in texts if text)
            if joined:
                return joined[:240]
        tool_name = content.get("tool_name") or content.get("name")
        if isinstance(tool_name, str) and tool_name.strip():
            return tool_name.strip()
    for key in ("tool_name", "provider_item_type", "kind", "role"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(payload.get("kind") or payload.get("role") or "entity")


def _llm_invocation_detail_payload(invocation: object) -> dict[str, object]:
    result = getattr(invocation, "result", None)
    error = getattr(invocation, "error", None)
    request_metadata = dict(getattr(invocation, "request_metadata", {}) or {})
    provider_request_preview = _optional_dict(
        getattr(invocation, "provider_request_payload_preview", None),
    ) or {}
    return {
        "id": getattr(invocation, "id", None),
        "kind": "llm_invocation",
        "llm_id": getattr(invocation, "llm_id", None),
        "status": _enum_or_text(getattr(invocation, "status", None)),
        "started_at": _iso_or_none(getattr(invocation, "started_at", None)),
        "completed_at": _iso_or_none(getattr(invocation, "completed_at", None)),
        "message_count": len(tuple(getattr(invocation, "messages", ()) or ())),
        "tool_schema_count": len(tuple(getattr(invocation, "tool_schemas", ()) or ())),
        "request_metadata": request_metadata,
        "provider_request_payload_preview": provider_request_preview,
        "provider_render_report": _llm_provider_render_report(provider_request_preview),
        "provider_wire_preview": _llm_provider_wire_preview(provider_request_preview),
        "replay_input": _llm_replay_input_payload(invocation),
        "provider_input_summary": _llm_provider_input_summary_payload(
            request_metadata,
            provider_request_preview,
        ),
        "runtime_observations": _llm_runtime_observations_payload(
            provider_request_preview,
        ),
        "result_summary": _llm_result_summary(result, error=error),
        "result_payload": result.to_payload() if result is not None else None,
        "error": error.to_payload() if error is not None else None,
    }


def _llm_provider_render_report(
    provider_request_preview: dict[str, object],
) -> dict[str, object]:
    render_report = provider_request_preview.get("render_report")
    return dict(render_report) if isinstance(render_report, dict) else {}


def _llm_provider_wire_preview(
    provider_request_preview: dict[str, object],
) -> dict[str, object]:
    if not provider_request_preview:
        return {}
    safe_keys = {
        "preview_source",
        "provider",
        "api_family",
        "model",
        "endpoint",
        "transport",
        "renderer_id",
        "render_strategy",
        "message_type",
        "payload_keys",
        "message_count",
        "content_count",
        "input_item_count",
        "input_item_types",
        "input_delta_mode",
        "input_baseline_count",
        "input_item_fingerprints",
        "input_baseline_fingerprints",
        "input_delta_count",
        "instructions_fingerprint",
        "tool_count",
        "tool_fingerprints",
        "tool_types",
        "has_previous_response_id",
        "previous_response_id",
        "has_system",
        "option_summary",
        "provider_input_summary",
        "runtime_context",
        "runtime_request_summary",
        "context_slice_summary",
    }
    return {
        key: value
        for key, value in provider_request_preview.items()
        if key in safe_keys and value not in (None, {}, [], ())
    }


def _llm_replay_input_payload(invocation: object) -> dict[str, object]:
    items = tuple(getattr(invocation, "input_items", ()) or ())
    kind_values: list[str] = []
    source_values: list[str] = []
    tool_result_excerpt_samples: list[str] = []
    protocol_counts = {
        "reasoning": 0,
        "function_call": 0,
        "function_call_output": 0,
        "provider_external_item": 0,
    }
    for item in items:
        kind = _enum_or_text(getattr(item, "kind", None))
        if kind:
            kind_values.append(kind)
            if kind in protocol_counts:
                protocol_counts[kind] += 1
        source = str(getattr(item, "source", "") or "").strip()
        if source:
            source_values.append(source)
        if kind == "function_call_output":
            excerpt = _llm_input_item_tool_result_excerpt(item)
            if excerpt is not None:
                tool_result_excerpt_samples.append(excerpt)
    unique_kinds = list(dict.fromkeys(kind_values))
    unique_sources = list(dict.fromkeys(source_values))
    return {
        "count": len(items),
        "kinds": unique_kinds[:12],
        "sources": unique_sources[:12],
        "kind_counts": {
            kind: kind_values.count(kind)
            for kind in unique_kinds[:12]
        },
        "tool_result_excerpt_count": len(tool_result_excerpt_samples),
        "tool_result_excerpt_sample": (
            tool_result_excerpt_samples[0] if tool_result_excerpt_samples else None
        ),
        "protocol_counts": protocol_counts,
        "summary": _llm_replay_input_summary(
            count=len(items),
            kinds=unique_kinds,
            protocol_counts=protocol_counts,
        ),
    }


def _llm_replay_input_summary(
    *,
    count: int,
    kinds: list[str],
    protocol_counts: dict[str, int],
) -> str:
    if count <= 0:
        return "No replay input items."
    kind_label = ", ".join(kinds[:4]) if kinds else "unknown"
    protocol_total = sum(protocol_counts.values())
    if protocol_total:
        return f"{count} items; {kind_label}; protocol={protocol_total}"
    return f"{count} items; {kind_label}"


def _llm_input_item_tool_result_excerpt(item: object) -> str | None:
    payload = getattr(item, "payload", None)
    if not isinstance(payload, dict):
        return None
    text = _llm_input_output_text(payload.get("output"))
    if not text.strip() or "tool_result:" not in text:
        return None
    return _bounded_text(text.strip().replace("\n", " "), limit=240)


def _llm_input_output_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        text = value.get("text")
        return text if isinstance(text, str) else ""
    return ""


def _llm_provider_input_summary_payload(
    request_metadata: dict[str, object],
    provider_request_preview: dict[str, object] | None,
) -> dict[str, object]:
    preview = provider_request_preview or {}
    request_render_snapshot = request_metadata.get("request_render_snapshot")
    tool_surface = request_metadata.get("tool_surface")
    context_payload = request_render_snapshot if isinstance(request_render_snapshot, dict) else {}
    tool_payload = tool_surface if isinstance(tool_surface, dict) else {}
    payload: dict[str, object] = {}
    _copy_first_text(
        payload,
        "request_render_snapshot_id",
        preview,
        request_metadata,
        context_payload,
        source_keys=("request_render_snapshot_id", "snapshot_id"),
    )
    _copy_first_text(
        payload,
        "request_render_snapshot_schema_version",
        preview,
        context_payload,
        source_keys=("request_render_snapshot_schema_version", "tree_schema_version"),
    )
    _copy_first_int(
        payload,
        "request_render_snapshot_included_node_count",
        preview,
        context_payload,
        source_keys=(
            "request_render_snapshot_included_node_count",
            "included_node_count",
        ),
    )
    if "request_render_snapshot_included_node_count" not in payload:
        included_node_ids = context_payload.get("included_node_ids")
        if isinstance(included_node_ids, (list, tuple)):
            payload["request_render_snapshot_included_node_count"] = len(
                included_node_ids,
            )
    _copy_first_text(payload, "request_render_snapshot_fingerprint", preview)
    _copy_first_text(
        payload,
        "tool_surface_id",
        preview,
        request_metadata,
        tool_payload,
        source_keys=("tool_surface_id", "id"),
    )
    _copy_first_text(payload, "tool_surface_snapshot_id", preview, request_metadata)
    _copy_first_int(payload, "tool_surface_function_count", preview, request_metadata)
    if "tool_surface_function_count" not in payload:
        functions = tool_payload.get("functions")
        if isinstance(functions, (list, tuple)):
            payload["tool_surface_function_count"] = len(functions)
    _copy_first_int(
        payload,
        "tool_surface_mirrored_schema_count",
        preview,
        request_metadata,
    )
    if "tool_surface_mirrored_schema_count" not in payload:
        mirrored_schema_names = tool_payload.get("mirrored_schema_names")
        if isinstance(mirrored_schema_names, (list, tuple)):
            payload["tool_surface_mirrored_schema_count"] = len(mirrored_schema_names)
    _copy_first_text(payload, "tool_surface_fingerprint", preview)
    return payload


def _llm_runtime_observations_payload(
    provider_request_preview: dict[str, object],
) -> dict[str, object]:
    render_report = provider_request_preview.get("render_report")
    render_report_payload = render_report if isinstance(render_report, dict) else {}
    tool_protocol = render_report_payload.get("tool_protocol")
    tool_protocol_payload = tool_protocol if isinstance(tool_protocol, dict) else {}
    observation_count = int(bool(tool_protocol_payload))
    summary_parts: list[str] = []
    tool_protocol_summary = _tool_protocol_health_summary(tool_protocol_payload)
    if tool_protocol_summary is not None:
        summary_parts.append(f"tool protocol: {tool_protocol_summary}")
    return {
        "observation_count": observation_count,
        "summary": (
            "; ".join(summary_parts)
            if summary_parts
            else "No runtime observations."
        ),
        "tool_protocol": _tool_protocol_health_payload(tool_protocol_payload),
    }


def _tool_protocol_health_payload(payload: dict[str, object]) -> dict[str, object]:
    if not payload:
        return {
            "present": False,
            "replay_has_protocol_breaks": False,
            "source_had_protocol_breaks": False,
            "filtered_count": 0,
        }
    return {
        "present": True,
        "replay_has_protocol_breaks": payload.get("replay_has_protocol_breaks") is True,
        "source_had_protocol_breaks": payload.get("source_had_protocol_breaks") is True,
        "filtered_count": _tool_protocol_filtered_count(payload),
        "dropped_orphan_tool_output_count": _int_value(
            payload.get("dropped_orphan_tool_output_count"),
        ),
        "dropped_missing_tool_output_count": _int_value(
            payload.get("dropped_missing_tool_output_count"),
        ),
        "dropped_duplicate_tool_call_id_count": _int_value(
            payload.get("dropped_duplicate_tool_call_id_count"),
        ),
        "dropped_duplicate_tool_output_id_count": _int_value(
            payload.get("dropped_duplicate_tool_output_id_count"),
        ),
    }


def _tool_protocol_health_summary(payload: dict[str, object]) -> str | None:
    if not payload:
        return None
    replay_status = (
        "breaks"
        if payload.get("replay_has_protocol_breaks") is True
        else "clean"
    )
    filtered_count = _tool_protocol_filtered_count(payload)
    if filtered_count:
        return f"{replay_status}, filtered={filtered_count}"
    return replay_status


def _tool_protocol_filtered_count(payload: dict[str, object]) -> int:
    return sum(
        _int_value(payload.get(key))
        for key in (
            "dropped_orphan_tool_output_count",
            "dropped_missing_tool_output_count",
            "dropped_duplicate_tool_call_id_count",
            "dropped_duplicate_tool_output_id_count",
        )
    )


def _llm_result_summary(result: object | None, *, error: object | None) -> str:
    if error is not None:
        message = getattr(error, "message", None)
        return str(message or "LLM invocation failed.")
    if result is None:
        return "LLM invocation has no result yet."
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()[:240]
    tool_calls = getattr(result, "tool_calls", None)
    if isinstance(tool_calls, (list, tuple)) and tool_calls:
        return f"{len(tool_calls)} tool calls"
    finish_reason = getattr(result, "finish_reason", None)
    return str(finish_reason or "LLM invocation completed.")


def _tool_run_detail_payload(tool_run: object) -> dict[str, object]:
    result = getattr(tool_run, "result", None)
    error = getattr(tool_run, "error", None)
    envelope = getattr(tool_run, "result_envelope_payload", None)
    envelope_payload = dict(envelope) if isinstance(envelope, dict) else None
    payload: dict[str, object] = {
        "id": getattr(tool_run, "id", None),
        "kind": "tool_run",
        "tool_id": getattr(tool_run, "tool_id", None),
        "call_id": getattr(tool_run, "call_id", None),
        "tool_surface_id": getattr(tool_run, "tool_surface_id", None),
        "function_id": getattr(tool_run, "function_id", None),
        "source_id": getattr(tool_run, "source_id", None),
        "schema_hash": getattr(tool_run, "schema_hash", None),
        "status": _enum_or_text(getattr(tool_run, "status", None)),
        "input_payload": dict(getattr(tool_run, "input_payload", {}) or {}),
        "metadata": dict(getattr(tool_run, "metadata", {}) or {}),
        "invocation_context_payload": _optional_dict(
            getattr(tool_run, "invocation_context_payload", None),
        ),
        "result_payload": result.to_payload() if result is not None else None,
        "result_summary": _tool_run_result_summary(result, error=error),
        "result_envelope": envelope_payload,
        "read_handles": _tool_result_envelope_list(envelope_payload, "read_handles"),
        "raw_output_blocks": _tool_result_envelope_list(
            envelope_payload,
            "raw_output_blocks",
        ),
        "artifact_refs": _tool_result_envelope_list(envelope_payload, "artifact_refs"),
        "evidence_refs": _tool_result_envelope_list(envelope_payload, "evidence_refs"),
        "created_at": _iso_or_none(getattr(tool_run, "created_at", None)),
        "started_at": _iso_or_none(getattr(tool_run, "started_at", None)),
        "completed_at": _iso_or_none(getattr(tool_run, "completed_at", None)),
        "attempt_count": getattr(tool_run, "attempt_count", None),
        "max_attempts": getattr(tool_run, "max_attempts", None),
        "worker_id": getattr(tool_run, "worker_id", None),
    }
    if error is not None:
        payload["error"] = error.to_payload()
    return {key: value for key, value in payload.items() if value is not None}


def _tool_run_result_summary(result: object | None, *, error: object | None) -> str:
    if error is not None:
        message = getattr(error, "message", None)
        return str(message or "Tool run failed.")
    if result is None:
        return "Tool run has no result yet."
    blocks = getattr(result, "blocks", ())
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                return text[:240]
    return "Tool completed."


def _tool_result_envelope_list(
    envelope: dict[str, object] | None,
    key: str,
) -> list[object]:
    if envelope is None:
        return []
    value = envelope.get(key)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _optional_dict(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def _copy_first_text(
    target: dict[str, object],
    target_key: str,
    *sources: dict[str, object],
    source_keys: tuple[str, ...] | None = None,
) -> None:
    keys = source_keys or (target_key,)
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                target[target_key] = value.strip()
                return


def _copy_first_int(
    target: dict[str, object],
    target_key: str,
    *sources: dict[str, object],
    source_keys: tuple[str, ...] | None = None,
) -> None:
    keys = source_keys or (target_key,)
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value in (None, "", {}, []):
                continue
            target[target_key] = _int_value(value)
            return


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


def _bounded_text(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 1].rstrip() + "..."


def _enum_or_text(value: object) -> str | None:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, str):
        return value
    return None


def _iso_or_none(value: object) -> str | None:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return None
