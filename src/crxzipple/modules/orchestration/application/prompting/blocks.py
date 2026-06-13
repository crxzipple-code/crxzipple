from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.orchestration.application.prompting.modes import PromptMode


@dataclass(frozen=True, slots=True)
class RunSurfacePolicy:
    surface: str = "interactive"
    surface_contract: str = "default_open"
    include_skills_catalog: bool = True
    include_tool_schemas: bool = True
    require_tool_call: bool = False
    record_assistant_messages: bool = True
    record_tool_call_messages: bool = True
    record_tool_result_messages: bool = True
    auto_continue_inline_tools: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "surface": self.surface,
            "surface_contract": self.surface_contract,
            "include_skills_catalog": self.include_skills_catalog,
            "include_tool_schemas": self.include_tool_schemas,
            "require_tool_call": self.require_tool_call,
            "record_assistant_messages": self.record_assistant_messages,
            "record_tool_call_messages": self.record_tool_call_messages,
            "record_tool_result_messages": self.record_tool_result_messages,
            "auto_continue_inline_tools": self.auto_continue_inline_tools,
        }


def resolve_run_surface_policy(mode: PromptMode) -> RunSurfacePolicy:
    maintenance_mode = mode in {
        PromptMode.COMPACTION,
        PromptMode.HEARTBEAT,
        PromptMode.MEMORY_FLUSH,
    }
    surface = (
        "maintenance_write"
        if mode is PromptMode.MEMORY_FLUSH
        else "maintenance"
        if maintenance_mode
        else "interactive"
    )
    surface_contract = "default_open" if surface == "interactive" else "declared_only"
    return RunSurfacePolicy(
        surface=surface,
        surface_contract=surface_contract,
        include_skills_catalog=not maintenance_mode,
        include_tool_schemas=(mode is PromptMode.MEMORY_FLUSH or not maintenance_mode),
        require_tool_call=mode is PromptMode.MEMORY_FLUSH,
        record_assistant_messages=mode is not PromptMode.MEMORY_FLUSH,
        record_tool_call_messages=mode is not PromptMode.MEMORY_FLUSH,
        record_tool_result_messages=mode is not PromptMode.MEMORY_FLUSH,
        auto_continue_inline_tools=mode is not PromptMode.MEMORY_FLUSH,
    )


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
class ContextRenderReport:
    snapshot_id: str
    estimate: dict[str, object] = field(default_factory=dict)
    included_node_ids: tuple[str, ...] = ()
    mirrored_node_ids: tuple[str, ...] = ()

    def estimated_tokens(self, *, fallback: int) -> int:
        total = 0
        for key in ("text_tokens", "tool_schema_tokens", "file_tokens"):
            value = self.estimate.get(key)
            if isinstance(value, int):
                total += max(value, 0)
        return total if total > 0 else fallback

    def to_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "estimate": dict(self.estimate),
            "included_node_ids": list(self.included_node_ids),
            "mirrored_node_ids": list(self.mirrored_node_ids),
        }


@dataclass(frozen=True, slots=True)
class PromptReport:
    mode: PromptMode
    context_blocks: tuple[PromptReportBlock, ...]
    context_budget_source: str
    context_budget_chars: int
    context_budget_estimated_tokens: int
    llm_context_window_tokens: int | None
    context_chars: int
    context_estimated_tokens: int
    transcript_message_count: int
    transcript_chars: int
    transcript_estimated_tokens: int
    transcript_tool_result_stats: dict[str, object] = field(default_factory=dict)
    transcript_budget: dict[str, object] = field(default_factory=dict)
    context_render: ContextRenderReport | None = None

    def to_payload(self) -> dict[str, object]:
        context_estimated_tokens = (
            self.context_render.estimated_tokens(fallback=self.context_estimated_tokens)
            if self.context_render is not None
            else self.context_estimated_tokens
        )
        payload = {
            "mode": self.mode.value,
            "context_blocks": [block.to_payload() for block in self.context_blocks],
            "context_budget": {
                "source": self.context_budget_source,
                "max_chars": self.context_budget_chars,
                "max_estimated_tokens": self.context_budget_estimated_tokens,
                "llm_context_window_tokens": self.llm_context_window_tokens,
            },
            "context": {
                "chars": self.context_chars,
                "estimated_tokens": self.context_estimated_tokens,
            },
            "transcript": {
                "message_count": self.transcript_message_count,
                "chars": self.transcript_chars,
                "estimated_tokens": self.transcript_estimated_tokens,
                "tool_result_stats": dict(self.transcript_tool_result_stats),
                "budget": dict(self.transcript_budget),
            },
            "estimated_total_tokens": (
                context_estimated_tokens + self.transcript_estimated_tokens
            ),
        }
        if self.context_render is not None:
            payload["context_render"] = self.context_render.to_payload()
        return payload
