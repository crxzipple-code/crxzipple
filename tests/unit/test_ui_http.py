from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
from uuid import uuid4

from PIL import Image

from crxzipple.interfaces.runtime_container import (
    AssemblyTarget,
    build_runtime_container,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountProfile,
    ChannelInteraction,
    ChannelInteractionRegistry,
    ChannelProfile,
    channel_dead_letter_topic,
)
from crxzipple.modules.context_workspace.application import EnsureContextWorkspaceInput
from crxzipple.modules.events import Event, EventTarget
from crxzipple.modules.access.application.events import (
    ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
)
from crxzipple.modules.operations.application.projections import (
    OPERATIONS_PROJECTION_MODULES,
)
from crxzipple.modules.daemon import DaemonInstance
from crxzipple.modules.process.domain import ProcessSession, ProcessStatus
from crxzipple.modules.llm.application import InvokeLlmInput, LlmAdapterResponse
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
    ToolCallIntent,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionOwnerReference,
    ExecutionStep,
    ExecutionStepItem,
    ExecutionStepItemKind,
    ExecutionStepKind,
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    PendingApprovalRequest,
)
from crxzipple.modules.session.application import (
    AppendSessionItemInput,
    EnsureSessionInput,
)
from crxzipple.modules.session.domain import SessionItemKind
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
)
from crxzipple.modules.tool.domain import (
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
    ToolRunResult,
)
from crxzipple.modules.settings.application import CreateSettingsResourceInput

from tests.unit.http_test_support import (
    AppKey,
    HttpModuleTestCase,
    _SequentialResultAdapter,
    _write_skill_package,
    seed_catalog_tool,
)


class _WarmupOnlyAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def warmup_websocket(self, profile, *, resolved_credential=None):  # noqa: ANN001, ANN201
        self.calls.append((profile.id, resolved_credential))
        return {
            "transport": "websocket",
            "endpoint": "wss://example.test/backend-api/codex/responses",
            "reused_connection": False,
        }


def _llm_input_items_from_messages(
    messages: tuple[LlmMessage, ...],
) -> tuple[LlmInputItem, ...]:
    return tuple(
        LlmInputItem(
            kind=LlmInputItemKind.MESSAGE,
            payload={"role": message.role.value, "content": message.content},
            source="test",
        )
        for message in messages
    )


def _invoke_llm_input(**kwargs: Any) -> InvokeLlmInput:
    messages = tuple(kwargs.get("messages") or ())
    if "input_items" not in kwargs and messages:
        kwargs["input_items"] = _llm_input_items_from_messages(messages)
    return InvokeLlmInput(**kwargs)


def _collect_runtime_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for value in payload.values():
        if isinstance(value, list):
            actions.extend(
                item
                for item in value
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and ("allowed" in item or "endpoint" in item)
            )
    return actions


def _empty_key_value_section(section_id: str, title: str) -> dict[str, Any]:
    return {"id": section_id, "title": title, "items": []}


def _empty_table_section(section_id: str, title: str) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "columns": [],
        "rows": [],
        "total": 0,
    }


def _minimal_tool_detail_payload(
    *,
    run_id: str,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "title": run_id,
        "status": "succeeded",
        "tone": "success",
        "summary": [],
        "invocation_context": [],
        "input_payload": input_payload,
        "result_payload": {},
        "result_summary": "",
        "error": "",
        "error_facts": _empty_key_value_section("error_facts", "Error Facts"),
        "assignments": _empty_table_section("assignments", "Assignments"),
        "events": _empty_table_section("events", "Events"),
        "artifacts": _empty_table_section("artifacts", "Artifacts"),
    }


def _minimal_llm_detail_payload(
    *,
    invocation_id: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "invocation_id": invocation_id,
        "title": invocation_id,
        "status": "succeeded",
        "tone": "success",
        "summary": [],
        "request_context": [],
        "runtime_observations": _empty_key_value_section(
            "runtime_observations",
            "Runtime Observations",
        ),
        "runtime_request_summary": {},
        "request_payload": request_payload,
        "provider_render_report": {},
        "provider_wire_preview": {},
        "provider_context_mapping": _empty_table_section(
            "provider_context_mapping",
            "Provider Context Mapping",
        ),
        "result_payload": {},
        "result_summary": "",
        "error": "",
        "resolver": _empty_key_value_section("resolver", "Resolver"),
        "error_facts": _empty_key_value_section("error_facts", "Error Facts"),
        "policy_trace": _empty_table_section("policy_trace", "Policy Trace"),
        "response_items": _empty_table_section("response_items", "Response Items"),
        "response_runtime_mapping": _empty_table_section(
            "response_runtime_mapping",
            "Response Runtime Mapping",
        ),
        "response_events": _empty_table_section("response_events", "Response Events"),
        "events": _empty_table_section("events", "Events"),
    }


def _terminate_subprocess(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


class UiHttpTestCase(HttpModuleTestCase):
    def _target_container(self, target: AssemblyTarget):
        return build_runtime_container(
            self.client.app.state.container.require(AppKey.CORE_SETTINGS),
            target=target,
        )

    def _process_operations_events(self) -> None:
        outbox_container = self._target_container(AssemblyTarget.EVENT_OUTBOX_PUBLISHER)
        try:
            outbox_container.require(
                AppKey.EVENT_OUTBOX_PUBLISHER_SERVICE,
            ).publish_available(limit=500)
        finally:
            outbox_container.close()
        observer_container = self._target_container(AssemblyTarget.OPERATIONS_OBSERVER)
        try:
            observer_container.require(
                AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE,
            ).process_available_events()
        finally:
            observer_container.close()

    def _materialize_operations(self, *modules: str) -> None:
        materializer = self.client.app.state.container.require(
            AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
        )
        materializer.materialize_modules(modules)

    def test_ui_workbench_linked_entity_detail_reads_session_item(self) -> None:
        session_service = self.client.app.state.container.require(AppKey.SESSION_SERVICE)
        session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:detail",
                agent_id="assistant",
                workspace="workspace-ui",
            ),
        )
        item = session_service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:detail",
                kind=SessionItemKind.TOOL_RESULT,
                role="tool",
                content_payload={
                    "tool_name": "browser.snapshot",
                    "content": [{"type": "text", "text": "Captured page state."}],
                },
                source_module="tool",
                source_kind="tool_run",
                source_id="tool-run-detail",
                call_id="call-detail",
                tool_name="browser.snapshot",
            ),
        )

        response = self.client.get(
            f"/ui/workbench/linked-entities/session_item/{item.id}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "session_item")
        self.assertEqual(payload["id"], item.id)
        self.assertEqual(payload["owner"], "session")
        self.assertEqual(payload["payload"]["kind"], "tool_result")
        self.assertEqual(payload["payload"]["call_id"], "call-detail")
        self.assertIn("browser.snapshot", payload["summary"])

    def test_ui_workbench_linked_entity_detail_reads_llm_response_item(self) -> None:
        container = self.client.app.state.container

        class _ResponseItemDetailAdapter:
            def invoke(self, _profile: object, request: object) -> LlmAdapterResponse:
                invocation_id = getattr(request, "invocation_id")
                return LlmAdapterResponse(
                    result=LlmResult(
                        text="ready",
                        usage=LlmUsage(input_tokens=3, output_tokens=2, total_tokens=5),
                        finish_reason="stop",
                    ),
                    response_items=(
                        LlmResponseItem(
                            id=f"{invocation_id}:item:0",
                            invocation_id=invocation_id,
                            sequence_no=0,
                            kind=LlmResponseItemKind.TOOL_CALL,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={
                                "tool_name": "browser.snapshot",
                                "arguments": {},
                            },
                            call_id="call-detail-llm",
                            tool_name="browser.snapshot",
                        ),
                    ),
                )

        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            _ResponseItemDetailAdapter(),
        )
        profile_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-detail",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-detail",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(profile_response.status_code, 201)
        invocation = container.require(AppKey.LLM_SERVICE).invoke(
            _invoke_llm_input(
                llm_id="openai.gpt-detail",
                invocation_id="llm-detail",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Inspect page.",
                    ),
                ),
            ),
        )

        response = self.client.get(
            f"/ui/workbench/linked-entities/llm_response_item_id/{invocation.response_items[0].id}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "llm_response_item")
        self.assertEqual(payload["id"], "llm-detail:item:0")
        self.assertEqual(payload["owner"], "llm")
        self.assertEqual(payload["payload"]["invocation_id"], "llm-detail")
        self.assertEqual(payload["payload"]["call_id"], "call-detail-llm")
        self.assertIn("browser.snapshot", payload["summary"])

    def test_ui_workbench_linked_entity_detail_reads_tool_run_evidence(
        self,
    ) -> None:
        container = self.client.app.state.container
        tool_run = ToolRun.create(
            run_id="tool-run-linked-detail",
            tool_id="command.exec",
            input_payload={"cmd": "printf hello"},
            metadata={"purpose": "raw-output-check"},
            invocation_context_payload={"workspace_dir": "/tmp/workspace"},
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        tool_run.call_id = "call-tool-linked-detail"
        tool_run.tool_surface_id = "tool_surface:command.exec"
        tool_run.start()
        tool_run.succeed(
            ToolRunResult(
                content=[
                    {
                        "type": "text",
                        "text": "exec completed with code 0: captured output",
                    },
                ],
                metadata={
                    "tool_result_envelope": {
                        "status": "ok",
                        "tool_name": "command.exec",
                        "output_payload": {
                            "exit_code": 0,
                            "stdout": "hello",
                            "stderr": "",
                        },
                        "read_handles": [
                            {
                                "kind": "raw_output_block",
                                "name": "stdout",
                                "tool": "exec",
                            },
                        ],
                        "raw_output_blocks": [
                            {
                                "name": "stdout",
                                "text": "hello",
                                "truncated": False,
                            },
                        ],
                        "artifact_refs": [],
                        "evidence_refs": [],
                    },
                },
            ),
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.tool_runs.add(tool_run)
            uow.commit()

        response = self.client.get(
            f"/ui/workbench/linked-entities/tool_run/{tool_run.id}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "tool_run")
        self.assertEqual(payload["id"], tool_run.id)
        self.assertEqual(payload["owner"], "tool")
        self.assertEqual(payload["label"], "command.exec")
        self.assertEqual(payload["payload"]["status"], "succeeded")
        self.assertEqual(payload["payload"]["call_id"], "call-tool-linked-detail")
        self.assertEqual(
            payload["payload"]["tool_surface_id"],
            "tool_surface:command.exec",
        )
        self.assertEqual(payload["payload"]["input_payload"], {"cmd": "printf hello"})
        self.assertEqual(
            payload["payload"]["result_summary"],
            "exec completed with code 0: captured output",
        )
        self.assertEqual(
            payload["payload"]["read_handles"],
            [
                {
                    "kind": "raw_output_block",
                    "name": "stdout",
                    "tool": "exec",
                },
            ],
        )
        self.assertEqual(
            payload["payload"]["raw_output_blocks"],
            [
                {
                    "name": "stdout",
                    "text": "hello",
                    "truncated": False,
                },
            ],
        )
        self.assertEqual(
            payload["payload"]["result_envelope"]["output_payload"]["exit_code"],
            0,
        )

    def test_operations_detail_endpoints_read_independent_projections(self) -> None:
        store = self.client.app.state.container.require(AppKey.OPERATIONS_PROJECTION_STORE)
        tool_detail = _minimal_tool_detail_payload(
            run_id="tool-run-projected-detail",
            input_payload={"large": "tool"},
        )
        llm_detail = _minimal_llm_detail_payload(
            invocation_id="llm-invocation-projected-detail",
            request_payload={"large": "llm"},
        )
        store.record_projection(
            module="tool",
            kind="page",
            payload={"module": "tool", "tool_run_details": []},
        )
        store.record_projection(
            module="tool",
            kind="tool_run_detail",
            query_key="tool-run-projected-detail",
            payload=tool_detail,
        )
        store.record_projection(
            module="llm",
            kind="page",
            payload={"module": "llm", "invocation_details": []},
        )
        store.record_projection(
            module="llm",
            kind="llm_invocation_detail",
            query_key="llm-invocation-projected-detail",
            payload=llm_detail,
        )

        tool_response = self.client.get(
            "/operations/tool/runs/tool-run-projected-detail/detail",
        )
        llm_response = self.client.get(
            "/operations/llm/invocations/llm-invocation-projected-detail/detail",
        )

        self.assertEqual(tool_response.status_code, 200)
        self.assertEqual(
            tool_response.json()["input_payload"],
            {"large": "tool"},
        )
        self.assertEqual(llm_response.status_code, 200)
        self.assertEqual(
            llm_response.json()["request_payload"],
            {"large": "llm"},
        )
        self.assertEqual(llm_response.json()["provider_render_report"], {})
        self.assertEqual(llm_response.json()["provider_wire_preview"], {})
        self.assertIn("policy_trace", llm_response.json())
        tool_page = store.get_projection(module="tool", kind="page")
        llm_page = store.get_projection(module="llm", kind="page")
        self.assertIsNotNone(tool_page)
        self.assertIsNotNone(llm_page)
        assert tool_page is not None
        assert llm_page is not None
        self.assertEqual(tool_page.payload["tool_run_details"], [])
        self.assertEqual(llm_page.payload["invocation_details"], [])

    def test_ui_bootstrap_exposes_console_routes(self) -> None:
        response = self.client.get("/ui/bootstrap")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["version"], 1)
        self.assertIn("/ui/workbench/runs/{run_id}", payload["routes"])
        self.assertIn("/turns", payload["routes"])
        self.assertIn("/operations/runtime", payload["routes"])
        self.assertIn("/operations/orchestration", payload["routes"])
        self.assertEqual(payload["sections"][0]["id"], "workbench")
        self.assertEqual(payload["sections"][0]["owner"], "workbench")

    def test_operations_stream_projects_refresh_events_without_raw_event_schema(
        self,
    ) -> None:
        container = self.client.app.state.container
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="operations.projection.invalidated",
                payload={
                    "module": "tool",
                    "kinds": ["page", "overview", "table"],
                    "query_key": "default",
                    "source": "operations-observer",
                },
            ),
        )

        with self.client.stream(
            "GET",
            "/operations/stream?snapshot_limit=1&timeout_seconds=0.01",
        ) as response:
            body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: connected", body)
        self.assertIn("event: snapshot", body)
        self.assertIn('"modules": ["tool"]', body)
        self.assertIn('"kinds": ["page", "overview", "table"]', body)
        self.assertNotIn("source_payload", body)
        self.assertNotIn('"topic"', body)

    def test_ui_bootstrap_covers_operations_action_endpoints(self) -> None:
        bootstrap_response = self.client.get("/ui/bootstrap")
        self.assertEqual(bootstrap_response.status_code, 200)
        bootstrap_routes = set(bootstrap_response.json()["routes"])
        container = self.client.app.state.container
        frontend_only_prefixes = ("/settings", "/trace")
        module_routes = (
            "/operations/orchestration",
            "/operations/tool",
            "/operations/llm",
            "/operations/access",
            "/operations/channels",
            "/operations/memory",
            "/operations/skills",
            "/operations/events",
            "/operations/daemon",
        )
        container.require(AppKey.OPERATIONS_PROJECTION_MATERIALIZER).materialize_modules(
            tuple(route.rsplit("/", 1)[-1] for route in module_routes),
        )

        missing_routes: list[tuple[str, str, str]] = []
        missing_disabled_reasons: list[tuple[str, str]] = []
        for module_route in module_routes:
            response = self.client.get(module_route)
            self.assertEqual(response.status_code, 200, module_route)
            actions = _collect_runtime_actions(response.json())
            for action in actions:
                action_id = str(action.get("id", ""))
                if action.get("allowed") is False and not action.get("disabled_reason"):
                    missing_disabled_reasons.append((module_route, action_id))
                endpoint = action.get("endpoint")
                if not isinstance(endpoint, str) or not endpoint:
                    continue
                action_route = endpoint.split("?", 1)[0]
                if action_route.startswith(frontend_only_prefixes):
                    continue
                if action_route not in bootstrap_routes:
                    missing_routes.append((module_route, action_id, action_route))

        self.assertEqual(missing_routes, [])
        self.assertEqual(missing_disabled_reasons, [])

    def test_ui_operations_runtime_status_exposes_infra_truth(self) -> None:
        response = self.client.get("/operations/runtime")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        by_id = {item["id"]: item for item in payload["checks"]}
        self.assertEqual(by_id["database"]["value"], "SQLite")
        self.assertEqual(by_id["database"]["status"], "sqlite")
        self.assertEqual(by_id["database"]["tone"], "warning")
        self.assertEqual(by_id["events"]["value"], "file")
        self.assertEqual(by_id["events"]["status"], "file")
        self.assertIn("migration", by_id)
        self.assertTrue(by_id["migration"]["value"])

    def test_event_relay_subscribes_workbench_llm_text_delta(self) -> None:
        relay_container = self._target_container(AssemblyTarget.EVENT_RELAY_WORKER)
        try:
            runtime = relay_container.require(AppKey.EVENT_RELAY_RUNTIME_EVENT_SERVICE)

            self.assertIsNotNone(runtime)
            self.assertIn(
                "event_relay.workbench.llm-text-delta",
                {
                    subscription.subscription_id
                    for subscription in runtime.subscriptions
                },
            )
        finally:
            relay_container.close()

    def test_ui_workbench_runtime_selectors_read_from_workbench_facade(self) -> None:
        container = self.client.app.state.container
        seed_catalog_tool(
            container,
            tool_id="workbench_visible_tool",
            name="Workbench Visible Tool",
            description="Visible through the Workbench facade.",
            tags=("workbench",),
            mutates_state=True,
            required_effect_ids=("effect:test",),
        )
        seed_catalog_tool(
            container,
            tool_id="workbench_disabled_tool",
            enabled=False,
        )
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-workbench-selector",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-workbench-selector",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)
        agent_response = self.client.post(
            "/agents",
            json={
                "id": "assistant-selector",
                "name": "Assistant Selector",
                "description": "Workbench facade agent.",
                "llm_routing_policy": {
                    "default_llm_id": "openai.gpt-workbench-selector",
                },
            },
        )
        self.assertEqual(agent_response.status_code, 201)

        tools_response = self.client.get("/ui/workbench/tools?enabled_only=true")
        agents_response = self.client.get("/ui/workbench/agents")
        models_response = self.client.get("/ui/workbench/models")

        self.assertEqual(tools_response.status_code, 200)
        tool_ids = {item["id"] for item in tools_response.json()}
        self.assertIn("workbench_visible_tool", tool_ids)
        self.assertNotIn("workbench_disabled_tool", tool_ids)
        visible_tool = next(
            item for item in tools_response.json() if item["id"] == "workbench_visible_tool"
        )
        self.assertEqual(visible_tool["name"], "Workbench Visible Tool")
        self.assertEqual(visible_tool["tags"], ["workbench"])
        self.assertEqual(visible_tool["required_effect_ids"], ["effect:test"])
        self.assertTrue(visible_tool["execution_policy"]["mutates_state"])

        self.assertEqual(agents_response.status_code, 200)
        agents = {item["id"]: item for item in agents_response.json()}
        self.assertIn("assistant-selector", agents)
        self.assertEqual(
            agents["assistant-selector"]["llm_routing_policy"]["default_llm_id"],
            "openai.gpt-workbench-selector",
        )

        self.assertEqual(models_response.status_code, 200)
        models = {item["id"]: item for item in models_response.json()}
        self.assertIn("openai.gpt-workbench-selector", models)
        self.assertEqual(models["openai.gpt-workbench-selector"]["provider"], "openai")

    def test_ui_workbench_run_and_steps_use_orchestration_read_model(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-5.4-mini",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        agent_response = self.client.post(
            "/agents",
            json={
                "id": "assistant",
                "name": "Assistant",
                "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
            },
        )
        self.assertEqual(agent_response.status_code, 201)

        intake_response = self.client.post(
            "/orchestration/runs/intake",
            json={
                "run_id": "run-ui-read-model",
                "inbound_instruction": {
                    "source": "http",
                    "content": "生成一份运行台摘要",
                },
                "session": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                    "channel": "webchat",
                },
                "metadata": {"trace_id": "trace-ui-read-model"},
                "enqueue": True,
            },
        )
        self.assertEqual(intake_response.status_code, 201)

        run_response = self.client.get("/ui/workbench/runs/run-ui-read-model")
        steps_response = self.client.get("/ui/workbench/runs/run-ui-read-model/steps")

        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertEqual(run_payload["run_id"], "run-ui-read-model")
        self.assertEqual(run_payload["session_key"], "agent:assistant:main")
        self.assertEqual(run_payload["title"], "生成一份运行台摘要")
        self.assertEqual(run_payload["agent"], {"id": "assistant", "name": "Assistant"})
        self.assertEqual(run_payload["trace"]["trace_id"], "trace-ui-read-model")

        self.assertEqual(steps_response.status_code, 200)
        steps_payload = steps_response.json()
        self.assertEqual([item["type"] for item in steps_payload], ["user_input", "agent_thinking"])
        self.assertEqual(steps_payload[0]["summary"], "生成一份运行台摘要")
        self.assertEqual(steps_payload[1]["status"], "queued")

    def test_ui_workbench_steps_can_be_filtered_by_turn_id(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-5.4-mini",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        agent_response = self.client.post(
            "/agents",
            json={
                "id": "assistant",
                "name": "Assistant",
                "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
            },
        )
        self.assertEqual(agent_response.status_code, 201)

        for run_id, content in (
            ("run-ui-turn-filter-1", "第一轮"),
            ("run-ui-turn-filter-2", "第二轮"),
        ):
            intake_response = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "run_id": run_id,
                    "inbound_instruction": {
                        "source": "http",
                        "content": content,
                    },
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                    },
                    "enqueue": True,
                },
            )
            self.assertEqual(intake_response.status_code, 201)

        all_steps_response = self.client.get(
            "/ui/workbench/runs/run-ui-turn-filter-2/steps",
        )
        filtered_steps_response = self.client.get(
            "/ui/workbench/runs/run-ui-turn-filter-2/steps"
            "?turn_id=run-ui-turn-filter-1",
        )

        self.assertEqual(all_steps_response.status_code, 200)
        self.assertEqual(filtered_steps_response.status_code, 200)
        self.assertEqual(
            {item["turn_id"] for item in all_steps_response.json()},
            {"run-ui-turn-filter-1", "run-ui-turn-filter-2"},
        )
        self.assertEqual(
            {item["turn_id"] for item in filtered_steps_response.json()},
            {"run-ui-turn-filter-1"},
        )

    def test_ui_workbench_home_does_not_reuse_latest_thread_for_accepted_run_without_session(
        self,
    ) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        latest_thread_run = OrchestrationRun(
            id="run-ui-latest-thread",
            inbound_instruction=InboundInstruction(
                source="ui.workbench",
                content="latest thread title",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            active_session_id="session-main",
            metadata={
                "session_key": "agent:assistant:main",
                "thread_title": "Latest Thread",
            },
            created_at=timestamp - timedelta(minutes=1),
            updated_at=timestamp,
            completed_at=timestamp,
        )
        accepted_run = OrchestrationRun(
            id="run-ui-new-accepted",
            inbound_instruction=InboundInstruction(
                source="ui.workbench",
                content="new accepted content",
            ),
            status=OrchestrationRunStatus.ACCEPTED,
            stage=OrchestrationRunStage.ACCEPTED,
            agent_id="assistant",
            metadata={"trace_id": "trace-ui-new-accepted"},
            created_at=timestamp + timedelta(seconds=1),
            updated_at=timestamp + timedelta(seconds=1),
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(latest_thread_run)
            uow.orchestration_runs.add(accepted_run)
            uow.commit()

        response = self.client.get(
            "/ui/workbench/home?run_id=run-ui-new-accepted",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_run_id"], "run-ui-new-accepted")
        self.assertIsNone(payload["active_thread_id"])
        self.assertEqual(payload["threads"][0]["title"], "Latest Thread")

    def test_ui_workbench_followup_run_includes_child_run_tool_steps(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        requester_run = OrchestrationRun(
            id="run-ui-requester",
            inbound_instruction=InboundInstruction(
                source="http",
                content="打开网页并查询信息",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "已派生浏览器查询。"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-requester",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            started_at=timestamp,
            completed_at=timestamp + timedelta(seconds=2),
        )
        child_run = OrchestrationRun(
            id="run-ui-child-browser",
            inbound_instruction=InboundInstruction(
                source="sessions_spawn",
                content="浏览器查询工具调用",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="browser-agent",
            current_step=1,
            result_payload={"output_text": "浏览器查询完成。"},
            metadata={
                "session_key": "agent:browser-agent:main",
                "trace_id": "trace-ui-child-browser",
                "sessions_spawn": {
                    "requester_run_id": "run-ui-requester",
                    "requester_session_key": "agent:assistant:main",
                },
            },
            created_at=timestamp + timedelta(seconds=3),
            updated_at=timestamp + timedelta(seconds=7),
            started_at=timestamp + timedelta(seconds=3),
            completed_at=timestamp + timedelta(seconds=7),
        )
        followup_run = OrchestrationRun(
            id="run-ui-followup",
            inbound_instruction=InboundInstruction(
                source="sessions_spawn_followup",
                content="Child session completed.",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "浏览器查询结果已汇总。"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-followup",
                "sessions_spawn_followup": {
                    "child_run_id": "run-ui-child-browser",
                    "child_session_key": "agent:browser-agent:main",
                    "requester_run_id": "run-ui-requester",
                    "requester_session_key": "agent:assistant:main",
                },
            },
            created_at=timestamp + timedelta(seconds=8),
            updated_at=timestamp + timedelta(seconds=10),
            started_at=timestamp + timedelta(seconds=8),
            completed_at=timestamp + timedelta(seconds=10),
        )
        browser_tool_run = ToolRun.create(
            run_id="tool-run-ui-browser-snapshot",
            tool_id="browser.snapshot",
            input_payload={"url": "https://example.test"},
            metadata={
                "source": "orchestration",
                "orchestration_run_id": "run-ui-child-browser",
                "session_key": "agent:browser-agent:main",
            },
            invocation_context_payload={
                "run_id": "run-ui-child-browser",
                "session_key": "agent:browser-agent:main",
            },
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        browser_tool_run.start()
        browser_tool_run.succeed(
            ToolRunResult.text("Captured browser snapshot."),
        )

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(requester_run)
            uow.orchestration_runs.add(child_run)
            uow.orchestration_runs.add(followup_run)
            uow.tool_runs.add(browser_tool_run)
            uow.commit()

        run_response = self.client.get("/ui/workbench/runs/run-ui-followup")
        steps_response = self.client.get("/ui/workbench/runs/run-ui-followup/steps")
        requester_steps_response = self.client.get(
            "/ui/workbench/runs/run-ui-requester/steps",
        )

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(steps_response.status_code, 200)
        self.assertEqual(requester_steps_response.status_code, 200)
        run_payload = run_response.json()
        self.assertEqual(run_payload["metrics"]["tool_calls"], 1)
        self.assertIn(
            "view_trace",
            {action["id"] for action in run_payload["actions"]},
        )
        self.assertIn(
            "open_operations",
            {action["id"] for action in run_payload["inspector"]["quick_actions"]},
        )
        self.assertEqual(
            run_payload["inspector"]["debug"][0]["items"][0]["value"],
            "trace-ui-followup",
        )
        self.assertEqual(
            [(turn["turn_id"], turn["ordinal"]) for turn in run_payload["turns"]],
            [("run-ui-requester", 1), ("run-ui-followup", 2)],
        )
        self.assertEqual(run_payload["current_turn_id"], "run-ui-followup")
        steps_payload = steps_response.json()
        self.assertIn(
            "browser.snapshot",
            {
                badge["label"]
                for step in steps_payload
                for badge in step["badges"]
            },
        )
        steps_by_turn = {
            turn_id: [step for step in steps_payload if step["turn_id"] == turn_id]
            for turn_id in {"run-ui-requester", "run-ui-followup"}
        }
        self.assertEqual(
            [step["type"] for step in steps_by_turn["run-ui-requester"]],
            ["user_input", "llm", "tool_call", "final_response"],
        )
        self.assertEqual(
            [step["type"] for step in steps_by_turn["run-ui-followup"]],
            ["user_input", "llm", "tool_call", "final_response"],
        )
        browser_steps = [
            step
            for step in steps_payload
            if step["badges"] and step["badges"][0]["label"] == "browser.snapshot"
        ]
        self.assertTrue(browser_steps)
        self.assertEqual(len(browser_steps), 2)
        self.assertTrue(all("Request:" in step["summary"] for step in browser_steps))
        self.assertTrue(
            all("Captured browser snapshot." in step["summary"] for step in browser_steps),
        )
        self.assertTrue(
            all(step["run_id"] == "run-ui-child-browser" for step in browser_steps),
        )
        requester_badges = {
            badge["label"]
            for step in requester_steps_response.json()
            for badge in step["badges"]
        }
        self.assertIn("browser.snapshot", requester_badges)

    def test_ui_workbench_enriches_artifact_previews_from_artifact_store(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        image = Image.new("RGB", (32, 18), color=(24, 96, 160))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        artifact = container.require(AppKey.ARTIFACT_SERVICE).create_artifact(
            data=buffer.getvalue(),
            mime_type="image/png",
            name="poster.png",
        )
        run = OrchestrationRun(
            id="run-ui-artifact",
            inbound_instruction=InboundInstruction(
                source="http",
                content="生成图片",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "图片已生成。"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-artifact",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            started_at=timestamp,
            completed_at=timestamp + timedelta(seconds=2),
        )
        tool_run = ToolRun.create(
            run_id="tool-run-ui-artifact",
            tool_id="image_tool",
            input_payload={"prompt": "poster"},
            metadata={
                "source": "orchestration",
                "orchestration_run_id": run.id,
            },
            invocation_context_payload={"run_id": run.id},
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        tool_run.start()
        tool_run.succeed(
            ToolRunResult(
                content=[
                    {
                        "type": "image_ref",
                        "artifact_id": artifact.id,
                        "mime_type": artifact.mime_type,
                        "name": artifact.name,
                    },
                ],
            ),
        )

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.tool_runs.add(tool_run)
            uow.commit()

        run_response = self.client.get("/ui/workbench/runs/run-ui-artifact")
        steps_response = self.client.get("/ui/workbench/runs/run-ui-artifact/steps")

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(steps_response.status_code, 200)
        cover = run_response.json()["cover_artifact"]
        self.assertEqual(cover["artifact_id"], artifact.id)
        self.assertEqual(cover["width"], 32)
        self.assertEqual(cover["height"], 18)
        artifact_payloads = [
            item
            for step in steps_response.json()
            for item in step["artifacts"]
        ]
        linked_entities = [
            item
            for step in steps_response.json()
            for item in step["linked_entities"]
        ]
        step_actions = [
            item
            for step in steps_response.json()
            for item in step["actions"]
        ]
        self.assertEqual(
            artifact_payloads[0]["preview_url"],
            f"/artifacts/{artifact.id}/preview",
        )
        self.assertEqual(
            artifact_payloads[0]["download_url"],
            f"/artifacts/{artifact.id}/download",
        )
        self.assertEqual(artifact_payloads[0]["mime_type"], "image/png")
        self.assertIn(
            ("artifact", artifact.id),
            {(item["type"], item["id"]) for item in linked_entities},
        )
        self.assertIn(
            f"view_artifact:{artifact.id}",
            {item["id"] for item in step_actions},
        )

    def test_ui_workbench_metrics_use_llm_invocation_usage(self) -> None:
        container = self.client.app.state.container
        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialResultAdapter(
                LlmResult(
                    text="done",
                    usage=LlmUsage(input_tokens=9, output_tokens=5, total_tokens=14),
                    finish_reason="stop",
                ),
                LlmResult(
                    text="done again",
                    usage=LlmUsage(input_tokens=8, output_tokens=6, total_tokens=14),
                    finish_reason="stop",
                ),
            ),
        )
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-5.4-mini",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)
        invocation = container.require(AppKey.LLM_SERVICE).invoke(
            _invoke_llm_input(
                llm_id="openai.gpt-5.4-mini",
                invocation_id="llm-invocation-ui-workbench",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Summarize.",
                    ),
                ),
            ),
        )
        second_invocation = container.require(AppKey.LLM_SERVICE).invoke(
            _invoke_llm_input(
                llm_id="openai.gpt-5.4-mini",
                invocation_id="llm-invocation-ui-workbench-2",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Continue.",
                    ),
                ),
            ),
        )
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-llm-usage",
            inbound_instruction=InboundInstruction(
                source="http",
                content="统计 token",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "done"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-llm-usage",
                "requested_llm_id": "openai.gpt-5.4-mini",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            started_at=timestamp,
            completed_at=timestamp + timedelta(seconds=2),
        )
        chain = ExecutionChain.create(
            chain_id="chain-ui-llm-usage",
            turn_id=run.id,
        )
        llm_step = ExecutionStep.create(
            step_id="step-ui-llm-usage",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=1,
            kind=ExecutionStepKind.LLM,
        )
        llm_step.start()
        llm_step.complete()
        chain.increment_step_count()
        llm_item = ExecutionStepItem.create(
            item_id="item-ui-llm-usage",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=invocation.id,
            ),
        )
        llm_item.complete(
            summary_payload={
                "llm_invocation_id": invocation.id,
                "llm_id": "openai.gpt-5.4-mini",
                "tool_call_session_item_ids": ["session-item-function-call-ui-usage"],
            },
        )
        second_llm_step = ExecutionStep.create(
            step_id="step-ui-llm-usage-2",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=2,
            kind=ExecutionStepKind.LLM,
        )
        second_llm_step.start()
        second_llm_step.complete()
        chain.increment_step_count()
        second_llm_item = ExecutionStepItem.create(
            item_id="item-ui-llm-usage-2",
            step_id=second_llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=second_invocation.id,
            ),
        )
        second_llm_item.complete(
            summary_payload={
                "llm_invocation_id": second_invocation.id,
                "llm_id": "openai.gpt-5.4-mini",
                "tool_call_session_item_ids": ["session-item-function-call-ui-usage-2"],
            },
        )
        chain.complete()

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.execution_chains.add(chain)
            uow.execution_steps.add(llm_step)
            uow.execution_step_items.add(llm_item)
            uow.execution_steps.add(second_llm_step)
            uow.execution_step_items.add(second_llm_item)
            uow.commit()

        run_response = self.client.get("/ui/workbench/runs/run-ui-llm-usage")
        steps_response = self.client.get("/ui/workbench/runs/run-ui-llm-usage/steps")
        invocations_response = self.client.get(
            "/llms/openai.gpt-5.4-mini/invocations?limit=5",
        )
        invocation_detail_response = self.client.get(f"/llms/calls/{invocation.id}")

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(invocations_response.status_code, 200)
        self.assertEqual(invocation_detail_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload["metrics"]["tokens"], 28)
        self.assertEqual(payload["metrics"]["llm_calls"], 2)
        self.assertIsNone(payload["metrics"]["estimated_cost_usd"])
        self.assertEqual(payload["model"]["id"], "openai.gpt-5.4-mini")
        invocation_payload = next(
            item for item in invocations_response.json() if item["id"] == invocation.id
        )
        self.assertEqual(len(invocation_payload["response_items"]), 1)
        self.assertEqual(
            invocation_payload["response_items"][0]["content_payload"]["text"],
            "done",
        )
        self.assertEqual(
            invocation_detail_response.json()["response_items"][0]["kind"],
            "assistant_message",
        )
        linked_assets = payload["inspector"]["linked_assets"]
        self.assertIn(
            ("llm_invocation", invocation.id),
            {(item["type"], item["id"]) for item in linked_assets},
        )
        self.assertIn(
            ("llm_invocation", second_invocation.id),
            {(item["type"], item["id"]) for item in linked_assets},
        )
        llm_steps = [
            step for step in steps_response.json() if step["type"] == "llm"
        ]
        self.assertEqual(llm_steps[0]["trace"]["llm_invocation_id"], invocation.id)
        self.assertEqual(
            llm_steps[1]["trace"]["llm_invocation_id"],
            second_invocation.id,
        )
        self.assertIn(
            ("llm_invocation", invocation.id),
            {
                (item["type"], item["id"])
                for item in llm_steps[0]["linked_entities"]
            },
        )
        self.assertIn("14 tokens", llm_steps[0]["summary"])
        self.assertIn("14 tokens", llm_steps[1]["summary"])

    def test_ui_workbench_reads_llm_trace_from_execution_chain_without_run_metadata(
        self,
    ) -> None:
        container = self.client.app.state.container

        class _ResponseItemResultAdapter:
            def invoke(self, _profile: object, request: object) -> LlmAdapterResponse:
                invocation_id = getattr(request, "invocation_id")
                return LlmAdapterResponse(
                    result=LlmResult(
                        text="我先检查页面状态。",
                        tool_calls=(
                            ToolCallIntent(
                                id="call-ui-progress",
                                name="browser.snapshot",
                                arguments={},
                            ),
                        ),
                        usage=LlmUsage(
                            input_tokens=7,
                            output_tokens=6,
                            total_tokens=13,
                        ),
                        finish_reason="stop",
                    ),
                    response_items=(
                        LlmResponseItem(
                            id=f"{invocation_id}:item:0",
                            invocation_id=invocation_id,
                            sequence_no=0,
                            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={},
                            user_timeline_candidate=True,
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:1",
                            invocation_id=invocation_id,
                            sequence_no=1,
                            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={"text": "我先检查页面状态。"},
                            user_timeline_candidate=True,
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:2",
                            invocation_id=invocation_id,
                            sequence_no=2,
                            kind=LlmResponseItemKind.REASONING,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={"summary": "Need inspectable page state."},
                            user_timeline_candidate=True,
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:3",
                            invocation_id=invocation_id,
                            sequence_no=3,
                            kind=LlmResponseItemKind.REASONING,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={"summary": "Do not reveal this hidden reasoning."},
                            user_timeline_candidate=False,
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:4",
                            invocation_id=invocation_id,
                            sequence_no=4,
                            kind=LlmResponseItemKind.REASONING,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={"summary": [], "text": None},
                            user_timeline_candidate=True,
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:5",
                            invocation_id=invocation_id,
                            sequence_no=5,
                            kind=LlmResponseItemKind.TOOL_CALL,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={
                                "call_id": "call-ui-plan",
                                "tool_name": "context_tree.update_plan",
                                "arguments": {
                                    "objective": "检查页面状态",
                                    "status": "in_progress",
                                    "current_step": "准备获取页面快照",
                                    "next_steps": "调用浏览器快照并总结可见控件",
                                },
                            },
                            call_id="call-ui-plan",
                            tool_name="context_tree.update_plan",
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:6",
                            invocation_id=invocation_id,
                            sequence_no=6,
                            kind=LlmResponseItemKind.TOOL_CALL,
                            phase=LlmMessagePhase.COMMENTARY,
                            content_payload={
                                "call_id": "call-ui-progress",
                                "tool_name": "browser.snapshot",
                                "arguments": {},
                            },
                            call_id="call-ui-progress",
                            tool_name="browser.snapshot",
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:7",
                            invocation_id=invocation_id,
                            sequence_no=7,
                            kind=LlmResponseItemKind.PROVIDER_EXTERNAL_ITEM,
                            phase=LlmMessagePhase.COMMENTARY,
                            provider_item_id="provider-web-search-ui-1",
                            provider_item_type="web_search_call",
                            content_payload={"status": "completed"},
                            user_timeline_candidate=True,
                        ),
                        LlmResponseItem(
                            id=f"{invocation_id}:item:8",
                            invocation_id=invocation_id,
                            sequence_no=8,
                            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                            phase=LlmMessagePhase.FINAL_ANSWER,
                            content_payload={"text": "页面状态已检查。"},
                            user_timeline_candidate=True,
                        ),
                    ),
                )

        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            _ResponseItemResultAdapter(),
        )
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-5.4-mini",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)
        invocation = container.require(AppKey.LLM_SERVICE).invoke(
            _invoke_llm_input(
                llm_id="openai.gpt-5.4-mini",
                invocation_id="llm-invocation-ui-chain-only",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Summarize.",
                    ),
                ),
            ),
        )
        timestamp = datetime.now(timezone.utc)
        session_service = container.require(AppKey.SESSION_SERVICE)
        session_service.ensure_session(
            EnsureSessionInput(
                key="agent:assistant:main",
                agent_id="assistant",
                workspace="workspace-ui",
            ),
        )
        progress_session_item = session_service.append_item(
            AppendSessionItemInput(
                session_key="agent:assistant:main",
                kind=SessionItemKind.ASSISTANT_MESSAGE,
                role="assistant",
                content_payload={
                    "text": "我看到已有 query service 能列 execution chains/steps/items。"
                },
                source_module="llm",
                source_kind="llm_response_item",
                source_id=f"{invocation.id}:item:0",
            ),
        )
        run = OrchestrationRun(
            id="run-ui-chain-only",
            inbound_instruction=InboundInstruction(
                source="http",
                content="从执行链读取 LLM",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "done"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-chain-only",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            started_at=timestamp,
            completed_at=timestamp + timedelta(seconds=2),
        )
        chain = ExecutionChain.create(
            chain_id="chain-ui-chain-only",
            turn_id=run.id,
        )
        intake_step = ExecutionStep.create(
            step_id="step-ui-chain-only-intake",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
        )
        intake_step.complete()
        chain.increment_step_count()
        llm_step = ExecutionStep.create(
            step_id="step-ui-chain-only-llm",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=1,
            kind=ExecutionStepKind.LLM,
        )
        llm_step.start()
        llm_step.complete()
        chain.increment_step_count()
        llm_item = ExecutionStepItem.create(
            item_id="item-ui-chain-only-llm",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=invocation.id,
            ),
        )
        llm_item.complete(
            summary_payload={
                "llm_invocation_id": invocation.id,
                "llm_id": "openai.gpt-5.4-mini",
                "tool_call_session_item_ids": ["session-item-function-call-ui-chain-only"],
            },
        )
        progress_item = ExecutionStepItem.create(
            item_id="item-ui-chain-only-progress",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=1,
            kind=ExecutionStepItemKind.SESSION_MESSAGE,
            owner=ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id=progress_session_item.id,
            ),
        )
        progress_item.complete(
            summary_payload={
                "session_item_ids": [progress_session_item.id],
                "message_role": "assistant",
                "message_kind": "assistant_progress",
                "assistant_progress_text": (
                    "我看到已有 query service 能列 execution chains/steps/items。"
                ),
                "llm_invocation_id": invocation.id,
            },
        )
        continuation_item = ExecutionStepItem.create(
            item_id="item-ui-chain-only-continuation",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=2,
            kind=ExecutionStepItemKind.CONTINUATION_DECISION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_continuation",
                owner_id=f"{invocation.id}:continuation",
            ),
        )
        continuation_item.complete(
            summary_payload={
                "llm_invocation_id": invocation.id,
                "continuation_id": f"{invocation.id}:continuation",
                "reason": "provider_end_turn_false",
                "end_turn": False,
                "needs_follow_up": True,
                "provider_continuation_state": {
                    "mode": "provider_native",
                    "transport": "http",
                    "previous_response_id": "resp_ui_1",
                    "fallback_reason": "websocket_continuation_failed_before_output",
                },
            },
        )
        final_step = ExecutionStep.create(
            step_id="step-ui-chain-only-final",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=2,
            kind=ExecutionStepKind.FINAL_RESPONSE,
        )
        final_step.complete()
        chain.increment_step_count()
        chain.complete()

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.execution_chains.add(chain)
            uow.execution_steps.add(intake_step)
            uow.execution_steps.add(llm_step)
            uow.execution_step_items.add(llm_item)
            uow.execution_step_items.add(progress_item)
            uow.execution_step_items.add(continuation_item)
            uow.execution_steps.add(final_step)
            uow.commit()

        run_response = self.client.get("/ui/workbench/runs/run-ui-chain-only")
        steps_response = self.client.get("/ui/workbench/runs/run-ui-chain-only/steps")

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(steps_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload["metrics"]["tokens"], 13)
        self.assertEqual(payload["metrics"]["llm_calls"], 1)
        self.assertEqual(payload["model"]["id"], "openai.gpt-5.4-mini")
        self.assertEqual(
            [item["kind"] for item in payload["timeline"]],
            [
                "user_input",
                "assistant_commentary",
                "assistant_commentary",
                "reasoning_summary",
                "reasoning_summary",
                "tool_call",
                "provider_external_activity",
                "final_answer",
                "continuation",
            ],
        )
        response_item_timeline_items = [
            item
            for item in payload["timeline"]
            if item["source_refs"].get("llm_response_item_id")
        ]
        self.assertEqual(
            [item["kind"] for item in response_item_timeline_items],
            [
                "assistant_commentary",
                "reasoning_summary",
                "reasoning_summary",
                "tool_call",
                "provider_external_activity",
                "final_answer",
            ],
        )
        self.assertEqual(
            [
                item
                for item in payload["timeline"]
                if item["kind"] in {"tool_run", "tool_result"}
                and item["source_refs"].get("provider_item_id")
            ],
            [],
        )
        session_item_timeline_items = [
            item
            for item in payload["timeline"]
            if item["source_refs"].get("session_item_id")
        ]
        self.assertEqual(len(session_item_timeline_items), 1)
        self.assertEqual(
            session_item_timeline_items[0]["content"]["markdown"],
            "我看到已有 query service 能列 execution chains/steps/items。",
        )
        self.assertEqual(
            session_item_timeline_items[0]["source_refs"]["source_event_name"],
            "assistant_progress",
        )
        continuation_timeline_items = [
            item for item in payload["timeline"] if item["kind"] == "continuation"
        ]
        self.assertEqual(
            continuation_timeline_items[0]["content"]["text"],
            (
                "provider_end_turn_false; end_turn=false; follow_up=true; "
                "provider=provider_native; transport=http; "
                "previous_response_id=resp_ui_1; "
                "fallback=websocket_continuation_failed_before_output"
            ),
        )
        self.assertEqual(
            continuation_timeline_items[0]["source_refs"]["llm_invocation_id"],
            invocation.id,
        )
        self.assertEqual(
            continuation_timeline_items[0]["source_refs"]["execution_step_id"],
            llm_step.id,
        )
        self.assertIn(
            ("llm_invocation", invocation.id),
            {
                (item["type"], item["id"])
                for item in payload["inspector"]["linked_assets"]
            },
        )
        timeline_diagnostics = next(
            section
            for section in payload["inspector"]["debug"]
            if section["id"] == "timeline_diagnostics"
        )
        self.assertEqual(
            {
                item["label"]: item["value"]
                for item in timeline_diagnostics["items"]
            },
            {
                "Timeline items": "9",
                "LLM response items": "6",
                "Tool lifecycle items": "1",
                "Hidden reasoning items": "1",
                "Provider external items": "1",
            },
        )
        steps_payload = steps_response.json()
        self.assertEqual(
            [step["type"] for step in steps_payload],
            [
                "user_input",
                "agent_progress",
                "llm",
                "continuation_decision",
                "final_response",
            ],
        )
        self.assertEqual(
            [step["step_id"] for step in steps_payload],
            [
                f"{run.id}:execution:{intake_step.id}",
                f"{run.id}:execution:{llm_step.id}:progress:1",
                f"{run.id}:execution:{llm_step.id}",
                f"{run.id}:execution:{llm_step.id}:continuation:2",
                f"{run.id}:execution:{final_step.id}",
            ],
        )
        self.assertEqual(
            [step["trace"]["step_id"] for step in steps_payload],
            [intake_step.id, llm_step.id, llm_step.id, llm_step.id, final_step.id],
        )
        progress_steps = [
            step for step in steps_payload if step["type"] == "agent_progress"
        ]
        self.assertEqual(progress_steps[0]["title"], "Agent Progress")
        self.assertEqual(
            progress_steps[0]["markdown"],
            "我看到已有 query service 能列 execution chains/steps/items。",
        )
        self.assertEqual(
            progress_steps[0]["trace"]["llm_invocation_id"],
            invocation.id,
        )
        self.assertEqual(
            progress_steps[0]["trace"]["session_item_id"],
            progress_session_item.id,
        )
        self.assertEqual(
            progress_steps[0]["trace"]["source_owner"],
            "session_item",
        )
        self.assertEqual(
            progress_steps[0]["trace"]["source_event_id"],
            progress_session_item.id,
        )
        llm_steps = [step for step in steps_payload if step["type"] == "llm"]
        self.assertEqual(llm_steps[0]["trace"]["llm_invocation_id"], invocation.id)
        self.assertEqual(
            llm_steps[0]["actions"][0]["target"]["route"],
            f"/workbench/traces/{run.metadata['trace_id']}?focus_id={invocation.id}",
        )
        self.assertIn("13 tokens", llm_steps[0]["summary"])
        self.assertIn("text:", llm_steps[0]["summary"])
        self.assertIn("tool calls: 2", llm_steps[0]["summary"])
        self.assertIn("progress recorded: 1", llm_steps[0]["summary"])
        self.assertIn(
            "Text + tools",
            {badge["label"] for badge in llm_steps[0]["badges"]},
        )
        continuation_steps = [
            step for step in steps_payload if step["type"] == "continuation_decision"
        ]
        self.assertEqual(continuation_steps[0]["title"], "Continuation Decision")
        self.assertEqual(
            continuation_steps[0]["summary"],
            (
                "provider_end_turn_false; end_turn=false; follow_up=true; "
                "provider=provider_native; transport=http; "
                "previous_response_id=resp_ui_1; "
                "fallback=websocket_continuation_failed_before_output"
            ),
        )
        self.assertIn(
            "provider_native",
            {badge["label"] for badge in continuation_steps[0]["badges"]},
        )
        self.assertIn(
            "http",
            {badge["label"] for badge in continuation_steps[0]["badges"]},
        )
        self.assertIn(
            "Continuation fallback",
            {badge["label"] for badge in continuation_steps[0]["badges"]},
        )
        self.assertEqual(
            continuation_steps[0]["trace"]["llm_invocation_id"],
            invocation.id,
        )

    def test_ui_workbench_displays_user_input_and_final_answer_timeline(self) -> None:
        container = self.client.app.state.container

        class _FinalAnswerAdapter:
            def invoke(self, _profile: object, request: object) -> LlmAdapterResponse:
                invocation_id = getattr(request, "invocation_id")
                return LlmAdapterResponse(
                    result=LlmResult(
                        text="这是最终答复。",
                        usage=LlmUsage(
                            input_tokens=5,
                            output_tokens=4,
                            total_tokens=9,
                        ),
                        finish_reason="stop",
                    ),
                    response_items=(
                        LlmResponseItem(
                            id=f"{invocation_id}:item:final",
                            invocation_id=invocation_id,
                            sequence_no=0,
                            kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                            phase=LlmMessagePhase.FINAL_ANSWER,
                            content_payload={"text": "这是最终答复。"},
                            user_timeline_candidate=True,
                        ),
                    ),
                )

        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            _FinalAnswerAdapter(),
        )
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-5.4-final",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-final",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)
        invocation = container.require(AppKey.LLM_SERVICE).invoke(
            InvokeLlmInput(
                llm_id="openai.gpt-5.4-final",
                invocation_id="llm-invocation-ui-final-only",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Answer directly.",
                    ),
                ),
                input_items=(
                    LlmInputItem(
                        kind=LlmInputItemKind.MESSAGE,
                        payload={"role": "user", "content": "Answer directly."},
                        source="test",
                    ),
                ),
            ),
        )
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-final-only",
            inbound_instruction=InboundInstruction(
                source="http",
                content="直接回答",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "这是最终答复。"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-final-only",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=1),
            started_at=timestamp,
            completed_at=timestamp + timedelta(seconds=1),
        )
        chain = ExecutionChain.create(
            chain_id="chain-ui-final-only",
            turn_id=run.id,
        )
        intake_step = ExecutionStep.create(
            step_id="step-ui-final-only-intake",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
        )
        intake_step.complete()
        chain.increment_step_count()
        llm_step = ExecutionStep.create(
            step_id="step-ui-final-only-llm",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=1,
            kind=ExecutionStepKind.LLM,
        )
        llm_step.complete()
        chain.increment_step_count()
        llm_item = ExecutionStepItem.create(
            item_id="item-ui-final-only-llm",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=invocation.id,
            ),
        )
        llm_item.complete(
            summary_payload={
                "llm_invocation_id": invocation.id,
                "llm_id": "openai.gpt-5.4-final",
            },
        )
        continuation_item = ExecutionStepItem.create(
            item_id="item-ui-final-only-continuation",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=1,
            kind=ExecutionStepItemKind.CONTINUATION_DECISION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_continuation",
                owner_id=f"{invocation.id}:continuation",
            ),
        )
        continuation_item.complete(
            summary_payload={
                "llm_invocation_id": invocation.id,
                "continuation_id": f"{invocation.id}:continuation",
                "reason": "none",
                "needs_follow_up": False,
            },
        )
        final_step = ExecutionStep.create(
            step_id="step-ui-final-only-final",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=2,
            kind=ExecutionStepKind.FINAL_RESPONSE,
        )
        final_step.complete()
        chain.increment_step_count()
        chain.complete()

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.execution_chains.add(chain)
            uow.execution_steps.add(intake_step)
            uow.execution_steps.add(llm_step)
            uow.execution_step_items.add(llm_item)
            uow.execution_step_items.add(continuation_item)
            uow.execution_steps.add(final_step)
            uow.commit()

        response = self.client.get("/ui/workbench/runs/run-ui-final-only")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["kind"] for item in payload["timeline"]],
            ["user_input", "final_answer"],
        )
        self.assertEqual(payload["timeline"][0]["content"]["text"], "直接回答")
        self.assertEqual(payload["timeline"][1]["content"]["text"], "这是最终答复。")
        self.assertEqual(
            payload["timeline"][1]["source_refs"]["llm_response_item_id"],
            "llm-invocation-ui-final-only:item:final",
        )

    def test_ui_workbench_marks_consecutive_tool_only_llm_steps(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-tool-only-streak",
            inbound_instruction=InboundInstruction(
                source="http",
                content="连续工具调用",
            ),
            status=OrchestrationRunStatus.RUNNING,
            stage=OrchestrationRunStage.LLM,
            agent_id="assistant",
            current_step=3,
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-tool-only-streak",
                "requested_llm_id": "openai.gpt-5.4-mini",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=3),
            started_at=timestamp,
        )
        chain = ExecutionChain.create(
            chain_id="chain-ui-tool-only-streak",
            turn_id=run.id,
        )
        steps: list[ExecutionStep] = []
        items: list[ExecutionStepItem] = []
        for index in range(1, 4):
            step = ExecutionStep.create(
                step_id=f"step-ui-tool-only-streak-{index}",
                chain_id=chain.id,
                turn_id=run.id,
                step_index=index,
                kind=ExecutionStepKind.LLM,
            )
            step.start()
            step.complete()
            item = ExecutionStepItem.create(
                item_id=f"item-ui-tool-only-streak-{index}",
                step_id=step.id,
                chain_id=chain.id,
                turn_id=run.id,
                item_index=0,
                kind=ExecutionStepItemKind.LLM_INVOCATION,
                owner=ExecutionOwnerReference(
                    owner_kind="llm_invocation",
                    owner_id=f"llm-ui-tool-only-streak-{index}",
                ),
            )
            item.complete(
                summary_payload={
                    "llm_invocation_id": f"llm-ui-tool-only-streak-{index}",
                    "llm_id": "openai.gpt-5.4-mini",
                    "tool_call_names": ["exec"],
                    "tool_call_session_item_ids": [f"session-item-tool-call-{index}"],
                },
            )
            chain.increment_step_count()
            steps.append(step)
            items.append(item)

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.execution_chains.add(chain)
            for step in steps:
                uow.execution_steps.add(step)
            for item in items:
                uow.execution_step_items.add(item)
            uow.commit()

        response = self.client.get("/ui/workbench/runs/run-ui-tool-only-streak/steps")

        self.assertEqual(response.status_code, 200)
        llm_steps = [step for step in response.json() if step["type"] == "llm"]
        self.assertEqual(len(llm_steps), 3)
        self.assertIn(
            "Tool only",
            {badge["label"] for badge in llm_steps[2]["badges"]},
        )
        self.assertNotIn(
            "Tool-only streak: 2",
            {badge["label"] for badge in llm_steps[1]["badges"]},
        )
        self.assertIn(
            "Tool-only streak: 3",
            {badge["label"] for badge in llm_steps[2]["badges"]},
        )
        self.assertIn("Tool-only streak: 3 LLM steps.", llm_steps[2]["summary"])

    def test_ui_workbench_surfaces_llm_loop_diagnostic_from_execution_chain(
        self,
    ) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-llm-loop-diagnostic",
            inbound_instruction=InboundInstruction(
                source="http",
                content="继续",
            ),
            status=OrchestrationRunStatus.FAILED,
            stage=OrchestrationRunStage.LLM,
            agent_id="assistant",
            current_step=1,
            metadata={"session_key": "agent:assistant:main"},
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=1),
            started_at=timestamp,
        )
        chain = ExecutionChain.create(
            chain_id="chain-ui-llm-loop-diagnostic",
            turn_id=run.id,
        )
        chain.start(active_step_id="step-ui-llm-loop-diagnostic")
        chain.increment_step_count()
        llm_step = ExecutionStep.create(
            step_id="step-ui-llm-loop-diagnostic",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=1,
            kind=ExecutionStepKind.LLM,
        )
        llm_step.fail(
            message="LLM response ended without a final answer.",
            code="llm_incomplete_terminal_response",
        )
        chain.fail(
            message="LLM response ended without a final answer.",
            code="llm_incomplete_terminal_response",
        )
        llm_item = ExecutionStepItem.create(
            item_id="item-ui-llm-loop-diagnostic",
            step_id=llm_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id="llm-ui-loop-diagnostic",
            ),
        )
        llm_item.summary_payload = {
            "llm_invocation_id": "llm-ui-loop-diagnostic",
            "llm_id": "openai.gpt-5.4-mini",
            "llm_loop_diagnostic": {
                "code": "llm_incomplete_terminal_response",
                "reason": "commentary_or_reasoning_without_final_answer_or_follow_up",
            },
        }
        llm_item.fail(
            message="LLM response ended without a final answer.",
            code="llm_incomplete_terminal_response",
        )

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.execution_chains.add(chain)
            uow.execution_steps.add(llm_step)
            uow.execution_step_items.add(llm_item)
            uow.commit()

        response = self.client.get("/ui/workbench/runs/run-ui-llm-loop-diagnostic/steps")

        self.assertEqual(response.status_code, 200)
        llm_steps = [step for step in response.json() if step["type"] == "llm"]
        self.assertEqual(len(llm_steps), 1)
        self.assertIn(
            "Loop diagnostic",
            {badge["label"] for badge in llm_steps[0]["badges"]},
        )
        self.assertIn(
            "loop diagnostic: llm_incomplete_terminal_response",
            llm_steps[0]["summary"],
        )

    def test_ui_workbench_reads_tool_runs_from_execution_chain_without_run_metadata(
        self,
    ) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-tool-chain-only",
            inbound_instruction=InboundInstruction(
                source="http",
                content="运行工具",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            current_step=1,
            result_payload={"output_text": "工具已完成。"},
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-tool-chain-only",
                "request_render_snapshot_id": "ctxsnap-ui-tool-chain-only",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            started_at=timestamp,
            completed_at=timestamp + timedelta(seconds=2),
        )
        tool_run = ToolRun.create(
            run_id="tool-run-ui-chain-only",
            tool_id="browser.snapshot",
            input_payload={"format": "text"},
            metadata={},
            invocation_context_payload={},
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        tool_run.start()
        tool_run.succeed(ToolRunResult.text("Captured browser snapshot."))
        chain = ExecutionChain.create(
            chain_id="chain-ui-tool-chain-only",
            turn_id=run.id,
        )
        intake_step = ExecutionStep.create(
            step_id="step-ui-tool-chain-only-intake",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
        )
        intake_step.complete()
        chain.increment_step_count()
        tool_step = ExecutionStep.create(
            step_id="step-ui-tool-chain-only-tool",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=1,
            kind=ExecutionStepKind.TOOL_BATCH,
        )
        tool_step.complete()
        chain.increment_step_count()
        tool_call_item = ExecutionStepItem.create(
            item_id="item-ui-tool-chain-only-call",
            step_id=tool_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_CALL,
            owner=ExecutionOwnerReference(
                owner_kind="tool_call",
                owner_id="call-ui-tool-chain-only",
            ),
        )
        tool_call_item.complete(
            summary_payload={
                "tool_call_id": "call-ui-tool-chain-only",
                "tool_name": "browser.snapshot",
                "tool_id": "browser.snapshot",
                "mode": "inline",
            },
        )
        tool_item = ExecutionStepItem.create(
            item_id="item-ui-tool-chain-only-tool",
            step_id=tool_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=1,
            kind=ExecutionStepItemKind.TOOL_RUN,
            owner=ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id=tool_run.id,
            ),
        )
        tool_item.complete(
            summary_payload={
                "tool_run_id": tool_run.id,
                "tool_call_id": "call-ui-tool-chain-only",
                "tool_name": "browser.snapshot",
                "tool_id": "browser.snapshot",
                "status": "succeeded",
                "tool_execution_plan": {
                    "tool_call_id": "call-ui-tool-chain-only",
                    "tool_name": "browser.snapshot",
                    "tool_id": "browser.snapshot",
                    "mode": "inline",
                    "strategy": "inline",
                    "environment": "local",
                    "arguments_digest": "digest-ui-tool-chain-only",
                },
            },
        )
        tool_result_item = ExecutionStepItem.create(
            item_id="item-ui-tool-chain-only-result",
            step_id=tool_step.id,
            chain_id=chain.id,
            turn_id=run.id,
            item_index=2,
            kind=ExecutionStepItemKind.TOOL_RESULT,
            owner=ExecutionOwnerReference(
                owner_kind="session_item",
                owner_id="session-item-tool-result-ui-chain-only",
            ),
        )
        tool_result_item.complete(
            summary_payload={
                "tool_run_id": tool_run.id,
                "tool_call_id": "call-ui-tool-chain-only",
                "tool_name": "browser.snapshot",
                "tool_id": "browser.snapshot",
                "result_message_id": "message-tool-result-ui-chain-only",
                "result_session_item_id": "session-item-tool-result-ui-chain-only",
                "session_item_ids": ["session-item-tool-result-ui-chain-only"],
                "result_summary": "exec completed with code 0: captured output",
                "exit_code": 0,
                "output_truncated": True,
                "read_handles": [
                    {
                        "kind": "raw_output_block",
                        "name": "stdout",
                        "tool": "exec",
                    },
                ],
                "tool_execution_plan": {
                    "tool_call_id": "call-ui-tool-chain-only",
                    "tool_name": "browser.snapshot",
                    "tool_id": "browser.snapshot",
                    "mode": "inline",
                    "strategy": "inline",
                    "environment": "local",
                    "arguments_digest": "digest-ui-tool-chain-only",
                },
            },
        )
        final_step = ExecutionStep.create(
            step_id="step-ui-tool-chain-only-final",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=2,
            kind=ExecutionStepKind.FINAL_RESPONSE,
        )
        final_step.complete()
        chain.increment_step_count()
        chain.complete()

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.tool_runs.add(tool_run)
            uow.execution_chains.add(chain)
            uow.execution_steps.add(intake_step)
            uow.execution_steps.add(tool_step)
            uow.execution_step_items.add(tool_call_item)
            uow.execution_step_items.add(tool_item)
            uow.execution_step_items.add(tool_result_item)
            uow.execution_steps.add(final_step)
            uow.commit()

        run_response = self.client.get("/ui/workbench/runs/run-ui-tool-chain-only")
        steps_response = self.client.get("/ui/workbench/runs/run-ui-tool-chain-only/steps")

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(steps_response.status_code, 200)
        run_payload = run_response.json()
        self.assertEqual(run_payload["metrics"]["tool_calls"], 1)
        tool_lifecycle_timeline_items = [
            item
            for item in run_payload["timeline"]
            if item["kind"] in {"tool_call", "tool_run", "tool_result"}
        ]
        self.assertEqual(
            [item["kind"] for item in tool_lifecycle_timeline_items],
            ["tool_call"],
        )
        tool_interaction = tool_lifecycle_timeline_items[0]
        lifecycle = tool_interaction["content"]["lifecycle"]
        self.assertEqual(tool_interaction["title"], "Tool Interaction: browser.snapshot")
        self.assertEqual(tool_interaction["content"]["lifecycle_item_count"], 3)
        self.assertEqual(
            [item["kind"] for item in lifecycle],
            ["tool_call", "tool_run", "tool_result"],
        )
        self.assertEqual(
            tool_interaction["source_refs"]["tool_call_id"],
            "call-ui-tool-chain-only",
        )
        self.assertEqual(
            tool_interaction["source_refs"]["tool_run_id"],
            tool_run.id,
        )
        self.assertEqual(
            lifecycle[1]["source_refs"]["execution_item_id"],
            tool_item.id,
        )
        self.assertEqual(
            tool_interaction["source_refs"]["request_render_snapshot_id"],
            "ctxsnap-ui-tool-chain-only",
        )
        self.assertEqual(
            lifecycle[1]["source_refs"]["request_render_snapshot_id"],
            "ctxsnap-ui-tool-chain-only",
        )
        self.assertEqual(
            tool_interaction["content"]["tool_execution_plan"][
                "arguments_digest"
            ],
            "digest-ui-tool-chain-only",
        )
        self.assertEqual(
            tool_interaction["source_refs"]["session_item_id"],
            "session-item-tool-result-ui-chain-only",
        )
        self.assertEqual(
            lifecycle[2]["source_refs"]["session_item_id"],
            "session-item-tool-result-ui-chain-only",
        )
        self.assertIn(
            (
                "exec completed with code 0: captured output "
                "Result item: session-item-tool-result-ui-chain-only."
            ),
            lifecycle[2]["content"]["text"],
        )
        self.assertEqual(
            lifecycle[2]["content"]["summary"],
            "exec completed with code 0: captured output",
        )
        self.assertEqual(lifecycle[2]["content"]["exit_code"], 0)
        self.assertTrue(lifecycle[2]["content"]["truncated"])
        self.assertEqual(
            lifecycle[2]["content"]["read_handles"],
            [
                {
                    "kind": "raw_output_block",
                    "name": "stdout",
                    "tool": "exec",
                },
            ],
        )
        self.assertEqual(
            lifecycle[2]["content"]["tool_execution_plan"][
                "tool_call_id"
            ],
            "call-ui-tool-chain-only",
        )
        steps_payload = steps_response.json()
        self.assertEqual(
            [step["type"] for step in steps_payload],
            ["user_input", "tool_call", "final_response"],
        )
        tool_step_payload = [
            step for step in steps_payload if step["type"] == "tool_call"
        ][0]
        self.assertEqual(
            tool_step_payload["step_id"],
            f"{run.id}:execution:{tool_step.id}:{tool_item.id}",
        )
        self.assertEqual(tool_step_payload["trace"]["step_id"], tool_step.id)
        self.assertEqual(tool_step_payload["trace"]["tool_run_id"], tool_run.id)
        self.assertEqual(
            tool_step_payload["actions"][0]["target"]["route"],
            f"/workbench/traces/{run.metadata['trace_id']}?focus_id={tool_run.id}",
        )
        self.assertIn("Captured browser snapshot.", tool_step_payload["summary"])

    def test_ui_workbench_run_view_keeps_long_session_timeline_scoped(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        large_blob = "x" * 20_000
        latest_run_id = "run-ui-long-session-099"

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            for index in range(100):
                run_id = f"run-ui-long-session-{index:03d}"
                call_id = f"call-ui-long-session-{index:03d}"
                step_id = f"step-ui-long-session-{index:03d}-tool"
                chain_id = f"chain-ui-long-session-{index:03d}"
                turn_time = timestamp + timedelta(seconds=index)
                run = OrchestrationRun(
                    id=run_id,
                    inbound_instruction=InboundInstruction(
                        source="http",
                        content=f"第 {index + 1} 轮工具任务",
                    ),
                    status=OrchestrationRunStatus.COMPLETED,
                    stage=OrchestrationRunStage.COMPLETED,
                    agent_id="assistant",
                    current_step=1,
                    result_payload={"output_text": "工具已完成。"},
                    metadata={
                        "session_key": "agent:assistant:long-session",
                        "trace_id": "trace-ui-long-session",
                        "turn_id": run_id,
                        "turn_ordinal": index + 1,
                        "request_render_snapshot_id": (
                            f"ctxsnap-ui-long-session-{index:03d}"
                        ),
                    },
                    created_at=turn_time,
                    updated_at=turn_time + timedelta(milliseconds=200),
                    started_at=turn_time,
                    completed_at=turn_time + timedelta(milliseconds=200),
                )
                chain = ExecutionChain.create(chain_id=chain_id, turn_id=run.id)
                tool_step = ExecutionStep.create(
                    step_id=step_id,
                    chain_id=chain.id,
                    turn_id=run.id,
                    step_index=0,
                    kind=ExecutionStepKind.TOOL_BATCH,
                )
                tool_step.complete()
                chain.increment_step_count()
                chain.complete()
                call_item = ExecutionStepItem.create(
                    item_id=f"item-ui-long-session-{index:03d}-call",
                    step_id=tool_step.id,
                    chain_id=chain.id,
                    turn_id=run.id,
                    item_index=0,
                    kind=ExecutionStepItemKind.TOOL_CALL,
                    owner=ExecutionOwnerReference(
                        owner_kind="tool_call",
                        owner_id=call_id,
                    ),
                    correlation_key=call_id,
                )
                call_item.complete(
                    summary_payload={
                        "tool_call_id": call_id,
                        "tool_name": "command.exec",
                        "tool_id": "command.exec",
                        "tool_execution_plan": {
                            "tool_call_id": call_id,
                            "tool_name": "command.exec",
                            "arguments_digest": (
                                f"digest-ui-long-session-{index:03d}"
                            ),
                            "arguments": {"raw": large_blob},
                        },
                        "raw_arguments": large_blob,
                    },
                )
                result_item = ExecutionStepItem.create(
                    item_id=f"item-ui-long-session-{index:03d}-result",
                    step_id=tool_step.id,
                    chain_id=chain.id,
                    turn_id=run.id,
                    item_index=1,
                    kind=ExecutionStepItemKind.TOOL_RESULT,
                    owner=ExecutionOwnerReference(
                        owner_kind="session_item",
                        owner_id=f"session-item-ui-long-session-{index:03d}",
                    ),
                    correlation_key=call_id,
                )
                result_item.complete(
                    summary_payload={
                        "tool_call_id": call_id,
                        "tool_name": "command.exec",
                        "tool_id": "command.exec",
                        "result_summary": "command completed",
                        "stdout": large_blob,
                        "provider_wire_preview": {"output": large_blob},
                    },
                )
                uow.orchestration_runs.add(run)
                uow.execution_chains.add(chain)
                uow.execution_steps.add(tool_step)
                uow.execution_step_items.add(call_item)
                uow.execution_step_items.add(result_item)
            uow.commit()

        response = self.client.get(f"/ui/workbench/runs/{latest_run_id}")

        self.assertEqual(response.status_code, 200)
        encoded = response.content.decode("utf-8")
        payload = response.json()
        self.assertEqual(len(payload["turns"]), 100)
        self.assertLess(len(encoded), 120_000)
        self.assertNotIn(large_blob, encoded)
        tool_timeline_items = [
            item
            for item in payload["timeline"]
            if item["kind"] in {"tool_call", "tool_run", "tool_result"}
        ]
        self.assertEqual(len(tool_timeline_items), 1)
        self.assertEqual(
            tool_timeline_items[0]["source_refs"]["tool_call_id"],
            "call-ui-long-session-099",
        )
        self.assertEqual(
            tool_timeline_items[0]["content"]["tool_execution_plan"][
                "arguments_digest"
            ],
            "digest-ui-long-session-099",
        )

    def test_ui_workbench_access_not_ready_projects_missing_access_step(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-missing-access",
            inbound_instruction=InboundInstruction(
                source="http",
                content="调用需要凭证的工具",
            ),
            status=OrchestrationRunStatus.FAILED,
            stage=OrchestrationRunStage.FAILED,
            agent_id="assistant",
            error=OrchestrationErrorPayload(
                message="Tool access is not ready.",
                code="access_not_ready",
                details={
                    "resource_type": "tool",
                    "resource_id": "missing_access_tool",
                    "display_name": "Missing Access Tool",
                    "access": {
                        "requirement_sets": [
                            {
                                "checks": [
                                    {
                                        "requirement": "env:MISSING_TOOL_TOKEN",
                                        "setup_flow": {"kind": "env"},
                                    },
                                ],
                            },
                        ],
                    },
                },
            ),
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-missing-access",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            completed_at=timestamp + timedelta(seconds=2),
        )

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.commit()

        response = self.client.get("/ui/workbench/runs/run-ui-missing-access/steps")
        run_response = self.client.get("/ui/workbench/runs/run-ui-missing-access")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run_response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [step["type"] for step in payload],
            ["user_input", "missing_access"],
        )
        missing_access = payload[1]
        self.assertEqual(missing_access["status"], "failed")
        self.assertIn("Missing Access Tool", missing_access["summary"])
        self.assertIn("env:MISSING_TOOL_TOKEN", missing_access["summary"])
        self.assertIn(
            ("access_requirement", "env:MISSING_TOOL_TOKEN"),
            {
                (item["type"], item["id"])
                for item in missing_access["linked_entities"]
            },
        )
        self.assertIn(
            "open_access_inventory",
            {item["id"] for item in missing_access["actions"]},
        )
        wait_items = [
            item for item in run_response.json()["timeline"] if item["kind"] == "wait_state"
        ]
        self.assertEqual(len(wait_items), 1)
        self.assertIn("Missing Access Tool", wait_items[0]["content"]["text"])

    def test_ui_workbench_chain_access_not_ready_projects_missing_access_step(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        error_details = {
            "stage": "llm",
            "resource_type": "llm_profile",
            "resource_id": "openai_codex.gpt-5.5",
            "access": {
                "requirement": "codex-oauth-default",
                "status": "setup_needed",
                "ready": False,
                "reason": "OAuth account 'openai-codex:default' was not found.",
                "setup_flow": {
                    "kind": "oauth_browser",
                    "metadata": {
                        "credential_binding_id": "codex-oauth-default",
                        "account_id": "openai-codex:default",
                    },
                },
            },
        }
        error_message = (
            "LLM profile 'openai_codex.gpt-5.5' access is not ready: "
            "OAuth account 'openai-codex:default' was not found."
        )
        run = OrchestrationRun(
            id="run-ui-chain-missing-codex-oauth",
            inbound_instruction=InboundInstruction(
                source="http",
                content="查航班",
            ),
            status=OrchestrationRunStatus.FAILED,
            stage=OrchestrationRunStage.FAILED,
            agent_id="assistant",
            error=OrchestrationErrorPayload(
                message=error_message,
                code="access_not_ready",
                details=error_details,
            ),
            metadata={
                "session_key": "agent:assistant:main",
                "requested_llm_id": "openai_codex.gpt-5.5",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            completed_at=timestamp + timedelta(seconds=2),
        )
        chain = ExecutionChain.create(
            chain_id="chain-ui-chain-missing-codex-oauth",
            turn_id=run.id,
        )
        intake_step = ExecutionStep.create(
            step_id="step-ui-chain-missing-codex-oauth-intake",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=0,
            kind=ExecutionStepKind.INTAKE,
        )
        intake_step.complete()
        chain.increment_step_count()
        llm_step = ExecutionStep.create(
            step_id="step-ui-chain-missing-codex-oauth-llm",
            chain_id=chain.id,
            turn_id=run.id,
            step_index=1,
            kind=ExecutionStepKind.LLM,
        )
        llm_step.start()
        llm_step.fail(
            message=error_message,
            code="access_not_ready",
            details=error_details,
        )
        chain.increment_step_count()
        chain.fail(
            message=error_message,
            code="access_not_ready",
            details=error_details,
        )

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.execution_chains.add(chain)
            uow.execution_steps.add(intake_step)
            uow.execution_steps.add(llm_step)
            uow.commit()

        response = self.client.get(
            "/ui/workbench/runs/run-ui-chain-missing-codex-oauth/steps",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [step["type"] for step in payload],
            ["user_input", "llm", "missing_access"],
        )
        self.assertIn("openai-codex:default", payload[1]["summary"])
        self.assertIn("### Failure guidance", payload[1]["markdown"])
        missing_access = payload[2]
        self.assertIn("codex-oauth-default", missing_access["summary"])
        self.assertIn(
            ("access_requirement", "codex-oauth-default"),
            {
                (item["type"], item["id"])
                for item in missing_access["linked_entities"]
            },
        )
        self.assertIn("open_access_inventory", {item["id"] for item in missing_access["actions"]})

    def test_ui_workbench_failed_run_exposes_user_guidance(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc)
        run = OrchestrationRun(
            id="run-ui-provider-failure-guidance",
            inbound_instruction=InboundInstruction(
                source="http",
                content="调用模型",
            ),
            status=OrchestrationRunStatus.FAILED,
            stage=OrchestrationRunStage.FAILED,
            agent_id="assistant",
            error=OrchestrationErrorPayload(
                message="provider rate limit",
                code="adapter_error",
                details={"provider": "openai"},
            ),
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-ui-provider-failure-guidance",
            },
            created_at=timestamp,
            updated_at=timestamp + timedelta(seconds=2),
            completed_at=timestamp + timedelta(seconds=2),
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.commit()

        steps_response = self.client.get(
            "/ui/workbench/runs/run-ui-provider-failure-guidance/steps",
        )
        run_response = self.client.get(
            "/ui/workbench/runs/run-ui-provider-failure-guidance",
        )

        self.assertEqual(steps_response.status_code, 200)
        self.assertEqual(run_response.status_code, 200)
        error_steps = [
            step for step in steps_response.json() if step["type"] == "error"
        ]
        self.assertEqual(len(error_steps), 1)
        self.assertIn("provider rate limit", error_steps[0]["summary"])
        self.assertIn("### Failure guidance", error_steps[0]["markdown"])
        self.assertIn("Error code: `adapter_error`", error_steps[0]["markdown"])
        self.assertIn("Operations or Trace", error_steps[0]["markdown"])
        error_timeline_items = [
            item for item in run_response.json()["timeline"] if item["kind"] == "error"
        ]
        self.assertEqual(len(error_timeline_items), 1)
        self.assertIn(
            "### Failure guidance",
            error_timeline_items[0]["content"]["markdown"],
        )

    def test_ui_workbench_run_returns_404_for_missing_run(self) -> None:
        response = self.client.get("/ui/workbench/runs/missing-run")

        self.assertEqual(response.status_code, 404)

    def test_ui_workbench_steps_hide_stale_cancelled_approval_request(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=5)
        approval = PendingApprovalRequest(
            request_id="approval-stale-cancelled",
            effect_id="workspace_search",
            label="workspace_search",
            tool_ids=("workspace_search",),
            tool_name="workspace_search",
        )
        run = OrchestrationRun(
            id="run-ui-cancelled-approval",
            inbound_instruction=InboundInstruction(
                source="http",
                content="cancelled approval",
            ),
            status=OrchestrationRunStatus.CANCELLED,
            stage=OrchestrationRunStage.CANCELLED,
            agent_id="assistant",
            pending_approval_request_payload=approval.to_payload(),
            metadata={
                "trace_id": "trace-ui-cancelled-approval",
                "session_key": "agent:assistant:main",
            },
            created_at=timestamp - timedelta(seconds=3),
            updated_at=timestamp,
            completed_at=timestamp,
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.commit()

        response = self.client.get(
            "/ui/workbench/runs/run-ui-cancelled-approval/steps",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("approval_required", [step["type"] for step in payload])
        self.assertFalse(
            any(
                action["id"].startswith("approval:")
                for step in payload
                for action in step["actions"]
            ),
        )

    def test_ui_workbench_steps_include_skill_draft_approval_detail(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=1)
        approval = PendingApprovalRequest(
            request_id="approval-skill-draft-1",
            effect_id="skill_authoring.apply",
            label="Skill authoring apply",
            reason="Apply skill draft after review.",
            tool_ids=("skill_draft_apply",),
            tool_name="skill_draft_apply",
            tool_arguments={
                "draft_id": "skill-draft:repo-review",
                "reason": "User approved.",
                "ignored": "not exposed",
            },
            execution_mode="inline",
            execution_strategy="async",
            execution_environment="local",
        )
        run = OrchestrationRun(
            id="run-ui-skill-draft-approval",
            inbound_instruction=InboundInstruction(
                source="http",
                content="apply skill draft",
            ),
            status=OrchestrationRunStatus.WAITING,
            stage=OrchestrationRunStage.WAITING_FOR_CONFIRMATION,
            agent_id="assistant",
            active_session_id="session-approval",
            pending_approval_request_payload=approval.to_payload(),
            metadata={
                "trace_id": "trace-ui-skill-draft-approval",
                "session_key": "agent:assistant:main",
            },
            created_at=timestamp - timedelta(seconds=3),
            updated_at=timestamp,
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.commit()

        response = self.client.get(
            "/ui/workbench/runs/run-ui-skill-draft-approval/steps",
        )
        run_response = self.client.get(
            "/ui/workbench/runs/run-ui-skill-draft-approval",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(run_response.status_code, 200)
        payload = response.json()
        approval_step = next(step for step in payload if step["type"] == "approval_required")
        self.assertEqual(approval_step["approval"]["request_id"], "approval-skill-draft-1")
        self.assertEqual(approval_step["approval"]["tool_name"], "skill_draft_apply")
        self.assertEqual(approval_step["approval"]["draft_id"], "skill-draft:repo-review")
        self.assertEqual(
            approval_step["approval"]["tool_arguments"],
            {
                "draft_id": "skill-draft:repo-review",
                "reason": "User approved.",
            },
        )
        self.assertIn(
            ("skill_draft", "skill-draft:repo-review"),
            {
                (item["type"], item["id"])
                for item in approval_step["linked_entities"]
            },
        )
        approval_timeline_items = [
            item for item in run_response.json()["timeline"] if item["kind"] == "approval"
        ]
        self.assertEqual(len(approval_timeline_items), 1)
        self.assertIn("Apply skill draft", approval_timeline_items[0]["content"]["text"])
        self.assertEqual(
            approval_timeline_items[0]["source_refs"]["approval_request_id"],
            "approval-skill-draft-1",
        )

    def test_orchestration_cancel_clears_pending_approval_request(self) -> None:
        approval = PendingApprovalRequest(
            request_id="approval-cancelled",
            effect_id="workspace_search",
            label="workspace_search",
            tool_ids=("workspace_search",),
        )
        run = OrchestrationRun(
            id="run-cancelled-approval",
            inbound_instruction=InboundInstruction(
                source="http",
                content="cancel approval",
            ),
            status=OrchestrationRunStatus.WAITING,
            stage=OrchestrationRunStage.WAITING_FOR_CONFIRMATION,
            pending_tool_run_ids=("tool-run-1",),
            pending_approval_request_payload=approval.to_payload(),
            worker_id="worker-1",
        )

        run.cancel(reason="user cancelled")

        self.assertIsNone(run.pending_approval_request())
        self.assertEqual(run.pending_tool_run_ids, ())
        self.assertIsNone(run.worker_id)
