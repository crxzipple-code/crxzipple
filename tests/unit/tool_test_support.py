from __future__ import annotations

import asyncio
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
import unittest

from crxzipple.core.config import (
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    load_settings,
)
from crxzipple.modules.dispatch.application import RecoverAbandonedDispatchTasksInput
from crxzipple.modules.dispatch.domain import DispatchTaskStatus
from crxzipple.modules.session.application import EnsureSessionInput
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    RegisterToolInput,
    RegisterToolParameterInput,
    SetToolAvailabilityInput,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolSourceKind,
    ToolRunStatus,
)
from crxzipple.modules.tool.infrastructure import (
    LocalToolCatalog,
    ToolNamespaceDefinition,
    ToolRuntimeRegistry,
    discover_tool_namespaces,
    register_scanned_tool_packages,
)
from tests.unit.support import (
    SampleApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
)
from tests.unit.orchestration_test_support import (
    process_next_orchestration_assignment,
)



class ToolTestCaseBase(unittest.TestCase):
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


__all__ = [name for name in globals() if not name.startswith("__")]
