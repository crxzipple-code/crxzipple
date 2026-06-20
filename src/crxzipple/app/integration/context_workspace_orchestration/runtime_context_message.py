from __future__ import annotations

import os
from datetime import datetime


def build_runtime_context_message(
    *,
    agent_id: str,
    llm_id: str,
    home_dir: str | None,
    workspace_dir: str | None,
    available_tool_ids: tuple[str, ...] = (),
    current_step: int | None = None,
    max_steps: int | None = None,
    remaining_steps: int | None = None,
    step_budget_status: str | None = None,
) -> str:
    now = datetime.now().astimezone()
    timezone_name = now.tzname() or "unknown"
    lines = [
        "# Runtime Context",
        "",
        "These are runtime facts for the current turn.",
        "",
        f"- Agent: {agent_id}",
        f"- Model: {llm_id}",
        f"- Current time: {now.isoformat(timespec='seconds')}",
        f"- Timezone: {timezone_name}",
    ]
    normalized_home = home_dir.strip() if home_dir is not None and home_dir.strip() else None
    normalized_workspace = (
        workspace_dir.strip()
        if workspace_dir is not None and workspace_dir.strip()
        else None
    )
    if (
        normalized_home is not None
        and normalized_workspace is not None
        and normalized_home == normalized_workspace
    ):
        lines.append(f"- Agent home / workspace: {normalized_home}")
    else:
        if normalized_home is not None:
            lines.append(f"- Agent home: {normalized_home}")
        if normalized_workspace is not None:
            lines.append(f"- Workspace: {normalized_workspace}")
    shell = os.environ.get("SHELL")
    normalized_shell = shell.strip() if shell is not None and shell.strip() else None
    if normalized_shell is not None:
        lines.append(f"- Shell: {normalized_shell}")
    command_tools = tuple(
        tool_id
        for tool_id in ("exec", "process")
        if tool_id in set(available_tool_ids)
    )
    if command_tools:
        lines.append(
            "- Local command runtime: "
            f"{', '.join(command_tools)} available via Context Tree schema enablement",
        )
    step_budget_lines = _step_budget_lines(
        current_step=current_step,
        max_steps=max_steps,
        remaining_steps=remaining_steps,
        step_budget_status=step_budget_status,
    )
    if step_budget_lines:
        lines.extend(step_budget_lines)
    lines.append("- Network access: unknown unless an enabled tool verifies it")
    lines.append("- Long-running local services: use daemon-managed services when available")
    return "\n".join(lines).strip()


def _step_budget_lines(
    *,
    current_step: int | None,
    max_steps: int | None,
    remaining_steps: int | None,
    step_budget_status: str | None,
) -> list[str]:
    if current_step is None or max_steps is None:
        return []
    normalized_remaining = (
        max(max_steps - current_step, 0)
        if remaining_steps is None
        else max(remaining_steps, 0)
    )
    normalized_status = (
        step_budget_status.strip()
        if step_budget_status is not None and step_budget_status.strip()
        else "unknown"
    )
    lines = [
        (
            "- Step budget: "
            f"{current_step}/{max_steps} used; "
            f"{normalized_remaining} remaining; status={normalized_status}"
        ),
    ]
    if normalized_status in {"finalize_now", "critical"}:
        lines.append(
            "- Step budget guidance: finish with the best supported answer now; "
            "avoid opening new exploratory branches unless they are required for the final answer."
        )
    elif normalized_status == "constrained":
        lines.append(
            "- Step budget guidance: prefer direct verification and convergence over broad exploration."
        )
    return lines
