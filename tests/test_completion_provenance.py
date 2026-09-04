from __future__ import annotations

import sys
import threading
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "orchestration"))

from completion_provenance import (  # noqa: E402
    CompletionProvenanceError,
    FailureOwnershipV1,
    ManagedProvenanceStore,
    consume_observation,
    load_observation,
    record_relevant_mutation,
    reuse_observation,
    validate_predecessor_extension,
    validate_resume_owner,
)
import execution_context  # noqa: E402


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _request(**changes):
    request = {
        "observation_id": "obs-001",
        "command_digest": "a" * 64,
        "cwd_token": "isolated_execution_root",
        "product_tree": "1" * 40,
        "state_digest": "b" * 64,
        "oracle_digest": "c" * 64,
        "freshness_deadline": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "mutation_epoch": 0,
        "invocation_id": "invoke-001",
    }
    request.update(changes)
    return request


def _result():
    return {
        "exit_code": 0,
        "stdout_digest": "d" * 64,
        "stderr_digest": "e" * 64,
        "started_at": NOW.isoformat().replace("+00:00", "Z"),
        "completed_at": (NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    }


def test_kernel_failure_owner_lifecycle_preserves_origin_and_blocks_early_release(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    binding = FailureOwnershipV1.create(
        store, binding_id="bind-001", target_kind="isolated_worktree", owner="executor"
    )
    failed = binding.record_failure(owner="repairer", reason="validation failed")
    assert failed.original_owner == "executor"
    assert failed.reason == "validation failed"
    assert failed.current_owner == "repairer"
    with pytest.raises(CompletionProvenanceError, match="not releasable"):
        failed.release(owner="executor")
    with pytest.raises(CompletionProvenanceError, match="current owner"):
        validate_resume_owner(failed, "executor")


def test_kernel_repair_and_rereview_owners_must_clear_before_release(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    binding = FailureOwnershipV1.create(store, "bind-002", "git_backed", "executor")
    repair = binding.record_failure("repairer", "broken oracle")
    rereview = repair.complete_repair("repairer", "reviewer")
    with pytest.raises(CompletionProvenanceError, match="rereview owner"):
        rereview.mark_releasable("repairer")
    ready = rereview.complete_rereview("reviewer")
    released = ready.release("executor")
    assert released.state == "released"
    assert released.repair_owner is None and released.rereview_owner is None
    assert released.release("executor").history == released.history
    with pytest.raises(CompletionProvenanceError, match="released binding"):
        released.record_failure("repairer", "late failure")


@pytest.mark.parametrize("owner", ["owner with spaces", " owner", "owner/"])
def test_kernel_ownership_rejects_non_identifier_owners(tmp_path, owner):
    store = ManagedProvenanceStore(tmp_path)

    with pytest.raises(CompletionProvenanceError, match="owner"):
        FailureOwnershipV1.create(store, "bind-owner", "git_backed", owner)

    binding = FailureOwnershipV1.create(store, "bind-valid", "git_backed", "executor")
    with pytest.raises(CompletionProvenanceError, match="owner"):
        binding.record_failure(owner, "validation failed")


def test_kernel_ids_are_globally_unique_across_managed_store(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    FailureOwnershipV1.create(store, "shared-id", "local_project", "owner")
    with pytest.raises(CompletionProvenanceError, match="already registered"):
        reuse_observation(store, _request(observation_id="shared-id"), lambda: _result(), now=NOW)


def test_kernel_execution_context_creates_typed_binding_ownership(tmp_path, monkeypatch):
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    runtime_root = tmp_path / "runtime"

    class FakeWorkspace:
        @staticmethod
        def load_state(*_args):
            return {
                "execution_workspace_state": {"path": str(execution_root), "kind": "worktree"},
                "git_identity": {
                    "source_repository": str(execution_root), "git_common_dir": str(execution_root / ".git"),
                    "git_dir": str(execution_root / ".git"), "branch_ref": "refs/heads/test",
                },
                "state_path": str(runtime_root / "state.json"),
            }

    monkeypatch.setattr(execution_context, "_execution_workspace_module", lambda: FakeWorkspace)
    binding = execution_context.create_or_load_task_execution_binding(
        control_root=tmp_path, plan_id="plan-001", task_id="task-001", workspace_id="ws-001",
        execution_id="exec-001", repository_id="repo-001", runtime_root=runtime_root,
    )
    assert binding["ownership"] == {
        **binding["ownership"],
        "binding_id": "binding:plan-001:task-001",
        "target_kind": "isolated_worktree",
        "state": "active",
        "original_owner": "task-001",
        "current_owner": "task-001",
        "reason": "binding created",
        "repair_owner": None,
        "rereview_owner": None,
        "releasable": False,
    }
    assert binding["ownership"]["history"]


def test_kernel_execution_context_rejects_missing_malformed_or_store_mismatched_ownership(tmp_path, monkeypatch):
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    runtime_root = tmp_path / "runtime"

    class FakeWorkspace:
        @staticmethod
        def load_state(*_args):
            return {
                "execution_workspace_state": {"path": str(execution_root), "kind": "worktree"},
                "git_identity": {},
                "state_path": str(runtime_root / "state.json"),
            }

    monkeypatch.setattr(execution_context, "_execution_workspace_module", lambda: FakeWorkspace)
    binding = execution_context.create_or_load_task_execution_binding(
        control_root=tmp_path, plan_id="plan-001", task_id="task-001", workspace_id="ws-001",
        execution_id="exec-001", repository_id="repo-001", runtime_root=runtime_root,
    )
    monkeypatch.setattr(execution_context, "_verify_binding_provenance", lambda *_: None)
    path = tmp_path / ".work-bundle/runtime/execution/plan-001/task-001/execution-binding.json"

    missing = dict(binding)
    missing.pop("ownership")
    path.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(SystemExit, match="ownership"):
        execution_context.load_task_execution_binding(tmp_path, "plan-001", "task-001")

    malformed = dict(binding)
    malformed["ownership"] = {**binding["ownership"], "current_owner": None}
    path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(SystemExit, match="ownership"):
        execution_context.load_task_execution_binding(tmp_path, "plan-001", "task-001")

    mismatched = dict(binding)
    mismatched["ownership"] = {**binding["ownership"], "current_owner": "attacker"}
    path.write_text(json.dumps(mismatched), encoding="utf-8")
    with pytest.raises(SystemExit, match="ownership"):
        execution_context.load_task_execution_binding(tmp_path, "plan-001", "task-001")


def test_observation_reuse_requires_complete_identity_and_freshness(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    calls = 0

    def run():
        nonlocal calls
        calls += 1
        return _result()

    first = reuse_observation(store, _request(), run, now=NOW)
    second = reuse_observation(store, _request(observation_id="obs-002", invocation_id="invoke-002"), run, now=NOW)
    changed = reuse_observation(
        store,
        _request(observation_id="obs-003", invocation_id="invoke-003", oracle_digest="f" * 64),
        run,
        now=NOW,
    )
    assert calls == 2
    assert second.observation_id == first.observation_id
    assert second.reuse_of == first.observation_id
    assert changed.observation_id == "obs-003"
    expired = _request(
        observation_id="obs-004",
        invocation_id="invoke-004",
        freshness_deadline=(NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    )
    with pytest.raises(CompletionProvenanceError, match="freshness"):
        reuse_observation(store, expired, run, now=NOW)


def test_observation_concurrent_requests_execute_once(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    barrier = threading.Barrier(2)
    calls = 0
    calls_lock = threading.Lock()

    def invoke(number):
        barrier.wait()

        def run():
            nonlocal calls
            with calls_lock:
                calls += 1
            return _result()

        return reuse_observation(
            store,
            _request(observation_id=f"obs-{number}", invocation_id=f"invoke-{number}"),
            run,
            now=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        observations = list(pool.map(invoke, (10, 11)))
    assert calls == 1
    assert len({item.observation_id for item in observations}) == 1
    assert sum(item.reuse_of is not None for item in observations) == 1


def test_observation_can_be_consumed_by_only_one_finalization(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    observation = reuse_observation(store, _request(), lambda: _result(), now=NOW)
    assert observation.to_dict()["consumed_by_finalization"] is None
    consume_observation(store, observation.observation_id, "final-001")
    assert load_observation(store, observation.observation_id).to_dict()["consumed_by_finalization"] == "final-001"
    consume_observation(store, observation.observation_id, "final-001")
    with pytest.raises(CompletionProvenanceError, match="already consumed"):
        consume_observation(store, observation.observation_id, "final-002")


def test_observation_relevant_mutation_invalidates_reuse(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    calls = 0

    def run():
        nonlocal calls
        calls += 1
        return _result()

    reuse_observation(store, _request(), run, now=NOW)
    assert record_relevant_mutation(store, "source changed") == 1
    reuse_observation(
        store,
        _request(observation_id="obs-new", invocation_id="invoke-new", mutation_epoch=1),
        run,
        now=NOW,
    )
    assert calls == 2


def test_predecessor_extension_uses_public_contract_not_byte_identity():
    predecessor = {"schema_version": 1, "public": {"mode": "safe"}, "private": "old"}
    extension = {"schema_version": 2, "public": {"mode": "safe"}, "private": "changed", "new": True}
    accepted = validate_predecessor_extension(
        predecessor,
        extension,
        authorized=True,
        public_contract_validator=lambda old, new: old["public"] == new["public"],
    )
    assert accepted is extension
    with pytest.raises(CompletionProvenanceError, match="authorized"):
        validate_predecessor_extension(predecessor, extension, authorized=False, public_contract_validator=lambda *_: True)
    with pytest.raises(CompletionProvenanceError, match="public contract"):
        validate_predecessor_extension(predecessor, extension, authorized=True, public_contract_validator=lambda *_: False)
