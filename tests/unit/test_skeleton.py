from __future__ import annotations

import os
import unittest

from crxzipple.modules import MODULE_NAMES
from crxzipple.modules.tool.application import RegisterToolInput
from tests.unit.support import SqliteTestHarness


class SkeletonTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_container()

    def tearDown(self) -> None:
        self.container.engine.dispose()
        self.harness.close()
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )

    def test_declares_expected_modules(self) -> None:
        self.assertEqual(
            MODULE_NAMES,
            ("tool", "session", "llm", "agent", "orchestration", "dispatch"),
        )

    def test_tool_service_registers_runtime_tool_and_publishes_event(self) -> None:
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="search",
                name="Search",
                description="Query external knowledge",
            ),
        )

        self.assertEqual(tool.id, "search")
        self.assertEqual(self.container.tool_service.get_tool("search"), tool)
        self.assertEqual(len(self.container.event_bus.published_events), 1)
        self.assertEqual(
            self.container.event_bus.published_events[0].name,
            "tool.registered",
        )


if __name__ == "__main__":
    unittest.main()
