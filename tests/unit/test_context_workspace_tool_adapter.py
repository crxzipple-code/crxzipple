from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping

from tests.unit.browser_tool_package_support import (
    browser_function_catalog_candidates,
    browser_source_records_from_package,
)
from crxzipple.app.integration.context_workspace_orchestration.tool_schema_bootstrap import (
    resolve_default_tool_schema_metadata,
)
from crxzipple.app.integration.context_workspace_tool import ToolContextNodeProvider
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextSliceBuilderService,
    ContextObservationSnapshotService,
    ContextOwnerRegistry,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
    ContextObservationRenderInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextSnapshotRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.tool.application import ToolRuntimeRequestBundle, ToolRuntimeRequestBundleGroup
from crxzipple.modules.tool.domain import Tool, ToolNotFoundError, ToolParameter
from crxzipple.modules.tool.infrastructure.tool_packages import load_tool_package_plan


def test_tool_adapter_expands_only_runtime_request_tool_nodes() -> None:
    tool_service = _FakeToolService(
        Tool(
            id="fetch_weather",
            source_id="bundled.openapi.weather",
            name="Fetch Weather",
            description="Fetch current weather for a location.",
            parameters=(
                ToolParameter(
                    name="location",
                    description="Location to query.",
                    data_type="string",
                    required=True,
                ),
            ),
            required_effect_ids=("network_fetch",),
        ),
        Tool(
            id="web_search",
            name="Web Search",
            description="Search the web.",
        ),
    )
    services = _context_services(tool_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tools")
    group_nodes = [node for node in tree.nodes if node.parent_id == "tools.available"]

    assert [node.id for node in group_nodes] == [
        "tools.bundle.bundled.openapi.weather",
    ]
    assert group_nodes[0].kind == "tool_bundle"
    assert group_nodes[0].metadata["source_id"] == "bundled.openapi.weather"
    assert "semantic_group" not in group_nodes[0].metadata
    assert "capability_group" not in group_nodes[0].metadata
    assert "Contains 1 tool function" in group_nodes[0].summary

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.bundle.bundled.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tools")
    tool_nodes = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.bundled.openapi.weather"
    ]

    assert [node.id for node in tool_nodes] == ["tools.tool.fetch_weather"]
    assert tool_nodes[0].state.schema_enabled is False
    assert tool_nodes[0].metadata["schema_default_enabled"] is False
    assert "location" in tool_nodes[0].summary
    assert tool_nodes[0].metadata["required_effect_ids"] == ["network_fetch"]
    assert "provider_schema" not in tool_nodes[0].metadata


def test_tool_adapter_expands_source_runtime_request_groups_before_functions() -> None:
    tool_service = _FakeToolService(
        Tool(
            id="fetch_weather",
            source_id="configured.openapi.weather",
            name="Fetch Weather",
            description="Fetch current weather for a location.",
        ),
        Tool(
            id="geocode_location",
            source_id="configured.openapi.weather",
            name="Geocode Location",
            description="Resolve a location name to coordinates.",
        ),
        groups_by_source={
            "configured.openapi.weather": (
                ToolRuntimeRequestBundleGroup(
                    group_key="forecast",
                    title="Forecast",
                    summary="Weather forecast calls.",
                    function_ids=("fetch_weather",),
                    function_count=1,
                ),
                ToolRuntimeRequestBundleGroup(
                    group_key="lookup",
                    title="Location Lookup",
                    summary="Location lookup calls.",
                    function_ids=("geocode_location",),
                    function_count=1,
                ),
            ),
        },
    )
    services = _context_services(tool_service)
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tool-groups",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather", "geocode_location"]},
        ),
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tool-groups",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tool-groups",
            node_id="tools.bundle.configured.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tool-groups")
    group_nodes = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.configured.openapi.weather"
    ]

    assert [node.id for node in group_nodes] == [
        "tools.bundle.configured.openapi.weather.group.forecast",
        "tools.bundle.configured.openapi.weather.group.lookup",
    ]
    assert {node.kind for node in group_nodes} == {"tool_bundle_group"}
    assert all("Contains 1 tool function" in node.summary for node in group_nodes)
    assert not [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.configured.openapi.weather"
        and node.kind == "tool_function"
    ]

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tool-groups",
            node_id="tools.bundle.configured.openapi.weather.group.forecast",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tool-groups")
    forecast_children = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.configured.openapi.weather.group.forecast"
    ]

    assert [node.id for node in forecast_children] == ["tools.tool.fetch_weather"]
    assert forecast_children[0].state.schema_enabled is False


def test_enabled_tool_function_enters_context_slice_active_tools() -> None:
    tool_service = _FakeToolService(
        Tool(
            id="fetch_weather",
            source_id="configured.openapi.weather",
            name="Fetch Weather",
            description="Fetch current weather for a location.",
        ),
        Tool(
            id="geocode_location",
            source_id="configured.openapi.weather",
            name="Geocode Location",
            description="Resolve a location name to coordinates.",
        ),
        groups_by_source={
            "configured.openapi.weather": (
                ToolRuntimeRequestBundleGroup(
                    group_key="forecast",
                    title="Forecast",
                    summary="Weather forecast calls.",
                    function_ids=("fetch_weather",),
                    function_count=1,
                ),
                ToolRuntimeRequestBundleGroup(
                    group_key="lookup",
                    title="Location Lookup",
                    summary="Location lookup calls.",
                    function_ids=("geocode_location",),
                    function_count=1,
                ),
            ),
        },
    )
    services = _context_services(tool_service)
    session_key = "session:tool-active-slice"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather", "geocode_location"]},
        ),
    )
    for node_id in (
        "tools.available",
        "tools.bundle.configured.openapi.weather",
        "tools.bundle.configured.openapi.weather.group.forecast",
    ):
        services["tree"].apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=ContextAction.EXPAND,
            ),
        )

    before_slice = services["slice"].build_slice(
        session_key=session_key,
        run_id="run-tool-active-slice",
    )
    assert before_slice.active_tools == ()

    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.tool.fetch_weather",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
            run_id="run-tool-active-slice",
        ),
    )
    after_slice = services["slice"].build_slice(
        session_key=session_key,
        run_id="run-tool-active-slice",
    )

    assert [tool.function_name for tool in after_slice.active_tools] == [
        "fetch_weather",
    ]
    assert after_slice.active_tools[0].source_id == "configured.openapi.weather"
    assert after_slice.active_tools[0].owner_ref["tool_id"] == "fetch_weather"
    assert after_slice.active_tools[0].metadata["status"] == "available"


def test_browser_source_runtime_request_groups_surface_in_context_tree() -> None:
    source = browser_source_records_from_package()[0]
    candidates = browser_function_catalog_candidates()
    groups = _runtime_request_groups_from_browser_source(source.config["runtime_request"]["groups"])
    tool_service = _FakeToolService(
        *(_tool_from_browser_candidate(candidate) for candidate in candidates),
        groups_by_source={source.source_id: groups},
        summary_by_source={
            source.source_id: str(source.config["runtime_request"]["summary"]),
        },
        metadata_by_source={
            source.source_id: {"runtime_request": dict(source.config["runtime_request"])},
        },
    )
    services = _context_services(tool_service)
    session_key = "session:browser-groups"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={
                "available_tool_names": [candidate.function_id for candidate in candidates],
            },
        ),
    )
    initial_render = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )

    assert "not just a DOM snapshot tool" in initial_render.debug_body
    assert "verifiable browser facts" in initial_render.debug_body
    assert "Avoid repeated tab inventory" in initial_render.debug_body
    assert "Browser Observation" not in initial_render.debug_body

    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree(session_key)
    bundle_nodes = [node for node in tree.nodes if node.parent_id == "tools.available"]

    assert [node.id for node in bundle_nodes] == ["tools.bundle.bundled.local_package.browser"]
    assert bundle_nodes[0].kind == "tool_bundle"
    assert bundle_nodes[0].state.collapsed is True
    assert bundle_nodes[0].metadata["source_id"] == "bundled.local_package.browser"
    bundle_prompt = bundle_nodes[0].metadata["runtime_request"]
    assert bundle_prompt["default_tool_schema_policy"] == {"priority": 20}
    assert bundle_prompt["default_tool_schema_group_refs"][0]["source_id"] == (
        "bundled.local_package.browser"
    )

    default_services = _context_services(tool_service)
    default_session_key = "session:browser-defaults"
    default_services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=default_session_key,
            agent_id="assistant",
            metadata={
                "available_tool_names": [candidate.function_id for candidate in candidates],
            },
        ),
    )
    source_default_metadata = resolve_default_tool_schema_metadata(
        tree_service=default_services["tree"],
        session_key=default_session_key,
        run_id="run-browser-defaults",
        draft=SimpleNamespace(flow_hint={}),  # type: ignore[arg-type]
    )
    assert source_default_metadata == {}
    browser_bootstrap_refs = [
        {
            "source_id": "bundled.local_package.browser",
            "group_key": "navigation",
            "reason": "test_browser_navigation",
        },
        {
            "source_id": "bundled.local_package.browser",
            "group_key": "observation",
            "reason": "test_browser_observation",
        },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "action_trace",
                "reason": "test_browser_action_trace",
            },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "native_script",
                "reason": "test_browser_native_script",
            },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "page_interaction",
                "reason": "test_browser_page_interaction",
            },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "forms_overlays",
                "reason": "test_browser_forms_overlays",
            },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "dom_inspection",
                "reason": "test_browser_dom_inspection",
            },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "network",
                "reason": "test_browser_network",
            },
            {
                "source_id": "bundled.local_package.browser",
                "group_key": "code_insight",
                "reason": "test_browser_code_insight",
            },
        ]
    default_metadata = resolve_default_tool_schema_metadata(
        tree_service=default_services["tree"],
        session_key=default_session_key,
        run_id="run-browser-defaults",
        draft=SimpleNamespace(
            flow_hint={"default_tool_schema_group_refs": browser_bootstrap_refs},
        ),  # type: ignore[arg-type]
    )
    default_group_refs = default_metadata["default_tool_schema_group_refs"]
    assert [
        {
            "source_id": ref["source_id"],
            "group_key": ref["group_key"],
            "reason": ref["reason"],
        }
        for ref in default_group_refs
    ] == browser_bootstrap_refs
    assert "browser.network.inspect" in default_metadata["default_tool_schema_ids"]
    assert "browser.runtime.inspect" in default_metadata["default_tool_schema_ids"]
    assert "browser.script.extract_request" in default_metadata["default_tool_schema_ids"]
    assert "browser.runtime.probe_client" not in default_metadata["default_tool_schema_ids"]
    assert "browser.runtime.call_client" not in default_metadata["default_tool_schema_ids"]
    assert "browser.evaluate" in default_metadata["default_tool_schema_ids"]
    assert "browser.action.trace" in default_metadata["default_tool_schema_ids"]
    assert "browser.native.run" in default_metadata["default_tool_schema_ids"]
    assert "browser.click" in default_metadata["default_tool_schema_ids"]
    assert "browser.type" in default_metadata["default_tool_schema_ids"]
    assert "browser.form.inspect" in default_metadata["default_tool_schema_ids"]
    assert "browser.dom.inspect" in default_metadata["default_tool_schema_ids"]
    assert "browser.tabs.list" not in default_metadata["default_tool_schema_ids"]
    rendered_default = default_services["render"].render_observation(
        ContextObservationRenderInput(
            session_key=default_session_key,
            metadata=default_metadata,
        ),
    )
    default_schema_names = [
        schema["name"]
        for schema in rendered_default.provider_attachments.get("tool_schemas", ())
    ]
    assert "browser.network.inspect" in default_schema_names
    assert "browser.runtime.inspect" in default_schema_names
    assert "browser.script.extract_request" in default_schema_names
    assert "browser.runtime.probe_client" not in default_schema_names
    assert "browser.runtime.call_client" not in default_schema_names
    assert "browser.evaluate" in default_schema_names
    assert "browser.action.trace" in default_schema_names
    assert "browser.native.run" in default_schema_names
    assert "browser.click" in default_schema_names
    assert "browser.type" in default_schema_names
    assert "browser.form.inspect" in default_schema_names
    assert "browser.dom.inspect" in default_schema_names
    assert "browser.tabs.list" not in default_schema_names

    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.bundle.bundled.local_package.browser",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree(session_key)
    group_nodes = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.bundled.local_package.browser"
    ]

    assert [node.id for node in group_nodes] == [
        "tools.bundle.bundled.local_package.browser.group.navigation",
        "tools.bundle.bundled.local_package.browser.group.observation",
        "tools.bundle.bundled.local_package.browser.group.code_insight",
        "tools.bundle.bundled.local_package.browser.group.network",
        "tools.bundle.bundled.local_package.browser.group.action_trace",
        "tools.bundle.bundled.local_package.browser.group.native_script",
        "tools.bundle.bundled.local_package.browser.group.forms_overlays",
        "tools.bundle.bundled.local_package.browser.group.dom_inspection",
        "tools.bundle.bundled.local_package.browser.group.page_interaction",
        "tools.bundle.bundled.local_package.browser.group.storage",
        "tools.bundle.bundled.local_package.browser.group.context_leases",
        "tools.bundle.bundled.local_package.browser.group.environment",
        "tools.bundle.bundled.local_package.browser.group.diagnostics",
    ]
    assert {node.kind for node in group_nodes} == {"tool_bundle_group"}
    assert not [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.bundled.local_package.browser"
        and node.kind == "tool_function"
    ]
    observation = next(node for node in group_nodes if node.owner_ref["group_key"] == "observation")
    action_trace = next(node for node in group_nodes if node.owner_ref["group_key"] == "action_trace")
    native_script = next(node for node in group_nodes if node.owner_ref["group_key"] == "native_script")
    forms_overlays = next(
        node for node in group_nodes if node.owner_ref["group_key"] == "forms_overlays"
    )
    network = next(node for node in group_nodes if node.owner_ref["group_key"] == "network")
    code_insight = next(
        node for node in group_nodes if node.owner_ref["group_key"] == "code_insight"
    )
    storage = next(node for node in group_nodes if node.owner_ref["group_key"] == "storage")
    diagnostics = next(
        node for node in group_nodes if node.owner_ref["group_key"] == "diagnostics"
    )
    assert observation.title == "Browser Observation"
    navigation = next(node for node in group_nodes if node.owner_ref["group_key"] == "navigation")
    assert "not a repeated pre-flight check" in navigation.summary
    assert "not an absence proof" in observation.summary
    assert observation.owner_ref["function_ids"] == ["browser.observe"]
    assert action_trace.title == "Action Trace"
    assert "verify the effect before claiming success" in action_trace.summary
    assert action_trace.owner_ref["function_ids"] == ["browser.action.trace"]
    assert native_script.title == "Native Browser Script"
    assert "Playwright-like sequence" in native_script.summary
    assert native_script.owner_ref["function_ids"] == ["browser.native.run"]
    assert "date/calendar pickers" in forms_overlays.summary
    assert "response/request bodies" in network.summary
    assert "one focused page action" in network.summary
    assert "live frontend scripts" in code_insight.summary
    assert "browser.evaluate" in code_insight.summary
    assert "client state" in storage.summary
    assert "observable evidence" in diagnostics.summary
    assert observation.metadata["default_tool_schema_ids"] == ["browser.observe"]
    assert observation.metadata["default_tool_schema_max_count"] == 1
    assert navigation.metadata["default_tool_schema_ids"] == ["browser.navigate"]
    assert navigation.metadata["default_tool_schema_max_count"] == 1
    assert network.metadata["default_tool_schema_ids"][:3] == [
        "browser.network.inspect",
        "browser.network.start_capture",
        "browser.network.list_requests",
    ]
    assert network.metadata["default_tool_schema_max_count"] == 6
    assert code_insight.metadata["default_tool_schema_ids"][-1] == "browser.evaluate"
    assert "browser.script.extract_request" in code_insight.metadata["default_tool_schema_ids"]
    assert "browser.runtime.probe_client" not in code_insight.metadata["default_tool_schema_ids"]
    assert "browser.runtime.call_client" not in code_insight.metadata["default_tool_schema_ids"]
    assert code_insight.metadata["default_tool_schema_max_count"] == 6
    assert code_insight.metadata["default_tool_schema_source"] == (
        "bundled.local_package.browser.runtime_request_group.code_insight"
    )
    assert native_script.metadata["default_tool_schema_ids"] == ["browser.native.run"]
    assert native_script.metadata["default_tool_schema_max_count"] == 1
    assert native_script.metadata["default_tool_schema_source"] == (
        "bundled.local_package.browser.runtime_request_group.native_script"
    )
    rendered_group_report = services["render"].render_observation(
        ContextObservationRenderInput(
            session_key=session_key,
            metadata={
                "default_tool_schema_group_refs": browser_bootstrap_refs,
            },
        ),
    )
    group_budget = rendered_group_report.provider_attachment_report[
        "tool_schema_mirror_budget"
    ]
    groups_by_key = {
        group.get("group_key"): group
        for group in group_budget["groups"]
        if group.get("kind") == "tool_bundle_group"
    }

    assert group_budget["group_count"] == 14
    assert group_budget["visible_group_count"] == 14
    assert group_budget["collapsed_group_count"] == 13
    assert group_budget["default_group_count"] == 9
    assert set(groups_by_key) == {
        "navigation",
        "observation",
        "action_trace",
        "native_script",
        "page_interaction",
        "forms_overlays",
        "dom_inspection",
        "network",
        "code_insight",
        "storage",
        "context_leases",
        "environment",
        "diagnostics",
    }
    assert groups_by_key["network"]["default_group"] is True
    assert groups_by_key["network"]["visibility"] == "visible_collapsed"
    assert groups_by_key["network"]["default_schema_count"] == 6
    assert groups_by_key["network"]["function_count"] == 10
    assert groups_by_key["code_insight"]["default_group"] is True
    assert groups_by_key["code_insight"]["default_schema_count"] == 6
    assert groups_by_key["action_trace"]["default_group"] is True
    assert groups_by_key["forms_overlays"]["default_group"] is True
    assert groups_by_key["page_interaction"]["default_group"] is True
    assert groups_by_key["dom_inspection"]["default_group"] is True

    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.bundle.bundled.local_package.browser.group.observation",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.bundle.bundled.local_package.browser.group.action_trace",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree(session_key)
    observation_children = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.bundled.local_package.browser.group.observation"
    ]
    action_trace_children = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.bundled.local_package.browser.group.action_trace"
    ]

    assert [node.id for node in observation_children] == ["tools.tool.browser.observe"]
    assert observation_children[0].state.schema_enabled is False
    assert [node.id for node in action_trace_children] == [
        "tools.tool.browser.action.trace",
    ]
    assert action_trace_children[0].state.schema_enabled is False
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    assert '<tool_function name="browser.observe"' in rendered.debug_body
    assert '<tool_function name="browser.action.trace"' in rendered.debug_body
    assert "The snapshot is only a first pass" not in rendered.debug_body
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.tool.browser.observe",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.tool.browser.action.trace",
            action=ContextAction.EXPAND,
        ),
    )
    rendered_after_function_expand = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    assert "The snapshot is only a first pass" in (
        rendered_after_function_expand.debug_body
    )
    assert "Use it to verify concrete page effects" in (
        rendered_after_function_expand.debug_body
    )
    assert rendered.tool_schema_mirror_available is True
    assert rendered.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered.provider_attachments

    for node_id in ("tools.tool.browser.observe", "tools.tool.browser.action.trace"):
        services["tree"].apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=ContextAction.ENABLE_TOOL_SCHEMA,
            ),
        )
    rendered_after_enable = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    mirrored_schema_names = [
        schema["name"]
        for schema in rendered_after_enable.provider_attachments.get("tool_schemas", ())
    ]
    assert rendered_after_enable.mirrored_node_ids == (
        "tools.tool.browser.observe",
        "tools.tool.browser.action.trace",
    )
    assert mirrored_schema_names == ["browser.observe", "browser.action.trace"]


def test_tool_schema_mirror_follows_context_node_state() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                source_id="bundled.openapi.weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
                parameters=(
                    ToolParameter(
                        name="location",
                        description="Location to query.",
                        data_type="string",
                        required=True,
                    ),
                ),
            ),
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.bundle.bundled.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )

    rendered_before_enable = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered_before_enable.tool_schema_mirror_available is True
    assert rendered_before_enable.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_before_enable.provider_attachments

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.fetch_weather",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered.mirrored_node_ids == ("tools.tool.fetch_weather",)
    assert rendered.provider_attachments["tool_schemas"][0]["name"] == "fetch_weather"

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.fetch_weather",
            action=ContextAction.DISABLE_TOOL_SCHEMA,
        ),
    )
    rendered_after_disable = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered_after_disable.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_after_disable.provider_attachments


def test_owner_refresh_clears_stale_tool_schema_state_without_action_marker() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                source_id="bundled.openapi.weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
                parameters=(
                    ToolParameter(
                        name="location",
                        description="Location to query.",
                        data_type="string",
                        required=True,
                    ),
                ),
            ),
        ),
    )
    session_key = "session:stale-schema-state"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.bundle.bundled.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree(session_key)
    stale_node = next(node for node in tree.nodes if node.id == "tools.tool.fetch_weather")
    stale_node.apply_state(
        stale_node.state.with_updates(schema_enabled=True, pinned=True),
    )
    stale_node.revision = "old-tool-context-revision"
    stale_node.metadata.pop("schema_enabled_source", None)
    services["nodes"].save(stale_node)

    rendered_after_refresh = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    tree_after_refresh = services["tree"].list_tree(session_key)
    refreshed_node = next(
        node for node in tree_after_refresh.nodes if node.id == "tools.tool.fetch_weather"
    )

    assert refreshed_node.state.schema_enabled is False
    assert refreshed_node.state.pinned is True
    assert refreshed_node.revision != "old-tool-context-revision"
    assert rendered_after_refresh.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_after_refresh.provider_attachments

    refreshed_node.apply_state(
        refreshed_node.state.with_updates(schema_enabled=True),
    )
    refreshed_node.metadata.pop("schema_enabled_source", None)
    services["nodes"].save(refreshed_node)
    rendered_after_same_revision_refresh = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    same_revision_tree = services["tree"].list_tree(session_key)
    same_revision_node = next(
        node for node in same_revision_tree.nodes if node.id == "tools.tool.fetch_weather"
    )

    assert same_revision_node.state.schema_enabled is False
    assert rendered_after_same_revision_refresh.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_after_same_revision_refresh.provider_attachments

    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.tool.fetch_weather",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
        ),
    )
    enabled_tree = services["tree"].list_tree(session_key)
    enabled_node = next(
        node for node in enabled_tree.nodes if node.id == "tools.tool.fetch_weather"
    )
    enabled_node.revision = "old-tool-context-revision"
    services["nodes"].save(enabled_node)
    rendered_after_action_refresh = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    action_refreshed_tree = services["tree"].list_tree(session_key)
    action_refreshed_node = next(
        node
        for node in action_refreshed_tree.nodes
        if node.id == "tools.tool.fetch_weather"
    )

    assert action_refreshed_node.state.schema_enabled is True
    assert action_refreshed_node.metadata["schema_enabled_source"] == (
        "context_tree_action"
    )
    assert rendered_after_action_refresh.mirrored_node_ids == (
        "tools.tool.fetch_weather",
    )
    assert rendered_after_action_refresh.provider_attachments["tool_schemas"][0][
        "name"
    ] == "fetch_weather"


def test_tool_schema_mirror_budget_limits_enabled_function_schemas() -> None:
    tools = tuple(
        Tool(
            id=f"tool_{index:02d}",
            source_id="configured.openapi.mass",
            name=f"Tool {index:02d}",
            description="A tool with a provider-callable schema.",
            parameters=(
                ToolParameter(
                    name="query",
                    description="Query value.",
                    data_type="string",
                    required=True,
                ),
            ),
        )
        for index in range(34)
    )
    tool_service = _FakeToolService(*tools)
    services = _context_services(tool_service)
    session_key = "session:schema-budget"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={"available_tool_names": [tool.id for tool in tools]},
        ),
    )

    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.bundle.configured.openapi.mass",
            action=ContextAction.EXPAND,
        ),
    )
    for tool in tools:
        services["tree"].apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=f"tools.tool.{tool.id}",
                action=ContextAction.ENABLE_TOOL_SCHEMA,
            ),
        )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key=session_key),
    )
    schemas = rendered.provider_attachments.get("tool_schemas")
    budget = rendered.provider_attachment_report["tool_schema_mirror_budget"]

    assert isinstance(schemas, list)
    assert len(schemas) == 32
    assert budget["status"] == "limited"
    assert budget["max_count"] == 32
    assert budget["enabled_candidate_count"] == 34
    assert budget["skipped_count"] == 2
    assert budget["skipped_by_reason"] == {"count_limit": 2}


def test_tool_schema_mirror_runtime_defaults_do_not_mutate_node_state() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                source_id="bundled.openapi.weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
                parameters=(
                    ToolParameter(
                        name="location",
                        description="Location to query.",
                        data_type="string",
                        required=True,
                    ),
                ),
            ),
        ),
    )
    session_key = "session:runtime-default-schema"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.bundle.bundled.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(
            session_key=session_key,
            metadata={
                "default_tool_schema_ids": ["fetch_weather"],
                "default_tool_schema_source": "runtime_policy.test",
            },
        ),
    )
    schemas = rendered.provider_attachments.get("tool_schemas")
    budget = rendered.provider_attachment_report["tool_schema_mirror_budget"]
    tree = services["tree"].list_tree(session_key)
    tool_node = next(node for node in tree.nodes if node.id == "tools.tool.fetch_weather")

    assert isinstance(schemas, list)
    assert schemas[0]["name"] == "fetch_weather"
    assert rendered.mirrored_node_ids == ("tools.tool.fetch_weather",)
    assert budget["default_schema_source"] == "runtime_policy.test"
    assert budget["default_requested_count"] == 1
    assert budget["default_candidate_count"] == 1
    assert budget["default_mirrored_count"] == 1
    assert tool_node.state.schema_enabled is False


def test_tool_schema_mirror_requires_expanded_tool_bundle() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                source_id="bundled.openapi.weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert not rendered.tool_schema_mirror_available
    assert rendered.mirrored_node_ids == ()
    assert "tools.bundle.bundled.openapi.weather" in rendered.included_node_ids

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.bundle.bundled.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )
    rendered_after_group_expand = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered_after_group_expand.tool_schema_mirror_available
    assert rendered_after_group_expand.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_after_group_expand.provider_attachments

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.fetch_weather",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
        ),
    )
    rendered_after_enable = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered_after_enable.mirrored_node_ids == ("tools.tool.fetch_weather",)
    assert rendered_after_enable.provider_attachments["tool_schemas"][0]["name"] == (
        "fetch_weather"
    )


def test_context_tree_control_group_is_not_default_provider_surface() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="context_tree.expand",
                source_id="bundled.local_package.context_tree",
                name="Context Tree Expand",
                description="Expand a context tree node.",
                tags=("context_tree",),
                capability_ids=("context_workspace.write",),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["context_tree.expand"]},
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert "tools.available" in rendered.included_node_ids
    assert "tools.bundle.bundled.local_package.context_tree" in rendered.included_node_ids
    assert "tools.tool.context_tree.expand" not in rendered.included_node_ids
    assert rendered.mirrored_node_ids == ()
    assert rendered.provider_attachments.get("tool_schemas", ()) == ()


def test_workspace_tools_group_by_workspace_before_session_capability() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="workspace_list",
                source_id="bundled.local_package.workspace",
                name="Workspace List",
                description="List workspace files.",
                tags=("workspace", "scope:workspace_bound"),
                capability_ids=("workspace.read", "session.read"),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["workspace_list"]},
        ),
    )
    tree = services["tree"].list_tree("session:tools")
    group_nodes = [node for node in tree.nodes if node.parent_id == "tools.available"]

    assert [node.id for node in group_nodes] == [
        "tools.bundle.bundled.local_package.workspace",
    ]


def test_source_kind_tags_do_not_become_runtime_request_bundle_titles() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="configured_cli_help",
                source_id="configured.cli.python",
                name="CLI Help",
                description="Read help output from a configured CLI source.",
                tags=("cli", "guided"),
            ),
            Tool(
                id="sample_mcp_echo",
                source_id="configured.mcp.sample",
                name="MCP Echo",
                description="Echo a message from an MCP sample server.",
                tags=("mcp", "sample"),
            ),
            Tool(
                id="sample_openapi_echo",
                source_id="configured.openapi.sample",
                name="OpenAPI Echo",
                description="Echo a message from an OpenAPI sample source.",
                tags=("openapi", "sample"),
            ),
            Tool(
                id="sample_openapi_weather",
                source_id="configured.openapi.weather",
                name="OpenAPI Weather",
                description="Fetch a forecast from an OpenAPI source.",
                tags=("openapi", "weather"),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={
                "available_tool_names": [
                    "configured_cli_help",
                    "sample_mcp_echo",
                    "sample_openapi_echo",
                    "sample_openapi_weather",
                ],
            },
        ),
    )
    tree = services["tree"].list_tree("session:tools")
    group_nodes = [node for node in tree.nodes if node.parent_id == "tools.available"]

    assert [node.id for node in group_nodes] == [
        "tools.bundle.configured.cli.python",
        "tools.bundle.configured.mcp.sample",
        "tools.bundle.configured.openapi.sample",
        "tools.bundle.configured.openapi.weather",
    ]
    assert {node.kind for node in group_nodes} == {"tool_bundle"}
    assert {node.title for node in group_nodes}.isdisjoint({"CLI", "MCP", "OpenAPI"})


def test_cli_sources_are_guidance_nodes_not_tool_functions() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="configured_cli_help",
                name="CLI Help",
                description="Read help output from a configured CLI source.",
                source_id="configured.cli.python",
                tags=("cli", "guided", "python"),
            ),
            Tool(
                id="configured_cli_execute",
                name="CLI Execute",
                description="Start a configured CLI process.",
                source_id="configured.cli.python",
                tags=("cli", "guided", "python"),
            ),
            Tool(
                id="exec",
                source_id="bundled.local_package.command",
                name="Workspace Exec",
                description="Run a workspace-bound shell command.",
                tags=("command", "process"),
                capability_ids=("process.spawn",),
            ),
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={
                "available_tool_names": [
                    "configured_cli_help",
                    "configured_cli_execute",
                    "exec",
                ],
            },
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.bundle.configured.cli.python",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.bundle.bundled.local_package.command",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tools")
    cli_children = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.configured.cli.python"
    ]
    command_children = [
        node
        for node in tree.nodes
        if node.parent_id == "tools.bundle.bundled.local_package.command"
    ]

    assert [node.id for node in cli_children] == [
        "tools.cli_source.configured.cli.python",
    ]
    assert [node.id for node in command_children] == ["tools.tool.exec"]
    cli_bundle = next(
        node for node in tree.nodes if node.id == "tools.bundle.configured.cli.python"
    )
    assert cli_bundle.metadata["function_count"] == 2
    assert cli_children[0].kind == "tool_cli_source"
    assert cli_children[0].owner_ref["execution_tool_id"] == "exec"
    assert cli_children[0].owner_ref["hidden_function_ids"] == [
        "configured_cli_execute",
        "configured_cli_help",
    ]

    rendered_before_enable = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered_before_enable.tool_schema_mirror_available is True
    assert rendered_before_enable.mirrored_node_ids == ()
    assert "tool_schemas" not in rendered_before_enable.provider_attachments

    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.exec",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered.mirrored_node_ids == ("tools.tool.exec",)
    assert rendered.provider_attachments["tool_schemas"][0]["name"] == "exec"


def test_owner_refresh_preserves_tool_schema_toggle_state() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="fetch_weather",
                source_id="bundled.openapi.weather",
                name="Fetch Weather",
                description="Fetch current weather for a location.",
            ),
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.bundle.bundled.openapi.weather",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.tool.fetch_weather",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
        ),
    )

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
            metadata={"available_tool_names": ["fetch_weather"]},
        ),
    )
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(session_key="session:tools"),
    )

    assert rendered.mirrored_node_ids == ("tools.tool.fetch_weather",)
    assert rendered.provider_attachments["tool_schemas"][0]["name"] == "fetch_weather"


def test_tool_adapter_keeps_tools_collapsed_without_resolved_surface() -> None:
    services = _context_services(_FakeToolService())

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:tools",
            agent_id="assistant",
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:tools",
            node_id="tools.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:tools")

    assert [node for node in tree.nodes if node.parent_id == "tools.available"] == []


def test_default_direct_tool_schema_ids_expand_matching_source_bundle() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="open_meteo_weather.forecast_weather",
                source_id="bundled.openapi.open_meteo_weather",
                name="Fetch Weather Forecast",
                description="Fetch current and hourly weather.",
            ),
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:weather-defaults",
            agent_id="assistant",
            metadata={
                "available_tool_names": ["open_meteo_weather.forecast_weather"],
            },
        ),
    )

    default_metadata = resolve_default_tool_schema_metadata(
        tree_service=services["tree"],
        session_key="session:weather-defaults",
        run_id="run-weather-defaults",
        draft=SimpleNamespace(
            flow_hint={
                "default_tool_schema_ids": [
                    "open_meteo_weather.forecast_weather",
                ],
            },
        ),  # type: ignore[arg-type]
    )

    assert default_metadata == {}
    rendered = services["render"].render_observation(
        ContextObservationRenderInput(
            session_key="session:weather-defaults",
            metadata={
                "default_tool_schema_ids": [
                    "open_meteo_weather.forecast_weather",
                ],
                "default_tool_schema_source": "turn_intake.weather_surface",
            },
        ),
    )

    assert rendered.provider_attachments["tool_schemas"][0]["name"] == (
        "open_meteo_weather.forecast_weather"
    )


def test_default_direct_command_tool_schema_ids_expand_command_bundle() -> None:
    services = _context_services(
        _FakeToolService(
            Tool(
                id="exec",
                source_id="bundled.local_package.command",
                name="Workspace Exec",
                description="Run a workspace-bound shell command.",
            ),
            Tool(
                id="process",
                source_id="bundled.local_package.command",
                name="Background Process",
                description="Manage a long-running background process.",
            ),
        ),
    )
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:command-defaults",
            agent_id="assistant",
            metadata={"available_tool_names": ["exec", "process"]},
        ),
    )

    default_metadata = resolve_default_tool_schema_metadata(
        tree_service=services["tree"],
        session_key="session:command-defaults",
        run_id="run-command-defaults",
        draft=SimpleNamespace(
            flow_hint={"default_tool_schema_ids": ["exec", "process"]},
        ),  # type: ignore[arg-type]
    )

    assert default_metadata == {}
    tree = services["tree"].list_tree("session:command-defaults")
    command_bundle = next(
        node
        for node in tree.nodes
        if node.id == "tools.bundle.bundled.local_package.command"
    )
    assert command_bundle.state.collapsed is False

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(
            session_key="session:command-defaults",
            metadata={
                "default_tool_schema_ids": ["exec", "process"],
                "default_tool_schema_source": "explicit_test.command_surface",
            },
        ),
    )

    assert {
        schema["name"]
        for schema in rendered.provider_attachments["tool_schemas"]
    } == {"exec", "process"}
    budget = rendered.provider_attachment_report["tool_schema_mirror_budget"]
    assert budget["default_requested_count"] == 2
    assert budget["default_candidate_count"] == 2
    assert budget["default_mirrored_count"] == 2


def test_core_default_schemas_come_from_tool_source_runtime_request_policy() -> None:
    command_plan = load_tool_package_plan("tools/command/tool.yaml")
    web_plan = load_tool_package_plan("tools/web/tool.yaml")
    context_tree_plan = load_tool_package_plan("tools/context_tree/tool.yaml")
    command_source_id = "bundled.local_package.command"
    web_source_id = "bundled.local_package.web"
    context_tree_source_id = "bundled.local_package.context_tree"
    tool_service = _FakeToolService(
        *_tools_from_local_package_plan(command_plan, source_id=command_source_id),
        *_tools_from_local_package_plan(web_plan, source_id=web_source_id),
        *_tools_from_local_package_plan(
            context_tree_plan,
            source_id=context_tree_source_id,
        ),
        groups_by_source={
            command_source_id: _runtime_request_groups_from_browser_source(
                command_plan.runtime_request["groups"],
            ),
            web_source_id: _runtime_request_groups_from_browser_source(
                web_plan.runtime_request["groups"],
            ),
            context_tree_source_id: _runtime_request_groups_from_browser_source(
                context_tree_plan.runtime_request["groups"],
            ),
        },
        metadata_by_source={
            command_source_id: {"runtime_request": command_plan.runtime_request},
            web_source_id: {"runtime_request": web_plan.runtime_request},
            context_tree_source_id: {"runtime_request": context_tree_plan.runtime_request},
        },
    )
    services = _context_services(tool_service)
    session_key = "session:source-policy-defaults"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={
                "available_tool_names": [
                    "exec",
                    "process",
                    "web.fetch_json",
                    "web.fetch_text",
                    "capability.search",
                ],
            },
        ),
    )

    default_metadata = resolve_default_tool_schema_metadata(
        tree_service=services["tree"],
        session_key=session_key,
        run_id="run-source-policy-defaults",
        draft=SimpleNamespace(flow_hint={}),  # type: ignore[arg-type]
    )

    assert default_metadata["default_tool_schema_ids"] == [
        "exec",
        "process",
        "capability.search",
    ]
    assert default_metadata["default_tool_schema_source"] == (
        "bundled.local_package.command.runtime_request_group.run_and_verify,"
        "bundled.local_package.command.runtime_request_group.background_processes,"
        "bundled.local_package.context_tree.runtime_request_group.capability_discovery"
    )
    assert default_metadata["default_tool_schema_group_refs"] == [
        {"source_id": command_source_id, "group_key": "run_and_verify", "priority": "10"},
        {
            "source_id": command_source_id,
            "group_key": "background_processes",
            "priority": "10",
        },
        {
            "source_id": context_tree_source_id,
            "group_key": "capability_discovery",
            "priority": "5",
        },
    ]
    for node_id in (
        "tools.available",
        "tools.bundle.bundled.local_package.context_tree",
        "tools.bundle.bundled.local_package.command",
    ):
        services["tree"].apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=ContextAction.EXPAND,
            ),
        )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(
            session_key=session_key,
            metadata=default_metadata,
        ),
    )

    assert {
        schema["name"]
        for schema in rendered.provider_attachments["tool_schemas"]
    } == {
        "exec",
        "process",
        "capability.search",
    }
    budget = rendered.provider_attachment_report["tool_schema_mirror_budget"]
    assert budget["default_schema_source"] == default_metadata["default_tool_schema_source"]
    assert budget["default_requested_count"] == 3
    assert budget["default_candidate_count"] == 3
    assert budget["default_mirrored_count"] == 3
    assert budget["default_group_match_count"] == 3
    assert budget["default_group_matches"] == [
        {
            "node_id": "tools.bundle.bundled.local_package.command.group.run_and_verify",
            "source_id": command_source_id,
            "group_key": "run_and_verify",
            "priority": "101000",
        },
        {
            "node_id": (
                "tools.bundle.bundled.local_package.command.group.background_processes"
            ),
            "source_id": command_source_id,
            "group_key": "background_processes",
            "priority": "102000",
        },
        {
            "node_id": (
                "tools.bundle.bundled.local_package.context_tree.group.capability_discovery"
            ),
            "source_id": context_tree_source_id,
            "group_key": "capability_discovery",
            "priority": "51000",
        },
    ]
    schemas_by_name = {
        schema["name"]: schema
        for schema in rendered.provider_attachments["tool_schemas"]
    }
    assert "Search available runtime capabilities" in schemas_by_name[
        "capability.search"
    ]["description"]
    assert "max_output_tokens" in schemas_by_name["exec"]["description"]
    assert "web.fetch_json" not in schemas_by_name


def test_explicit_browser_network_schema_survives_default_surface_budget() -> None:
    browser_plan = load_tool_package_plan("tools/browser/tool.yaml")
    context_tree_plan = load_tool_package_plan("tools/context_tree/tool.yaml")
    browser_source_id = "bundled.local_package.browser"
    context_tree_source_id = "bundled.local_package.context_tree"
    tool_service = _FakeToolService(
        *_tools_from_local_package_plan(browser_plan, source_id=browser_source_id),
        *_tools_from_local_package_plan(
            context_tree_plan,
            source_id=context_tree_source_id,
        ),
        groups_by_source={
            browser_source_id: _runtime_request_groups_from_browser_source(
                browser_plan.runtime_request["groups"],
            ),
            context_tree_source_id: _runtime_request_groups_from_browser_source(
                context_tree_plan.runtime_request["groups"],
            ),
        },
        metadata_by_source={
            browser_source_id: {"runtime_request": browser_plan.runtime_request},
            context_tree_source_id: {"runtime_request": context_tree_plan.runtime_request},
        },
    )
    services = _context_services(tool_service)
    session_key = "session:browser-network-budget"
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key=session_key,
            agent_id="assistant",
            metadata={
                "available_tool_names": [
                    "browser.navigate",
                    "browser.observe",
                    "browser.code.search",
                    "browser.runtime.inspect",
                    "browser.evaluate",
                    "browser.network.inspect",
                    "capability.search",
                ],
            },
        ),
    )

    default_metadata = resolve_default_tool_schema_metadata(
        tree_service=services["tree"],
        session_key=session_key,
        run_id="run-browser-network-budget",
        draft=SimpleNamespace(flow_hint={}),  # type: ignore[arg-type]
    )
    for node_id in (
        "tools.available",
        "tools.bundle.bundled.local_package.browser",
        "tools.bundle.bundled.local_package.browser.group.network",
    ):
        services["tree"].apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=ContextAction.EXPAND,
            ),
        )
    services["tree"].apply_action(
        ContextActionInput(
            session_key=session_key,
            node_id="tools.tool.browser.network.inspect",
            action=ContextAction.ENABLE_TOOL_SCHEMA,
        ),
    )

    rendered = services["render"].render_observation(
        ContextObservationRenderInput(
            session_key=session_key,
            metadata={
                **default_metadata,
                "tool_schema_mirror_max_count": 6,
            },
        ),
    )

    schema_names = [
        schema["name"]
        for schema in rendered.provider_attachments["tool_schemas"]
    ]
    assert "browser.network.inspect" in schema_names
    assert "tools.tool.browser.network.inspect" in rendered.mirrored_node_ids


def _context_services(tool_service: "_FakeToolService"):
    registry = ContextOwnerRegistry()
    registry.register(ToolContextNodeProvider(tool_service, tool_service))
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    snapshots = InMemoryContextSnapshotRepository()
    return {
        "workspace": ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
        ),
        "tree": ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
            owner_registry=registry,
        ),
        "render": ContextObservationSnapshotService(
            workspace_repository=workspaces,
            node_repository=nodes,
            snapshot_repository=snapshots,
            owner_registry=registry,
        ),
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
        ),
        "nodes": nodes,
    }


def _tools_from_local_package_plan(plan: Any, *, source_id: str) -> tuple[Tool, ...]:
    return tuple(
        Tool(
            id=handler.tool.id,
            source_id=source_id,
            name=handler.tool.name,
            description=handler.tool.description,
            parameters=handler.tool.parameters,
            required_effect_ids=handler.tool.required_effect_ids,
            capability_ids=handler.tool.capability_ids,
            tags=handler.tool.tags,
        )
        for handler in plan.local_handlers
    )


class _FakeToolService:
    def __init__(
        self,
        *tools: Tool,
        groups_by_source: dict[str, tuple[ToolRuntimeRequestBundleGroup, ...]] | None = None,
        summary_by_source: dict[str, str] | None = None,
        metadata_by_source: dict[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self._tools = {tool.id: tool for tool in tools}
        self._groups_by_source = groups_by_source or {}
        self._summary_by_source = summary_by_source or {}
        self._metadata_by_source = metadata_by_source or {}

    def get_tool(self, tool_id: str) -> Tool:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_id}' does not exist.")
        return tool

    def get_tools(self, tool_ids) -> dict[str, Tool]:
        return {
            str(tool_id): self._tools[str(tool_id)]
            for tool_id in tool_ids
            if str(tool_id) in self._tools
        }

    def list_runtime_request_bundles(
        self,
        function_ids,
    ) -> tuple[ToolRuntimeRequestBundle, ...]:
        grouped: dict[str, list[Tool]] = {}
        for function_id in function_ids:
            tool = self._tools.get(str(function_id))
            if tool is None:
                continue
            source_id = tool.source_id or f"test.source.{tool.id}"
            grouped.setdefault(source_id, []).append(tool)
        return tuple(
            ToolRuntimeRequestBundle(
                source_id=source_id,
                title=_bundle_title(source_id),
                summary=(
                    self._summary_by_source.get(source_id)
                    or f"{_bundle_title(source_id)} tools."
                ),
                source_kind=_source_kind(source_id),
                function_ids=tuple(tool.id for tool in tools),
                function_count=len(tools),
                groups=_visible_runtime_request_groups(
                    self._groups_by_source.get(source_id, ()),
                    tools,
                ),
                capability_ids=tuple(
                    dict.fromkeys(
                        capability
                        for tool in tools
                        for capability in tool.capability_ids
                    ),
                ),
                metadata=dict(self._metadata_by_source.get(source_id, {})),
            )
            for source_id, tools in grouped.items()
        )


def _visible_runtime_request_groups(
    groups: tuple[ToolRuntimeRequestBundleGroup, ...],
    tools: list[Tool],
) -> tuple[ToolRuntimeRequestBundleGroup, ...]:
    tool_ids = {tool.id for tool in tools}
    tools_by_id = {tool.id: tool for tool in tools}
    visible_groups: list[ToolRuntimeRequestBundleGroup] = []
    for group in groups:
        function_ids = tuple(
            function_id for function_id in group.function_ids if function_id in tool_ids
        )
        if not function_ids:
            continue
        visible_groups.append(
            ToolRuntimeRequestBundleGroup(
                group_key=group.group_key,
                title=group.title,
                summary=group.summary,
                function_ids=function_ids,
                function_count=len(function_ids),
                capability_ids=tuple(
                    dict.fromkeys(
                        capability_id
                        for function_id in function_ids
                        for capability_id in tools_by_id[function_id].capability_ids
                    ),
                ),
                metadata=dict(group.metadata),
            ),
        )
    return tuple(visible_groups)


def _runtime_request_groups_from_browser_source(
    raw_groups: Mapping[str, object],
) -> tuple[ToolRuntimeRequestBundleGroup, ...]:
    groups: list[ToolRuntimeRequestBundleGroup] = []
    for group_key, value in sorted(
        raw_groups.items(),
        key=lambda item: int(item[1].get("order", 1000)) if isinstance(item[1], Mapping) else 1000,
    ):
        if not isinstance(value, Mapping):
            continue
        function_ids = tuple(
            str(function_id)
            for function_id in value.get("function_ids", ())
            if isinstance(function_id, str) and function_id.strip()
        )
        groups.append(
            ToolRuntimeRequestBundleGroup(
                group_key=group_key,
                title=str(value.get("title") or group_key),
                summary=str(value.get("summary") or ""),
                function_ids=function_ids,
                function_count=len(function_ids),
                metadata={
                    key: value[key]
                    for key in (
                        "order",
                        "default_tool_schema_ids",
                        "default_tool_schema_max_count",
                        "default_tool_schema_source",
                    )
                    if key in value
                },
            ),
        )
    return tuple(groups)


def _tool_from_browser_candidate(candidate: Any) -> Tool:
    return Tool(
        id=candidate.function_id,
        source_id=candidate.source_id,
        name=candidate.name,
        description=candidate.description,
        required_effect_ids=candidate.requirements.required_effect_ids,
        runtime_requirement_sets=candidate.requirements.runtime_requirement_sets,
        capability_ids=candidate.capability_ids,
        tags=tuple(str(tag) for tag in candidate.metadata.get("tags", ())),
    )


def _bundle_title(source_id: str) -> str:
    return source_id.rsplit(".", 1)[-1].replace("_", " ").title()


def _source_kind(source_id: str) -> str:
    if ".openapi." in source_id:
        return "openapi"
    if ".mcp." in source_id:
        return "mcp"
    if ".cli." in source_id:
        return "cli"
    if ".local_package." in source_id:
        return "local_package"
    return "local_package"
