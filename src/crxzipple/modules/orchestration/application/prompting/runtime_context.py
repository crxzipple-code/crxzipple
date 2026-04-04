from __future__ import annotations

from datetime import datetime


def build_runtime_context_message(
    *,
    agent_id: str,
    llm_id: str,
    home_dir: str | None,
    workspace_dir: str | None,
) -> str:
    now = datetime.now().astimezone()
    lines = [
        "# Runtime Context",
        "",
        "These are runtime facts for the current turn.",
        "",
        f"- Agent: {agent_id}",
        f"- Model: {llm_id}",
        f"- Current time: {now.isoformat(timespec='seconds')}",
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
    return "\n".join(lines).strip()
