from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ORCHESTRATION = Path(__file__).resolve().parents[1] / "scripts" / "orchestration"
loaded_core = sys.modules.get("core")
loaded_core_path = Path(getattr(loaded_core, "__file__", "")) if loaded_core is not None else None
if loaded_core_path is not None and ORCHESTRATION not in loaded_core_path.parents:
    sys.modules.pop("core", None)
sys.path.insert(0, str(ORCHESTRATION))

import execution_context  # noqa: E402
import review_runtime  # noqa: E402
from task_ownership import (  # noqa: E402
    OwnershipBlocker,
    TaskCandidate,
    canonical_relative_path,
    validate_task_acceptance_ownership,
)


OID_A = "a" * 40
OID_B = "b" * 40
OID_C = "c" * 40
OID_D = "d" * 40

ACCEPTED_RESULT_FIELDS = {
    "schema",
    "plan_id",
    "task_id",
    "binding_id",
    "baseline_identity",
    "accepted_source",
    "authority_projection",
    "executor_result_digest",
    "validation_evidence_ids",
    "review_id",
    "owner_identity",
    "knowledge_disposition",
    "accepted_at",
    "invalidation",
}


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _task(root: Path) -> dict[str, object]:
    return {
        "plan_id": "plan-001",
        "task_id": "task-001",
        "depends_on": ["task-000"],
        "source_ids": ["REQ-001"],
        "files": {
            "read": ["src/./read.py"],
            "write": ["src//a.py"],
            "forbidden": ["secrets/key.txt"],
        },
        "validation": [
            {
                "id": "VAL-001",
                "kind": "process",
                "command": "pytest -q",
                "boundary": "component",
                "freshness": "current_task_batch",
            }
        ],
        "review_required": True,
        "executor_profile": {"capability": "judgment"},
        "workspace": {"root": str(root)},
    }


def _binding(root: Path) -> dict[str, object]:
    return {
        "plan_id": "plan-001",
        "task_id": "task-001",
        "workspace_id": "ws-001",
        "execution_id": "exec-001",
        "repository_id": "repo-001",
        "execution_path": str(root),
        "control_root": str(root),
        "git_identity": {"branch_ref": "refs/heads/main"},
        "baseline": {"head": OID_A, "tree": OID_B},
        "ownership": {
            "binding_id": "binding:plan-001:task-001",
            "state": "active",
            "current_owner": "task-001",
            "history": [{"event": "created"}],
        },
    }


def _record_validation_observation(
    root: Path, binding: dict[str, object], task: dict[str, object]
) -> str:
    item = task["validation"][0]
    assert isinstance(item, dict)
    item["evidence_reuse"] = {
        "mode": "deterministic", "max_age_seconds": 3600,
        "environment_inputs": [], "include_head": False,
    }
    evidence = execution_context.capture_repository_evidence(root)

    def observe(receipt: dict[str, object]) -> dict[str, object]:
        receipt.update({
            "exit_code": 0,
            "stdout_digest": "1" * 64,
            "stderr_digest": "2" * 64,
            "started_at": "2026-09-08T01:00:00Z",
            "completed_at": "2026-09-08T01:00:01Z",
        })
        return {
            "id": item.get("id"), "command": item.get("command"),
            "invariant_ids": item.get("invariant_ids", []), "result": "passed",
        }

    observed = execution_context._completion_provenance_module().observe_validation(
        binding, task, item, evidence, observe,
        lambda: execution_context.capture_repository_evidence(root),
    )
    return str(observed["observation_id"])


def _handoff() -> dict[str, object]:
    return {
        "type": "executor-result",
        "related": {"plan": "plan-001", "task": "task-001"},
        "result": {"state": "completed", "summary": "Implemented the bounded slice."},
        "changes": {"files": [{"path": "src/a.py", "change": "updated"}]},
        "task_fit_check": {"task": "task-001", "result": "clean"},
        "knowledge_disposition": {"action": "none", "affected_authority": []},
        "acceptance_review": {"required": True, "verdict": "accept", "review_id": "review-001"},
        "delegation_evidence": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "agent-001",
            "run_id": "run-001",
            "mechanism": "host-native",
        },
        "validation": {"commands": [{"command": "pytest -q", "result": "passed"}]},
    }


def _validated() -> dict[str, object]:
    return {
        "result_state": "completed",
        "knowledge_disposition": {
            "action": "none",
            "reason": "No durable authority changed.",
            "affected_authority": [],
        },
        "task_ownership": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "agent-001",
            "run_id": "run-001",
            "mechanism": "host-native",
        },
        "observed_validation": [{"id": "VAL-001", "observation_id": "obs-001", "result": "passed"}],
    }


def _build_accepted_task_result(
    task: dict[str, object],
    binding: dict[str, object],
    handoff: dict[str, object],
    validated: dict[str, object],
    **kwargs: object,
) -> dict[str, object]:
    review = handoff.get("acceptance_review")
    assert isinstance(review, dict)
    return execution_context.build_accepted_task_result(
        task, binding, handoff, validated, accepted_review=review, **kwargs
    )


def test_common_accepted_result_path_rejects_embedded_handoff_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "entries": {}, "status": "clean"},
    )

    with pytest.raises(SystemExit, match="accepted mandatory review"):
        execution_context.build_accepted_task_result(
            _task(tmp_path), _binding(tmp_path), _handoff(), _validated()
        )


def test_repair_review_preparation_derives_exact_stored_controller_frontier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous_identity = {
        "artifact_id": "task-001",
        "revision": OID_A,
        "sha256": "1" * 64,
        "source_tree": OID_B,
    }
    previous = {
        "review_id": "review-prior",
        "review_target_kind": "task",
        "verdict": "repair",
        "target_identity": previous_identity,
        "evidence": {"mode": "direct", "capabilities": [], "commands": [], "artifacts": [], "unavailable_evidence": []},
        "reviewer_run": {"run_id": "reviewer-run-prior", "sha256": "2" * 64},
        "findings": [
            {
                "finding_id": "F-001",
                "severity": "blocking",
                "recommended_owner": "task_owner",
                "evidence": [{"locator": "source:src/a.py"}],
            }
        ],
    }
    store = tmp_path / ".work-bundle/orchestration/reviews"
    store.mkdir(parents=True)
    path = store / "review-prior.json"
    path.write_text(__import__("json").dumps(previous), encoding="utf-8")
    path.chmod(0o444)
    validated = SimpleNamespace(review_id="review-prior", target_identity=previous_identity)
    monkeypatch.setattr(
        review_runtime,
        "load_stored_review",
        lambda *_args, **_kwargs: (previous, validated),
    )
    repaired_identity = {
        "artifact_id": "task-001",
        "revision": OID_C,
        "sha256": "3" * 64,
        "source_tree": OID_D,
    }

    loaded, frontier = execution_context._stored_task_repair_preparation(
        tmp_path, _task(tmp_path), base=OID_A, repaired_identity=repaired_identity
    )

    assert loaded == previous
    assert frontier == {
        "prior_review_id": "review-prior",
        "blocking_finding_ids": ["F-001"],
        "previous_reviewed_identity": previous_identity,
        "repaired_identity": repaired_identity,
        "affected_boundaries": ["source:src/a.py"],
        "frozen_evidence_reference": review_runtime.review_evidence_identity(previous),
    }


def test_shared_scope_canonicalizer_normalizes_equivalent_paths_and_rejects_unsafe() -> None:
    assert canonical_relative_path("src/./a.py") == "src/a.py"
    assert canonical_relative_path("src//a.py") == "src/a.py"

    for unsafe in ("", ".", "../src/a.py", "/src/a.py", "src\\a.py", "src/*.py"):
        with pytest.raises(OwnershipBlocker, match="unsafe|empty"):
            canonical_relative_path(unsafe)

    with pytest.raises(SystemExit, match="unsafe"):
        execution_context._task_scope_paths(["../src/a.py"], Path.cwd(), "write scope")


def test_declared_and_observed_scopes_use_the_same_canonical_semantics() -> None:
    with pytest.raises(OwnershipBlocker, match="controller mutated"):
        validate_task_acceptance_ownership(
            delegation_evidence=_handoff()["delegation_evidence"],
            mutation_events=[{"actor_kind": "controller", "paths": ["src/./a.py"]}],
            write_scope=["src//a.py"],
            validations_passed=True,
        )

    with pytest.raises(OwnershipBlocker, match="unsafe"):
        TaskCandidate(
            task_id="task-001",
            dependencies=(),
            write_scope=("../outside.py",),
            execution_workspace="bound-worktree",
        )


def test_accepted_result_is_deterministic_current_authority_not_handoff_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "entries": {}, "status": "dirty"},
    )

    first = _build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )
    appended = deepcopy(binding)
    appended["ownership"]["history"].append({"event": "audit-appended"})
    second = _build_accepted_task_result(
        task, appended, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )

    assert first == second
    assert set(first) == ACCEPTED_RESULT_FIELDS
    assert first["schema"] == "accepted-task-result-v1"
    assert set(first["authority_projection"]) == {
        "task_digest",
        "binding_digest",
        "scope_digest",
        "validation_obligations_digest",
        "required_review_digest",
        "ownership_digest",
    }
    assert set(first["accepted_source"]) == {"head", "tree", "state_digest"}
    assert first["baseline_identity"] == {"head": OID_A, "tree": OID_B}
    assert first["accepted_source"]["state_digest"] == execution_context.semantic_digest(
        {
            "plan_id": first["plan_id"],
            "task_id": first["task_id"],
            "binding_id": first["binding_id"],
            "baseline_identity": {"head": OID_A, "tree": OID_B},
            "accepted_source": {"head": OID_A, "tree": OID_B},
            "authority_projection": first["authority_projection"],
            "knowledge_disposition": first["knowledge_disposition"],
        }
    )
    assert first["validation_evidence_ids"] == ["obs-001"]
    assert first["knowledge_disposition"] == _validated()["knowledge_disposition"]
    assert "mutation_events" not in repr(first)
    assert "validation" not in first["executor_result_digest"]
    execution_context.assert_accepted_task_result_current(task, appended, first)

    tampered_disposition = deepcopy(first)
    tampered_disposition["knowledge_disposition"] = {
        "action": "update",
        "reason": "Tampered after acceptance.",
        "affected_authority": ["REQ-001"],
    }
    with pytest.raises(SystemExit, match="accepted task result.*source"):
        execution_context.assert_accepted_task_result_current(task, binding, tampered_disposition)

    changed_scope = deepcopy(task)
    changed_scope["files"]["write"] = ["src/other.py"]
    with pytest.raises(SystemExit, match="accepted task result.*scope"):
        execution_context.assert_accepted_task_result_current(changed_scope, appended, first)

    changed_source = deepcopy(task)
    changed_source["source_ids"] = ["REQ-002"]
    with pytest.raises(SystemExit, match="accepted task result.*task"):
        execution_context.assert_accepted_task_result_current(changed_source, appended, first)

    changed_binding = deepcopy(binding)
    changed_binding["execution_id"] = "exec-002"
    with pytest.raises(SystemExit, match="accepted task result.*binding"):
        execution_context.assert_accepted_task_result_current(task, changed_binding, first)

    changed_review = deepcopy(task)
    changed_review["review_required"] = False
    with pytest.raises(SystemExit, match="review"):
        execution_context.assert_accepted_task_result_current(changed_review, binding, first)

    invalidated = deepcopy(first)
    invalidated["invalidation"] = {"reason": "accepted source changed"}
    with pytest.raises(SystemExit, match="explicitly invalidated"):
        execution_context.assert_accepted_task_result_current(task, binding, invalidated)


@pytest.mark.parametrize("predecessor_kind", ["task", "integrated_stage"])
def test_standalone_repair_review_rematerializes_compact_result_without_executor_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, predecessor_kind: str
) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    source = tmp_path / "source.py"
    source.write_text("VALUE = 1\n")
    _git(tmp_path, "add", "source.py")
    _git(tmp_path, "commit", "-qm", "accepted executor result")
    accepted_head = _git(tmp_path, "rev-parse", "HEAD")
    accepted_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    binding["baseline"] = {"head": accepted_head, "tree": accepted_tree}
    prior = _build_accepted_task_result(
        task,
        binding,
        _handoff(),
        _validated(),
        accepted_at="2026-09-08T01:00:00Z",
    )
    binding["accepted_result"] = prior
    previous_identity = {
        "artifact_id": "task-001" if predecessor_kind == "task" else "plan-001",
        "revision": accepted_head,
        "sha256": "1" * 64,
        "source_tree": accepted_tree,
    }
    source.write_text("VALUE = 2\n")
    _git(tmp_path, "add", "source.py")
    _git(tmp_path, "commit", "-qm", "repair reviewed endpoint")
    reviewed_head = _git(tmp_path, "rev-parse", "HEAD")
    reviewed_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    repaired_identity = {
        "artifact_id": "task-001",
        "revision": reviewed_head,
        "sha256": "2" * 64,
        "source_tree": reviewed_tree,
    }
    reviewer = {
        "agent_id": "reviewer-001",
        "capability": "judgment",
        "authorship": "none",
        "repair_participation": "none",
        "decision_participation": "none",
        "deliberation_participation": "none",
        "context_origin": "direct_source",
    }
    evidence = {
        "mode": "direct",
        "capabilities": ["bounded source inspection"],
        "unavailable_evidence": [],
        "commands": [],
        "artifacts": [],
    }
    previous_review: dict[str, object] = {
        "verdict": "repair",
        "review_id": "review-finding-001",
        "reviewed_head": accepted_head,
        "review_mode": "initial",
        "review_target_kind": "task",
        "repair_frontier": None,
        "review_reset": None,
        "target_identity": previous_identity,
        "reviewer": reviewer,
        "evidence": evidence,
        "findings": [{
            "finding_id": "FINDING-001",
            "stage": "implementation",
            "class": "implementation_defect",
            "severity": "blocking",
            "first_broken_artifact": "implementation",
            "obligation_basis": "accepted_requirement",
            "evidence": [{
                "kind": "test",
                "locator": "tests/test_orchestration_accepted_result.py",
                "digest_or_identity": "red-001",
                "observation": "standalone repair review could not be materialized",
            }],
            "target_identity": previous_identity,
            "summary": "Repair acceptance was coupled to executor redispatch.",
            "recommended_owner": "task_owner",
            "disposition": "repair_task",
        }],
        "started_at": "2026-09-08T01:01:00Z",
        "completed_at": "2026-09-08T01:02:00Z",
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }
    if predecessor_kind == "task":
        previous_review.update(
            required=True,
            reviewer_independent=True,
            reviewed_head=accepted_head,
        )
    else:
        previous_review.pop("reviewed_head")
        previous_review["review_target_kind"] = "stage"
        previous_review["stage"] = "integrated_implementation"
    repair_review = {
        **previous_review,
        "required": True,
        "reviewer_independent": True,
        "review_target_kind": "task",
        "verdict": "accept",
        "review_id": "review-repair-001",
        "reviewed_head": reviewed_head,
        "review_mode": "repair",
        "target_identity": repaired_identity,
        "findings": [],
        "previous_review": previous_review,
        "repair_frontier": {
            "prior_review_id": "review-finding-001",
            "blocking_finding_ids": ["FINDING-001"],
            "previous_reviewed_identity": previous_identity,
            "repaired_identity": repaired_identity,
            "affected_boundaries": ["scripts/orchestration/execution_context.py"],
            "frozen_evidence_reference": review_runtime.review_evidence_identity(previous_review),
        },
        "started_at": "2026-09-08T01:03:00Z",
        "completed_at": "2026-09-08T01:04:00Z",
    }
    (tmp_path / "unrelated.py").write_text("UNCHANGED_FRONTIER = True\n")
    _git(tmp_path, "add", "unrelated.py")
    _git(tmp_path, "commit", "-qm", "later unrelated lifecycle progress")
    persisted: dict[str, object] = {}
    monkeypatch.setattr(execution_context, "load_task_execution_binding", lambda *_: binding)
    monkeypatch.setattr(execution_context, "_persist_binding", lambda value, _root: persisted.update(value))
    monkeypatch.setattr(
        execution_context,
        "build_accepted_task_result",
        lambda *_args, **_kwargs: pytest.fail("executor handoff must not be replayed"),
    )

    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_: None)
    (tmp_path / ".git/info/exclude").write_text(".work-bundle/\n", encoding="utf-8")
    review_reference = review_runtime.publish_review(
        tmp_path, repair_review, current_target_identity=repaired_identity
    )
    observation_id = _record_validation_observation(tmp_path, binding, task)
    repaired = execution_context.materialize_accepted_task_repair_review(
        tmp_path,
        task,
        review_reference,
        accepted_at="2026-09-08T01:05:00Z",
        validation_evidence_ids=[observation_id],
    )

    for field in (
        "baseline_identity",
        "executor_result_digest",
        "owner_identity",
        "knowledge_disposition",
    ):
        assert repaired[field] == prior[field]
    assert repaired["accepted_source"]["head"] == reviewed_head
    assert repaired["accepted_source"]["tree"] == reviewed_tree
    assert repaired["review_id"] == "review-repair-001"
    assert repaired["validation_evidence_ids"] == [observation_id]
    assert repaired["authority_projection"]["required_review_digest"] == execution_context.semantic_digest(
        execution_context._accepted_review_projection(repair_review)
    )
    assert persisted["accepted_result"] == repaired
    assert "previous_review" not in repr(repaired)

    divergent_head = _git(tmp_path, "commit-tree", accepted_tree, "-m", "divergent endpoint")
    cases = [
        (reviewed_head, accepted_tree, "revision/tree identity is mismatched"),
        ("f" * 40, accepted_tree, "target revision does not resolve"),
        (divergent_head, accepted_tree, "not an ancestor"),
    ]
    for index, (target_head, target_tree, message) in enumerate(cases):
        invalid = deepcopy(repair_review)
        invalid["review_id"] = f"review-invalid-target-{index}"
        invalid_identity = {
            **invalid["target_identity"],
            "revision": target_head,
            "source_tree": target_tree,
        }
        invalid["reviewed_head"] = target_head
        invalid["target_identity"] = invalid_identity
        invalid["repair_frontier"]["repaired_identity"] = invalid_identity
        invalid_reference = review_runtime.publish_review(
            tmp_path, invalid, current_target_identity=invalid_identity
        )
        with pytest.raises(SystemExit, match=message):
            execution_context.materialize_accepted_task_repair_review(
                tmp_path, task, invalid_reference, accepted_at="2026-09-08T01:05:00Z"
            )
    if predecessor_kind == "integrated_stage":
        wrong_plan = deepcopy(repair_review)
        wrong_plan["review_id"] = "review-wrong-predecessor-plan"
        wrong_identity = {
            **wrong_plan["previous_review"]["target_identity"],
            "artifact_id": "plan-other",
        }
        wrong_plan["previous_review"]["target_identity"] = wrong_identity
        wrong_plan["previous_review"]["findings"][0]["target_identity"] = wrong_identity
        wrong_plan["repair_frontier"]["previous_reviewed_identity"] = wrong_identity
        wrong_plan_reference = review_runtime.publish_review(
            tmp_path, wrong_plan, current_target_identity=repaired_identity
        )
        with pytest.raises(SystemExit, match="exact current task and predecessor owner"):
            execution_context.materialize_accepted_task_repair_review(
                tmp_path, task, wrong_plan_reference
            )

        wrong_stage = deepcopy(repair_review)
        wrong_stage["review_id"] = "review-wrong-predecessor-stage"
        wrong_stage["previous_review"]["stage"] = "plan"
        with pytest.raises(review_runtime.ReviewContractError, match="stage predecessor must be integrated_implementation"):
            review_runtime.publish_review(tmp_path, wrong_stage, current_target_identity=repaired_identity)


def test_standalone_review_recomposes_changed_task_authority_without_executor_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_task = _task(tmp_path)
    binding = _binding(tmp_path)
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "status": "clean", "entries": {}},
    )
    prior = _build_accepted_task_result(
        old_task, binding, _handoff(), _validated(), accepted_at="2026-09-08T02:00:00Z"
    )
    binding["accepted_result"] = prior
    current_task = deepcopy(old_task)
    current_task["files"]["write"] = ["src/a.py", "src/b.py"]
    current_task["validation"][0]["command"] = "pytest -q tests/current"
    previous_identity = {
        "artifact_id": "task-001", "revision": OID_A,
        "sha256": "1" * 64, "source_tree": OID_B,
    }
    current_identity = {
        "artifact_id": "task-001", "revision": OID_C,
        "sha256": "2" * 64, "source_tree": OID_D,
    }
    review = {
        "required": True,
        "reviewer_independent": True,
        "review_id": "review-current-authority",
        "reviewed_head": OID_C,
        "review_mode": "initial",
        "review_target_kind": "task",
        "repair_frontier": None,
        "review_reset": {
            "prior_review_id": "review-001",
            "reason_class": "scope",
            "reason": "Current task scope authority changed.",
        },
        "target_identity": current_identity,
        "reviewer": {"agent_id": "reviewer-current"},
        "verdict": "accept",
        "previous_review": {
            "review_id": "review-001",
            "review_target_kind": "task",
            "target_identity": previous_identity,
        },
    }
    validated_review = SimpleNamespace(
        review_id="review-current-authority",
        review_mode="initial",
        verdict="accepted",
        target_identity=current_identity,
        repair_frontier=None,
        review_reset=review["review_reset"],
        reviewer={"agent_id": "reviewer-current"},
    )
    monkeypatch.setattr(execution_context, "load_task_execution_binding", lambda *_: binding)
    monkeypatch.setattr(
        review_runtime,
        "load_stored_review",
        lambda _root, _reference, **_kwargs: (review, validated_review),
    )
    monkeypatch.setattr(
        review_runtime,
        "stored_review_target_identity",
        lambda _root, _reference: current_identity,
    )
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_C, "tree": OID_D, "status": "clean", "entries": {}},
    )

    def git_result(arguments, **_kwargs):
        if "merge-base" in arguments:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        value = OID_D if str(arguments[-1]).endswith("^{tree}") else OID_C
        return SimpleNamespace(returncode=0, stdout=value + "\n", stderr="")

    monkeypatch.setattr(execution_context.subprocess, "run", git_result)
    persisted: dict[str, object] = {}
    monkeypatch.setattr(execution_context, "_persist_binding", lambda value, _root: persisted.update(value))
    monkeypatch.setattr(
        execution_context,
        "build_accepted_task_result",
        lambda *_args, **_kwargs: pytest.fail("executor result replayed"),
    )
    monkeypatch.setattr(
        execution_context,
        "_claim_bound_validation_observations",
        lambda *_args: [{"observation_id": "obs-current"}],
    )

    accepted = execution_context.materialize_accepted_task_review(
        tmp_path,
        current_task,
        {"review_id": "review-current-authority", "sha256": "9" * 64},
        {
            "causal_class": "claim_relevant_drift",
            "affected_task": "task-001",
            "authorized_lifecycle_action": "rematerialize_accepted_result",
        },
        validation_evidence_ids=["obs-current"],
    )

    for field in (
        "baseline_identity", "executor_result_digest",
        "owner_identity", "knowledge_disposition",
    ):
        assert accepted[field] == prior[field]
    assert accepted["validation_evidence_ids"] == ["obs-current"]
    assert accepted["accepted_source"]["head"] == OID_C
    assert accepted["accepted_source"]["tree"] == OID_D
    assert accepted["authority_projection"] == execution_context._accepted_authority_projection(
        current_task, binding, accepted_review=review, owner_identity=prior["owner_identity"]
    )
    assert persisted["accepted_result"] == accepted
    assert "previous_review" not in repr(accepted)
    assert "causal_class" not in repr(accepted)


def test_legacy_accepted_result_without_disposition_remains_current_for_nonknowledge_consumers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "entries": {}, "status": "clean"},
    )
    accepted = _build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )
    legacy = deepcopy(accepted)
    legacy.pop("knowledge_disposition")
    legacy["accepted_source"]["state_digest"] = execution_context._accepted_source_state_digest(
        plan_id=legacy["plan_id"],
        task_id=legacy["task_id"],
        binding_id=legacy["binding_id"],
        baseline_identity=legacy["baseline_identity"],
        head=legacy["accepted_source"]["head"],
        tree=legacy["accepted_source"]["tree"],
        authority_projection=legacy["authority_projection"],
    )

    execution_context.assert_accepted_task_result_current(task, binding, legacy)


def test_actual_accepted_repair_review_mode_and_frontier_are_digest_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "entries": {}, "status": "dirty"},
    )
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    initial = _build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )
    repaired_handoff = deepcopy(_handoff())
    repaired_handoff["acceptance_review"].update(
        {
            "review_mode": "repair",
            "repair_frontier": {
                "prior_review_id": "review-prior",
                "frozen_evidence_reference": "evidence-001",
            },
        }
    )
    repaired = _build_accepted_task_result(
        task, binding, repaired_handoff, _validated(), accepted_at="2026-09-06T10:00:00Z"
    )

    assert (
        initial["authority_projection"]["required_review_digest"]
        != repaired["authority_projection"]["required_review_digest"]
    )
    assert repaired["authority_projection"]["required_review_digest"] == execution_context.semantic_digest(
        {
            "required": True,
            "review_id": "review-001",
            "verdict": "accepted",
            "review_mode": "repair",
            "repair_frontier": repaired_handoff["acceptance_review"]["repair_frontier"],
        }
    )
    execution_context.assert_accepted_task_result_current(task, binding, repaired)


def test_unrelated_repository_advance_does_not_stale_accepted_task_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = {"head": OID_A, "tree": OID_B, "entries": {}, "status": "dirty"}
    monkeypatch.setattr(execution_context, "capture_repository_evidence", lambda _root: repository)
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    accepted = _build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )

    repository = {"head": OID_C, "tree": OID_D, "entries": {}, "status": "clean"}
    execution_context.assert_accepted_task_result_current(task, binding, accepted)


def test_dependency_topology_change_invalidates_accepted_task_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "entries": {}, "status": "dirty"},
    )
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    accepted = _build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )

    changed = deepcopy(task)
    changed["depends_on"] = ["task-other"]
    with pytest.raises(SystemExit, match="task"):
        execution_context.assert_accepted_task_result_current(changed, binding, accepted)


def test_materialize_persists_one_result_in_existing_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    persisted: list[dict[str, object]] = []
    monkeypatch.setattr(execution_context, "load_task_execution_binding", lambda *_args: deepcopy(binding))
    monkeypatch.setattr(execution_context, "_persist_binding", lambda value, _root: persisted.append(value))
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": OID_A, "tree": OID_B, "entries": {}, "status": "dirty"},
    )

    accepted = execution_context.materialize_accepted_task_result(
        tmp_path,
        task,
        _handoff(),
        _validated(),
        accepted_review=_handoff()["acceptance_review"],
        accepted_at="2026-09-06T10:00:00Z",
    )

    assert len(persisted) == 1
    assert persisted[0]["accepted_result"] == accepted
    assert persisted[0]["ownership"] == binding["ownership"]
