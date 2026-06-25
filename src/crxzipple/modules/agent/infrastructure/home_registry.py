from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from crxzipple.modules.agent.domain.exceptions import AgentValidationError


def derive_agent_home_root(database_url: str) -> Path:
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        raw_path = database_url.removeprefix("sqlite:///").split("?", 1)[0]
        database_path = Path(raw_path).expanduser()
        if not database_path.is_absolute():
            database_path = database_path.resolve()
        return (database_path.parent / ".crxzipple" / "agents").resolve()
    return Path(".crxzipple/agents").resolve()


def list_registered_agent_homes(root_dir: str | Path) -> tuple[tuple[str, str], ...]:
    root = Path(root_dir).expanduser()
    with _registry_lock(root, shared=True):
        entries = _load_registry_entries(root)
    return tuple(sorted(entries.items()))


def resolve_registered_agent_home(
    root_dir: str | Path,
    agent_id: str,
) -> str | None:
    root = Path(root_dir).expanduser()
    with _registry_lock(root, shared=True):
        return _load_registry_entries(root).get(agent_id)


def register_agent_home(
    root_dir: str | Path,
    *,
    agent_id: str,
    home_dir: str,
) -> Path:
    root = Path(root_dir).expanduser()
    with _registry_lock(root, shared=False):
        entries = _load_registry_entries(root)
        entries[agent_id] = str(Path(home_dir).expanduser())
        return _write_registry_entries(root, entries)


def unregister_agent_home(
    root_dir: str | Path,
    *,
    agent_id: str,
) -> Path:
    root = Path(root_dir).expanduser()
    with _registry_lock(root, shared=False):
        entries = _load_registry_entries(root)
        entries.pop(agent_id, None)
        return _write_registry_entries(root, entries)


def load_registered_agent_profiles_from_root(root_dir: str | Path) -> tuple[tuple[str, str], ...]:
    root = Path(root_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    discovered: dict[str, str] = {}
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        config_path = child / "agent.json"
        if not config_path.is_file():
            continue
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
        raw_id = payload.get("id")
        if raw_id is None or not str(raw_id).strip():
            raise AgentValidationError(
                f"Agent home config '{config_path}' must define a non-empty id.",
            )
        discovered[str(raw_id).strip()] = str(child.resolve())
    return tuple(sorted(discovered.items()))


def _load_registry_entries(root_dir: str | Path) -> dict[str, str]:
    root = Path(root_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    registry_path = root / "registry.json"
    entries: dict[str, str] = {}

    if registry_path.is_file():
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AgentValidationError(
                f"Agent home registry '{registry_path}' is not valid JSON.",
            ) from exc
        if not isinstance(payload, dict):
            raise AgentValidationError(
                f"Agent home registry '{registry_path}' must contain a JSON object.",
            )
        raw_entries = payload.get("agents", {})
        if not isinstance(raw_entries, dict):
            raise AgentValidationError(
                f"Agent home registry '{registry_path}' must define an object field 'agents'.",
            )
        for agent_id, home_dir in raw_entries.items():
            normalized_id = str(agent_id).strip()
            normalized_home_dir = str(home_dir).strip()
            if normalized_id and normalized_home_dir:
                entries[normalized_id] = normalized_home_dir

    for agent_id, home_dir in load_registered_agent_profiles_from_root(root):
        entries.setdefault(agent_id, home_dir)

    return entries


def _write_registry_entries(root: Path, entries: dict[str, str]) -> Path:
    registry_path = root / "registry.json"
    payload = {
        "version": 1,
        "agents": {
            agent_id: entries[agent_id]
            for agent_id in sorted(entries)
        },
    }
    _write_text_atomically(
        registry_path,
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    )
    return registry_path


@contextmanager
def _registry_lock(root: Path, *, shared: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "registry.json.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_text_atomically(path: Path, payload: str) -> None:
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
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
