from __future__ import annotations

from collections.abc import Callable

from crxzipple.modules.context_workspace.domain import ContextEstimate, ContextNode

from .xml_renderer import (
    node_state_label,
    render_context_node_without_descendants,
)


def text_estimate(text: str) -> ContextEstimate:
    normalized = text or ""
    return ContextEstimate(
        text_chars=len(normalized),
        text_tokens=max((len(normalized) + 3) // 4, 1) if normalized else 0,
    )


def aggregate_estimate(nodes: tuple[ContextNode, ...]) -> ContextEstimate:
    total = ContextEstimate()
    for node in nodes:
        total = total.plus(node.estimate)
    return total


def estimate_breakdown(nodes: tuple[ContextNode, ...]) -> dict[str, object]:
    return {
        "by_owner": estimate_breakdown_by(nodes, key=lambda node: node.owner),
        "by_kind": estimate_breakdown_by(nodes, key=lambda node: node.kind),
        "session": session_budget_breakdown(nodes),
        "evidence": evidence_observation_breakdown(nodes),
        "plan": working_plan_breakdown(nodes),
        "top_rendered_nodes": top_rendered_node_estimates(nodes),
    }


def estimate_breakdown_by(
    nodes: tuple[ContextNode, ...],
    *,
    key: Callable[[ContextNode], object],
) -> dict[str, dict[str, object]]:
    totals: dict[str, ContextEstimate] = {}
    for node in nodes:
        group = str(key(node) or "").strip() or "unknown"
        totals[group] = totals.get(group, ContextEstimate()).plus(node.estimate)
    return {group: estimate.to_payload() for group, estimate in sorted(totals.items())}


def top_rendered_node_estimates(
    nodes: tuple[ContextNode, ...],
    *,
    limit: int = 20,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for node in nodes:
        rendered = render_context_node_without_descendants(node)
        estimate = text_estimate(rendered)
        rows.append(
            {
                "node_id": node.id,
                "owner": node.owner,
                "kind": node.kind,
                "title": node.title,
                "state": node_state_label(node),
                "text_chars": estimate.text_chars,
                "text_tokens": estimate.text_tokens,
            },
        )
    rows.sort(
        key=lambda item: (
            int(item.get("text_chars") or 0),
            str(item.get("node_id") or ""),
        ),
        reverse=True,
    )
    return rows[: max(int(limit), 0)]


def session_budget_breakdown(nodes: tuple[ContextNode, ...]) -> dict[str, object]:
    session_nodes = tuple(node for node in nodes if node.owner == "session")
    estimate = aggregate_estimate(session_nodes)
    range_nodes = tuple(
        node for node in session_nodes if node.kind == "session_item_range"
    )
    range_notice_nodes = tuple(
        node for node in session_nodes if node.kind == "session_range_notice"
    )
    warning_count = sum(
        1
        for node in range_nodes
        if str(node.metadata.get("range_budget_status") or "") == "split_required"
    )
    blocked_count = sum(
        1
        for node in tuple(range_nodes) + range_notice_nodes
        if str(node.metadata.get("range_budget_status") or "") == "blocked"
    )
    limited_count = sum(
        1
        for node in range_notice_nodes
        if str(node.metadata.get("notice_kind") or "") == "range_limit"
    )
    return {
        **estimate.to_payload(),
        "node_count": len(session_nodes),
        "segment_node_count": sum(
            1 for node in session_nodes if node.kind == "session_segment"
        ),
        "item_node_count": sum(
            1 for node in session_nodes if node.kind == "session_item"
        ),
        "tool_interaction_count": sum(
            1 for node in session_nodes if node.kind == "tool_interaction"
        ),
        "range_node_count": len(range_nodes),
        "range_notice_count": len(range_notice_nodes),
        "range_warning_count": warning_count,
        "range_blocked_count": blocked_count,
        "range_limited_count": limited_count,
        "status": "warning" if warning_count or blocked_count or limited_count else "ok",
    }


def working_plan_breakdown(nodes: tuple[ContextNode, ...]) -> dict[str, object]:
    plan_node = next((node for node in nodes if node.id == "work.plan"), None)
    if plan_node is None:
        return {
            "present": False,
            "status": "missing",
            "plan_update_count": 0,
        }
    return {
        "present": True,
        "status": str(plan_node.metadata.get("status") or "empty"),
        "plan_state": str(plan_node.metadata.get("plan_state") or ""),
        "plan_phase": str(plan_node.metadata.get("plan_phase") or ""),
        "plan_phase_signature": str(
            plan_node.metadata.get("plan_phase_signature") or "",
        ),
        "previous_plan_phase_signature": str(
            plan_node.metadata.get("previous_plan_phase_signature") or "",
        ),
        "phase_changed": bool(plan_node.metadata.get("phase_changed")),
        "update_reason": str(plan_node.metadata.get("update_reason") or ""),
        "plan_update_count": _metadata_int(
            plan_node.metadata.get("plan_update_count"),
        ),
    }


def evidence_observation_breakdown(nodes: tuple[ContextNode, ...]) -> dict[str, object]:
    evidence_nodes = tuple(node for node in nodes if node.kind == "session_evidence")
    observed_refs: list[str] = []
    uncertain_refs: list[str] = []
    for node in evidence_nodes:
        facts = node.metadata.get("facts")
        if not isinstance(facts, dict):
            facts = {}
        evidence_ref = _metadata_text(
            facts.get("evidence_ref")
            or node.metadata.get("evidence_ref")
            or node.owner_ref.get("evidence_ref"),
        )
        if evidence_ref is None:
            continue
        observed = (
            node.metadata.get("verified") is True
            or node.owner_ref.get("verified") is True
            or _metadata_text(node.metadata.get("evidence_lifecycle_status")) == "verified"
            or _metadata_text(node.owner_ref.get("evidence_lifecycle_status")) == "verified"
        )
        if observed:
            observed_refs.append(evidence_ref)
        else:
            uncertain_refs.append(evidence_ref)
    observed_refs = list(dict.fromkeys(observed_refs))
    uncertain_refs = list(dict.fromkeys(uncertain_refs))
    return {
        "session_evidence_count": len(evidence_nodes),
        "observed_evidence_count": len(observed_refs),
        "observed_evidence_refs": observed_refs,
        "uncertain_evidence_count": len(uncertain_refs),
        "uncertain_evidence_refs": uncertain_refs,
    }


def _metadata_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _metadata_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


__all__ = [
    "aggregate_estimate",
    "estimate_breakdown",
    "estimate_breakdown_by",
    "evidence_observation_breakdown",
    "session_budget_breakdown",
    "text_estimate",
    "top_rendered_node_estimates",
    "working_plan_breakdown",
]
