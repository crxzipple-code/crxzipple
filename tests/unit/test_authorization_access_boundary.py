from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "crxzipple"


def _read_files(root: Path) -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    }


def test_access_module_does_not_depend_on_internal_authorization_runtime() -> None:
    access_sources = _read_files(SRC_ROOT / "modules" / "access")
    forbidden = (
        "crxzipple.modules.authorization",
        "AbacAuthorizationEvaluator",
        "AuthorizationPolicy",
        "TemporaryAuthorizationGrant",
    )

    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {needle}"
        for path, text in access_sources.items()
        for needle in forbidden
        if needle in text
    ]

    assert offenders == []


def test_authorization_runtime_is_not_access_backed() -> None:
    sources = {
        **_read_files(SRC_ROOT / "bootstrap"),
        **_read_files(SRC_ROOT / "modules" / "authorization"),
    }
    forbidden = (
        "AccessBackedAuthorization",
        "AccessAuthorizationPolicy",
        "AccessTemporaryGrant",
    )

    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {needle}"
        for path, text in sources.items()
        for needle in forbidden
        if needle in text
    ]

    assert offenders == []


def test_orchestration_internal_authorization_names_do_not_use_access() -> None:
    sources = _read_files(SRC_ROOT / "modules" / "orchestration")
    forbidden = (
        "grant_run_access",
        "grant_session_access",
        "grant_agent_effect_access",
        "grant_agent_tool_access",
        "tool.access_tool",
        "tool.access_effect",
        "remote_tool_access",
        "sensitive_access",
    )

    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {needle}"
        for path, text in sources.items()
        for needle in forbidden
        if needle in text
    ]

    assert offenders == []


def test_access_settings_no_longer_materializes_authorization_policies() -> None:
    sources = {
        **_read_files(SRC_ROOT / "modules" / "settings"),
        SRC_ROOT / "shared" / "settings.py": (
            SRC_ROOT / "shared" / "settings.py"
        ).read_text(encoding="utf-8"),
    }

    offenders = [
        f"{path.relative_to(REPO_ROOT)}"
        for path, text in sources.items()
        if "authorization_policies" in text
    ]

    assert offenders == []
