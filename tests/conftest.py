from __future__ import annotations

import os
from pathlib import Path

import pytest


if os.environ.get("CRXZIPPLE_USE_EXTERNAL_TEST_INFRA") != "1":
    os.environ["APP_EVENTS_BACKEND"] = "file"
    os.environ.pop("APP_EVENTS_REDIS_URL", None)
    os.environ.pop("APP_EVENTS_REDIS_KEY_PREFIX", None)
    os.environ.pop("APP_EVENTS_REDIS_BLOCK_MS", None)
    os.environ.pop("APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS", None)
os.environ.setdefault("APP_CHANNEL_PROFILE_PATHS", os.pathsep)


_RUNTIME_FILE_SUFFIXES = (
    "_cli.py",
    "_http.py",
)


_RUNTIME_FILE_NAMES = {
    "test_main_cli.py",
    "test_browser_cdp_host_daemon.py",
    "test_daemon_manager.py",
    "test_daemon_service.py",
    "test_events.py",
    "test_orchestration_approval.py",
    "test_orchestration_context.py",
    "test_orchestration_executor_leases.py",
    "test_orchestration_memory.py",
    "test_orchestration_queue.py",
    "test_orchestration_tools.py",
    "test_operations_observation.py",
    "test_tool_background.py",
    "test_tool_execution.py",
    "test_worker_loops.py",
}


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    root = Path(str(config.rootpath)).resolve()
    for item in items:
        path = Path(str(item.fspath)).resolve()
        try:
            relative_path = path.relative_to(root)
        except ValueError:
            relative_path = path
        path_parts = relative_path.parts
        file_name = path.name
        if path_parts[:2] == ("tests", "integration"):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.live)
            item.add_marker(pytest.mark.slow)
            continue
        if "benchmark" in item.name:
            item.add_marker(pytest.mark.benchmark)
        if _is_runtime_test_file(file_name):
            item.add_marker(pytest.mark.runtime)
        else:
            item.add_marker(pytest.mark.fast)


def _is_runtime_test_file(file_name: str) -> bool:
    if file_name in _RUNTIME_FILE_NAMES:
        return True
    return file_name.startswith("test_") and file_name.endswith(_RUNTIME_FILE_SUFFIXES)
