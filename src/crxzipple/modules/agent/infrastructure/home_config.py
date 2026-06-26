from __future__ import annotations

import json
import os
from pathlib import Path

from crxzipple.modules.agent.domain.entities import AgentProfile
from crxzipple.modules.agent.infrastructure.home_config_io import (
    load_agent_home_config,
    write_text_atomically,
)
from crxzipple.modules.agent.infrastructure.home_config_payloads import (
    apply_agent_home_config_payload,
    build_agent_home_config_payload,
    profile_from_agent_home_config_payload,
)


def render_agent_home_config(profile: AgentProfile, *, root: Path) -> str:
    payload = build_agent_home_config_payload(profile, root=root)
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def write_agent_home_config(profile: AgentProfile, *, home_dir: str) -> Path:
    root = Path(home_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "agent.json"
    write_text_atomically(
        path,
        render_agent_home_config(profile, root=root),
        replace=os.replace,
    )
    return path


__all__ = [
    "apply_agent_home_config_payload",
    "build_agent_home_config_payload",
    "load_agent_home_config",
    "profile_from_agent_home_config_payload",
    "render_agent_home_config",
    "write_agent_home_config",
]
