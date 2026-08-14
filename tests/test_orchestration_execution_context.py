from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from execution_context import build_review_package, build_task_brief  # noqa: E402


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "workspace"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    metadata = root / ".work-bundle" / "project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "metadata_version: 3\n"
        f"workspace_root: {root}\n"
        "workspace_mode: single-repository\n",
        encoding="utf-8",
    )

    spec = root / ".work-bundle/orchestration/spec/active/spec-001.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "---\n"
        "id: spec-001\n"
        "---\n\n"
        "# Compiler contract\n\n"
        "- **REQ-003**: Retry exactly three times before returning failure.\n"
        "- **CON-002**: Never write outside the assigned files.\n"
        "- **API-002**: `compile_task(task: Path) -> dict[str, object]`\n"
        "- **TEST-004**: Focused pytest exits with status 0.\n",
        encoding="utf-8",
    )

    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "---\n"
        "id: plan-001\n"
        "source_spec: [.work-bundle/orchestration/spec/active/spec-001.md]\n"
        "allocated_rules: [{id: parent-rule, requirement: must-not-be-inherited}]\n"
        "---\n\n# Plan\n",
        encoding="utf-8",
    )

    task = root / ".work-bundle/orchestration/plan/active/plan-001/phase-001/task-004.md"
    task.parent.mkdir(parents=True)
    task.write_text(
        "---\n"
        "id: task-004\n"
        "plan_id: plan-001\n"
        "phase_id: phase-001\n"
        "goal: Compile a bounded executor packet.\n"
        "source_ids: [REQ-003, CON-002, API-002, TEST-004]\n"
        "truth_basis:\n"
        "  purpose: Compile a bounded executor packet.\n"
        "  as_is_evidence: [scripts/orchestration/execution_context.py]\n"
        "  decision_authority: [REQ-003, CON-002]\n"
        "  expected_delta: [API-002]\n"
        "  conflict_status: clear\n"
        "files:\n"
        "  read: [scripts/orchestration/core.py]\n"
        "  write: [scripts/orchestration/execution_context.py]\n"
        "  forbidden: [.work-bundle/knowledge/**, credentials/**]\n"
        "interfaces:\n"
        "  consumes: [API-002]\n"
        "  produces: [API-002]\n"
        "methodology:\n"
        "  primary: tdd\n"
        "  skills: [dev-test-driven-development]\n"
        "allocated_rules:\n"
        "  - {id: scoped-rule, requirement: Keep the executor packet bounded.}\n"
        "allocated_skills:\n"
        "  - {name: dev-test-driven-development}\n"
        "executor_profile:\n"
        "  capability: mechanical\n"
        "  context_mode: compiled-brief\n"
        "validation:\n"
        "  - {command: uv run --with pytest pytest -q tests/test_one.py, proves: TEST-004, expected: exit 0}\n"
        "---\n\n# Task\n",
        encoding="utf-8",
    )
    return root, spec, task


def args(root: Path, task: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "project_root": str(root),
        "workspace_root": None,
        "task": str(task),
        "handoff": None,
        "base": None,
        "head": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_task_brief_resolves_source_ids_and_keeps_allocations_task_local(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)

    target = build_task_brief(args(root, task))
    packet = target.read_text(encoding="utf-8")

    assert target == root / ".work-bundle/runtime/execution/plan-001/task-004/task-brief.yaml"
    assert "Retry exactly three times before returning failure." in packet
    assert "Never write outside the assigned files." in packet
    assert "`compile_task(task: Path) -> dict[str, object]`" in packet
    assert "Focused pytest exits with status 0." in packet
    assert "scoped-rule" in packet
    assert "dev-test-driven-development" in packet
    assert "parent-rule" not in packet
    assert ".work-bundle/knowledge/**" in packet
    assert ".work-bundle/knowledge/notes" not in packet
    assert "handoff_contract: executor-result-v1" in packet
    assert "review_required: true" in packet
    assert "truth_basis:" in packet
    assert 'purpose: "Compile a bounded executor packet."' in packet
    assert "REQ-003: Retry exactly three times before returning failure." in packet
    assert "conflict_status: clear" in packet


def test_build_task_brief_fails_closed_when_truth_basis_is_missing(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    content = task.read_text(encoding="utf-8")
    content = re.sub(r"truth_basis:\n(?:  .*\n){5}", "", content)
    task.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit, match="Task Truth Basis is required"):
        build_task_brief(args(root, task))


def test_build_task_brief_routes_truth_basis_conflict_to_typed_blocker(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace("conflict_status: clear", "conflict_status: escalate"),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="decision-blocked"):
        build_task_brief(args(root, task))


@pytest.mark.parametrize("authority", ["invented design decision", "REQ-777"])
def test_build_task_brief_rejects_unallocated_decision_authority(
    tmp_path: Path, authority: str
) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "decision_authority: [REQ-003, CON-002]",
            f"decision_authority: [REQ-003, {authority}]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="decision_authority.*allocated source_ids"):
        build_task_brief(args(root, task))


def test_build_task_brief_preserves_review_not_required_from_task_contract(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "validation:\n",
            "acceptance_review:\n  required: false\nvalidation:\n",
        ),
        encoding="utf-8",
    )

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert "review_required: false" in packet
    assert "review_required: true" not in packet


def test_build_task_brief_preserves_explicit_review_requirement(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "validation:\n",
            "acceptance_review:\n  required: true\nvalidation:\n",
        ),
        encoding="utf-8",
    )

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert "review_required: true" in packet


def test_build_task_brief_fails_closed_for_missing_source_id_without_reading_knowledge(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(task.read_text(encoding="utf-8").replace("TEST-004]", "TEST-004, REQ-999]"), encoding="utf-8")
    knowledge = root / ".work-bundle/knowledge/notes/hidden.md"
    knowledge.parent.mkdir(parents=True)
    knowledge.write_text("- **REQ-999**: This must never be used.\n", encoding="utf-8")

    with pytest.raises(SystemExit, match=r"REQ-999.*spec-001\.md"):
        build_task_brief(args(root, task))

    assert not (root / ".work-bundle/runtime/execution/plan-001/task-004/task-brief.yaml").exists()


def test_build_task_brief_reads_current_task_contract_sections(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    content = task.read_text(encoding="utf-8")
    content = content.replace("goal: Compile a bounded executor packet.\n", "")
    content = content.replace("  skills: [dev-test-driven-development]", "  required_skills: [dev-test-driven-development]")
    content = re.sub(r"interfaces:\n(?:  .*\n){2}", "", content)
    content = re.sub(r"validation:\n  - .*\n", "", content)
    content = content.replace(
        "# Task\n",
        "# Task\n\n"
        "## Goal\n\nCompile from the current task contract.\n\n"
        "## Files and interfaces\n\n"
        "| Path or interface | Read/write | Required usage |\n"
        "| --- | --- | --- |\n"
        "| API-002 | consumes | Exact compiler signature |\n\n"
        "## Validation\n\n"
        "| Command or inspection | Proves | Expected |\n"
        "| --- | --- | --- |\n"
        "| `uv run --with pytest pytest -q tests/test_one.py` | TEST-004 | exit 0 |\n",
    )
    task.write_text(content, encoding="utf-8")

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert "Compile from the current task contract." in packet
    assert "dev-test-driven-development" in packet
    assert "API-002: `compile_task(task: Path) -> dict[str, object]`" in packet
    assert "Focused pytest exits with status 0." in packet


def test_build_task_brief_rejects_credential_values_before_writing_packet(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    spec.write_text(
        spec.read_text(encoding="utf-8")
        + "- **REQ-005**: credential_value: SYNTHETIC-CANARY-DO-NOT-LEAK\n",
        encoding="utf-8",
    )
    task.write_text(task.read_text(encoding="utf-8").replace("TEST-004]", "TEST-004, REQ-005]"), encoding="utf-8")

    with pytest.raises(SystemExit, match="credential-like value") as error:
        build_task_brief(args(root, task))

    assert "SYNTHETIC-CANARY" not in str(error.value)
    assert not (root / ".work-bundle/runtime/execution/plan-001/task-004/task-brief.yaml").exists()


def test_build_task_brief_rejects_protected_credential_path_scope(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "read: [scripts/orchestration/core.py]", "read: [credentials/credentials.yaml]"
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="forbidden protected path"):
        build_task_brief(args(root, task))

    assert not (root / ".work-bundle/runtime/execution/plan-001/task-004/task-brief.yaml").exists()


def test_build_review_package_contains_only_bounded_task_diff_and_evidence(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    source = root / "src/compiler.py"
    source.parent.mkdir()
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    source.write_text(
        "def compile_task():\n    password = 'DIFF-CANARY-DO-NOT-LEAK'\n    return 'new'\n",
        encoding="utf-8",
    )
    git(root, "add", "src/compiler.py")
    git(root, "commit", "-qm", "head")
    head = git(root, "rev-parse", "HEAD")

    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related:\n"
        "  task: task-004\n"
        "changes:\n"
        "  files:\n"
        "    - {path: src/compiler.py, action: modified, symbols: [compile_task]}\n"
        "validation:\n"
        "  commands:\n"
        "    - {command: uv run --with pytest pytest -q tests/test_one.py, result: passed}\n"
        "unresolved:\n"
        "  - Confirm retry timing with the caller.\n"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n"
        "session_history: SHOULD-NOT-APPEAR\n",
        encoding="utf-8",
    )

    target = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head=head)
    )
    package = target.read_text(encoding="utf-8")

    assert target == root / ".work-bundle/runtime/execution/plan-001/task-004/review-package.md"
    assert f"Base: {base}" in package
    assert f"Head: {head}" in package
    assert "src/compiler.py" in package
    assert "compile_task" in package
    assert "return 'new'" in package
    assert "DIFF-CANARY-DO-NOT-LEAK" not in package
    assert "password: <redacted>" in package
    assert "result: passed" in package
    assert "Confirm retry timing with the caller." in package
    assert "scoped-rule" in package
    assert "dev-test-driven-development" in package
    assert "## Review rubric" in package
    assert "## Accepted Truth Basis" in package
    assert "## Knowledge disposition" in package
    assert "No stable authority changed." in package
    assert "SHOULD-NOT-APPEAR" not in package
    assert ".work-bundle/knowledge/notes" not in package


def test_build_review_package_includes_tracked_and_untracked_worktree_changes(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    source = root / "src/compiler.py"
    source.parent.mkdir()
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    source.write_text("def compile_task():\n    return 'working'\n", encoding="utf-8")
    new_test = root / "tests/test_compiler.py"
    new_test.parent.mkdir()
    new_test.write_text("def test_compile_task():\n    assert True\n", encoding="utf-8")

    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {task: task-004}\n"
        "validation:\n"
        "  commands:\n"
        "    - {command: uv run pytest -q, result: passed}\n"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )

    target = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head="worktree")
    )
    package = target.read_text(encoding="utf-8")

    assert re.search(r"Head: worktree:[0-9a-f]{64}", package)
    assert "M\\tsrc/compiler.py" in package or "M\tsrc/compiler.py" in package
    assert "A\\ttests/test_compiler.py" in package or "A\ttests/test_compiler.py" in package
    assert "return 'working'" in package
    assert "def test_compile_task" in package


def test_build_review_package_never_reads_tracked_protected_diff_content(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    protected = root / "credentials/credentials.yaml"
    protected.parent.mkdir()
    protected.write_text("credential_id: safe-reference\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    protected.write_text("opaque_value: TRACKED-PROTECTED-CANARY\n", encoding="utf-8")
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {task: task-004}\n"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )

    package = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head="worktree")
    ).read_text(encoding="utf-8")

    assert "credentials/credentials.yaml" in package
    assert "content withheld: protected path" in package
    assert "TRACKED-PROTECTED-CANARY" not in package


def test_build_review_package_rejects_invalid_knowledge_disposition(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    source = root / "src/compiler.py"
    source.parent.mkdir()
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {task: task-004}\n"
        "knowledge_disposition:\n"
        "  action: write-now\n"
        "  reason: Executor should persist knowledge.\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="knowledge disposition action"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))


@pytest.mark.parametrize(
    "disposition",
    [
        "  action: update\n  reason: Stable authority changed.\n  affected_authority: []\n",
        "  action: update\n  reason: Run ks-write-knowledge now.\n  affected_authority: [REQ-003]\n",
        "  action: update\n  reason: Stable authority changed.\n  affected_authority: [.work-bundle/knowledge/notes/new.md]\n",
    ],
)
def test_build_review_package_rejects_unbounded_knowledge_disposition(
    tmp_path: Path, disposition: str
) -> None:
    root, _, task = workspace(tmp_path)
    source = root / "src/compiler.py"
    source.parent.mkdir()
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {task: task-004}\n"
        "knowledge_disposition:\n"
        + disposition,
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="knowledge disposition"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))
