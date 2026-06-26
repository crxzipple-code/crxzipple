from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
            raw_reasoning_policy=str(
                payload.get("raw_reasoning_policy", "hidden_by_default"),
            ),
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


__all__ = ["AgentLlmPolicy", "AgentLlmRoutingPolicy"]
