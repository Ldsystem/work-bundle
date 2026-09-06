from __future__ import annotations

import builtins
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
WORK_BUNDLE = REPO_ROOT / "scripts" / "work-bundle"
for path in (WORK_BUNDLE, ORCHESTRATION):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import execution_context  # noqa: E402
import review_runtime  # noqa: E402
from stage_events import StageEventError, validate_stage_event  # noqa: E402
from test_orchestration_execution_context import (  # noqa: E402
    _bind_task_execution,
    _compiled_brief,
    _ensure_source_file,
    args,
    build_review_package,
    build_task_brief,
    git,
    workspace,
)
from test_stage_events import event  # noqa: E402


def _document(root: Path, task: Path) -> dict:
    return execution_context._read_structured(build_task_brief(args(root, task)))[0]


def _delegation_evidence() -> dict[str, object]:
    return {
        "delegated": True,
        "owner_kind": "subagent",
        "agent_id": "ctx-fixture-agent",
        "run_id": "ctx-fixture-run",
        "mechanism": "host-native",
    }


def _without_terminal_evidence(brief: dict[str, object], reason: str) -> dict[str, object]:
    projected = deepcopy(brief)
    projected["validation"] = []
    projected["evidence_capability"] = {
        "result": "no_validation_bearing_obligation",
        "reason": reason,
        "invariants": [],
    }
    projected["evidence_applicability"] = {
        kind: {"required": False, "reasons": []}
        for kind in ("metadata", "repository", "codegraph")
    }
    return projected


def test_ctx_01_unrelated_runtime_history_does_not_inflate_unchanged_task_brief(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    first = build_task_brief(args(root, task)).read_bytes()
    history = root / ".work-bundle/runtime/history/unrelated.jsonl"
    history.parent.mkdir(parents=True)
    history.write_text("{\"provenance\":\"x\"}\n" * 50_000, encoding="utf-8")
    (history.parent / "accepted-handoffs.json").write_text("[]\n", encoding="utf-8")

    second = build_task_brief(args(root, task)).read_bytes()

    assert second == first


def test_ctx_01_repair_package_uses_frontier_without_reacquiring_review_history(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "acceptance_review:\n  required: false\n",
            "acceptance_review:\n  required: true\n",
        ),
        encoding="utf-8",
    )
    scoped = _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "reviewed")
    base = git(root, "rev-parse", "HEAD")
    base_tree = git(root, "rev-parse", "HEAD^{tree}")
    brief = _compiled_brief(root, task)
    _bind_task_execution(root, brief)
    scoped.write_text("def compile_task():\n    return 'repaired'\n", encoding="utf-8")
    git(root, "add", str(scoped.relative_to(root)))
    git(root, "commit", "-qm", "repaired")
    head = git(root, "rev-parse", "HEAD")
    head_tree = git(root, "rev-parse", "HEAD^{tree}")
    identity = lambda tree, digest: {
        "artifact_id": "task-004", "revision": "rev-1", "sha256": digest, "source_tree": tree
    }
    handoff = {
        "id": "handoff-task-004",
        "type": "executor-result",
        "related": {"plan": "plan-001", "task": "task-004"},
        "result": {"state": "partial"},
        "task_fit_check": {"task": "task-004", "result": "repaired"},
        "acceptance_review": {
            "required": True,
            "verdict": "pending",
            "review_mode": "repair",
            "repair_frontier": {
                "prior_review_id": "review-prior",
                "blocking_finding_ids": ["RF-FINDING-1"],
                "previous_reviewed_identity": identity(base_tree, execution_context.semantic_digest("old")),
                "repaired_identity": identity(head_tree, execution_context.semantic_digest("new")),
                "affected_boundaries": ["compile_task"],
                "frozen_evidence_reference": execution_context.semantic_digest("frozen"),
            },
        },
        "changes": {"files": [{"path": "scripts/orchestration/execution_context.py", "action": "modified"}]},
        "repository": [{
            "root": str(root.resolve()), "target_kind": "git-backed",
            "preflight_kind": "git-clean-worktree", "baseline": "initial", "status": "clean",
        }],
        "codegraph": [{"root": str(root.resolve()), "applicable": False, "up_to_date": False, "reason": "no-index"}],
        "knowledge_disposition": {"action": "none", "reason": "No stable authority changed.", "affected_authority": []},
        "previous_review_history": "MUST-NOT-BE-PROJECTED",
    }
    handoff_path = root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text("\n".join(execution_context._dump_yaml(handoff)) + "\n", encoding="utf-8")

    package = build_review_package(
        args(root, task, handoff=str(handoff_path), base=base, head=head)
    ).read_text(encoding="utf-8")

    assert "Review mode: repair" in package
    assert "RF-FINDING-1" in package
    assert execution_context.semantic_digest("frozen") in package
    assert "MUST-NOT-BE-PROJECTED" not in package
    assert f"Base: {base}" in package and f"Head: {head}" in package


def test_ctx_02_semantic_authority_is_retained_once_and_referenced_by_id(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    document = _document(root, task)
    brief = document["task_brief"]
    rendered = build_task_brief(args(root, task)).read_text(encoding="utf-8")

    assert brief["semantic_authority"]["records"]["REQ-003"]["canonical_field"] == "requirements"
    assert brief["semantic_authority"]["records"]["API-002"]["canonical_field"] == "interface_semantics"
    assert brief["interfaces"] == {"consumes": ["API-002"], "produces": ["API-002"]}
    assert brief["validation"][0]["proves"] == "TEST-004"
    for meaning in (
        "Retry exactly three times before returning failure.",
        "Never write outside the assigned files.",
        "`compile_task(task: Path) -> dict[str, object]`",
        "Focused pytest exits with status 0.",
    ):
        assert rendered.count(meaning) == 1


def test_ctx_03_executor_capability_projection_contains_only_allocated_capabilities(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    brief = _document(root, task)["task_brief"]

    assert brief["capability_projection"] == {
        "executor": {"capability": "mechanical", "reason": "task executor_profile allocation"},
        "rules": [{"id": "scoped-rule", "reason": "Keep the executor packet bounded."}],
        "skills": [{"id": "dev-test-driven-development", "reason": "task methodology allocation"}],
        "traversal": "runtime_only",
    }
    assert "parent-rule" not in json.dumps(brief)


def test_ctx_04_success_evidence_projects_compact_receipt_not_history_or_stdout() -> None:
    projected = execution_context.project_validation_evidence(
        [{"id": "VAL-001", "command": "pytest -q", "result": "passed", "stdout": "large output", "history": [1, 2]}],
        evidence_capability={
            "invariants": [{"boundary": "component", "freshness": "current_task_batch", "evidence_ids": ["VAL-001"]}]
        },
        observed=[{"id": "VAL-001", "observation_id": "observation-001", "result": "passed"}],
    )

    assert projected == [{
        "id": "VAL-001",
        "digest": execution_context.semantic_digest({"command": "pytest -q", "result": "passed"}),
        "result": "passed",
        "boundary": "component",
        "freshness": "current_task_batch",
        "invalidation_receipt": "observation-001",
        "expansion_reason": None,
    }]
    assert "stdout" not in json.dumps(projected)
    assert "history" not in json.dumps(projected)


def test_ctx_05_failed_evidence_expands_only_with_allowed_reason() -> None:
    item = {"id": "VAL-001", "command": "pytest -q", "result": "failed", "stderr": "assertion failed"}
    projected = execution_context.project_validation_evidence(
        [item], evidence_capability={"invariants": []}, expansion_reason="failed_validation"
    )

    assert projected[0]["expansion_reason"] == "failed_validation"
    assert projected[0]["details"] == item
    with pytest.raises(SystemExit, match="expansion_reason"):
        execution_context.project_validation_evidence(
            [item], evidence_capability={"invariants": []}, expansion_reason="whole_history"
        )


def test_ctx_06_no_retrieval_escape_hatch_and_context_metrics_use_existing_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _, task = workspace(tmp_path)
    document = _document(root, task)
    brief = document["task_brief"]
    metrics = document["compiled_context_metrics"]

    assert brief["runtime_context"] == {
        "authority": "compiled",
        "histories": "runtime_lazy",
        "executor_retrieval": "forbidden",
    }
    assert all(isinstance(value, int) and value >= 0 for key, value in metrics.items() if key != "expansion_reason")
    assert metrics["expansion_reason"] is None
    assert "hard_limit" not in json.dumps(document)

    compiled_packet = _without_terminal_evidence(
        brief, "CTX-06 executes only from its already-compiled packet."
    )
    handoff = {
        "type": "executor-result",
        "related": {"plan": brief["plan_id"], "task": brief["task_id"]},
        "result": {"state": "completed"},
        "task_fit_check": {"task": brief["task_id"], "result": "clean"},
        "delegation_evidence": _delegation_evidence(),
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }
    original_open = builtins.open
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes

    def retrieval_is_denied(file: object) -> bool:
        candidate = str(file)
        return (
            ".work-bundle/knowledge" in candidate
            or ".work-bundle/orchestration" in candidate
        )

    def deny_runtime_retrieval(file: object, *args: object, **kwargs: object):
        if retrieval_is_denied(file):
            raise AssertionError(f"executor retrieval attempted: {file}")
        return original_open(file, *args, **kwargs)

    def deny_path_text(file: Path, *args: object, **kwargs: object) -> str:
        if retrieval_is_denied(file):
            raise AssertionError(f"executor retrieval attempted: {file}")
        return original_read_text(file, *args, **kwargs)

    def deny_path_bytes(file: Path) -> bytes:
        if retrieval_is_denied(file):
            raise AssertionError(f"executor retrieval attempted: {file}")
        return original_read_bytes(file)

    monkeypatch.setattr(builtins, "open", deny_runtime_retrieval)
    monkeypatch.setattr(Path, "read_text", deny_path_text)
    monkeypatch.setattr(Path, "read_bytes", deny_path_bytes)
    accepted = execution_context.validate_executor_result_for_task(handoff, compiled_packet)
    assert accepted["result_state"] == "completed"
    assert accepted["task_ownership"]["agent_id"] == "ctx-fixture-agent"

    payload = event()
    payload["compiled_context_metrics"] = metrics
    assert validate_stage_event(payload).compiled_context_metrics == metrics
    invalid = deepcopy(payload)
    invalid["compiled_context_metrics"]["expansion_reason"] = "whole_history"
    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_CONTEXT_METRICS_INVALID"):
        validate_stage_event(invalid)


def test_completed_task_acceptance_requires_subagent_delegation_evidence(tmp_path: Path) -> None:
    root, _, task = workspace(tmp_path)
    brief = _without_terminal_evidence(
        _document(root, task)["task_brief"], "Ownership-only acceptance fixture."
    )
    handoff = {
        "type": "executor-result",
        "related": {"plan": brief["plan_id"], "task": brief["task_id"]},
        "result": {"state": "completed"},
        "task_fit_check": {"task": brief["task_id"], "result": "clean"},
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }

    with pytest.raises(SystemExit, match="workspace-blocked.*subagent ownership"):
        execution_context.validate_executor_result_for_task(handoff, brief)


def test_completed_task_acceptance_rejects_controller_task_scope_mutation(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    brief = _without_terminal_evidence(
        _document(root, task)["task_brief"], "Ownership-only acceptance fixture."
    )
    handoff = {
        "type": "executor-result",
        "related": {"plan": brief["plan_id"], "task": brief["task_id"]},
        "result": {"state": "completed"},
        "task_fit_check": {"task": brief["task_id"], "result": "clean"},
        "delegation_evidence": _delegation_evidence(),
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }

    with pytest.raises(SystemExit, match="review-blocked.*controller mutated"):
        execution_context.validate_executor_result_for_task(
            handoff,
            brief,
            mutation_events=[{
                "actor_kind": "controller",
                "paths": [brief["files"]["write"][0]],
            }],
        )
    assert "mutation_events" not in handoff
    durable_history = {**handoff, "mutation_events": []}
    with pytest.raises(SystemExit, match="forbidden field mutation_events"):
        execution_context.validate_executor_result_for_task(durable_history, brief)


def test_repair_acceptance_requires_exact_runtime_owner_and_continuity(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    scoped = _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline")
    brief = _without_terminal_evidence(
        _document(root, task)["task_brief"], "Repair ownership fixture."
    )
    binding = _bind_task_execution(root, brief)
    scoped.write_text("def compile_task():\n    return 'repair'\n", encoding="utf-8")
    frontier = {
        "prior_review_id": "review-prior",
        "frozen_evidence_reference": execution_context.semantic_digest("evidence"),
    }
    handoff = {
        "type": "executor-result",
        "related": {"plan": brief["plan_id"], "task": brief["task_id"]},
        "result": {"state": "completed"},
        "task_fit_check": {"task": brief["task_id"], "result": "repaired"},
        "delegation_evidence": _delegation_evidence(),
        "acceptance_review": {"required": False, "repair_frontier": frontier},
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }
    continuity = {
        brief["task_id"]: {
            "binding_id": binding["ownership"]["binding_id"],
            "baseline_identity": execution_context.semantic_digest(binding["baseline"]),
            "evidence_identity": frontier["frozen_evidence_reference"],
            "previous_review_identity": frontier["prior_review_id"],
        }
    }
    prior = {brief["task_id"]: _delegation_evidence()}

    accepted = execution_context.validate_executor_result_for_task(
        handoff,
        brief,
        prior_ownership=prior,
        repair_continuity=continuity,
    )
    assert accepted["task_ownership"]["agent_id"] == "ctx-fixture-agent"

    replacement = deepcopy(handoff)
    replacement["delegation_evidence"] = {
        **_delegation_evidence(),
        "agent_id": "unrelated-agent",
        "run_id": "unrelated-run",
    }
    with pytest.raises(SystemExit, match="replacement is not authorized"):
        execution_context.validate_executor_result_for_task(
            replacement,
            brief,
            prior_ownership=prior,
            repair_continuity=continuity,
        )
    execution_context.validate_executor_result_for_task(
        replacement,
        brief,
        prior_ownership=prior,
        repair_continuity=continuity,
        authorized_replacements={brief["task_id"]},
    )

    stale = deepcopy(continuity)
    stale[brief["task_id"]]["baseline_identity"] = "stale"
    with pytest.raises(SystemExit, match="continuity identities do not match"):
        execution_context.validate_executor_result_for_task(
            handoff,
            brief,
            prior_ownership=prior,
            repair_continuity=stale,
        )


def test_accepted_dependency_deltas_use_exact_handoff_and_observed_checkpoint(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "phase_id: phase-001\n",
            "phase_id: phase-001\ndepends_on: [task-dependency]\n",
        ),
        encoding="utf-8",
    )
    scoped = _ensure_source_file(root)
    dependency = root / "references/assets/orchestration/workflow.md"
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.write_text("before\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline")
    baseline = git(root, "rev-parse", "HEAD")
    baseline_tree = git(root, "rev-parse", "HEAD^{tree}")

    brief = _document(root, task)["task_brief"]
    _bind_task_execution(root, brief)

    dependency.write_text("accepted dependency\n", encoding="utf-8")
    git(root, "add", str(dependency.relative_to(root)))
    git(root, "commit", "-qm", "accepted dependency")
    checkpoint = git(root, "rev-parse", "HEAD")
    checkpoint_tree = git(root, "rev-parse", "HEAD^{tree}")
    scoped.write_text("def compile_task():\n    return 'task repair'\n", encoding="utf-8")
    git(root, "add", str(scoped.relative_to(root)))
    git(root, "commit", "-qm", "task repair")

    identity = lambda commit, tree: {
        "artifact_id": "task-dependency",
        "revision": commit,
        "sha256": execution_context.semantic_digest({"commit": commit, "tree": tree}),
        "source_tree": tree,
    }
    dependency_handoff = {
        "id": "handoff-accepted-dependency",
        "type": "executor-result",
        "related": {"plan": brief["plan_id"], "task": "task-dependency"},
        "result": {"state": "completed"},
        "acceptance_review": {
            "required": True,
            "verdict": "accept",
            "review_mode": "repair",
            "target_identity": identity(checkpoint, checkpoint_tree),
            "repair_frontier": {
                "previous_reviewed_identity": identity(baseline, baseline_tree),
                "repaired_identity": identity(checkpoint, checkpoint_tree),
            },
        },
    }
    accepted_path = (
        root
        / ".work-bundle/orchestration/handoff/executor/active/handoff-accepted-dependency.yaml"
    )
    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    accepted_path.write_text(
        "\n".join(execution_context._dump_yaml(dependency_handoff)) + "\n",
        encoding="utf-8",
    )
    descriptor = {
        "task_id": "task-dependency",
        "handoff_id": "handoff-accepted-dependency",
        "handoff_sha256": hashlib.sha256(accepted_path.read_bytes()).hexdigest(),
        "integrated_base": baseline,
        "integrated_head": checkpoint,
    }

    current = _without_terminal_evidence(brief, "Dependency attribution fixture.")
    current["evidence_applicability"] = {
        "metadata": {"required": False, "reasons": []},
        "repository": {"required": True, "reasons": ["accepted dependency delta"]},
        "codegraph": {"required": False, "reasons": []},
    }
    handoff = {
        "type": "executor-result",
        "related": {"plan": brief["plan_id"], "task": brief["task_id"]},
        "result": {"state": "completed"},
        "task_fit_check": {"task": brief["task_id"], "result": "clean"},
        "delegation_evidence": _delegation_evidence(),
        "repository": [{
            "root": str(root.resolve()),
            "target_kind": "git-backed",
            "preflight_kind": "git-clean-worktree",
            "baseline": "initial",
            "status": "clean",
        }],
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }

    with pytest.raises(SystemExit, match="workflow.md"):
        execution_context.validate_executor_result_for_task(handoff, current, observe=True)
    accepted = execution_context.validate_executor_result_for_task(
        handoff, current, observe=True, accepted_dependency_deltas=[descriptor]
    )
    assert accepted["result_state"] == "completed"

    cli_handoff = deepcopy(handoff)
    cli_handoff["result"]["state"] = "partial"
    cli_handoff["changes"] = {
        "files": [
            {
                "path": "scripts/orchestration/execution_context.py",
                "action": "modified",
            }
        ]
    }
    cli_handoff["codegraph"] = [
        {
            "root": str(root.resolve()),
            "applicable": False,
            "up_to_date": False,
            "reason": "no-index",
        }
    ]
    cli_handoff_path = (
        root / ".work-bundle/orchestration/handoff/executor/active/handoff-task-004.yaml"
    )
    cli_handoff_path.write_text(
        "\n".join(execution_context._dump_yaml(cli_handoff)) + "\n", encoding="utf-8"
    )
    cli = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/orch.py"),
            "build-review-package",
            "--project-root",
            str(root),
            "--task",
            str(task),
            "--handoff",
            str(cli_handoff_path),
            "--base",
            baseline,
            "--head",
            git(root, "rev-parse", "HEAD"),
            "--accepted-dependency-deltas",
            json.dumps([descriptor]),
        ],
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0, cli.stderr
    assert "review-package.md" in cli.stdout

    accepted_bytes = accepted_path.read_bytes()
    wrong_plan_handoff = deepcopy(dependency_handoff)
    wrong_plan_handoff["related"]["plan"] = "plan-WRONG"
    accepted_path.write_text(
        "\n".join(execution_context._dump_yaml(wrong_plan_handoff)) + "\n",
        encoding="utf-8",
    )
    wrong_plan = {
        **descriptor,
        "handoff_sha256": hashlib.sha256(accepted_path.read_bytes()).hexdigest(),
    }
    with pytest.raises(SystemExit, match="plan"):
        execution_context.validate_executor_result_for_task(
            handoff, current, observe=True, accepted_dependency_deltas=[wrong_plan]
        )
    accepted_path.write_bytes(accepted_bytes)

    stale = {**descriptor, "handoff_sha256": "0" * 64}
    with pytest.raises(SystemExit, match="handoff identity is stale"):
        execution_context.validate_executor_result_for_task(
            handoff, current, observe=True, accepted_dependency_deltas=[stale]
        )
    mismatched = {**descriptor, "integrated_head": git(root, "rev-parse", "HEAD")}
    with pytest.raises(SystemExit, match="checkpoint is mismatched"):
        execution_context.validate_executor_result_for_task(
            handoff, current, observe=True, accepted_dependency_deltas=[mismatched]
        )
    unaccepted_handoff = deepcopy(dependency_handoff)
    unaccepted_handoff["acceptance_review"]["verdict"] = "pending"
    accepted_path.write_text(
        "\n".join(execution_context._dump_yaml(unaccepted_handoff)) + "\n",
        encoding="utf-8",
    )
    unaccepted = {
        **descriptor,
        "handoff_sha256": hashlib.sha256(accepted_path.read_bytes()).hexdigest(),
    }
    with pytest.raises(SystemExit, match="not an accepted repair result"):
        execution_context.validate_executor_result_for_task(
            handoff, current, observe=True, accepted_dependency_deltas=[unaccepted]
        )
    accepted_path.write_bytes(accepted_bytes)
    dependency.write_text("later task mutation\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="changed after integration"):
        execution_context.validate_executor_result_for_task(
            handoff, current, observe=True, accepted_dependency_deltas=[descriptor]
        )


def test_accepted_dependency_repair_chain_is_ordered_contiguous_and_last_wins(
    tmp_path: Path,
) -> None:
    root, _, _ = workspace(tmp_path)
    dependency_path = "references/assets/orchestration/workflow.md"
    dependency = root / dependency_path
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.write_text("version zero\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "chain baseline")
    commits = [git(root, "rev-parse", "HEAD")]
    trees = [git(root, "rev-parse", "HEAD^{tree}")]
    for number in range(1, 4):
        dependency.write_text(f"version {number}\n", encoding="utf-8")
        git(root, "add", dependency_path)
        git(root, "commit", "-qm", f"accepted dependency repair {number}")
        commits.append(git(root, "rev-parse", "HEAD"))
        trees.append(git(root, "rev-parse", "HEAD^{tree}"))
    unrelated = root / "tests/task-local.txt"
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    unrelated.write_text("dependent task change\n", encoding="utf-8")
    git(root, "add", str(unrelated.relative_to(root)))
    git(root, "commit", "-qm", "dependent task change")

    task = {
        "task_id": "dependent-task",
        "plan_id": "plan-001",
        "depends_on": ["task-dependency"],
        "workspace": {"root": str(root)},
    }
    handoff_root = root / ".work-bundle/orchestration/handoff/executor/active"
    handoff_root.mkdir(parents=True, exist_ok=True)

    def identity(index: int) -> dict[str, object]:
        return {
            "artifact_id": "task-dependency",
            "revision": commits[index],
            "sha256": execution_context.semantic_digest(
                {"commit": commits[index], "tree": trees[index]}
            ),
            "source_tree": trees[index],
        }

    handoffs: list[dict[str, object]] = []
    descriptors: list[dict[str, object]] = []
    paths: list[Path] = []
    for index in range(1, 4):
        handoff_id = f"handoff-chain-{index}"
        handoff = {
            "id": handoff_id,
            "type": "executor-result",
            "related": {"plan": "plan-001", "task": "task-dependency"},
            "result": {"state": "completed"},
            "acceptance_review": {
                "required": True,
                "verdict": "accept",
                "review_mode": "repair",
                "target_identity": identity(index),
                "repair_frontier": {
                    "previous_reviewed_identity": identity(index - 1),
                    "repaired_identity": identity(index),
                },
            },
        }
        path = handoff_root / f"{handoff_id}.yaml"
        path.write_text("\n".join(execution_context._dump_yaml(handoff)) + "\n", encoding="utf-8")
        handoffs.append(handoff)
        paths.append(path)
        descriptors.append(
            {
                "task_id": "task-dependency",
                "handoff_id": handoff_id,
                "handoff_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "integrated_base": commits[index - 1],
                "integrated_head": commits[index],
            }
        )

    assert execution_context._accepted_dependency_paths(task, root, descriptors) == {
        dependency_path
    }

    with pytest.raises(SystemExit, match="anchored|incomplete"):
        execution_context._accepted_dependency_paths(task, root, descriptors[1:])
    with pytest.raises(SystemExit, match="anchored|incomplete"):
        execution_context._accepted_dependency_paths(task, root, descriptors[-1:])

    with pytest.raises(SystemExit, match="ordered|source.*contiguous"):
        execution_context._accepted_dependency_paths(
            task, root, [descriptors[1], descriptors[0], descriptors[2]]
        )
    with pytest.raises(SystemExit, match="source.*contiguous|incomplete"):
        execution_context._accepted_dependency_paths(task, root, [descriptors[0], descriptors[2]])
    nonadjacent = deepcopy(descriptors)
    nonadjacent[1] = {**nonadjacent[1], "integrated_base": commits[0]}
    with pytest.raises(SystemExit, match="integrated.*contiguous|non-adjacent"):
        execution_context._accepted_dependency_paths(task, root, nonadjacent)
    missing = deepcopy(descriptors)
    missing[1] = {**missing[1], "handoff_id": "handoff-chain-missing"}
    with pytest.raises(SystemExit, match="missing or ambiguous"):
        execution_context._accepted_dependency_paths(task, root, missing)

    rejected = deepcopy(handoffs[1])
    rejected["acceptance_review"]["verdict"] = "pending"
    paths[1].write_text(
        "\n".join(execution_context._dump_yaml(rejected)) + "\n", encoding="utf-8"
    )
    unaccepted = deepcopy(descriptors)
    unaccepted[1] = {
        **unaccepted[1],
        "handoff_sha256": hashlib.sha256(paths[1].read_bytes()).hexdigest(),
    }
    with pytest.raises(SystemExit, match="not an accepted repair"):
        execution_context._accepted_dependency_paths(task, root, unaccepted)
    paths[1].write_text(
        "\n".join(execution_context._dump_yaml(handoffs[1])) + "\n", encoding="utf-8"
    )

    dependency.write_text("unaccepted later mutation\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="changed after integration"):
        execution_context._accepted_dependency_paths(task, root, descriptors)


def test_cumulative_accepted_result_delta_requires_complete_final_review_chain(
    tmp_path: Path,
) -> None:
    root, _, _ = workspace(tmp_path)
    dependency_path = "references/assets/orchestration/workflow.md"
    repair_path = "scripts/orchestration/dependency_repair.py"
    final_path = "tests/dependency_result.md"
    dependency = root / dependency_path
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.write_text("accepted base\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "accepted base")
    commits = [git(root, "rev-parse", "HEAD")]
    trees = [git(root, "rev-parse", "HEAD^{tree}")]
    for label, changed_path in (
        ("initial repair target", dependency_path),
        ("accepted repair", repair_path),
        ("fresh accepted result", final_path),
    ):
        changed = root / changed_path
        changed.parent.mkdir(parents=True, exist_ok=True)
        changed.write_text(label + "\n", encoding="utf-8")
        git(root, "add", changed_path)
        git(root, "commit", "-qm", label)
        commits.append(git(root, "rev-parse", "HEAD"))
        trees.append(git(root, "rev-parse", "HEAD^{tree}"))
    local = root / "tests/task-local.txt"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("dependent task\n", encoding="utf-8")
    git(root, "add", str(local.relative_to(root)))
    git(root, "commit", "-qm", "dependent task")

    def identity(index: int) -> dict[str, object]:
        return {
            "artifact_id": "task-dependency",
            "revision": commits[index],
            "sha256": execution_context.semantic_digest(
                {"commit": commits[index], "tree": trees[index]}
            ),
            "source_tree": trees[index],
        }

    def reviewer(agent: str) -> dict[str, object]:
        return {
            "agent_id": agent,
            "capability": "judgment",
            "authorship": "none",
            "repair_participation": "none",
            "decision_participation": "none",
            "deliberation_participation": "none",
            "context_origin": "direct_source",
        }

    def review(review_id: str, index: int, verdict: str) -> dict[str, object]:
        return {
            "required": True,
            "reviewer_independent": True,
            "verdict": verdict,
            "reviewed_head": commits[index],
            "review_id": review_id,
            "review_mode": "initial",
            "review_target_kind": "task",
            "repair_frontier": None,
            "review_reset": None,
            "target_identity": identity(index),
            "reviewer": reviewer("reviewer-" + review_id),
            "evidence": {
                "mode": "direct",
                "capabilities": ["source inspection"],
                "unavailable_evidence": [],
                "commands": [],
                "artifacts": [],
            },
            "findings": [],
            "started_at": f"2026-09-06T00:0{index}:00Z",
            "completed_at": f"2026-09-06T00:0{index}:30Z",
            "staleness": {"is_stale": False, "reason": None, "supersedes": None},
        }

    base_review = review("review-base", 0, "accept")
    initial_repair = review("review-initial-repair", 1, "repair")
    initial_repair["review_reset"] = {
        "prior_review_id": "review-base",
        "reason_class": "validation_allocation",
        "reason": "Validation authority changed.",
    }
    initial_repair["previous_review"] = base_review
    initial_repair["findings"] = [{
        "finding_id": "CHAIN-FINDING",
        "stage": "implementation",
        "class": "implementation_defect",
        "severity": "blocking",
        "first_broken_artifact": "implementation",
        "obligation_basis": "accepted_requirement",
        "evidence": [{
            "kind": "test", "locator": "CHAIN", "digest_or_identity": "red",
            "observation": "repair required",
        }],
        "target_identity": identity(1),
        "summary": "Repair the chain.",
        "recommended_owner": "task_owner",
        "disposition": "repair_task",
    }]
    accepted_repair = review("review-accepted-repair", 2, "accept")
    accepted_repair["review_mode"] = "repair"
    accepted_repair["repair_frontier"] = {
        "prior_review_id": "review-initial-repair",
        "blocking_finding_ids": ["CHAIN-FINDING"],
        "previous_reviewed_identity": identity(1),
        "repaired_identity": identity(2),
        "affected_boundaries": [dependency_path],
        "frozen_evidence_reference": review_runtime.review_evidence_identity(initial_repair),
    }
    accepted_repair["previous_review"] = {
        key: value for key, value in initial_repair.items() if key != "previous_review"
    }
    final_review = review("review-final", 3, "accept")
    final_review["review_reset"] = {
        "prior_review_id": "review-accepted-repair",
        "reason_class": "validation_allocation",
        "reason": "Cumulative result validation changed.",
    }
    final_review["previous_review"] = {
        key: value for key, value in accepted_repair.items() if key != "previous_review"
    }

    handoff_root = root / ".work-bundle/orchestration/handoff/executor/active"
    handoff_root.mkdir(parents=True, exist_ok=True)
    records = [
        ("handoff-base", base_review, "completed"),
        ("handoff-initial-repair", initial_repair, "partial"),
        ("handoff-accepted-repair", accepted_repair, "completed"),
        ("handoff-final", final_review, "completed"),
    ]
    references: dict[str, dict[str, str]] = {}
    for handoff_id, acceptance, state in records:
        path = handoff_root / f"{handoff_id}.yaml"
        document = {
            "id": handoff_id,
            "type": "executor-result",
            "related": {"plan": "plan-001", "task": "task-dependency"},
            "result": {"state": state},
            "acceptance_review": acceptance,
        }
        rendered = "\n".join(execution_context._dump_yaml(document)) + "\n"
        path.write_text(rendered.replace(": none\n", ': "none"\n'), encoding="utf-8")
        references[handoff_id] = {
            "handoff_id": handoff_id,
            "handoff_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    descriptor = {
        "task_id": "task-dependency",
        "accepted_result_base": references["handoff-base"],
        "review_chain": [
            references["handoff-initial-repair"],
            references["handoff-accepted-repair"],
            references["handoff-final"],
        ],
        "integrated_base": commits[0],
        "integrated_head": commits[3],
    }
    task = {
        "task_id": "dependent-task",
        "plan_id": "plan-001",
        "depends_on": ["task-dependency"],
        "workspace": {"root": str(root)},
    }

    final_handoff_path = handoff_root / "handoff-final.yaml"
    original_final_bytes = final_handoff_path.read_bytes()
    same_reviewer_document = deepcopy(document)
    same_reviewer_document["acceptance_review"]["reviewer"] = deepcopy(
        accepted_repair["reviewer"]
    )
    rendered = "\n".join(execution_context._dump_yaml(same_reviewer_document)) + "\n"
    final_handoff_path.write_text(
        rendered.replace(": none\n", ': "none"\n'), encoding="utf-8"
    )
    same_reviewer = deepcopy(descriptor)
    same_reviewer["review_chain"][-1]["handoff_sha256"] = hashlib.sha256(
        final_handoff_path.read_bytes()
    ).hexdigest()
    with pytest.raises(SystemExit, match="fresh|reviewer|independent"):
        execution_context._accepted_dependency_paths(task, root, [same_reviewer])
    final_handoff_path.write_bytes(original_final_bytes)

    assert execution_context._accepted_dependency_paths(task, root, [descriptor]) == {
        dependency_path, repair_path, final_path
    }
    missing = deepcopy(descriptor)
    missing["review_chain"] = missing["review_chain"][1:]
    with pytest.raises(SystemExit, match="chain|prior"):
        execution_context._accepted_dependency_paths(task, root, [missing])
    reordered = deepcopy(descriptor)
    reordered["review_chain"][0], reordered["review_chain"][1] = (
        reordered["review_chain"][1], reordered["review_chain"][0]
    )
    with pytest.raises(SystemExit, match="chain|prior|ordered"):
        execution_context._accepted_dependency_paths(task, root, [reordered])
    intermediate = deepcopy(descriptor)
    intermediate["review_chain"] = intermediate["review_chain"][:1]
    intermediate["integrated_head"] = commits[1]
    with pytest.raises(SystemExit, match="final|accept"):
        execution_context._accepted_dependency_paths(task, root, [intermediate])
    wrong_checkpoint = deepcopy(descriptor)
    wrong_checkpoint["integrated_head"] = commits[2]
    with pytest.raises(SystemExit, match="checkpoint|mismatched"):
        execution_context._accepted_dependency_paths(task, root, [wrong_checkpoint])
    stale_identity = deepcopy(descriptor)
    stale_identity["review_chain"][-1]["handoff_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="stale"):
        execution_context._accepted_dependency_paths(task, root, [stale_identity])

    commits.append(git(root, "rev-parse", "HEAD"))
    trees.append(git(root, "rev-parse", "HEAD^{tree}"))
    later_review = review("review-later", 4, "repair")
    later_review["review_reset"] = {
        "prior_review_id": "review-final",
        "reason_class": "validation_allocation",
        "reason": "A later accepted result superseded the terminal result.",
    }
    later_review["previous_review"] = {
        key: value for key, value in final_review.items() if key != "previous_review"
    }
    later_review["findings"] = [deepcopy(initial_repair["findings"][0])]
    later_review["findings"][0]["finding_id"] = "LATER-FINDING"
    later_review["findings"][0]["target_identity"] = identity(4)
    later_path = handoff_root / "handoff-later.yaml"
    later_document = {
        "id": "handoff-later",
        "type": "executor-result",
        "related": {"plan": "plan-001", "task": "task-dependency"},
        "result": {"state": "partial"},
        "acceptance_review": later_review,
    }
    rendered = "\n".join(execution_context._dump_yaml(later_document)) + "\n"
    later_path.write_text(rendered.replace(": none\n", ': "none"\n'), encoding="utf-8")
    with pytest.raises(SystemExit, match="terminal result is stale"):
        execution_context._accepted_dependency_paths(task, root, [descriptor])


def test_authority_recovery_receipt_is_helper_created_fresh_and_rechecked(
    tmp_path: Path,
) -> None:
    root, _, task_path = workspace(tmp_path)
    dependency_path = "references/assets/orchestration/workflow.md"
    dependency = root / dependency_path
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.write_text("original accepted baseline\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "original dependency baseline")
    baseline = git(root, "rev-parse", "HEAD")
    baseline_tree = git(root, "rev-parse", "HEAD^{tree}")

    dependent = _compiled_brief(root, task_path)
    dependency_brief = deepcopy(dependent)
    dependency_brief["task_id"] = "task-dependency"
    binding = _bind_task_execution(
        root,
        dependency_brief,
        execution_id="dependency-exec",
        write_scope=[dependency_path],
    )
    binding_path = (
        root
        / ".work-bundle/runtime/execution/plan-001/task-dependency/execution-binding.json"
    )
    binding_digest = hashlib.sha256(binding_path.read_bytes()).hexdigest()

    dependency.write_text("missing accepted result base\n", encoding="utf-8")
    git(root, "add", dependency_path)
    git(root, "commit", "-qm", "missing accepted result base")
    expected_base_head = git(root, "rev-parse", "HEAD")
    expected_base_tree = git(root, "rev-parse", "HEAD^{tree}")

    dependency.write_text("fresh whole-task accepted result\n", encoding="utf-8")
    git(root, "add", dependency_path)
    git(root, "commit", "-qm", "fresh recovered dependency result")
    recovered_head = git(root, "rev-parse", "HEAD")
    recovered_tree = git(root, "rev-parse", "HEAD^{tree}")

    def identity(commit: str, tree: str) -> dict[str, object]:
        return {
            "artifact_id": "task-dependency",
            "revision": commit,
            "sha256": execution_context.semantic_digest({"commit": commit, "tree": tree}),
            "source_tree": tree,
        }

    def reviewer(agent_id: str) -> dict[str, object]:
        return {
            "agent_id": agent_id,
            "capability": "judgment",
            "authorship": "none",
            "repair_participation": "none",
            "decision_participation": "none",
            "deliberation_participation": "none",
            "context_origin": "direct_source",
        }

    previous = {
        "required": True,
        "reviewer_independent": True,
        "verdict": "accept",
        "reviewed_head": expected_base_head,
        "review_id": "review-dependency-accepted-historical",
        "review_mode": "initial",
        "review_target_kind": "task",
        "repair_frontier": None,
        "review_reset": None,
        "target_identity": identity(expected_base_head, expected_base_tree),
        "reviewer": reviewer("historical-reviewer"),
        "evidence": {
            "mode": "direct",
            "capabilities": ["whole-task source review"],
            "unavailable_evidence": [],
            "commands": [],
            "artifacts": [],
        },
        "findings": [],
        "started_at": "2026-09-06T01:00:00Z",
        "completed_at": "2026-09-06T01:01:00Z",
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }
    recovered_review = {
        **deepcopy(previous),
        "review_id": "review-dependency-authority-recovery",
        "reviewed_head": recovered_head,
        "target_identity": identity(recovered_head, recovered_tree),
        "reviewer": reviewer("fresh-recovery-reviewer"),
        "review_reset": {
            "prior_review_id": previous["review_id"],
            "reason_class": "authority",
            "reason": "The accepted-result handoff bytes are unavailable.",
        },
        "previous_review": previous,
        "started_at": "2026-09-06T01:02:00Z",
        "completed_at": "2026-09-06T01:03:00Z",
    }
    recovered_handoff = {
        "id": "handoff-recovered-dependency",
        "type": "executor-result",
        "status": "active",
        "project": "fixture",
        "created_at": "2026-09-06",
        "updated_at": "2026-09-06",
        "related": {"plan": "plan-001", "task": "task-dependency"},
        "result": {"state": "completed"},
        "delegation_evidence": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "dependency-owner",
            "run_id": "dependency-run",
            "mechanism": "host-native",
        },
        "acceptance_review": recovered_review,
    }
    handoff_dir = root / ".work-bundle/orchestration/handoff/executor/active"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    recovered_path = handoff_dir / "handoff-recovered-dependency.yaml"
    index = root / ".work-bundle/orchestration/handoff/index.jsonl"
    index.write_text("", encoding="utf-8")
    create_receipt = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/orch.py"),
            "create-accepted-base-absence-receipt",
            "--project-root",
            str(root),
            "--plan-id",
            "plan-001",
            "--task-id",
            "task-dependency",
            "--expected-head",
            expected_base_head,
            "--expected-tree",
            expected_base_tree,
            "--proposed-handoff-id",
            recovered_handoff["id"],
            "--proposed-review-id",
            recovered_review["review_id"],
            "--final-head",
            recovered_head,
            "--final-tree",
            recovered_tree,
        ],
        capture_output=True,
        text=True,
    )
    assert create_receipt.returncode == 0, create_receipt.stderr
    receipt_reference = json.loads(create_receipt.stdout)
    recovered_path.write_text(
        ("\n".join(execution_context._dump_yaml(recovered_handoff)) + "\n").replace(
            ": none\n", ': "none"\n'
        ),
        encoding="utf-8",
    )
    index.write_text(
        json.dumps({
            "id": recovered_handoff["id"],
            "type": "executor-result",
            "status": "active",
            "path": str(recovered_path.relative_to(root)),
            "related_plan": "plan-001",
            "related_task": "task-dependency",
        }) + "\n",
        encoding="utf-8",
    )

    assert set(receipt_reference) == {"receipt_id", "receipt_sha256"}
    receipt_path = execution_context._recovery_receipt_path(
        root, "plan-001", "task-dependency", receipt_reference["receipt_id"]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema"] == "accepted-result-recovery-receipt-v1"
    assert receipt["binding_id"] == binding["ownership"]["binding_id"]
    assert receipt["binding_sha256"] == binding_digest
    assert receipt["baseline_head"] == baseline
    assert receipt["baseline_tree"] == baseline_tree
    assert receipt["expected_base_query"]["result"] == "absent"
    assert receipt["freshness"] == "current_validation_attempt"
    assert receipt["proposed_recovered_result"] == {
        "handoff_id": recovered_handoff["id"],
        "review_id": recovered_review["review_id"],
        "final_head": recovered_head,
        "final_tree": recovered_tree,
    }

    recovered_reference = {
        "handoff_id": recovered_handoff["id"],
        "handoff_sha256": hashlib.sha256(recovered_path.read_bytes()).hexdigest(),
    }
    descriptor = {
        "task_id": "task-dependency",
        "execution_baseline_recovery": {
            "binding_id": binding["ownership"]["binding_id"],
            "binding_sha256": binding_digest,
            "baseline_head": baseline,
            "baseline_tree": baseline_tree,
            "recovery_receipt": receipt_reference,
        },
        "recovered_result": recovered_reference,
        "accepted_result_delta": {
            "expected_base_head": expected_base_head,
            "expected_base_tree": expected_base_tree,
            "final_head": recovered_head,
            "final_tree": recovered_tree,
        },
        "integrated_base": expected_base_head,
        "integrated_head": recovered_head,
    }
    dependent["depends_on"] = ["task-dependency"]
    assert execution_context._accepted_dependency_paths(dependent, root, [descriptor]) == {
        dependency_path
    }

    wrong_delta_base = deepcopy(descriptor)
    wrong_delta_base["accepted_result_delta"]["expected_base_head"] = baseline
    wrong_delta_base["accepted_result_delta"]["expected_base_tree"] = baseline_tree
    wrong_delta_base["integrated_base"] = baseline
    with pytest.raises(SystemExit, match="accepted_result_delta.*mismatch"):
        execution_context._accepted_dependency_paths(dependent, root, [wrong_delta_base])

    caller_assertion = deepcopy(descriptor)
    caller_assertion["execution_baseline_recovery"]["accepted_base_absent"] = True
    with pytest.raises(SystemExit, match="closed|shape"):
        execution_context._accepted_dependency_paths(dependent, root, [caller_assertion])

    recovered_review_with_gap = deepcopy(recovered_review)
    recovered_review_with_gap["evidence"]["unavailable_evidence"] = ["historical handoff"]
    recovered_handoff_with_gap = deepcopy(recovered_handoff)
    recovered_handoff_with_gap["acceptance_review"] = recovered_review_with_gap
    recovered_path.write_text(
        ("\n".join(execution_context._dump_yaml(recovered_handoff_with_gap)) + "\n").replace(
            ": none\n", ': "none"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="unavailable_evidence|complete"):
        execution_context._accepted_dependency_paths(dependent, root, [{
            **descriptor,
            "recovered_result": {
                **recovered_reference,
                "handoff_sha256": hashlib.sha256(recovered_path.read_bytes()).hexdigest(),
            },
        }])
    recovered_path.write_text(
        ("\n".join(execution_context._dump_yaml(recovered_handoff)) + "\n").replace(
            ": none\n", ': "none"\n'
        ),
        encoding="utf-8",
    )

    extra = handoff_dir / "unrelated-record.yaml"
    extra.write_text(
        "id: unrelated-record\ntype: executor-result\n"
        "related: {plan: plan-other, task: task-other}\nresult: {state: partial}\n",
        encoding="utf-8",
    )
    index.write_text(
        index.read_text(encoding="utf-8")
        + json.dumps({"id": "unrelated-record", "related_plan": "plan-other", "related_task": "task-other"})
        + "\n",
        encoding="utf-8",
    )
    assert execution_context._accepted_dependency_paths(dependent, root, [descriptor]) == {
        dependency_path
    }

    archived_dir = root / ".work-bundle/orchestration/handoff/executor/archived"
    archived_dir.mkdir(parents=True, exist_ok=True)
    expected_base_handoff = deepcopy(recovered_handoff)
    expected_base_handoff["id"] = "handoff-restored-accepted-base"
    expected_base_handoff["acceptance_review"] = previous
    expected_base_path = archived_dir / "handoff-restored-accepted-base.yaml"
    expected_base_path.write_text(
        ("\n".join(execution_context._dump_yaml(expected_base_handoff)) + "\n").replace(
            ": none\n", ': "none"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="recoverable accepted base"):
        execution_context._accepted_dependency_paths(dependent, root, [descriptor])
    expected_base_path.unlink()

    duplicate_path = archived_dir / "handoff-recovered-dependency-duplicate.yaml"
    duplicate_path.write_bytes(recovered_path.read_bytes())
    with pytest.raises(SystemExit, match="ambiguous"):
        execution_context._accepted_dependency_paths(dependent, root, [descriptor])
    duplicate_path.unlink()

    mismatched = deepcopy(recovered_handoff)
    mismatched["acceptance_review"]["review_id"] = "different-proposed-review"
    recovered_path.write_text(
        ("\n".join(execution_context._dump_yaml(mismatched)) + "\n").replace(
            ": none\n", ': "none"\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="proposal|proposed|mismatch"):
        execution_context._accepted_dependency_paths(dependent, root, [{
            **descriptor,
            "recovered_result": {
                **recovered_reference,
                "handoff_sha256": hashlib.sha256(recovered_path.read_bytes()).hexdigest(),
            },
        }])


def test_authority_recovery_receipt_rejects_recoverable_accepted_base(tmp_path: Path) -> None:
    root, _, task_path = workspace(tmp_path)
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline")
    brief = _compiled_brief(root, task_path)
    brief["task_id"] = "task-dependency"
    _bind_task_execution(root, brief, execution_id="dependency-exec")
    handoff_dir = root / ".work-bundle/orchestration/handoff/executor/archived"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    commit = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", "HEAD^{tree}")
    accepted = {
        "id": "handoff-historical-accepted-base",
        "type": "executor-result",
        "related": {"plan": "plan-001", "task": "task-dependency"},
        "result": {"state": "completed"},
        "acceptance_review": {
            "required": True,
            "reviewer_independent": True,
            "verdict": "accept",
            "reviewed_head": commit,
            "review_id": "review-historical-accepted-base",
            "review_mode": "initial",
            "review_target_kind": "task",
            "repair_frontier": None,
            "review_reset": None,
            "target_identity": {
                "artifact_id": "task-dependency",
                "revision": commit,
                "sha256": execution_context.semantic_digest({"commit": commit, "tree": tree}),
                "source_tree": tree,
            },
            "reviewer": {
                "agent_id": "historical-reviewer",
                "capability": "judgment",
                "authorship": "none",
                "repair_participation": "none",
                "decision_participation": "none",
                "deliberation_participation": "none",
                "context_origin": "direct_source",
            },
            "evidence": {
                "mode": "direct",
                "capabilities": ["whole-task source review"],
                "unavailable_evidence": [],
                "commands": [],
                "artifacts": [],
            },
            "findings": [],
            "started_at": "2026-09-06T01:00:00Z",
            "completed_at": "2026-09-06T01:01:00Z",
            "staleness": {"is_stale": False, "reason": None, "supersedes": None},
        },
    }
    accepted_path = handoff_dir / "handoff-historical-accepted-base.yaml"
    accepted_path.write_text(
        ("\n".join(execution_context._dump_yaml(accepted)) + "\n").replace(
            ": none\n", ': "none"\n'
        ),
        encoding="utf-8",
    )
    index = root / ".work-bundle/orchestration/handoff/index.jsonl"
    index.write_text("", encoding="utf-8")

    with pytest.raises(SystemExit, match="recoverable accepted base"):
        execution_context.create_accepted_base_absence_receipt(
            root,
            "plan-001",
            "task-dependency",
            commit,
            tree,
            "handoff-proposed-recovery",
            "review-proposed-recovery",
            commit,
            tree,
        )

    distinct = root / "tests/distinct-expected-base.txt"
    distinct.parent.mkdir(parents=True, exist_ok=True)
    distinct.write_text("distinct expected identity\n", encoding="utf-8")
    git(root, "add", str(distinct.relative_to(root)))
    git(root, "commit", "-qm", "distinct expected base identity")
    distinct_head = git(root, "rev-parse", "HEAD")
    distinct_tree = git(root, "rev-parse", "HEAD^{tree}")
    reference = execution_context.create_accepted_base_absence_receipt(
        root,
        "plan-001",
        "task-dependency",
        distinct_head,
        distinct_tree,
        "handoff-proposed-recovery",
        "review-proposed-recovery",
        distinct_head,
        distinct_tree,
    )
    receipt_path = execution_context._recovery_receipt_path(
        root, "plan-001", "task-dependency", reference["receipt_id"]
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["expected_base_head"] == distinct_head
    assert receipt["expected_base_tree"] == distinct_tree


def test_rf_07_brief_rebuild_retains_original_execution_binding_and_baseline(
    tmp_path: Path,
) -> None:
    root, _, task = workspace(tmp_path)
    scoped = _ensure_source_file(root)
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline")
    brief = _compiled_brief(root, task)
    original = _bind_task_execution(root, brief)
    scoped.write_text("def compile_task():\n    return 'repair'\n", encoding="utf-8")
    git(root, "add", str(scoped.relative_to(root)))
    git(root, "commit", "-qm", "repair")

    build_task_brief(args(root, task))
    retained = execution_context.capture_task_baseline_once(
        execution_context.load_task_execution_binding(root, "plan-001", "task-004")
    )

    assert retained["ownership"]["binding_id"] == original["ownership"]["binding_id"]
    assert retained["baseline"] == original["baseline"]
    assert retained["baseline"]["head"] != git(root, "rev-parse", "HEAD")
