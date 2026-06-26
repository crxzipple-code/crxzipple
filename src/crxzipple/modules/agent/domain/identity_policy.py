from __future__ import annotations

from dataclasses import dataclass
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


__all__ = ["AgentIdentity", "AgentInstructionPolicy"]
