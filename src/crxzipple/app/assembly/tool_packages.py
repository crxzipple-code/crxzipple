"""Tool package activation assembly helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import os
from typing import Any

from crxzipple.app.keys import AppKey
from crxzipple.modules.tool.application import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
    ToolDependencyBinding,
    ToolFunctionStatus,
)
from crxzipple.modules.tool.infrastructure import (
    ToolPackageApplyContext,
    apply_tool_package_plans,
    resolve_tool_package_activations,
)


def validate_tool_package_plans(package_plans) -> None:
    resolve_tool_package_activations(
        ToolPackageApplyContext(
            capability_ids=DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids,
        ),
        package_plans,
        include_local=True,
        include_openapi=True,
        include_runtimes=True,
    )


def activate_tool_packages_from_context(ctx) -> None:
    dependency_bindings = tool_activation_bindings_from_context(
        ctx,
        ctx.require(AppKey.TOOL_CAPABILITY_BINDINGS),
    )
    activate_tool_packages(
        settings=ctx.require(AppKey.CORE_SETTINGS),
        runtime_bootstrap_config=ctx.require(AppKey.RUNTIME_BOOTSTRAP_CONFIG),
        package_plans=ctx.require(AppKey.TOOL_PACKAGE_PLANS),
        local_runtime_registry=ctx.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY),
        remote_tool_registry=ctx.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY),
        sandbox_tool_registry=ctx.require(AppKey.TOOL_SANDBOX_RUNTIME_REGISTRY),
        tool_discovery_registry=ctx.require(AppKey.TOOL_DISCOVERY_REGISTRY),
        dependency_bindings=dependency_bindings,
        local_function_refs_by_namespace=active_local_function_refs_by_namespace(ctx),
        capability_ids=ctx.require(AppKey.TOOL_CAPABILITY_CATALOG).capability_ids,
    )


def activate_tool_packages(
    *,
    settings: Any,
    runtime_bootstrap_config: Any,
    package_plans: tuple[Any, ...],
    local_runtime_registry: Any,
    remote_tool_registry: Any,
    sandbox_tool_registry: Any,
    tool_discovery_registry: Any,
    dependency_bindings: Mapping[str, ToolDependencyBinding],
    local_function_refs_by_namespace: Mapping[str, tuple[str, ...]] | None = None,
    capability_ids: tuple[str, ...] | None = None,
    include_openapi: bool | None = None,
) -> None:
    resolved_bindings = dict(dependency_bindings)
    ensure_tool_activation_binding(
        resolved_bindings,
        ToolDependencyBinding(
            "settings",
            settings,
            capability_ids=("runtime_settings.read",),
        ),
    )
    apply_tool_package_plans(
        ToolPackageApplyContext(
            local_runtime_registry=local_runtime_registry,
            remote_tool_registry=remote_tool_registry,
            sandbox_tool_registry=sandbox_tool_registry,
            tool_discovery_registry=tool_discovery_registry,
            local_function_refs_by_namespace=local_function_refs_by_namespace,
            settings=settings,
            dependency_bindings=resolved_bindings,
            config={
                "tool_remote_default_max_concurrency": (
                    runtime_bootstrap_config.tool_remote_default_max_concurrency
                ),
            },
            capability_ids=(
                capability_ids or DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids
            ),
        ),
        package_plans,
        include_openapi=(
            activate_bundled_openapi_packages()
            if include_openapi is None
            else include_openapi
        ),
    )


def active_local_function_refs_by_namespace(
    ctx,
) -> Mapping[str, tuple[str, ...]]:
    prefix = "bundled.local_package."
    refs_by_namespace: dict[str, list[str]] = {}
    for function in ctx.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).list_functions(
        status=ToolFunctionStatus.ACTIVE,
    ):
        if not function.source_id.startswith(prefix):
            continue
        namespace = function.source_id.removeprefix(prefix)
        refs_by_namespace.setdefault(namespace, []).append(function.handler_ref)
    return {
        namespace: tuple(dict.fromkeys(refs))
        for namespace, refs in refs_by_namespace.items()
    }


def ensure_tool_activation_binding(
    bindings: dict[str, ToolDependencyBinding],
    binding: ToolDependencyBinding,
) -> None:
    bindings.setdefault(binding.dependency_id, binding)


def tool_activation_bindings_from_context(
    ctx,
    base_bindings: Mapping[str, ToolDependencyBinding],
) -> Mapping[str, ToolDependencyBinding]:
    bindings = dict(base_bindings)
    ensure_tool_activation_binding(
        bindings,
        ToolDependencyBinding(
            "credential_provider",
            ctx.require(AppKey.ACCESS_SERVICE),
            capability_ids=("credential.read", "access.readiness"),
        ),
    )
    if ctx.has(AppKey.ARTIFACT_SERVICE):
        artifact_service = ctx.require(AppKey.ARTIFACT_SERVICE)
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "artifact_service",
                artifact_service,
                capability_ids=(
                    "artifact.read",
                    "artifact.write",
                    "browser.artifact_write",
                ),
            ),
        )
    if ctx.has(AppKey.BROWSER_INFRASTRUCTURE):
        browser = ctx.require(AppKey.BROWSER_INFRASTRUCTURE)
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_system_config",
                browser.system_config,
                capability_ids=("browser.profile_read", "runtime_settings.read"),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_system_config_store",
                browser.system_config_store,
                capability_ids=("browser.profile_read", "runtime_settings.read"),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_tool_application",
                browser.tool_application_service,
                capability_ids=(
                    "browser.control",
                    "browser.page_action",
                    "browser.code_read",
                ),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_observation_service",
                browser.observation_service,
                capability_ids=(
                    "browser.profile_read",
                    "browser.page_action",
                    "browser.runtime_readiness",
                ),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_profile_resolver",
                browser.profile_resolver,
                capability_ids=("browser.profile_read", "browser.runtime_readiness"),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_capabilities_resolver",
                browser.capabilities_resolver,
                capability_ids=("browser.profile_read", "browser.runtime_readiness"),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_runtime_state_store",
                browser.runtime_state_store,
                capability_ids=("browser.runtime_readiness",),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_profile_probe_service",
                browser.profile_probe_service,
                capability_ids=("browser.runtime_readiness",),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "browser_profile_allocator_service",
                browser.profile_allocator_service,
                capability_ids=("browser.profile_read", "browser.runtime_readiness"),
            ),
        )
    if ctx.has(AppKey.MOBILE_INFRASTRUCTURE):
        mobile = ctx.require(AppKey.MOBILE_INFRASTRUCTURE)
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_system_config",
                mobile.system_config,
                capability_ids=("mobile.device_read",),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_system_config_store",
                mobile.system_config_store,
                capability_ids=("mobile.device_read",),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_facade",
                mobile.facade,
                capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "mobile_result_serializer",
                mobile.result_serializer,
                capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
            ),
        )
    if ctx.has(AppKey.MEMORY_RUNTIME_SERVICE):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "memory_runtime_service",
                ctx.require(AppKey.MEMORY_RUNTIME_SERVICE),
                capability_ids=(
                    "memory.context_lookup",
                    "memory.search",
                    "memory.read",
                    "memory.write",
                    "memory.flush_marker",
                ),
            ),
        )
    if ctx.has(AppKey.PROCESS_SERVICE):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "process_service",
                ctx.require(AppKey.PROCESS_SERVICE),
                capability_ids=("process.spawn", "process.manage"),
            ),
        )
    if ctx.has(AppKey.SESSION_SERVICE):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "session_service",
                ctx.require(AppKey.SESSION_SERVICE),
                capability_ids=("session.read", "session.write", "session.tree_read"),
            ),
        )
    if ctx.has(AppKey.SESSION_WORKSPACE_LOOKUP):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "session_workspace_lookup",
                ctx.require(AppKey.SESSION_WORKSPACE_LOOKUP),
                capability_ids=("workspace.lookup", "session.read"),
            ),
        )
    if ctx.has(AppKey.SESSION_RUNTIME_CONTROL):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "session_runtime_control",
                ctx.require(AppKey.SESSION_RUNTIME_CONTROL),
                capability_ids=(
                    "session.read",
                    "session.write",
                    "session.tree_read",
                    "session.route_enqueue",
                    "session.tree_cancel",
                    "run_control.yield",
                ),
            ),
        )
    if ctx.has(AppKey.CONTEXT_TREE_SERVICE):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "context_tree_service",
                ctx.require(AppKey.CONTEXT_TREE_SERVICE),
                capability_ids=("context_workspace.read", "context_workspace.write"),
            ),
        )
    if ctx.has(AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE):
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "context_observation_snapshot_service",
                ctx.require(AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE),
                capability_ids=("context_workspace.read", "context_workspace.render"),
            ),
        )
    if ctx.has(AppKey.SKILL_MANAGER):
        skill_manager = ctx.require(AppKey.SKILL_MANAGER)
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "skill_manager",
                skill_manager,
                capability_ids=("skill.read",),
            ),
        )
        ensure_tool_activation_binding(
            bindings,
            ToolDependencyBinding(
                "skill_authoring_service",
                skill_manager,
                capability_ids=("skill.authoring",),
            ),
        )
    return bindings


def build_tool_execution_capability_bindings(
    *,
    artifact_service: Any,
    browser_infrastructure: Any,
    mobile_infrastructure: Any,
    memory_runtime_service: Any,
    process_service: Any,
    session_service: Any,
    session_workspace_lookup: Callable[[str], str | None],
    session_runtime_control: Any,
    access_service: Any,
    skill_manager: Any,
) -> Mapping[str, ToolDependencyBinding]:
    bindings = (
        ToolDependencyBinding(
            "credential_provider",
            access_service,
            capability_ids=("credential.read", "access.readiness"),
        ),
        ToolDependencyBinding(
            "artifact_service",
            artifact_service,
            capability_ids=(
                "artifact.read",
                "artifact.write",
                "browser.artifact_write",
            ),
        ),
        ToolDependencyBinding(
            "browser_system_config",
            browser_infrastructure.system_config,
            capability_ids=("browser.profile_read", "runtime_settings.read"),
        ),
        ToolDependencyBinding(
            "browser_system_config_store",
            browser_infrastructure.system_config_store,
            capability_ids=("browser.profile_read", "runtime_settings.read"),
        ),
        ToolDependencyBinding(
            "browser_tool_application",
            browser_infrastructure.tool_application_service,
            capability_ids=(
                "browser.control",
                "browser.page_action",
                "browser.code_read",
            ),
        ),
        ToolDependencyBinding(
            "browser_profile_resolver",
            browser_infrastructure.profile_resolver,
            capability_ids=("browser.profile_read", "browser.runtime_readiness"),
        ),
        ToolDependencyBinding(
            "browser_capabilities_resolver",
            browser_infrastructure.capabilities_resolver,
            capability_ids=("browser.profile_read", "browser.runtime_readiness"),
        ),
        ToolDependencyBinding(
            "browser_runtime_state_store",
            browser_infrastructure.runtime_state_store,
            capability_ids=("browser.runtime_readiness",),
        ),
        ToolDependencyBinding(
            "browser_profile_probe_service",
            browser_infrastructure.profile_probe_service,
            capability_ids=("browser.runtime_readiness",),
        ),
        ToolDependencyBinding(
            "browser_profile_allocator_service",
            browser_infrastructure.profile_allocator_service,
            capability_ids=("browser.profile_read", "browser.runtime_readiness"),
        ),
        ToolDependencyBinding(
            "mobile_system_config",
            mobile_infrastructure.system_config,
            capability_ids=("mobile.device_read",),
        ),
        ToolDependencyBinding(
            "mobile_system_config_store",
            mobile_infrastructure.system_config_store,
            capability_ids=("mobile.device_read",),
        ),
        ToolDependencyBinding(
            "mobile_facade",
            mobile_infrastructure.facade,
            capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
        ),
        ToolDependencyBinding(
            "mobile_result_serializer",
            mobile_infrastructure.result_serializer,
            capability_ids=("mobile.device_read", "mobile.action", "mobile.screenshot"),
        ),
        ToolDependencyBinding(
            "memory_runtime_service",
            memory_runtime_service,
            capability_ids=(
                "memory.context_lookup",
                "memory.search",
                "memory.read",
                "memory.write",
                "memory.flush_marker",
            ),
        ),
        ToolDependencyBinding(
            "process_service",
            process_service,
            capability_ids=("process.spawn", "process.manage"),
        ),
        ToolDependencyBinding(
            "session_service",
            session_service,
            capability_ids=("session.read", "session.write", "session.tree_read"),
        ),
        ToolDependencyBinding(
            "session_workspace_lookup",
            session_workspace_lookup,
            capability_ids=("workspace.lookup", "session.read"),
        ),
        ToolDependencyBinding(
            "session_runtime_control",
            session_runtime_control,
            capability_ids=(
                "session.read",
                "session.write",
                "session.tree_read",
                "session.route_enqueue",
                "session.tree_cancel",
                "run_control.yield",
            ),
        ),
        ToolDependencyBinding(
            "skill_manager",
            skill_manager,
            capability_ids=("skill.read",),
        ),
        ToolDependencyBinding(
            "skill_authoring_service",
            skill_manager,
            capability_ids=("skill.authoring",),
        ),
    )
    return {binding.dependency_id: binding for binding in bindings}


def activate_bundled_openapi_packages() -> bool:
    return os.getenv("APP_TOOL_OPENAPI_PROVIDER_PATHS") is None
