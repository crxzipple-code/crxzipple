from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import shutil
from urllib.parse import quote

from crxzipple.modules.browser.domain import (
    BrowserProfileAllocation,
    BrowserProfilePool,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserSystemConfig,
)

from ..application.ports import (
    BrowserProfileAllocationStore,
    BrowserProfilePoolStore,
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
class InMemoryBrowserProfilePoolStore(BrowserProfilePoolStore):
    _pools: dict[str, BrowserProfilePool] = field(default_factory=dict)

    def list_pools(self) -> tuple[BrowserProfilePool, ...]:
        return tuple(deepcopy(self._pools[pool_id]) for pool_id in sorted(self._pools))

    def get_pool(self, *, pool_id: str) -> BrowserProfilePool | None:
        pool = self._pools.get(pool_id.strip().lower())
        if pool is None:
            return None
        return deepcopy(pool)

    def save_pool(self, pool: BrowserProfilePool) -> BrowserProfilePool:
        self._pools[pool.pool_id] = deepcopy(pool)
        return deepcopy(pool)

    def delete_pool(self, *, pool_id: str) -> None:
        self._pools.pop(pool_id.strip().lower(), None)


@dataclass(slots=True)
class FileBackedBrowserProfilePoolStore(BrowserProfilePoolStore):
    root_dir: Path | str

    def __post_init__(self) -> None:
        root_dir = Path(self.root_dir).expanduser().resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
        self.root_dir = root_dir

    def list_pools(self) -> tuple[BrowserProfilePool, ...]:
        pools: list[BrowserProfilePool] = []
        for path in sorted(Path(self.root_dir).glob("*.json")):
            pool = self._load_path(path)
            if pool is not None:
                pools.append(pool)
        return tuple(pools)

    def get_pool(self, *, pool_id: str) -> BrowserProfilePool | None:
        return self._load_path(self._pool_path(pool_id))

    def save_pool(self, pool: BrowserProfilePool) -> BrowserProfilePool:
        self._pool_path(pool.pool_id).write_text(
            json.dumps(_pool_payload(pool), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        loaded = self.get_pool(pool_id=pool.pool_id)
        return loaded or pool

    def delete_pool(self, *, pool_id: str) -> None:
        self._pool_path(pool_id).unlink(missing_ok=True)

    def _load_path(self, path: Path) -> BrowserProfilePool | None:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return _pool_from_payload(payload)

    def _pool_path(self, pool_id: str) -> Path:
        return Path(self.root_dir) / f"{pool_id.strip().lower()}.json"


@dataclass(slots=True)
class InMemoryBrowserProfileAllocationStore(BrowserProfileAllocationStore):
    _allocations: dict[str, BrowserProfileAllocation] = field(default_factory=dict)

    def list_allocations(self) -> tuple[BrowserProfileAllocation, ...]:
        return tuple(
            deepcopy(self._allocations[allocation_id])
            for allocation_id in sorted(self._allocations)
        )

    def get_allocation(
        self,
        *,
        allocation_id: str,
    ) -> BrowserProfileAllocation | None:
        allocation = self._allocations.get(allocation_id.strip())
        if allocation is None:
            return None
        return deepcopy(allocation)

    def save_allocation(
        self,
        allocation: BrowserProfileAllocation,
    ) -> BrowserProfileAllocation:
        self._allocations[allocation.allocation_id] = deepcopy(allocation)
        return deepcopy(allocation)

    def delete_allocation(self, *, allocation_id: str) -> None:
        self._allocations.pop(allocation_id.strip(), None)


@dataclass(slots=True)
class FileBackedBrowserProfileAllocationStore(BrowserProfileAllocationStore):
    root_dir: Path | str

    def __post_init__(self) -> None:
        root_dir = Path(self.root_dir).expanduser().resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
        self.root_dir = root_dir

    def list_allocations(self) -> tuple[BrowserProfileAllocation, ...]:
        allocations: list[BrowserProfileAllocation] = []
        for path in sorted(Path(self.root_dir).glob("*.json")):
            allocation = self._load_path(path)
            if allocation is not None:
                allocations.append(allocation)
        return tuple(
            sorted(
                allocations,
                key=lambda item: (item.acquired_at, item.allocation_id),
            )
        )

    def get_allocation(
        self,
        *,
        allocation_id: str,
    ) -> BrowserProfileAllocation | None:
        return self._load_path(self._allocation_path(allocation_id))

    def save_allocation(
        self,
        allocation: BrowserProfileAllocation,
    ) -> BrowserProfileAllocation:
        self._allocation_path(allocation.allocation_id).write_text(
            json.dumps(_allocation_payload(allocation), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        loaded = self.get_allocation(allocation_id=allocation.allocation_id)
        return loaded or allocation

    def delete_allocation(self, *, allocation_id: str) -> None:
        self._allocation_path(allocation_id).unlink(missing_ok=True)

    def _load_path(self, path: Path) -> BrowserProfileAllocation | None:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return _allocation_from_payload(payload)

    def _allocation_path(self, allocation_id: str) -> Path:
        return Path(self.root_dir) / f"{quote(allocation_id.strip(), safe='')}.json"


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
                frame_id=item.frame_id,
                backend_node_id=item.backend_node_id,
                bbox=dict(item.bbox) if item.bbox is not None else None,
                evidence=item.evidence,
                confidence=item.confidence,
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
                frame_id=item.frame_id,
                backend_node_id=item.backend_node_id,
                bbox=dict(item.bbox) if item.bbox is not None else None,
                evidence=item.evidence,
                confidence=item.confidence,
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
                    frame_id=(
                        str(item["frame_id"])
                        if item.get("frame_id") is not None
                        else None
                    ),
                    backend_node_id=(
                        int(item["backend_node_id"])
                        if item.get("backend_node_id") is not None
                        else None
                    ),
                    bbox=(
                        dict(item["bbox"])
                        if isinstance(item.get("bbox"), dict)
                        else None
                    ),
                    evidence=tuple(item.get("evidence") or ()),
                    confidence=(
                        float(item["confidence"])
                        if item.get("confidence") is not None
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
                    "frame_id": item.frame_id,
                    "backend_node_id": item.backend_node_id,
                    "bbox": dict(item.bbox) if item.bbox is not None else None,
                    "evidence": list(item.evidence),
                    "confidence": item.confidence,
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


def _pool_payload(pool: BrowserProfilePool) -> dict[str, object]:
    return {
        "pool_id": pool.pool_id,
        "display_name": pool.display_name,
        "enabled": pool.enabled,
        "profile_names": list(pool.profile_names),
        "target_hosts": list(pool.target_hosts),
        "selection_strategy": pool.selection_strategy,
        "max_concurrency_per_profile": pool.max_concurrency_per_profile,
        "max_concurrency_total": pool.max_concurrency_total,
        "allocation_ttl_seconds": pool.allocation_ttl_seconds,
        "cooldown_seconds": pool.cooldown_seconds,
        "failure_cooldown_seconds": pool.failure_cooldown_seconds,
        "allow_attach_only": pool.allow_attach_only,
        "close_targets_on_release": pool.close_targets_on_release,
        "close_targets_on_expire": pool.close_targets_on_expire,
        "health_policy": dict(pool.health_policy),
        "metadata": dict(pool.metadata),
    }


def _pool_from_payload(payload: dict[str, object]) -> BrowserProfilePool:
    raw_pool_id = payload.get("pool_id")
    if not isinstance(raw_pool_id, str):
        raise ValueError("browser pool payload must include a string pool_id.")
    return BrowserProfilePool(
        pool_id=raw_pool_id,
        display_name=_optional_text(payload.get("display_name")),
        enabled=bool(payload.get("enabled", True)),
        profile_names=_text_tuple(payload.get("profile_names")),
        target_hosts=_text_tuple(payload.get("target_hosts")),
        selection_strategy=str(payload.get("selection_strategy") or "least_busy"),  # type: ignore[arg-type]
        max_concurrency_per_profile=int(payload.get("max_concurrency_per_profile") or 1),
        max_concurrency_total=(
            int(payload["max_concurrency_total"])
            if payload.get("max_concurrency_total") is not None
            else None
        ),
        allocation_ttl_seconds=int(payload.get("allocation_ttl_seconds") or 900),
        cooldown_seconds=int(payload.get("cooldown_seconds") or 0),
        failure_cooldown_seconds=int(payload.get("failure_cooldown_seconds") or 300),
        allow_attach_only=bool(payload.get("allow_attach_only", False)),
        close_targets_on_release=bool(payload.get("close_targets_on_release", True)),
        close_targets_on_expire=bool(payload.get("close_targets_on_expire", True)),
        health_policy=_mapping(payload.get("health_policy")),
        metadata=_mapping(payload.get("metadata")),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list):
        return ()
    resolved: list[str] = []
    for item in value:
        text = _optional_text(item)
        if text is not None:
            resolved.append(text)
    return tuple(resolved)


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _allocation_payload(allocation: BrowserProfileAllocation) -> dict[str, object]:
    return {
        "allocation_id": allocation.allocation_id,
        "pool_id": allocation.pool_id,
        "profile_name": allocation.profile_name,
        "consumer_kind": allocation.consumer_kind,
        "consumer_id": allocation.consumer_id,
        "target_host": allocation.target_host,
        "status": allocation.status,
        "acquired_at": allocation.acquired_at.isoformat(),
        "expires_at": allocation.expires_at.isoformat(),
        "last_heartbeat_at": (
            allocation.last_heartbeat_at.isoformat()
            if allocation.last_heartbeat_at is not None
            else None
        ),
        "released_at": (
            allocation.released_at.isoformat()
            if allocation.released_at is not None
            else None
        ),
        "release_reason": allocation.release_reason,
        "owned_target_ids": list(allocation.owned_target_ids),
        "metadata": dict(allocation.metadata),
    }


def _allocation_from_payload(payload: dict[str, object]) -> BrowserProfileAllocation:
    raw_allocation_id = payload.get("allocation_id")
    if not isinstance(raw_allocation_id, str):
        raise ValueError("browser allocation payload must include a string allocation_id.")
    return BrowserProfileAllocation(
        allocation_id=raw_allocation_id,
        pool_id=str(payload.get("pool_id") or ""),
        profile_name=str(payload.get("profile_name") or ""),
        consumer_kind=str(payload.get("consumer_kind") or "manual"),  # type: ignore[arg-type]
        consumer_id=str(payload.get("consumer_id") or ""),
        target_host=_optional_text(payload.get("target_host")),
        status=str(payload.get("status") or "active"),  # type: ignore[arg-type]
        acquired_at=_datetime(payload.get("acquired_at")),
        expires_at=_datetime(payload.get("expires_at")),
        last_heartbeat_at=(
            _datetime(payload.get("last_heartbeat_at"))
            if payload.get("last_heartbeat_at") is not None
            else None
        ),
        released_at=(
            _datetime(payload.get("released_at"))
            if payload.get("released_at") is not None
            else None
        ),
        release_reason=_optional_text(payload.get("release_reason")),
        owned_target_ids=tuple(
            str(item)
            for item in (
                payload.get("owned_target_ids")
                if isinstance(payload.get("owned_target_ids"), list | tuple)
                else ()
            )
        ),
        metadata=_mapping(payload.get("metadata")),
    )


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("browser allocation datetime must be an ISO timestamp.")
    return datetime.fromisoformat(value)
