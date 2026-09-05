from __future__ import annotations

import sys
import threading
import json
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "orchestration"))

from completion_provenance import (  # noqa: E402
    CompletionProvenanceError,
    FailureOwnershipV1,
    ManagedProvenanceStore,
    claim_observation_identity,
    consume_observation,
    load_observation,
    record_relevant_mutation,
    release_completion_binding,
    resolve_completion_owner,
    resume_failed_stage,
    retain_binding_owner,
    reuse_observation,
    validate_predecessor_extension,
    validate_resume_owner,
)
import execution_context  # noqa: E402
import plans  # noqa: E402
import completion_provenance  # noqa: E402


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


def test_validation_policy_defaults_are_explicit_and_conservative():
    policy = completion_provenance.validation_reuse_policy
    assert policy({"kind": "process"})["max_age_seconds"] == 0
    assert policy({"evidence_reuse": {"mode": "deterministic"}})["max_age_seconds"] == 3600
    assert policy({"evidence_reuse": {"mode": "live"}})["max_age_seconds"] == 0
    assert policy({"evidence_reuse": {"mode": "live", "max_age_seconds": 30}})["max_age_seconds"] == 30


def test_validation_environment_binds_dependency_profile_without_temp_paths(tmp_path, monkeypatch):
    dependency = tmp_path / "runtime.lock"
    dependency.write_text("python=3.13;pytest=9.1.1")
    policy = completion_provenance.validation_reuse_policy({"evidence_reuse": {
        "mode": "deterministic", "dependency_files": ["runtime.lock"], "profile": "isolated-pytest",
        "environment_inputs": ["CLAIM_MODE"],
    }})
    before = completion_provenance.validation_environment_identity(tmp_path, policy)
    assert completion_provenance.validation_environment_identity(tmp_path, {**policy, "profile": "different-profile"}) != before
    monkeypatch.setenv("TMPDIR", "/volatile/other-temp-root")
    assert completion_provenance.validation_environment_identity(tmp_path, policy) == before
    dependency.write_text("python=3.13;pytest=next")
    assert completion_provenance.validation_environment_identity(tmp_path, policy) != before
    dependency.write_text("python=3.13;pytest=9.1.1")
    monkeypatch.setenv("CLAIM_MODE", "changed")
    assert completion_provenance.validation_environment_identity(tmp_path, policy) != before
    assert "/volatile" not in json.dumps(before)


def test_reuse_revalidates_stored_result_shape(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    reuse_observation(store, _request(), lambda: _result(), now=NOW)
    with store.locked():
        state = store._read_unlocked()
        del state["observations"][0]["result"]["exit_code"]
        store._write_unlocked(state)
    with pytest.raises(CompletionProvenanceError, match="closed and complete"):
        reuse_observation(store, _request(observation_id="obs-002"), lambda: pytest.fail("must not execute"), now=NOW)


def _result():
    return {
        "exit_code": 0,
        "stdout_digest": "d" * 64,
        "stderr_digest": "e" * 64,
        "started_at": NOW.isoformat().replace("+00:00", "Z"),
        "completed_at": (NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    }


def _native_event(**changes):
    event = {
        "event_id": "event-template",
        "timestamp": NOW.isoformat().replace("+00:00", "Z"),
        "process_id": "process-c01",
        "stage": "completion",
        "attempt_id": "attempt-c01",
        "event_type": "stage_started",
        "enforcement_mode": "native",
        "join_ids": {
            "specification_id": "spec-001",
            "plan_id": "plan-001",
            "phase_id": "phase-c",
            "task_id": "task-c01",
            "review_id": None,
            "evaluation_id": None,
        },
        "clocks": {"wall_ms": 1, "active_ms": 1, "billed_ms": None},
        "finding_class": None,
        "return_reason": None,
        "owner": "task-c01",
        "identity": {"product_tree": "1" * 40, "artifact_digest": "a" * 64, "mutation_epoch": 0},
        "privacy": "operational_metadata_only",
    }
    event.update(changes)
    return event


def _stage_events_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "work-bundle" / "stage_events.py"
    spec = importlib.util.spec_from_file_location("_c01_stage_events", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    # Unit-test ownership after the independently tested stage-gate boundary.
    monkeypatch.setattr(execution_context, "_find_plan", lambda *_: (tmp_path / "plan.md", {}))
    monkeypatch.setattr("review_runtime.require_plan_reviews", lambda *_: None)
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
    monkeypatch.setattr(execution_context, "_find_plan", lambda *_: (tmp_path / "plan.md", {}))
    monkeypatch.setattr("review_runtime.require_plan_reviews", lambda *_: None)
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


def test_different_observation_identities_execute_concurrently(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    executing = threading.Barrier(2)

    def invoke(number):
        def run():
            executing.wait(timeout=2)
            # Re-enter a store operation while the other observation is running.
            assert store.mutation_epoch == 0
            return _result()
        return reuse_observation(store, _request(observation_id=f"parallel-{number}",
            command_digest=str(number) * 64), run, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(list(pool.map(invoke, (1, 2)))) == 2


def test_epoch_revocation_during_execution_prevents_publication(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    def run():
        record_relevant_mutation(store, "concurrent revocation")
        return _result()
    with pytest.raises(CompletionProvenanceError, match="epoch"):
        reuse_observation(store, _request(), run, now=NOW)
    with store.locked():
        assert store._read_unlocked()["observations"] == []


def test_failed_execution_releases_identity_reservation_for_retry(tmp_path):
    store = ManagedProvenanceStore(tmp_path)
    def fail():
        raise RuntimeError("interrupted execution")
    with pytest.raises(RuntimeError, match="interrupted"):
        reuse_observation(store, _request(), fail, now=NOW)
    result = reuse_observation(store, _request(), _result, now=NOW)
    assert result.reuse_of is None


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


def test_completion_claim_deduplicates_and_consumes_once_with_native_events(tmp_path):
    store = ManagedProvenanceStore(tmp_path / "provenance")
    events_root = tmp_path / "events"
    events_root.mkdir()
    calls = 0

    def run():
        nonlocal calls
        calls += 1
        return _result()

    first = claim_observation_identity(
        store,
        _request(),
        run,
        finalization_id="final-001",
        now=NOW,
        stage_event_workspace=events_root,
        stage_event=_native_event(),
    )
    second = claim_observation_identity(
        store,
        _request(observation_id="obs-002", invocation_id="invoke-002"),
        run,
        finalization_id="final-001",
        now=NOW,
        stage_event_workspace=events_root,
        stage_event=_native_event(),
    )

    assert calls == 1
    assert first.consumed_by_finalization == "final-001"
    assert second.reuse_of == first.observation_id
    assert second.consumed_by_finalization == "final-001"
    with pytest.raises(CompletionProvenanceError, match="already consumed"):
        claim_observation_identity(
            store,
            _request(observation_id="obs-003", invocation_id="invoke-003"),
            run,
            finalization_id="final-002",
            now=NOW,
        )
    events = _stage_events_module().query_stage_events(events_root)
    assert [event.event_type for event in events] == ["suite_completed", "suite_reused"]
    assert all(event.enforcement_mode == "native" for event in events)


def test_failure_resume_and_release_preserve_first_owner_and_emit_native_events(tmp_path):
    store = ManagedProvenanceStore(tmp_path / "provenance")
    events_root = tmp_path / "events"
    events_root.mkdir()
    FailureOwnershipV1.create(store, "bind-c01", "isolated_worktree", "task-c01")

    retained = retain_binding_owner(
        store,
        "bind-c01",
        repair_owner="repair-c01",
        reason="validation failed",
        stage_event_workspace=events_root,
        stage_event=_native_event(),
    )
    assert retained.original_owner == "task-c01"
    assert resolve_completion_owner(store, "bind-c01") == "repair-c01"
    with pytest.raises(CompletionProvenanceError, match="current owner"):
        resume_failed_stage(store, "bind-c01", owner="task-c01")
    resumed = resume_failed_stage(
        store,
        "bind-c01",
        owner="repair-c01",
        stage_event_workspace=events_root,
        stage_event=_native_event(),
    )
    ready = resumed.complete_repair("repair-c01", "review-c01").complete_rereview("review-c01")
    released = release_completion_binding(
        store,
        "bind-c01",
        owner="task-c01",
        stage_event_workspace=events_root,
        stage_event=_native_event(),
    )

    assert ready.original_owner == released.original_owner == "task-c01"
    assert released.state == "released"
    events = _stage_events_module().query_stage_events(events_root)
    assert [event.event_type for event in events] == ["binding_retained", "stage_started", "binding_released"]


def test_execution_workspace_cleanup_rejects_retained_binding():
    module = execution_context._execution_workspace_module()
    retained = {
        "binding_id": "bind-c01",
        "target_kind": "isolated_worktree",
        "state": "repair_owned",
        "original_owner": "task-c01",
        "current_owner": "repair-c01",
        "reason": "validation failed",
        "repair_owner": "repair-c01",
        "rereview_owner": None,
        "releasable": False,
        "history": [{
            "transition_id": "transition-c01",
            "from": "active",
            "to": "repair_owned",
            "owner": "repair-c01",
            "reason": "validation failed",
            "timestamp": NOW.isoformat().replace("+00:00", "Z"),
        }],
    }
    with pytest.raises(module.ExecutionWorkspaceError, match="WB_EXECUTION_BINDING_RETAINED"):
        module.assert_binding_released_for_cleanup(retained)
    released = {**retained, "state": "released", "current_owner": "task-c01", "repair_owner": None, "releasable": True}
    assert module.assert_binding_released_for_cleanup(released)["original_owner"] == "task-c01"


def test_completed_task_transition_releases_active_binding_and_persists_workspace_owner(tmp_path, monkeypatch):
    control_root = tmp_path / "workspace"
    (control_root / ".work-bundle").mkdir(parents=True)
    store = ManagedProvenanceStore(control_root / ".work-bundle/runtime/completion-provenance")
    created = FailureOwnershipV1.create(store, "binding:plan-001:task-c01", "isolated_worktree", "task-c01")
    binding = {
        "plan_id": "plan-001",
        "task_id": "task-c01",
        "workspace_id": "workspace-001",
        "execution_id": "execution-c01",
        "repository_id": "repo-main",
        "runtime_root": str(tmp_path / "runtime"),
        "ownership": created.to_dict(),
    }
    persisted = []
    retained = []

    monkeypatch.setattr(plans, "resolve_workspace_root", lambda _args: control_root)
    monkeypatch.setattr(plans, "load_task_execution_binding", lambda *_args: binding)
    monkeypatch.setattr(plans, "_persist_binding", lambda value, _root: persisted.append(value))
    monkeypatch.setattr(
        plans,
        "_execution_workspace_module",
        lambda: type("Workspace", (), {"retain_binding_owner": staticmethod(lambda *args, **kwargs: retained.append((args, kwargs)))})(),
    )

    released = plans._release_completed_task_binding(
        type("Args", (), {"workspace_root": str(control_root)})(),
        {"id": "task-c01", "plan_id": "plan-001", "phase_id": "phase-c"},
    )

    assert released["state"] == "released"
    assert persisted[0]["ownership"] == released
    assert retained[0][1]["ownership"] == released
