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
    BrowserProfileRuntimeState,
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


class _RuntimeStateStore:
    def __init__(self, state: BrowserProfileRuntimeState) -> None:
        self._state = state

    def get(self, *, profile_name: str):  # noqa: ANN201
        if profile_name == self._state.profile_name:
            return self._state
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

    def test_unexpected_adapter_errors_become_display_safe_error_payloads(self) -> None:
        class _Coordinator:
            def execute(self, command):  # noqa: ANN001, ANN201
                del command
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        service = BrowserToolApplicationService(
            control_command_assembler=_ControlAssembler(),
            page_action_assembler=_PageActionAssembler(),
            execution_coordinator=_Coordinator(),
            runtime_state_store=_NoRuntimeStateStore(),
        )

        with self.assertRaises(BrowserToolApplicationError) as exc_info:
            service.execute_page_action(
                profile_name="crxzipple",
                kind="script-list",
                target_id="tab-1",
            )

        payload = exc_info.exception.to_payload()
        self.assertEqual(payload["code"], "browser_execution_failed")
        self.assertEqual(payload["category"], "browser")
        self.assertEqual(payload["profile"], "crxzipple")
        self.assertEqual(payload["family"], "page-action")
        self.assertEqual(payload["kind"], "script-list")
        self.assertEqual(payload["target_id"], "tab-1")
        self.assertIn("Expecting value", payload["message"])

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

    def test_target_errors_include_recovery_runtime_state(self) -> None:
        class _Coordinator:
            def execute(self, command):  # noqa: ANN001, ANN201
                del command
                raise BrowserValidationError(
                    "Browser tab 'old-tab' is not available through Playwright CDP.",
                )

        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            last_target_id="active-tab",
            metadata={
                "active_target_id": "active-tab",
                "tabs": [
                    {
                        "target_id": "active-tab",
                        "type": "page",
                        "title": "Flight Search",
                        "url": "https://example.test/search?token=secret#frag",
                        "ws_url": "ws://127.0.0.1/devtools/page/active-tab",
                    },
                    {
                        "target_id": "worker-1",
                        "type": "service_worker",
                        "title": "Worker",
                        "url": "https://example.test/sw.js",
                    },
                ],
            },
        )
        service = BrowserToolApplicationService(
            control_command_assembler=_ControlAssembler(),
            page_action_assembler=_PageActionAssembler(),
            execution_coordinator=_Coordinator(),
            runtime_state_store=_RuntimeStateStore(runtime_state),
        )

        with self.assertRaises(BrowserToolApplicationError) as exc_info:
            service.execute_page_action(
                profile_name="crxzipple",
                kind="snapshot",
                target_id="old-tab",
            )

        payload = exc_info.exception.to_payload()
        self.assertEqual(payload["code"], "browser_target_not_found")
        self.assertTrue(payload["retryable"])
        recovery = payload["browser_recovery"]
        self.assertEqual(recovery["next_action"], "refresh-browser-observation")
        self.assertEqual(recovery["requested_target_id"], "old-tab")
        self.assertEqual(recovery["active_target_id"], "active-tab")
        self.assertEqual(recovery["retry_target_id"], "active-tab")
        self.assertEqual(recovery["available_tabs"]["count"], 1)
        self.assertEqual(
            recovery["available_tabs"]["items"][0]["url"],
            "https://example.test/search",
        )
        self.assertNotIn("ws_url", recovery["available_tabs"]["items"][0])

    def test_ref_errors_include_generation_recovery_details(self) -> None:
        class _Coordinator:
            def execute(self, command):  # noqa: ANN001, ANN201
                del command
                raise BrowserValidationError(
                    "Browser ref 'r999' was not found for tab 'tab-1'.",
                )

        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            last_target_id="tab-1",
            metadata={
                "active_target_id": "tab-1",
                "tabs": [
                    {
                        "target_id": "tab-1",
                        "type": "page",
                        "title": "Checkout",
                        "url": "https://example.test/checkout",
                    },
                ],
            },
        )
        runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=4,
            snapshot_format="interactive",
            ref_count=12,
            frame_count=1,
        )
        service = BrowserToolApplicationService(
            control_command_assembler=_ControlAssembler(),
            page_action_assembler=_PageActionAssembler(),
            execution_coordinator=_Coordinator(),
            runtime_state_store=_RuntimeStateStore(runtime_state),
        )

        with self.assertRaises(BrowserToolApplicationError) as exc_info:
            service.execute_page_action(
                profile_name="crxzipple",
                kind="click",
                target_id="tab-1",
                ref="r999",
            )

        payload = exc_info.exception.to_payload()
        self.assertEqual(payload["code"], "browser_ref_not_available")
        recovery = payload["browser_recovery"]
        self.assertEqual(recovery["next_action"], "refresh-interactive-refs")
        self.assertEqual(recovery["requested_ref"], "r999")
        self.assertEqual(recovery["target_id"], "tab-1")
        self.assertEqual(recovery["current_ref_generation"], 4)
        self.assertEqual(recovery["snapshot_generation"], 4)
        self.assertEqual(
            recovery["recommended_tools"],
            ["browser.observe", "browser.dom.clickability"],
        )


if __name__ == "__main__":
    unittest.main()
