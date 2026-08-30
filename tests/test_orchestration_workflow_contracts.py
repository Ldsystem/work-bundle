from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCH_ROOT))

from doctor import check_active_handoff_contract
from execution_context import (
    build_review_package,
    evaluate_knowledge_closure_state,
    validate_executor_result_for_task,
)
from handoffs import cmd_write_handoff, index_handoffs
from plans import _material_repository_root, _verified_handoff_tree


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


def _task_brief(*, plan_id: str = "plan-001", task_id: str = "task-001") -> dict[str, object]:
    return {
        "task_id": task_id,
        "plan_id": plan_id,
        "source_ids": [],
        "files": {"read": [], "write": []},
        "truth_basis": {},
        "validation": [],
        "review_required": False,
    }


def _completed_executor_result(
    *,
    plan: str | None = "plan-001",
    task: str = "task-001",
    acceptance_review: dict[str, object] | None = None,
) -> dict[str, object]:
    related: dict[str, object] = {"task": task}
    if plan is not None:
        related["plan"] = plan
    handoff: dict[str, object] = {
        "type": "executor-result",
        "related": related,
        "result": {"state": "completed"},
        "task_fit_check": {"task": task, "result": "clean"},
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }
    if acceptance_review is not None:
        handoff["acceptance_review"] = acceptance_review
    return handoff


def test_handoff_helper_indexes_sparse_executor_result(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("result:\n  state: completed\n  summary: ok\n", encoding="utf-8")
    cmd_write_handoff(handoff_args(tmp_path, content_file=str(content)))
    row = next(item for item in index_handoffs(handoff_args(tmp_path)) if item["id"] == "handoff-exec-20990101-001")
    assert row["type"] == "executor-result"
    assert row["related_task"] == "task-001"
    assert row["path"].endswith("handoff-exec-20990101-001-task-result.yaml")


def test_handoff_tree_resolves_recorded_repository_instead_of_control_root(tmp_path: Path) -> None:
    from test_orchestration_execution_context import git

    control_root = tmp_path / "control"
    execution_root = tmp_path / "execution-flow"
    control_root.mkdir()
    execution_root.mkdir()
    git(execution_root, "init", "-q")
    git(execution_root, "config", "user.email", "test@example.com")
    git(execution_root, "config", "user.name", "Test")
    (execution_root / "feature.ts").write_text("export const ready = true;\n", encoding="utf-8")
    git(execution_root, "add", ".")
    git(execution_root, "commit", "-qm", "feature")
    head = git(execution_root, "rev-parse", "HEAD").strip()
    tree = git(execution_root, "rev-parse", "HEAD^{tree}").strip()
    handoff = {
        "repository": [{"root": str(execution_root), "metadata": {"actual_commit": head}}],
    }

    assert _verified_handoff_tree(control_root, handoff) == tree


def test_material_repository_prefers_fresh_terminal_plan_acceptance_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_orchestration_execution_context import git

    control_root = tmp_path / "control"
    earlier_root = tmp_path / "earlier"
    accepted_root = tmp_path / "accepted"
    control_root.mkdir()
    for root, content in ((earlier_root, "old\n"), (accepted_root, "accepted\n")):
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.email", "test@example.com")
        git(root, "config", "user.name", "Test")
        (root / "feature.ts").write_text(content, encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "feature")

    command = "pnpm run ci"
    earlier_head = git(earlier_root, "rev-parse", "HEAD").strip()
    accepted_head = git(accepted_root, "rev-parse", "HEAD").strip()
    validated = [
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(earlier_root), "metadata": {"actual_commit": earlier_head}}],
                "validation": {"commands": []},
            },
            {"task_id": "task-001", "files": {"write": ["feature.ts"]}},
        ),
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(accepted_root), "metadata": {"actual_commit": accepted_head}}],
                "validation": {"commands": [{"command": command, "result": "passed"}]},
            },
            {"task_id": "task-002", "files": {"write": ["feature.ts"]}},
        ),
    ]
    monkeypatch.setattr("plans._plan_task_order", lambda _args, _plan_id: {"task-001": 1, "task-002": 2})

    assert _material_repository_root(
        argparse.Namespace(project_root=str(control_root)), "plan-001", validated, [command]
    ) == accepted_root.resolve()


def test_material_repository_rejects_fresh_acceptance_before_later_material_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_orchestration_execution_context import git

    earlier_root = tmp_path / "earlier"
    later_root = tmp_path / "later"
    for root in (earlier_root, later_root):
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.email", "test@example.com")
        git(root, "config", "user.name", "Test")
        (root / "feature.ts").write_text(f"{root.name}\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "feature")

    command = "pnpm run ci"
    earlier_head = git(earlier_root, "rev-parse", "HEAD").strip()
    later_head = git(later_root, "rev-parse", "HEAD").strip()
    validated = [
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(earlier_root), "metadata": {"actual_commit": earlier_head}}],
                "validation": {"commands": [{"command": command, "result": "passed"}]},
            },
            {"task_id": "task-010", "files": {"write": ["feature.ts"]}},
        ),
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(later_root), "metadata": {"actual_commit": later_head}}],
                "validation": {"commands": []},
            },
            {"task_id": "task-002", "files": {"write": ["feature.ts"]}},
        ),
    ]
    monkeypatch.setattr("plans._plan_task_order", lambda _args, _plan_id: {"task-010": 1, "task-002": 2})

    with pytest.raises(SystemExit, match="acceptance-blocked: final plan repository is ambiguous"):
        _material_repository_root(
            argparse.Namespace(project_root=str(tmp_path)), "plan-001", validated, [command]
        )


def test_material_repository_rejects_material_handoff_without_repository_provenance(tmp_path: Path) -> None:
    command = "pnpm run ci"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    metadata = tmp_path / ".work-bundle/project.yaml"
    metadata.parent.mkdir()
    metadata.write_text(
        "metadata_version: 3\n"
        "workspace_root: " + str(tmp_path) + "\n"
        "workspace_mode: multi-repository\n"
        "source_repositories:\n"
        "  first:\n"
        "    project_root: " + str(first) + "\n"
        "  second:\n"
        "    project_root: " + str(second) + "\n",
        encoding="utf-8",
    )
    validated = [
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "validation": {"commands": [{"command": command, "result": "passed"}]},
            },
            {"task_id": "task-001", "files": {"write": ["feature.ts"]}},
        ),
    ]

    with pytest.raises(
        SystemExit, match="acceptance-blocked: material handoff repository provenance is unavailable"
    ):
        _material_repository_root(
            argparse.Namespace(project_root=str(tmp_path)), "plan-001", validated, [command]
        )


def test_write_handoff_fills_missing_task_plan_from_authorized_args(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "related:\n  task: task-001\nresult:\n  state: completed\n  summary: ok\n",
        encoding="utf-8",
    )
    cmd_write_handoff(
        handoff_args(tmp_path, content_file=str(content), related_plan="plan-B", related_task="task-001")
    )
    row = next(item for item in index_handoffs(handoff_args(tmp_path)) if item["id"] == "handoff-exec-20990101-001")
    written = (tmp_path / row["path"]).read_text(encoding="utf-8")
    assert "plan: plan-B" in written
    assert "task: task-001" in written


def test_write_handoff_rejects_conflicting_plan_identity(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "related:\n  plan: plan-A\n  task: task-001\nresult:\n  state: completed\n  summary: ok\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Handoff plan mismatch"):
        cmd_write_handoff(
            handoff_args(tmp_path, content_file=str(content), related_plan="plan-B", related_task="task-001")
        )


def test_write_handoff_rejects_nested_and_flat_plan_conflict(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "related:\n  plan: plan-B\n  task: task-001\nrelated_plan: plan-A\n"
        "result:\n  state: completed\n  summary: ok\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Handoff plan identity conflict"):
        cmd_write_handoff(
            handoff_args(tmp_path, content_file=str(content), related_plan="plan-B", related_task="task-001")
        )


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
        "front-matter `source_knowledge` contains accepted authority only",
        "Candidate, background, blocked, and superseded",
        "AUTH-NNN: <carried constraint>",
    ]:
        assert token in contract
    assert "Extra evidence loop" not in contract


def test_specification_contract_requires_bounded_impact_decisions() -> None:
    contract = read("references/assets/orchestration/contract/specification-v1.md")
    skill = read("skills/orch-create-specification/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    evals = read("references/evals/orchestration/evals.json")
    for text in (contract, skill, workflow):
        for token in [
            "impact_decisions",
            "accepted | excluded | blocking",
            "none_relevant",
            "stopping_reason",
            "projects_to",
            "current-state evidence",
            "dirty work",
        ]:
            assert token in text
        assert "durable knowledge" in text
        assert "projects_to" in text and "stable" in text
        assert "user-observable or contractual outcome" in text
        assert "measurable quality target" in text
    for text in (contract, skill):
        assert "blocking" in text and "open question" in text.lower()
    assert "blocking relations prevent verification" in workflow
    assert "impact-decision view" in skill
    assert "keep repository traversal out of `dev-semantic-convergence`" in skill
    assert "Git history, prior work artifacts, execution evidence, or durable knowledge" in skill
    assert "user did not mention" in contract
    assert "existing downstream consumer" in evals
    assert "greenfield isolated utility" in evals
    assert "mandatory full-history archaeology" in evals
    assert "prior work artifacts, execution evidence, or durable knowledge" in evals
    assert "related-but-non-material relation" in evals


def test_archive_plan_uses_accepted_execution_dispositions_as_knowledge_gate(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Stable authority changed.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


@pytest.mark.parametrize(
    ("verdict", "action", "closure_return"),
    [
        ("repair", "update", "missing"),
        ("accept", "none", "missing"),
        ("accept", "reclassify", "completed"),
    ],
)
def test_archive_plan_allows_only_resolved_or_non_triggering_dispositions(
    tmp_path: Path, verdict: str, action: str, closure_return: str
) -> None:
    from plans import cmd_archive_plan

    plan_root = tmp_path / ".work-bundle/orchestration/plan/active"
    handoff_root = tmp_path / ".work-bundle/orchestration/handoff/executor/active"
    plan_root.mkdir(parents=True)
    handoff_root.mkdir(parents=True)
    (plan_root / "plan.md").write_text(
        "---\nid: plan-001\nstatus: Completed\n---\n\n"
        "## 2.1 Knowledge Base Update Carry Forward\n\n"
        "- **Disposition**: not-needed\n"
        f"- **Closure return**: {closure_return}\n",
        encoding="utf-8",
    )
    (handoff_root / "task.yaml").write_text(
        "id: handoff-001\ntype: executor-result\nstatus: active\n"
        "related: {plan: plan-001, task: task-001}\n"
        f"acceptance_review: {{verdict: {verdict}}}\n"
        "knowledge_disposition:\n"
        f"  action: {action}\n"
        "  reason: Task-local evidence.\n"
        f"  affected_authority: {'[]' if action == 'none' else '[AUTH-001]'}\n",
        encoding="utf-8",
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-001"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan.md").is_file()


def _write_archive_plan(
    tmp_path: Path,
    plan_id: str,
    *,
    disposition: str = "not-needed",
    closure_return: str = "missing",
) -> None:
    plan_root = tmp_path / ".work-bundle/orchestration/plan/active"
    plan_root.mkdir(parents=True, exist_ok=True)
    (plan_root / f"{plan_id}.md").write_text(
        f"---\nid: {plan_id}\nstatus: Completed\n---\n\n"
        "## 2.1 Knowledge Base Update Carry Forward\n\n"
        f"- **Disposition**: {disposition}\n"
        f"- **Closure return**: {closure_return}\n",
        encoding="utf-8",
    )
    task = plan_root / f"{plan_id}/phase-001/task.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        f"---\nid: task-001\nplan_id: {plan_id}\nphase_id: phase-001\nstatus: Completed\n---\n",
        encoding="utf-8",
    )


FOLLOW_ON_WRITE_SCOPE_FILE = "scripts/orchestration/plans.py"
ARCHIVE_NEUTRAL_COMMAND = "env true"


def _append_plan_knowledge(root: Path, *, closure_return: str = "missing") -> None:
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 2.1 Knowledge Base Update Carry Forward\n\n"
        + "- **Disposition**: not-needed\n"
        + f"- **Closure return**: {closure_return}\n",
        encoding="utf-8",
    )


def _append_plan_integration_command(root: Path, command: str) -> None:
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )


def _write_follow_on_plan_task(
    root: Path, *, task_id: str = "task-005", write_file: str = FOLLOW_ON_WRITE_SCOPE_FILE
) -> Path:
    source = root / ".work-bundle/orchestration/plan/active/plan-001/phase-001/task-004.md"
    task = source.with_name(f"{task_id}.md")
    task.write_text(
        source.read_text(encoding="utf-8")
        .replace("id: task-004\n", f"id: {task_id}\n")
        .replace(
            "write: [scripts/orchestration/execution_context.py]\n",
            f"write: [{write_file}]\n",
        ),
        encoding="utf-8",
    )
    return task


def _git_commit_file(root: Path, relative: str, content: str, message: str) -> str:
    from test_orchestration_execution_context import git

    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(root, "add", "--", relative)
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def _git_write_tree(root: Path) -> str:
    from test_orchestration_execution_context import git

    git(root, "add", "-A")
    return git(root, "write-tree")


def _record_repository_commit(evidence: str, actual_commit: str) -> str:
    marker = "    status: clean\n"
    assert marker in evidence
    return evidence.replace(
        marker,
        marker + "    metadata:\n" + f"      actual_commit: {actual_commit}\n",
        1,
    )


def _complete_evidence_blocks(root: Path, *, actual_commit: str | None = None) -> str:
    from test_orchestration_execution_context import evidence_blocks

    evidence = evidence_blocks(root)
    return evidence if actual_commit is None else _record_repository_commit(evidence, actual_commit)


def _write_follow_on_executor_handoff(
    root: Path,
    *,
    task_id: str,
    created_at: str,
    write_file: str = FOLLOW_ON_WRITE_SCOPE_FILE,
    extra_command: str | None = None,
    extra_result: str = "passed",
    actual_commit: str | None = None,
    reviewed_head: str | None = None,
) -> Path:
    from test_orchestration_execution_context import TASK_VALIDATION_COMMAND

    extra = "" if extra_command is None else f"    - {{command: {extra_command}, result: {extra_result}}}\n"
    review = "" if reviewed_head is None else f"acceptance_review: {{reviewed_head: {reviewed_head}}}\n"
    evidence = _complete_evidence_blocks(root, actual_commit=actual_commit)
    handoff = root / f".work-bundle/orchestration/handoff/executor/active/handoff-{task_id}.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        f"id: handoff-{task_id}\n"
        "type: executor-result\n"
        f"created_at: {created_at}\n"
        f"related: {{plan: plan-001, task: {task_id}}}\n"
        "result: {state: completed}\n"
        f"task_fit_check: {{task: {task_id}, result: clean}}\n"
        "changes:\n"
        "  files:\n"
        f"    - {{path: {write_file}, action: modified}}\n"
        "validation:\n"
        "  commands:\n"
        f"    - {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
        f"{extra}"
        f"{review}"
        f"{evidence}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )
    return handoff


def _write_earlier_integration_pass(root: Path, command: str, *, created_at: str) -> Path:
    from test_orchestration_execution_context import TASK_VALIDATION_COMMAND, git, write_executor_handoff

    try:
        head = git(root, "rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        git(root, "add", ".")
        git(root, "commit", "-qm", "integration acceptance baseline")
        head = git(root, "rev-parse", "HEAD")

    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    content = (
        handoff.read_text(encoding="utf-8")
        .replace("id: handoff-task-004\n", f"id: handoff-task-004\ncreated_at: {created_at}\n")
        .replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        )
    )
    handoff.write_text(_record_repository_commit(content, head), encoding="utf-8")
    return handoff


def _write_archive_handoff(
    tmp_path: Path,
    filename: str,
    related: str,
    *,
    verdict: str | None = "accept",
    action: str = "update",
    location: str = "active",
    result_state: str | None = None,
) -> None:
    handoff_root = tmp_path / ".work-bundle/orchestration/handoff/executor" / location
    handoff_root.mkdir(parents=True, exist_ok=True)
    affected = "[]" if action == "none" else "[AUTH-001]"
    review_line = "" if verdict is None else f"acceptance_review: {{verdict: {verdict}}}\n"
    result_line = "" if result_state is None else f"result: {{state: {result_state}}}\n"
    (handoff_root / filename).write_text(
        f"id: {filename.rsplit('.', 1)[0]}\ntype: executor-result\nstatus: {location}\n"
        f"related: {related}\n"
        f"{result_line}"
        f"{review_line}"
        "knowledge_disposition:\n"
        f"  action: {action}\n"
        "  reason: Task-local evidence.\n"
        f"  affected_authority: {affected}\n",
        encoding="utf-8",
    )


def test_archive_plan_ignores_foreign_plan_handoff_with_colliding_task_id(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-A")
    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(tmp_path, "plan-a.yaml", "{plan: plan-A, task: task-001}")

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()
    assert (tmp_path / ".work-bundle/orchestration/plan/active/plan-A.md").is_file()


def test_archive_plan_skips_unrelated_unparseable_executor_yaml(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-A")
    _write_archive_plan(tmp_path, "plan-B")
    handoff_root = tmp_path / ".work-bundle/orchestration/handoff/executor/active"
    handoff_root.mkdir(parents=True, exist_ok=True)
    (handoff_root / "foreign-block.yaml").write_text(
        "id: foreign\n"
        "type: executor-result\n"
        "related:\n"
        "  plan: plan-A\n"
        "  task: task-001\n"
        "summary: >\n"
        "  unsupported folded scalar\n",
        encoding="utf-8",
    )
    (handoff_root / "foreign-inline.yaml").write_text(
        "id: foreign-inline\n"
        "type: executor-result\n"
        "related: {plan: plan-A, task: task-001}\n"
        "summary: >\n"
        "  unsupported folded scalar\n",
        encoding="utf-8",
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()
    assert (tmp_path / ".work-bundle/orchestration/plan/active/plan-A.md").is_file()


def test_archive_plan_ignores_task_only_handoff_with_ambiguous_task_id(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(tmp_path, "task-only.yaml", "{task: task-001}")

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_archive_plan_ignores_archived_foreign_handoff_with_colliding_task_id(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-A")
    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(
        tmp_path, "historical.yaml", "{plan: plan-A, task: task-001}", location="archived"
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_archive_plan_same_plan_accepted_update_still_blocks_unresolved_closure(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Task-local evidence.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_archive_plan_same_plan_resolved_closure_allows_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-B", closure_return="completed")
    _write_archive_handoff(tmp_path, "plan-b.yaml", "{plan: plan-B, task: task-001}")

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


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
        "semantically distinct from generic `source_ids`",
        "none-relevant",
        "verified specification's accepted `source_knowledge`",
        "AUTH-NNN: <carried constraint>",
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
        "must not name knowledge paths or any `ks-*` skill",
        "exact paths already present in the compiled task scope",
        "allocated `AUTH-NNN` aliases",
        "related.plan",
        "must equal the assigned task's `plan_id` and `id`",
        "fails closed before `Completed` and before `build-review-package`",
        "A review-required task cannot become `Completed` until the verdict is `accept`",
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
        "AUTH-NNN: <carried constraint>",
        "same five-field Truth Basis",
        "earliest ordinary task",
        "knowledge disposition",
        "review owns approved persistence",
        "minimum orchestration overhead",
        "accepted task dispositions",
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
        "`Completed` does not require `verdict: accept` unless review was required",
        "optional task review when acceptance_review.required: true",
        "accepted Truth Basis",
        "test oracle",
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
        "accepted `update`, `supersede`, or `reclassify`",
        "rejected dispositions",
        "archive",
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
        "ordinary characterization task",
        "conflict_status escalate",
        "asks to invoke a ks-* writer",
        "implementation and tests do not match",
        "device-local checkout observations disagree",
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


def test_no_review_completed_handoff_does_not_require_accept_or_reviewer() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    for token in [
        "`Completed` does not require `verdict: accept` unless review was required",
        "assign `dev-code-review` only when `acceptance_review.required: true`",
        "Skip this hop when review is not required",
    ]:
        assert token in execute
    assert "verdict: accept" not in str(_completed_executor_result())

    validated = validate_executor_result_for_task(_completed_executor_result(), _task_brief())
    assert validated["result_state"] == "completed"
    assert validated["knowledge_disposition"]["action"] == "none"


def test_execute_plan_requires_bound_observation_and_isolate_or_serialize() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    plan = read("skills/orch-create-implementation-plan/SKILL.md")
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    for token in [
        "harness-owned task execution binding",
        "capture the pre-task baseline once",
        "cannot supply or replace that baseline",
        "bound execution repository",
        "isolate via prepare_worktree or serialize",
        "Git-state-neutral",
        "validate-executor-result",
    ]:
        assert token in execute
    assert "mutating siblings on the same execution path isolate via prepare_worktree or serialize" in plan
    assert "cannot supply or replace that baseline" in contract
    assert "corroboration" in contract
    assert "not independent proof" in contract or "not authority" in contract


def test_optional_review_package_does_not_absorb_sibling_task_files(tmp_path: Path) -> None:
    from test_orchestration_execution_context import (
        WRITE_SCOPE_FILE,
        args as review_args,
        git,
        workspace,
        write_executor_handoff,
    )

    root, _, task_b = workspace(tmp_path)
    scoped = root / WRITE_SCOPE_FILE
    scoped.parent.mkdir(parents=True, exist_ok=True)
    scoped.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    task_a_file = root / "src/task_a.py"
    task_a_file.parent.mkdir(parents=True, exist_ok=True)
    task_a_file.write_text("TASK_A_OLD = 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    scoped.write_text("def compile_task():\n    return 'task-b'\n", encoding="utf-8")
    task_a_file.write_text("TASK_A_NEW = 2\n", encoding="utf-8")
    from test_orchestration_execution_context import _bind_passing_observation

    handoff = _bind_passing_observation(root, task_b)

    package = build_review_package(
        review_args(root, task_b, handoff=str(handoff), base=base, head="worktree")
    ).read_text(encoding="utf-8")
    diff = package.split("## Diff", 1)[1].split("## Out-of-scope changes", 1)[0]
    diagnostics = package.split("## Out-of-scope changes", 1)[1].split("## ", 1)[0]

    assert "## Out-of-scope changes" in package
    assert "return 'task-b'" in diff
    assert "TASK_A_NEW" not in diff
    assert "src/task_a.py" not in diff
    assert "src/task_a.py" in diagnostics
    assert WRITE_SCOPE_FILE in package.split("## Changed files", 1)[1].split("## ", 1)[0]


def test_failing_declared_plan_acceptance_blocks_archive_without_second_reviewer(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    review = read("skills/orch-review-plan/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "declared plan-level/integration acceptance observed on the final integrated workspace",
        "do not start another implementation-review agent to produce plan-level acceptance",
        "Archive remains blocked while any required knowledge, validation, review",
    ]:
        assert token in review
    for token in [
        "declared plan-level/integration acceptance is recorded",
        "It does not redo task code review, reread implementation for code quality, or start another implementation-review agent",
        "Missing review verdicts are not a blocker when no task set `acceptance_review.required: true`",
    ]:
        assert token in workflow

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    _write_archive_plan(tmp_path, "plan-B")
    plan = tmp_path / ".work-bundle/orchestration/plan/active/plan-B.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    _write_archive_handoff(
        tmp_path,
        "plan-b.yaml",
        "{plan: plan-B, task: task-001}",
        verdict=None,
        action="none",
        result_state="completed",
    )
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/plan-b.yaml"
    handoff.write_text(
        handoff.read_text(encoding="utf-8")
        + "validation:\n"
        + "  commands:\n"
        + f"    - {{command: {command}, result: failed}}\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/active/plan-B.md").is_file()


def test_passing_declared_plan_acceptance_allows_archive_without_second_reviewer(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import (
        TASK_VALIDATION_COMMAND,
        git,
        workspace,
        write_executor_handoff,
    )

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-qm", "final workspace")
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    handoff.write_text(
        handoff.read_text(encoding="utf-8").replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        ),
        encoding="utf-8",
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_unvalidated_handoff_cannot_satisfy_declared_plan_acceptance(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    _write_archive_plan(tmp_path, "plan-B")
    plan = tmp_path / ".work-bundle/orchestration/plan/active/plan-B.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    _write_archive_handoff(
        tmp_path,
        "plan-b.yaml",
        "{plan: plan-B, task: task-001}",
        verdict=None,
        action="none",
        result_state="completed",
    )
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/plan-b.yaml"
    handoff.write_text(
        handoff.read_text(encoding="utf-8")
        + "validation:\n"
        + "  commands:\n"
        + f"    - {{command: {command}, result: passed}}\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))


def _record_tree_fresh_integration_pass(root: Path, command: str) -> str:
    from test_orchestration_execution_context import TASK_VALIDATION_COMMAND, git, write_executor_handoff

    git(root, "add", ".")
    git(root, "commit", "-qm", "tree-fresh acceptance baseline")
    head = git(root, "rev-parse", "HEAD")
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    content = handoff.read_text(encoding="utf-8").replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        )
    handoff.write_text(_record_repository_commit(content, head), encoding="utf-8")
    return head


def test_tree_fresh_executor_pass_without_harness_observation_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    command = "env false"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _record_tree_fresh_integration_pass(root, command)

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_task_worktree_command_pass_cannot_archive_different_final_workspace(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import git, workspace

    command = "test -f worktree-only-marker"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    git(root, "add", ".")
    git(root, "commit", "-qm", "final workspace")
    worktree = tmp_path / "isolated-task-worktree"
    git(root, "worktree", "add", str(worktree), "HEAD")
    (worktree / "worktree-only-marker").write_text("isolated\n", encoding="utf-8")
    _write_earlier_integration_pass(root, command, created_at="2026-08-17")

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()
    assert not (root / "worktree-only-marker").exists()


def test_passing_mutating_integration_command_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    command = "touch mutated-by-acceptance.txt"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _record_tree_fresh_integration_pass(root, command)

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_contradictory_validated_plan_acceptance_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import (
        TASK_VALIDATION_COMMAND,
        workspace,
        write_executor_handoff,
    )

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    passed = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    passed.write_text(
        passed.read_text(encoding="utf-8").replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        ),
        encoding="utf-8",
    )
    failed = passed.parent / "handoff-task-004-failed.yaml"
    failed.write_text(
        passed.read_text(encoding="utf-8")
        .replace("id: handoff-task-004\n", "id: handoff-task-004-failed\n")
        .replace(f"- {{command: {command}, result: passed}}\n", f"- {{command: {command}, result: failed}}\n"),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))


def test_stale_plan_acceptance_after_later_material_task_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_earlier_integration_pass(root, command, created_at="2026-08-15")
    _write_follow_on_plan_task(root)
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'later'\n",
        "task-005",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-005",
        created_at="2026-08-16",
        actual_commit=later,
    )

    with pytest.raises(SystemExit, match="acceptance-blocked:.*is stale"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_fresh_plan_acceptance_rerun_after_later_task_allows_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'old'\n", "task-004")
    _write_earlier_integration_pass(root, command, created_at="2026-08-15")
    _write_follow_on_plan_task(root)
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'fresh'\n",
        "task-005",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-005",
        created_at="2026-08-16",
        extra_command=command,
        actual_commit=later,
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_archive_moves_plan_directory_named_for_root_artifact(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    active = root / ".work-bundle/orchestration/plan/active"
    (active / "compiler-plan.md").rename(active / "plan-001-feature.md")
    (active / "plan-001").rename(active / "plan-001-feature")

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    archived = root / ".work-bundle/orchestration/plan/archived"
    assert (archived / "plan-001-feature.md").is_file()
    assert (archived / "plan-001-feature").is_dir()
    assert not (active / "plan-001-feature").exists()


def test_archive_reconciles_archived_root_with_active_plan_directory(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    plan_root = root / ".work-bundle/orchestration/plan"
    active = plan_root / "active"
    archived = plan_root / "archived"
    archived.mkdir(exist_ok=True)
    (active / "compiler-plan.md").rename(archived / "plan-001-feature.md")
    (active / "plan-001").rename(active / "plan-001-feature")

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (archived / "plan-001-feature.md").is_file()
    assert (archived / "plan-001-feature").is_dir()
    assert not (active / "plan-001-feature").exists()


def test_same_day_out_of_id_order_stale_plan_acceptance_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'first'\n", "task-010")
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'later'\n",
        "task-002",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        actual_commit=later,
    )

    with pytest.raises(SystemExit, match="acceptance-blocked:.*is stale"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_same_day_out_of_id_order_fresh_rerun_allows_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'first'\n", "task-010")
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'later'\n",
        "task-002",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        extra_command=command,
        actual_commit=later,
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_historical_failed_plan_acceptance_does_not_poison_fresh_head_pass(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'broken'\n", "task-010-fail")
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        extra_result="failed",
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'repaired'\n",
        "task-002-pass",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        extra_command=command,
        actual_commit=later,
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_same_tree_contradictory_plan_acceptance_still_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    head = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'now'\n", "terminal")
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        extra_result="failed",
        actual_commit=head,
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-004",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=head,
    )

    with pytest.raises(SystemExit, match="acceptance-blocked:.*contradictory"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))


def test_precommit_tree_pass_survives_same_tree_finalization_commit(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, git, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'base'\n", "task-010")
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    (root / FOLLOW_ON_WRITE_SCOPE_FILE).write_text("def archive_plan():\n    return 'final'\n", encoding="utf-8")
    tree = _git_write_tree(root)
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        extra_command=command,
        reviewed_head=tree,
    )
    git(root, "commit", "-qm", "finalize")

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_archive_plan_no_review_completed_update_blocks_until_closure_return(
    tmp_path: Path,
) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Task-local evidence.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_archive_plan_ignores_unvalidated_update_handoff(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(
        tmp_path,
        "plan-b.yaml",
        "{plan: plan-B, task: task-001}",
        verdict=None,
        result_state="completed",
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_archive_plan_review_required_cannot_downgrade_via_omitted_required(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "acceptance_review:\n  required: false\n",
            "acceptance_review:\n  required: true\n",
        ),
        encoding="utf-8",
    )
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Task-local evidence.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_missing_or_wrong_plan_identity_cannot_complete_without_review_package() -> None:
    missing = _completed_executor_result(plan=None)
    with pytest.raises(SystemExit, match="Handoff plan identity missing"):
        validate_executor_result_for_task(missing, _task_brief())

    mismatched = _completed_executor_result(plan="plan-A")
    with pytest.raises(SystemExit, match="Handoff plan mismatch: expected plan-001, got plan-A"):
        validate_executor_result_for_task(mismatched, _task_brief())


def test_review_required_task_fails_closed_until_independent_accept() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    review = read("skills/orch-review-plan/SKILL.md")
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    for token in [
        "Do not perform acceptance judgment or mark a review-required task complete",
        "`Completed` does not require `verdict: accept` unless review was required",
    ]:
        assert token in execute
    for token in [
        "missing `acceptance_review.verdict` blocks only a task that explicitly required independent review",
        "`acceptance_review.verdict: accept` only for those explicitly required reviews",
    ]:
        assert token in review
    assert "A review-required task cannot become `Completed` until the verdict is `accept`" in contract

    pending = {
        "related": {"plan": "plan-001", "task": "task-001"},
        "result": {"state": "completed"},
        "acceptance_review": {"required": True, "verdict": "pending"},
        "knowledge_disposition": {
            "action": "update",
            "reason": "Task-local evidence.",
            "affected_authority": ["AUTH-001"],
        },
    }
    closure = evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=[pending],
        closure_return="missing",
    )
    assert (closure["disposition"], closure["archive_blocked"]) == ("not-needed", False)

    review_required_handoff = _completed_executor_result(
        acceptance_review={"required": True, "verdict": "pending"}
    )
    with pytest.raises(SystemExit, match="accept|review"):
        validate_executor_result_for_task(
            review_required_handoff, {**_task_brief(), "review_required": True}
        )

    accepted = _completed_executor_result(
        acceptance_review={"required": True, "verdict": "accept"}
    )
    validated = validate_executor_result_for_task(accepted, {**_task_brief(), "review_required": True})
    assert validated["result_state"] == "completed"


def test_overlapping_writes_are_not_parallelizable() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    create = read("skills/orch-create-implementation-plan/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    plan = read("references/assets/orchestration/contract/plan-v1.md")
    assert "Partition only independent tasks with disjoint write scopes" in execute
    assert "disjoint write scopes" in create
    assert "write scopes are disjoint" in workflow
    assert "disjoint write scopes" in workflow
    assert "assign parallel tasks only when dependencies are satisfied and write scopes are disjoint" in plan
    assert "unsafe parallelization is explicitly blocked by dependency or scope evidence" in plan


def test_plan_contract_has_no_placeholder_markdown_links() -> None:
    plan = read("references/assets/orchestration/contract/plan-v1.md")

    assert "](.work-bundle/orchestration/spec/active/...)" not in plan
    assert "`.work-bundle/orchestration/spec/active/...`" in plan


def test_dev_create_task_plan_tests_omit_heavy_orchestration_requirements() -> None:
    skill = read("skills/dev-create-task-plan/SKILL.md")
    assert "Do not import executor-result, `Completed`, review package, archive helper, or heavy Knowledge Base Update closure" in skill
    tests = read("tests/test_dev_skill_contracts.py")
    assert "dev-create-task-plan" in tests
    assert ".work-bundle/runtime/dev-plans/" in tests
