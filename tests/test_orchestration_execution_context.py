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

import execution_context  # noqa: E402
from execution_context import build_review_package, build_task_brief  # noqa: E402


ACCEPTED_AUTHORITY_PATH = ".work-bundle/knowledge/notes/accepted-authority.md"
ACCEPTED_AUTHORITY = "AUTH-001"
ACCEPTED_CONSTRAINT = "Executors must not retrieve durable knowledge to reconstruct authority."
DECOY_KNOWLEDGE = "This decoy note must never appear in compiled authority."


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
        "status: verified\n"
        "source_knowledge:\n"
        f"  - path: {ACCEPTED_AUTHORITY_PATH}\n"
        f"    constraint: {ACCEPTED_CONSTRAINT}\n"
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
        f"  decision_authority: [{ACCEPTED_AUTHORITY}]\n"
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


def carry_accepted_constraint(spec: Path) -> None:
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            f"  - {ACCEPTED_AUTHORITY_PATH}\n",
            f"  - path: {ACCEPTED_AUTHORITY_PATH}\n    constraint: {ACCEPTED_CONSTRAINT}\n",
        ),
        encoding="utf-8",
    )


def write_decoy_knowledge(root: Path) -> Path:
    knowledge = root / ACCEPTED_AUTHORITY_PATH
    knowledge.parent.mkdir(parents=True, exist_ok=True)
    knowledge.write_text(DECOY_KNOWLEDGE + "\n", encoding="utf-8")
    return knowledge


def committed_review_base(root: Path) -> str:
    source = root / "src/compiler.py"
    source.parent.mkdir()
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return git(root, "rev-parse", "HEAD")


def write_executor_handoff(root: Path, disposition: str) -> Path:
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {plan: plan-001, task: task-004}\n"
        "knowledge_disposition:\n"
        + disposition,
        encoding="utf-8",
    )
    return handoff


def retarget_plan(root: Path, task: Path, plan_id: str) -> None:
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace("id: plan-001\n", f"id: {plan_id}\n"),
        encoding="utf-8",
    )
    task.write_text(
        task.read_text(encoding="utf-8").replace("plan_id: plan-001\n", f"plan_id: {plan_id}\n"),
        encoding="utf-8",
    )


def write_related_handoff(root: Path, related_block: str) -> Path:
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        f"{related_block}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )
    return handoff


COMPILED_AUTHORITY = f"{ACCEPTED_AUTHORITY}: {ACCEPTED_CONSTRAINT}"


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
    assert ACCEPTED_AUTHORITY in packet
    assert COMPILED_AUTHORITY in packet
    assert ACCEPTED_CONSTRAINT in packet
    assert ACCEPTED_AUTHORITY_PATH not in packet.split("truth_basis:", 1)[1].split("expected_delta:", 1)[0]
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


def test_build_task_brief_accepts_explicit_none_relevant_decision_authority(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"decision_authority: [{ACCEPTED_AUTHORITY}]",
            "decision_authority: [none-relevant]",
        ),
        encoding="utf-8",
    )

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert "none-relevant" in packet


def test_build_task_brief_rejects_none_relevant_from_unverified_specification(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8").replace("status: verified", "status: draft"), encoding="utf-8")
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"decision_authority: [{ACCEPTED_AUTHORITY}]", "decision_authority: [none-relevant]"
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="requires a verified specification"):
        build_task_brief(args(root, task))


@pytest.mark.parametrize(
    "authority",
    [
        "invented design decision",
        "REQ-003",
        ".work-bundle/knowledge/notes/candidate.md",
        ".work-bundle/knowledge/notes/background.md",
        ".work-bundle/knowledge/notes/blocked.md",
        ".work-bundle/knowledge/notes/superseded.md",
    ],
)
def test_build_task_brief_rejects_decision_authority_not_carried_by_verified_spec(
    tmp_path: Path, authority: str
) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"decision_authority: [{ACCEPTED_AUTHORITY}]",
            f"decision_authority: [{authority}]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="decision_authority.*verified specification authority"):
        build_task_brief(args(root, task))


def test_build_task_brief_does_not_allocate_aliases_for_non_authority_source_context(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "# Compiler contract",
            "# Compiler contract\n\n## Source Context\n\n- **Candidate**: `.work-bundle/knowledge/notes/candidate.md` remains non-authority.",
        ),
        encoding="utf-8",
    )
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            ACCEPTED_AUTHORITY, "AUTH-002"
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="decision_authority.*verified specification authority"):
        build_task_brief(args(root, task))


@pytest.mark.parametrize(
    ("upstream", "review_verdict", "action", "closure_return", "expected"),
    [
        ("not-needed", "accept", "update", "missing", ("required", True)),
        ("not-needed", "accept", "supersede", "completed", ("completed", False)),
        ("not-needed", "accept", "reclassify", "not-needed", ("not-needed", False)),
        ("not-needed", "repair", "update", "missing", ("not-needed", False)),
        ("not-needed", "accept", "none", "missing", ("not-needed", False)),
        ("required", "accept", "none", "blocked", ("blocked", True)),
    ],
)
def test_final_knowledge_closure_is_driven_by_accepted_task_dispositions(
    upstream: str,
    review_verdict: str,
    action: str,
    closure_return: str,
    expected: tuple[str, bool],
) -> None:
    handoffs = [
        {
            "related": {"task": "task-004"},
            "acceptance_review": {"verdict": review_verdict},
            "knowledge_disposition": {
                "action": action,
                "reason": "Task-local evidence.",
                "affected_authority": [] if action == "none" else [ACCEPTED_AUTHORITY],
            },
        }
    ]

    result = execution_context.evaluate_knowledge_closure_state(
        upstream_disposition=upstream,
        accepted_task_handoffs=handoffs,
        closure_return=closure_return,
    )

    assert (result["disposition"], result["archive_blocked"]) == expected


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
        "  plan: plan-001\n"
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
        "related: {plan: plan-001, task: task-004}\n"
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
        "related: {plan: plan-001, task: task-004}\n"
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
        "related: {plan: plan-001, task: task-004}\n"
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
        "  action: update\n  reason: Run ks-track-open-questions now.\n  affected_authority: [REQ-003]\n",
        "  action: update\n  reason: Stable authority changed.\n  affected_authority: [.work-bundle/knowledge/notes/new.md]\n",
        "  action: update\n  reason: Stable authority changed.\n  affected_authority: [../../outside/authority.md]\n",
        "  action: update\n  reason: Stable authority changed.\n  affected_authority: [credentials/credentials.yaml]\n",
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
        "related: {plan: plan-001, task: task-004}\n"
        "knowledge_disposition:\n"
        + disposition,
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="knowledge disposition"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))


def test_build_task_brief_compiles_auth_alias_with_carried_constraint(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    carry_accepted_constraint(spec)
    write_decoy_knowledge(root)

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert COMPILED_AUTHORITY in packet
    assert ACCEPTED_CONSTRAINT in packet
    assert "decision_authority:" in packet
    assert ACCEPTED_AUTHORITY_PATH not in packet.split("truth_basis:", 1)[1].split("expected_delta:", 1)[0]
    assert DECOY_KNOWLEDGE not in packet


def test_build_review_package_receives_same_resolved_auth_semantics(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    carry_accepted_constraint(spec)
    write_decoy_knowledge(root)
    base = committed_review_base(root)
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )

    brief = build_task_brief(args(root, task)).read_text(encoding="utf-8")
    package = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head=base)
    ).read_text(encoding="utf-8")

    assert COMPILED_AUTHORITY in brief
    assert COMPILED_AUTHORITY in package
    assert ACCEPTED_CONSTRAINT in package
    assert "## Accepted Truth Basis" in package
    assert ACCEPTED_AUTHORITY_PATH not in package.split("## Accepted Truth Basis", 1)[1].split("## Allowed scope", 1)[0]
    assert DECOY_KNOWLEDGE not in package


def test_build_task_brief_compiles_auth_without_reading_durable_knowledge(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    carry_accepted_constraint(spec)
    knowledge = write_decoy_knowledge(root)

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert COMPILED_AUTHORITY in packet
    assert knowledge.read_text(encoding="utf-8") == DECOY_KNOWLEDGE + "\n"
    assert DECOY_KNOWLEDGE not in packet
    assert ACCEPTED_AUTHORITY_PATH not in packet.split("forbidden:", 1)[0]


def test_build_task_brief_fails_closed_when_auth_lacks_carried_constraint(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            f"  - path: {ACCEPTED_AUTHORITY_PATH}\n    constraint: {ACCEPTED_CONSTRAINT}\n",
            f"  - {ACCEPTED_AUTHORITY_PATH}\n",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="carried semantic constraint"):
        build_task_brief(args(root, task))


@pytest.mark.parametrize("action", ["update", "supersede", "reclassify"])
def test_build_review_package_accepts_allocated_auth_in_knowledge_disposition(
    tmp_path: Path, action: str
) -> None:
    root, spec, task = workspace(tmp_path)
    carry_accepted_constraint(spec)
    base = committed_review_base(root)
    handoff = write_executor_handoff(
        root,
        f"  action: {action}\n  reason: Stable accepted authority changed.\n"
        f"  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    package = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head=base)
    ).read_text(encoding="utf-8")

    assert COMPILED_AUTHORITY in package
    assert ACCEPTED_CONSTRAINT in package
    assert f"action: {action}" in package
    assert ACCEPTED_AUTHORITY in package
    assert ACCEPTED_AUTHORITY_PATH not in package.split("## Knowledge disposition", 1)[1].split("## Allocated", 1)[0]


def test_build_review_package_rejects_unallocated_auth_in_knowledge_disposition(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    carry_accepted_constraint(spec)
    base = committed_review_base(root)
    handoff = write_executor_handoff(
        root,
        "  action: update\n  reason: Stable accepted authority changed.\n"
        "  affected_authority: [AUTH-002]\n",
    )

    with pytest.raises(SystemExit, match="unallocated decision authority"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))


def test_build_review_package_rejects_missing_plan_identity(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    base = committed_review_base(root)
    handoff = write_related_handoff(root, "related:\n  task: task-004\n")
    review_target = root / ".work-bundle/runtime/execution/plan-B/task-004/review-package.md"

    with pytest.raises(SystemExit, match="Handoff plan identity missing"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))

    assert not review_target.exists()


def test_build_review_package_rejects_null_plan_identity(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    base = committed_review_base(root)
    handoff = write_related_handoff(root, "related:\n  plan: null\n  task: task-004\n")

    with pytest.raises(SystemExit, match="Handoff plan identity missing"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))


def test_build_review_package_rejects_wrong_explicit_plan(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    base = committed_review_base(root)
    handoff = write_related_handoff(root, "related:\n  plan: plan-A\n  task: task-004\n")

    with pytest.raises(SystemExit, match="Handoff plan mismatch: expected plan-B, got plan-A"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))


def test_build_review_package_rejects_conflicting_plan_identities(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    base = committed_review_base(root)
    handoff = write_related_handoff(
        root,
        "related:\n  plan: plan-B\n  task: task-004\nrelated_plan: plan-A\n",
    )

    with pytest.raises(SystemExit, match="Handoff plan identity conflict"):
        build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))


def test_build_review_package_accepts_matching_plan_identity(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    base = committed_review_base(root)
    handoff = write_related_handoff(root, "related:\n  plan: plan-B\n  task: task-004\n")

    target = build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))

    assert target == root / ".work-bundle/runtime/execution/plan-B/task-004/review-package.md"
    assert target.is_file()
