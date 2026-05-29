from __future__ import annotations

import os
import unittest

from crxzipple.modules import MODULE_NAMES
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.tool.domain.exceptions import ToolNotFoundError
from tests.unit.tool_catalog_seed import seed_catalog_tool
from tests.unit.support import SqliteTestHarness


class SkeletonTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_runtime_container()
        self.tool_service = self.container.require(AppKey.TOOL_SERVICE)
        self.event_bus = self.container.require(AppKey.EVENTS_BUS)

    def tearDown(self) -> None:
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
            (
                "access",
                "tool",
                "session",
                "llm",
                "agent",
                "orchestration",
                "dispatch",
                "events",
                "channels",
            ),
        )

    def test_tool_service_reads_catalog_tool(self) -> None:
        with self.assertRaises(ToolNotFoundError):
            self.tool_service.get_tool("search")

        tool = seed_catalog_tool(
            self.container,
            tool_id="search",
            name="Search",
            description="Query external knowledge",
        )

        self.assertEqual(tool.id, "search")
        self.assertEqual(self.tool_service.get_tool("search"), tool)


if __name__ == "__main__":
    unittest.main()
