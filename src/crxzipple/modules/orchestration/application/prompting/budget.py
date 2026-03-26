from __future__ import annotations

import math

from crxzipple.modules.orchestration.application.prompting.blocks import (
    PromptBlock,
    PromptBlockPolicy,
)
from crxzipple.modules.orchestration.application.prompting.modes import PromptMode


DEFAULT_SYSTEM_PROMPT_TOTAL_CHARS = 120_000
DEFAULT_SYSTEM_PROMPT_TOTAL_TOKENS = 30_000
_ESTIMATED_CHARS_PER_TOKEN = 4
_TRUNCATION_MARKER = "\n\n[...truncated for prompt budget...]\n"


def apply_system_prompt_budget(
    blocks: tuple[PromptBlock, ...],
    *,
    mode: PromptMode | None = None,
    total_max_chars: int = DEFAULT_SYSTEM_PROMPT_TOTAL_CHARS,
    total_max_tokens: int = DEFAULT_SYSTEM_PROMPT_TOTAL_TOKENS,
) -> tuple[PromptBlock, ...]:
    remaining_budget = max(0, total_max_chars)
    remaining_token_budget = max(0, total_max_tokens)
    planned_blocks: list[tuple[int, PromptBlock]] = []
    for index, block in enumerate(blocks):
        normalized = block.content.strip()
        if not normalized:
            continue
        if not _mode_allowed(block.policy, mode=mode):
            continue
        normalized, truncated = _apply_block_policy_cap(
            normalized,
            policy=block.policy,
            already_truncated=block.truncated,
        )
        if not normalized.strip():
            continue
        planned_blocks.append(
            (
                index,
                PromptBlock(
                    kind=block.kind,
                    content=normalized,
                    metadata=dict(block.metadata),
                    truncated=truncated,
                    policy=block.policy,
                ),
            ),
        )
    allocated_blocks: list[tuple[int, PromptBlock]] = []
    for index, block in sorted(
        planned_blocks,
        key=lambda item: (-item[1].policy.priority, item[0]),
    ):
        if remaining_budget <= 0 or remaining_token_budget <= 0:
            break
        normalized = block.content
        truncated = block.truncated
        max_chars = min(
            remaining_budget,
            max(0, remaining_token_budget * _ESTIMATED_CHARS_PER_TOKEN),
        )
        if len(normalized) > max_chars:
            if max_chars <= len(_TRUNCATION_MARKER):
                continue
            normalized = _truncate_content(
                normalized,
                max_chars=max_chars,
                strategy=block.policy.truncate_strategy,
            )
            truncated = True
        if not normalized.strip():
            continue
        estimated_tokens = estimate_text_tokens(normalized)
        allocated_blocks.append(
            (
                index,
                PromptBlock(
                    kind=block.kind,
                    content=normalized,
                    metadata=dict(block.metadata),
                    truncated=truncated,
                    policy=block.policy,
                ),
            ),
        )
        remaining_budget = max(0, remaining_budget - len(normalized))
        remaining_token_budget = max(0, remaining_token_budget - estimated_tokens)
    return tuple(
        block
        for _, block in sorted(allocated_blocks, key=lambda item: item[0])
    )


def estimate_text_tokens(content: str) -> int:
    normalized = content.strip()
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / _ESTIMATED_CHARS_PER_TOKEN))


def _apply_block_policy_cap(
    content: str,
    *,
    policy: PromptBlockPolicy,
    already_truncated: bool,
) -> tuple[str, bool]:
    normalized = content.strip()
    if not normalized:
        return "", already_truncated
    if policy.max_tokens is None or policy.max_tokens <= 0:
        return normalized, already_truncated
    max_chars = max(0, policy.max_tokens * _ESTIMATED_CHARS_PER_TOKEN)
    if len(normalized) <= max_chars:
        return normalized, already_truncated
    return (
        _truncate_content(
            normalized,
            max_chars=max_chars,
            strategy=policy.truncate_strategy,
        ),
        True,
    )


def _mode_allowed(
    policy: PromptBlockPolicy,
    *,
    mode: PromptMode | None,
) -> bool:
    if not policy.mode_allowlist or mode is None:
        return True
    return mode in policy.mode_allowlist


def _truncate_content(
    content: str,
    *,
    max_chars: int,
    strategy: str = "tail",
) -> str:
    if max_chars <= 0:
        return ""
    if len(content) <= max_chars:
        return content
    if len(_TRUNCATION_MARKER) >= max_chars:
        return _TRUNCATION_MARKER[:max_chars]
    if strategy == "head":
        tail_budget = max(1, max_chars - len(_TRUNCATION_MARKER))
        return f"{_TRUNCATION_MARKER}{content[-tail_budget:].lstrip()}"
    if strategy == "middle":
        available = max(2, max_chars - len(_TRUNCATION_MARKER))
        head_budget = max(1, math.ceil(available / 2))
        tail_budget = max(1, available - head_budget)
        return (
            f"{content[:head_budget].rstrip()}"
            f"{_TRUNCATION_MARKER}"
            f"{content[-tail_budget:].lstrip()}"
        )
    head_budget = max(1, max_chars - len(_TRUNCATION_MARKER))
    return f"{content[:head_budget].rstrip()}{_TRUNCATION_MARKER}"
