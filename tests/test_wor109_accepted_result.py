from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest


ORCHESTRATION = Path(__file__).resolve().parents[1] / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import execution_context  # noqa: E402
from task_ownership import (  # noqa: E402
    OwnershipBlocker,
    TaskCandidate,
    canonical_relative_path,
    validate_task_acceptance_ownership,
)


OID_A = "a" * 40
OID_B = "b" * 40


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
        "git_identity": {"branch_ref": "refs/heads/main"},
        "baseline": {"head": OID_A, "tree": OID_B},
        "ownership": {
            "binding_id": "binding:plan-001:task-001",
            "state": "active",
            "current_owner": "task-001",
            "history": [{"event": "created"}],
        },
    }


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
        "task_ownership": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "agent-001",
            "run_id": "run-001",
            "mechanism": "host-native",
        },
        "observed_validation": [{"id": "VAL-001", "observation_id": "obs-001", "result": "passed"}],
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

    first = execution_context.build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )
    appended = deepcopy(binding)
    appended["ownership"]["history"].append({"event": "audit-appended"})
    second = execution_context.build_accepted_task_result(
        task, appended, _handoff(), _validated(), accepted_at="2026-09-06T10:00:00Z"
    )

    assert first == second
    assert first["schema"] == "accepted-task-result-v1"
    assert first["validation_evidence_ids"] == ["obs-001"]
    assert "mutation_events" not in repr(first)
    assert "validation" not in first["executor_result_digest"]
    execution_context.assert_accepted_task_result_current(task, appended, first)

    changed_scope = deepcopy(task)
    changed_scope["files"]["write"] = ["src/other.py"]
    with pytest.raises(SystemExit, match="accepted task result.*scope"):
        execution_context.assert_accepted_task_result_current(changed_scope, appended, first)

    changed_source = deepcopy(task)
    changed_source["source_ids"] = ["REQ-002"]
    with pytest.raises(SystemExit, match="accepted task result.*source"):
        execution_context.assert_accepted_task_result_current(changed_source, appended, first)

    changed_binding = deepcopy(binding)
    changed_binding["execution_id"] = "exec-002"
    with pytest.raises(SystemExit, match="accepted task result.*binding"):
        execution_context.assert_accepted_task_result_current(task, changed_binding, first)

    tampered = deepcopy(first)
    tampered["ownership"]["agent_id"] = "other-agent"
    with pytest.raises(SystemExit, match="tampered"):
        execution_context.assert_accepted_task_result_current(task, binding, tampered)

    changed_review = deepcopy(task)
    changed_review["review_required"] = False
    with pytest.raises(SystemExit, match="validation/review"):
        execution_context.assert_accepted_task_result_current(changed_review, binding, first)

    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("changed after acceptance\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="repository"):
        execution_context.assert_accepted_task_result_current(task, binding, first)


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
        accepted_at="2026-09-06T10:00:00Z",
    )

    assert len(persisted) == 1
    assert persisted[0]["accepted_result"] == accepted
    assert persisted[0]["ownership"] == binding["ownership"]
