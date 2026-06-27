from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from crxzipple.modules.tool.application.result_envelope import ToolResultEnvelope


def artifact_result_envelope(
    *,
    large_text_artifacts: list[dict[str, Any]],
    raw_output_artifacts: list[dict[str, Any]],
) -> ToolResultEnvelope:
    artifacts = [*large_text_artifacts, *raw_output_artifacts]
    evidence_refs = tuple(
        str(item["artifact_id"])
        for item in artifacts
        if str(item.get("artifact_id") or "").strip()
    )
    omitted_chars = sum(int(item.get("omitted_chars") or 0) for item in artifacts)
    original_chars = sum(
        int(item.get("original_text_chars") or 0)
        for item in artifacts
    )
    return ToolResultEnvelope(
        status="ok",
        summary=artifact_result_summary(
            large_text_artifacts=large_text_artifacts,
            raw_output_artifacts=raw_output_artifacts,
        ),
        output_payload={
            "externalized": True,
            "artifact_count": len(evidence_refs),
        },
        artifact_refs=tuple(
            {
                "kind": "artifact",
                "artifact_id": item.get("artifact_id"),
                "mime_type": item.get("mime_type"),
                "name": item.get("name"),
            }
            for item in artifacts
        ),
        key_facts={
            "externalized_text_block_count": len(large_text_artifacts),
            "externalized_raw_output_block_count": len(raw_output_artifacts),
            "artifact_count": len(evidence_refs),
            "original_text_chars": original_chars,
        },
        evidence_refs=evidence_refs,
        read_handles=tuple(
            {
                "kind": "artifact",
                "artifact_id": item.get("artifact_id"),
                "mime_type": item.get("mime_type"),
                "name": item.get("name"),
            }
            for item in artifacts
        ),
        omitted_count=len(artifacts),
        omitted_chars=omitted_chars,
        truncated=True,
        provider_replay_payload={
            "summary": artifact_result_summary(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ),
            "artifact_refs": list(evidence_refs),
            "read_handles": [
                {"kind": "artifact", "artifact_id": artifact_id}
                for artifact_id in evidence_refs
            ],
        },
        user_summary_payload={
            "summary": artifact_result_summary(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ),
            "artifact_count": len(evidence_refs),
        },
        trace_payload={
            "externalized_text_artifacts": large_text_artifacts,
            "externalized_raw_output_artifacts": raw_output_artifacts,
        },
    )


def merge_tool_result_envelopes(
    existing: Any,
    artifact_envelope: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(existing, Mapping) or not existing:
        return dict(artifact_envelope)
    merged = dict(existing)
    artifact_payload = dict(artifact_envelope)
    for key in (
        "artifact_refs",
        "evidence_refs",
        "warnings",
    ):
        merged[key] = _merged_json_list(merged.get(key), artifact_payload.get(key))
    artifact_read_handles = _json_list(artifact_payload.get("read_handles"))
    if artifact_read_handles:
        merged["read_handles"] = artifact_read_handles
    else:
        merged["read_handles"] = _merged_json_list(
            merged.get("read_handles"),
            artifact_payload.get("read_handles"),
        )
    for key in ("output_payload", "key_facts", "trace_payload"):
        merged[key] = _merged_json_mapping(
            merged.get(key),
            artifact_payload.get(key),
        )
    merged["provider_replay_payload"] = _merged_provider_replay_payload(
        merged.get("provider_replay_payload"),
        artifact_payload.get("provider_replay_payload"),
    )
    merged["user_summary_payload"] = _merged_json_mapping(
        merged.get("user_summary_payload"),
        artifact_payload.get("user_summary_payload"),
    )
    merged["omitted_count"] = int(merged.get("omitted_count") or 0) + int(
        artifact_payload.get("omitted_count") or 0,
    )
    merged["omitted_chars"] = int(merged.get("omitted_chars") or 0) + int(
        artifact_payload.get("omitted_chars") or 0,
    )
    merged["truncated"] = bool(merged.get("truncated")) or bool(
        artifact_payload.get("truncated"),
    )
    artifact_summary = artifact_payload.get("summary")
    if isinstance(artifact_summary, str) and artifact_summary.strip():
        warnings = _merged_json_list(
            merged.get("warnings"),
            [artifact_summary.strip()],
        )
        if warnings:
            merged["warnings"] = warnings
    return {
        key: value
        for key, value in merged.items()
        if value not in (None, {}, [], ())
    }


def artifact_result_summary(
    *,
    large_text_artifacts: list[dict[str, Any]],
    raw_output_artifacts: list[dict[str, Any]],
) -> str:
    if large_text_artifacts and raw_output_artifacts:
        return "Tool result text and raw output were externalized to artifact refs."
    if raw_output_artifacts:
        return "Tool raw output was externalized to artifact refs."
    return "Large text tool result was externalized to artifact refs."


def _merged_json_mapping(first: Any, second: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(first, Mapping):
        merged.update(dict(first))
    if isinstance(second, Mapping):
        merged.update(dict(second))
    return merged


def _merged_provider_replay_payload(first: Any, second: Any) -> dict[str, Any]:
    merged = _merged_json_mapping(first, second)
    if isinstance(first, Mapping) and "summary" in first:
        merged["summary"] = first["summary"]
    read_handles = _merged_json_list(
        first.get("read_handles") if isinstance(first, Mapping) else None,
        second.get("read_handles") if isinstance(second, Mapping) else None,
    )
    second_read_handles = (
        _json_list(second.get("read_handles")) if isinstance(second, Mapping) else []
    )
    if second_read_handles:
        read_handles = second_read_handles
    if read_handles:
        merged["read_handles"] = read_handles
    artifact_refs = _merged_json_list(
        first.get("artifact_refs") if isinstance(first, Mapping) else None,
        second.get("artifact_refs") if isinstance(second, Mapping) else None,
    )
    if artifact_refs:
        merged["artifact_refs"] = artifact_refs
    return merged


def _merged_json_list(first: Any, second: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in (*_json_list(first), *_json_list(second)):
        marker = json.dumps(value, ensure_ascii=True, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(value)
    return merged


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []
