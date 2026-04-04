from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from crxzipple.modules.browser.domain import (
    BrowserProfileConfig,
    BrowserSystemConfig,
    DEFAULT_BROWSER_MCP_COMMAND,
)


@dataclass(frozen=True, slots=True)
class BrowserStateRoot:
    root_dir: Path
    config_dir: Path
    profiles_dir: Path
    runtime_dir: Path
    refs_dir: Path


def ensure_browser_state_root(
    root_dir: str | Path,
) -> BrowserStateRoot:
    root_path = Path(root_dir).expanduser().resolve()
    config_dir = root_path / "config"
    profiles_dir = root_path / "profiles"
    runtime_dir = root_path / "runtime"
    refs_dir = root_path / "refs"

    for directory in (root_path, config_dir, profiles_dir, runtime_dir, refs_dir):
        directory.mkdir(parents=True, exist_ok=True)

    _write_json(
        root_path / "layout.json",
        {
            "module": "browser",
            "layout_version": 1,
        },
    )

    return BrowserStateRoot(
        root_dir=root_path,
        config_dir=config_dir,
        profiles_dir=profiles_dir,
        runtime_dir=runtime_dir,
        refs_dir=refs_dir,
    )


def initialize_browser_state_root(
    root_dir: str | Path,
    *,
    system_config: BrowserSystemConfig,
) -> BrowserStateRoot:
    state_root = ensure_browser_state_root(root_dir)
    persist_browser_system_config(state_root, system_config=system_config)
    return state_root


def bootstrap_browser_state_root(
    root_dir: str | Path,
    *,
    system_config: BrowserSystemConfig,
) -> BrowserStateRoot:
    state_root = ensure_browser_state_root(root_dir)
    if not (state_root.config_dir / "system.json").is_file():
        persist_browser_system_config(state_root, system_config=system_config)
    return state_root


def persist_browser_system_config(
    root: BrowserStateRoot | str | Path,
    *,
    system_config: BrowserSystemConfig,
) -> BrowserStateRoot:
    state_root = (
        root if isinstance(root, BrowserStateRoot) else ensure_browser_state_root(root)
    )

    _write_json(
        state_root.config_dir / "system.json",
        {
            "default_profile": system_config.default_profile,
            "headless": system_config.headless,
            "executable_path": system_config.executable_path,
            "no_sandbox": system_config.no_sandbox,
            "managed_tab_limit": system_config.managed_tab_limit,
            "cdp_host": system_config.cdp_host,
            "cdp_port_range_start": system_config.cdp_port_range_start,
            "cdp_port_range_end": system_config.cdp_port_range_end,
            "mcp_command": list(system_config.mcp_command),
            "mcp_timeout_seconds": system_config.mcp_timeout_seconds,
            "profiles": [_profile_payload(profile) for profile in system_config.profiles],
        },
    )

    for profile in system_config.profiles:
        profile_dir = state_root.profiles_dir / profile.name
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "userdata").mkdir(parents=True, exist_ok=True)
        _write_json(
            profile_dir / "profile.json",
            _profile_payload(profile),
        )

    return state_root


def load_browser_system_config(
    root: BrowserStateRoot | str | Path,
) -> BrowserSystemConfig:
    state_root = (
        root if isinstance(root, BrowserStateRoot) else ensure_browser_state_root(root)
    )
    system_path = state_root.config_dir / "system.json"
    if not system_path.is_file():
        raise FileNotFoundError(f"Browser system config does not exist: {system_path}")

    payload = json.loads(system_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("browser system config must decode to an object.")

    payload_profiles = {
        profile.name: profile for profile in _profiles_from_system_payload(payload)
    }
    file_profiles = _load_profile_configs(state_root)
    merged_profiles = {**payload_profiles, **file_profiles}
    if merged_profiles:
        ordered_names = _ordered_profile_names(payload, merged_profiles)
        profiles = tuple(merged_profiles[name] for name in ordered_names)
    else:
        profiles = ()

    if not profiles:
        raise ValueError("browser state root must define at least one profile.")

    for profile in profiles:
        profile_dir = state_root.profiles_dir / profile.name
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "userdata").mkdir(parents=True, exist_ok=True)

    default_profile = _optional_text(payload.get("default_profile")) or profiles[0].name
    if default_profile not in {profile.name for profile in profiles}:
        default_profile = profiles[0].name

    return BrowserSystemConfig(
        default_profile=default_profile,
        profiles=profiles,
        headless=bool(payload.get("headless", False)),
        executable_path=_optional_text(payload.get("executable_path")),
        no_sandbox=bool(payload.get("no_sandbox", False)),
        managed_tab_limit=(
            int(payload["managed_tab_limit"])
            if payload.get("managed_tab_limit") is not None
            else None
        ),
        cdp_host=str(payload.get("cdp_host") or "127.0.0.1"),
        cdp_port_range_start=int(payload.get("cdp_port_range_start", 9222)),
        cdp_port_range_end=int(payload.get("cdp_port_range_end", 9322)),
        mcp_command=tuple(payload.get("mcp_command") or DEFAULT_BROWSER_MCP_COMMAND),
        mcp_timeout_seconds=int(payload.get("mcp_timeout_seconds", 30)),
    )


def _load_profile_configs(state_root: BrowserStateRoot) -> dict[str, BrowserProfileConfig]:
    profiles: dict[str, BrowserProfileConfig] = {}
    for profile_path in sorted(state_root.profiles_dir.glob("*/profile.json")):
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        profile = _profile_from_payload(payload)
        profiles[profile.name] = profile
    return profiles


def _profiles_from_system_payload(payload: dict[str, object]) -> tuple[BrowserProfileConfig, ...]:
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        return ()
    resolved: list[BrowserProfileConfig] = []
    for item in raw_profiles:
        if not isinstance(item, dict):
            continue
        resolved.append(_profile_from_payload(item))
    return tuple(resolved)


def _ordered_profile_names(
    payload: dict[str, object],
    profiles: dict[str, BrowserProfileConfig],
) -> tuple[str, ...]:
    ordered: list[str] = []
    raw_profiles = payload.get("profiles")
    if isinstance(raw_profiles, list):
        for item in raw_profiles:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name")
            if not isinstance(raw_name, str):
                continue
            name = raw_name.strip().lower()
            if name in profiles and name not in ordered:
                ordered.append(name)
    for name in sorted(profiles):
        if name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def _profile_payload(profile: BrowserProfileConfig) -> dict[str, object]:
    return {
        "name": profile.name,
        "driver": profile.driver,
        "cdp_url": profile.cdp_url,
        "cdp_port": profile.cdp_port,
        "user_data_dir": profile.user_data_dir,
        "attach_only": profile.attach_only,
    }


def _profile_from_payload(payload: dict[str, object]) -> BrowserProfileConfig:
    raw_name = payload.get("name")
    if not isinstance(raw_name, str):
        raise ValueError("browser profile payload must include a string name.")
    raw_port = payload.get("cdp_port")
    cdp_port = int(raw_port) if raw_port is not None else None
    return BrowserProfileConfig(
        name=raw_name,
        driver=str(payload.get("driver") or "managed"),  # type: ignore[arg-type]
        cdp_url=_optional_text(payload.get("cdp_url")),
        cdp_port=cdp_port,
        user_data_dir=_optional_text(payload.get("user_data_dir")),
        attach_only=bool(payload.get("attach_only", False)),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
