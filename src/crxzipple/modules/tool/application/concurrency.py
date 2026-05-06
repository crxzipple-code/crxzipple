from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from crxzipple.modules.tool.domain.entities import Tool, ToolRun


@dataclass(frozen=True, slots=True)
class ToolRunConcurrencyGroup:
    key: str
    max_in_flight: int


@dataclass(frozen=True, slots=True)
class ToolRunConcurrencyPolicy:
    default_max_in_flight: int = 4
    image_max_in_flight: int = 4
    shared_state_max_in_flight: int = 1

    def group_for(
        self,
        *,
        run: ToolRun,
        tool: Tool | None,
    ) -> ToolRunConcurrencyGroup:
        tool_id = (tool.id if tool is not None else run.tool_id).strip().lower()
        runtime_key = (
            (tool.resolved_runtime_key() if tool is not None else run.tool_id)
            .strip()
            .lower()
        )
        tags = frozenset(tool.tags if tool is not None else ())

        if self._is_image_tool(tool_id=tool_id, runtime_key=runtime_key, tags=tags):
            return ToolRunConcurrencyGroup(
                key="capability:image",
                max_in_flight=max(int(self.image_max_in_flight), 1),
            )
        if self._is_shared_state_tool(tool_id=tool_id, runtime_key=runtime_key, tags=tags):
            return ToolRunConcurrencyGroup(
                key=f"capability:{self._shared_state_group(tool_id=tool_id, tags=tags)}",
                max_in_flight=max(int(self.shared_state_max_in_flight), 1),
            )
        return ToolRunConcurrencyGroup(
            key=f"tool:{run.tool_id}",
            max_in_flight=max(int(self.default_max_in_flight), 1),
        )

    def group_for_tool(self, tool: Tool) -> ToolRunConcurrencyGroup:
        tool_id = tool.id.strip().lower()
        runtime_key = tool.resolved_runtime_key().strip().lower()
        tags = frozenset(tool.tags)

        if self._is_image_tool(tool_id=tool_id, runtime_key=runtime_key, tags=tags):
            return ToolRunConcurrencyGroup(
                key="capability:image",
                max_in_flight=max(int(self.image_max_in_flight), 1),
            )
        if self._is_shared_state_tool(tool_id=tool_id, runtime_key=runtime_key, tags=tags):
            return ToolRunConcurrencyGroup(
                key=f"capability:{self._shared_state_group(tool_id=tool_id, tags=tags)}",
                max_in_flight=max(int(self.shared_state_max_in_flight), 1),
            )
        return ToolRunConcurrencyGroup(
            key=f"tool:{tool.id}",
            max_in_flight=max(int(self.default_max_in_flight), 1),
        )

    def can_start(
        self,
        *,
        run: ToolRun,
        tool: Tool | None,
        active_counts: Counter[str],
    ) -> bool:
        group = self.group_for(run=run, tool=tool)
        return active_counts[group.key] < group.max_in_flight

    def reserve(
        self,
        *,
        run: ToolRun,
        tool: Tool | None,
        active_counts: Counter[str],
    ) -> None:
        group = self.group_for(run=run, tool=tool)
        active_counts[group.key] += 1

    @staticmethod
    def _is_image_tool(
        *,
        tool_id: str,
        runtime_key: str,
        tags: frozenset[str],
    ) -> bool:
        return (
            "image" in tags
            and ("openai" in tags or "generation" in tags or "edit" in tags)
        ) or tool_id.startswith("openai_image_") or runtime_key.startswith("openai_image_")

    @staticmethod
    def _is_shared_state_tool(
        *,
        tool_id: str,
        runtime_key: str,
        tags: frozenset[str],
    ) -> bool:
        shared_tags = {
            "browser",
            "command",
            "filesystem",
            "mobile",
            "scope:workspace_bound",
            "scope:session_context",
            "system-managed",
            "workspace",
        }
        if tags.intersection(shared_tags):
            return True
        return tool_id.startswith(
            (
                "browser_",
                "mobile_",
                "workspace_",
                "sessions_",
            ),
        ) or runtime_key in {
            "apply_patch",
            "edit",
            "exec",
            "process",
            "read",
            "write",
        }

    @staticmethod
    def _shared_state_group(*, tool_id: str, tags: frozenset[str]) -> str:
        for tag in (
            "browser",
            "command",
            "mobile",
            "workspace",
            "scope:workspace_bound",
            "scope:session_context",
            "filesystem",
        ):
            if tag in tags:
                if tag == "scope:workspace_bound":
                    return "workspace"
                if tag == "scope:session_context":
                    return "session"
                if tag == "filesystem":
                    return "workspace"
                return tag
        for prefix, group in (
            ("browser_", "browser"),
            ("mobile_", "mobile"),
            ("workspace_", "workspace"),
            ("sessions_", "session"),
        ):
            if tool_id.startswith(prefix):
                return group
        return "system"
