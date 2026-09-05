from __future__ import annotations

import builtins
import hashlib
import json
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
    scoped = _ensure_source_file(root)
    dependency = root / "references/assets/orchestration/workflow.md"
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.write_text("before\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "baseline")
    baseline = git(root, "rev-parse", "HEAD")
    baseline_tree = git(root, "rev-parse", "HEAD^{tree}")

    brief = _document(root, task)["task_brief"]
    brief["depends_on"] = ["task-dependency"]
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
    accepted_bytes = accepted_path.read_bytes()
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
