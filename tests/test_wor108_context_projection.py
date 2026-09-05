from __future__ import annotations

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

    payload = event()
    payload["compiled_context_metrics"] = metrics
    assert validate_stage_event(payload).compiled_context_metrics == metrics
    invalid = deepcopy(payload)
    invalid["compiled_context_metrics"]["expansion_reason"] = "whole_history"
    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_CONTEXT_METRICS_INVALID"):
        validate_stage_event(invalid)


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
