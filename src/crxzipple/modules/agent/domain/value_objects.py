from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    max_turns: int = 12

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
            max_turns=int(payload.get("max_turns", 12)),
        )


@dataclass(frozen=True, slots=True)
class AgentRuntimePreferences:
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "attrs", dict(self.attrs))

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"attrs": dict(self.attrs)}
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
