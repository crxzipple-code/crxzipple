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
    lines.append("- Network access: unknown unless an enabled tool verifies it")
    lines.append("- Long-running local services: use daemon-managed services when available")
    return "\n".join(lines).strip()
