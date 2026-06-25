from __future__ import annotations

import hashlib
import json
from typing import Protocol
from urllib.parse import urlparse

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.domain import OrchestrationRun


class ToolProbeObservationPort(Protocol):
    def record_tool_call(
        self,
        run: OrchestrationRun,
        *,
        tool_id: str,
        tool_call: ToolCallIntent,
    ) -> None: ...


class RunMetadataToolProbeObservationRecorder:
    def record_tool_call(
        self,
        run: OrchestrationRun,
        *,
        tool_id: str,
        tool_call: ToolCallIntent,
    ) -> None:
        target = _normalized_probe_target(
            tool_id=tool_id,
            arguments=tool_call.arguments,
        )
        if target is None:
            return
        payload = run.metadata.get("repeated_probe_observation")
        if not isinstance(payload, dict):
            payload = {
                "targets": {},
                "repeated": [],
                "repeated_count": 0,
            }
        targets = payload.get("targets")
        if not isinstance(targets, dict):
            targets = {}
        target_key = str(target["key"])
        entry = targets.get(target_key)
        next_step = _total_probe_count(targets) + 1
        if not isinstance(entry, dict):
            entry = {
                **target,
                "count": 0,
                "first_seen_step": next_step,
                "last_seen_step": next_step,
                "tool_call_ids": [],
            }
        count = int(entry.get("count") or 0) + 1
        entry["count"] = count
        entry["last_seen_step"] = next_step
        tool_call_ids = entry.get("tool_call_ids")
        if not isinstance(tool_call_ids, list):
            tool_call_ids = []
        if tool_call.id not in tool_call_ids:
            tool_call_ids.append(tool_call.id)
        entry["tool_call_ids"] = tool_call_ids[-8:]
        targets[target_key] = entry
        repeated_entries = [
            dict(value)
            for value in targets.values()
            if isinstance(value, dict) and int(value.get("count") or 0) >= 3
        ]
        repeated_entries.sort(
            key=lambda item: (
                -int(item.get("count") or 0),
                str(item.get("key") or ""),
            ),
        )
        payload["targets"] = targets
        payload["repeated"] = repeated_entries[:20]
        payload["repeated_count"] = len(repeated_entries)
        run.metadata["repeated_probe_observation"] = payload


def _normalized_probe_target(
    *,
    tool_id: str,
    arguments: dict[str, object],
) -> dict[str, object] | None:
    url = _first_text_argument(
        arguments,
        ("url", "href", "uri", "endpoint", "request_url", "requestUrl"),
    )
    if url is not None:
        url_target = _normalized_url_probe_target(tool_id=tool_id, value=url)
        if url_target is not None:
            return url_target
    command = _first_text_argument(arguments, ("command", "cmd"))
    if command is not None:
        fingerprint = _command_fingerprint(command)
        return {
            "key": f"{tool_id}:command:{fingerprint}",
            "kind": "command",
            "tool_id": tool_id,
            "command_fingerprint": fingerprint,
        }
    if arguments:
        fingerprint = _json_fingerprint(arguments)
        return {
            "key": f"{tool_id}:args:{fingerprint}",
            "kind": "arguments",
            "tool_id": tool_id,
            "argument_fingerprint": fingerprint,
        }
    return {
        "key": f"{tool_id}:no_args",
        "kind": "no_args",
        "tool_id": tool_id,
    }


def _normalized_url_probe_target(
    *,
    tool_id: str,
    value: str,
) -> dict[str, object] | None:
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    domain = (parsed.netloc or "").lower()
    path = parsed.path or normalized
    if not domain and normalized.startswith("/"):
        path = normalized.split("?", 1)[0] or "/"
    elif not domain and "://" not in normalized:
        path = normalized.split("?", 1)[0] or normalized
    path = path or "/"
    key_target = f"{domain}{path}" if domain else path
    return {
        "key": f"{tool_id}:url:{key_target}",
        "kind": "url",
        "tool_id": tool_id,
        "domain": domain,
        "path": path,
        "normalized_url": key_target,
    }


def _first_text_argument(
    arguments: dict[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _command_fingerprint(command: str) -> str:
    normalized = " ".join(command.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _json_fingerprint(arguments: dict[str, object]) -> str:
    try:
        payload = json.dumps(arguments, ensure_ascii=True, sort_keys=True)
    except TypeError:
        payload = repr(sorted(arguments.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _total_probe_count(targets: dict[object, object]) -> int:
    total = 0
    for value in targets.values():
        if isinstance(value, dict):
            total += int(value.get("count") or 0)
    return total
