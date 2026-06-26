from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_WORKSPACE_TOOL_DIR = PROJECT_ROOT / ".crxzipple" / "tools"
DEFAULT_BUNDLED_TOOL_DIR = PROJECT_ROOT / "tools"
DEFAULT_BROWSER_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "browser"
DEFAULT_MOBILE_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "mobile"
DEFAULT_DAEMON_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "daemon"
DEFAULT_EVENTS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "events"
DEFAULT_OPERATIONS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "operations"
DEFAULT_CHANNELS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "channels"
DEFAULT_ACCESS_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "access"
DEFAULT_MEMORY_STATE_DIR = PROJECT_ROOT / ".crxzipple" / "memory"


def load_tool_local_paths() -> tuple[str, ...]:
    configured_paths = [
        DEFAULT_WORKSPACE_TOOL_DIR,
        DEFAULT_BUNDLED_TOOL_DIR,
    ]

    unique_paths: list[str] = []
    seen: set[Path] = set()
    for path in configured_paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(str(resolved))
    return tuple(unique_paths)
