from __future__ import annotations

import pytest

from crxzipple.modules.tool.application.capabilities import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
    TOOL_CAPABILITY_IDS,
    ToolCapabilityCatalog,
    ToolCapabilityRequirement,
    ToolPackageCapabilityManifest,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure import load_tool_package_plan
from crxzipple.modules.tool.application.activation import ToolDependencyBinding
from crxzipple.modules.tool.infrastructure import (
    LocalToolRuntimeRegistry,
    ToolDiscoveryRegistry,
    ToolPackageApplyContext,
    ToolRuntimeRegistry,
    apply_tool_package_plans,
)


EXPECTED_CAPABILITY_IDS = (
    "credential.read",
    "access.readiness",
    "artifact.read",
    "artifact.write",
    "bounded_network.http",
    "workspace.lookup",
    "workspace.read",
    "workspace.write",
    "process.spawn",
    "process.manage",
    "browser.profile_read",
    "browser.control",
    "browser.page_action",
    "browser.artifact_write",
    "browser.runtime_readiness",
    "runtime_settings.read",
    "mobile.device_read",
    "mobile.action",
    "mobile.screenshot",
    "memory.context_lookup",
    "memory.search",
    "memory.read",
    "memory.write",
    "memory.flush_marker",
    "session.read",
    "session.write",
    "session.tree_read",
    "session.route_enqueue",
    "session.tree_cancel",
    "run_control.yield",
    "context_workspace.read",
    "context_workspace.write",
    "context_workspace.render",
    "tool_catalog.read",
    "skill.read",
    "skill.authoring",
)


def test_default_catalog_covers_formal_tool_capabilities() -> None:
    assert DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids == EXPECTED_CAPABILITY_IDS
    assert TOOL_CAPABILITY_IDS == EXPECTED_CAPABILITY_IDS
    assert not any(
        capability_id.startswith("orchestration.")
        for capability_id in DEFAULT_TOOL_CAPABILITY_CATALOG.capability_ids
    )


def test_catalog_returns_requirement_by_capability_id() -> None:
    requirement = DEFAULT_TOOL_CAPABILITY_CATALOG.requirement_for(" workspace.read ")

    assert requirement == ToolCapabilityRequirement(
        id="workspace.read",
        label="Workspace Read",
        description="Read files under a workspace boundary.",
    )


def test_catalog_rejects_unknown_manifest_capability() -> None:
    manifest = ToolPackageCapabilityManifest(
        package_id="workspace",
        capability_ids=("workspace.read", "workspace.delete"),
    )

    with pytest.raises(ToolValidationError, match="Unknown tool capability"):
        DEFAULT_TOOL_CAPABILITY_CATALOG.validate_manifest(manifest)


def test_catalog_builds_validated_manifest_with_normalized_capabilities() -> None:
    manifest = DEFAULT_TOOL_CAPABILITY_CATALOG.manifest_for(
        package_id="workspace",
        capability_ids=(" workspace.read ", "workspace.write", "workspace.read"),
    )

    assert manifest.package_id == "workspace"
    assert manifest.capability_ids == ("workspace.read", "workspace.write")


def test_catalog_rejects_orchestration_capability_ids() -> None:
    with pytest.raises(ToolValidationError, match="not a formal capability"):
        ToolPackageCapabilityManifest(
            package_id="agent",
            capability_ids=("orchestration.run_complete",),
        )


def test_catalog_rejects_duplicate_requirement_ids() -> None:
    with pytest.raises(ToolValidationError, match="Duplicate tool capability id"):
        ToolCapabilityCatalog(
            requirements=(
                ToolCapabilityRequirement(
                    id="workspace.read",
                    label="Workspace Read",
                    description="Read workspace files.",
                ),
                ToolCapabilityRequirement(
                    id="workspace.read",
                    label="Workspace Read Again",
                    description="Read workspace files again.",
                ),
            ),
        )


def test_tool_package_manifest_parses_validated_capabilities(tmp_path) -> None:
    package_dir = tmp_path / "sample"
    package_dir.mkdir()
    manifest = package_dir / "tool.yaml"
    manifest.write_text(
        "\n".join(
            [
                "kind: local_package",
                "namespace: sample",
                "capabilities:",
                "  - workspace.read",
                "local_tools:",
                "  - id: sample_read",
                "    name: Sample Read",
                "    description: Sample read tool.",
                "    provider_name: local_system",
                "    entrypoint: tools.debug.local:echo",
                "    capabilities:",
                "      - workspace.write",
                "    parameters: []",
                "    supported_modes: [inline]",
                "    supported_strategies: [async]",
                "    supported_environments: [local]",
            ],
        ),
        encoding="utf-8",
    )

    plan = load_tool_package_plan(manifest)

    assert plan.capability_ids == ("workspace.read",)
    assert plan.local_handlers[0].capability_ids == (
        "workspace.read",
        "workspace.write",
    )
    assert plan.local_handlers[0].tool.capability_ids == (
        "workspace.read",
        "workspace.write",
    )


def test_tool_package_manifest_rejects_unknown_capability(tmp_path) -> None:
    package_dir = tmp_path / "sample"
    package_dir.mkdir()
    manifest = package_dir / "tool.yaml"
    manifest.write_text(
        "\n".join(
            [
                "kind: local_package",
                "namespace: sample",
                "capabilities:",
                "  - workspace.delete",
                "local_tools: []",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolValidationError, match="Unknown tool capability"):
        load_tool_package_plan(manifest)


def test_tool_package_activation_rejects_unavailable_target_capability(
    tmp_path,
) -> None:
    package_dir = tmp_path / "sample"
    package_dir.mkdir()
    manifest = package_dir / "tool.yaml"
    manifest.write_text(
        "\n".join(
            [
                "kind: local_package",
                "namespace: sample",
                "capabilities:",
                "  - workspace.read",
                "local_tools:",
                "  - id: sample_read",
                "    name: Sample Read",
                "    description: Sample read tool.",
                "    provider_name: local_system",
                "    entrypoint: tools.debug.local:echo",
                "    parameters: []",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolValidationError, match="unavailable tool capability"):
        apply_tool_package_plans(
            ToolPackageApplyContext(
                local_runtime_registry=LocalToolRuntimeRegistry(),
                capability_ids=("workspace.write",),
            ),
            (load_tool_package_plan(manifest),),
        )


def test_tool_package_activation_rejects_dependency_outside_declared_capability(
    tmp_path,
) -> None:
    package_dir = tmp_path / "sample"
    package_dir.mkdir()
    manifest = package_dir / "tool.yaml"
    manifest.write_text(
        "\n".join(
            [
                "kind: local_package",
                "namespace: sample",
                "capabilities:",
                "  - workspace.read",
                "dependencies:",
                "  - id: credential_provider",
                "    kind: service_dependency",
                "local_tools:",
                "  - id: sample_read",
                "    name: Sample Read",
                "    description: Sample read tool.",
                "    provider_name: local_system",
                "    entrypoint: tools.debug.local:echo",
                "    parameters: []",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolValidationError, match="bound to capabilities"):
        apply_tool_package_plans(
            ToolPackageApplyContext(
                local_runtime_registry=LocalToolRuntimeRegistry(),
                dependency_bindings={
                    "credential_provider": ToolDependencyBinding(
                        "credential_provider",
                        object(),
                        capability_ids=("credential.read",),
                    ),
                },
            ),
            (load_tool_package_plan(manifest),),
        )


def test_openapi_activation_requires_credential_dependency_binding() -> None:
    plan = load_tool_package_plan("tools/brave_search/tool.yaml")

    with pytest.raises(
        ToolValidationError,
        match="credential dependency binding 'credential_provider'",
    ):
        apply_tool_package_plans(
            ToolPackageApplyContext(
                remote_tool_registry=ToolRuntimeRegistry(),
                tool_discovery_registry=ToolDiscoveryRegistry(),
            ),
            (plan,),
        )


def test_tool_package_activation_rejects_missing_runtime_requirement(
    tmp_path,
) -> None:
    package_dir = tmp_path / "sample"
    package_dir.mkdir()
    manifest = package_dir / "tool.yaml"
    manifest.write_text(
        "\n".join(
            [
                "kind: local_package",
                "namespace: sample",
                "capabilities:",
                "  - bounded_network.http",
                "dependencies:",
                "  - id: daemon-group:sample",
                "    kind: external_requirement",
                "local_tools:",
                "  - id: sample_echo",
                "    name: Sample Echo",
                "    description: Sample echo tool.",
                "    provider_name: local_system",
                "    entrypoint: tools.debug.local:echo",
                "    parameters: []",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(ToolValidationError, match="unavailable runtime requirement"):
        apply_tool_package_plans(
            ToolPackageApplyContext(
                local_runtime_registry=LocalToolRuntimeRegistry(),
                external_requirements=(),
            ),
            (load_tool_package_plan(manifest),),
        )
