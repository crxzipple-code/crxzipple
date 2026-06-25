from __future__ import annotations

from typing import Any


def runtime_context_input_item(runtime_context: dict[str, Any]) -> dict[str, Any] | None:
    text = runtime_context_input_text(runtime_context)
    if not text:
        return None
    return {
        "type": "message",
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": text,
            },
        ],
    }


def runtime_context_input_text(runtime_context: dict[str, Any]) -> str:
    if not isinstance(runtime_context, dict) or not runtime_context:
        return ""
    lines = [
        "# Runtime Context",
        "",
        "These are runtime facts for the current turn.",
        "",
    ]
    for label, key in (
        ("Agent", "agent_id"),
        ("Model", "llm_id"),
        ("Agent home", "agent_home_dir"),
        ("Workspace", "workspace_dir"),
    ):
        value = runtime_context.get(key)
        if value not in (None, "", {}, []):
            lines.append(f"- {label}: {value}")
    current_step = _runtime_int(runtime_context.get("current_step"))
    max_steps = _runtime_int(runtime_context.get("max_steps"))
    remaining_steps = _runtime_int(runtime_context.get("remaining_steps"))
    status = _runtime_text(runtime_context.get("step_budget_status")) or "unknown"
    if current_step is not None and max_steps is not None:
        if remaining_steps is None:
            remaining_steps = max(max_steps - current_step, 0)
        lines.append(
            "- Step budget: "
            f"{current_step}/{max_steps} used; "
            f"{remaining_steps} remaining; status={status}",
        )
        if status in {"finalize_now", "critical"}:
            lines.append(
                "- Step budget guidance: finish with the best supported answer now "
                "when available evidence can support an answer. Avoid opening new "
                "exploratory branches unless a specific missing fact is required for "
                "the final answer.",
            )
        elif status == "constrained":
            lines.append(
                "- Step budget guidance: prefer direct verification and convergence "
                "over broad exploration. Before any new probe, identify the specific "
                "missing fact it will add; otherwise summarize the current evidence "
                "and answer.",
            )
    return "\n".join(lines).strip()


def _runtime_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _runtime_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
