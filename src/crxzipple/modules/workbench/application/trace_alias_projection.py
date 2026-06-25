from __future__ import annotations

from collections.abc import Iterable


def trace_aliases(trace_id: str, runs: Iterable[object]) -> set[str]:
    normalized = trace_id.strip()
    aliases = {normalized} if normalized else set()
    if not normalized:
        return aliases
    for run in runs:
        metadata = getattr(run, "metadata", {}) or {}
        metadata_trace_id = metadata.get("trace_id")
        metadata_correlation_id = metadata.get("correlation_id")
        session_key = getattr(run, "session_key", None)
        run_id = getattr(run, "id", None)
        if normalized in {
            run_id,
            session_key,
            metadata_trace_id if isinstance(metadata_trace_id, str) else None,
            (
                metadata_correlation_id
                if isinstance(metadata_correlation_id, str)
                else None
            ),
        }:
            aliases.add(str(run_id))
            if isinstance(session_key, str) and session_key.strip():
                aliases.add(session_key.strip())
            if isinstance(metadata_trace_id, str) and metadata_trace_id.strip():
                aliases.add(metadata_trace_id.strip())
            if (
                isinstance(metadata_correlation_id, str)
                and metadata_correlation_id.strip()
            ):
                aliases.add(metadata_correlation_id.strip())
    return aliases
