from __future__ import annotations

from dataclasses import dataclass
import json

from crxzipple.modules.daemon.infrastructure.state_root import DaemonStateRoot
from crxzipple.modules.daemon.infrastructure.stores import (
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
)

_DROP_RETIRED_BROWSER_MCP_SERVICES = "0062_drop_retired_browser_mcp_services"
_RETIRED_BROWSER_MCP_PREFIX = "mcp:browser:"


@dataclass(frozen=True, slots=True)
class DaemonStateMigrationResult:
    migration_id: str
    removed_service_keys: tuple[str, ...]
    skipped: bool = False


def apply_daemon_state_migrations(
    state_root: DaemonStateRoot,
) -> tuple[DaemonStateMigrationResult, ...]:
    return (
        _drop_retired_browser_mcp_services(state_root),
    )


def _drop_retired_browser_mcp_services(
    state_root: DaemonStateRoot,
) -> DaemonStateMigrationResult:
    marker_path = (
        state_root.root_dir
        / "migrations"
        / f"{_DROP_RETIRED_BROWSER_MCP_SERVICES}.json"
    )
    if marker_path.exists():
        return DaemonStateMigrationResult(
            migration_id=_DROP_RETIRED_BROWSER_MCP_SERVICES,
            removed_service_keys=(),
            skipped=True,
        )

    spec_store = FileBackedDaemonServiceSpecStore(state_root.config_dir)
    retired_keys = tuple(
        spec.key
        for spec in spec_store.load()
        if _is_retired_browser_mcp_service_key(spec.key)
    )
    if retired_keys:
        retired_key_set = frozenset(retired_keys)
        spec_store.retire_keys(retired_keys)
        FileBackedDaemonInstanceStore(state_root.instances_dir).update(
            lambda instances: tuple(
                instance
                for instance in instances
                if instance.service_key not in retired_key_set
            ),
        )
        FileBackedDaemonLeaseStore(state_root.leases_dir).update(
            lambda leases: tuple(
                lease for lease in leases if lease.service_key not in retired_key_set
            ),
        )

    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps(
            {
                "migration_id": _DROP_RETIRED_BROWSER_MCP_SERVICES,
                "removed_service_keys": retired_keys,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return DaemonStateMigrationResult(
        migration_id=_DROP_RETIRED_BROWSER_MCP_SERVICES,
        removed_service_keys=retired_keys,
    )


def _is_retired_browser_mcp_service_key(value: str) -> bool:
    return value.strip().lower().startswith(_RETIRED_BROWSER_MCP_PREFIX)
