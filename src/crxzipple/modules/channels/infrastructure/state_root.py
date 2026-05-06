from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import tempfile

from typing import TypeVar

from crxzipple.modules.channels.domain import (
    ChannelInteractionRegistry,
    ChannelRuntimeRegistry,
    ChannelSystemConfig,
)

_StoreValue = TypeVar(
    "_StoreValue",
    ChannelInteractionRegistry,
    ChannelSystemConfig,
    ChannelRuntimeRegistry,
)


@dataclass(frozen=True, slots=True)
class ChannelStateRoot:
    root_dir: Path
    config_dir: Path
    runtime_dir: Path
    interactions_dir: Path


def ensure_channel_state_root(root_dir: str | Path) -> ChannelStateRoot:
    root_path = Path(root_dir).expanduser().resolve()
    config_dir = root_path / "config"
    runtime_dir = root_path / "runtime"
    interactions_dir = runtime_dir / "interactions"
    for directory in (root_path, config_dir, runtime_dir, interactions_dir):
        directory.mkdir(parents=True, exist_ok=True)
    _write_json(
        root_path / "layout.json",
        {
            "module": "channels",
            "layout_version": 1,
        },
    )
    return ChannelStateRoot(
        root_dir=root_path,
        config_dir=config_dir,
        runtime_dir=runtime_dir,
        interactions_dir=interactions_dir,
    )


def bootstrap_channel_state_root(
    root_dir: str | Path,
    *,
    system_config: ChannelSystemConfig | None = None,
    runtime_registry: ChannelRuntimeRegistry | None = None,
    interaction_registry: ChannelInteractionRegistry | None = None,
) -> ChannelStateRoot:
    state_root = ensure_channel_state_root(root_dir)
    if system_config is not None and not (state_root.config_dir / "system.json").is_file():
        persist_channel_system_config(state_root, system_config=system_config)
    if runtime_registry is not None and not (state_root.runtime_dir / "registry.json").is_file():
        persist_channel_runtime_registry(state_root, registry=runtime_registry)
    if interaction_registry is not None and not (
        state_root.interactions_dir / "registry.json"
    ).is_file():
        persist_channel_interaction_registry(
            state_root,
            registry=interaction_registry,
        )
    return state_root


def persist_channel_system_config(
    root: ChannelStateRoot | str | Path,
    *,
    system_config: ChannelSystemConfig,
) -> ChannelStateRoot:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    _write_json(
        state_root.config_dir / "system.json",
        system_config.to_payload(),
    )
    return state_root


def load_channel_system_config(
    root: ChannelStateRoot | str | Path,
) -> ChannelSystemConfig:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    path = state_root.config_dir / "system.json"
    lock_path = state_root.config_dir / "system.json.lock"
    with _file_lock(lock_path, shared=True):
        return _load_channel_system_config_unlocked(path)


def persist_channel_runtime_registry(
    root: ChannelStateRoot | str | Path,
    *,
    registry: ChannelRuntimeRegistry,
) -> ChannelStateRoot:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    _write_json(
        state_root.runtime_dir / "registry.json",
        registry.to_payload(),
    )
    return state_root


def load_channel_runtime_registry(
    root: ChannelStateRoot | str | Path,
) -> ChannelRuntimeRegistry:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    path = state_root.runtime_dir / "registry.json"
    lock_path = state_root.runtime_dir / "registry.json.lock"
    with _file_lock(lock_path, shared=True):
        return _load_channel_runtime_registry_unlocked(path)


def persist_channel_interaction_registry(
    root: ChannelStateRoot | str | Path,
    *,
    registry: ChannelInteractionRegistry,
) -> ChannelStateRoot:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    _write_json(
        state_root.interactions_dir / "registry.json",
        registry.to_payload(),
    )
    return state_root


def load_channel_interaction_registry(
    root: ChannelStateRoot | str | Path,
) -> ChannelInteractionRegistry:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    path = state_root.interactions_dir / "registry.json"
    lock_path = state_root.interactions_dir / "registry.json.lock"
    with _file_lock(lock_path, shared=True):
        return _load_channel_interaction_registry_unlocked(path)


def update_channel_system_config(
    root: ChannelStateRoot | str | Path,
    mutator: Callable[[ChannelSystemConfig], ChannelSystemConfig],
) -> ChannelSystemConfig:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    path = state_root.config_dir / "system.json"
    lock_path = state_root.config_dir / "system.json.lock"
    with _file_lock(lock_path, shared=False):
        current = _load_channel_system_config_unlocked(path)
        updated = mutator(current)
        if updated != current:
            _write_json_atomically(path, updated.to_payload())
        return _load_channel_system_config_unlocked(path)


def update_channel_runtime_registry(
    root: ChannelStateRoot | str | Path,
    mutator: Callable[[ChannelRuntimeRegistry], ChannelRuntimeRegistry],
) -> ChannelRuntimeRegistry:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    path = state_root.runtime_dir / "registry.json"
    lock_path = state_root.runtime_dir / "registry.json.lock"
    with _file_lock(lock_path, shared=False):
        current = _load_channel_runtime_registry_unlocked(path)
        updated = mutator(current)
        if updated != current:
            _write_json_atomically(path, updated.to_payload())
        return _load_channel_runtime_registry_unlocked(path)


def update_channel_interaction_registry(
    root: ChannelStateRoot | str | Path,
    mutator: Callable[[ChannelInteractionRegistry], ChannelInteractionRegistry],
) -> ChannelInteractionRegistry:
    state_root = root if isinstance(root, ChannelStateRoot) else ensure_channel_state_root(root)
    path = state_root.interactions_dir / "registry.json"
    lock_path = state_root.interactions_dir / "registry.json.lock"
    with _file_lock(lock_path, shared=False):
        current = _load_channel_interaction_registry_unlocked(path)
        updated = mutator(current)
        if updated != current:
            _write_json_atomically(path, updated.to_payload())
        return _load_channel_interaction_registry_unlocked(path)


def _load_channel_system_config_unlocked(path: Path) -> ChannelSystemConfig:
    if not path.is_file():
        return ChannelSystemConfig()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("channel system config must decode to an object.")
    return ChannelSystemConfig.from_payload(payload)


def _load_channel_runtime_registry_unlocked(path: Path) -> ChannelRuntimeRegistry:
    if not path.is_file():
        return ChannelRuntimeRegistry()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("channel runtime registry must decode to an object.")
    return ChannelRuntimeRegistry.from_payload(payload)


def _load_channel_interaction_registry_unlocked(path: Path) -> ChannelInteractionRegistry:
    if not path.is_file():
        return ChannelInteractionRegistry()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("channel interaction registry must decode to an object.")
    return ChannelInteractionRegistry.from_payload(payload)


@contextmanager
def _file_lock(path: Path, *, shared: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    lock_path = path.with_name(f"{path.name}.lock")
    with _file_lock(lock_path, shared=False):
        _write_json_atomically(path, payload)


def _write_json_atomically(path: Path, payload: dict[str, object]) -> None:
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
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
