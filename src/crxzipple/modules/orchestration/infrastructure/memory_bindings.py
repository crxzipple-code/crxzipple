from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_BINDING_RELATIVE_PATH = Path(".state") / "memory-binding.json"


@dataclass(frozen=True, slots=True)
class AgentMemoryBinding:
    space_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "space_id", _normalize_optional_text(self.space_id))

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.space_id is not None:
            payload["space_id"] = self.space_id
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AgentMemoryBinding":
        payload = payload or {}
        return cls(
            space_id=(
                str(payload["space_id"])
                if payload.get("space_id") is not None
                else None
            ),
        )


@dataclass(slots=True)
class MemoryBindingService:
    def load(self, home_dir: str | Path) -> AgentMemoryBinding:
        sidecar_binding = _load_sidecar_binding(home_dir)
        if sidecar_binding.to_payload():
            return sidecar_binding
        payload = _load_agent_home_payload(home_dir)
        if payload is None:
            return sidecar_binding
        return binding_from_agent_home_payload(payload)

    def save(self, home_dir: str | Path, binding: AgentMemoryBinding) -> Path:
        root = Path(home_dir).expanduser()
        path = _binding_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_agent_memory_binding(binding), encoding="utf-8")
        return path

    def sidecar_files_from_runtime_preferences_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> dict[str, str]:
        return build_agent_memory_binding_sidecar_files(
            binding_from_runtime_preferences_payload(payload),
        )

    def sidecar_files_from_agent_home_payload(
        self,
        payload: dict[str, Any] | None,
    ) -> dict[str, str]:
        return build_agent_memory_binding_sidecar_files(
            binding_from_agent_home_payload(payload),
        )


def binding_from_runtime_preferences_payload(
    payload: dict[str, Any] | None,
) -> AgentMemoryBinding:
    payload = payload or {}
    return AgentMemoryBinding(
        space_id=_coerce_optional_text(payload.get("memory_space_id")),
    )


def binding_from_agent_home_payload(
    payload: dict[str, Any] | None,
) -> AgentMemoryBinding:
    payload = payload or {}
    runtime_payload = payload.get("runtime_preferences")
    runtime_payload = runtime_payload if isinstance(runtime_payload, dict) else {}
    runtime_binding = binding_from_runtime_preferences_payload(runtime_payload)
    legacy_binding = binding_from_runtime_preferences_payload(payload)
    return AgentMemoryBinding(
        space_id=runtime_binding.space_id or legacy_binding.space_id,
    )


def render_agent_memory_binding(binding: AgentMemoryBinding) -> str:
    return json.dumps(binding.to_payload(), ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def build_agent_memory_binding_sidecar_files(
    binding: AgentMemoryBinding,
) -> dict[str, str]:
    if not binding.to_payload():
        return {}
    return {
        _BINDING_RELATIVE_PATH.as_posix(): render_agent_memory_binding(binding),
    }


def load_agent_memory_binding(home_dir: str | Path) -> AgentMemoryBinding:
    return MemoryBindingService().load(home_dir)


def write_agent_memory_binding(
    home_dir: str | Path,
    binding: AgentMemoryBinding,
) -> Path:
    return MemoryBindingService().save(home_dir, binding)


def _binding_path(home_dir: str | Path) -> Path:
    return Path(home_dir).expanduser() / _BINDING_RELATIVE_PATH


def _load_sidecar_binding(home_dir: str | Path) -> AgentMemoryBinding:
    path = _binding_path(home_dir)
    if not path.exists():
        return AgentMemoryBinding()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return AgentMemoryBinding()
    if not isinstance(payload, dict):
        return AgentMemoryBinding()
    return AgentMemoryBinding.from_payload(payload)


def _load_agent_home_payload(home_dir: str | Path) -> dict[str, Any] | None:
    path = Path(home_dir).expanduser() / "agent.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _normalize_optional_text(str(value))
