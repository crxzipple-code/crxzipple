from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.action_projection import (
    dedupe_linked_entities,
    linked_entity,
)
from crxzipple.modules.workbench.application.projection_helpers import (
    optional_text,
    truncate,
)


def missing_access_payload(run: OrchestrationRun) -> dict[str, object] | None:
    if run.error is None or run.error.code != "access_not_ready":
        return None
    return dict(run.error.details)


def failure_guidance_markdown(
    *,
    message: str,
    code: str | None,
    details: dict[str, object] | None,
) -> str:
    normalized_code = (code or "error").strip() or "error"
    normalized_message = message.strip() or "Run failed."
    guidance = failure_guidance_items(
        code=normalized_code,
        message=normalized_message,
        details=details or {},
    )
    lines = [
        "### Failure guidance",
        "",
        f"- Error code: `{normalized_code}`",
        f"- Error message: {normalized_message}",
    ]
    if guidance:
        lines.extend(["", "Recommended next steps:"])
        lines.extend(f"- {item}" for item in guidance)
    return "\n".join(lines)


def failure_guidance_items(
    *,
    code: str,
    message: str,
    details: dict[str, object],
) -> tuple[str, ...]:

    haystack = f"{code} {message}".lower()
    items: list[str] = []
    if code == "access_not_ready":
        setup_flow = details.get("access")
        setup_kind = (
            optional_text(setup_flow.get("setup_flow", {}).get("kind"))
            if isinstance(setup_flow, dict)
            and isinstance(setup_flow.get("setup_flow"), dict)
            else None
        )
        if setup_kind == "oauth_browser":
            items.append("Open Access setup and complete the OAuth browser login, then retry the run.")
        else:
            items.append("Open Access inventory and complete the missing credential setup, then retry the run.")
        resource_type = optional_text(details.get("resource_type"))
        resource_id = optional_text(details.get("resource_id"))
        if resource_type is not None and resource_id is not None:
            items.append(f"Check `{resource_type}:{resource_id}` access readiness before retrying.")
        for requirement in access_requirement_labels(details.get("access")):
            items.append(f"Required access binding: `{requirement}`.")
    elif "postgres" in haystack or "database is not reachable" in haystack:
        items.append("Start local infrastructure with `make dev-up`, then retry the run.")
        items.append("If the database was reset, run `python -m crxzipple.main db upgrade head` before retrying.")
    elif "provider" in haystack or "rate limit" in haystack or "llm" in haystack:
        items.append("Open the LLM invocation detail in Operations or Trace and check provider transport, request preview, and provider error facts.")
        items.append("Retry with a smaller model/input or wait for the provider limit window to recover if the error is rate-limit related.")
    elif "tool" in haystack:
        items.append("Open the linked ToolRun detail and inspect `result_envelope`, `read_handles`, stdout/stderr, and raw output blocks.")
        items.append("Retry after fixing the tool input, runtime access, or local environment reported by the ToolRun.")
    else:
        items.append("Open Trace for the failed step and inspect linked LLM, ToolRun, SessionItem, and response item facts.")
    if code != "access_not_ready":
        resource_type = optional_text(details.get("resource_type"))
        resource_id = optional_text(details.get("resource_id"))
        if resource_type is not None and resource_id is not None:
            items.append(f"Check `{resource_type}:{resource_id}` configuration before retrying.")
    return tuple(dict.fromkeys(items))


def missing_access_summary(payload: dict[str, object]) -> str:

    display_name = optional_text(payload.get("display_name"))
    resource_type = optional_text(payload.get("resource_type")) or "resource"
    resource_id = optional_text(payload.get("resource_id")) or "unknown"
    access_payload = payload.get("access")
    requirements = access_requirement_labels(access_payload)
    subject = display_name or f"{resource_type}:{resource_id}"
    if requirements:
        return (
            f"External access is not ready for {subject}: "
            f"{', '.join(requirements)}."
        )
    return f"External access is not ready for {subject}."


def missing_access_entities(payload: dict[str, object]) -> tuple[Any, ...]:

    entities: list[Any] = []
    resource_type = optional_text(payload.get("resource_type")) or "resource"
    resource_id = optional_text(payload.get("resource_id"))
    if resource_id is not None:
        entities.append(
            linked_entity(
                entity_type=f"{resource_type}_access",
                entity_id=resource_id,
                label=optional_text(payload.get("display_name")) or resource_id,
                owner="access",
                route="/settings/access-assets",
            ),
        )
    for requirement in access_requirement_labels(payload.get("access")):
        entities.append(
            linked_entity(
                entity_type="access_requirement",
                entity_id=requirement,
                label=requirement,
                owner="access",
                route="/settings/access-assets",
            ),
        )
    return dedupe_linked_entities(tuple(entities))


def access_requirement_labels(value: object) -> tuple[str, ...]:

    if not isinstance(value, dict):
        return ()
    labels: list[str] = []
    direct_requirement = optional_text(value.get("requirement"))
    if direct_requirement is not None:
        labels.append(direct_requirement)
    checks = value.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            requirement = optional_text(check.get("requirement"))
            if requirement is not None:
                labels.append(requirement)
    requirement_sets = value.get("requirement_sets")
    if not isinstance(requirement_sets, list):
        return tuple(dict.fromkeys(labels))
    for requirement_set in requirement_sets:
        if not isinstance(requirement_set, dict):
            continue
        checks = requirement_set.get("checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            requirement = optional_text(check.get("requirement"))
            if requirement is not None:
                labels.append(requirement)
    return tuple(dict.fromkeys(labels))


def approval_detail(payload: dict[str, object]):
    tool_arguments = approval_tool_arguments(payload.get("tool_arguments"))
    tool_name = optional_text(payload.get("tool_name"))
    draft_id = (
        optional_text(tool_arguments.get("draft_id"))
        if tool_name == "skill_draft_apply"
        else None
    )
    return models.ApprovalRequestDetail(
        request_id=str(payload.get("request_id") or payload.get("id") or ""),
        effect_id=str(payload.get("effect_id") or ""),
        label=str(payload.get("label") or ""),
        reason=str(payload.get("reason") or ""),
        tool_name=tool_name,
        tool_ids=tuple(
            str(item)
            for item in payload.get("tool_ids", ()) or ()
            if str(item).strip()
        ),
        tool_arguments=tool_arguments,
        execution_mode=optional_text(payload.get("execution_mode")),
        execution_strategy=optional_text(payload.get("execution_strategy")),
        execution_environment=optional_text(payload.get("execution_environment")),
        draft_id=draft_id,
    )


def approval_tool_arguments(value: object) -> dict[str, object]:

    if not isinstance(value, dict):
        return {}
    allowed = {"draft_id", "reason"}
    result: dict[str, object] = {}
    for key, raw in value.items():
        key_text = str(key)
        if key_text not in allowed:
            continue
        if raw is None:
            continue
        if isinstance(raw, (str, int, float, bool)):
            result[key_text] = raw
        else:
            result[key_text] = truncate(str(raw), limit=200)
    return result


def approval_entities(approval: Any | None) -> tuple[Any, ...]:

    if approval is None or not approval.draft_id:
        return ()
    return (
        linked_entity(
            entity_type="skill_draft",
            entity_id=approval.draft_id,
            label="Skill draft",
            owner="skills",
            route="/settings/skills",
        ),
    )


def approval_summary(payload: dict[str, object]) -> str:
    reason = payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    capability = payload.get("capability")
    if isinstance(capability, str) and capability.strip():
        return f"Approval is required for {capability.strip()}."
    return "Approval is required before the run can continue."
