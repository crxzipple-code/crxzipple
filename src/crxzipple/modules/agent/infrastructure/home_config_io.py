from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from crxzipple.modules.agent.domain.exceptions import AgentValidationError


def load_agent_home_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise AgentValidationError(
            f"Agent home config '{config_path}' does not exist.",
        )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentValidationError(
            f"Agent home config '{config_path}' is not valid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise AgentValidationError(
            f"Agent home config '{config_path}' must contain a JSON object.",
        )
    return payload


def write_text_atomically(
    path: Path,
    payload: str,
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_path_raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_path_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


__all__ = ["load_agent_home_config", "write_text_atomically"]
