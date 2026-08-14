import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_runtime_rule_paths_exist_without_duplicated_loading_algorithm() -> None:
    for path in sorted(REPO_ROOT.glob("skills/orch-*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        for rule_path in re.findall(r"`(rules/orchestration/[^`]+)`", text):
            assert (REPO_ROOT / rule_path).is_file(), f"{path.name}: {rule_path}"
        if path.name == "SKILL.md" and path.parent.name in {
            "orch-create-specification",
            "orch-create-implementation-plan",
            "orch-execute-plan",
            "orch-review-plan",
        }:
            assert "## Rule Loading (mandatory)" not in text
            assert "Central `AGENTS.md` owns rule discovery and loading" in text


def test_obsolete_role_context_surface_is_removed() -> None:
    for relative in [
        "skills/wb-select-role-context/SKILL.md",
        "rules/role-context.md",
        "references/wb-select-role-context-contract.yaml",
        "scripts/work-bundle/role_context.py",
    ]:
        assert not (REPO_ROOT / relative).exists(), relative

    for relative in [
        "skills/orch-create-document/SKILL.md",
        "skills/orch-create-handoff/SKILL.md",
        "references/assets/keep-summarizing/workflow.md",
        "scripts/work-bundle/README.md",
        "scripts/work-bundle/core.py",
        "scripts/work-bundle/dispatcher.py",
        "scripts/work-bundle/metadata_profile.py",
        "scripts/work-bundle/project.py",
        "rules/index.yaml",
    ]:
        text = read(relative).lower()
        assert "wb-select-role-context" not in text, relative
        assert "role-context" not in text, relative
        assert "role context" not in text, relative


def test_specification_uses_compact_semantic_convergence_and_workspace_policy() -> None:
    text = read("skills/orch-create-specification/SKILL.md")
    for token in [
        "dev-semantic-convergence",
        "user-purpose coverage",
        "authority and evidence support",
        "requirement, constraint, and open-question consistency",
        "impact radius",
        "Knowledge Base Update disposition",
        "execution-workspace policy",
        "semantic_loop:",
        "Quality gate: verified|blocked",
        "Initial User Purpose Evidence",
        "Design Interrogation",
    ]:
        assert token in text
    assert "Extra evidence loop" not in text


def test_planner_allocates_methodology_capability_and_bounded_context() -> None:
    text = read("skills/orch-create-implementation-plan/SKILL.md")
    for token in [
        "Prefer the fewest phases and tasks",
        "source-ID coverage",
        "dev-systematic-debugging",
        "dev-test-driven-development",
        "dev-code-review",
        "mechanical",
        "standard",
        "judgment",
        "context_mode: compiled-brief",
        "acceptance_review:",
        "after_failed_repairs: 2",
        "common contract group",
        "post-barrier convergence task",
        "Truth Basis",
        "earliest ordinary task",
        "cheaply falsify",
        "Do not add a risk score",
    ]:
        assert token in text


def test_execute_skill_uses_compiler_independent_review_and_typed_blockers() -> None:
    text = read("skills/orch-execute-plan/SKILL.md")
    for token in [
        "## Execution Constraints (skill-owned)",
        "## Scheduler-Owned Constraints",
        "## Executor-Owned Constraints",
        "build-task-brief",
        "build-review-package",
        "dev-code-review",
        "The scheduler does not perform code-quality review",
        "reviewer_independent: false",
        "After two failed repair rounds",
        "acceptance_review.verdict: accept",
        "context-blocked",
        "repository-blocked",
        "decision-blocked",
        "validation-blocked",
        "review-blocked",
        "knowledge-blocked",
        "workspace-blocked",
        "no-index",
        "no-retrieval",
        "Truth Basis",
        "knowledge disposition",
        "task-local evidence",
        "review owns",
    ]:
        assert token in text


def test_final_review_is_workflow_audit_not_code_review() -> None:
    text = read("skills/orch-review-plan/SKILL.md")
    for token in [
        "workflow audit",
        "Independent `dev-code-review` owns task-scoped implementation quality",
        "acceptance_review.verdict: accept",
        "review-blocked",
        "knowledge-blocked",
        "repository-blocked",
        "workspace-blocked",
        "repair plan only",
        "repair specification",
        "Do not broadly inspect source",
        "Do not create a repair specification for every failed gate",
    ]:
        assert token in text


def test_orch_doctor_remains_read_only() -> None:
    text = read("skills/orch-doctor/SKILL.md")
    assert "## Read-Only Constraints (skill-owned)" in text
    assert "Files changed: none" in text
