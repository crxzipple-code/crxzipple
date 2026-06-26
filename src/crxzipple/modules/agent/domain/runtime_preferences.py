from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.agent.domain.value_common import normalize_optional_text


_REMOVED_RUNTIME_ATTR_KEYS = frozenset(
    {
        "skill_ids",
        "skills",
        "tool_ids",
        "tools",
        "memory_space",
        "memory_space_id",
    },
)


@dataclass(frozen=True, slots=True)
class AgentRuntimePreferences:
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "home_dir", normalize_optional_text(self.home_dir))
        object.__setattr__(self, "workdir", normalize_optional_text(self.workdir))
        object.__setattr__(self, "workspace", normalize_optional_text(self.workspace))
        object.__setattr__(
            self,
            "sandbox_mode",
            normalize_optional_text(self.sandbox_mode),
        )
        object.__setattr__(
            self,
            "attrs",
            {
                key: value
                for key, value in dict(self.attrs).items()
                if key not in _REMOVED_RUNTIME_ATTR_KEYS
            },
        )

    @property
    def resolved_home_dir(self) -> str | None:
        return self.home_dir

    @property
    def resolved_workdir(self) -> str | None:
        return self.workdir or self.workspace or self.home_dir

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"attrs": dict(self.attrs)}
        if self.home_dir is not None:
            payload["home_dir"] = self.home_dir
        if self.workdir is not None:
            payload["workdir"] = self.workdir
        if self.workspace is not None:
            payload["workspace"] = self.workspace
        if self.sandbox_mode is not None:
            payload["sandbox_mode"] = self.sandbox_mode
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentRuntimePreferences":
        payload = payload or {}
        return cls(
            home_dir=(
                str(payload["home_dir"])
                if payload.get("home_dir") is not None
                else None
            ),
            workdir=(
                str(payload["workdir"])
                if payload.get("workdir") is not None
                else None
            ),
            workspace=(
                str(payload["workspace"])
                if payload.get("workspace") is not None
                else None
            ),
            sandbox_mode=(
                str(payload["sandbox_mode"])
                if payload.get("sandbox_mode") is not None
                else None
            ),
            attrs=dict(payload.get("attrs", {}))
            if isinstance(payload.get("attrs"), dict)
            else {},
        )


__all__ = ["AgentRuntimePreferences"]
