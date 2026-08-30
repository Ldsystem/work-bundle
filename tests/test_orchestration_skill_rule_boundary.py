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
        "impact-decision view",
        "accepted | excluded | blocking",
        "none_relevant",
        "stopping_reason",
        "projects_to",
    ]:
        assert token in text
    assert "Extra evidence loop" not in text


def test_planner_allocates_methodology_capability_and_bounded_context() -> None:
    text = read("skills/orch-create-implementation-plan/SKILL.md")
    for token in [
        "minimum orchestration overhead",
        "independently falsifiable",
        "bounded failure radius",
        "Do not split one mechanical increment",
        "source-ID coverage",
        "dev-systematic-debugging",
        "dev-test-driven-development",
        "dev-code-review",
        "mechanical",
        "standard",
        "judgment",
        "context_mode: compiled-brief",
        "acceptance_review:",
        "acceptance_review.required: false",
        "Do not infer",
        "soft applicability prose",
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
        "validate-executor-result",
        "build-review-package",
        "dev-code-review",
        "The scheduler does not perform code-quality review",
        "reviewer_independent: false",
        "After two failed repair rounds",
        "acceptance_review.required: true",
        "review_required: true",
        "does not require `verdict: accept`",
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
        "compiled Truth Basis",
        "AUTH constraints",
        "universal task-review evidence",
        "implementation-review agent",
        "explicitly required",
        "review-blocked",
        "knowledge-blocked",
        "repository-blocked",
        "workspace-blocked",
        "repair plan only",
        "repair specification",
        "Do not broadly inspect source",
        "Do not create a repair specification for every failed gate",
        "aggregate accepted task dispositions",
        "accepted `update`, `supersede`, or `reclassify`",
        "rejected task dispositions",
        "archive remains blocked",
        "RuntimeVerificationClassificationV1",
        "invariant_trace",
        "negative_evidence",
        "owning_repair",
        "execution_introduced_bug",
        "implementation_gap",
        "new_feature",
        "uncovered_fixture",
    ]:
        assert token in text


def test_runtime_verification_classification_contract_routes_the_first_broken_artifact() -> None:
    for relative in [
        "skills/orch-review-plan/SKILL.md",
        "rules/orchestration/orch-review-completion.md",
    ]:
        text = read(relative)
        for token in [
            "RuntimeVerificationClassificationV1",
            "original user request",
            "accepted specification",
            "invariant_trace",
            "negative_evidence",
            "execution_introduced_bug",
            "implementation_gap",
            "new_feature",
            "uncovered_fixture",
            "owning_repair",
            "presentation",
            "wb-violation-evaluation",
            "work-bundle-scoped or mixed",
            "same-scope specification-owned",
            "task repair",
            "plan repair",
            "specification repair",
        ]:
            assert token in text, f"{relative}: {token}"
        assert "unit tests alone" in text
        assert "must not decide the semantic class" in text


def test_workflow_makes_task_review_optional_on_the_chain() -> None:
    text = read("references/assets/orchestration/workflow.md")
    for token in [
        "optional task review",
        "validate-executor-result",
        "does not require `verdict: accept`",
        "acceptance_review.required: true",
    ]:
        assert token in text
    assert "-> independent dev-code-review" not in text


def test_orchestration_doctor_uses_optional_review_anchors() -> None:
    text = (REPO_ROOT / "scripts/orchestration/doctor.py").read_text(encoding="utf-8")

    assert '"optional task review"' in text
    assert '"acceptance_review.required: true"' in text
    assert '"independent dev-code-review"' not in text


def test_doctor_execute_path_requires_validate_not_universal_review() -> None:
    text = read("scripts/orchestration/doctor.py")
    start = text.index('skill_root / "orch-execute-plan" / "SKILL.md"')
    first_list = text[start:].split("[", 1)[1].split("]", 1)[0]
    assert "validate-executor-result" in first_list
    assert "acceptance_review.verdict: accept" not in first_list
    assert "build-review-package" not in first_list

    review_start = text.index('skill_root / "orch-review-plan" / "SKILL.md"')
    review_list = text[review_start:].split("[", 1)[1].split("]", 1)[0]
    assert "acceptance_review.verdict: accept" not in review_list
    assert "compiled Truth Basis" in review_list


def test_orch_doctor_remains_read_only() -> None:
    text = read("skills/orch-doctor/SKILL.md")
    assert "## Read-Only Constraints (skill-owned)" in text
    assert "Files changed: none" in text
