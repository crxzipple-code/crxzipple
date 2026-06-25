from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MobileStateRoot:
    root_dir: Path
    config_dir: Path
    runtime_dir: Path
    leases_dir: Path
    refs_dir: Path


def bootstrap_mobile_state_root(base_dir: str) -> MobileStateRoot:
    root_dir = Path(base_dir).expanduser().resolve()
    config_dir = root_dir / "config"
    runtime_dir = root_dir / "runtime"
    leases_dir = root_dir / "leases"
    refs_dir = root_dir / "refs"
    for directory in (root_dir, config_dir, runtime_dir, leases_dir, refs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return MobileStateRoot(
        root_dir=root_dir,
        config_dir=config_dir,
        runtime_dir=runtime_dir,
        leases_dir=leases_dir,
        refs_dir=refs_dir,
    )
