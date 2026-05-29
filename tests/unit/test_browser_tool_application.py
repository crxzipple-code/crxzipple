from __future__ import annotations

import unittest
from typing import Any, Mapping

from crxzipple.modules.browser.application import (
    BrowserToolApplicationError,
    BrowserToolApplicationService,
)
from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserActionTarget,
    BrowserControlCommand,
    BrowserPageActionCommand,
    BrowserValidationError,
)


class _ControlAssembler:
    def assemble(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserControlCommand:
        return BrowserControlCommand(
            profile_name=profile_name,
            kind=kind,
            target_id=target_id,
            payload=payload or {},
            timeout_ms=timeout_ms,
        )


class _PageActionAssembler:
    def assemble(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        ref: str | None = None,
        selector: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserPageActionCommand:
        return BrowserPageActionCommand(
            profile_name=profile_name,
            kind=kind,
            target=BrowserActionTarget(
                target_id=target_id,
                ref=ref,
                selector=selector,
            ),
            payload=payload or {},
            timeout_ms=timeout_ms,
        )


class _NoRuntimeStateStore:
    def get(self, *, profile_name: str):  # noqa: ANN201
        del profile_name
        return None


class BrowserToolApplicationServiceTestCase(unittest.TestCase):
    def test_validation_errors_become_display_safe_error_payloads(self) -> None:
        class _Coordinator:
            def execute(self, command):  # noqa: ANN001, ANN201
                del command
                raise BrowserValidationError("Browser profile 'ghost' is not configured.")

        service = BrowserToolApplicationService(
            control_command_assembler=_ControlAssembler(),
            page_action_assembler=_PageActionAssembler(),
            execution_coordinator=_Coordinator(),
            runtime_state_store=_NoRuntimeStateStore(),
        )

        with self.assertRaises(BrowserToolApplicationError) as exc_info:
            service.execute_page_action(
                profile_name="ghost",
                kind="snapshot",
                target_id="tab-1",
            )

        payload = exc_info.exception.to_payload()
        self.assertEqual(payload["code"], "browser_profile_not_configured")
        self.assertEqual(payload["category"], "browser")
        self.assertEqual(payload["profile"], "ghost")
        self.assertEqual(payload["family"], "page-action")
        self.assertEqual(payload["kind"], "snapshot")
        self.assertEqual(payload["target_id"], "tab-1")
        self.assertTrue(payload["setup_required"])

    def test_success_payload_is_serialized_for_tool_handlers(self) -> None:
        captured_commands: list[object] = []

        class _Coordinator:
            def execute(self, command):  # noqa: ANN001, ANN201
                captured_commands.append(command)
                return BrowserActionResult(
                    command=command,
                    ok=True,
                    target_id="tab-1",
                    value={"title": "Ready"},
                    message="done",
                )

        service = BrowserToolApplicationService(
            control_command_assembler=_ControlAssembler(),
            page_action_assembler=_PageActionAssembler(),
            execution_coordinator=_Coordinator(),
            runtime_state_store=_NoRuntimeStateStore(),
        )

        result = service.execute_control(profile_name="crxzipple", kind="list-tabs")

        self.assertEqual(len(captured_commands), 1)
        self.assertEqual(result.payload["ok"], True)
        self.assertEqual(result.payload["target_id"], "tab-1")
        self.assertEqual(result.payload["value"], {"title": "Ready"})
        self.assertEqual(
            result.runtime_metadata["browser_host_service_key"],
            "host:browser:crxzipple",
        )


if __name__ == "__main__":
    unittest.main()
