from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode


@dataclass(frozen=True, slots=True)
class RunSurfacePolicy:
    surface: str = "interactive"
    surface_contract: str = "default_open"
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
            "include_tool_schemas": self.include_tool_schemas,
            "require_tool_call": self.require_tool_call,
            "record_assistant_messages": self.record_assistant_messages,
            "record_tool_call_messages": self.record_tool_call_messages,
            "record_tool_result_messages": self.record_tool_result_messages,
            "auto_continue_inline_tools": self.auto_continue_inline_tools,
        }


def resolve_run_surface_policy(mode: RuntimeRequestMode) -> RunSurfacePolicy:
    maintenance_mode = mode in {
        RuntimeRequestMode.COMPACTION,
        RuntimeRequestMode.HEARTBEAT,
        RuntimeRequestMode.MEMORY_FLUSH,
    }
    surface = (
        "maintenance_write"
        if mode is RuntimeRequestMode.MEMORY_FLUSH
        else "maintenance"
        if maintenance_mode
        else "interactive"
    )
    surface_contract = "default_open" if surface == "interactive" else "declared_only"
    return RunSurfacePolicy(
        surface=surface,
        surface_contract=surface_contract,
        include_tool_schemas=(mode is RuntimeRequestMode.MEMORY_FLUSH or not maintenance_mode),
        require_tool_call=False,
        record_assistant_messages=mode is not RuntimeRequestMode.MEMORY_FLUSH,
        record_tool_call_messages=mode is not RuntimeRequestMode.MEMORY_FLUSH,
        record_tool_result_messages=mode is not RuntimeRequestMode.MEMORY_FLUSH,
        auto_continue_inline_tools=mode is not RuntimeRequestMode.MEMORY_FLUSH,
    )


@dataclass(frozen=True, slots=True)
class RequestRenderSnapshotReport:
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
            "estimate": _estimate_summary(self.estimate),
            "included_node_count": len(self.included_node_ids),
            "mirrored_node_count": len(self.mirrored_node_ids),
        }


@dataclass(frozen=True, slots=True)
class RuntimeRequestReport:
    mode: RuntimeRequestMode
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
    request_render_snapshot: RequestRenderSnapshotReport | None = None

    def to_payload(self) -> dict[str, object]:
        context_estimated_tokens = (
            self.request_render_snapshot.estimated_tokens(fallback=self.context_estimated_tokens)
            if self.request_render_snapshot is not None
            else self.context_estimated_tokens
        )
        payload = {
            "mode": self.mode.value,
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
        if self.request_render_snapshot is not None:
            payload["request_render_snapshot"] = self.request_render_snapshot.to_payload()
        return payload


def _estimate_summary(estimate: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "estimated_tokens",
        "text_tokens",
        "tool_schema_tokens",
        "file_tokens",
        "text_chars",
        "image_count",
        "file_count",
        "provider_attachment_count",
        "truncated",
        "status",
    ):
        value = estimate.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    breakdown = estimate.get("breakdown")
    if isinstance(breakdown, dict):
        by_kind = breakdown.get("by_kind")
        if isinstance(by_kind, dict):
            summary["kind_count"] = len(by_kind)
        by_owner = breakdown.get("by_owner")
        if isinstance(by_owner, dict):
            summary["owner_count"] = len(by_owner)
    return summary
