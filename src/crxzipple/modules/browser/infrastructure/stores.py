from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
from urllib.parse import quote

from crxzipple.modules.browser.domain import (
    BrowserStoredRef,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
)

from ..application.ports import (
    BrowserRefStore,
    BrowserRuntimeStateStore,
    BrowserSystemConfigStore,
)
from .state_root import (
    BrowserStateRoot,
    bootstrap_browser_state_root,
    ensure_browser_state_root,
    load_browser_system_config,
    persist_browser_system_config,
)


@dataclass(slots=True)
class InMemoryBrowserSystemConfigStore(BrowserSystemConfigStore):
    config: BrowserSystemConfig

    def load(self) -> BrowserSystemConfig:
        return self.config

    def save(self, config: BrowserSystemConfig) -> BrowserSystemConfig:
        self.config = config
        return self.config


@dataclass(slots=True)
class FileBackedBrowserSystemConfigStore(BrowserSystemConfigStore):
    root_dir: Path | str
    bootstrap_config: BrowserSystemConfig | None = None
    state_root: BrowserStateRoot = field(init=False)

    def __post_init__(self) -> None:
        if self.bootstrap_config is None:
            self.state_root = ensure_browser_state_root(self.root_dir)
        else:
            self.state_root = bootstrap_browser_state_root(
                self.root_dir,
                system_config=self.bootstrap_config,
            )

    def load(self) -> BrowserSystemConfig:
        config = load_browser_system_config(self.state_root)
        persist_browser_system_config(self.state_root, system_config=config)
        return config

    def save(self, config: BrowserSystemConfig) -> BrowserSystemConfig:
        self._prune_stale_profiles(config)
        persist_browser_system_config(self.state_root, system_config=config)
        return self.load()

    def _prune_stale_profiles(self, config: BrowserSystemConfig) -> None:
        valid_names = {profile.name for profile in config.profiles}

        for profile_dir in self.state_root.profiles_dir.iterdir():
            if not profile_dir.is_dir():
                continue
            if profile_dir.name not in valid_names:
                shutil.rmtree(profile_dir, ignore_errors=True)

        for runtime_path in self.state_root.runtime_dir.glob("*.json"):
            if runtime_path.stem not in valid_names:
                runtime_path.unlink(missing_ok=True)

        for ref_path in self.state_root.refs_dir.iterdir():
            candidate_name = ref_path.stem if ref_path.is_file() else ref_path.name
            if candidate_name not in valid_names:
                if ref_path.is_dir():
                    shutil.rmtree(ref_path, ignore_errors=True)
                else:
                    ref_path.unlink(missing_ok=True)


@dataclass(slots=True)
class InMemoryBrowserRuntimeStateStore(BrowserRuntimeStateStore):
    _states: dict[str, BrowserProfileRuntimeState] = field(default_factory=dict)

    def get(
        self,
        *,
        profile_name: str,
    ) -> BrowserProfileRuntimeState | None:
        state = self._states.get(profile_name)
        if state is None:
            return None
        return deepcopy(state)

    def save(self, state: BrowserProfileRuntimeState) -> None:
        self._states[state.profile_name] = deepcopy(state)

    def delete(
        self,
        *,
        profile_name: str,
    ) -> None:
        self._states.pop(profile_name, None)


@dataclass(slots=True)
class InMemoryBrowserRefStore(BrowserRefStore):
    _refs: dict[str, dict[str, tuple[BrowserStoredRef, ...]]] = field(default_factory=dict)

    def get_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> tuple[BrowserStoredRef, ...]:
        profile_refs = self._refs.get(profile_name.strip().lower(), {})
        refs = profile_refs.get(target_id.strip(), ())
        return tuple(
            BrowserStoredRef(
                ref=item.ref,
                selector=item.selector,
                scope_selector=item.scope_selector,
                uid=item.uid,
                nth=item.nth,
                generation=item.generation,
                snapshot_format=item.snapshot_format,
                frame_path=item.frame_path,
                label=item.label,
                role=item.role,
                text=item.text,
                tag=item.tag,
            )
            for item in refs
        )

    def save_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
        refs: tuple[BrowserStoredRef, ...],
    ) -> None:
        normalized_profile = profile_name.strip().lower()
        normalized_target = target_id.strip()
        self._refs.setdefault(normalized_profile, {})[normalized_target] = tuple(
            BrowserStoredRef(
                ref=item.ref,
                selector=item.selector,
                scope_selector=item.scope_selector,
                uid=item.uid,
                nth=item.nth,
                generation=item.generation,
                snapshot_format=item.snapshot_format,
                frame_path=item.frame_path,
                label=item.label,
                role=item.role,
                text=item.text,
                tag=item.tag,
            )
            for item in refs
        )

    def delete_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> None:
        normalized_profile = profile_name.strip().lower()
        profile_refs = self._refs.get(normalized_profile)
        if profile_refs is None:
            return
        profile_refs.pop(target_id.strip(), None)
        if not profile_refs:
            self._refs.pop(normalized_profile, None)

    def delete_profile_refs(
        self,
        *,
        profile_name: str,
    ) -> None:
        self._refs.pop(profile_name.strip().lower(), None)


@dataclass(slots=True)
class FileBackedBrowserRuntimeStateStore(BrowserRuntimeStateStore):
    root_dir: Path | str

    def __post_init__(self) -> None:
        root_dir = Path(self.root_dir).expanduser().resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
        self.root_dir = root_dir

    def get(
        self,
        *,
        profile_name: str,
    ) -> BrowserProfileRuntimeState | None:
        path = self._state_path(profile_name)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        metadata = payload.get("metadata")
        return BrowserProfileRuntimeState(
            profile_name=str(payload.get("profile_name", profile_name)),
            attachment_status=str(payload.get("attachment_status", "idle")),
            browser_ref=payload.get("browser_ref"),
            last_target_id=payload.get("last_target_id"),
            running_pid=payload.get("running_pid"),
            last_error=payload.get("last_error"),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def save(self, state: BrowserProfileRuntimeState) -> None:
        payload = {
            "profile_name": state.profile_name,
            "attachment_status": state.attachment_status,
            "browser_ref": state.browser_ref,
            "last_target_id": state.last_target_id,
            "running_pid": state.running_pid,
            "last_error": state.last_error,
            "metadata": dict(state.metadata),
        }
        self._state_path(state.profile_name).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def delete(
        self,
        *,
        profile_name: str,
    ) -> None:
        self._state_path(profile_name).unlink(missing_ok=True)

    def _state_path(self, profile_name: str) -> Path:
        normalized = profile_name.strip().lower()
        return Path(self.root_dir) / f"{normalized}.json"


@dataclass(slots=True)
class FileBackedBrowserRefStore(BrowserRefStore):
    root_dir: Path | str

    def __post_init__(self) -> None:
        root_dir = Path(self.root_dir).expanduser().resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
        self.root_dir = root_dir

    def get_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> tuple[BrowserStoredRef, ...]:
        path = self._tab_path(profile_name=profile_name, target_id=target_id)
        if not path.is_file():
            return ()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return ()
        raw_refs = payload.get("refs")
        if not isinstance(raw_refs, list):
            return ()
        resolved: list[BrowserStoredRef] = []
        for item in raw_refs:
            if not isinstance(item, dict):
                continue
            resolved.append(
                BrowserStoredRef(
                    ref=str(item.get("ref") or ""),
                    selector=(
                        str(item["selector"])
                        if item.get("selector") is not None
                        else None
                    ),
                    scope_selector=(
                        str(item["scope_selector"])
                        if item.get("scope_selector") is not None
                        else None
                    ),
                    uid=(
                        str(item["uid"])
                        if item.get("uid") is not None
                        else None
                    ),
                    nth=(
                        int(item["nth"])
                        if item.get("nth") is not None
                        else None
                    ),
                    generation=int(item.get("generation") or 1),
                    snapshot_format=(
                        str(item["snapshot_format"])
                        if item.get("snapshot_format") is not None
                        else None
                    ),
                    frame_path=tuple(item.get("frame_path") or ()),
                    label=(
                        str(item["label"])
                        if item.get("label") is not None
                        else None
                    ),
                    role=(
                        str(item["role"])
                        if item.get("role") is not None
                        else None
                    ),
                    text=(
                        str(item["text"])
                        if item.get("text") is not None
                        else None
                    ),
                    tag=(
                        str(item["tag"])
                        if item.get("tag") is not None
                        else None
                    ),
                )
            )
        return tuple(resolved)

    def save_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
        refs: tuple[BrowserStoredRef, ...],
    ) -> None:
        path = self._tab_path(profile_name=profile_name, target_id=target_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profile_name": profile_name.strip().lower(),
            "target_id": target_id.strip(),
            "refs": [
                    {
                        "ref": item.ref,
                        "selector": item.selector,
                        "scope_selector": item.scope_selector,
                        "uid": item.uid,
                        "nth": item.nth,
                        "generation": item.generation,
                        "snapshot_format": item.snapshot_format,
                        "frame_path": list(item.frame_path),
                        "label": item.label,
                        "role": item.role,
                    "text": item.text,
                    "tag": item.tag,
                }
                for item in refs
            ],
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def delete_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> None:
        path = self._tab_path(profile_name=profile_name, target_id=target_id)
        path.unlink(missing_ok=True)

    def delete_profile_refs(
        self,
        *,
        profile_name: str,
    ) -> None:
        profile_dir = Path(self.root_dir) / profile_name.strip().lower()
        if profile_dir.is_dir():
            shutil.rmtree(profile_dir, ignore_errors=True)

    def _tab_path(self, *, profile_name: str, target_id: str) -> Path:
        normalized_profile = profile_name.strip().lower()
        normalized_target = quote(target_id.strip(), safe="")
        return Path(self.root_dir) / normalized_profile / f"{normalized_target}.json"
