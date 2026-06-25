from __future__ import annotations

from hashlib import sha256

from crxzipple.modules.orchestration.domain import (
    ExecutionStepItemKind,
    ExecutionStepKind,
)


MAX_EXECUTION_ID_LENGTH = 100


def tool_batch_correlation_key(
    *,
    turn_id: str,
    llm_invocation_id: str,
) -> str:
    return f"{turn_id}:tool_batch:{llm_invocation_id}"


def approval_correlation_key(
    *,
    turn_id: str,
    request_id: str,
) -> str:
    return f"{turn_id}:approval:{request_id}"


def resume_correlation_key(
    *,
    turn_id: str,
    source_step_id: str,
    reason: str,
) -> str:
    return f"{turn_id}:resume:{source_step_id}:{reason}"


def final_response_correlation_key(
    *,
    turn_id: str,
    owner_id: str,
) -> str:
    return f"{turn_id}:final_response:{owner_id}"


def execution_chain_id(turn_id: str) -> str:
    return _bounded_id("chain", turn_id)


def execution_step_id(
    *,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> str:
    return _bounded_id("step", f"{turn_id}:{step_index}:{kind.value}")


def execution_step_item_id(
    *,
    step_id: str,
    item_index: int,
    kind: ExecutionStepItemKind,
) -> str:
    return _bounded_id("item", f"{step_id}:{item_index}:{kind.value}")


def execution_step_correlation_key(
    *,
    turn_id: str,
    step_index: int,
    kind: ExecutionStepKind,
) -> str:
    return f"{turn_id}:{step_index}:{kind.value}"


def _bounded_id(prefix: str, value: str) -> str:
    raw = f"{prefix}:{value}"
    if len(raw) <= MAX_EXECUTION_ID_LENGTH:
        return raw
    digest = sha256(raw.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"
