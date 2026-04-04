from __future__ import annotations

import unittest

from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserControlCommandAssembler,
    DefaultBrowserExecutionPlanner,
    DefaultBrowserPageActionAssembler,
    DefaultBrowserProfileResolver,
    DefaultBrowserProfileSelectionOpsFactory,
    DefaultBrowserProfileTabOpsFactory,
)
from crxzipple.modules.browser.domain import BrowserProfileConfig, BrowserSystemConfig
from crxzipple.modules.browser.infrastructure import (
    InMemoryBrowserRefStore,
    InMemoryBrowserRuntimeStateStore,
    InMemoryBrowserSystemConfigStore,
    InMemoryCdpBackedPlaywrightActionEngine,
    InMemoryCdpControlEngine,
    InMemoryMcpActionEngine,
    InMemoryMcpControlEngine,
    StaticBrowserEngineRegistry,
)
from crxzipple.modules.browser.interfaces import (
    BrowserControlRequest,
    BrowserPageActionRequest,
    BrowserResultSerializer,
    BrowserInterfaceFacade,
)


class BrowserInterfacesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(name="crxzipple"),
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                ),
            ),
            cdp_port_range_start=9333,
            cdp_port_range_end=9340,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=InMemoryBrowserRuntimeStateStore(),
            ref_store=InMemoryBrowserRefStore(),
            execution_planner=DefaultBrowserExecutionPlanner(),
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                mcp_control=InMemoryMcpControlEngine(),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
                mcp_backed=InMemoryMcpActionEngine(),
            ),
            tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
            selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
        )
        self.facade = BrowserInterfaceFacade(
            control_command_assembler=DefaultBrowserControlCommandAssembler(),
            page_action_assembler=DefaultBrowserPageActionAssembler(),
            execution_coordinator=coordinator,
        )
        self.serializer = BrowserResultSerializer()

    def test_facade_executes_control_request(self) -> None:
        open_result = self.facade.execute(
            BrowserControlRequest(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )
        list_result = self.facade.execute(
            BrowserControlRequest(
                profile_name="crxzipple",
                kind="list-tabs",
            )
        )

        self.assertTrue(open_result.ok)
        self.assertEqual(len(list_result.value), 1)
        self.assertEqual(list_result.value[0].target_id, open_result.target_id)

    def test_facade_executes_page_action_request(self) -> None:
        open_result = self.facade.execute(
            BrowserControlRequest(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        click_result = self.facade.execute(
            BrowserPageActionRequest(
                profile_name="user",
                kind="click",
                target_id=open_result.target_id,
                ref="e3",
            )
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.target_id, open_result.target_id)
        self.assertEqual(click_result.value["engine"], "mcp-backed")
        self.assertEqual(click_result.value["ref"], "e3")

    def test_result_serializer_shapes_control_result_for_transport_layers(self) -> None:
        open_result = self.facade.execute(
            BrowserControlRequest(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )
        serialized = self.serializer.serialize(open_result)

        self.assertTrue(serialized["ok"])
        self.assertEqual(serialized["command"]["family"], "control")
        self.assertEqual(serialized["command"]["kind"], "open-tab")
        self.assertEqual(serialized["value"]["target_id"], open_result.target_id)
        self.assertEqual(serialized["value"]["url"], "https://example.com")

    def test_result_serializer_shapes_page_action_result_for_transport_layers(self) -> None:
        open_result = self.facade.execute(
            BrowserControlRequest(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        click_result = self.facade.execute(
            BrowserPageActionRequest(
                profile_name="user",
                kind="click",
                target_id=open_result.target_id,
                ref="e9",
                selector="#confirm",
                payload={"button": "left"},
            )
        )
        serialized = self.serializer.serialize(click_result)

        self.assertTrue(serialized["ok"])
        self.assertEqual(serialized["command"]["family"], "page-action")
        self.assertEqual(serialized["command"]["target"]["ref"], "e9")
        self.assertEqual(serialized["command"]["target"]["selector"], "#confirm")
        self.assertEqual(serialized["value"]["engine"], "mcp-backed")
        self.assertEqual(serialized["value"]["tab"]["target_id"], open_result.target_id)


if __name__ == "__main__":
    unittest.main()
