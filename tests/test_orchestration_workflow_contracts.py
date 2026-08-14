import argparse
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCH_ROOT))

from doctor import check_active_handoff_contract
from handoffs import cmd_write_handoff, index_handoffs


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def evals() -> list[dict[str, object]]:
    return json.loads(read("references/evals/orchestration/evals.json"))["evals"]


def handoff_args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "project_root": str(tmp_path),
        "content_file": str(tmp_path / "handoff-content.txt"),
        "type": "executor-result",
        "status": "active",
        "id": "handoff-exec-20990101-001",
        "title": "Task Result",
        "format": None,
        "related_spec": "spec-001",
        "related_plan": "plan-001",
        "related_phase": "phase-001",
        "related_task": "task-001",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_handoff_helper_indexes_sparse_executor_result(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("result:\n  state: completed\n  summary: ok\n", encoding="utf-8")
    cmd_write_handoff(handoff_args(tmp_path, content_file=str(content)))
    row = next(item for item in index_handoffs(handoff_args(tmp_path)) if item["id"] == "handoff-exec-20990101-001")
    assert row["type"] == "executor-result"
    assert row["related_task"] == "task-001"
    assert row["path"].endswith("handoff-exec-20990101-001-task-result.yaml")


def test_handoff_helper_rejects_active_orchestration_handoff(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("# retired\n", encoding="utf-8")
    args = handoff_args(tmp_path, content_file=str(content), type="orchestration", id="handoff-orch-20990101-001")
    with pytest.raises(SystemExit, match="Active orchestration handoff creation is retired"):
        cmd_write_handoff(args)


def test_doctor_rejects_forbidden_executor_fields_and_retired_handoffs(tmp_path: Path) -> None:
    root = tmp_path / ".work-bundle/orchestration/handoff"
    executor = root / "executor/active"
    orchestration = root / "orchestration/active"
    executor.mkdir(parents=True)
    orchestration.mkdir(parents=True)
    (executor / "bad.yaml").write_text("id: bad\nrecommended_next_actions: []\n", encoding="utf-8")
    (orchestration / "bad.md").write_text("# retired\n", encoding="utf-8")
    issues: list[str] = []
    check_active_handoff_contract(issues, tmp_path / ".work-bundle/orchestration")
    assert any("forbidden field recommended_next_actions" in issue for issue in issues)
    assert any("active orchestration handoff is retired" in issue for issue in issues)


def test_specification_contract_uses_semantic_loop_and_workspace_policy() -> None:
    contract = read("references/assets/orchestration/contract/specification-v1.md")
    for token in [
        "Initial User Purpose Evidence",
        "Draft Requirement Breakdown",
        "Source Context",
        "Design Interrogation",
        "Knowledge Base Update",
        "Quality gate: verified|blocked",
        "execution_workspace:",
        "isolation: required|preferred|existing",
        "semantic_loop:",
        "dev-semantic-convergence",
    ]:
        assert token in contract
    assert "Extra evidence loop" not in contract


def test_task_contract_compiles_methodology_capability_and_review() -> None:
    contract = read("references/assets/orchestration/contract/task-v1.md")
    for token in [
        "source_ids:",
        "truth_basis:",
        "as_is_evidence:",
        "decision_authority:",
        "expected_delta:",
        "conflict_status: clear|escalate",
        "decision-blocked",
        "must be an accepted ID already present in the task's `source_ids`",
        "methodology:",
        "tdd|systematic-debugging|direct|loop-coding",
        "executor_profile:",
        "mechanical|standard|judgment",
        "context_mode: compiled-brief",
        "after_failed_repairs: 2",
        "acceptance_review:",
        "verdict: pending",
        "Fresh task validation evidence exists",
        "acceptance_review.verdict",
    ]:
        assert token in contract


def test_executor_result_contract_carries_acceptance_review() -> None:
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    for token in [
        "acceptance_review:",
        "reviewer_independent: true | false",
        "verdict: pending | accept | repair | blocked",
        "reviewed_head: commit-or-tree-identity",
        "scope: specification | correctness | quality | validation | rule",
        "Full specification, root-plan, and phase inspection is an escalation path",
        "knowledge_disposition:",
        "none | update | supersede | reclassify",
        "review owns any approved persistence follow-up",
        "must not name knowledge paths or persistence skills",
    ]:
        assert token in contract


def test_workflow_separates_durable_artifacts_from_runtime_packets() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "Disposable task briefs, review packages, and lightweight development plans",
        ".work-bundle/runtime/",
        "no active/archive/index lifecycle",
        "build-task-brief",
        "Missing source IDs fail closed",
        "Full specification, root-plan, and phase reading is an escalation path",
        "Execution remains no-retrieval",
    ]:
        assert token in workflow


def test_workflow_assigns_review_ownership_and_repair_loop() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "Reviewers own acceptance judgment",
        "Schedulers own dependencies",
        "they do not perform code-quality review",
        "reviewer_independent: false",
        "After two failed low-cost repair rounds",
        "A task becomes `Completed` only when",
        "required `accept` review evidence",
    ]:
        assert token in workflow


def test_review_rule_uses_typed_resume_routing() -> None:
    rule = read("rules/orchestration/orch-review-completion.md")
    for token in [
        "review-blocked",
        "knowledge-blocked",
        "repository-blocked",
        "workspace-blocked",
        "resume the owning execution step",
        "plan repair only for a decomposition defect",
        "specification repair only for a requirement, design, or authority defect",
        "Do not create a repair specification for every failed review gate",
    ]:
        assert token in rule


def test_workflow_preserves_repository_codegraph_workspace_and_secret_safety() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        ".work-bundle/project.yaml",
        "Never stash, reset, clean, restore, delete, or overwrite user work",
        "CodeGraph first only when a target contains `.codegraph/`",
        "Record `no-index`",
        "Never delete user or harness workspaces",
        "Never copy credential values",
        "credential-inject",
    ]:
        assert token in workflow


def test_evals_cover_twenty_migration_behaviors() -> None:
    cases = evals()
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)
    for token in [
        "accepted independent task review",
        "no task-review verdict",
        "wrong API requirement",
        "Knowledge Base Update disposition required",
        "semantic view finds one missing constraint",
        "omits one spec ID",
        "low-judgment two-file implementation",
        "Compile a task brief",
        "changes testable production behavior",
        "configuration-only task",
        "unexpected retry bug",
        "independent task reviewer",
        "second repeated repair rejection",
        "lightweight mechanical plan",
        "provenance owner is user",
        "credential-inject",
        "Hydrate .codegraph",
        "before the final edit",
        "durable knowledge update is unresolved",
        "compiled brief is valid",
    ]:
        assert token in prompts
    for token in [
        "review-blocked",
        "specification repair",
        "knowledge-blocked",
        "semantic_loop",
        "capability mechanical",
        "fails closed on missing IDs",
        "systematic debugging",
        "escalates to full orchestration",
        "Refuses deletion",
        "does not blindly copy or symlink",
        "evidence is stale",
        "full specification, root-plan, and phase reads",
    ]:
        assert token in expected
