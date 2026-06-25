from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)
from crxzipple.modules.operations.application.read_models.tool_run_result_payloads import (
    tool_run_result_payload,
)
from crxzipple.modules.tool.domain import ToolRun


def browser_run_label(run: ToolRun) -> str:
    if not is_browser_tool_run(run):
        return "-"
    metadata = result_metadata(run)
    profile_name = optional_metadata_text(metadata.get("profile_name"))
    if profile_name is None:
        profile_name = optional_metadata_text(run.input_payload.get("profile"))
    if profile_name is None:
        profile_name = optional_metadata_text(run.input_payload.get("profile_name"))
    pool_id = optional_metadata_text(metadata.get("browser_profile_pool"))
    if pool_id is None:
        pool_id = optional_metadata_text(run.input_payload.get("profile_pool"))
    allocation_id = optional_metadata_text(metadata.get("browser_allocation_id"))
    target_host = optional_metadata_text(metadata.get("browser_target_host"))
    parts = [profile_name or "-"]
    if pool_id is not None:
        parts.append(f"pool:{pool_id}")
    if allocation_id is not None:
        parts.append(f"alloc:{short_browser_identifier(allocation_id)}")
    if target_host is not None:
        parts.append(target_host)
    return " · ".join(parts)


def browser_profile_summary_items(run: ToolRun) -> tuple[OperationsKeyValueItemModel, ...]:
    if not is_browser_tool_run(run):
        return ()
    metadata = result_metadata(run)
    profile_name = optional_metadata_text(metadata.get("profile_name"))
    profile_source = optional_metadata_text(metadata.get("profile_source"))
    if profile_name is None:
        profile_name = optional_metadata_text(run.input_payload.get("profile"))
    if profile_name is None:
        profile_name = optional_metadata_text(run.input_payload.get("profile_name"))
    if profile_source is None and profile_name is not None:
        profile_source = input_profile_source(run) or "browser.default_profile"
    items = [
        OperationsKeyValueItemModel(
            label="Browser Profile",
            value=profile_name or "-",
        ),
        OperationsKeyValueItemModel(
            label="Profile Source",
            value=profile_source or "-",
        ),
    ]
    for label, key in (
        ("Browser Profile Pool", "browser_profile_pool"),
        ("Browser Allocation", "browser_allocation_id"),
        ("Host Service", "browser_host_service_key"),
        ("Target Host", "browser_target_host"),
        ("Host Generation", "browser_host_generation"),
        ("Target", "browser_target_id"),
        ("Page Generation", "browser_page_generation"),
        ("Snapshot Generation", "browser_snapshot_generation"),
        ("Ref Generation", "browser_current_ref_generation"),
    ):
        value = optional_metadata_text(metadata.get(key))
        if value is not None:
            items.append(OperationsKeyValueItemModel(label=label, value=value))
    return tuple(items)


def is_browser_tool_run(run: ToolRun) -> bool:
    metadata = result_metadata(run)
    result_tool = optional_metadata_text(metadata.get("tool"))
    return any(
        value.startswith("browser.")
        for value in (
            run.tool_id,
            run.function_id or "",
            run.source_id or "",
            result_tool or "",
        )
    ) or run.source_id == "bundled.local_package.browser"


def result_metadata(run: ToolRun) -> dict[str, Any]:
    payload = tool_run_result_payload(run)
    metadata = payload.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def optional_metadata_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def short_browser_identifier(value: str) -> str:
    if len(value) <= 18:
        return value
    return f"{value[:10]}...{value[-6:]}"


def input_profile_source(run: ToolRun) -> str | None:
    for key in ("profile", "profile_name"):
        if optional_metadata_text(run.input_payload.get(key)) is not None:
            return f"input.{key}"
    return None
