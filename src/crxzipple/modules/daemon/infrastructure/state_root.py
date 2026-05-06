from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DaemonStateRoot:
    root_dir: Path
    config_dir: Path
    instances_dir: Path
    leases_dir: Path


def bootstrap_daemon_state_root(base_dir: str) -> DaemonStateRoot:
    root_dir = Path(base_dir).expanduser().resolve()
    config_dir = root_dir / "config"
    instances_dir = root_dir / "instances"
    leases_dir = root_dir / "leases"
    for directory in (root_dir, config_dir, instances_dir, leases_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return DaemonStateRoot(
        root_dir=root_dir,
        config_dir=config_dir,
        instances_dir=instances_dir,
        leases_dir=leases_dir,
    )
