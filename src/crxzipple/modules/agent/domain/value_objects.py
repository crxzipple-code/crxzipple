from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.agent.domain.exceptions import AgentValidationError


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
_VALID_MEMORY_ACCESS = frozenset({"read", "read_write"})


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
class AgentLlmPolicy:
    reasoning_summary_policy: str = "visible_and_replay_when_provider_supports"
    raw_reasoning_policy: str = "hidden_by_default"
    tool_use_policy: str = "auto"
    parallel_tool_calls_policy: str = "provider_default"
    final_answer_policy: str = "phase_or_codex_unknown_fallback"
    commentary_visibility_policy: str = "user_progress"
    provider_external_item_policy: str = "history_and_trace_no_toolrun"

    def to_payload(self) -> dict[str, object]:
        return {
            "reasoning_summary_policy": self.reasoning_summary_policy,
            "raw_reasoning_policy": self.raw_reasoning_policy,
            "tool_use_policy": self.tool_use_policy,
            "parallel_tool_calls_policy": self.parallel_tool_calls_policy,
            "final_answer_policy": self.final_answer_policy,
            "commentary_visibility_policy": self.commentary_visibility_policy,
            "provider_external_item_policy": self.provider_external_item_policy,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AgentLlmPolicy":
        payload = payload or {}
        return cls(
            reasoning_summary_policy=str(
                payload.get(
                    "reasoning_summary_policy",
                    "visible_and_replay_when_provider_supports",
                ),
            ),
            raw_reasoning_policy=str(payload.get("raw_reasoning_policy", "hidden_by_default")),
            tool_use_policy=str(payload.get("tool_use_policy", "auto")),
            parallel_tool_calls_policy=str(
                payload.get("parallel_tool_calls_policy", "provider_default"),
            ),
            final_answer_policy=str(
                payload.get("final_answer_policy", "phase_or_codex_unknown_fallback"),
            ),
            commentary_visibility_policy=str(
                payload.get("commentary_visibility_policy", "user_progress"),
            ),
            provider_external_item_policy=str(
                payload.get(
                    "provider_external_item_policy",
                    "history_and_trace_no_toolrun",
                ),
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
class AgentMemoryBinding:
    enabled: bool = True
    scope_ref: str | None = None
    access: str = "read_write"

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope_ref", _normalize_optional_text(self.scope_ref))
        normalized_access = _normalize_memory_access(self.access)
        object.__setattr__(self, "access", normalized_access)

    @property
    def writable(self) -> bool:
        return self.enabled and self.access == "read_write"

    def effective_scope_ref(self, agent_id: str) -> str:
        if self.scope_ref is None or self.scope_ref == "auto":
            return agent_id
        return self.scope_ref

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": self.enabled,
            "access": self.access,
        }
        if self.scope_ref is not None:
            payload["scope_ref"] = self.scope_ref
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "AgentMemoryBinding":
        payload = payload or {}
        scope_ref = payload.get("scope_ref")
        return cls(
            enabled=_bool_value(payload.get("enabled"), default=True),
            scope_ref=str(scope_ref) if scope_ref is not None else None,
            access=str(payload.get("access") or "read_write"),
        )


@dataclass(frozen=True, slots=True)
class AgentRuntimePreferences:
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
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


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None

def _normalize_memory_access(value: str | None) -> str:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return "read_write"
    if normalized not in _VALID_MEMORY_ACCESS:
        raise AgentValidationError(
            f"Unsupported agent memory access '{normalized}'.",
        )
    return normalized


def _bool_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
