from __future__ import annotations

from datetime import datetime


def build_runtime_context_message(
    *,
    agent_id: str,
    llm_id: str,
    home_dir: str | None,
    workdir: str | None,
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
    if home_dir is not None and workdir is not None and home_dir == workdir:
        lines.append(f"- Agent home / workdir: {home_dir}")
    else:
        if home_dir is not None and home_dir.strip():
            lines.append(f"- Agent home: {home_dir.strip()}")
        if workdir is not None and workdir.strip():
            lines.append(f"- Workdir: {workdir.strip()}")
    return "\n".join(lines).strip()
