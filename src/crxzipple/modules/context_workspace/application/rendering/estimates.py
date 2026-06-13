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
        "evidence": evidence_path_breakdown(nodes),
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


def evidence_path_breakdown(nodes: tuple[ContextNode, ...]) -> dict[str, object]:
    evidence_nodes = tuple(node for node in nodes if node.kind == "session_evidence")
    browser_tool_interactions = tuple(
        node
        for node in nodes
        if node.kind == "tool_interaction"
        and (
            (_metadata_text(node.metadata.get("tool_name")) or "").startswith("browser.")
            or (_metadata_text(node.owner_ref.get("tool_name")) or "").startswith("browser.")
        )
    )
    investigation_warnings = browser_investigation_warning_refs(nodes)
    verified_paths: list[str] = []
    browser_verified_paths: list[str] = []
    unverified_paths: list[str] = []
    for node in evidence_nodes:
        facts = node.metadata.get("facts")
        if not isinstance(facts, dict):
            facts = {}
        path = _metadata_text(
            facts.get("evidence_path")
            or node.metadata.get("evidence_path")
            or node.owner_ref.get("evidence_path"),
        )
        if path is None:
            continue
        verified = (
            node.metadata.get("verified") is True
            or node.owner_ref.get("verified") is True
            or _metadata_text(node.metadata.get("evidence_lifecycle_status")) == "verified"
            or _metadata_text(node.owner_ref.get("evidence_lifecycle_status")) == "verified"
        )
        if verified:
            verified_paths.append(path)
            tool_name = _metadata_text(
                node.metadata.get("tool_name") or node.owner_ref.get("tool_name"),
            )
            if tool_name is not None and tool_name.startswith("browser."):
                browser_verified_paths.append(path)
        else:
            unverified_paths.append(path)
    verified_paths = list(dict.fromkeys(verified_paths))
    browser_verified_paths = list(dict.fromkeys(browser_verified_paths))
    unverified_paths = list(dict.fromkeys(unverified_paths))
    warning_types = list(
        dict.fromkeys(
            warning_type
            for item in investigation_warnings
            for warning_type in _metadata_text_list(item.get("warning_types"))
        ),
    )
    no_terminal_fact = bool(browser_tool_interactions) and not browser_verified_paths
    if no_terminal_fact and "evidence_path_no_terminal_fact" not in warning_types:
        warning_types.append("evidence_path_no_terminal_fact")
    return {
        "session_evidence_count": len(evidence_nodes),
        "verified_evidence_path_count": len(verified_paths),
        "verified_evidence_paths": verified_paths,
        "browser_verified_evidence_path_count": len(browser_verified_paths),
        "browser_verified_evidence_paths": browser_verified_paths,
        "unverified_evidence_paths": unverified_paths,
        "browser_tool_interaction_count": len(browser_tool_interactions),
        "browser_evidence_path_no_terminal_fact": no_terminal_fact,
        "browser_investigation_warning_count": len(investigation_warnings),
        "browser_investigation_warnings": investigation_warnings,
        "browser_investigation_warning_types": warning_types,
        "final_response_requires_evidence_path": bool(browser_verified_paths),
    }


def browser_investigation_warning_refs(
    nodes: tuple[ContextNode, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for node in nodes:
        if node.kind != "investigation_warning":
            continue
        code = _metadata_text(node.metadata.get("code") or node.owner_ref.get("code"))
        latest_tool = _metadata_text(
            node.metadata.get("latest_tool") or node.owner_ref.get("latest_tool"),
        )
        warning_types = _metadata_text_list(
            node.metadata.get("warning_types") or node.owner_ref.get("warning_types"),
        )
        if not warning_types:
            warning_types = list(
                _browser_investigation_warning_types(
                    code=code or "",
                    latest_tool=latest_tool or "",
                ),
            )
        rows.append(
            {
                "node_id": node.id,
                "code": code or "browser_investigation_warning",
                "warning_types": warning_types,
                "severity": (
                    _metadata_text(node.metadata.get("severity") or node.owner_ref.get("severity"))
                    or "warning"
                ),
                "latest_tool": latest_tool or "",
                "latest_sequence_no": _metadata_int(
                    node.metadata.get("latest_sequence_no")
                    or node.owner_ref.get("latest_sequence_no"),
                ),
                "summary": node.summary,
            },
        )
    return rows


def _browser_investigation_warning_types(
    *,
    code: str,
    latest_tool: str,
) -> tuple[str, ...]:
    if code == "browser.endpoint_candidate_not_escalated":
        return ("candidate_not_escalated",)
    if code == "browser.network_capture_no_requests":
        return ("evidence_path_no_terminal_fact",)
    if code == "browser.same_probe_repeated":
        if latest_tool in {
            "browser.script.extract_request",
            "browser.script.find_request",
            "browser.code.search",
        }:
            return ("same_script_candidate_repetition", "same_tool_repetition")
        return ("same_tool_repetition",)
    return ("browser_investigation",)


def _metadata_text_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        text = _metadata_text(value)
        return [text] if text else []
    values = [_metadata_text(item) for item in value]
    return list(dict.fromkeys(item for item in values if item is not None))


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
    "browser_investigation_warning_refs",
    "estimate_breakdown",
    "estimate_breakdown_by",
    "evidence_path_breakdown",
    "session_budget_breakdown",
    "text_estimate",
    "top_rendered_node_estimates",
    "working_plan_breakdown",
]
