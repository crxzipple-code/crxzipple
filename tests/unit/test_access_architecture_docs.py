from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_DOC = (
    REPO_ROOT
    / "docs"
    / "reports"
    / "authorization-access-boundary-remediation-checklist-20260508.md"
)
ACTIVE_DOCS = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "agents" / "hosted-agent-operating-contract.md",
    REPO_ROOT / "docs" / "instruction-assets-memory-auth-design.md",
    REPO_ROOT / "docs" / "orchestration-design.md",
    REPO_ROOT / "docs" / "ui" / "current-ui-design-functional-spec.md",
    REPO_ROOT / "docs" / "ui" / "runtime-ui-read-model-contracts.md",
)


def test_access_authorization_boundary_uses_current_governance_language() -> None:
    text = CHECKLIST_DOC.read_text(encoding="utf-8")
    normalized = " ".join(text.lower().split())

    forbidden_current_constraints = [
        "authorization remains a decision protocol/evaluator inside the access boundary",
    ]

    for phrase in forbidden_current_constraints:
        assert phrase not in normalized

    required_current_constraints = [
        "access owns authorization policy / temporary grant”的阶段性判断",
        "`authorization` = internal abac runtime and governance",
        "`access` = external provider/account/credential governance",
        "access 去 abac 化",
        "access action 删除",
    ]

    for phrase in required_current_constraints:
        assert phrase in normalized


def test_access_governance_checklist_tracks_doc_constraint_test() -> None:
    text = CHECKLIST_DOC.read_text(encoding="utf-8")

    assert "Worker B：Access 去 ABAC 化" in text
    assert "Access query/read model 不再展示内部 ABAC policy" in text


def test_active_docs_do_not_reintroduce_access_owned_authorization_truth() -> None:
    forbidden_phrases = (
        "access-owned authorization",
        "access-owned policy",
        "access owns authorization policy",
        "access owns internal abac",
        "authorization policy and temporary grant truth are part of access",
        "policy and grant repositories are owned by access",
        "access-owned policy/grant truth",
    )

    offenders: list[str] = []
    for path in ACTIVE_DOCS:
        text = " ".join(path.read_text(encoding="utf-8").lower().split())
        for phrase in forbidden_phrases:
            if phrase in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {phrase}")

    assert offenders == []
