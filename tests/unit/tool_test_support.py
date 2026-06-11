from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any
import unittest

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    load_settings,
)
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.dispatch.application import RecoverAbandonedDispatchTasksInput
from crxzipple.modules.dispatch.domain import DispatchTaskStatus
from crxzipple.modules.session.application import EnsureSessionInput
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolDefinitionOrigin,
    ToolParameter,
    ToolRunStatus,
)
from crxzipple.modules.tool.infrastructure import (
    LocalToolRuntimeRegistry,
    ToolDependencyBinding,
    ToolNamespaceDefinition,
    ToolRuntimeRegistry,
    discover_tool_namespaces,
)
from tests.unit.support import (
    SampleApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
    publish_outbox_events,
    published_event_bus_events,
)
from tests.unit.orchestration_test_support import (
    process_next_orchestration_assignment,
)
from tests.unit.tool_catalog_seed import seed_catalog_tool, static_text_handler


_TOOL_DEPENDENCY_CAPABILITIES: Mapping[str, tuple[str, ...]] = {
    "artifact_service": ("artifact.read", "artifact.write", "browser.artifact_write"),
    "browser_capabilities_resolver": (
        "browser.profile_read",
        "browser.runtime_readiness",
    ),
    "browser_tool_application": (
        "browser.control",
        "browser.page_action",
        "browser.code_read",
    ),
    "browser_observation_service": (
        "browser.profile_read",
        "browser.page_action",
        "browser.runtime_readiness",
    ),
    "browser_profile_probe_service": ("browser.runtime_readiness",),
    "browser_profile_resolver": ("browser.profile_read", "browser.runtime_readiness"),
    "browser_runtime_state_store": ("browser.runtime_readiness",),
    "browser_system_config_store": (
        "browser.profile_read",
        "runtime_settings.read",
    ),
    "credential_provider": ("credential.read", "access.readiness"),
    "memory_runtime_service": (
        "memory.context_lookup",
        "memory.search",
        "memory.read",
        "memory.write",
        "memory.flush_marker",
    ),
    "mobile_facade": ("mobile.device_read", "mobile.action", "mobile.screenshot"),
    "mobile_result_serializer": (
        "mobile.device_read",
        "mobile.action",
        "mobile.screenshot",
    ),
    "session_runtime_control": (
        "session.read",
        "session.write",
        "session.tree_read",
        "session.route_enqueue",
        "session.tree_cancel",
        "run_control.yield",
    ),
    "process_service": ("process.spawn", "process.manage"),
    "session_service": ("session.read", "session.write", "session.tree_read"),
    "session_workspace_lookup": ("workspace.lookup", "session.read"),
    "skill_manager": ("skill.read",),
    "skill_authoring_service": ("skill.read",),
}


def tool_dependency_bindings(
    values: Mapping[str, Any],
) -> dict[str, ToolDependencyBinding]:
    return {
        dependency_id: ToolDependencyBinding(
            dependency_id,
            value,
            capability_ids=_TOOL_DEPENDENCY_CAPABILITIES.get(dependency_id, ()),
        )
        for dependency_id, value in values.items()
    }



class ToolTestCaseBase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_runtime_container()
        self._bind_runtime_services()

    def tearDown(self) -> None:
        self.harness.close()
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )

    def _bind_runtime_services(self) -> None:
        self.access_service = self.container.require(AppKey.ACCESS_SERVICE)
        self.agent_service = self.container.require(AppKey.AGENT_SERVICE)
        self.artifact_service = self.container.require(AppKey.ARTIFACT_SERVICE)
        self.authorization_service = self.container.require(
            AppKey.AUTHORIZATION_SERVICE,
        )
        self.dispatch_service = self.container.require(AppKey.DISPATCH_SERVICE)
        self.event_bus = self.container.require(AppKey.EVENTS_BUS)
        self.file_memory_service = self.container.require(AppKey.FILE_MEMORY_SERVICE)
        self.memory_runtime_service = self.container.require(
            AppKey.MEMORY_RUNTIME_SERVICE,
        )
        self.llm_adapter_registry = self.container.require(
            AppKey.LLM_ADAPTER_REGISTRY,
        )
        self.llm_service = self.container.require(AppKey.LLM_SERVICE)
        self.local_runtime_registry = self.container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY)
        self.memory_context_resolver = self.container.require(
            AppKey.MEMORY_CONTEXT_RESOLVER,
        )
        self.orchestration_run_query_service = self.container.require(
            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE,
        )
        self.orchestration_scheduler_service = self.container.require(
            AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
        )
        self.process_service = self.container.require(AppKey.PROCESS_SERVICE)
        self.session_service = self.container.require(AppKey.SESSION_SERVICE)
        self.skill_manager = self.container.require(AppKey.SKILL_MANAGER)
        self.tool_runtime_event_service = self.container.require(
            AppKey.TOOL_RUNTIME_EVENT_SERVICE,
        )
        self.tool_scheduler_service = self.container.require(
            AppKey.TOOL_SCHEDULER_SERVICE,
        )
        self.tool_service = self.container.require(AppKey.TOOL_SERVICE)
        self.tool_worker_service = self.container.require(AppKey.TOOL_WORKER_SERVICE)
        self.uow_factory = self.container.require(AppKey.UNIT_OF_WORK_FACTORY)

    def seed_tool(self, **kwargs: Any):
        return seed_catalog_tool(self.container, **kwargs)

    def publish_outbox_events(self) -> int:
        return publish_outbox_events(self.container)

    def published_event_bus_events(self) -> tuple[object, ...]:
        return published_event_bus_events(self.container)


__all__ = [name for name in globals() if not name.startswith("__")]
