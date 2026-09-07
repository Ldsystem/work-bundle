from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from reviewer_run_fixtures import bind_review_receipt


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = ROOT / "scripts/orchestration"
WORK_BUNDLE = ROOT / "scripts/work-bundle"
sys.path.insert(0, str(ORCHESTRATION))

from review_runtime import (  # noqa: E402
    ReviewContractError,
    plan_review_identity,
    resume_plan_return,
    route_review_verdict,
)
import execution_context  # noqa: E402
from test_wor109_accepted_result import _binding, _handoff, _task, _validated  # noqa: E402
from task_ownership import (  # noqa: E402
    OwnershipBlocker,
    SubagentDispatch,
    TaskCandidate,
    TaskOwnershipScheduler,
)

sys.path.insert(0, str(WORK_BUNDLE))
from stage_events import derive_planning_economics, validate_stage_event  # noqa: E402


ZERO_SHA = "0" * 64
ZERO_TREE = "0" * 40


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def stage_event(
    event_id: str,
    *,
    stage: str = "implementation",
    event_type: str = "stage_started",
    task_id: str | None = None,
    review_id: str | None = None,
    timestamp: str = "2026-09-07T00:00:00Z",
    attempt_id: str | None = None,
    finding_class: str | None = None,
    evaluation_id: str | None = None,
) -> object:
    return validate_stage_event(
        {
            "event_id": event_id,
            "timestamp": timestamp,
            "process_id": "process-001",
            "stage": stage,
            "attempt_id": attempt_id or event_id,
            "event_type": event_type,
            "enforcement_mode": "native",
            "join_ids": {
                "specification_id": "spec-001",
                "plan_id": "plan-001",
                "phase_id": "phase-001",
                "task_id": task_id,
                "review_id": review_id,
                "evaluation_id": evaluation_id,
            },
            "clocks": {"wall_ms": 1, "active_ms": 1, "billed_ms": None},
            "finding_class": finding_class,
            "return_reason": None,
            "owner": "plan_owner",
            "identity": {
                "product_tree": ZERO_TREE,
                "artifact_digest": ZERO_SHA,
                "mutation_epoch": 1,
            },
            "privacy": "operational_metadata_only",
        }
    )


class AvailableAdapter:
    def available(self) -> bool:
        return True

    def dispatch(self, task: TaskCandidate, *, operation: str) -> SubagentDispatch:
        return SubagentDispatch(
            task.task_id,
            {
                "delegated": True,
                "owner_kind": "subagent",
                "agent_id": f"agent-{task.task_id}",
                "run_id": f"run-{task.task_id}",
                "mechanism": "host-native",
            },
        )

    def wait(self, handle: object) -> object:
        return {"completed": handle}


class UnavailableAdapter(AvailableAdapter):
    def available(self) -> bool:
        return False


def candidate(
    task_id: str,
    *paths: str,
    dependencies: tuple[str, ...] = (),
    common_contract: str | None = None,
    barrier: str | None = None,
    convergence_owner: str | None = None,
    barrier_participants: tuple[str, ...] = (),
) -> TaskCandidate:
    return TaskCandidate(
        task_id=task_id,
        dependencies=dependencies,
        write_scope=paths,
        execution_workspace=f"workspace-{task_id}",
        common_contract=common_contract,
        barrier=barrier,
        convergence_owner=convergence_owner,
        barrier_participants=barrier_participants,
    )


def development_case(case_id: str) -> dict[str, object]:
    payload = json.loads(read("references/evals/development/evals.json"))
    return next(case for case in payload["evals"] if case["id"] == case_id)


def allocation_gap() -> dict[str, object]:
    return {
        "finding_id": "finding-under-decomposed",
        "stage": "implementation",
        "class": "allocation_gap",
        "severity": "blocking",
        "first_broken_artifact": "plan",
        "obligation_basis": "accepted_requirement",
        "evidence": [
            {
                "kind": "runtime",
                "locator": "task-003",
                "digest_or_identity": "independent-repair-frontiers",
                "observation": "Two independently owned regions now fail separately.",
            }
        ],
        "target_identity": {
            "artifact_id": "plan-001",
            "revision": "1",
            "sha256": ZERO_SHA,
            "source_tree": ZERO_TREE,
        },
        "summary": "The task is materially under-decomposed.",
        "recommended_owner": "plan_owner",
        "disposition": "reslice_plan",
    }


def test_pd_01_cardinality_never_overrides_evidenced_runtime_seams() -> None:
    tasks = [candidate(f"task-{index:03d}", f"src/seam-{index}.py") for index in range(1, 7)]
    result = TaskOwnershipScheduler(AvailableAdapter()).run_wave(tasks, completed=set())

    assert result.dispatched == tuple(task.task_id for task in tasks)
    assert len(result.ownership) == 6


def test_pd_02_helper_allocation_cannot_leave_production_lifecycle_unowned() -> None:
    with pytest.raises(OwnershipBlocker, match="subagent execution is unavailable"):
        TaskOwnershipScheduler(UnavailableAdapter()).run_wave(
            [candidate("task-production", "src/production.py")], completed=set()
        )

    scheduler = TaskOwnershipScheduler(AvailableAdapter())
    with pytest.raises(OwnershipBlocker, match="controller mutated task-owned implementation scope"):
        scheduler.validate_acceptance(
            delegation_evidence={
                "delegated": True,
                "owner_kind": "subagent",
                "agent_id": "helper-owner",
                "run_id": "helper-run",
                "mechanism": "host-native",
            },
            mutation_events=[{"actor_kind": "controller", "paths": ["src/production.py"]}],
            write_scope=["src/production.py"],
            validations_passed=True,
        )


def test_pd_03_executor_acceptance_path_has_explicit_controller_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution = read("skills/orch-execute-plan/SKILL.md")
    assert "TaskOwnershipScheduler.validate_acceptance" in execution

    with pytest.raises(OwnershipBlocker, match="requires subagent ownership"):
        TaskOwnershipScheduler(AvailableAdapter()).validate_acceptance(
            delegation_evidence=None,
            mutation_events=[],
            write_scope=["src/production.py"],
            validations_passed=True,
        )

    task = _task(tmp_path)
    binding = _binding(tmp_path)
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {
            "head": "a" * 40,
            "tree": "b" * 40,
            "entries": {},
            "status": "clean",
        },
    )
    first = execution_context.build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-07T00:00:00Z"
    )
    historical = deepcopy(binding)
    historical["ownership"]["history"].append({"event": "historical-audit"})
    second = execution_context.build_accepted_task_result(
        task, historical, _handoff(), _validated(), accepted_at="2026-09-07T00:00:00Z"
    )
    assert first == second
    assert "mutation_events" not in repr(first)


def test_pd_04_independently_repairable_entry_points_remain_distinct() -> None:
    tasks = [
        candidate("task-entry-a", "src/entry_a.py"),
        candidate("task-entry-b", "src/entry_b.py"),
    ]
    result = TaskOwnershipScheduler(AvailableAdapter()).run_wave(tasks, completed=set())
    assert result.dispatched == ("task-entry-a", "task-entry-b")
    assert tuple(owner["agent_id"] for owner in result.ownership) == (
        "agent-task-entry-a",
        "agent-task-entry-b",
    )


def test_pd_05_coherent_mechanical_increment_is_not_micro_tasked_by_file_count() -> None:
    task = candidate("task-mechanical", "src/edit.py", "tests/test_edit.py", "docs/edit.md")
    result = TaskOwnershipScheduler(AvailableAdapter()).run_wave([task], completed=set())
    assert result.dispatched == ("task-mechanical",)
    assert len(result.results) == 1


def test_pd_06_producer_convergence_requires_a_real_barrier_and_owner() -> None:
    scheduler = TaskOwnershipScheduler(AvailableAdapter())
    convergence = candidate(
        "task-converge",
        "src/converge.py",
        dependencies=("task-a", "task-b"),
        common_contract="contract-v1",
        barrier="barrier-producers",
        convergence_owner="task-converge",
        barrier_participants=("task-a", "task-b"),
    )
    waiting = scheduler.run_wave(
        [convergence], completed={"task-a", "task-b"}, accepted_handoffs=set()
    )
    released = scheduler.run_wave(
        [convergence],
        completed={"task-a", "task-b"},
        accepted_handoffs={"task-a", "task-b"},
    )
    assert waiting.dispatched == ()
    assert released.dispatched == ("task-converge",)


def test_pd_07_load_bearing_specification_authority_survives_compaction() -> None:
    task = _task(Path("/tmp/wor109-authority"))
    projection = execution_context._accepted_task_projection(task)
    scopes = execution_context._canonical_task_scopes(task)
    validation = execution_context._accepted_validation_projection(task)

    assert projection["source_ids"] == ["REQ-001"]
    assert scopes == {
        "read": ["src/read.py"],
        "write": ["src/a.py"],
        "forbidden": ["secrets/key.txt"],
    }
    assert validation == [
        {
            "id": "VAL-001",
            "command": "pytest -q",
            "boundary": "component",
            "freshness": "current_task_batch",
        }
    ]


def test_pd_08_planning_economics_are_derived_without_cardinality_judgment() -> None:
    records = [
        stage_event("phase"),
        stage_event("task-a", task_id="task-a"),
        stage_event("task-b", task_id="task-b"),
        stage_event(
            "scope-repair",
            event_type="reslice_recorded",
            attempt_id="repair-scope",
            finding_class="allocation_gap",
        ),
        stage_event(
            "task-repair",
            event_type="work_returned",
            task_id="task-a",
            review_id="review-task-a",
            attempt_id="repair-task",
            finding_class="implementation_defect",
        ),
        stage_event("suite-first", event_type="suite_started", evaluation_id="eval-001"),
        stage_event("suite-rerun", event_type="suite_started", evaluation_id="eval-001"),
        stage_event(
            "green",
            event_type="suite_completed",
            evaluation_id="eval-001",
            timestamp="2026-09-07T00:00:01Z",
        ),
        stage_event(
            "accepted",
            stage="integrated_implementation",
            event_type="stage_completed",
            review_id="review-001",
            timestamp="2026-09-07T00:00:02.200Z",
        ),
    ]
    result = derive_planning_economics(records, process_id="process-001", plan_id="plan-001")
    assert result["initial_cardinality"] == {"phases": 1, "tasks": 2}
    assert result["plan_revisions"] == 1
    assert result["scope_allocation_repairs"] == 1
    assert result["task_review_repairs"] == 1
    assert result["validation_reruns"] == 1
    assert result["first_green_to_final_accept_ms"] == 1200
    assert set(result) == {
        "initial_cardinality",
        "plan_revisions",
        "plan_reviews",
        "scope_allocation_repairs",
        "task_review_repairs",
        "validation_reruns",
        "first_green_to_final_accept_ms",
    }


def test_pd_09_under_decomposition_returns_only_the_affected_plan_region(
    tmp_path: Path,
) -> None:
    binding = {"binding_id": "binding-task-003", "sha256": "1" * 64}
    baseline = {"head": "2" * 40, "tree": "3" * 40}
    unaffected = [
        {
            "artifact_id": "task-001",
            "revision": "1",
            "sha256": ZERO_SHA,
            "source_tree": ZERO_TREE,
        }
    ]
    region = {
        "task_ids": ["task-003"],
        "paths": ["scripts/orchestration/review_runtime.py"],
        "interfaces": ["API-PD-001"],
        "validation_oracles": ["VAL-004"],
    }
    routed = route_review_verdict(
        allocation_gap(),
        affected_region=region,
        unaffected_evidence_identities=unaffected,
        original_binding_identity=binding,
        original_baseline_identity=baseline,
    )
    assert routed["execution_state"] == "paused_for_reslice"
    assert routed["affected_region"] == region
    assert routed["preserved_evidence_identities"] == unaffected
    assert routed["silent_expansion_allowed"] is False

    orch = tmp_path / ".work-bundle/orchestration"
    spec = orch / "spec/active/spec.md"
    plan = orch / "plan/active/plan.md"
    spec.parent.mkdir(parents=True)
    plan.parent.mkdir(parents=True)
    spec.write_text("---\nid: spec-test\nstatus: verified\n---\nAuthority\n", encoding="utf-8")
    plan.write_text(
        "---\nid: plan-001\nstatus: Planned\nsource_spec: [spec-test]\n---\nOriginal\n",
        encoding="utf-8",
    )
    plan.write_text(plan.read_text(encoding="utf-8").replace("Original", "Resliced"), encoding="utf-8")

    with pytest.raises(ReviewContractError, match="accepted repaired plan-review authority"):
        resume_plan_return(
            routed,
            workspace_root=tmp_path,
            plan_path=plan,
            current_binding_identity=binding,
            current_baseline_identity=baseline,
            current_unaffected_evidence_identities=unaffected,
        )

    review = {
        "review_id": "review-plan",
        "stage": "plan",
        "target_identity": plan_review_identity(tmp_path, plan),
        "reviewer": {
            "agent_id": "reviewer-1",
            "capability": "judgment",
            "authorship": "none",
            "repair_participation": "none",
            "decision_participation": "none",
            "deliberation_participation": "none",
            "context_origin": "direct_source",
        },
        "evidence": {
            "mode": "direct",
            "capabilities": ["source inspection"],
            "unavailable_evidence": [],
            "commands": [],
            "artifacts": [],
        },
        "verdict": "accepted",
        "findings": [],
        "started_at": "2026-09-07T00:00:00Z",
        "completed_at": "2026-09-07T00:01:00Z",
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }
    review = bind_review_receipt(tmp_path, review)
    reviews = orch / "reviews"
    reviews.mkdir()
    (reviews / "plan.json").write_text(json.dumps(review), encoding="utf-8")

    resumed = resume_plan_return(
        routed,
        workspace_root=tmp_path,
        plan_path=plan,
        current_binding_identity=binding,
        current_baseline_identity=baseline,
        current_unaffected_evidence_identities=unaffected,
    )
    assert resumed["execution_state"] == "ready_from_repaired_authority"
    assert resumed["preserved_evidence_identities"] == unaffected


def test_pd_10_hypothetical_defects_do_not_create_speculative_tasks() -> None:
    finding = allocation_gap()
    finding.update(
        {
            "finding_id": "finding-advisory",
            "class": "advisory_enhancement",
            "severity": "advisory",
            "first_broken_artifact": "implementation",
            "obligation_basis": "none",
            "evidence": [],
            "recommended_owner": "backlog_owner",
            "disposition": "record_advisory",
        }
    )
    routed = route_review_verdict(finding)
    assert routed["return_to"] == "backlog_owner"
    assert routed["action"] == "record_advisory"
    assert routed["execution_state"] == "returned_for_repair"


def test_pd_11_same_owner_pre_mutation_path_amendment_stays_lightweight() -> None:
    case = development_case("dev-lightweight-pre-mutation-one-file-amendment")
    amended = candidate("task-light", "src/original.py", "src/discovered.py")
    result = TaskOwnershipScheduler(AvailableAdapter()).run_wave([amended], completed=set())
    assert "Before mutation" in case["prompt"]
    assert "same implementation owner" in case["prompt"]
    assert "Amends Files.Modify once" in case["expected_output"]
    assert result.dispatched == ("task-light",)
    assert result.ownership[0]["agent_id"] == "agent-task-light"


def test_pd_12_material_lightweight_scope_pressure_escalates() -> None:
    case = development_case("dev-lightweight-material-under-decomposition")
    routed = route_review_verdict(
        allocation_gap(),
        affected_region={
            "task_ids": ["task-light"],
            "paths": ["src/new-owner.py"],
            "interfaces": [],
            "validation_oracles": ["VAL-NEW"],
        },
        original_binding_identity={"binding_id": "binding-light", "sha256": "1" * 64},
        original_baseline_identity={"head": "2" * 40, "tree": "3" * 40},
    )
    assert "new production owner and an independent validation boundary" in case["prompt"]
    assert case["expected_output"] == (
        "Treats the task as materially under-decomposed and escalates to full orchestration "
        "instead of repeatedly expanding the lightweight plan."
    )
    assert routed["action"] == "reslice_plan"
    assert routed["silent_expansion_allowed"] is False


def test_pd_13_normal_lightweight_change_remains_one_disposable_plan() -> None:
    case = development_case("dev-lightweight-amendment-lane-separation")
    result = TaskOwnershipScheduler(AvailableAdapter()).run_wave(
        [candidate("task-light", "src/only.py")], completed=set()
    )
    assert "executor result, task state, review package, and archive record" in case["prompt"]
    assert case["expected_output"] == (
        "Allows only the exact bounded Files.Modify amendment and rejects heavy lifecycle "
        "artifacts; the lightweight lane remains one disposable plan."
    )
    assert result.dispatched == ("task-light",)


def test_pd_14_equivalent_under_decomposition_routes_by_lane_without_widening() -> None:
    routed = route_review_verdict(
        allocation_gap(),
        affected_region={
            "task_ids": ["task-003"],
            "paths": ["scripts/orchestration/review_runtime.py"],
            "interfaces": ["API-PD-001"],
            "validation_oracles": ["VAL-004"],
        },
        original_binding_identity={"binding_id": "binding-task-003", "sha256": "1" * 64},
        original_baseline_identity={"head": "2" * 40, "tree": "3" * 40},
    )
    assert routed["action"] == "reslice_plan"
    assert routed["silent_expansion_allowed"] is False
    assert routed["preserve_valid_work_and_evidence"] is True
    case = development_case("dev-lightweight-material-under-decomposition")
    assert "escalates to full orchestration" in case["expected_output"]
    assert "instead of repeatedly expanding" in case["expected_output"]
