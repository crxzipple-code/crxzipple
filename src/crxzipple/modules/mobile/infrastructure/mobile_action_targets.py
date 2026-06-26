from __future__ import annotations

from crxzipple.modules.mobile.application.ports import MobileRefStore
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileStoredRef,
    MobileValidationError,
)

from .adb_client import AndroidAdbClient
from .adb_engine_helpers import ref_generation as _ref_generation
from .ui_node_resolution import (
    ResolvedNode,
    find_nodes_by_selector as _find_nodes_by_selector,
)


def resolve_ref(
    ref_store: MobileRefStore,
    *,
    device_name: str,
    runtime_state: MobileDeviceRuntimeState,
    ref: str,
) -> MobileStoredRef:
    generation = _ref_generation(ref)
    current_generation = runtime_state.current_ref_generation
    if current_generation is None:
        raise MobileValidationError(
            "No mobile snapshot is available. Capture a new snapshot first.",
        )
    if generation != current_generation:
        raise MobileValidationError(
            f"Mobile ref '{ref}' is stale. Capture a new snapshot before continuing.",
        )
    refs = ref_store.get_refs(device_name=device_name, generation=generation)
    normalized = ref.strip().lower()
    for item in refs:
        if item.ref == normalized:
            return item
    raise MobileValidationError(f"Mobile ref '{ref}' was not found.")


def resolve_target_node(
    ref_store: MobileRefStore,
    *,
    plan: MobileExecutionPlan,
    command: MobileActionCommand,
    runtime_state: MobileDeviceRuntimeState,
    client: AndroidAdbClient,
) -> ResolvedNode:
    if plan.device is None:
        raise MobileExecutionError("Resolved mobile device is required for mobile actions.")
    if command.target.ref:
        ref = resolve_ref(
            ref_store,
            device_name=plan.device.name,
            runtime_state=runtime_state,
            ref=command.target.ref,
        )
        return ResolvedNode(
            text=ref.text,
            content_desc=ref.content_desc,
            resource_id=ref.resource_id,
            class_name=ref.class_name,
            xpath=ref.xpath,
            bounds=ref.bounds,
            clickable=ref.clickable,
            focusable=ref.focusable,
            focused=ref.focused,
            enabled=ref.enabled,
        )
    if command.target.selector:
        matches = _find_nodes_by_selector(client.dump_ui_xml(), command.target.selector)
        if not matches:
            raise MobileValidationError(
                f"Mobile selector '{command.target.selector}' did not match any node.",
            )
        return matches[0]
    raise MobileValidationError(f"{command.kind} requires ref or selector.")


__all__ = ["resolve_ref", "resolve_target_node"]
