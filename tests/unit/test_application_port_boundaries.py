from __future__ import annotations

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _assert_no_word(text: str, word: str) -> None:
    assert re.search(rf"\b{re.escape(word)}\b", text) is None


def test_cross_module_application_dependencies_use_ports() -> None:
    guarded_files = {
        "src/crxzipple/modules/access/application/importer.py": (
            "SettingsActionService",
            "SettingsQueryService",
        ),
        "src/crxzipple/modules/access/application/settings_integration.py": (
            "SettingsActionService",
            "SettingsQueryService",
        ),
        "src/crxzipple/modules/ocr/application/services.py": (
            "ArtifactApplicationService",
        ),
        "src/crxzipple/modules/channels/application/control.py": (
            "DaemonApplicationService",
        ),
        "src/crxzipple/modules/dispatch/application/observers/wakeup.py": (
            "EventsApplicationService",
        ),
        "src/crxzipple/modules/event_relay/application/runtime.py": (
            "EventsApplicationService",
        ),
        "src/crxzipple/modules/event_relay/application/observers.py": (
            "EventsApplicationService",
        ),
        "src/crxzipple/modules/operations/application/projections.py": (
            "EventsApplicationService",
        ),
        "src/crxzipple/modules/operations/application/observer_runtime_service.py": (
            "EventsApplicationService",
        ),
        "src/crxzipple/modules/daemon/application/manager.py": (
            "ProcessApplicationService",
        ),
    }

    for relative_path, forbidden_words in guarded_files.items():
        text = _source(relative_path)
        for word in forbidden_words:
            _assert_no_word(text, word)
