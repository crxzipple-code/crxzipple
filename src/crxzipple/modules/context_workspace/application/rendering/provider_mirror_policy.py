from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.context_workspace.domain import ContextNode

TOOL_SCHEMA_MIRROR_MAX_COUNT = 32
TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS = 24_000


@dataclass(frozen=True, slots=True)
class ToolSurfacePolicy:
    default_schema_ids: frozenset[str] = frozenset()
    default_schema_source: str = "runtime_policy"
    default_group_refs: tuple[dict[str, str], ...] = ()
    default_group_matches: tuple[dict[str, str], ...] = ()
    default_schema_priorities: dict[str, int] = field(default_factory=dict)
    default_schema_reasons: dict[str, str] = field(default_factory=dict)
    max_count: int = TOOL_SCHEMA_MIRROR_MAX_COUNT
    max_estimated_tokens: int = TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS

    @classmethod
    def from_metadata(cls, metadata: dict[str, object]) -> "ToolSurfacePolicy":
        return cls(
            default_schema_ids=default_tool_schema_ids_from_metadata(metadata),
            default_schema_source=default_tool_schema_source_from_metadata(metadata),
            default_group_refs=default_tool_schema_group_refs_from_metadata(metadata),
            default_group_matches=default_tool_schema_group_matches_from_metadata(
                metadata,
            ),
            default_schema_priorities=default_tool_schema_priorities_from_metadata(
                metadata,
            ),
            default_schema_reasons=default_tool_schema_reasons_from_metadata(metadata),
            max_count=positive_int_from_metadata(
                metadata.get("tool_schema_mirror_max_count"),
                fallback=TOOL_SCHEMA_MIRROR_MAX_COUNT,
            ),
            max_estimated_tokens=positive_int_from_metadata(
                metadata.get("tool_schema_mirror_max_estimated_tokens"),
                fallback=TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS,
            ),
        )

    def priority_for(
        self,
        node: ContextNode,
        *,
        schema_name: str,
        enabled_by_default: bool,
    ) -> int:
        if schema_name.startswith("context_tree."):
            return 0
        tool_id = node.owner_ref.get("tool_id")
        if isinstance(tool_id, str) and tool_id.startswith("context_tree."):
            return 0
        if node.state.schema_enabled:
            return 10
        if enabled_by_default:
            for key in (schema_name, tool_id, node.id):
                if isinstance(key, str) and key in self.default_schema_priorities:
                    return self.default_schema_priorities[key]
            return 100
        return 10_000

    def reason_for(self, node: ContextNode, *, schema_name: str) -> str | None:
        tool_id = node.owner_ref.get("tool_id")
        for key in (schema_name, tool_id, node.id):
            if isinstance(key, str):
                reason = self.default_schema_reasons.get(key)
                if reason:
                    return reason
        return None

    def budget_metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "policy_kind": "tool_surface_policy",
            "max_count": self.max_count,
            "max_estimated_tokens": self.max_estimated_tokens,
        }
        if self.default_schema_ids:
            metadata["default_schema_source"] = self.default_schema_source
            metadata["default_requested_count"] = len(self.default_schema_ids)
        if self.default_group_refs:
            metadata["default_group_refs"] = [
                dict(ref) for ref in self.default_group_refs
            ]
            metadata["default_group_ref_count"] = len(self.default_group_refs)
        if self.default_group_matches:
            metadata["default_group_matches"] = [
                dict(match) for match in self.default_group_matches
            ]
            metadata["default_group_match_count"] = len(self.default_group_matches)
        if self.default_schema_priorities:
            metadata["default_schema_priorities"] = dict(
                self.default_schema_priorities,
            )
        if self.default_schema_reasons:
            metadata["default_schema_reasons"] = dict(self.default_schema_reasons)
        return metadata


def default_tool_schema_ids_from_metadata(metadata: dict[str, object]) -> frozenset[str]:
    value = metadata.get("default_tool_schema_ids")
    if isinstance(value, str):
        values: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(value)
    else:
        values = ()
    return frozenset(
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip()
    )


def default_tool_schema_source_from_metadata(metadata: dict[str, object]) -> str:
    value = metadata.get("default_tool_schema_source")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "runtime_policy"


def default_tool_schema_group_refs_from_metadata(
    metadata: dict[str, object],
) -> tuple[dict[str, str], ...]:
    value = metadata.get("default_tool_schema_group_refs")
    if not isinstance(value, (list, tuple)):
        return ()
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ref = {
            key: text
            for key in ("node_id", "source_id", "group_key", "reason")
            for text in (_metadata_text(item.get(key)),)
            if text is not None
        }
        if ref:
            refs.append(ref)
    return tuple(refs)


def default_tool_schema_group_matches_from_metadata(
    metadata: dict[str, object],
) -> tuple[dict[str, str], ...]:
    value = metadata.get("default_tool_schema_group_matches")
    if not isinstance(value, (list, tuple)):
        return ()
    matches: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        match = {
            key: text
            for key in ("node_id", "source_id", "group_key", "priority", "reason")
            for text in (_metadata_text(item.get(key)),)
            if text is not None
        }
        if match:
            matches.append(match)
    return tuple(matches)


def default_tool_schema_priorities_from_metadata(
    metadata: dict[str, object],
) -> dict[str, int]:
    value = metadata.get("default_tool_schema_priorities")
    if not isinstance(value, dict):
        return {}
    priorities: dict[str, int] = {}
    for key, raw_priority in value.items():
        text = _metadata_text(key)
        if text is None:
            continue
        priority = positive_int_from_metadata(raw_priority, fallback=0)
        if priority > 0:
            priorities[text] = priority
    return priorities


def default_tool_schema_reasons_from_metadata(
    metadata: dict[str, object],
) -> dict[str, str]:
    value = metadata.get("default_tool_schema_reasons")
    if not isinstance(value, dict):
        return {}
    reasons: dict[str, str] = {}
    for key, raw_reason in value.items():
        text = _metadata_text(key)
        reason = _metadata_text(raw_reason)
        if text is not None and reason is not None:
            reasons[text] = reason
    return reasons


def node_matches_default_tool_schema(
    node: ContextNode,
    *,
    schema_name: str,
    policy: ToolSurfacePolicy,
) -> bool:
    if not policy.default_schema_ids:
        return False
    tool_id = node.owner_ref.get("tool_id")
    return (
        schema_name in policy.default_schema_ids
        or (isinstance(tool_id, str) and tool_id in policy.default_schema_ids)
        or node.id in policy.default_schema_ids
    )


def tool_schema_mirror_priority(
    node: ContextNode,
    *,
    schema_name: str,
    enabled_by_default: bool,
    policy: ToolSurfacePolicy,
) -> int:
    return policy.priority_for(
        node,
        schema_name=schema_name,
        enabled_by_default=enabled_by_default,
    )


def positive_int_from_metadata(value: object, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value if value > 0 else fallback
    if isinstance(value, float):
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return fallback
        return parsed if parsed > 0 else fallback
    return fallback


def _metadata_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "TOOL_SCHEMA_MIRROR_MAX_COUNT",
    "TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS",
    "ToolSurfacePolicy",
    "node_matches_default_tool_schema",
    "tool_schema_mirror_priority",
]
