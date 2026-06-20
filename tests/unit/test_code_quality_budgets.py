from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

FILE_LINE_BUDGETS = {
    "frontend/src/pages/operations/modules/ToolOperationsPage.vue": 4300,
    "frontend/src/pages/operations/modules/tool/viewHelpers.ts": 700,
    "tests/unit/test_ui_http.py": 3300,
    "tests/unit/test_ui_operations_http.py": 3400,
    "tests/unit/test_ui_operations_actions_http.py": 260,
    "tests/unit/test_browser_tool_http.py": 3200,
    "tests/unit/test_browser_tool_http_advanced.py": 2200,
    "tests/browser/test_browser_tool_http.py": 3200,
}


def test_f14_large_file_budgets_do_not_regress() -> None:
    failures: list[str] = []
    for relative_path, budget in FILE_LINE_BUDGETS.items():
        path = ROOT / relative_path
        if not path.exists():
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > budget:
            failures.append(f"{relative_path}: {line_count} lines exceeds budget {budget}")

    assert failures == []
