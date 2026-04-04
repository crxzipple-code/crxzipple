from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.agent.domain.exceptions import AgentValidationError


_VALID_MEMORY_RETRIEVAL_BACKENDS = frozenset({"keyword", "hybrid", "vector"})


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    display_name: str | None = None
    theme: str | None = None
    emoji: str | None = None
    avatar: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        if self.theme is not None:
            payload["theme"] = self.theme
        if self.emoji is not None:
            payload["emoji"] = self.emoji
        if self.avatar is not None:
            payload["avatar"] = self.avatar
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AgentIdentity":
        payload = payload or {}
        return cls(
            display_name=(
                str(payload["display_name"])
                if payload.get("display_name") is not None
                else None
            ),
            theme=str(payload["theme"]) if payload.get("theme") is not None else None,
            emoji=str(payload["emoji"]) if payload.get("emoji") is not None else None,
            avatar=str(payload["avatar"]) if payload.get("avatar") is not None else None,
        )


@dataclass(frozen=True, slots=True)
class AgentInstructionPolicy:
    system_prompt: str = ""
    response_style: str | None = None
    thinking_default: str | None = None
    stream_by_default: bool = False

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "system_prompt": self.system_prompt,
            "stream_by_default": self.stream_by_default,
        }
        if self.response_style is not None:
            payload["response_style"] = self.response_style
        if self.thinking_default is not None:
            payload["thinking_default"] = self.thinking_default
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentInstructionPolicy":
        payload = payload or {}
        return cls(
            system_prompt=str(payload.get("system_prompt", "")),
            response_style=(
                str(payload["response_style"])
                if payload.get("response_style") is not None
                else None
            ),
            thinking_default=(
                str(payload["thinking_default"])
                if payload.get("thinking_default") is not None
                else None
            ),
            stream_by_default=bool(payload.get("stream_by_default", False)),
        )


@dataclass(frozen=True, slots=True)
class AgentLlmRoutingPolicy:
    default_llm_id: str
    fallback_llm_ids: tuple[str, ...] = ()
    image_llm_id: str | None = None
    document_llm_id: str | None = None

    def __post_init__(self) -> None:
        normalized_fallbacks = tuple(
            dict.fromkeys(
                llm_id.strip()
                for llm_id in self.fallback_llm_ids
                if llm_id is not None and llm_id.strip()
            ),
        )
        object.__setattr__(self, "fallback_llm_ids", normalized_fallbacks)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "default_llm_id": self.default_llm_id,
            "fallback_llm_ids": list(self.fallback_llm_ids),
        }
        if self.image_llm_id is not None:
            payload["image_llm_id"] = self.image_llm_id
        if self.document_llm_id is not None:
            payload["document_llm_id"] = self.document_llm_id
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentLlmRoutingPolicy":
        payload = payload or {}
        return cls(
            default_llm_id=str(payload.get("default_llm_id", "")),
            fallback_llm_ids=tuple(
                str(item) for item in payload.get("fallback_llm_ids", ()) or ()
            ),
            image_llm_id=(
                str(payload["image_llm_id"])
                if payload.get("image_llm_id") is not None
                else None
            ),
            document_llm_id=(
                str(payload["document_llm_id"])
                if payload.get("document_llm_id") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class AgentExecutionPolicy:
    timeout_seconds: int = 120
    max_turns: int = 99

    def to_payload(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_turns": self.max_turns,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentExecutionPolicy":
        payload = payload or {}
        return cls(
            timeout_seconds=int(payload.get("timeout_seconds", 120)),
            max_turns=int(payload.get("max_turns", 99)),
        )


@dataclass(frozen=True, slots=True)
class AgentRuntimePreferences:
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    memory_retrieval_backend: str | None = None
    attrs: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "home_dir", _normalize_optional_text(self.home_dir))
        object.__setattr__(self, "workdir", _normalize_optional_text(self.workdir))
        object.__setattr__(self, "workspace", _normalize_optional_text(self.workspace))
        object.__setattr__(
            self,
            "sandbox_mode",
            _normalize_optional_text(self.sandbox_mode),
        )
        object.__setattr__(
            self,
            "memory_retrieval_backend",
            _normalize_memory_retrieval_backend(self.memory_retrieval_backend),
        )
        object.__setattr__(self, "attrs", dict(self.attrs))

    @property
    def resolved_home_dir(self) -> str | None:
        return self.home_dir or self.workspace

    @property
    def resolved_workdir(self) -> str | None:
        return self.workdir or self.workspace or self.home_dir

    @property
    def compat_workspace(self) -> str | None:
        return self.resolved_workdir

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
        if self.memory_retrieval_backend is not None:
            payload["memory_retrieval_backend"] = self.memory_retrieval_backend
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
            memory_retrieval_backend=(
                str(payload["memory_retrieval_backend"])
                if payload.get("memory_retrieval_backend") is not None
                else None
            ),
            attrs=dict(payload.get("attrs", {}))
            if isinstance(payload.get("attrs"), dict)
            else {},
        )


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None

def _normalize_memory_retrieval_backend(value: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized not in _VALID_MEMORY_RETRIEVAL_BACKENDS:
        raise AgentValidationError(
            f"Unsupported memory_retrieval_backend '{normalized}'.",
        )
    return normalized


@dataclass(frozen=True, slots=True)
class AgentToolPreferences:
    requested_effect_ids: tuple[str, ...] = ()
    requested_tool_ids: tuple[str, ...] = ()
    preferred_tags: tuple[str, ...] = ()
    prefers_background_tools: bool = True
    prefers_mutating_tools: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_effect_ids",
            tuple(
                dict.fromkeys(
                    item.strip()
                    for item in self.requested_effect_ids
                    if item is not None and item.strip()
                ),
            ),
        )
        object.__setattr__(
            self,
            "requested_tool_ids",
            tuple(
                dict.fromkeys(
                    item.strip()
                    for item in self.requested_tool_ids
                    if item is not None and item.strip()
                ),
            ),
        )
        object.__setattr__(
            self,
            "preferred_tags",
            tuple(
                dict.fromkeys(
                    item.strip().lower()
                    for item in self.preferred_tags
                    if item is not None and item.strip()
                ),
            ),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "requested_effect_ids": list(self.requested_effect_ids),
            "requested_tool_ids": list(self.requested_tool_ids),
            "preferred_tags": list(self.preferred_tags),
            "prefers_background_tools": self.prefers_background_tools,
            "prefers_mutating_tools": self.prefers_mutating_tools,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentToolPreferences":
        payload = payload or {}
        return cls(
            requested_effect_ids=tuple(
                str(item) for item in (payload.get("requested_effect_ids") or ())
            ),
            requested_tool_ids=tuple(
                str(item) for item in (payload.get("requested_tool_ids") or ())
            ),
            preferred_tags=tuple(
                str(item) for item in (payload.get("preferred_tags") or ())
            ),
            prefers_background_tools=bool(
                payload.get("prefers_background_tools", True),
            ),
            prefers_mutating_tools=bool(
                payload.get("prefers_mutating_tools", True),
            ),
        )
