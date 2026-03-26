from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.orchestration.application.prompting.modes import PromptMode


@dataclass(frozen=True, slots=True)
class RunSurfacePolicy:
    auto_recall_memories: bool = False
    include_memory_lookup_guidance: bool = True
    include_skills_catalog: bool = True
    include_skill_request_surface: bool = True
    include_tool_schemas: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "auto_recall_memories": self.auto_recall_memories,
            "include_memory_lookup_guidance": self.include_memory_lookup_guidance,
            "include_skills_catalog": self.include_skills_catalog,
            "include_skill_request_surface": self.include_skill_request_surface,
            "include_tool_schemas": self.include_tool_schemas,
        }


@dataclass(frozen=True, slots=True)
class PromptBlockPolicy:
    priority: int = 100
    max_tokens: int | None = None
    truncate_strategy: str = "tail"
    mode_allowlist: tuple[PromptMode, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "priority": self.priority,
            "max_tokens": self.max_tokens,
            "truncate_strategy": self.truncate_strategy,
            "mode_allowlist": [mode.value for mode in self.mode_allowlist],
        }


@dataclass(frozen=True, slots=True)
class PromptBlock:
    kind: str
    content: str
    metadata: dict[str, object] = field(default_factory=dict)
    truncated: bool = False
    policy: PromptBlockPolicy = field(default_factory=PromptBlockPolicy)


@dataclass(frozen=True, slots=True)
class PromptReportBlock:
    kind: str
    chars: int
    estimated_tokens: int
    metadata: dict[str, object] = field(default_factory=dict)
    truncated: bool = False
    policy: PromptBlockPolicy = field(default_factory=PromptBlockPolicy)

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "chars": self.chars,
            "estimated_tokens": self.estimated_tokens,
            "truncated": self.truncated,
            "metadata": dict(self.metadata),
            "policy": self.policy.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class PromptReport:
    mode: PromptMode
    system_blocks: tuple[PromptReportBlock, ...]
    system_budget_source: str
    system_budget_chars: int
    system_budget_estimated_tokens: int
    llm_context_window_tokens: int | None
    system_chars: int
    system_estimated_tokens: int
    transcript_message_count: int
    transcript_chars: int
    transcript_estimated_tokens: int

    def to_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "system_blocks": [block.to_payload() for block in self.system_blocks],
            "system_budget": {
                "source": self.system_budget_source,
                "max_chars": self.system_budget_chars,
                "max_estimated_tokens": self.system_budget_estimated_tokens,
                "llm_context_window_tokens": self.llm_context_window_tokens,
            },
            "system": {
                "chars": self.system_chars,
                "estimated_tokens": self.system_estimated_tokens,
            },
            "transcript": {
                "message_count": self.transcript_message_count,
                "chars": self.transcript_chars,
                "estimated_tokens": self.transcript_estimated_tokens,
            },
            "estimated_total_tokens": (
                self.system_estimated_tokens + self.transcript_estimated_tokens
            ),
        }
