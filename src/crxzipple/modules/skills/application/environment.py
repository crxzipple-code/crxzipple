from __future__ import annotations

import os
import platform
import sys


def current_platform_tags() -> tuple[str, ...]:
    tags: list[str] = []
    _append_platform_tag(tags, sys.platform)
    _append_platform_tag(tags, platform.system())
    _append_platform_tag(tags, os.name)
    if sys.platform == "darwin":
        _append_platform_tag(tags, "macos")
        _append_platform_tag(tags, "mac")
    elif sys.platform.startswith("linux"):
        _append_platform_tag(tags, "linux")
        _append_platform_tag(tags, "posix")
    elif sys.platform.startswith(("win32", "cygwin", "msys")):
        _append_platform_tag(tags, "windows")
        _append_platform_tag(tags, "win32")
    return tuple(tags)


def unsupported_platforms(
    supported_platforms: tuple[str, ...],
    *,
    active_platform: str | None = None,
) -> tuple[str, ...]:
    supported = frozenset(_platform_aliases(*supported_platforms))
    if not supported:
        return ()
    active_values = (active_platform,) if active_platform else current_platform_tags()
    active = tuple(_platform_aliases(*active_values))
    if supported.intersection(active):
        return ()
    return (active[0] if active else "unknown",)


def _platform_aliases(*values: str | None) -> tuple[str, ...]:
    tags: list[str] = []
    for value in values:
        _append_platform_tag(tags, value)
    return tuple(tags)


def _append_platform_tag(tags: list[str], value: str | None) -> None:
    if value is None:
        return
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized:
        return
    aliases = {
        "darwin": ("darwin", "macos", "mac"),
        "mac": ("macos", "mac", "darwin"),
        "macos": ("macos", "mac", "darwin"),
        "osx": ("macos", "mac", "darwin"),
        "linux": ("linux", "posix"),
        "gnu-linux": ("linux", "posix"),
        "posix": ("posix",),
        "win": ("windows", "win32", "nt"),
        "win32": ("windows", "win32", "nt"),
        "windows": ("windows", "win32", "nt"),
        "nt": ("windows", "win32", "nt"),
    }.get(normalized, (normalized,))
    for alias in aliases:
        if alias not in tags:
            tags.append(alias)
