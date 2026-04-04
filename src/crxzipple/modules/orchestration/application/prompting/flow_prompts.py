from __future__ import annotations

from crxzipple.modules.orchestration.application.prompting.blocks import (
    PromptBlock,
    PromptBlockPolicy,
)
from crxzipple.modules.orchestration.application.prompting.modes import PromptMode

_FLOW_PROMPT_POLICY = PromptBlockPolicy(priority=900, max_tokens=1_500)


def build_flow_prompt_block(
    *,
    mode: PromptMode,
    hint_payload: dict[str, object] | None,
) -> PromptBlock | None:
    if mode is PromptMode.SESSION_START:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_session_start_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    if mode is PromptMode.APPROVAL_RESUME:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_approval_resume_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    if mode is PromptMode.APPROVAL_DENIED:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_approval_denied_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    if mode is PromptMode.RECOVERY_RESUME:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_recovery_resume_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    if mode is PromptMode.HEARTBEAT:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_heartbeat_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    if mode is PromptMode.MEMORY_FLUSH:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_memory_flush_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    if mode is PromptMode.COMPACTION:
        return PromptBlock(
            kind="flow_prompt",
            content=_build_compaction_prompt(hint_payload),
            metadata=_flow_prompt_metadata(mode, hint_payload),
            policy=_FLOW_PROMPT_POLICY,
        )
    return None


def _build_session_start_prompt(hint_payload: dict[str, object] | None) -> str:
    event = _hint_text(hint_payload, "event")
    session_kind = _hint_text(hint_payload, "session_kind")
    reason = _hint_text(hint_payload, "reason")
    lines = [
        "# Session Start",
        "",
        "You are replying at the start of a new active session.",
    ]
    if event == "reset":
        lines[2] = "You are replying after the active session was reset."
    if session_kind is not None:
        lines.append(f"- Session kind: {session_kind}")
    if reason is not None:
        lines.append(f"- Reset reason: {reason}")
    lines.extend(
        [
            "Orient yourself using the current project context and the latest user request.",
            "Do not assume unseen prior context from earlier sessions unless it is present in the transcript, workspace context, or recalled memory.",
        ],
    )
    return "\n".join(lines).strip()


def _build_approval_resume_prompt(hint_payload: dict[str, object] | None) -> str:
    effect_line = _effect_line(hint_payload)
    decision = _hint_text(hint_payload, "decision")
    lines = [
        "# Approval Update",
        "",
        "The user approved the requested additional access for this turn.",
    ]
    if effect_line is not None:
        lines.append(effect_line)
    lines.extend(
        [
            "Resume the interrupted task from where it left off.",
            "Do not restart the task from scratch.",
        ],
    )
    if decision == "allow_once":
        lines.extend(
            [
                "This approval is valid only for the current turn.",
                "If the same access is needed in a later turn and the tool is not currently visible, request it again instead of assuming it still exists.",
                "This approval applies only to the requested effect above, not to every gated remote or local tool.",
                "If the tool you need is still not visible after resuming, request a different effect instead of claiming that no callable tool exists.",
            ],
        )
    elif decision == "allow_for_session":
        lines.append(
            "This approval remains available for later turns in the current session unless visibility changes.",
        )
    elif decision == "always_for_agent":
        lines.append(
            "This approval should remain available for future turns with this agent unless visibility changes.",
        )
    else:
        lines.append(
            "Do not request the same access again unless a different effect is required later.",
        )
    return "\n".join(lines).strip()


def _build_approval_denied_prompt(hint_payload: dict[str, object] | None) -> str:
    effect_line = _effect_line(hint_payload)
    lines = [
        "# Approval Update",
        "",
        "The user denied the requested additional access.",
    ]
    if effect_line is not None:
        lines.append(effect_line)
    lines.extend(
        [
            "Continue with the tools and access that are already available.",
            "Do not request the same access again unless the user changes direction or there is materially new justification.",
            "Prefer a fallback answer, a safer path, or a concise explanation of the limitation.",
        ],
    )
    return "\n".join(lines).strip()


def _build_recovery_resume_prompt(hint_payload: dict[str, object] | None) -> str:
    reason = _hint_text(hint_payload, "reason")
    lines = [
        "# Recovery Update",
        "",
        "A paused run is resuming after background work completed or terminal results became available.",
    ]
    if reason is not None:
        lines.append(f"- Resume reason: {reason}")
    lines.extend(
        [
            "Continue from the current state instead of restarting the task.",
            "Use the newly available tool results before deciding the next step.",
        ],
    )
    return "\n".join(lines).strip()


def _build_heartbeat_prompt(hint_payload: dict[str, object] | None) -> str:
    reason = _hint_text(hint_payload, "reason")
    idle_reply = _hint_text(hint_payload, "idle_reply")
    lines = [
        "# Heartbeat",
        "",
        "You are handling a lightweight heartbeat check for the current session.",
    ]
    if reason is not None:
        lines.append(f"- Heartbeat reason: {reason}")
    if idle_reply is not None:
        lines.append(f"- Default idle reply: {idle_reply}")
    lines.extend(
        [
            "If there is clear unfinished work that can move forward safely with the current context and visible tools, continue it.",
            "If there is nothing actionable right now, reply briefly with the default idle reply.",
            "Do not restart the task from scratch.",
            "Do not request additional access, read skill guidance, or perform broad exploratory work just because a heartbeat occurred.",
        ],
    )
    return "\n".join(lines).strip()


def _build_compaction_prompt(hint_payload: dict[str, object] | None) -> str:
    reason = _hint_text(hint_payload, "reason")
    preserve = _hint_text(hint_payload, "preserve")
    lines = [
        "# Compaction",
        "",
        "You are compacting the current session context so later turns can continue with less history.",
    ]
    if reason is not None:
        lines.append(f"- Compaction reason: {reason}")
    if preserve is not None:
        lines.append(f"- Preserve explicitly: {preserve}")
    lines.extend(
        [
            "Produce a concise, factual summary of the session state rather than a normal user-facing reply.",
            "Preserve open tasks, completed work, decisions, approvals, constraints, user preferences, and any important tool results.",
            "Remove repetition, incidental chatter, and details that are no longer needed to continue the work.",
            "Do not invent facts that are not present in the transcript, recalled memory, workspace context, or tool results.",
            "Do not call tools, request additional access, or read skill guidance during compaction.",
        ],
    )
    return "\n".join(lines).strip()


def _build_memory_flush_prompt(hint_payload: dict[str, object] | None) -> str:
    reason = _hint_text(hint_payload, "reason")
    lines = [
        "# Memory Flush",
        "",
        "You are capturing durable memory for the current session.",
    ]
    if reason is not None:
        lines.append(f"- Flush reason: {reason}")
    lines.extend(
        [
            "Write only durable facts worth carrying into future sessions: decisions, constraints, stable preferences, ongoing commitments, and important project context.",
            "Do not write transient chatter, low-signal progress updates, or details that matter only for the current turn.",
            "This run is only for durable memory capture. Never answer or continue the user's conversation in this run.",
            "If there is durable memory to keep, call memory_write_daily exactly once with the markdown note body to append to today's daily memory file.",
            "If there is nothing durable to record, call memory_flush_skip exactly once.",
            "Do not return the memory note body directly in your assistant message.",
            "Do not call any other tools, request additional access, read skill guidance, or search memory during a memory flush.",
        ],
    )
    return "\n".join(lines).strip()


def _flow_prompt_metadata(
    mode: PromptMode,
    hint_payload: dict[str, object] | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {"mode": mode.value}
    if not hint_payload:
        return metadata
    for key in (
        "decision",
        "effect_id",
        "label",
        "event",
        "session_kind",
        "reason",
        "idle_reply",
        "preserve",
    ):
        value = hint_payload.get(key)
        if isinstance(value, str) and value.strip():
            metadata[key] = value.strip()
    return metadata


def _effect_line(hint_payload: dict[str, object] | None) -> str | None:
    if not hint_payload:
        return None
    effect_id = hint_payload.get("effect_id")
    label = hint_payload.get("label")
    effect_text = str(effect_id).strip() if effect_id is not None else ""
    label_text = str(label).strip() if label is not None else ""
    if effect_text and label_text:
        return f"- Requested effect: {label_text} ({effect_text})"
    if effect_text:
        return f"- Requested effect: {effect_text}"
    if label_text:
        return f"- Requested effect: {label_text}"
    return None


def _hint_text(hint_payload: dict[str, object] | None, key: str) -> str | None:
    if not hint_payload:
        return None
    value = hint_payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
