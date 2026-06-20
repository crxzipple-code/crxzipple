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


class UiOperationsHttpTestCase(HttpModuleTestCase):
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


    def test_operations_orchestration_health_ignores_retained_historical_failures(
        self,
    ) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        run = OrchestrationRun(
            id="run-ui-old-failure",
            inbound_instruction=InboundInstruction(
                source="http",
                content="old failure",
            ),
            status=OrchestrationRunStatus.FAILED,
            stage=OrchestrationRunStage.FAILED,
            agent_id="assistant",
            error=OrchestrationErrorPayload(
                message="Old retained failure.",
                code="engine_failed",
            ),
            metadata={"trace_id": "trace-ui-old-failure"},
            created_at=timestamp - timedelta(seconds=3),
            updated_at=timestamp,
            completed_at=timestamp,
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.commit()

        self._materialize_operations("orchestration")
        response = self.client.get("/operations/orchestration")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["health"], "healthy")
        metrics = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metrics["failed"]["label"], "Recent Failed")
        self.assertEqual(metrics["failed"]["value"], "0")
        self.assertEqual(metrics["failed"]["delta"], "1 retained")
        self.assertEqual(payload["recent_failures"]["total"], 1)

    def test_operations_orchestration_ingress_ignores_legacy_accepted_fallback(
        self,
    ) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        run = OrchestrationRun(
            id="run-ui-legacy-accepted",
            inbound_instruction=InboundInstruction(
                source="ui.workbench",
                content="legacy accepted",
            ),
            status=OrchestrationRunStatus.ACCEPTED,
            stage=OrchestrationRunStage.ACCEPTED,
            agent_id="assistant",
            metadata={"trace_id": "trace-ui-legacy-accepted"},
            created_at=timestamp,
            updated_at=timestamp,
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(run)
            uow.commit()

        self._materialize_operations("orchestration")
        response = self.client.get("/operations/orchestration")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        metrics = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metrics["ingress"]["value"], "0")
        self.assertEqual(metrics["ingress"]["delta"], "ingress requests")
        self.assertEqual(payload["ingress_queue"]["total"], 0)
        self.assertEqual(payload["ingress_queue"]["rows"], [])

    def test_ui_operations_unknown_module_returns_404(self) -> None:
        response = self.client.get("/operations/not-a-module/overview")

        self.assertEqual(response.status_code, 404)

    def test_ui_operations_module_overviews_cover_runtime_modules(self) -> None:
        modules = {"access", "channels", "memory", "skills", "events", "daemon"}

        for module in modules:
            with self.subTest(module=module):
                self._materialize_operations(module)
                response = self.client.get(f"/operations/{module}/overview")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["module"], module)
                self.assertTrue(payload["metrics"])
                self.assertIn(payload["health"], {"healthy", "warning", "error"})

    def test_ui_operations_modules_endpoint_lists_materialized_overviews(self) -> None:
        selected_modules = {"access", "daemon"}
        self._materialize_operations(*selected_modules)

        response = self.client.get("/operations/modules")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["module"] for item in payload],
            [
                module
                for module in OPERATIONS_PROJECTION_MODULES
                if module in selected_modules
            ],
        )
        self.assertTrue(all(item["metrics"] for item in payload))

    def test_ui_operations_module_pages_expose_named_sections(self) -> None:
        expected_sections = {
            "context_workspace": {
                "workspaces",
                "visible_nodes",
                "node_status",
                "snapshots",
                "observation_slices",
                "context_budget",
                "diagnostics",
            },
        }

        for module, section_ids in expected_sections.items():
            with self.subTest(module=module):
                self._materialize_operations(module)
                response = self.client.get(f"/operations/{module}")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["module"], module)
                self.assertEqual(
                    {section["id"] for section in payload["sections"]},
                    section_ids,
                )
                self.assertEqual(
                    [tab["id"] for tab in payload["tabs"]],
                    [section["id"] for section in payload["sections"]],
                )

    def test_ui_operations_skills_page_uses_skill_catalog_state(self) -> None:
        container = self.client.app.state.container
        seed_catalog_tool(
            container,
            tool_id="ui_skill_ready_tool",
            name="UI Skill Ready Tool",
            description="Tool used by UI skills operations tests.",
        )
        system_root = container.require(AppKey.SKILL_MANAGER).repository._system_root
        _write_skill_package(
            system_root / "ui-skill-ready",
            name="ui-skill-ready",
            description="Ready skill for operations UI.",
            instructions="# UI Skill Ready\n\nUse the ready tool.\n",
            tags=("ops",),
            required_tools=("ui_skill_ready_tool",),
        )
        _write_skill_package(
            system_root / "ui-skill-missing",
            name="ui-skill-missing",
            description="Missing tool skill for operations UI.",
            instructions="# UI Skill Missing\n\nNeeds a missing tool.\n",
            tags=("ops",),
            required_tools=("ui_skill_missing_tool",),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="skills.resolution.completed",
                kind="observe",
                payload={
                    "skill": "ui-skill-ready",
                    "skill_name": "ui-skill-ready",
                    "surface": "interactive",
                    "status": "setup_needed",
                    "ready_count": 1,
                    "setup_needed_count": 1,
                    "total_count": 2,
                    "missing_tools": ["ui_skill_missing_tool"],
                },
                trace={"trace_id": "trace-skills-ui-direct"},
            )
        )
        self._process_operations_events()

        self._materialize_operations("skills")
        response = self.client.get(
            "/operations/skills",
            params={"search": "ui-skill"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "skills")
        self.assertNotIn("sections", payload)

        metric_ids = {item["id"] for item in payload["metrics"]}
        self.assertIn("installed_skills", metric_ids)
        self.assertIn("ready_skills", metric_ids)
        self.assertIn("missing_capabilities", metric_ids)

        installed_rows = payload["recently_resolved_skills"]["rows"]
        self.assertEqual(payload["recently_resolved_skills"]["total"], 2)
        status_by_skill = {
            row["cells"]["skill"]: row["cells"]["status"]
            for row in installed_rows
        }
        self.assertEqual(status_by_skill["ui-skill-ready"], "Ready")
        self.assertEqual(status_by_skill["ui-skill-missing"], "Setup Needed")

        missing_rows = payload["missing_capabilities"]["rows"]
        self.assertTrue(
            any(row["cells"]["required"] == "ui_skill_missing_tool" for row in missing_rows)
        )
        capability_rows = payload["capability_requirements"]["rows"]
        self.assertTrue(
            any(row["cells"]["capability"] == "ui_skill_ready_tool" for row in capability_rows)
        )
        self.assertTrue(
            any(row["cells"]["capability"] == "ui_skill_missing_tool" for row in capability_rows)
        )
        self.assertGreaterEqual(payload["resolution_logs"]["total"], 1)
        self.assertIn("skill_reads", payload)
        self.assertTrue(
            any(
                row["cells"]["event"] == "resolution.completed"
                and row["cells"]["skill"] == "ui-skill-ready"
                for row in payload["resolution_logs"]["rows"]
            )
        )
        self.assertTrue(payload["skill_details"])
        self.assertIn(
            "ui-skill-ready",
            {item["skill_id"] for item in payload["skill_details"]},
        )
        self.assertTrue(
            any(
                item["skill_id"] == "ui-skill-ready"
                and item["events"]["total"] >= 1
                for item in payload["skill_details"]
            )
        )
        sync_response = self.client.post(
            "/operations/skills/sync",
            json={"surface": "interactive", "reason": "test skill operations sync"},
        )
        self.assertEqual(sync_response.status_code, 200)
        sync_payload = sync_response.json()
        self.assertGreaterEqual(sync_payload["synced_count"], 2)
        self.assertIn(
            "ui-skill-ready",
            {item["name"] for item in sync_payload["skills"]},
        )

    def test_ui_operations_memory_page_uses_file_memory_runtime_state(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "memory-ui-agent-home"
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "memory-ui-agent",
                    "name": "Memory UI Agent",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "runtime_preferences": {"home_dir": str(home_dir)},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            daily_response = self.client.post(
                "/memory/daily",
                json={
                    "agent_id": "memory-ui-agent",
                    "content": "Remember the benchmark plan for memory operations.",
                    "title": "Benchmark Plan",
                },
            )
            self.assertEqual(daily_response.status_code, 201)
            daily_path = daily_response.json()["path"]

            long_term_response = self.client.post(
                "/memory/long-term",
                json={
                    "agent_id": "memory-ui-agent",
                    "content": "# Preferences\nUse concise operational notes.\n",
                },
            )
            self.assertEqual(long_term_response.status_code, 201)
            search_response = self.client.get(
                "/memory/search",
                params={"agent_id": "memory-ui-agent", "query": "benchmark"},
            )
            self.assertEqual(search_response.status_code, 200)
            container = self.client.app.state.container
            self._process_operations_events()
            container.require(AppKey.EVENTS_SERVICE).publish(
                Event(
                    name="memory.index.sync_succeeded",
                    kind="observe",
                    payload={
                        "space_id": "memory-ui-agent",
                        "owner_id": "memory-ui-agent",
                        "path": daily_path,
                        "changed_path_count": 1,
                        "reindexed_files": 1,
                        "chunk_count": 2,
                        "duration_ms": 7,
                        "status": "succeeded",
                    },
                    trace={"trace_id": "trace-memory-ui-direct"},
                )
            )

            self._materialize_operations("memory")
            response = self.client.get(
                "/operations/memory",
                params={
                    "agent_id": "memory-ui-agent",
                    "search": "benchmark",
                    "limit": 20,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "memory")
        self.assertNotIn("sections", payload)

        metric_ids = {item["id"] for item in payload["metrics"]}
        self.assertIn("memory_stores", metric_ids)
        self.assertIn("indexed_files", metric_ids)
        self.assertIn("retrieval_hits", metric_ids)
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(
            metric_by_id["watch_failures"]["delta"],
            "watcher and observed memory errors",
        )

        self.assertGreaterEqual(payload["memory_stores"]["total"], 1)
        store_rows = payload["memory_stores"]["rows"]
        self.assertTrue(
            any(row["cells"]["agent"] == "memory-ui-agent" for row in store_rows)
        )

        source_paths = {
            row["cells"]["file"] for row in payload["source_files"]["rows"]
        }
        self.assertIn(daily_path, source_paths)
        self.assertGreaterEqual(payload["index_sync_activity"]["total"], 1)
        self.assertTrue(
            any(
                row["cells"]["operation"] == "index.sync_succeeded"
                and row["cells"]["space_id"] == "memory-ui-agent"
                for row in payload["index_sync_activity"]["rows"]
            )
        )
        self.assertEqual(payload["file_details"], [])
        detail_response = self.client.get(
            f"/operations/memory/files/memory-ui-agent:{daily_path}/detail",
        )
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertTrue(detail_payload["file_id"].endswith(daily_path))
        self.assertGreaterEqual(detail_payload["related"]["total"], 1)
        self.assertGreaterEqual(payload["memory_usage"]["total"], 1)
        self.assertGreaterEqual(payload["index_jobs"]["total"], 1)
        self.assertGreaterEqual(payload["context_resolution"]["total"], 1)
        self.assertGreaterEqual(payload["index_sync_activity"]["total"], 1)
        self.assertGreaterEqual(payload["source_scan_status"]["total"], 1)
        event_names = {
            row["cells"]["event"]
            for row in payload["recent_retrieval_logs"]["rows"]
        }
        self.assertIn("retrieval.succeeded", event_names)
        self.assertTrue(
            any(
                row["cells"]["operation"] == "index.sync_succeeded"
                or row["cells"]["operation"] == "index.marked_dirty"
                for row in payload["index_sync_activity"]["rows"]
            )
        )
        self.assertEqual(detail_payload["raw_payload"]["file"]["path"], daily_path)

    def test_ui_operations_access_page_uses_access_inventory_state(self) -> None:
        container = self.client.app.state.container
        previous = os.environ.pop("UI_ACCESS_MISSING_TOKEN", None)
        container.require(AppKey.SETTINGS_ACTION_SERVICE).create_resource(
            CreateSettingsResourceInput(
                resource_id="ui-access-missing-token",
                resource_kind="access-assets",
                owner_module="access",
                payload={
                    "config_id": "ui-access-missing-token",
                    "assets": (
                        {
                            "asset_id": "ui_access_missing_token",
                            "asset_kind": "env",
                            "display_name": "UI Access Missing Token",
                            "governance_scope": "tool",
                            "status": "active",
                        },
                    ),
                    "consumer_bindings": (
                        {
                            "binding_id": "ui_access_missing_tool_access",
                            "consumer_module": "tool",
                            "consumer_kind": "tool",
                            "consumer_id": "ui_access_missing_tool",
                            "display_name": "UI Access Missing Tool",
                            "asset_id": "ui_access_missing_token",
                            "requirement_sets": (
                                ("env:UI_ACCESS_MISSING_TOKEN",),
                            ),
                            "status": "active",
                        },
                    ),
                },
                display_name="UI Access Missing Token",
                reason="seed settings-owned access inventory test data",
                publish=True,
                source="test",
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic=f"events.named.{ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT}",
                kind="fact",
                payload={
                    "event_name": ACCESS_CREDENTIAL_RESOLVE_FAILED_EVENT,
                    "requirement": "env:UI_ACCESS_MISSING_TOKEN",
                    "status": "failed",
                    "reason": "UI access token is missing",
                },
                trace={"trace_id": "trace-access-ui"},
            ),
        )

        try:
            self._materialize_operations("access")
            response = self.client.get(
                "/operations/access?search=UI_ACCESS_MISSING_TOKEN"
            )
        finally:
            if previous is not None:
                os.environ["UI_ACCESS_MISSING_TOKEN"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "access")
        self.assertNotIn("sections", payload)

        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metric_by_id["missing_access"]["value"], "1")
        self.assertEqual(metric_by_id["setup_available"]["value"], "1")
        self.assertEqual(metric_by_id["failed_auth"]["value"], "1")

        target_rows = payload["access_targets"]["rows"]
        self.assertEqual(payload["access_targets"]["total"], 1)
        self.assertEqual(target_rows[0]["cells"]["requirements"], "env:UI_ACCESS_MISSING_TOKEN")
        self.assertEqual(target_rows[0]["cells"]["setup"], "Available")
        self.assertEqual(target_rows[0]["cells"]["required_by"], "tool: ui_access_missing_tool")

        self.assertEqual(payload["missing_access"]["total"], 1)
        self.assertEqual(payload["access_requirements"]["total"], 1)
        self.assertEqual(
            payload["access_requirements"]["rows"][0]["cells"]["slot"],
            "env:UI_ACCESS_MISSING_TOKEN",
        )
        self.assertEqual(payload["provider_auth_blocked"]["total"], 1)
        self.assertEqual(payload["setup_flows"]["total"], 1)
        self.assertEqual(
            payload["setup_flows"]["rows"][0]["cells"]["requirement"],
            "env:UI_ACCESS_MISSING_TOKEN",
        )
        self.assertEqual(payload["access_usage"]["total"], 1)

        detail_by_id = {
            item["target_id"]: item for item in payload["target_details"]
        }
        self.assertIn(target_rows[0]["id"], detail_by_id)
        detail = detail_by_id[target_rows[0]["id"]]
        self.assertEqual(detail["checks"]["total"], 1)
        self.assertEqual(detail["setup"]["total"], 1)
        self.assertEqual(detail["usages"]["total"], 1)
        self.assertEqual(detail["events"]["total"], 1)
        self.assertEqual(payload["recent_access_events"]["total"], 1)
        self.assertEqual(payload["access_audit_summary"]["total"], 1)
        self.assertEqual(
            payload["recent_access_events"]["rows"][0]["cells"]["trace"],
            "trace-access-ui",
        )

    def test_ui_operations_daemon_overview_reads_projection_without_runtime_refresh(self) -> None:
        container = self.client.app.state.container
        original = container.require(AppKey.DAEMON_MANAGER).list_instances
        refresh_values: list[bool] = []

        def list_instances_spy(*, service_key=None, refresh=True):
            refresh_values.append(refresh)
            return original(service_key=service_key, refresh=False)

        container.require(AppKey.DAEMON_MANAGER).list_instances = list_instances_spy
        try:
            self._materialize_operations("daemon")
            response = self.client.get("/operations/daemon/overview")
        finally:
            container.require(AppKey.DAEMON_MANAGER).list_instances = original

        self.assertEqual(response.status_code, 200)
        self.assertTrue(refresh_values)
        self.assertNotIn(True, refresh_values)

    def test_ui_operations_daemon_page_uses_materialized_runtime_state(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=3)
        daemon_process = subprocess.Popen(["sleep", "60"], start_new_session=True)
        self.addCleanup(_terminate_subprocess, daemon_process)
        process_session = ProcessSession(
            id=f"proc-daemon-ui-tool-{uuid4().hex}",
            command="printf daemon-process-output",
            shell="/bin/sh",
            working_directory=str(Path.cwd()),
            session_key="daemon:worker:tool",
            metadata={
                "daemon_service_key": "worker:tool",
                "daemon_worker_id": "worker-tool-ui-1",
            },
            pid=daemon_process.pid,
            status=ProcessStatus.RUNNING,
            exit_code=None,
            started_at=timestamp,
            updated_at=timestamp,
            ended_at=None,
        )
        container.require(AppKey.PROCESS_SERVICE).repository.save(process_session)
        container.require(AppKey.PROCESS_SERVICE).repository.stdout_path(process_session.id).write_text(
            "daemon process ready\n",
            encoding="utf-8",
        )
        instance = DaemonInstance(
            id="daemon-ui-tool-worker",
            service_key="worker:tool",
            status="ready",
            worker_id="worker-tool-ui-1",
            pid=4312,
            endpoint="http://127.0.0.1:9012",
            started_at=timestamp,
            last_healthcheck_at=datetime.now(timezone.utc),
            metadata={
                "process_id": process_session.id,
                "env_fingerprint": "fingerprint-ui-a",
                "env_keys": ["PYTHONPATH", "APP_EVENTS_BACKEND"],
                "env_drift_detected": True,
                "expected_env_fingerprint": "fingerprint-ui-b",
                "actual_env_fingerprint": "fingerprint-ui-a",
            },
        )
        container.require(AppKey.DAEMON_SERVICE).save_instance(instance)
        lease = container.require(AppKey.DAEMON_SERVICE).acquire_lease(
            service_key="worker:tool",
            owner_kind="ui_test",
            owner_id="daemon_page",
            ttl_seconds=600,
            metadata={"reason": "operations page"},
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="daemon.instance.ready",
                kind="observe",
                payload={
                    "event_name": "daemon.instance.ready",
                    "instance_id": instance.id,
                    "service_key": instance.service_key,
                    "worker_id": instance.worker_id,
                    "process_id": process_session.id,
                    "status": "ready",
                    "message": "daemon worker ready",
                },
                occurred_at=timestamp + timedelta(seconds=5),
                trace={"trace_id": "trace-daemon-ui-direct"},
                ordering_key=instance.id,
            ),
        )
        original = container.require(AppKey.DAEMON_MANAGER).list_instances
        refresh_values: list[bool] = []

        def list_instances_spy(*, service_key=None, refresh=True):
            refresh_values.append(refresh)
            return original(service_key=service_key, refresh=False)

        container.require(AppKey.DAEMON_MANAGER).list_instances = list_instances_spy
        try:
            self._materialize_operations("daemon")
            response = self.client.get("/operations/daemon?service_key=worker:tool")
        finally:
            container.require(AppKey.DAEMON_MANAGER).list_instances = original

        self.assertEqual(response.status_code, 200)
        self.assertTrue(refresh_values)
        self.assertNotIn(True, refresh_values)
        payload = response.json()
        self.assertEqual(payload["module"], "daemon")
        self.assertNotIn("sections", payload)
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertGreaterEqual(int(metric_by_id["env_drift"]["value"]), 1)
        self.assertGreaterEqual(int(metric_by_id["events"]["value"]), 1)
        direct_event_row = next(
            item
            for item in payload["daemon_events"]["rows"]
            if item["cells"]["trace"] == "trace-daemon-ui-direct"
        )
        self.assertEqual(direct_event_row["cells"]["event"], "instance.ready")
        self.assertEqual(direct_event_row["cells"]["service_key"], "worker:tool")
        self.assertGreaterEqual(payload["instances"]["total"], 1)
        instance_row = next(
            item
            for item in payload["instances"]["rows"]
            if item["id"] == "daemon-ui-tool-worker"
        )
        self.assertEqual(instance_row["id"], "daemon-ui-tool-worker")
        self.assertEqual(instance_row["cells"]["service_key"], "worker:tool")
        self.assertEqual(instance_row["cells"]["env_drift"], "Yes")
        self.assertGreaterEqual(payload["leases"]["total"], 1)
        self.assertIn(lease.id, {item["id"] for item in payload["leases"]["rows"]})
        drain_items = {
            item["label"]: item["value"]
            for item in payload["drain_overview"]["items"]
        }
        self.assertEqual(drain_items["Executor Max Assignments"], "4")
        self.assertEqual(drain_items["Tool Worker Max In-flight"], "4")
        tab_ids = {item["id"] for item in payload["tabs"]}
        self.assertIn("processes", tab_ids)
        self.assertGreaterEqual(payload["processes"]["total"], 1)
        process_row = next(
            item
            for item in payload["processes"]["rows"]
            if item["id"] == process_session.id
        )
        self.assertEqual(process_row["cells"]["service_key"], "worker:tool")
        self.assertEqual(process_row["cells"]["status"], "Running")
        self.assertEqual(process_row["cells"]["binding"], "Bound")
        service_rows = {item["id"]: item for item in payload["services"]["rows"]}
        self.assertGreaterEqual(
            int(service_rows["worker:tool"]["cells"]["active_leases"]),
            1,
        )
        instance_details = {
            item["instance_id"]: item for item in payload["instance_details"]
        }
        self.assertIn("daemon-ui-tool-worker", instance_details)
        self.assertGreaterEqual(
            instance_details["daemon-ui-tool-worker"]["events"]["total"],
            1,
        )
        environment_items = {
            item["label"]: item["value"]
            for item in instance_details["daemon-ui-tool-worker"]["environment"]["items"]
        }
        self.assertEqual(environment_items["Drift Detected"], "Yes")
        action_by_id = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(
            action_by_id["healthcheck_service"]["endpoint"],
            "/operations/daemon/services/{service_key}/healthcheck",
        )
        process_segments = {
            item["id"]: item["value"]
            for item in payload["process_health"]["segments"]
        }
        self.assertGreaterEqual(process_segments["running"], 1)
        process_details = {
            item["process_id"]: item for item in payload["process_details"]
        }
        self.assertIn(process_session.id, process_details)
        self.assertEqual(process_details[process_session.id]["output"]["total"], 1)
        lease_segments = {
            item["id"]: item["value"]
            for item in payload["lease_health"]["segments"]
        }
        self.assertGreaterEqual(lease_segments["active"], 1)

    def test_ui_operations_daemon_page_reports_missing_process_sessions(self) -> None:
        container = self.client.app.state.container
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=2)
        missing_process_id = f"missing-daemon-proc-{uuid4().hex}"
        instance = DaemonInstance(
            id="daemon-ui-missing-process",
            service_key="worker:tool",
            status="ready",
            worker_id="worker-tool-ui-missing",
            pid=98765,
            endpoint=None,
            started_at=timestamp,
            last_healthcheck_at=timestamp,
            metadata={
                "process_id": missing_process_id,
                "session_key": "daemon:worker:tool",
                "command": "python -m crxzipple.main tool-worker run",
            },
        )
        container.require(AppKey.DAEMON_SERVICE).save_instance(instance)

        self._materialize_operations("daemon")
        response = self.client.get("/operations/daemon?service_key=worker:tool")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        instance_row = next(
            item
            for item in payload["instances"]["rows"]
            if item["id"] == "daemon-ui-missing-process"
        )
        self.assertEqual(instance_row["cells"]["status"], "Ready")
        process_row = next(
            item
            for item in payload["processes"]["rows"]
            if item["id"] == missing_process_id
        )
        self.assertEqual(process_row["cells"]["status"], "Missing")
        self.assertEqual(process_row["cells"]["binding"], "Missing Session")
        self.assertEqual(process_row["cells"]["output"], "stderr")

    def test_ui_operations_daemon_health_ignores_historical_process_failures(self) -> None:
        container = self.client.app.state.container
        ended_at = datetime.now(timezone.utc) - timedelta(days=2)
        process_session = ProcessSession(
            id=f"historical-daemon-failed-{uuid4().hex}",
            command="python -m crxzipple.main old-worker",
            shell="/bin/sh",
            working_directory=str(Path.cwd()),
            session_key="daemon:worker:tool",
            metadata={"daemon_service_key": "worker:tool"},
            pid=12345,
            status=ProcessStatus.FAILED,
            exit_code=1,
            started_at=ended_at - timedelta(minutes=5),
            updated_at=ended_at,
            ended_at=ended_at,
        )
        container.require(AppKey.PROCESS_SERVICE).repository.save(process_session)

        self._materialize_operations("daemon")
        response = self.client.get("/operations/daemon")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotEqual(payload["health"], "error")
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertNotEqual(metric_by_id["processes"]["tone"], "danger")

    def test_ui_operations_tool_overview_uses_tool_runtime_state(self) -> None:
        container = self.client.app.state.container
        seed_catalog_tool(
            container,
            tool_id="ui_background_tool",
            name="UI Background Tool",
            description="Tool used by UI operations tests.",
            supported_modes=(ToolMode.BACKGROUND,),
            requires_confirmation=True,
        )
        asyncio.run(
            container.require(AppKey.TOOL_SERVICE).execute(
                ExecuteToolInput(
                    tool_id="ui_background_tool",
                    mode=ToolMode.BACKGROUND,
                    run_id="tool-run-ui-ops",
                ),
            ),
        )
        self._materialize_operations("tool")

        response = self.client.get("/operations/tool/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "tool")
        self.assertEqual(payload["title"], "Tool")
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metric_by_id["active_runs"]["value"], "1")
        self.assertGreaterEqual(int(metric_by_id["confirmation"]["value"]), 1)
        self.assertIn(
            {
                "Priority": "background",
                "Run ID": "tool-run-ui-ops",
                "Lane Key": "ui_background_tool",
                "Wait Reason": "queued",
                "Wait Time": payload["queue"][0]["Wait Time"],
            },
            payload["queue"],
        )
        self.assertTrue(payload["lane_locks"])

    def test_ui_operations_tool_page_uses_tool_runtime_state(self) -> None:
        container = self.client.app.state.container
        seed_catalog_tool(
            container,
            tool_id="ui_background_tool",
            name="UI Background Tool",
            description="Tool used by UI operations page tests.",
            supported_modes=(ToolMode.BACKGROUND,),
            requires_confirmation=True,
            access_requirements=("env:UI_ACCESS_MISSING_TOKEN",),
        )
        seed_catalog_tool(
            container,
            tool_id="ui_inline_tool",
            name="UI Inline Tool",
            description="Inline tool used by UI operations page tests.",
        )
        seed_catalog_tool(
            container,
            tool_id="openai_image_generate_ui",
            name="OpenAI Image Generate UI",
            description="OpenAI image tool used by UI operations page tests.",
            supported_modes=(ToolMode.BACKGROUND,),
            tags=("openai", "image", "generation"),
            runtime_key="openai_image_generate",
        )
        stored_artifact = container.require(AppKey.ARTIFACT_SERVICE).create_artifact(
            data=b"tool output",
            mime_type="text/plain",
            name="tool-output.txt",
        )
        timestamp = datetime.now(timezone.utc) - timedelta(minutes=7)
        queued_run = ToolRun.create(
            run_id="tool-run-ui-page-queued",
            tool_id="ui_background_tool",
            input_payload={"prompt": "queue"},
            metadata={
                "source": "orchestration",
                "orchestration_run_id": "run-tool-source",
            },
            invocation_context_payload={
                "run_id": "run-tool-source",
                "step_id": "step-tool-source",
                "trace_id": "trace-tool-page",
            },
            target=ToolExecutionTarget(mode=ToolMode.BACKGROUND),
        )
        queued_run.created_at = timestamp
        queued_run.queue()
        running_run = ToolRun.create(
            run_id="tool-run-ui-page-running",
            tool_id="ui_background_tool",
            input_payload={"prompt": "run"},
            metadata={
                "source": "orchestration",
                "orchestration_run_id": "run-tool-source",
            },
            invocation_context_payload={
                "run_id": "run-tool-source",
                "trace_id": "trace-tool-page",
            },
            target=ToolExecutionTarget(mode=ToolMode.BACKGROUND),
        )
        running_run.created_at = timestamp + timedelta(seconds=5)
        running_run.dispatch(worker_id="tool-worker-ui", lease_seconds=600)
        running_run.start()
        running_run.started_at = timestamp + timedelta(seconds=6)
        running_run.heartbeat_at = datetime.now(timezone.utc)
        running_run.lease_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=600,
        )
        worker = ToolWorkerRegistration.create(
            worker_id="tool-worker-ui",
            lease_seconds=600,
            max_in_flight=2,
        )
        worker.reserve_slot()
        worker.heartbeat_at = datetime.now(timezone.utc)
        worker.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=600)
        worker.capabilities_payload = {
            "runtime_metrics": {
                "counters": [],
                "gauges": [
                    {
                        "name": "tool.remote_provider_limiter.active",
                        "labels": {"provider_key": "provider:ui-image"},
                        "value": 1.0,
                    },
                    {
                        "name": "tool.remote_provider_limiter.waiters",
                        "labels": {"provider_key": "provider:ui-image"},
                        "value": 2.0,
                    },
                ],
                "timings": [
                    {
                        "name": "tool.remote_provider_limiter.wait_seconds",
                        "labels": {"provider_key": "provider:ui-image"},
                        "count": 3,
                        "total_seconds": 1.5,
                        "max_seconds": 0.75,
                        "avg_seconds": 0.5,
                    },
                ],
            },
            "runtime_registry": {
                "registrations": [
                    {
                        "runtime_key": "ui-image.generate",
                        "concurrency_key": "provider:ui-image",
                        "max_concurrency": 3,
                    },
                ],
            },
        }
        assignment = ToolRunAssignment.create(
            assignment_id="assignment-ui-tool-page",
            run_id=running_run.id,
            tool_id=running_run.tool_id,
            worker_id=worker.id,
            attempt_count=running_run.attempt_count,
            lease_seconds=600,
        )
        assignment.start()
        assignment.assigned_at = timestamp + timedelta(seconds=6)
        assignment.started_at = timestamp + timedelta(seconds=7)
        assignment.heartbeat_at = datetime.now(timezone.utc)
        assignment.lease_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=600,
        )
        failed_run = ToolRun.create(
            run_id="tool-run-ui-page-failed",
            tool_id="ui_inline_tool",
            input_payload={"prompt": "fail"},
            metadata={
                "source": "orchestration",
                "orchestration_run_id": "run-tool-source",
            },
            invocation_context_payload={
                "run_id": "run-tool-source",
                "trace_id": "trace-tool-page",
            },
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        failed_run.created_at = timestamp + timedelta(seconds=10)
        failed_run.start()
        failed_run.fail("403 Provider Access missing")
        failed_run.started_at = timestamp + timedelta(seconds=12)
        failed_run.completed_at = timestamp + timedelta(seconds=18)
        failed_run.heartbeat_at = failed_run.completed_at
        artifact_run = ToolRun.create(
            run_id="tool-run-ui-page-artifact",
            tool_id="ui_inline_tool",
            input_payload={"prompt": "artifact"},
            metadata={
                "source": "orchestration",
                "orchestration_run_id": "run-tool-source",
            },
            invocation_context_payload={
                "run_id": "run-tool-source",
                "trace_id": "trace-tool-page",
            },
            target=ToolExecutionTarget(mode=ToolMode.INLINE),
        )
        artifact_run.created_at = timestamp + timedelta(seconds=20)
        artifact_run.start()
        artifact_run.succeed(
            ToolRunResult.text(
                "artifact ready",
                metadata={"artifact_ids": [stored_artifact.id]},
            ),
        )
        artifact_run.started_at = timestamp + timedelta(seconds=22)
        artifact_run.completed_at = timestamp + timedelta(seconds=30)
        artifact_run.heartbeat_at = artifact_run.completed_at

        source_run = OrchestrationRun(
            id="run-tool-source",
            inbound_instruction=InboundInstruction(
                source="http",
                content="Run UI tool.",
            ),
            status=OrchestrationRunStatus.RUNNING,
            stage=OrchestrationRunStage.TOOL,
            agent_id="assistant",
            metadata={
                "session_key": "agent:assistant:tool",
                "trace_id": "trace-tool-page",
                "turn_id": "turn-tool-source",
            },
        )
        tool_chain = ExecutionChain.create(
            chain_id="chain-ui-tool-ops-page",
            turn_id=source_run.id,
        )
        tool_step = ExecutionStep.create(
            step_id="step-ui-tool-ops-page",
            chain_id=tool_chain.id,
            turn_id=source_run.id,
            step_index=0,
            kind=ExecutionStepKind.TOOL_BATCH,
        )
        tool_step.start()
        tool_chain.increment_step_count()
        tool_item = ExecutionStepItem.create(
            item_id="item-ui-tool-ops-page-running",
            step_id=tool_step.id,
            chain_id=tool_chain.id,
            turn_id=source_run.id,
            item_index=0,
            kind=ExecutionStepItemKind.TOOL_RUN,
            owner=ExecutionOwnerReference(
                owner_kind="tool_run",
                owner_id=running_run.id,
            ),
            correlation_key="call-ui-tool-running",
        )
        tool_item.start()

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(source_run)
            uow.tool_runs.add(queued_run)
            uow.tool_runs.add(running_run)
            uow.tool_runs.add(failed_run)
            uow.tool_runs.add(artifact_run)
            uow.execution_chains.add(tool_chain)
            uow.execution_steps.add(tool_step)
            uow.execution_step_items.add(tool_item)
            uow.tool_workers.add(worker)
            uow.tool_run_assignments.add(assignment)
            uow.commit()

        async def _ui_image_handler(arguments):  # noqa: ANN001
            return ToolRunResult.text("ok")

        container.require(AppKey.TOOL_REMOTE_RUNTIME_REGISTRY).register(
            "ui-image.generate",
            _ui_image_handler,
            concurrency_key="provider:ui-image",
            max_concurrency=3,
        )

        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="tool.run.queued",
                payload={
                    "run_id": queued_run.id,
                    "tool_id": queued_run.tool_id,
                    "status": "queued",
                    "mode": queued_run.target.mode.value,
                },
                occurred_at=timestamp + timedelta(seconds=1),
                trace={"trace_id": "trace-tool-page"},
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="tool.assignment.started",
                payload={
                    "assignment_id": assignment.id,
                    "run_id": running_run.id,
                    "tool_id": running_run.tool_id,
                    "worker_id": worker.id,
                    "status": "running",
                    "attempt_count": assignment.attempt_count,
                },
                occurred_at=timestamp + timedelta(seconds=8),
                trace={"trace_id": "trace-tool-page"},
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="tool.run.failed",
                payload={
                    "run_id": failed_run.id,
                    "tool_id": failed_run.tool_id,
                    "status": "failed",
                    "error_message": "403 Provider Access missing",
                    "mode": failed_run.target.mode.value,
                },
                occurred_at=timestamp + timedelta(seconds=19),
                trace={"trace_id": "trace-tool-page"},
            ),
        )
        self._process_operations_events()
        self._materialize_operations("tool")

        response = self.client.get("/operations/tool")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "tool")
        self.assertEqual(payload["role"]["scope"], "tool")
        self.assertEqual(payload["tool_runs"]["total"], 4)
        for legacy_key in (
            "running_tools",
            "waiting_tools",
            "long_running_runs",
            "failed_tools",
        ):
            self.assertNotIn(legacy_key, payload)
        self.assertEqual(payload["tool_queue"]["total"], 1)
        tab_ids = {item["id"] for item in payload["tabs"]}
        self.assertIn("runs", tab_ids)
        self.assertNotIn("running", tab_ids)
        self.assertNotIn("waiting", tab_ids)
        self.assertNotIn("failures", tab_ids)
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metric_by_id["active_runs"]["value"], "2")
        self.assertGreaterEqual(int(metric_by_id["confirmation"]["value"]), 1)
        self.assertEqual(metric_by_id["worker_policy"]["value"], "4")
        self.assertEqual(metric_by_id["retry_policy"]["value"], "3x / 30s / 5s")
        self.assertEqual(payload["tool_types"]["title"], "Tool Call Share")
        self.assertEqual(payload["tool_types"]["total"], 4)
        tool_call_segments = {
            item["id"]: item for item in payload["tool_types"]["segments"]
        }
        self.assertEqual(tool_call_segments["ui_background_tool"]["value"], 2)
        self.assertEqual(
            tool_call_segments["ui_background_tool"]["label"],
            "UI Background Tool",
        )
        self.assertEqual(tool_call_segments["ui_inline_tool"]["value"], 2)

        run_rows = {item["id"]: item for item in payload["tool_runs"]["rows"]}
        self.assertEqual(
            run_rows["tool-run-ui-page-queued"]["cells"]["source"],
            "run-tool-source / step-tool-source",
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-queued"]["cells"]["trace"],
            "trace-tool-page",
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-running"]["cells"]["source"],
            "run-tool-source / call-ui-tool-running",
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-running"]["cells"]["chain_id"],
            tool_chain.id,
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-running"]["cells"]["step_id"],
            tool_step.id,
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-running"]["cells"]["trace_route"],
            "/workbench/traces/trace-tool-page?focus_id=tool-run-ui-page-running",
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-running"]["cells"]["assignment_status"],
            "Running",
        )
        self.assertEqual(
            run_rows["tool-run-ui-page-running"]["cells"]["lease_state"],
            "Active",
        )
        worker_segments = {
            item["id"]: item["value"] for item in payload["worker_pool"]["segments"]
        }
        self.assertEqual(payload["worker_pool"]["total"], 1)
        self.assertEqual(worker_segments["active"], 1)
        worker_rows = {item["id"]: item for item in payload["workers"]["rows"]}
        self.assertEqual(payload["workers"]["total"], 1)
        self.assertEqual(worker_rows[worker.id]["cells"]["status"], "Active")
        self.assertEqual(worker_rows[worker.id]["cells"]["current_run"], running_run.id)
        self.assertEqual(worker_rows[worker.id]["cells"]["load"], "1/2")
        worker_details = {
            item["worker_id"]: item for item in payload["worker_details"]
        }
        self.assertIn(worker.id, worker_details)
        worker_detail = worker_details[worker.id]
        worker_summary = {
            item["label"]: item["value"] for item in worker_detail["summary"]
        }
        self.assertEqual(worker_summary["Worker Load"], "1/2")
        self.assertEqual(worker_summary["Current Run"], running_run.id)
        self.assertEqual(
            worker_detail["runtimes"]["rows"][0]["cells"]["provider"],
            "ui-image",
        )
        provider_limit_row = worker_detail["provider_limits"]["rows"][0]
        self.assertEqual(provider_limit_row["cells"]["provider"], "ui-image")
        self.assertEqual(provider_limit_row["cells"]["capacity"], "1/3")
        self.assertEqual(provider_limit_row["cells"]["waiting"], "2")
        self.assertIn("runtime_registry", worker_detail["raw_payload"])
        queue_rows = {item["id"]: item for item in payload["tool_queue"]["rows"]}
        self.assertEqual(set(queue_rows), {"waiting for scheduler"})
        self.assertEqual(queue_rows["waiting for scheduler"]["cells"]["count"], "1")
        capability_rows = {
            item["id"]: item for item in payload["capability_limits"]["rows"]
        }
        self.assertIn("tool:*", capability_rows)
        self.assertEqual(
            capability_rows["tool:*"]["cells"]["capability"],
            "Default tool groups",
        )
        self.assertEqual(capability_rows["tool:*"]["cells"]["active"], "1")
        self.assertEqual(capability_rows["tool:*"]["cells"]["waiting"], "1")
        self.assertEqual(capability_rows["tool:*"]["cells"]["limit"], "4/worker")
        provider_rows = {
            item["id"]: item for item in payload["provider_limits"]["rows"]
        }
        self.assertGreaterEqual(payload["provider_limits"]["total"], 1)
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["provider"], "ui-image")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["limit"], "3/proc")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["capacity"], "1/6")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["active"], "1")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["waiting"], "2")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["runtimes"], "1")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["wait_count"], "3")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["avg_wait"], "500ms")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["max_wait"], "750ms")
        self.assertEqual(provider_rows["provider:ui-image"]["cells"]["state"], "Waiting")
        self.assertEqual(
            provider_rows["provider:ui-image"]["cells"]["sources"],
            f"api-process, {worker.id}",
        )
        self.assertEqual(provider_rows["provider:openai"]["cells"]["provider"], "openai")
        self.assertEqual(provider_rows["provider:openai"]["cells"]["limit"], "4/worker")
        self.assertEqual(provider_rows["provider:openai"]["cells"]["capacity"], "0/2")
        self.assertGreaterEqual(
            int(provider_rows["provider:openai"]["cells"]["runtimes"]),
            1,
        )
        self.assertEqual(provider_rows["provider:openai"]["cells"]["state"], "Ready")
        self.assertEqual(provider_rows["provider:openai"]["cells"]["sources"], worker.id)
        provider_history_rows = {
            item["id"]: item for item in payload["provider_history"]["rows"]
        }
        self.assertIn("local", provider_history_rows)
        self.assertEqual(
            provider_history_rows["local"]["cells"]["provider"],
            "Local",
        )
        self.assertGreaterEqual(
            int(provider_history_rows["local"]["cells"]["tools"]),
            2,
        )
        self.assertEqual(provider_history_rows["local"]["cells"]["runs"], "4")
        self.assertEqual(provider_history_rows["local"]["cells"]["active"], "2")
        self.assertEqual(
            provider_history_rows["local"]["cells"]["failures"],
            "1",
        )
        self.assertEqual(
            provider_history_rows["local"]["cells"]["success_rate"],
            "50%",
        )
        self.assertEqual(
            provider_history_rows["local"]["cells"]["avg_duration"],
            "7s",
        )
        self.assertEqual(
            provider_history_rows["local"]["cells"]["max_duration"],
            "8s",
        )
        self.assertEqual(
            provider_history_rows["local"]["cells"]["state"],
            "Warning",
        )
        blocker_rows = {item["id"]: item for item in payload["run_blockers"]["rows"]}
        self.assertEqual(payload["run_blockers"]["total"], 2)
        self.assertEqual(
            blocker_rows["tool-run-ui-page-running"]["cells"]["reason"],
            "running on worker",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-running"]["cells"]["blocked_by"],
            f"worker:{worker.id}",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-running"]["cells"]["next_step"],
            "monitor worker heartbeat",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-running"]["cells"]["retry_budget"],
            "2 left (1/3)",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-queued"]["cells"]["reason"],
            "waiting for scheduler",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-queued"]["cells"]["blocked_by"],
            "scheduler",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-queued"]["cells"]["next_step"],
            "scheduler dispatch",
        )
        self.assertEqual(
            blocker_rows["tool-run-ui-page-queued"]["cells"]["candidate_workers"],
            "1",
        )
        self.assertIn(
            "ui_background_tool",
            {item["cells"]["tool"] for item in payload["auth_missing"]["rows"]},
        )
        access_row = next(
            item
            for item in payload["auth_missing"]["rows"]
            if item["cells"]["tool"] == "ui_background_tool"
        )
        self.assertEqual(access_row["cells"]["missing_access"], "env:UI_ACCESS_MISSING_TOKEN")
        self.assertIn(access_row["cells"]["status"], {"setup_needed", "unsupported"})
        runtime_rows = [
            item
            for item in payload["auth_missing"]["rows"]
            if item["cells"]["tool"] == "browser.snapshot"
        ]
        if runtime_rows:
            runtime_row = runtime_rows[0]
            self.assertEqual(runtime_row["cells"]["category"], "Runtime")
            self.assertEqual(
                runtime_row["cells"]["missing_access"],
                "browser-profile-runtime",
            )
            self.assertEqual(runtime_row["cells"]["action"], "Open Daemon")
            self.assertEqual(runtime_row["cells"]["route"], "/operations/daemon")
        self.assertIn(
            stored_artifact.id,
            {
                item["cells"]["artifact_id"]
                for item in payload["recent_artifacts"]["rows"]
            },
        )
        artifact_row = next(
            item
            for item in payload["recent_artifacts"]["rows"]
            if item["cells"]["artifact_id"] == stored_artifact.id
        )
        self.assertEqual(artifact_row["cells"]["name"], "tool-output.txt")
        self.assertEqual(artifact_row["cells"]["mime_type"], "text/plain")
        self.assertEqual(artifact_row["cells"]["size"], "11 B")
        self.assertEqual(
            artifact_row["cells"]["route"],
            f"/artifacts/{stored_artifact.id}/download",
        )
        lifecycle_events = {
            item["cells"]["event"] for item in payload["tool_lifecycle_events"]["rows"]
        }
        self.assertIn("source.created", lifecycle_events)
        self.assertIn("function.created", lifecycle_events)
        inline_items = {
            item["label"]: item["value"] for item in payload["inline_risk"]["items"]
        }
        self.assertEqual(inline_items["Inline Failures"], "1")
        strategy_modes = {
            item["cells"]["mode"] for item in payload["strategies"]["rows"]
        }
        self.assertEqual(strategy_modes, {"background", "inline"})
        action_by_id = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(
            action_by_id["cancel_tool_run"]["audit_event"],
            "tool.run.cancel",
        )
        self.assertEqual(
            action_by_id["cancel_tool_run"]["endpoint"],
            "/operations/tool/runs/{run_id}/cancel",
        )
        self.assertEqual(
            action_by_id["retry_tool_run"]["audit_event"],
            "tool.run.retry",
        )
        self.assertEqual(
            action_by_id["retry_tool_run"]["endpoint"],
            "/operations/tool/runs/{run_id}/retry",
        )
        self.assertNotIn("error", run_rows["tool-run-ui-page-failed"]["cells"])
        self.assertNotIn(
            "error",
            {item["key"] for item in payload["tool_runs"]["columns"]},
        )
        self.assertEqual(payload["tool_run_details"], [])
        detail_response = self.client.get(
            "/operations/tool/runs/tool-run-ui-page-running/detail"
        )
        self.assertEqual(detail_response.status_code, 200)
        running_detail = detail_response.json()
        artifact_detail_response = self.client.get(
            "/operations/tool/runs/tool-run-ui-page-artifact/detail"
        )
        self.assertEqual(artifact_detail_response.status_code, 200)
        artifact_detail = artifact_detail_response.json()
        failed_detail_response = self.client.get(
            "/operations/tool/runs/tool-run-ui-page-failed/detail"
        )
        self.assertEqual(failed_detail_response.status_code, 200)
        failed_detail = failed_detail_response.json()
        missing_detail_response = self.client.get(
            "/operations/tool/runs/missing-tool-run/detail"
        )
        self.assertEqual(missing_detail_response.status_code, 404)
        details = {
            running_detail["run_id"]: running_detail,
            artifact_detail["run_id"]: artifact_detail,
            failed_detail["run_id"]: failed_detail,
        }
        self.assertIn("tool-run-ui-page-running", details)
        self.assertEqual(running_detail["input_payload"], {"prompt": "run"})
        running_summary = {
            item["label"]: item["value"]
            for item in running_detail["summary"]
        }
        self.assertEqual(running_summary["Turn ID"], source_run.id)
        self.assertEqual(running_summary["Chain ID"], tool_chain.id)
        self.assertEqual(running_summary["Step ID"], tool_step.id)
        self.assertEqual(running_summary["Step Kind"], "tool_batch")
        self.assertEqual(
            {
                item["label"]: item["value"]
                for item in running_detail["invocation_context"]
            }["trace_id"],
            "trace-tool-page",
        )
        self.assertEqual(running_detail["assignments"]["rows"][0]["id"], assignment.id)
        self.assertEqual(
            artifact_detail["artifacts"]["rows"][0]["cells"]["artifact_id"],
            stored_artifact.id,
        )
        self.assertEqual(failed_detail["error"], "403 Provider Access missing")
        failed_error_facts = {
            item["label"]: item["value"]
            for item in failed_detail["error_facts"]["items"]
        }
        self.assertEqual(failed_error_facts["Error Family"], "access")
        self.assertEqual(failed_error_facts["Error Code"], "access_denied")
        self.assertEqual(failed_error_facts["HTTP Status"], "403")
        self.assertEqual(failed_error_facts["Retryable"], "Yes")

        failed_filter_response = self.client.get(
            "/operations/tool?status=failed&limit=1&offset=0"
        )
        self.assertEqual(failed_filter_response.status_code, 200)
        failed_filter_payload = failed_filter_response.json()
        self.assertEqual(failed_filter_payload["tool_runs"]["total"], 1)
        self.assertEqual(failed_filter_payload["tool_run_details"], [])
        self.assertEqual(
            [item["id"] for item in failed_filter_payload["tool_runs"]["rows"]],
            ["tool-run-ui-page-failed"],
        )
        self.assertNotIn(
            "error",
            failed_filter_payload["tool_runs"]["rows"][0]["cells"],
        )
        self.assertEqual(
            failed_filter_payload["tool_runs"]["rows"][0]["cells"]["actions"],
            "Open / Trace / Retry",
        )
        limit_response = self.client.get("/operations/tool?limit=1")
        self.assertEqual(limit_response.status_code, 200)
        limit_payload = limit_response.json()
        self.assertEqual(len(limit_payload["tool_runs"]["rows"]), 1)
        self.assertEqual(limit_payload["tool_run_details"], [])

        active_page_response = self.client.get(
            "/operations/tool?status=active&limit=1&offset=1"
        )
        self.assertEqual(active_page_response.status_code, 200)
        active_page_payload = active_page_response.json()
        self.assertEqual(active_page_payload["tool_runs"]["total"], 2)
        self.assertEqual(
            [item["id"] for item in active_page_payload["tool_runs"]["rows"]],
            ["tool-run-ui-page-queued"],
        )

        running_filter_response = self.client.get(
            "/operations/tool?status=running&limit=10&offset=0"
        )
        self.assertEqual(running_filter_response.status_code, 200)
        running_filter_payload = running_filter_response.json()
        self.assertEqual(
            [item["id"] for item in running_filter_payload["tool_runs"]["rows"]],
            ["tool-run-ui-page-running"],
        )

        waiting_filter_response = self.client.get(
            "/operations/tool?status=waiting&limit=10&offset=0"
        )
        self.assertEqual(waiting_filter_response.status_code, 200)
        waiting_filter_payload = waiting_filter_response.json()
        self.assertEqual(waiting_filter_payload["tool_runs"]["total"], 1)
        self.assertEqual(
            [item["id"] for item in waiting_filter_payload["tool_runs"]["rows"]],
            ["tool-run-ui-page-queued"],
        )

        long_running_filter_response = self.client.get(
            "/operations/tool?status=long_running&limit=10&offset=0"
        )
        self.assertEqual(long_running_filter_response.status_code, 200)
        long_running_filter_payload = long_running_filter_response.json()
        self.assertEqual(
            [item["id"] for item in long_running_filter_payload["tool_runs"]["rows"]],
            ["tool-run-ui-page-running", "tool-run-ui-page-queued"],
        )

        recent_success_response = self.client.get(
            "/operations/tool?status=succeeded&time_window=24h&limit=10&offset=0"
        )
        self.assertEqual(recent_success_response.status_code, 200)
        recent_success_payload = recent_success_response.json()
        self.assertEqual(recent_success_payload["tool_runs"]["total"], 1)
        self.assertEqual(
            [item["id"] for item in recent_success_payload["tool_runs"]["rows"]],
            ["tool-run-ui-page-artifact"],
        )

        filter_cases = (
            (
                "tool_id=ui_inline_tool",
                2,
                ["tool-run-ui-page-artifact", "tool-run-ui-page-failed"],
            ),
            ("provider=local", 4, None),
            (
                "mode=inline",
                2,
                ["tool-run-ui-page-artifact", "tool-run-ui-page-failed"],
            ),
            ("strategy=async", 4, None),
            ("environment=local", 4, None),
            ("worker_id=tool-worker-ui", 1, ["tool-run-ui-page-running"]),
            ("has_artifact=yes", 1, ["tool-run-ui-page-artifact"]),
            ("retryable=yes", 1, ["tool-run-ui-page-failed"]),
            ("search=Provider%20Access", 1, ["tool-run-ui-page-failed"]),
        )
        for query_string, expected_total, expected_ids in filter_cases:
            with self.subTest(query_string=query_string):
                filter_response = self.client.get(
                    f"/operations/tool?{query_string}&limit=10&offset=0",
                )
                self.assertEqual(filter_response.status_code, 200)
                filter_payload = filter_response.json()
                self.assertEqual(filter_payload["tool_runs"]["total"], expected_total)
                if expected_ids is not None:
                    self.assertEqual(
                        [
                            item["id"]
                            for item in filter_payload["tool_runs"]["rows"]
                        ],
                        expected_ids,
                    )

    def test_ui_operations_tool_worker_pool_excludes_old_expired_registrations(
        self,
    ) -> None:
        container = self.client.app.state.container
        now = datetime.now(timezone.utc)
        live_worker = ToolWorkerRegistration.create(
            worker_id="tool-worker-live-ui",
            lease_seconds=600,
            max_in_flight=4,
        )
        live_worker.heartbeat_at = now
        live_worker.lease_expires_at = now + timedelta(seconds=600)
        expired_worker = ToolWorkerRegistration.create(
            worker_id="tool-worker-old-ui",
            lease_seconds=600,
            max_in_flight=4,
        )
        expired_worker.heartbeat_at = now - timedelta(minutes=30)
        expired_worker.lease_expires_at = now - timedelta(minutes=29)

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.tool_workers.add(live_worker)
            uow.tool_workers.add(expired_worker)
            uow.commit()
        self._materialize_operations("tool")

        response = self.client.get("/operations/tool")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["worker_pool"]["title"],
            "Worker Pool by Current Registrations",
        )
        self.assertEqual(payload["worker_pool"]["total"], 1)
        worker_segments = {
            item["id"]: item["value"] for item in payload["worker_pool"]["segments"]
        }
        self.assertEqual(worker_segments, {"idle": 1})
        worker_rows = {item["id"]: item for item in payload["workers"]["rows"]}
        self.assertEqual(payload["workers"]["total"], 2)
        self.assertEqual(
            worker_rows[expired_worker.id]["cells"]["status"],
            "Lease Expired",
        )

    def test_ui_operations_tool_worker_lifecycle_events_and_prune_action(self) -> None:
        container = self.client.app.state.container
        worker = container.require(AppKey.TOOL_WORKER_SERVICE).register_worker(
            worker_id="tool-worker-lifecycle-ui",
            max_in_flight=2,
        )
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            persisted_worker = uow.tool_workers.get(worker.id)
            assert persisted_worker is not None
            persisted_worker.heartbeat_at = datetime.now(timezone.utc) - timedelta(
                minutes=20,
            )
            persisted_worker.lease_expires_at = datetime.now(timezone.utc) - timedelta(
                minutes=19,
            )
            uow.tool_workers.add(persisted_worker)
            uow.commit()

        container.require(AppKey.TOOL_WORKER_SERVICE).register_worker(
            worker_id=worker.id,
            max_in_flight=3,
        )
        self._process_operations_events()
        self._materialize_operations("tool")

        response = self.client.get("/operations/tool")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        worker_rows = {item["id"]: item for item in payload["workers"]["rows"]}
        self.assertEqual(worker_rows[worker.id]["cells"]["load"], "0/3")
        self.assertIn("default", worker_rows[worker.id]["cells"]["capabilities"])
        lifecycle_events = {
            item["cells"]["event"] for item in payload["tool_lifecycle_events"]["rows"]
        }
        self.assertIn("worker.recovered", lifecycle_events)
        self.assertIn("worker.capabilities_updated", lifecycle_events)
        worker_detail = next(
            item for item in payload["worker_details"] if item["worker_id"] == worker.id
        )
        worker_detail_events = {
            item["cells"]["event"] for item in worker_detail["events"]["rows"]
        }
        self.assertIn("worker.recovered", worker_detail_events)
        self.assertIn("worker.capabilities_updated", worker_detail_events)

        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            expired_worker = uow.tool_workers.get(worker.id)
            assert expired_worker is not None
            expired_worker.heartbeat_at = datetime.now(timezone.utc) - timedelta(
                hours=2,
            )
            expired_worker.lease_expires_at = datetime.now(timezone.utc) - timedelta(
                hours=2,
            )
            uow.tool_workers.add(expired_worker)
            uow.commit()

        prune_response = self.client.post(
            "/tools/workers/prune-expired?retention_seconds=3600",
        )

        self.assertEqual(prune_response.status_code, 200)
        prune_payload = prune_response.json()
        self.assertEqual(prune_payload["pruned_count"], 1)
        self.assertEqual(prune_payload["worker_ids"], [worker.id])
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            self.assertIsNone(uow.tool_workers.get(worker.id))

    def test_ui_operations_llm_overview_uses_llm_runtime_state(self) -> None:
        container = self.client.app.state.container
        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            _SequentialResultAdapter(
                LlmResult(
                    text="hello from llm ops",
                    usage=LlmUsage(input_tokens=11, output_tokens=7, total_tokens=18),
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
                "context_window_tokens": 128000,
                "max_concurrency": 2,
                "concurrency_key": "provider:openai",
            },
        )
        self.assertEqual(llm_response.status_code, 201)
        invocation = container.require(AppKey.LLM_SERVICE).invoke(
            InvokeLlmInput(
                llm_id="openai.gpt-5.4-mini",
                invocation_id="llm-invocation-ui-ops",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Summarize runtime state.",
                    ),
                ),
                input_items=(
                    LlmInputItem(
                        kind=LlmInputItemKind.MESSAGE,
                        payload={
                            "role": "user",
                            "content": "Summarize runtime state.",
                        },
                        source="test",
                    ),
                ),
            ),
        )
        self._materialize_operations("llm")

        response = self.client.get("/operations/llm/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "llm")
        self.assertEqual(payload["title"], "LLM")
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(
            metric_by_id["profiles"]["value"],
            str(len(container.require(AppKey.LLM_SERVICE).list_profiles())),
        )
        self.assertEqual(metric_by_id["tokens"]["value"], "18")
        self.assertIn(
            {
                "Priority": "succeeded",
                "Run ID": invocation.id,
                "Lane Key": "openai.gpt-5.4-mini",
                "Wait Reason": "stop",
                "Wait Time": payload["queue"][0]["Wait Time"],
            },
            payload["queue"],
        )
        self.assertIn(
            {
                "Lane Key": "provider:openai",
                "Holder Run ID": "openai.gpt-5.4-mini",
                "TTL": "60s",
                "Expires At": "2",
                "Reason": "openai/openai_responses",
            },
            payload["lane_locks"],
        )

    def test_ui_operations_llm_warmup_action_uses_llm_owner_service(self) -> None:
        container = self.client.app.state.container
        adapter = _WarmupOnlyAdapter()
        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        previous_token = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "operations-warmup-token"
        try:
            create_response = self.client.post(
                "/llms",
                json={
                    "id": "openai.gpt-ops-warmup",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
                    "credential_binding_id": "openai-api-key",
                },
            )
            self.assertEqual(create_response.status_code, 201)

            warmup_response = self.client.post(
                "/operations/llm/profiles/openai.gpt-ops-warmup/warmup",
                json={"reason": "unit test operations llm warmup"},
            )

            self.assertEqual(warmup_response.status_code, 200)
            warmup_payload = warmup_response.json()
            self.assertEqual(warmup_payload["llm_id"], "openai.gpt-ops-warmup")
            self.assertEqual(warmup_payload["status"], "warmed")
            self.assertEqual(warmup_payload["details"]["transport"], "websocket")
            self.assertEqual(
                adapter.calls,
                [("openai.gpt-ops-warmup", "operations-warmup-token")],
            )
            self.assertEqual(
                container.require(AppKey.LLM_SERVICE).list_invocations(
                    llm_id="openai.gpt-ops-warmup",
                ),
                [],
            )
            audits_response = self.client.get("/operations/actions/audits")
            self.assertEqual(audits_response.status_code, 200)
            audits = audits_response.json()
            self.assertEqual(audits[0]["audit_event"], "llm.profile.warmup")
            self.assertEqual(audits[0]["target_id"], "openai.gpt-ops-warmup")
            self.assertEqual(audits[0]["status"], "succeeded")

            self._process_operations_events()
            self._materialize_operations("llm")
            operations_response = self.client.get("/operations/llm")
            self.assertEqual(operations_response.status_code, 200)
            operations_payload = operations_response.json()
            access_rows = {
                item["id"]: item
                for item in operations_payload["provider_access_health"]["rows"]
            }
            self.assertEqual(
                access_rows["openai.gpt-ops-warmup"]["cells"]["warmup"],
                "Warmed (websocket)",
            )
            lifecycle_events = {
                item["cells"]["event"]
                for item in operations_payload["llm_lifecycle_events"]["rows"]
            }
            self.assertIn("llm.profile_warmup_succeeded", lifecycle_events)
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous_token

    def test_ui_operations_llm_page_uses_runtime_state_and_events(self) -> None:
        class PreviewingResultAdapter(_SequentialResultAdapter):
            def preview_request(self, _profile, _request):  # noqa: ANN001
                return {
                    "renderer_id": "openai_responses",
                    "transport": "http",
                    "render_strategy": "full_replay",
                    "endpoint": "https://api.openai.test/v1/responses",
                    "tool_count": 1,
                    "payload_preview": {
                        "input": [{"role": "user", "content": "raw provider input"}],
                        "tools": [{"name": "command_exec", "parameters": {}}],
                    },
                    "render_report": {
                        "renderer_id": "openai_responses",
                        "transport": "http",
                        "render_strategy": "full_replay",
                        "tool_surface": {
                            "source_tool_schema_count": 1,
                            "provider_visible_tool_count": 1,
                            "provider_visible_tool_names": ["command_exec"],
                            "dropped_tool_schema_count": 0,
                        },
                        "tool_protocol": {
                            "schema_version": "2026-06-19.runtime_input_filter.v1",
                            "replay_has_protocol_breaks": False,
                            "source_had_protocol_breaks": False,
                            "replay_orphan_tool_output_count": 0,
                            "replay_missing_tool_output_count": 0,
                            "replay_duplicate_tool_call_id_count": 0,
                            "replay_duplicate_tool_output_id_count": 0,
                            "dropped_orphan_tool_output_count": 0,
                            "dropped_missing_tool_output_count": 1,
                            "dropped_duplicate_tool_call_id_count": 0,
                            "dropped_duplicate_tool_output_id_count": 0,
                        },
                    },
                }

        class FailingLlmAdapter:
            def preview_request(self, _profile, _request):  # noqa: ANN001
                return {
                    "preview_source": "failing_adapter",
                    "transport": "websocket",
                    "has_previous_response_id": True,
                    "previous_response_id": "resp-before-failure",
                    "input_delta_mode": True,
                    "input_delta_count": 1,
                    "input_baseline_count": 3,
                    "preview_error": "provider rejected continuation delta",
                }

            def invoke(self, _profile, _request):  # noqa: ANN001
                raise RuntimeError("provider rate limit")

        container = self.client.app.state.container
        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            PreviewingResultAdapter(
                LlmResult(
                    text="hello from llm ops page",
                    usage=LlmUsage(input_tokens=11, output_tokens=7, total_tokens=18),
                    finish_reason="stop",
                ),
            ),
        )
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-ops-page",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-ops-page",
                "credential_binding_id": "openai-api-key",
                "context_window_tokens": 100,
                "max_concurrency": 2,
                "concurrency_key": "provider:openai",
            },
        )
        self.assertEqual(llm_response.status_code, 201)
        succeeded = container.require(AppKey.LLM_SERVICE).invoke(
            InvokeLlmInput(
                llm_id="openai.gpt-ops-page",
                invocation_id="llm-invocation-ui-page-succeeded",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Summarize runtime state.",
                    ),
                ),
                input_items=(
                    LlmInputItem(
                        kind=LlmInputItemKind.MESSAGE,
                        payload={
                            "role": "user",
                            "content": "Summarize runtime state.",
                        },
                        source="session_item",
                    ),
                    LlmInputItem(
                        kind=LlmInputItemKind.REASONING,
                        payload={"summary": "Inspect operations state."},
                        source="session_item",
                    ),
                    LlmInputItem(
                        kind=LlmInputItemKind.FUNCTION_CALL,
                        payload={"call_id": "call-ui-linked", "name": "command.exec"},
                        source="session_item",
                    ),
                    LlmInputItem(
                        kind=LlmInputItemKind.FUNCTION_CALL_OUTPUT,
                        payload={
                            "call_id": "call-ui-linked",
                            "output": [
                                {
                                    "type": "text",
                                    "text": (
                                        "tool_result:\n"
                                        "summary: command ran\n"
                                        "stdout_excerpt: linked detail output"
                                    ),
                                },
                            ],
                        },
                        source="session_item",
                    ),
                ),
                request_metadata={
                    "request_render_snapshot_id": "ctxsnap-ui-linked-llm",
                    "request_render_snapshot": {
                        "snapshot_id": "ctxsnap-ui-linked-llm",
                        "tree_schema_version": "2026-06-11.context_tree.v2",
                        "included_node_ids": [
                            "runtime.contract",
                            "tools.available",
                        ],
                    },
                    "tool_surface_snapshot_id": "toolsnap-ui-linked-llm",
                    "tool_surface": {
                        "id": "tool_surface:ctxsnap-ui-linked-llm",
                        "functions": [
                            {
                                "name": "command.exec",
                                "tool_id": "command.exec",
                            },
                        ],
                        "mirrored_schema_names": ["command.exec"],
                    },
                    "runtime_input_filter": {
                        "mode": "request_render_session_refs",
                        "input_before_filter_count": 4,
                        "input_after_filter_count": 3,
                        "allowed_session_item_count": 3,
                        "dropped_input_item_count": 1,
                        "dropped_orphan_function_call_count": 1,
                        "dropped_orphan_function_call_ids": ["call-ui-orphan"],
                    },
                },
            ),
        )
        linked_run = OrchestrationRun(
            id="run-ui-llm-ops-page",
            inbound_instruction=InboundInstruction(
                source="http",
                content="Summarize runtime state.",
            ),
            status=OrchestrationRunStatus.COMPLETED,
            stage=OrchestrationRunStage.COMPLETED,
            agent_id="assistant",
            result_payload={
                "llm_id": "openai.gpt-ops-page",
                "output_text": "hello from llm ops page",
            },
            metadata={
                "session_key": "agent:assistant:main",
                "trace_id": "trace-llm-ops-page",
                "turn_id": "turn-llm-ops-page",
            },
        )
        llm_chain = ExecutionChain.create(
            chain_id="chain-ui-llm-ops-page",
            turn_id=linked_run.id,
        )
        llm_step = ExecutionStep.create(
            step_id="step-ui-llm-ops-page",
            chain_id=llm_chain.id,
            turn_id=linked_run.id,
            step_index=0,
            kind=ExecutionStepKind.LLM,
        )
        llm_step.complete()
        llm_chain.increment_step_count()
        llm_item = ExecutionStepItem.create(
            item_id="item-ui-llm-ops-page",
            step_id=llm_step.id,
            chain_id=llm_chain.id,
            turn_id=linked_run.id,
            item_index=0,
            kind=ExecutionStepItemKind.LLM_INVOCATION,
            owner=ExecutionOwnerReference(
                owner_kind="llm_invocation",
                owner_id=succeeded.id,
            ),
        )
        llm_item.complete(
            summary_payload={
                "llm_invocation_id": succeeded.id,
                "llm_id": "openai.gpt-ops-page",
            },
        )
        llm_chain.complete()
        with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
            uow.orchestration_runs.add(linked_run)
            uow.execution_chains.add(llm_chain)
            uow.execution_steps.add(llm_step)
            uow.execution_step_items.add(llm_item)
            uow.commit()
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="orchestration.llm_resolved",
                kind="observe",
                payload={
                    "event_name": "orchestration.llm_resolved",
                    "run_id": linked_run.id,
                    "requested_llm_id": "auto",
                    "resolved_llm_id": "openai.gpt-ops-page",
                    "strategy": "agent_default",
                    "status": "resolved",
                    "routing_input_block_count": 3,
                    "session_replay_window": {
                        "active_session_only": True,
                        "from_sequence_no": 11,
                        "to_sequence_no": 13,
                        "item_count": 3,
                    },
                },
                trace={"trace_id": "trace-llm-ops-page"},
            ),
        )

        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            FailingLlmAdapter(),
        )
        failed = container.require(AppKey.LLM_SERVICE).invoke(
            InvokeLlmInput(
                llm_id="openai.gpt-ops-page",
                invocation_id="llm-invocation-ui-page-failed",
                messages=(
                    LlmMessage(
                        role=LlmMessageRole.USER,
                        content="Trigger a failure.",
                    ),
                ),
                input_items=(
                    LlmInputItem(
                        kind=LlmInputItemKind.MESSAGE,
                        payload={"role": "user", "content": "Trigger a failure."},
                        source="test",
                    ),
                ),
            ),
        )
        self._process_operations_events()
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="llm.stream_delta_observed",
                kind="observe",
                payload={
                    "event_name": "llm.stream_delta_observed",
                    "invocation_id": succeeded.id,
                    "llm_id": "openai.gpt-ops-page",
                    "status": "streaming",
                    "streaming": True,
                    "text_delta_length": 5,
                },
                trace={"trace_id": "trace-llm-ops-page"},
                ordering_key=succeeded.id,
            ),
        )
        self._materialize_operations("llm")

        response = self.client.get("/operations/llm")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "llm")
        self.assertEqual(payload["role"]["scope"], "llm")
        self.assertEqual(payload["recent_invocations"]["total"], 2)
        recent_rows = {item["id"]: item for item in payload["recent_invocations"]["rows"]}
        self.assertEqual(
            recent_rows[succeeded.id]["cells"]["run_id"],
            linked_run.id,
        )
        self.assertEqual(
            recent_rows[succeeded.id]["cells"]["trace"],
            "trace-llm-ops-page",
        )
        self.assertEqual(
            recent_rows[succeeded.id]["cells"]["trace_route"],
            f"/workbench/traces/trace-llm-ops-page?focus_id={succeeded.id}",
        )
        self.assertEqual(
            recent_rows[succeeded.id]["cells"]["chain_id"],
            llm_chain.id,
        )
        self.assertEqual(
            recent_rows[succeeded.id]["cells"]["step_id"],
            llm_step.id,
        )
        self.assertEqual(payload["failed_invocations"]["total"], 1)
        self.assertEqual(
            payload["failed_invocations"]["rows"][0]["cells"]["invocation_id"],
            failed.id,
        )
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metric_by_id["tokens"]["value"], "18")
        action_by_id = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(
            action_by_id["open_invocation"]["endpoint"],
            "/operations/llm/invocations/{invocation_id}/detail",
        )
        self.assertFalse(action_by_id["disable_profile"]["allowed"])
        self.assertIsNone(action_by_id["disable_profile"]["endpoint"])
        self.assertIn(
            "not exposed",
            action_by_id["disable_profile"]["disabled_reason"],
        )
        access_rows = {
            item["id"]: item for item in payload["provider_access_health"]["rows"]
        }
        self.assertEqual(
            access_rows["openai.gpt-ops-page"]["cells"]["status"],
            "Available",
        )
        self.assertEqual(payload["provider_auth_blocked"]["total"], 0)
        error_rows = payload["error_summary"]["rows"]
        self.assertEqual(error_rows[0]["cells"]["error_code"], "adapter_error")
        self.assertEqual(payload["token_usage"]["total"], 18)
        lifecycle_events = {
            item["cells"]["event"]
            for item in payload["llm_lifecycle_events"]["rows"]
        }
        self.assertIn("llm.invocation_started", lifecycle_events)
        self.assertIn("llm.invocation_succeeded", lifecycle_events)
        self.assertIn("llm.invocation_failed", lifecycle_events)
        self.assertIn("llm.stream_delta_observed", lifecycle_events)
        self.assertEqual(payload["streaming_requests"]["total"], 1)
        self.assertEqual(payload["invocation_details"], [])
        succeeded_detail_response = self.client.get(
            f"/operations/llm/invocations/{succeeded.id}/detail"
        )
        self.assertEqual(succeeded_detail_response.status_code, 200)
        failed_detail_response = self.client.get(
            f"/operations/llm/invocations/{failed.id}/detail"
        )
        self.assertEqual(failed_detail_response.status_code, 200)
        missing_detail_response = self.client.get(
            "/operations/llm/invocations/missing-invocation/detail"
        )
        self.assertEqual(missing_detail_response.status_code, 404)
        details_by_id = {
            succeeded.id: succeeded_detail_response.json(),
            failed.id: failed_detail_response.json(),
        }
        self.assertIn(succeeded.id, details_by_id)
        self.assertIn(failed.id, details_by_id)
        succeeded_summary = {
            item["label"]: item["value"]
            for item in details_by_id[succeeded.id]["summary"]
        }
        self.assertEqual(succeeded_summary["Chain ID"], llm_chain.id)
        self.assertEqual(succeeded_summary["Step ID"], llm_step.id)
        self.assertEqual(succeeded_summary["Step Kind"], "llm")
        runtime_observations = {
            item["label"]: item
            for item in details_by_id[succeeded.id]["runtime_observations"]["items"]
        }
        self.assertEqual(runtime_observations["Runtime observations"]["value"], "1")
        self.assertNotIn("Loop correction warnings", runtime_observations)
        self.assertNotIn("Tool-only streak", runtime_observations)
        self.assertNotIn("Evidence frontier items", runtime_observations)
        self.assertNotIn("Evidence observed", runtime_observations)
        self.assertNotIn("Evidence uncertain", runtime_observations)
        self.assertEqual(runtime_observations["Tool protocol replay"]["value"], "clean")
        self.assertEqual(
            runtime_observations["Tool protocol source"]["value"],
            "clean",
        )
        self.assertEqual(
            runtime_observations["Tool protocol filtered"]["value"],
            "filtered=1; orphan=0; missing=1; dup_call=0; dup_output=0",
        )
        linked_llm_response = self.client.get(
            f"/ui/workbench/linked-entities/llm_invocation/{succeeded.id}",
        )
        self.assertEqual(linked_llm_response.status_code, 200)
        linked_llm_payload = linked_llm_response.json()
        self.assertEqual(linked_llm_payload["type"], "llm_invocation")
        self.assertEqual(linked_llm_payload["payload"]["runtime_observations"]["observation_count"], 1)
        self.assertEqual(
            linked_llm_payload["payload"]["provider_input_summary"][
                "request_render_snapshot_id"
            ],
            "ctxsnap-ui-linked-llm",
        )
        self.assertEqual(
            linked_llm_payload["payload"]["provider_input_summary"][
                "request_render_snapshot_schema_version"
            ],
            "2026-06-11.context_tree.v2",
        )
        self.assertEqual(
            linked_llm_payload["payload"]["provider_input_summary"][
                "request_render_snapshot_included_node_count"
            ],
            2,
        )
        self.assertEqual(
            linked_llm_payload["payload"]["provider_input_summary"][
                "tool_surface_id"
            ],
            "tool_surface:ctxsnap-ui-linked-llm",
        )
        self.assertEqual(
            linked_llm_payload["payload"]["provider_input_summary"][
                "tool_surface_function_count"
            ],
            1,
        )
        self.assertEqual(
            linked_llm_payload["payload"]["replay_input"]["count"],
            4,
        )
        self.assertEqual(
            linked_llm_payload["payload"]["replay_input"]["kinds"],
            ["message", "reasoning", "function_call", "function_call_output"],
        )
        self.assertEqual(
            linked_llm_payload["payload"]["replay_input"]["sources"],
            ["session_item"],
        )
        self.assertEqual(
            linked_llm_payload["payload"]["replay_input"]["protocol_counts"],
            {
                "reasoning": 1,
                "function_call": 1,
                "function_call_output": 1,
                "provider_external_item": 0,
            },
        )
        self.assertEqual(
            linked_llm_payload["payload"]["replay_input"][
                "tool_result_excerpt_count"
            ],
            1,
        )
        self.assertIn(
            "stdout_excerpt: linked detail output",
            linked_llm_payload["payload"]["replay_input"][
                "tool_result_excerpt_sample"
            ],
        )
        provider_preview_json = json.dumps(
            linked_llm_payload["payload"]["provider_request_payload_preview"],
        )
        self.assertNotIn("full tree body must not be summarized here", provider_preview_json)
        self.assertEqual(
            linked_llm_payload["payload"]["provider_render_report"][
                "renderer_id"
            ],
            "openai_responses",
        )
        self.assertEqual(
            linked_llm_payload["payload"]["provider_render_report"][
                "tool_surface"
            ]["provider_visible_tool_names"],
            ["command_exec"],
        )
        self.assertEqual(
            linked_llm_payload["payload"]["provider_wire_preview"]["endpoint"],
            "https://api.openai.test/v1/responses",
        )
        self.assertNotIn(
            "render_report",
            linked_llm_payload["payload"]["provider_wire_preview"],
        )
        self.assertNotIn(
            "payload_preview",
            linked_llm_payload["payload"]["provider_wire_preview"],
        )
        self.assertNotIn(
            "input",
            linked_llm_payload["payload"]["provider_wire_preview"],
        )
        self.assertNotIn(
            "tools",
            linked_llm_payload["payload"]["provider_wire_preview"],
        )
        self.assertEqual(
            linked_llm_payload["payload"]["runtime_observations"]["tool_protocol"][
                "replay_has_protocol_breaks"
            ],
            False,
        )
        self.assertEqual(
            linked_llm_payload["payload"]["runtime_observations"]["tool_protocol"][
                "source_had_protocol_breaks"
            ],
            False,
        )
        self.assertEqual(
            linked_llm_payload["payload"]["runtime_observations"]["tool_protocol"][
                "filtered_count"
            ],
            1,
        )
        resolver_items = {
            item["label"]: item["value"]
            for item in details_by_id[succeeded.id]["resolver"]["items"]
        }
        self.assertEqual(resolver_items["Requested"], "auto")
        self.assertEqual(resolver_items["Resolved"], "openai.gpt-ops-page")
        self.assertEqual(resolver_items["Routing Input Blocks"], "3")
        self.assertEqual(
            resolver_items["Session Replay Window"],
            "seq=11..13; items=3; active_only=true",
        )
        self.assertEqual(resolver_items["Run ID"], linked_run.id)
        self.assertEqual(
            details_by_id[failed.id]["error_facts"]["items"][1]["value"],
            "adapter_error",
        )
        failed_error_facts = {
            item["label"]: item["value"]
            for item in details_by_id[failed.id]["error_facts"]["items"]
        }
        self.assertEqual(
            failed_error_facts["Provider Error Message"],
            "provider rate limit",
        )
        self.assertEqual(
            failed_error_facts["Provider Preview Error"],
            "provider rejected continuation delta",
        )
        self.assertEqual(failed_error_facts["Provider Transport"], "websocket")
        self.assertEqual(
            failed_error_facts["Provider Continuation"],
            "previous_response_id=resp-before-failure",
        )
        self.assertEqual(
            failed_error_facts["Provider Input Delta"],
            "mode=true; delta=1; baseline=3",
        )
        succeeded_events = {
            item["cells"]["event"]
            for item in details_by_id[succeeded.id]["events"]["rows"]
        }
        self.assertIn("llm.stream_delta_observed", succeeded_events)

        filtered_response = self.client.get("/operations/llm?limit=1")
        self.assertEqual(filtered_response.status_code, 200)
        filtered_payload = filtered_response.json()
        self.assertEqual(len(filtered_payload["recent_invocations"]["rows"]), 1)
        self.assertEqual(filtered_payload["invocation_details"], [])

    def test_ui_operations_events_page_uses_event_bus_state(self) -> None:
        container = self.client.app.state.container
        topic = "events.named.operations.events.test"
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="operations.events.test",
                topic=topic,
                kind="fact",
                payload={
                    "event_name": "operations.events.test",
                    "run_id": "run-events-ops",
                    "status": "observed",
                },
                trace={"trace_id": "trace-events-ops"},
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).set_subscription_cursor(
            "operations.observer.events.test",
            source_topic=topic,
            cursor="0",
        )

        self._materialize_operations("events")
        response = self.client.get("/operations/events")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "events")
        self.assertNotIn("sections", payload)
        self.assertNotIn("observers", payload)
        self.assertNotIn("projec" + "tion_mapping_failures", payload)
        self.assertIn("observer_coverage", payload)
        self.assertIn("observer_lag", payload)
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertGreaterEqual(int(metric_by_id["topics"]["value"]), 1)
        self.assertGreaterEqual(int(metric_by_id["subscriptions"]["value"]), 1)
        self.assertIn("observers", metric_by_id)
        tab_by_id = {item["id"]: item for item in payload["tabs"]}
        self.assertIn("observer", tab_by_id)
        self.assertIn("observer_coverage", tab_by_id)
        self.assertIn("observer_lag", tab_by_id)
        self.assertEqual(tab_by_id["observer_coverage"]["label"], "Observer Coverage")
        self.assertEqual(tab_by_id["observer_lag"]["label"], "Observer Lag")
        self.assertGreater(payload["observer_health"]["total"], 0)
        self.assertEqual(payload["observer_coverage"]["title"], "Observer Coverage")
        self.assertEqual(payload["observer_lag"]["title"], "Observer Lag")
        observer_row = payload["observer_health"]["rows"][0]
        self.assertTrue(
            observer_row["cells"]["subscription"].startswith("operations.observer."),
        )
        self.assertTrue(
            observer_row["cells"]["source_topic"].startswith("events.named."),
        )
        self.assertGreaterEqual(payload["recent_events"]["total"], 1)
        recent_row = payload["recent_events"]["rows"][0]
        self.assertEqual(recent_row["cells"]["event"], "operations.events.test")
        self.assertEqual(recent_row["cells"]["topic"], topic)
        self.assertEqual(recent_row["cells"]["run"], "run-events-ops")
        self.assertEqual(payload["subscriptions"]["rows"][0]["cells"]["status"], "Lagging")
        self.assertEqual(payload["topics"]["rows"][0]["cells"]["latest_cursor"], "1")
        details_by_id = {
            item["event_id"]: item for item in payload["event_details"]
        }
        self.assertIn(recent_row["id"], details_by_id)
        self.assertEqual(
            details_by_id[recent_row["id"]]["trace"]["trace_id"],
            "trace-events-ops",
        )

        filtered_response = self.client.get(
            "/operations/events?topic_prefix=events.named.operations&search=run-events-ops",
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_payload = filtered_response.json()
        self.assertEqual(filtered_payload["module"], "events")
        self.assertEqual(filtered_payload["recent_events"]["total"], 1)

    def test_ui_operations_channels_page_uses_runtime_and_event_state(self) -> None:
        container = self.client.app.state.container
        container.require(AppKey.CHANNEL_PROFILE_SERVICE).upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="ops",
                        transport_mode="callback",
                    ),
                ),
            ),
        )
        container.require(AppKey.WEBHOOK_CHANNEL_RUNTIME_SERVICE).ensure_registered(
            runtime_id="webhook-runtime-ui-ops",
        )
        container.require(AppKey.CHANNEL_INFRASTRUCTURE).interaction_service.upsert_interaction(
            ChannelInteraction(
                interaction_id="webhook:ops:event:ui-ops",
                channel_type="webhook",
                channel_account_id="ops",
                external_event_id="evt-channel-ui-ops",
                external_message_id="msg-channel-ui-ops",
                external_conversation_id="conv-channel-ui-ops",
                external_user_id="user-channel-ui-ops",
                reply_address={
                    "channel_type": "webhook",
                    "channel_account_id": "ops",
                    "webhook_url": "https://example.invalid/channels/ops",
                },
                agent_id="assistant",
                session_key="agent:assistant:webhook:ui-ops",
                run_id="run-channel-ui-ops",
                status="delivered",
                metadata={
                    "active_session_id": "session-channel-ui-ops",
                    "observe_cursor": "7",
                    "last_delivered_at": "2026-05-04T08:30:00Z",
                    "delivered_artifact_ids": "artifact-channel-ui-ops",
                },
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic=channel_dead_letter_topic(
                    "webhook",
                    runtime_id="webhook-runtime-ui-ops",
                ),
                kind="fact",
                target=EventTarget(
                    runtime_id="webhook-runtime-ui-ops",
                    channel_type="webhook",
                    channel_account_id="ops",
                ),
                payload={
                    "event_name": "channel.observation.dead_lettered",
                    "channel_type": "webhook",
                    "runtime_id": "webhook-runtime-ui-ops",
                    "outbound_id": "out-channel-ui-ops",
                    "run_id": "run-channel-ui-ops",
                    "status": "http_503",
                    "attempt_count": 3,
                },
                trace={"trace_id": "trace-channels-ops"},
            ),
        )

        self._materialize_operations("channels")
        response = self.client.get("/operations/channels")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "channels")
        self.assertNotIn("sections", payload)
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metric_by_id["dead_letters"]["value"], "1")
        self.assertEqual(metric_by_id["interactions"]["value"], "1")
        interaction_rows = {
            item["id"]: item for item in payload["interactions"]["rows"]
        }
        self.assertEqual(
            interaction_rows["webhook:ops:event:ui-ops"]["cells"]["status"],
            "Delivered",
        )
        runtime_rows = {
            item["id"]: item for item in payload["channel_status"]["rows"]
        }
        self.assertIn("webhook-runtime-ui-ops", runtime_rows)
        self.assertEqual(
            runtime_rows["webhook-runtime-ui-ops"]["cells"]["channel_type"],
            "webhook",
        )
        dead_letter_rows = payload["dead_letter_queue"]["rows"]
        self.assertEqual(dead_letter_rows[0]["cells"]["outbound_id"], "out-channel-ui-ops")
        self.assertEqual(dead_letter_rows[0]["cells"]["reason"], "http_503")
        details_by_id = {
            item["record_id"]: item for item in payload["record_details"]
        }
        self.assertIn(dead_letter_rows[0]["id"], details_by_id)
        self.assertEqual(
            details_by_id[dead_letter_rows[0]["id"]]["trace"]["trace_id"],
            "trace-channels-ops",
        )
        runtime_details = {
            item["runtime_id"]: item for item in payload["runtime_details"]
        }
        self.assertEqual(
            runtime_details["webhook-runtime-ui-ops"]["dead_letters"]["total"],
            1,
        )
        interaction_rows = {
            item["id"]: item for item in payload["interactions"]["rows"]
        }
        self.assertIn("webhook:ops:event:ui-ops", interaction_rows)
        self.assertEqual(
            interaction_rows["webhook:ops:event:ui-ops"]["cells"]["run_id"],
            "run-channel-ui-ops",
        )
        interaction_details = {
            item["interaction_id"]: item for item in payload["interaction_details"]
        }
        interaction_routing = {
            item["label"]: item["value"]
            for item in interaction_details["webhook:ops:event:ui-ops"]["routing"]["items"]
        }
        self.assertEqual(
            interaction_routing["Observe Cursor"],
            "7",
        )
        interaction_metadata = {
            item["label"]: item["value"]
            for item in interaction_details["webhook:ops:event:ui-ops"]["metadata"]["items"]
        }
        self.assertEqual(
            interaction_metadata["Last Delivered At"],
            "2026-05-04T08:30:00Z",
        )
        self.assertEqual(
            interaction_metadata["Delivered Artifact Ids"],
            "artifact-channel-ui-ops",
        )
        self.assertNotIn(
            "Last " + "Projec" + "ted At",
            interaction_metadata,
        )
        self.assertEqual(
            interaction_details["webhook:ops:event:ui-ops"]["events"]["total"],
            1,
        )
        serialized_payload = json.dumps(payload, ensure_ascii=False).lower()
        self.assertNotIn("projec" + "ted", serialized_payload)
        self.assertNotIn("projec" + "tion", serialized_payload)
        self.assertGreaterEqual(payload["contracts"]["total"], 1)

        filtered_response = self.client.get(
            "/operations/channels?channel_type=webhook&search=out-channel-ui-ops",
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_payload = filtered_response.json()
        self.assertEqual(filtered_payload["channel_status"]["total"], 0)
        self.assertEqual(filtered_payload["dead_letter_queue"]["total"], 1)

    def test_ui_operations_channels_health_ignores_historical_failed_interactions(
        self,
    ) -> None:
        container = self.client.app.state.container
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=3)
        container.require(AppKey.CHANNEL_PROFILE_SERVICE).upsert_profile(
            ChannelProfile(channel_type="webhook"),
        )
        container.require(AppKey.CHANNEL_INFRASTRUCTURE).interaction_registry_store.save(
            ChannelInteractionRegistry(
                interactions=(
                    ChannelInteraction(
                        interaction_id="webhook:ops:event:historical-failed",
                        channel_type="webhook",
                        channel_account_id="ops",
                        run_id="run-channel-historical-failed",
                        status="failed",
                        last_error="historical delivery failure",
                        created_at=old_timestamp,
                        updated_at=old_timestamp,
                    ),
                ),
            ),
        )

        self._materialize_operations("channels")
        response = self.client.get("/operations/channels")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotEqual(payload["health"], "error")
        metric_by_id = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metric_by_id["interactions"]["value"], "1")
        self.assertIn("0 failed", metric_by_id["interactions"]["delta"])

    def test_ui_trace_summary_and_events_use_event_read_model(self) -> None:
        container = self.client.app.state.container
        base_time = datetime(2026, 4, 29, 6, 30, tzinfo=timezone.utc)
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic="turn.session.agent:assistant:trace-ui",
                kind="fact",
                occurred_at=base_time,
                payload={
                    "event_name": "orchestration.run.queued",
                    "run_id": "run-ui-trace",
                    "step_id": "step-ui-trace-intake",
                    "session_key": "agent:assistant:trace-ui",
                    "status": "queued",
                    "stage": "queued",
                    "summary": "queued for trace ui",
                },
                trace={
                    "trace_id": "trace-ui-events",
                    "correlation_id": "corr-ui",
                    "step_id": "step-ui-trace-intake",
                },
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic="turn.live.session.agent:assistant:trace-ui",
                kind="live",
                occurred_at=base_time + timedelta(seconds=2),
                payload={
                    "event_name": "orchestration.run.llm_text_delta",
                    "run_id": "run-ui-trace",
                    "step_id": "step-ui-trace-llm",
                    "session_key": "agent:assistant:trace-ui",
                    "invocation_id": "llm-ui-trace",
                    "text_delta": "hello trace",
                },
                trace={
                    "trace_id": "trace-ui-events",
                    "correlation_id": "corr-ui",
                    "step_id": "step-ui-trace-llm",
                },
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic="events.named.llm.invocation_succeeded",
                kind="fact",
                occurred_at=base_time + timedelta(seconds=4),
                payload={
                    "event_name": "llm.invocation_succeeded",
                    "run_id": "run-ui-trace",
                    "step_id": "step-ui-trace-llm",
                    "invocation_id": "llm-ui-trace",
                    "llm_response_item_id": "llm-ui-trace:item:tool-call",
                    "tool_call_id": "call-ui-trace-browser",
                    "finish_reason": "tool_calls",
                    "text_present": True,
                    "text_chars": 8,
                    "tool_call_count": 1,
                    "tool_call_names": ["browser.snapshot"],
                },
                trace={
                    "trace_id": "trace-ui-events",
                    "correlation_id": "corr-ui",
                    "step_id": "step-ui-trace-llm",
                    "llm_invocation_id": "llm-ui-trace",
                    "llm_response_item_id": "llm-ui-trace:item:tool-call",
                    "tool_call_id": "call-ui-trace-browser",
                },
            ),
        )
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic="events.named.orchestration.execution.llm_step_completed",
                kind="fact",
                occurred_at=base_time + timedelta(seconds=6),
                payload={
                    "event_name": "orchestration.execution.llm_step_completed",
                    "run_id": "run-ui-trace",
                    "step_id": "step-ui-trace-llm",
                    "execution_item_id": "item-ui-trace-progress",
                    "llm_invocation_id": "llm-ui-trace",
                    "session_item_ids": ["session-item-progress-ui-trace"],
                    "assistant_progress_item_ids": ["session-item-progress-ui-trace"],
                    "tool_call_session_item_ids": ["session-item-tool-call-ui-trace"],
                    "tool_call_names": ["browser.snapshot"],
                    "text_present": True,
                    "text_chars": 8,
                },
                trace={
                    "trace_id": "trace-ui-events",
                    "correlation_id": "corr-ui",
                    "step_id": "step-ui-trace-llm",
                    "execution_item_id": "item-ui-trace-progress",
                    "llm_invocation_id": "llm-ui-trace",
                    "session_item_id": "session-item-progress-ui-trace",
                },
            ),
        )

        events_response = self.client.get("/ui/trace/trace-ui-events/events")
        summary_response = self.client.get("/ui/trace/trace-ui-events")
        step_events_response = self.client.get(
            "/ui/trace/trace-ui-events/events?focus_id=step-ui-trace-llm",
        )
        step_summary_response = self.client.get(
            "/ui/trace/trace-ui-events?focus_id=step-ui-trace-llm",
        )

        self.assertEqual(events_response.status_code, 200)
        events_payload = events_response.json()
        self.assertEqual(
            [item["name"] for item in events_payload],
            [
                "orchestration.run.queued",
                "orchestration.run.llm_text_delta",
                "llm.invocation_succeeded",
                "orchestration.execution.llm_step_completed",
            ],
        )
        self.assertEqual(events_payload[0]["family"], "orchestration")
        self.assertEqual(events_payload[0]["summary"], "queued for trace ui")
        self.assertEqual(events_payload[1]["trace"]["llm_invocation_id"], "llm-ui-trace")
        self.assertEqual(events_payload[1]["trace"]["step_id"], "step-ui-trace-llm")
        self.assertEqual(events_payload[1]["relative_ms"], 2000)
        self.assertEqual(events_payload[2]["family"], "llm")
        self.assertEqual(
            events_payload[2]["trace"]["llm_response_item_id"],
            "llm-ui-trace:item:tool-call",
        )
        self.assertEqual(
            events_payload[2]["trace"]["tool_call_id"],
            "call-ui-trace-browser",
        )
        self.assertTrue(events_payload[2]["payload"]["text_present"])
        self.assertEqual(events_payload[2]["payload"]["text_chars"], 8)
        self.assertEqual(events_payload[2]["payload"]["tool_call_count"], 1)
        self.assertEqual(
            events_payload[2]["payload"]["tool_call_names"],
            ["browser.snapshot"],
        )
        self.assertEqual(events_payload[3]["family"], "orchestration")
        self.assertEqual(
            events_payload[3]["trace"]["execution_item_id"],
            "item-ui-trace-progress",
        )
        self.assertEqual(
            events_payload[3]["trace"]["session_item_id"],
            "session-item-progress-ui-trace",
        )
        self.assertEqual(
            events_payload[3]["payload"]["assistant_progress_item_ids"],
            ["session-item-progress-ui-trace"],
        )
        self.assertEqual(
            events_payload[3]["payload"]["tool_call_session_item_ids"],
            ["session-item-tool-call-ui-trace"],
        )

        self.assertEqual(summary_response.status_code, 200)
        summary_payload = summary_response.json()
        self.assertEqual(summary_payload["trace_id"], "trace-ui-events")
        self.assertEqual(summary_payload["event_count"], 4)
        self.assertEqual(summary_payload["key_event_count"], 3)
        self.assertEqual(summary_payload["status"], "running")
        self.assertIn("orchestration", summary_payload["owners"])
        self.assertIn("llm", summary_payload["owners"])

        self.assertEqual(step_events_response.status_code, 200)
        step_events_payload = step_events_response.json()
        self.assertEqual(
            [item["name"] for item in step_events_payload],
            [
                "orchestration.run.llm_text_delta",
                "llm.invocation_succeeded",
                "orchestration.execution.llm_step_completed",
            ],
        )
        self.assertEqual(
            step_events_payload[0]["trace"]["step_id"],
            "step-ui-trace-llm",
        )
        self.assertEqual(step_summary_response.status_code, 200)
        step_summary_payload = step_summary_response.json()
        self.assertEqual(step_summary_payload["event_count"], 3)
        self.assertIn(
            {"type": "step_id", "id": "step-ui-trace-llm"},
            step_summary_payload["linked_entities"],
        )
        self.assertIn(
            {"type": "llm_response_item_id", "id": "llm-ui-trace:item:tool-call"},
            step_summary_payload["linked_entities"],
        )
        self.assertIn(
            {"type": "tool_call_id", "id": "call-ui-trace-browser"},
            step_summary_payload["linked_entities"],
        )
        self.assertIn(
            {"type": "execution_item_id", "id": "item-ui-trace-progress"},
            step_summary_payload["linked_entities"],
        )
        self.assertIn(
            {"type": "session_item_id", "id": "session-item-progress-ui-trace"},
            step_summary_payload["linked_entities"],
        )

    def test_ui_trace_events_are_gated_by_trace_timeline_slice_refs(self) -> None:
        container = self.client.app.state.container
        base_time = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
        session_key = "agent:assistant:trace-slice"
        run_id = "run-ui-trace-slice"
        trace_id = "trace-ui-slice"

        container.require(AppKey.SESSION_SERVICE).ensure_session(
            EnsureSessionInput(
                key=session_key,
                agent_id="assistant",
                workspace="workspace-ui",
            ),
        )
        visible_item = container.require(AppKey.SESSION_SERVICE).append_item(
            AppendSessionItemInput(
                session_key=session_key,
                kind=SessionItemKind.ASSISTANT_MESSAGE,
                role="assistant",
                content_payload={"text": "Visible trace content."},
                source_module="llm",
                source_kind="response_item",
                source_id="llm-response-visible-trace",
            ),
        )
        container.require(AppKey.CONTEXT_WORKSPACE_SERVICE).ensure_workspace(
            EnsureContextWorkspaceInput(
                session_key=session_key,
                agent_id="assistant",
            ),
        )

        for offset, name, session_item_id in (
            (0, "orchestration.run.queued", None),
            (2, "orchestration.execution.llm_step_completed", visible_item.id),
            (4, "orchestration.execution.llm_step_completed", "session-item-hidden-trace"),
        ):
            payload: dict[str, object] = {
                "event_name": name,
                "run_id": run_id,
                "session_key": session_key,
                "summary": f"{name} {offset}",
            }
            trace: dict[str, object] = {
                "trace_id": trace_id,
                "run_id": run_id,
                "session_key": session_key,
            }
            if session_item_id is not None:
                payload["session_item_ids"] = [session_item_id]
                trace["session_item_id"] = session_item_id
            container.require(AppKey.EVENTS_SERVICE).publish(
                Event(
                    topic=f"events.named.{name}",
                    kind="fact",
                    occurred_at=base_time + timedelta(seconds=offset),
                    payload=payload,
                    trace=trace,
                ),
            )

        context_slice = container.require(AppKey.CONTEXT_SLICE_BUILDER).build_slice(
            session_key=session_key,
            run_id=run_id,
            audience="trace_timeline",
        )
        self.assertIn(
            visible_item.id,
            {
                item.owner_ref.get("session_item_id")
                for item in context_slice.items
            },
        )

        events_response = self.client.get(f"/ui/trace/{trace_id}/events")
        summary_response = self.client.get(f"/ui/trace/{trace_id}")

        self.assertEqual(events_response.status_code, 200)
        events_payload = events_response.json()
        self.assertEqual(len(events_payload), 1)
        self.assertEqual(
            events_payload[0]["trace"]["session_item_id"],
            visible_item.id,
        )
        self.assertEqual(
            events_payload[0]["payload"]["session_item_ids"],
            [visible_item.id],
        )

        self.assertEqual(summary_response.status_code, 200)
        summary_payload = summary_response.json()
        self.assertEqual(summary_payload["event_count"], 1)
        self.assertEqual(summary_payload["key_event_count"], 1)
        self.assertIn(
            {"type": "session_item_id", "id": visible_item.id},
            summary_payload["linked_entities"],
        )

    def test_ui_trace_aliases_run_metadata_to_session_events(self) -> None:
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
                "run_id": "run-ui-trace-alias",
                "inbound_instruction": {
                    "source": "http",
                    "content": "alias this trace",
                },
                "session": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                    "channel": "webchat",
                },
                "metadata": {"trace_id": "trace-ui-alias"},
                "enqueue": True,
            },
        )
        self.assertEqual(intake_response.status_code, 201)

        self.client.app.state.container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                topic="turn.session.agent:assistant:main",
                kind="fact",
                payload={
                    "event_name": "orchestration.run.message_appended",
                    "session_key": "agent:assistant:main",
                    "message_id": "msg-ui-trace-alias",
                    "summary": "session-only event matched through trace alias",
                },
            ),
        )

        response = self.client.get("/ui/trace/trace-ui-alias/events")

        self.assertEqual(response.status_code, 200)
        event_names = [item["name"] for item in response.json()]
        self.assertIn("orchestration.run.message_appended", event_names)
