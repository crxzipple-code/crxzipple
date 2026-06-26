from __future__ import annotations

import os
from pathlib import Path

from crxzipple.core.config_env import env_flag


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AUTHORIZATION_POLICY_DIR = PROJECT_ROOT / "config" / "authorization_policies"
DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH = (
    PROJECT_ROOT / ".crxzipple" / "authorization_runtime.yaml"
)


def load_authorization_enabled() -> bool:
    return env_flag("APP_AUTHORIZATION_ENABLED", default=True)


def iter_authorization_policy_paths() -> tuple[Path, ...]:
    raw = os.getenv("APP_AUTHORIZATION_POLICY_PATHS", "").strip()
    if raw:
        configured_paths = [
            Path(part.strip()).expanduser()
            for part in raw.split(os.pathsep)
            if part.strip()
        ]
    elif DEFAULT_AUTHORIZATION_POLICY_DIR.exists():
        configured_paths = [DEFAULT_AUTHORIZATION_POLICY_DIR]
    else:
        configured_paths = []

    resolved_files: list[Path] = []
    for path in configured_paths:
        if path.is_dir():
            resolved_files.extend(
                candidate
                for pattern in ("*.yaml", "*.yml", "*.json")
                for candidate in sorted(path.glob(pattern))
                if candidate.is_file()
            )
            continue
        if path.is_file():
            resolved_files.append(path)

    unique_files: list[Path] = []
    seen: set[Path] = set()
    for path in resolved_files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(resolved)
    runtime_path = authorization_runtime_policy_path().resolve()
    if runtime_path not in seen:
        unique_files.append(runtime_path)
    return tuple(unique_files)


def authorization_runtime_policy_path() -> Path:
    raw = os.getenv("APP_AUTHORIZATION_RUNTIME_POLICY_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_AUTHORIZATION_RUNTIME_POLICY_PATH
