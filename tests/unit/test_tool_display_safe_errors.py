from __future__ import annotations

import asyncio
import unittest

from crxzipple.modules.browser.application import (
    BrowserToolApplicationError,
    BrowserToolExecutionError,
)
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import ToolRunResult, ToolRunStatus
from tests.unit.tool_test_support import ToolTestCaseBase


class ToolDisplaySafeErrorsTestCase(ToolTestCaseBase):
    def test_display_safe_runtime_error_persists_code_and_details(self) -> None:
        tool = self.seed_tool(
            tool_id="browser_display_safe_error_tool",
            name="Browser Display Safe Error Tool",
            description="Raises a browser application error.",
            runtime_key="browser_display_safe_error_tool",
        )

        async def browser_display_safe_error_tool(
            _arguments: dict[str, object],
        ) -> ToolRunResult:
            raise BrowserToolApplicationError(
                BrowserToolExecutionError(
                    code="browser_profile_not_configured",
                    message="Browser profile 'ghost' is not configured.",
                    details={
                        "profile": "ghost",
                        "family": "page-action",
                        "kind": "snapshot",
                    },
                    setup_required=True,
                ),
            )

        self.local_runtime_registry.register(tool, browser_display_safe_error_tool)

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="browser_display_safe_error_tool",
                    arguments={},
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        assert tool_run.error is not None
        self.assertEqual(tool_run.error.code, "browser_profile_not_configured")
        self.assertEqual(
            tool_run.error.message,
            "Browser profile 'ghost' is not configured.",
        )
        self.assertEqual(tool_run.error.details["category"], "browser")
        self.assertEqual(tool_run.error.details["profile"], "ghost")
        self.assertTrue(tool_run.error.details["setup_required"])


if __name__ == "__main__":
    unittest.main()
