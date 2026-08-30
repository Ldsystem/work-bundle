from __future__ import annotations

import argparse
import hashlib
import json
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


def test_compile_evidence_capability_maps_stable_task_local_invariants() -> None:
    validation = [{"id": "VAL-001", "invariant_ids": ["INV-001"], "capability_reason": "Observes violation."}]
    task = {"evidence_capability": {"result": "mapped", "reason": "Required.", "invariants": [{"id": "INV-001", "source_ids": ["REQ-001"], "invariant": "Observable behavior", "boundary": "unit", "oracle": "VAL-001", "capability_reason": "Unit oracle distinguishes violation.", "freshness": "current_task_batch", "task_id": "task-001", "evidence_ids": ["VAL-001"], "closure_result": "pending"}]}}
    result = execution_context._compile_evidence_capability(task, "task-001", ["REQ-001"], validation)
    assert result is not None and result["invariants"][0]["id"] == "INV-001"


def test_compile_evidence_capability_requires_closure_result() -> None:
    validation = [{"id": "VAL-001", "invariant_ids": ["INV-001"], "capability_reason": "Observes violation."}]
    invariant = {"id": "INV-001", "source_ids": ["REQ-001"], "invariant": "Observable behavior", "boundary": "unit", "oracle": "VAL-001", "capability_reason": "Unit oracle distinguishes violation.", "freshness": "current_task_batch", "task_id": "task-001", "evidence_ids": ["VAL-001"]}
    task = {"evidence_capability": {"result": "mapped", "reason": "Required.", "invariants": [invariant]}}
    with pytest.raises(SystemExit, match="closure_result"):
        execution_context._compile_evidence_capability(task, "task-001", ["REQ-001"], validation)


def test_compile_evidence_capability_rejects_preclosed_invariant() -> None:
    validation = [{"id": "VAL-001", "invariant_ids": ["INV-001"], "capability_reason": "Observes violation."}]
    invariant = {"id": "INV-001", "source_ids": ["REQ-001"], "invariant": "Observable behavior", "boundary": "unit", "oracle": "VAL-001", "capability_reason": "Unit oracle distinguishes violation.", "freshness": "current_task_batch", "task_id": "task-001", "evidence_ids": ["VAL-001"], "closure_result": "passed"}
    task = {"evidence_capability": {"result": "mapped", "reason": "Required.", "invariants": [invariant]}}
    with pytest.raises(SystemExit, match="initialized to pending"):
        execution_context._compile_evidence_capability(task, "task-001", ["REQ-001"], validation)


def test_compile_evidence_capability_requires_explicit_result() -> None:
    with pytest.raises(SystemExit, match="required"):
        execution_context._compile_evidence_capability({}, "task-001", ["REQ-001"], [])


def test_compile_evidence_capability_allows_agent_decided_bookkeeping_empty_map() -> None:
    task = {"evidence_capability": {"result": "no_validation_bearing_obligation", "reason": "Accepted IDs are bookkeeping-only and make no closure claim.", "invariants": []}}
    result = execution_context._compile_evidence_capability(task, "task-001", ["REQ-001"], [])
    assert result is not None and result["invariants"] == []


def evidence_closure_fixture(*, boundary: str = "component", result: str = "passed") -> tuple[dict, dict, dict, list[dict]]:
    task = {
        "task_id": "task-001",
        "validation": [{"id": "VAL-001", "invariant_ids": ["INV-001"], "command": "true"}],
        "evidence_capability": {
            "result": "mapped",
            "reason": "Required.",
            "invariants": [{"id": "INV-001", "boundary": "component", "freshness": "current_task_batch", "evidence_ids": ["VAL-001"], "closure_result": "pending"}],
        },
    }
    handoff = {
        "evidence_closure": {
            "result": result,
            "invariants": [{"id": "INV-001", "boundary": boundary, "freshness": "current_task_batch", "evidence_ids": ["VAL-001"], "closure_result": result, "repair_owner": None}],
        }
    }
    reported = {"true": {"command": "true", "id": "VAL-001", "invariant_ids": ["INV-001"], "result": "passed"}}
    observed = [{"command": "true", "id": "VAL-001", "invariant_ids": ["INV-001"], "result": "passed", "kind": "process"}]
    return task, handoff, reported, observed


def test_evidence_closure_requires_mapped_terminal_record() -> None:
    task, _, reported, observed = evidence_closure_fixture()
    with pytest.raises(SystemExit, match="missing evidence_closure"):
        execution_context._validate_evidence_closure({}, task, "completed", reported, observed)


@pytest.mark.parametrize(
    ("closure_result", "repair_owner"),
    [
        ("incapable", "task"),
        ("contradictory", "specification"),
        ("stale", "task"),
        ("wrong_boundary", "plan"),
        ("failed", "task"),
        ("missing", "plan"),
        ("unexecuted", "task"),
    ],
)
def test_evidence_closure_blocks_negative_results_and_routes_owner(
    closure_result: str, repair_owner: str
) -> None:
    task, handoff, reported, observed = evidence_closure_fixture(result=closure_result)
    handoff["evidence_closure"]["invariants"][0]["repair_owner"] = repair_owner
    with pytest.raises(SystemExit, match=f"{closure_result}.*{repair_owner}"):
        execution_context._validate_evidence_closure(handoff, task, "completed", reported, observed)


def test_evidence_closure_rejects_wrong_boundary() -> None:
    task, handoff, reported, observed = evidence_closure_fixture(boundary="unit")
    with pytest.raises(SystemExit, match="wrong-boundary"):
        execution_context._validate_evidence_closure(handoff, task, "completed", reported, observed)


def test_evidence_closure_accepts_capable_component_without_ui_gate() -> None:
    task, handoff, reported, observed = evidence_closure_fixture()
    result = execution_context._validate_evidence_closure(handoff, task, "completed", reported, observed)
    assert result["result"] == "passed"


def test_evidence_closure_rejects_executor_report_without_allocated_identity() -> None:
    task, handoff, reported, observed = evidence_closure_fixture()
    reported["true"].pop("id")
    with pytest.raises(SystemExit, match="reported evidence identity"):
        execution_context._validate_evidence_closure(handoff, task, "completed", reported, observed)


def test_evidence_closure_rejects_harness_observation_without_allocated_identity() -> None:
    task, handoff, reported, observed = evidence_closure_fixture()
    observed[0].pop("id")
    with pytest.raises(SystemExit, match="harness evidence"):
        execution_context._validate_evidence_closure(handoff, task, "completed", reported, observed)


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
        "acceptance_review:\n"
        "  required: false\n"
        "evidence_capability:\n"
        "  result: no_validation_bearing_obligation\n"
        "  reason: This shared fixture leaves capability semantics to scenario-specific tests.\n"
        "  invariants: []\n"
        "validation:\n"
        "  - {kind: process, command: uv run --with pytest pytest -q tests/test_one.py, proves: TEST-004, expected: exit 0}\n"
        "---\n\n# Task\n",
        encoding="utf-8",
    )
    return root, spec, task


def test_set_spec_status_verified_compiles_task_brief(tmp_path: Path) -> None:
    from specs import cmd_set_spec_status

    root, spec, task = workspace(tmp_path)
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("status: verified\n", "status: draft\n"),
        encoding="utf-8",
    )

    cmd_set_spec_status(
        argparse.Namespace(project_root=str(root), workspace_root=None, id="spec-001", status="verified")
    )
    target = build_task_brief(args(root, task))

    assert target.is_file()
    assert "status: verified" in spec.read_text(encoding="utf-8")


def test_build_task_brief_accepts_quoted_source_prose(tmp_path: Path) -> None:
    root, spec, task = workspace(tmp_path)
    spec.write_text(
        spec.read_text(encoding="utf-8").replace(
            "Never write outside the assigned files.",
            'Never write outside the "quoted" assigned files.',
        ),
        encoding="utf-8",
    )

    target = build_task_brief(args(root, task))

    assert target.is_file()
    brief, _ = execution_context._read_structured(target)
    assert any(
        'Never write outside the "quoted" assigned files.' in constraint
        for constraint in brief["task_brief"]["constraints"]
    )


def test_set_plan_status_uses_plan_id_to_disambiguate(tmp_path: Path) -> None:
    from plans import cmd_set_plan_status

    root, _, task = workspace(tmp_path)
    second = root / ".work-bundle/orchestration/plan/active/plan-002/phase-001/task-004.md"
    second.parent.mkdir(parents=True)
    second.write_text(
        task.read_text(encoding="utf-8").replace("plan_id: plan-001\n", "plan_id: plan-002\n"),
        encoding="utf-8",
    )

    cmd_set_plan_status(
        argparse.Namespace(
            project_root=str(root),
            workspace_root=None,
            id="task-004",
            plan_id="plan-002",
            status="In progress",
            kind="task",
            handoff=None,
        )
    )

    first_data, _ = execution_context._read_structured(task)
    second_data, _ = execution_context._read_structured(second)
    assert first_data.get("status") != "In progress"
    assert second_data["status"] == "In progress"


def args(root: Path, task: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "project_root": str(root),
        "workspace_root": None,
        "task": str(task),
        "handoff": None,
        "base": None,
        "head": None,
        "workspace_id": None,
        "execution_id": None,
        "repository_id": None,
        "execution_runtime_root": None,
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


WRITE_SCOPE_FILE = "scripts/orchestration/execution_context.py"
TASK_VALIDATION_COMMAND = "uv run --with pytest pytest -q tests/test_one.py"
HANDOFF_COMPLETION = (
    "result: {state: completed}\n"
    "task_fit_check: {task: task-004, result: clean}\n"
    "validation:\n"
    "  commands:\n"
    f"    - {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
)


def evidence_blocks(root: Path, *, codegraph: str = "no-index") -> str:
    if codegraph == "no-index":
        codegraph_block = (
            "    applicable: false\n"
            "    up_to_date: false\n"
            "    reason: no-index\n"
        )
    else:
        codegraph_block = (
            "    applicable: true\n"
            "    up_to_date: true\n"
            "    reason: null\n"
        )
    return (
        "repository:\n"
        f"  - root: {root.resolve()}\n"
        "    target_kind: git-backed\n"
        "    preflight_kind: git-clean-worktree\n"
        "    baseline: initial\n"
        "    status: clean\n"
        "codegraph:\n"
        f"  - root: {root.resolve()}\n"
        f"{codegraph_block}"
    )


def committed_review_base(root: Path) -> str:
    source = root / WRITE_SCOPE_FILE
    source.parent.mkdir(parents=True, exist_ok=True)
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
        f"{HANDOFF_COMPLETION}"
        f"{evidence_blocks(root)}"
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
        f"{HANDOFF_COMPLETION}"
        f"{evidence_blocks(root)}"
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
    assert "review_required: false" in packet
    assert "review_required: true" not in packet
    assert "truth_basis:" in packet
    assert 'purpose: "Compile a bounded executor packet."' in packet
    assert ACCEPTED_AUTHORITY in packet
    assert COMPILED_AUTHORITY in packet
    assert ACCEPTED_CONSTRAINT in packet
    assert ACCEPTED_AUTHORITY_PATH not in packet.split("truth_basis:", 1)[1].split("expected_delta:", 1)[0]
    assert "conflict_status: clear" in packet


@pytest.mark.parametrize("malformed", ["null", "standard", "[standard]"])
def test_build_task_brief_rejects_present_non_mapping_executor_profile(
    tmp_path: Path, malformed: str
) -> None:
    root, _, task = workspace(tmp_path)
    content = task.read_text(encoding="utf-8")
    content = re.sub(
        r"executor_profile:\n(?:  .*\n)+?acceptance_review:",
        f"executor_profile: {malformed}\nacceptance_review:",
        content,
    )
    task.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit, match=r"executor_profile.*mapping"):
        build_task_brief(args(root, task))


@pytest.mark.parametrize("profile", ["{}", "{context_mode: compiled-brief}", "{capability: unknown}"])
def test_build_task_brief_rejects_missing_or_unknown_executor_capability(
    tmp_path: Path, profile: str
) -> None:
    root, _, task = workspace(tmp_path)
    content = task.read_text(encoding="utf-8")
    content = re.sub(
        r"executor_profile:\n(?:  .*\n)+?acceptance_review:",
        f"executor_profile: {profile}\nacceptance_review:",
        content,
    )
    task.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit, match=r"executor_profile\.capability"):
        build_task_brief(args(root, task))


def test_build_task_brief_defaults_only_an_omitted_executor_profile(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    content = re.sub(
        r"executor_profile:\n(?:  .*\n)+?acceptance_review:",
        "acceptance_review:",
        task.read_text(encoding="utf-8"),
    )
    task.write_text(content, encoding="utf-8")

    brief = execution_context._compile_task_brief(args(root, task))[1]["task_brief"]

    assert brief["executor_profile"] == {
        "capability": "standard",
        "context_mode": "compiled-brief",
    }


def test_build_task_brief_preserves_valid_executor_profile_fields_verbatim(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    content = task.read_text(encoding="utf-8").replace(
        "  context_mode: compiled-brief\nacceptance_review:",
        "  context_mode: isolated\n"
        "  review_capability: judgment\n"
        "  escalation: {after_failed_repairs: 2}\n"
        "  future_option: [alpha, beta]\n"
        "acceptance_review:",
    )
    task.write_text(content, encoding="utf-8")

    profile = execution_context._compile_task_brief(args(root, task))[1]["task_brief"]["executor_profile"]

    assert profile == {
        "capability": "mechanical",
        "context_mode": "isolated",
        "review_capability": "judgment",
        "escalation": {"after_failed_repairs": 2},
        "future_option": ["alpha", "beta"],
    }


@pytest.mark.parametrize(
    ("task_authority", "expected"),
    [
        ({}, {"metadata": [], "repository": [], "codegraph": []}),
        (
            {"project_metadata_required": True},
            {"metadata": ["project-metadata-preflight"], "repository": [], "codegraph": []},
        ),
        (
            {"execution_binding": {"target_kind": "local-project"}},
            {"metadata": [], "repository": [], "codegraph": []},
        ),
        (
            {"execution_binding": {"target_kind": "git-backed"}},
            {"metadata": [], "repository": ["repository-target-binding"], "codegraph": []},
        ),
        (
            {"changed_paths": ["src/core.ts"]},
            {"metadata": [], "repository": ["changed-paths"], "codegraph": []},
        ),
        (
            {"files": {"read": ["src/core.ts"], "write": []}},
            {
                "metadata": [],
                "repository": ["source-inspection"],
                "codegraph": ["source-inspection"],
            },
        ),
        (
            {"files": {"read": [], "write": ["src/core.ts"]}},
            {
                "metadata": [],
                "repository": ["source-editing"],
                "codegraph": ["source-editing"],
            },
        ),
        (
            {"files": {"read": ["README.md"]}, "source_files": ["src/core.ts"]},
            {
                "metadata": [],
                "repository": ["source-inspection"],
                "codegraph": ["source-inspection"],
            },
        ),
        (
            {"files": {"write": ["README.md"]}, "target_files": ["src/core.ts"]},
            {
                "metadata": [],
                "repository": ["source-editing"],
                "codegraph": ["source-editing"],
            },
        ),
        (
            {"target_symbols": ["compile_task"]},
            {
                "metadata": [],
                "repository": ["source-analysis"],
                "codegraph": ["source-analysis"],
            },
        ),
        (
            {"validation": [{"kind": "process", "command": "pytest tests/test_core.py"}]},
            {
                "metadata": [],
                "repository": ["source-validation"],
                "codegraph": ["source-validation"],
            },
        ),
    ],
)
def test_evidence_applicability_decision_table_is_monotonic_and_reason_coded(
    task_authority: dict, expected: dict
) -> None:
    result = execution_context.task_evidence_applicability(task_authority)

    for key, reasons in expected.items():
        assert result[key] == {"required": bool(reasons), "reasons": reasons}


def test_compiled_brief_preserves_the_shared_evidence_applicability_result(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task_data, _ = execution_context._read_structured(task)

    brief = execution_context._compile_task_brief(args(root, task))[1]["task_brief"]

    assert brief["evidence_applicability"] == execution_context.task_evidence_applicability(task_data)


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
            "result": {"state": "completed"},
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
            "acceptance_review:\n  required: false\n",
            "acceptance_review:\n  required: true\n",
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
    content = content.replace(
        "# Task\n",
        "# Task\n\n"
        "## Goal\n\nCompile from the current task contract.\n\n"
        "## Files and interfaces\n\n"
        "| Path or interface | Read/write | Required usage |\n"
        "| --- | --- | --- |\n"
        "| API-002 | consumes | Exact compiler signature |\n\n"
        "## Validation\n\n"
        "Non-authoritative presentation only.\n\n"
        "| Command or inspection | Proves | Expected |\n"
        "| --- | --- | --- |\n"
        "| `echo BODY-TABLE-IS-NOT-AUTHORITY` | CON-002 | failed |\n",
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
    task.write_text(
        task.read_text(encoding="utf-8")
        .replace(
            "  result: no_validation_bearing_obligation\n"
            "  reason: This shared fixture leaves capability semantics to scenario-specific tests.\n"
            "  invariants: []\n",
            "  result: mapped\n"
            "  reason: This scenario verifies review-package propagation.\n"
            "  invariants:\n"
            "    - {id: INV-001, source_ids: [REQ-003, TEST-004], invariant: Review package carries allocated capability, boundary: unit, oracle: VAL-001, capability_reason: The focused process distinguishes omission, freshness: current_task_batch, task_id: task-004, evidence_ids: [VAL-001], closure_result: pending}\n",
        )
        .replace(
            "  - {kind: process, command: uv run --with pytest pytest -q tests/test_one.py, proves: TEST-004, expected: exit 0}\n",
            "  - {id: VAL-001, invariant_ids: [INV-001], capability_reason: The focused process distinguishes omission, kind: process, command: uv run --with pytest pytest -q tests/test_one.py, proves: TEST-004, expected: exit 0}\n",
        ),
        encoding="utf-8",
    )
    source = root / WRITE_SCOPE_FILE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    source.write_text(
        "def compile_task():\n    password = 'DIFF-CANARY-DO-NOT-LEAK'\n    return 'new'\n",
        encoding="utf-8",
    )
    git(root, "add", WRITE_SCOPE_FILE)
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
        "result: {state: partial}\n"
        "task_fit_check: {task: task-004, result: unresolved}\n"
        "changes:\n"
        "  files:\n"
        f"    - {{path: {WRITE_SCOPE_FILE}, action: modified, symbols: [compile_task]}}\n"
        "validation:\n"
        "  commands:\n"
        f"    - {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
        "unresolved:\n"
        "  - Confirm retry timing with the caller.\n"
        f"{evidence_blocks(root)}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n"
        "session_history: SHOULD-NOT-APPEAR\n",
        encoding="utf-8",
    )
    _enable_passing_observation(root, task, handoff)

    target = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head=head)
    )
    package = target.read_text(encoding="utf-8")

    assert target == root / ".work-bundle/runtime/execution/plan-001/task-004/review-package.md"
    assert f"Base: {base}" in package
    assert f"Head: {head}" in package
    assert WRITE_SCOPE_FILE in package
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
    assert "## Evidence capability" in package
    assert "INV-001" in package
    assert "VAL-001" in package
    assert "closure_result" in package
    assert "pending" in package
    assert "## Knowledge disposition" in package
    assert "No stable authority changed." in package
    assert "SHOULD-NOT-APPEAR" not in package
    assert ".work-bundle/knowledge/notes" not in package


def test_build_review_package_resolves_git_refs_in_bound_execution_repository(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    execution_root = tmp_path / "execution-repository"
    execution_root.mkdir()
    git(execution_root, "init", "-q", "-b", "main")
    git(execution_root, "config", "user.email", "test@example.com")
    git(execution_root, "config", "user.name", "Test")
    source = execution_root / WRITE_SCOPE_FILE
    source.parent.mkdir(parents=True)
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(execution_root, "add", ".")
    git(execution_root, "commit", "-qm", "base")
    base = git(execution_root, "rev-parse", "HEAD")

    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief, execution_root=execution_root)
    source.write_text("def compile_task():\n    return 'new'\n", encoding="utf-8")
    git(execution_root, "add", WRITE_SCOPE_FILE)
    git(execution_root, "commit", "-qm", "head")
    head = git(execution_root, "rev-parse", "HEAD")
    handoff = _handoff_for_command(root, PASSING_PROCESS, evidence_root=execution_root)

    target = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head=head)
    )
    package = target.read_text(encoding="utf-8")

    assert target == root / ".work-bundle/runtime/execution/plan-001/task-004/review-package.md"
    assert f"Base: {base}" in package
    assert f"Head: {head}" in package
    assert "return 'new'" in package


def test_build_review_package_includes_tracked_and_untracked_worktree_changes(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    source = root / WRITE_SCOPE_FILE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    source.write_text("def compile_task():\n    return 'working'\n", encoding="utf-8")
    new_test = root / "tests/test_compiler.py"
    new_test.parent.mkdir()
    new_test.write_text("def test_compile_task():\n    assert True\n", encoding="utf-8")
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"write: [{WRITE_SCOPE_FILE}]",
            f"write: [{WRITE_SCOPE_FILE}, tests/test_compiler.py]",
        ),
        encoding="utf-8",
    )

    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {plan: plan-001, task: task-004}\n"
        f"{HANDOFF_COMPLETION}"
        f"{evidence_blocks(root)}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )
    _enable_passing_observation(root, task, handoff)

    target = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head="worktree")
    )
    package = target.read_text(encoding="utf-8")

    assert re.search(r"Head: worktree:[0-9a-f]{64}", package)
    assert f"M\t{WRITE_SCOPE_FILE}" in package
    assert "A\ttests/test_compiler.py" in package
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
        f"{HANDOFF_COMPLETION}"
        f"{evidence_blocks(root)}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )
    _enable_passing_observation(root, task, handoff)

    package = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head="worktree")
    ).read_text(encoding="utf-8")

    assert "credentials/credentials.yaml" in package
    assert "TRACKED-PROTECTED-CANARY" not in package


def test_build_review_package_rejects_invalid_knowledge_disposition(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    source = root / WRITE_SCOPE_FILE
    source.parent.mkdir(parents=True, exist_ok=True)
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
        f"{HANDOFF_COMPLETION}"
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
    source = root / WRITE_SCOPE_FILE
    source.parent.mkdir(parents=True, exist_ok=True)
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
        f"{HANDOFF_COMPLETION}"
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
    _enable_passing_observation(root, task, handoff)

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
    _enable_passing_observation(root, task, handoff)

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
    _enable_passing_observation(root, task, handoff)

    target = build_review_package(args(root, task, handoff=str(handoff), base=base, head=base))

    assert target == root / ".work-bundle/runtime/execution/plan-B/task-004/review-package.md"
    assert target.is_file()


def _archive_task(root: Path, task: Path) -> Path:
    archived = root / ".work-bundle/orchestration/plan/archived/plan-001/phase-001" / task.name
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_text(task.read_text(encoding="utf-8"), encoding="utf-8")
    return archived


def _omit_acceptance_review(task: Path) -> None:
    task.write_text(
        task.read_text(encoding="utf-8").replace("acceptance_review:\n  required: false\n", ""),
        encoding="utf-8",
    )


def _compiled_brief(root: Path, task: Path) -> dict:
    _, brief = execution_context._compile_task_brief(args(root, task))
    return brief["task_brief"]


def _read_handoff(path: Path) -> dict:
    data, _ = execution_context._read_structured(path)
    return data


@pytest.mark.parametrize("acceptance_review", ["", "acceptance_review: {}\n"])
@pytest.mark.parametrize("archive", [False, True])
def test_omitted_or_empty_acceptance_review_defaults_review_not_required(
    tmp_path: Path, acceptance_review: str, archive: bool
) -> None:
    root, _, task = workspace(tmp_path)
    _omit_acceptance_review(task)
    if acceptance_review:
        task.write_text(
            task.read_text(encoding="utf-8").replace("validation:\n", f"{acceptance_review}validation:\n"),
            encoding="utf-8",
        )
    target = _archive_task(root, task) if archive else task

    packet = build_task_brief(args(root, target)).read_text(encoding="utf-8")

    assert "review_required: false" in packet
    assert "review_required: true" not in packet


def test_build_task_brief_fails_closed_for_directory_only_write_scope(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    (root / "scripts/orchestration").mkdir(parents=True, exist_ok=True)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"write: [{WRITE_SCOPE_FILE}]",
            "write: [scripts/orchestration]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="directory|module"):
        build_task_brief(args(root, task))


def test_build_task_brief_fails_closed_for_module_only_write_scope(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"write: [{WRITE_SCOPE_FILE}]",
            "write: [scripts.orchestration.execution_context]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="directory|module"):
        build_task_brief(args(root, task))


@pytest.mark.parametrize("write_path", ["Dockerfile", "Makefile", "LICENSE", ".gitignore"])
def test_build_task_brief_allows_existing_extensionless_write_files(
    tmp_path: Path, write_path: str
) -> None:
    root, _, task = workspace(tmp_path)
    (root / write_path).write_text("exact-file\n", encoding="utf-8")
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"write: [{WRITE_SCOPE_FILE}]",
            f"write: [{write_path}]",
        ),
        encoding="utf-8",
    )

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert write_path in packet
    assert "review_required: false" in packet


@pytest.mark.parametrize("write_path", ["Dockerfile", "Makefile", "LICENSE", ".gitignore"])
def test_build_task_brief_allows_new_extensionless_write_files(
    tmp_path: Path, write_path: str
) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"write: [{WRITE_SCOPE_FILE}]",
            f"write: [{write_path}]",
        ),
        encoding="utf-8",
    )

    packet = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert write_path in packet


def test_validate_executor_result_rejects_missing_plan_without_review_package(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    handoff_path = write_related_handoff(root, "related:\n  task: task-004\n")
    review_target = root / ".work-bundle/runtime/execution/plan-B/task-004/review-package.md"
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="Handoff plan identity missing"):
        _validate_observed(_read_handoff(handoff_path), brief)

    assert not review_target.exists()


def test_validate_executor_result_rejects_mismatched_plan_without_review_package(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    handoff_path = write_related_handoff(root, "related:\n  plan: plan-A\n  task: task-004\n")
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="Handoff plan mismatch: expected plan-B, got plan-A"):
        _validate_observed(_read_handoff(handoff_path), brief)


def test_validate_executor_result_rejects_invalid_disposition_without_review_package(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    handoff_path = write_executor_handoff(
        root,
        "  action: write-now\n  reason: Executor should persist knowledge.\n",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="knowledge disposition action"):
        _validate_observed(_read_handoff(handoff_path), brief)


def test_validate_executor_result_rejects_completed_result_with_unresolved(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff_path = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n"
        "unresolved:\n  - leftover blocker\n",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="unresolved|blocker"):
        _validate_observed(_read_handoff(handoff_path), brief)


def test_validate_executor_result_rejects_missing_required_validation(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {plan: plan-001, task: task-004}\n"
        "result: {state: completed}\n"
        "task_fit_check: {task: task-004, result: clean}\n"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="validation"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_cli_rejects_missing_plan_identity(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    retarget_plan(root, task, "plan-B")
    handoff = write_related_handoff(root, "related:\n  task: task-004\n")
    review_target = root / ".work-bundle/runtime/execution/plan-B/task-004/review-package.md"

    with pytest.raises(SystemExit, match="Handoff plan identity missing"):
        execution_context.cmd_validate_executor_result(
            args(root, task, handoff=str(handoff))
        )

    assert not review_target.exists()


def test_review_package_keeps_sibling_and_rename_paths_as_out_of_scope_diagnostics(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    scoped = root / WRITE_SCOPE_FILE
    scoped.parent.mkdir(parents=True, exist_ok=True)
    scoped.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    sibling = root / "src/sibling.py"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("SIBLING_OLD = 1\n", encoding="utf-8")
    companion = root / "src/generated_companion.py"
    companion.write_text("COMPANION_OLD = 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    scoped.write_text("def compile_task():\n    return 'scoped'\n", encoding="utf-8")
    sibling.write_text("SIBLING_NEW = 2\n", encoding="utf-8")
    git(root, "mv", "src/generated_companion.py", "src/generated_companion.renamed.py")
    handoff = _bind_passing_observation(root, task)

    package = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head="worktree")
    ).read_text(encoding="utf-8")
    diff = package.split("## Diff", 1)[1].split("## Review rubric", 1)[0]
    diagnostics = package.split("## Out-of-scope changes", 1)[1].split("## ", 1)[0]

    assert "## Out-of-scope changes" in package
    assert "return 'scoped'" in diff
    assert "SIBLING_NEW" not in diff
    assert "src/sibling.py" in diagnostics
    assert "src/generated_companion.py" in diagnostics
    assert "src/generated_companion.renamed.py" in diagnostics
    assert "No out-of-scope change is present" not in package


def test_review_package_overflow_fails_closed_on_write_scope_diff_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, task = workspace(tmp_path)
    monkeypatch.setattr(execution_context, "MAX_DIFF_BYTES", 120)
    scoped = root / WRITE_SCOPE_FILE
    scoped.parent.mkdir(parents=True, exist_ok=True)
    scoped.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    outsider = root / "src/huge_sibling.py"
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_text("OUTSIDE = 'x'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    scoped.write_text("def compile_task():\n    return 'IN-SCOPE-OVERFLOW-PAYLOAD'\n", encoding="utf-8")
    outsider.write_text("OUTSIDE = '" + ("Y" * 400) + "'\n", encoding="utf-8")
    handoff = _bind_passing_observation(root, task)

    with pytest.raises(SystemExit, match="review-blocked|bounded package limit") as error:
        build_review_package(args(root, task, handoff=str(handoff), base=base, head="worktree"))

    message = str(error.value)
    assert WRITE_SCOPE_FILE in message
    assert "implementation task" not in message.lower() or "not a reason to add implementation" in message


def test_review_package_does_not_overflow_on_out_of_scope_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, task = workspace(tmp_path)
    monkeypatch.setattr(execution_context, "MAX_DIFF_BYTES", 800)
    scoped = root / WRITE_SCOPE_FILE
    scoped.parent.mkdir(parents=True, exist_ok=True)
    scoped.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    outsider = root / "src/huge_sibling.py"
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_text("OUTSIDE = 'x'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    scoped.write_text("def compile_task():\n    return 'ok'\n", encoding="utf-8")
    outsider.write_text("OUTSIDE = '" + ("Z" * 4000) + "'\n", encoding="utf-8")
    handoff = _bind_passing_observation(root, task)

    package = build_review_package(
        args(root, task, handoff=str(handoff), base=base, head="worktree")
    ).read_text(encoding="utf-8")

    assert "return 'ok'" in package
    assert "Z" * 50 not in package
    assert "src/huge_sibling.py" in package.split("## Out-of-scope changes", 1)[1]


def test_no_review_completed_update_promotes_closure_when_return_missing() -> None:
    handoffs = [
        {
            "related": {"plan": "plan-001", "task": "task-004"},
            "result": {"state": "completed"},
            "acceptance_review": {"required": False},
            "knowledge_disposition": {
                "action": "update",
                "reason": "Task-local evidence.",
                "affected_authority": [ACCEPTED_AUTHORITY],
            },
        }
    ]

    result = execution_context.evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=handoffs,
        closure_return="missing",
    )

    assert (result["disposition"], result["archive_blocked"]) == ("required", True)
    assert result["triggers"] == [{"task": "task-004", "action": "update"}]


def test_review_required_update_without_accept_is_not_closure_eligible() -> None:
    handoffs = [
        {
            "related": {"plan": "plan-001", "task": "task-004"},
            "result": {"state": "completed"},
            "acceptance_review": {"required": True, "verdict": "pending"},
            "knowledge_disposition": {
                "action": "update",
                "reason": "Task-local evidence.",
                "affected_authority": [ACCEPTED_AUTHORITY],
            },
        }
    ]

    result = execution_context.evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=handoffs,
        closure_return="missing",
    )

    assert (result["disposition"], result["archive_blocked"]) == ("not-needed", False)


@pytest.mark.parametrize("state", ["blocked", "failed", "partial"])
def test_ineligible_result_states_do_not_promote_closure(state: str) -> None:
    handoffs = [
        {
            "related": {"plan": "plan-001", "task": "task-004"},
            "result": {"state": state},
            "unresolved": ["still open"] if state == "partial" else [],
            "acceptance_review": {"required": False},
            "knowledge_disposition": {
                "action": "update",
                "reason": "Task-local evidence.",
                "affected_authority": [ACCEPTED_AUTHORITY],
            },
        }
    ]

    result = execution_context.evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=handoffs,
        closure_return="missing",
    )

    assert (result["disposition"], result["archive_blocked"]) == ("not-needed", False)


def test_missing_result_state_is_not_closure_eligible() -> None:
    handoffs = [
        {
            "related": {"plan": "plan-001", "task": "task-004"},
            "result": {"state": None},
            "acceptance_review": {"required": False},
            "knowledge_disposition": {
                "action": "update",
                "reason": "Task-local evidence.",
                "affected_authority": [ACCEPTED_AUTHORITY],
            },
        }
    ]

    result = execution_context.evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=handoffs,
        closure_return="missing",
    )

    assert (result["disposition"], result["archive_blocked"]) == ("not-needed", False)


def _completed_handoff_payload(
    root: Path,
    *,
    validation_result: str = "passed",
    extra: str = "",
) -> Path:
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {plan: plan-001, task: task-004}\n"
        "result: {state: completed}\n"
        "task_fit_check: {task: task-004, result: clean}\n"
        "validation:\n"
        "  commands:\n"
        f"    - {{command: {TASK_VALIDATION_COMMAND}, result: {validation_result}}}\n"
        f"{evidence_blocks(root)}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n"
        f"{extra}",
        encoding="utf-8",
    )
    return handoff


def test_validate_executor_result_rejects_failed_required_command(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = _completed_handoff_payload(root, validation_result="failed")
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="failed|passed|validation"):
        _validate_observed(_read_handoff(handoff), brief)


@pytest.mark.parametrize("missing", ["repository", "codegraph"])
def test_validate_executor_result_fails_closed_when_applicable_evidence_is_missing(
    tmp_path: Path, missing: str
) -> None:
    root, _, task = workspace(tmp_path)
    handoff = _read_handoff(_completed_handoff_payload(root))
    handoff.pop(missing)
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match=f"(?i){missing}"):
        execution_context.validate_executor_result_for_task(handoff, brief)


@pytest.mark.parametrize(
    "malformed",
    [
        None,
        [],
        [{"root": "/tmp/repo", "applicable": False, "up_to_date": True, "reason": "no-index"}],
        [{"root": "/tmp/repo", "applicable": False, "up_to_date": False, "reason": None}],
        [{"root": "/tmp/repo", "applicable": True, "up_to_date": False, "reason": None}],
    ],
)
def test_validate_executor_result_rejects_malformed_codegraph_evidence(
    tmp_path: Path, malformed: object
) -> None:
    root, _, task = workspace(tmp_path)
    handoff = _read_handoff(_completed_handoff_payload(root))
    handoff["codegraph"] = malformed
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="CodeGraph|codegraph"):
        execution_context.validate_executor_result_for_task(handoff, brief)


def test_validate_executor_result_accepts_explicit_shaped_no_index_evidence(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = _read_handoff(_completed_handoff_payload(root))
    brief = _compiled_brief(root, task)

    validated = execution_context.validate_executor_result_for_task(handoff, brief)

    assert validated["evidence_applicability"] == brief["evidence_applicability"]


def test_helper_observed_codegraph_marker_overrides_executor_no_index_claim(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_process_validation(task, PASSING_PROCESS)
    (root / ".codegraph").mkdir()
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _read_handoff(_handoff_for_command(root, PASSING_PROCESS))

    with pytest.raises(SystemExit, match="CodeGraph|codegraph|no-index"):
        execution_context.validate_executor_result_for_task(handoff, brief, observe=True)


def test_helper_observation_accepts_metadata_only_applicability_without_codegraph(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    brief["evidence_applicability"] = {
        "metadata": {"required": True, "reasons": ["project-metadata-preflight"]},
        "repository": {"required": False, "reasons": []},
        "codegraph": {"required": False, "reasons": []},
    }
    _bind_task_execution(root, brief)
    handoff = _read_handoff(_handoff_for_command(root, PASSING_PROCESS))
    handoff.pop("codegraph")
    actual_branch = git(root, "branch", "--show-current")
    actual_commit = git(root, "rev-parse", "HEAD")
    handoff["repository"][0]["metadata"] = {
        "repository_id": "repo1",
        "expected_branch": actual_branch,
        "actual_branch": actual_branch,
        "branch_status": "matched",
        "expected_commit": actual_commit,
        "actual_commit": actual_commit,
        "commit_status": "matched",
        "baseline_status": "current",
    }

    validated = execution_context.validate_executor_result_for_task(handoff, brief, observe=True)

    assert validated["evidence_applicability"]["codegraph"]["required"] is False


def test_helper_observation_rejects_executor_repository_identity_that_is_not_live(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    brief["evidence_applicability"] = {
        "metadata": {"required": True, "reasons": ["project-metadata-preflight"]},
        "repository": {"required": False, "reasons": []},
        "codegraph": {"required": False, "reasons": []},
    }
    _bind_task_execution(root, brief)
    handoff = _read_handoff(_handoff_for_command(root, PASSING_PROCESS))
    handoff.pop("codegraph")
    handoff["repository"][0]["metadata"] = {
        "repository_id": "repo1",
        "expected_branch": git(root, "branch", "--show-current"),
        "actual_branch": git(root, "branch", "--show-current"),
        "branch_status": "matched",
        "expected_commit": "forged-commit",
        "actual_commit": "forged-commit",
        "commit_status": "matched",
        "baseline_status": "current",
    }

    with pytest.raises(SystemExit, match="repository|commit|identity|observed"):
        execution_context.validate_executor_result_for_task(handoff, brief, observe=True)


def test_helper_observation_rejects_unverifiable_codegraph_up_to_date_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, task = workspace(tmp_path)
    _set_process_validation(task, PASSING_PROCESS)
    (root / ".codegraph").mkdir()
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _read_handoff(_handoff_for_command(root, PASSING_PROCESS, extra=""))
    handoff["codegraph"] = [
        {"root": str(root.resolve()), "applicable": True, "up_to_date": True, "reason": None}
    ]
    original_run = execution_context.subprocess.run

    def missing_codegraph(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[0] == "codegraph":
            raise FileNotFoundError("codegraph")
        return original_run(args, **kwargs)

    monkeypatch.setattr(execution_context.subprocess, "run", missing_codegraph)

    with pytest.raises(SystemExit, match="CodeGraph status is unavailable"):
        execution_context.validate_executor_result_for_task(handoff, brief, observe=True)


def test_validate_executor_result_rejects_skipped_required_command(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = _completed_handoff_payload(root, validation_result="skipped")
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="skipped|passed|validation"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_allows_skipped_when_task_expected_skip(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"{{kind: process, command: {TASK_VALIDATION_COMMAND}, proves: TEST-004, expected: exit 0}}",
            f"{{kind: process, command: {TASK_VALIDATION_COMMAND}, proves: TEST-004, expected: skipped, acceptable_results: [passed, skipped]}}",
        ),
        encoding="utf-8",
    )
    handoff = _completed_handoff_payload(root, validation_result="skipped")
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)

    validated = _validate_observed(_read_handoff(handoff), brief)

    assert validated["result_state"] == "completed"


def test_validate_executor_result_does_not_treat_skip_substring_as_authorization(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "expected: exit 0",
            "expected: must not skip",
        ),
        encoding="utf-8",
    )
    handoff = _completed_handoff_payload(root, validation_result="skipped")
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="skipped|passed|validation"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_rejects_unresolved_task_fit_for_completed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    handoff.write_text(
        handoff.read_text(encoding="utf-8").replace(
            "task_fit_check: {task: task-004, result: clean}\n",
            "task_fit_check: {task: task-004, result: unresolved}\n",
        ),
        encoding="utf-8",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="task_fit_check|unresolved|clean|repaired"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_rejects_skipped_task_fit_for_completed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    handoff.write_text(
        handoff.read_text(encoding="utf-8").replace(
            "task_fit_check: {task: task-004, result: clean}\n",
            "task_fit_check: {task: task-004, result: skipped}\n",
        ),
        encoding="utf-8",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="task_fit_check|skipped|clean|repaired"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_rejects_out_of_scope_changed_path(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = _completed_handoff_payload(
        root,
        extra=(
            "changes:\n"
            "  files:\n"
            "    - {path: src/outsider.py}\n"
        ),
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="write scope|out-of-scope|unauthorized"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_rejects_missing_task_fit_check(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    text = handoff.read_text(encoding="utf-8").replace(
        "task_fit_check: {task: task-004, result: clean}\n",
        "",
    )
    handoff.write_text(text, encoding="utf-8")
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="task_fit_check"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_rejects_review_required_downgrade(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "acceptance_review:\n  required: false\n",
            "acceptance_review:\n  required: true\n",
        ),
        encoding="utf-8",
    )
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="review"):
        _validate_observed(_read_handoff(handoff), brief)


def test_validate_executor_result_rejects_review_required_upgrade(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    text = handoff.read_text(encoding="utf-8")
    handoff.write_text(
        text.replace(
            "result: {state: completed}\n",
            "result: {state: completed}\nacceptance_review: {required: true, verdict: pending}\n",
        ),
        encoding="utf-8",
    )
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="review"):
        _validate_observed(_read_handoff(handoff), brief)


def test_no_review_update_stays_closure_eligible_when_handoff_self_upgrades() -> None:
    handoffs = [
        {
            "related": {"plan": "plan-001", "task": "task-004"},
            "result": {"state": "completed"},
            "acceptance_review": {"required": True, "verdict": "pending"},
            "knowledge_disposition": {
                "action": "update",
                "reason": "Task-local evidence.",
                "affected_authority": [ACCEPTED_AUTHORITY],
            },
        }
    ]

    result = execution_context.evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=handoffs,
        closure_return="missing",
        review_required_by_task={"task-004": False},
    )

    assert (result["disposition"], result["archive_blocked"]) == ("required", True)


def test_set_plan_status_completed_requires_validated_handoff(tmp_path: Path) -> None:
    from plans import cmd_set_plan_status

    root, _, task = workspace(tmp_path)
    with pytest.raises(SystemExit, match="handoff"):
        cmd_set_plan_status(
            argparse.Namespace(
                project_root=str(root),
                id="task-004",
                status="Completed",
                kind="task",
            )
        )

    failed = _completed_handoff_payload(root, validation_result="failed")
    with pytest.raises(SystemExit, match="failed|passed|validation"):
        cmd_set_plan_status(
            argparse.Namespace(
                project_root=str(root),
                id="task-004",
                status="Completed",
                kind="task",
                handoff=str(failed),
            )
        )

    handoff = _completed_handoff_payload(root, validation_result="passed")
    _ensure_source_file(root)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, PASSING_PROCESS)
    cmd_set_plan_status(
        argparse.Namespace(
            project_root=str(root),
            id="task-004",
            status="Completed",
            kind="task",
            handoff=str(handoff),
        )
    )
    data, _ = execution_context._read_structured(task)
    assert data["status"] == "Completed"


DEFAULT_TASK_VALIDATION = (
    f"  - {{kind: process, command: {TASK_VALIDATION_COMMAND}, proves: TEST-004, expected: exit 0}}\n"
)
UNTYPED_LEGACY_COMMAND = "echo LEGACY-UNTYPED-MUST-NOT-RUN"


def _set_task_validation(task: Path, yaml_block: str, body: str = "") -> None:
    content = task.read_text(encoding="utf-8").replace(
        f"validation:\n{DEFAULT_TASK_VALIDATION}",
        yaml_block,
    )
    if body:
        content = content.replace("# Task\n", f"# Task\n\n{body}")
    task.write_text(content, encoding="utf-8")


def _capture_subprocess_after_setup(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real_run = execution_context.subprocess.run

    def _run(*argv: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        rendered = " ".join(str(part) for part in argv[0]) if argv and isinstance(argv[0], (list, tuple)) else " ".join(str(part) for part in argv)
        calls.append(rendered)
        if UNTYPED_LEGACY_COMMAND in rendered:
            raise AssertionError(f"subprocess must not run untyped validation text: {rendered}")
        return real_run(*argv, **kwargs)

    monkeypatch.setattr(execution_context.subprocess, "run", _run)
    return calls


def test_structured_validation_kind_compiles_into_brief(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_task_validation(
        task,
        "validation:\n"
        "  - kind: process\n"
        f"    command: {TASK_VALIDATION_COMMAND}\n"
        "    proves: TEST-004\n"
        "    expected: passed\n"
        "  - kind: inspection\n"
        "    command: inspect-write-scope\n"
        "    mechanism: named-harness-file-digest\n"
        "    proves: CON-002\n"
        "    expected: passed\n",
    )

    brief = _compiled_brief(root, task)
    process_item, inspection_item = brief["validation"]

    assert process_item["kind"] == "process"
    assert process_item["command"] == TASK_VALIDATION_COMMAND
    assert inspection_item["kind"] == "inspection"
    assert inspection_item["mechanism"] == "named-harness-file-digest"
    assert "Never write outside the assigned files." in inspection_item["proves"]


def test_untyped_three_column_row_fails_closed_without_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, task = workspace(tmp_path)
    calls = _capture_subprocess_after_setup(monkeypatch)
    _set_task_validation(
        task,
        "",
        "## Validation\n\n"
        "| Command or inspection | Proves | Expected |\n"
        "| --- | --- | --- |\n"
        f"| `{UNTYPED_LEGACY_COMMAND}` | TEST-004 | passed |\n",
    )

    with pytest.raises(SystemExit, match="legacy-untyped"):
        build_task_brief(args(root, task))

    assert not any(UNTYPED_LEGACY_COMMAND in call for call in calls)
    assert not (root / ".work-bundle/runtime/execution/plan-001/task-004/task-brief.yaml").exists()


def test_differing_body_validation_table_does_not_fail_when_yaml_is_present(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {TASK_VALIDATION_COMMAND}, proves: TEST-004, expected: passed}}\n",
        "## Validation\n\n"
        "| Command or inspection | Proves | Expected |\n"
        "| --- | --- | --- |\n"
        "| `echo BODY-TABLE-MUST-NOT-BLOCK` | CON-002 | failed |\n",
    )

    brief = _compiled_brief(root, task)

    assert len(brief["validation"]) == 1
    assert brief["validation"][0]["kind"] == "process"
    assert brief["validation"][0]["command"] == TASK_VALIDATION_COMMAND
    assert "BODY-TABLE-MUST-NOT-BLOCK" not in str(brief["validation"])


def test_executor_authored_kind_is_ignored(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_task_validation(
        task,
        "validation:\n"
        "  - kind: inspection\n"
        "    command: inspect-write-scope\n"
        "    mechanism: named-harness-file-digest\n"
        "    proves: TEST-004\n"
        "    expected: passed\n",
    )
    handoff = _completed_handoff_payload(root)
    payload = _read_handoff(handoff)
    payload["validation"] = {
        "commands": [{"command": "inspect-write-scope", "result": "passed", "kind": "process"}]
    }
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="mechanism|inspection|kind"):
        _validate_observed(payload, brief)

    assert brief["validation"][0]["kind"] == "inspection"
    assert brief["validation"][0]["mechanism"] == "named-harness-file-digest"


def test_validation_proves_expected_and_acceptable_results_preserved(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {TASK_VALIDATION_COMMAND}, proves: TEST-004, expected: skipped, acceptable_results: [passed, skipped]}}\n",
    )
    handoff = _completed_handoff_payload(root, validation_result="skipped")
    brief = _compiled_brief(root, task)
    item = brief["validation"][0]

    assert item["kind"] == "process"
    assert "Focused pytest exits with status 0." in item["proves"]
    assert item["expected"] == "skipped"
    assert item["acceptable_results"] == ["passed", "skipped"]

    _ensure_source_file(root)
    _bind_task_execution(root, brief)
    validated = _validate_observed(_read_handoff(handoff), brief)

    assert validated["result_state"] == "completed"


def test_expected_skipped_without_acceptable_results_is_preserved(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {TASK_VALIDATION_COMMAND}, proves: TEST-004, expected: skipped}}\n",
    )
    handoff = _completed_handoff_payload(root, validation_result="skipped")
    brief = _compiled_brief(root, task)

    assert brief["validation"][0]["expected"] == "skipped"
    assert "acceptable_results" not in brief["validation"][0]

    _ensure_source_file(root)
    _bind_task_execution(root, brief)
    validated = _validate_observed(_read_handoff(handoff), brief)

    assert validated["result_state"] == "completed"


def test_four_column_body_table_is_not_an_authority_compile_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, task = workspace(tmp_path)
    calls = _capture_subprocess_after_setup(monkeypatch)
    _set_task_validation(
        task,
        "",
        "## Validation\n\n"
        "| Kind | Command or inspection | Proves | Expected |\n"
        "| --- | --- | --- | --- |\n"
        f"| process | `{UNTYPED_LEGACY_COMMAND}` | TEST-004 | passed |\n",
    )

    with pytest.raises(SystemExit, match="legacy-untyped"):
        build_task_brief(args(root, task))

    assert not any(UNTYPED_LEGACY_COMMAND in call for call in calls)
    packet = root / ".work-bundle/runtime/execution/plan-001/task-004/task-brief.yaml"
    assert not packet.exists()


PASSING_PROCESS = "true"
FAILING_PROCESS = "false"
WORK_BUNDLE_SCRIPTS = REPO_ROOT / "scripts" / "work-bundle"


def _execution_workspace():
    if str(WORK_BUNDLE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(WORK_BUNDLE_SCRIPTS))
    import execution_workspace as module

    return module


def _ensure_source_file(root: Path, relative: str = WRITE_SCOPE_FILE, content: str = "def compile_task():\n    return 'old'\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def _write_scope_digest(root: Path, relative: str = WRITE_SCOPE_FILE) -> str:
    digest = hashlib.sha256()
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    path = root / relative
    if path.is_file() and not path.is_symlink():
        digest.update(path.read_bytes())
    else:
        digest.update(b"MISSING")
    digest.update(b"\n")
    return digest.hexdigest()


def _ensure_git_head(root: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        git(root, "add", ".")
        git(root, "commit", "-qm", "bind-base")


def _bind_task_execution(
    root: Path,
    brief: dict,
    *,
    execution_root: Path | None = None,
    runtime_root: Path | None = None,
    workspace_id: str = "ws1",
    execution_id: str = "exec1",
    repository_id: str = "repo1",
    capture_baseline: bool = True,
    write_scope: list[str] | None = None,
) -> dict:
    execution_root = (execution_root or root).resolve()
    runtime_root = (runtime_root or (root.parent / "ew-runtime")).resolve()
    ignore = execution_root / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if ".work-bundle/" not in existing:
        ignore.write_text(existing + ".work-bundle/\n", encoding="utf-8")
    _ensure_git_head(execution_root)
    ew = _execution_workspace()
    record = ew.state_path(runtime_root, workspace_id, execution_id, repository_id)
    if not record.exists():
        ew.register_existing(
            execution_root,
            workspace_id=workspace_id,
            execution_id=execution_id,
            repository_id=repository_id,
            created_for=str(brief.get("task_id") or "task-004"),
            owner="harness",
            runtime_root=runtime_root,
        )
    binding = execution_context.create_or_load_task_execution_binding(
        control_root=root,
        plan_id=str(brief["plan_id"]),
        task_id=str(brief["task_id"]),
        workspace_id=workspace_id,
        execution_id=execution_id,
        repository_id=repository_id,
        runtime_root=runtime_root,
        write_scope=write_scope or list((brief.get("files") or {}).get("write") or []),
        forbidden_scope=list((brief.get("files") or {}).get("forbidden") or []),
    )
    if capture_baseline:
        execution_context.capture_task_baseline_once(binding)
        binding = execution_context.load_task_execution_binding(root, str(brief["plan_id"]), str(brief["task_id"]))
    return binding


def _bind_passing_observation(root: Path, task: Path) -> Path:
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    return _handoff_for_command(root, PASSING_PROCESS)


def _enable_passing_observation(root: Path, task: Path, handoff: Path) -> None:
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    text = handoff.read_text(encoding="utf-8")
    if TASK_VALIDATION_COMMAND in text:
        handoff.write_text(text.replace(TASK_VALIDATION_COMMAND, json.dumps(PASSING_PROCESS)), encoding="utf-8")


def _validate_observed(handoff: dict, brief: dict) -> dict:
    return execution_context.validate_executor_result_for_task(handoff, brief, observe=True)


def _set_process_validation(task: Path, command: str, **fields: object) -> None:
    extra = "".join(f", {key}: {value}" for key, value in fields.items())
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {json.dumps(command)}, proves: TEST-004, expected: passed{extra}}}\n",
    )


def _handoff_for_command(
    root: Path,
    command: str,
    result: str = "passed",
    extra: str = "",
    *,
    evidence_root: Path | None = None,
) -> Path:
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {plan: plan-001, task: task-004}\n"
        "result: {state: completed}\n"
        "task_fit_check: {task: task-004, result: clean}\n"
        "validation:\n"
        "  commands:\n"
        f"    - {{command: {json.dumps(command)}, result: {result}}}\n"
        f"{evidence_blocks(evidence_root or root)}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n"
        f"{extra}",
        encoding="utf-8",
    )
    return handoff


def test_completed_without_harness_provenance_fails_closed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _set_process_validation(task, PASSING_PROCESS)
    handoff = _handoff_for_command(root, PASSING_PROCESS)
    brief = _compiled_brief(root, task)

    with pytest.raises(SystemExit, match="harness|binding|provenance"):
        _validate_observed(_read_handoff(handoff), brief)


def test_nonzero_process_fails_unless_acceptable_results_include_failed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_process_validation(task, FAILING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, FAILING_PROCESS, result="failed")

    with pytest.raises(SystemExit, match="failed|passed|acceptable"):
        _validate_observed(_read_handoff(handoff), brief)

    task.write_text(
        task.read_text(encoding="utf-8").replace(
            f"command: {json.dumps(FAILING_PROCESS)}, proves: TEST-004, expected: passed",
            f"command: {json.dumps(FAILING_PROCESS)}, proves: TEST-004, expected: passed, acceptable_results: [failed]",
        ),
        encoding="utf-8",
    )
    brief = _compiled_brief(root, task)
    validated = _validate_observed(_read_handoff(handoff), brief)
    assert validated["result_state"] == "completed"

    passed_label = _handoff_for_command(root, FAILING_PROCESS, result="passed")
    with pytest.raises(SystemExit, match="passed|failed|observed"):
        _validate_observed(_read_handoff(passed_label), brief)


def test_expected_skipped_observes_skipped_without_running_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {json.dumps(FAILING_PROCESS)}, proves: TEST-004, expected: skipped}}\n",
    )
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    calls = _capture_subprocess_after_setup(monkeypatch)
    handoff = _handoff_for_command(root, FAILING_PROCESS, result="skipped")

    validated = _validate_observed(_read_handoff(handoff), brief)

    assert validated["result_state"] == "completed"
    assert not any(FAILING_PROCESS in call for call in calls)


def test_named_inspection_does_not_use_executor_exit_code(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    digest = _write_scope_digest(root)
    _set_task_validation(
        task,
        "validation:\n"
        "  - kind: inspection\n"
        "    command: inspect-write-scope\n"
        "    mechanism: named-harness-file-digest\n"
        f"    digest: {digest}\n"
        "    proves: TEST-004\n"
        "    expected: passed\n",
    )
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, "inspect-write-scope")
    payload = _read_handoff(handoff)
    payload["validation"] = {
        "commands": [
            {
                "command": "inspect-write-scope",
                "result": "passed",
                "exit_code": 0,
                "mechanism": "named-harness-file-digest",
            }
        ]
    }

    validated = _validate_observed(payload, brief)

    assert validated["result_state"] == "completed"
    assert "exit_code" not in str(validated.get("observed_validation") or {})


def test_wrong_worktree_cannot_grant_completed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    ew = _execution_workspace()
    runtime = tmp_path / "ew-runtime"
    other = ew.prepare_worktree(
        root,
        workspace_id="ws1",
        execution_id="other-exec",
        repository_id="repo1",
        branch="codex/other-exec",
        created_for="other-task",
        runtime_root=runtime,
    )
    other_root = Path(str(other["execution_workspace_state"]["path"]))
    _bind_task_execution(
        root,
        brief,
        execution_root=other_root,
        runtime_root=runtime,
        execution_id="other-exec",
    )
    (other_root / "unauthorized-other.py").write_text("leak\n", encoding="utf-8")
    handoff = _handoff_for_command(root, PASSING_PROCESS, evidence_root=other_root)

    with pytest.raises(SystemExit, match="write scope|unauthorized|delta"):
        _validate_observed(_read_handoff(handoff), brief)


def test_control_root_observation_cannot_authorize_isolated_worktree(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    marker_command = "python3 -c \"import pathlib,sys; sys.exit(0 if pathlib.Path('bound-marker.txt').exists() else 2)\""
    # quoted below via json.dumps in helpers
    _set_process_validation(task, marker_command)
    brief = _compiled_brief(root, task)
    (root / "bound-marker.txt").write_text("control-only\n", encoding="utf-8")
    ew = _execution_workspace()
    runtime = tmp_path / "ew-runtime"
    isolated = ew.prepare_worktree(
        root,
        workspace_id="ws1",
        execution_id="iso-exec",
        repository_id="repo1",
        branch="codex/iso-exec",
        created_for="task-004",
        runtime_root=runtime,
    )
    isolated_root = Path(str(isolated["execution_workspace_state"]["path"]))
    _bind_task_execution(
        root,
        brief,
        execution_root=isolated_root,
        runtime_root=runtime,
        execution_id="iso-exec",
    )
    handoff = _handoff_for_command(root, marker_command)

    with pytest.raises(SystemExit, match="failed|passed|observed|binding"):
        _validate_observed(_read_handoff(handoff), brief)


def test_in_batch_mutation_is_validation_blocked(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    mutating = (
        "python3 -c \"from pathlib import Path; "
        f"p=Path('{WRITE_SCOPE_FILE}'); p.parent.mkdir(parents=True, exist_ok=True); "
        "p.write_text(p.read_text()+'# mutated\\n' if p.exists() else '# mutated\\n')\""
    )
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {json.dumps(PASSING_PROCESS)}, proves: TEST-004, expected: passed}}\n"
        f"  - {{kind: process, command: {json.dumps(mutating)}, proves: TEST-004, expected: passed}}\n",
    )
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        "id: handoff-task-004\n"
        "type: executor-result\n"
        "related: {plan: plan-001, task: task-004}\n"
        "result: {state: completed}\n"
        "task_fit_check: {task: task-004, result: clean}\n"
        "validation:\n"
        "  commands:\n"
        f"    - {{command: {json.dumps(PASSING_PROCESS)}, result: passed}}\n"
        f"    - {{command: {json.dumps(mutating)}, result: passed}}\n"
        f"{evidence_blocks(root)}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="validation-blocked"):
        _validate_observed(_read_handoff(handoff), brief)


def test_omitted_unauthorized_path_fails_closed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    (root / "src/unauthorized.py").parent.mkdir(parents=True, exist_ok=True)
    (root / "src/unauthorized.py").write_text("leak\n", encoding="utf-8")
    handoff = _handoff_for_command(root, PASSING_PROCESS)

    with pytest.raises(SystemExit, match="write scope|unauthorized|delta"):
        _validate_observed(_read_handoff(handoff), brief)

    reported = _handoff_for_command(
        root,
        PASSING_PROCESS,
        extra="changes:\n  files:\n    - {path: src/unauthorized.py, action: created}\n",
    )
    with pytest.raises(SystemExit, match="write scope|unauthorized|delta"):
        _validate_observed(_read_handoff(reported), brief)


def test_further_edit_to_baseline_dirty_path_is_task_caused(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    scoped = _ensure_source_file(root)
    outsider = root / "src/preexisting.py"
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_text("OLD\n", encoding="utf-8")
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    outsider.write_text("NEW\n", encoding="utf-8")
    scoped.write_text("def compile_task():\n    return 'new'\n", encoding="utf-8")
    handoff = _handoff_for_command(
        root,
        PASSING_PROCESS,
        extra=f"changes:\n  files:\n    - {{path: {WRITE_SCOPE_FILE}, action: modified}}\n",
    )

    with pytest.raises(SystemExit, match="write scope|unauthorized|delta"):
        _validate_observed(_read_handoff(handoff), brief)


def test_committed_delta_is_checked_when_worktree_is_clean(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    leaked = root / "src/committed_leak.py"
    leaked.parent.mkdir(parents=True, exist_ok=True)
    leaked.write_text("committed-leak\n", encoding="utf-8")
    git(root, "add", "src/committed_leak.py")
    git(root, "commit", "-qm", "task commit")
    handoff = _handoff_for_command(root, PASSING_PROCESS)

    with pytest.raises(SystemExit, match="write scope|unauthorized|delta"):
        _validate_observed(_read_handoff(handoff), brief)


def test_overlapping_mutating_siblings_in_shared_worktree_are_blocked(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    sibling = root / ".work-bundle/orchestration/plan/active/plan-001/phase-001/task-005.md"
    sibling.write_text(task.read_text(encoding="utf-8").replace("id: task-004\n", "id: task-005\n"), encoding="utf-8")
    _set_process_validation(task, PASSING_PROCESS)
    _set_process_validation(sibling, PASSING_PROCESS)
    brief_a = _compiled_brief(root, task)
    brief_b = _compiled_brief(root, sibling)
    _bind_task_execution(root, brief_a, execution_id="exec-a")

    with pytest.raises(SystemExit, match="isolate|serialize|overlapping"):
        _bind_task_execution(root, brief_b, execution_id="exec-b")


def test_later_brief_rebuild_does_not_recapture_task_baseline(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    scoped = _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    binding = _bind_task_execution(root, brief)
    original_head = binding["baseline"]["head"]
    scoped.write_text("def compile_task():\n    return 'after-baseline'\n", encoding="utf-8")
    git(root, "add", WRITE_SCOPE_FILE)
    git(root, "commit", "-qm", "after baseline")
    build_task_brief(args(root, task))
    rebuilt = execution_context.capture_task_baseline_once(
        execution_context.load_task_execution_binding(root, "plan-001", "task-004")
    )

    assert rebuilt["baseline"]["head"] == original_head
    assert rebuilt["baseline"]["head"] != git(root, "rev-parse", "HEAD")

    handoff = _handoff_for_command(
        root,
        PASSING_PROCESS,
        extra=f"changes:\n  files:\n    - {{path: {WRITE_SCOPE_FILE}, action: modified}}\n",
    )
    validated = _validate_observed(_read_handoff(handoff), brief)
    assert validated["result_state"] == "completed"


def test_set_plan_status_completed_observes_bound_worktree(tmp_path: Path) -> None:
    from plans import cmd_set_plan_status

    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(
        root,
        PASSING_PROCESS,
        extra=f"changes:\n  files:\n    - {{path: {WRITE_SCOPE_FILE}, action: modified}}\n",
    )

    cmd_set_plan_status(
        argparse.Namespace(
            project_root=str(root),
            id="task-004",
            status="Completed",
            kind="task",
            handoff=str(handoff),
            workspace_id=None,
            execution_id=None,
            repository_id=None,
            execution_runtime_root=None,
        )
    )
    data, _ = execution_context._read_structured(task)
    assert data["status"] == "Completed"


def test_executor_minted_harness_receipt_fails_closed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, PASSING_PROCESS)
    payload = _read_handoff(handoff)
    payload["harness_receipt"] = {"result": "passed", "exit_code": 0}

    with pytest.raises(SystemExit, match="harness_receipt|receipt"):
        _validate_observed(payload, brief)


def test_execution_workspace_module_loads_with_orchestration_only_sys_path() -> None:
    script = r"""
import sys
from pathlib import Path

orch = Path("scripts/orchestration").resolve()
work_bundle = Path("scripts/work-bundle").resolve()
sys.path.insert(0, str(orch))
sys.path[:] = [
    item for item in sys.path
    if Path(item).resolve() != work_bundle
]
import execution_context
execution_context._EW_MODULE = None
module = execution_context._execution_workspace_module()
assert callable(getattr(module, "load_state", None))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_structured_validation_without_kind_fails_closed_without_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, task = workspace(tmp_path)
    calls = _capture_subprocess_after_setup(monkeypatch)
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{command: {json.dumps(UNTYPED_LEGACY_COMMAND)}, proves: TEST-004, expected: passed}}\n",
    )

    with pytest.raises(SystemExit, match="kind|legacy-untyped"):
        build_task_brief(args(root, task))

    assert not any(UNTYPED_LEGACY_COMMAND in call for call in calls)


def test_test_id_fallback_is_not_executable_terminal_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, task = workspace(tmp_path)
    calls = _capture_subprocess_after_setup(monkeypatch)
    _set_task_validation(task, "")

    with pytest.raises(SystemExit, match="kind|legacy-untyped|TEST"):
        build_task_brief(args(root, task))

    assert not any("Focused pytest" in call for call in calls)
    assert not any(UNTYPED_LEGACY_COMMAND in call for call in calls)


def test_disjoint_mutating_siblings_in_shared_worktree_are_blocked(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    sibling = root / ".work-bundle/orchestration/plan/active/plan-001/phase-001/task-005.md"
    sibling.write_text(
        task.read_text(encoding="utf-8")
        .replace("id: task-004\n", "id: task-005\n")
        .replace(
            "write: [scripts/orchestration/execution_context.py]",
            "write: [tests/test_compiler.py]",
        ),
        encoding="utf-8",
    )
    _set_process_validation(task, PASSING_PROCESS)
    _set_process_validation(sibling, PASSING_PROCESS)
    brief_a = _compiled_brief(root, task)
    brief_b = _compiled_brief(root, sibling)
    _bind_task_execution(root, brief_a, execution_id="exec-a")

    with pytest.raises(SystemExit, match="isolate|serialize"):
        _bind_task_execution(root, brief_b, execution_id="exec-b")


def test_index_only_post_baseline_mutation_is_task_caused(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    outsider = root / "src/preexisting.py"
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_text("A\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    outsider.write_text("B\n", encoding="utf-8")
    git(root, "add", "src/preexisting.py")
    outsider.write_text("C\n", encoding="utf-8")
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    outsider.write_text("D\n", encoding="utf-8")
    git(root, "add", "src/preexisting.py")
    outsider.write_text("C\n", encoding="utf-8")
    handoff = _handoff_for_command(root, PASSING_PROCESS)

    with pytest.raises(SystemExit, match="write scope|unauthorized|delta"):
        _validate_observed(_read_handoff(handoff), brief)


def test_executor_handoff_cannot_supply_baseline(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_process_validation(task, PASSING_PROCESS)
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, PASSING_PROCESS)
    payload = _read_handoff(handoff)
    payload["baseline"] = {"head": "0" * 40}

    with pytest.raises(SystemExit, match="forbidden field baseline|baseline"):
        _validate_observed(payload, brief)


def test_named_inspection_without_digest_fails_closed(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_task_validation(
        task,
        "validation:\n"
        "  - kind: inspection\n"
        "    command: inspect-write-scope\n"
        "    mechanism: named-harness-file-digest\n"
        "    proves: TEST-004\n"
        "    expected: passed\n",
    )
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, "inspect-write-scope")
    payload = _read_handoff(handoff)
    payload["validation"] = {
        "commands": [{"command": "inspect-write-scope", "result": "passed", "mechanism": "named-harness-file-digest"}]
    }

    with pytest.raises(SystemExit, match="digest|falsif|inspection"):
        _validate_observed(payload, brief)


def test_named_inspection_wrong_digest_fails(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    _ensure_source_file(root)
    _set_task_validation(
        task,
        "validation:\n"
        "  - kind: inspection\n"
        "    command: inspect-write-scope\n"
        "    mechanism: named-harness-file-digest\n"
        f"    digest: {'0' * 64}\n"
        "    proves: TEST-004\n"
        "    expected: passed\n",
    )
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, "inspect-write-scope")
    payload = _read_handoff(handoff)
    payload["validation"] = {
        "commands": [{"command": "inspect-write-scope", "result": "passed", "mechanism": "named-harness-file-digest"}]
    }

    with pytest.raises(SystemExit, match="digest|failed|inspection"):
        _validate_observed(payload, brief)
