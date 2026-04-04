from __future__ import annotations

from pathlib import Path

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.infrastructure.home_config import render_agent_home_config


def ensure_agent_home_scaffold(profile: AgentProfile) -> None:
    # Only scaffold explicit agent homes; a legacy workspace path should not be
    # mutated into an agent home implicitly.
    home_dir = profile.runtime_preferences.home_dir
    if home_dir is None or not home_dir.strip():
        return
    root = Path(home_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)

    for relative_dir in ("memory", "skills", ".state"):
        (root / relative_dir).mkdir(parents=True, exist_ok=True)

    _write_if_missing(root / "agent.json", render_agent_home_config(profile, root=root))
    _write_if_missing(
        root / "AGENT.md",
        _build_agent_markdown(profile),
        alias_paths=(root / "AGENTS.md",),
    )
    _write_if_missing(root / "SOUL.md", _build_soul_markdown())
    _write_if_missing(root / "USER.md", _build_user_markdown())
    _write_if_missing(root / "IDENTITY.md", _build_identity_markdown(profile))
    _write_if_missing(
        root / "MEMORY.md",
        _build_memory_markdown(profile),
        alias_paths=(root / "memory.md",),
    )
    _write_if_missing(root / ".state" / "memory-binding.json", "{}\n")


def _write_if_missing(
    path: Path,
    content: str,
    *,
    alias_paths: tuple[Path, ...] = (),
) -> None:
    if path.exists() or any(alias.exists() for alias in alias_paths):
        return
    path.write_text(content, encoding="utf-8")


def _build_agent_markdown(profile: AgentProfile) -> str:
    lines = [
        "# AGENT.md",
        "",
        "## Role",
        f"- Agent ID: {profile.id}",
        f"- Name: {profile.name}",
    ]
    if profile.description:
        lines.append(f"- Purpose: {profile.description}")
    else:
        lines.append("- Purpose: Define this agent's ongoing responsibilities here.")
    lines.extend(
        [
            "",
            "## Working Rules",
            "- Follow the current user request and the runtime context.",
            "- Use tools when they are necessary and available.",
            "- Keep durable long-term facts in MEMORY.md or memory/ entries.",
            "",
        ],
    )
    return "\n".join(lines)


def _build_soul_markdown() -> str:
    return "\n".join(
        [
            "# SOUL.md",
            "",
            "- Voice:",
            "- Style:",
            "- Boundaries:",
            "",
        ],
    )


def _build_user_markdown() -> str:
    return "\n".join(
        [
            "# USER.md",
            "",
            "- Preferred address:",
            "- Preferences:",
            "- Notes:",
            "",
        ],
    )


def _build_identity_markdown(profile: AgentProfile) -> str:
    lines = [
        "# IDENTITY.md",
        "",
        f"- Agent ID: {profile.id}",
        f"- Display name: {profile.identity.display_name or profile.name}",
        f"- Theme: {profile.identity.theme or ''}",
        f"- Emoji: {profile.identity.emoji or ''}",
        f"- Avatar: {profile.identity.avatar or ''}",
        "",
    ]
    return "\n".join(lines)


def _build_memory_markdown(profile: AgentProfile) -> str:
    del profile
    return ""
