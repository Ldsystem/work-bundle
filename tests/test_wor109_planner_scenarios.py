from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = ROOT / "scripts/orchestration"
WORK_BUNDLE = ROOT / "scripts/work-bundle"
sys.path.insert(0, str(ORCHESTRATION))

from review_runtime import route_review_verdict  # noqa: E402
import execution_context  # noqa: E402
from test_wor109_accepted_result import _binding, _handoff, _task, _validated  # noqa: E402

sys.path.insert(0, str(WORK_BUNDLE))
from stage_events import derive_planning_economics, validate_stage_event  # noqa: E402


ZERO_SHA = "0" * 64
ZERO_TREE = "0" * 40


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def planning_contracts() -> tuple[str, ...]:
    return (
        read("skills/orch-create-implementation-plan/SKILL.md"),
        read("rules/orchestration/orch-artifact-authoring.md"),
        read("references/assets/orchestration/contract/plan-v1.md"),
        read("references/assets/orchestration/workflow.md"),
    )


def stage_event(
    event_id: str,
    *,
    stage: str = "implementation",
    event_type: str = "stage_started",
    task_id: str | None = None,
    review_id: str | None = None,
) -> object:
    return validate_stage_event(
        {
            "event_id": event_id,
            "timestamp": "2026-09-07T00:00:00Z",
            "process_id": "process-001",
            "stage": stage,
            "attempt_id": event_id,
            "event_type": event_type,
            "enforcement_mode": "native",
            "join_ids": {
                "specification_id": "spec-001",
                "plan_id": "plan-001",
                "phase_id": "phase-001",
                "task_id": task_id,
                "review_id": review_id,
                "evaluation_id": None,
            },
            "clocks": {"wall_ms": 1, "active_ms": 1, "billed_ms": None},
            "finding_class": None,
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
    for contract in planning_contracts():
        assert "task or phase cardinality" in contract
        assert "expected total orchestration cost" in contract
        assert "production, dependency, validation, review, and repair seams" in contract


def test_pd_02_helper_allocation_cannot_leave_production_lifecycle_unowned() -> None:
    for contract in planning_contracts():
        assert "authoritative production path" in contract
        assert "production owner" in contract
        assert "helper-only" in contract


def test_pd_03_executor_acceptance_path_has_explicit_controller_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    execution = read("skills/orch-execute-plan/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    assert "TaskOwnershipScheduler.validate_acceptance" in execution
    assert "validate the executor-result with the shared helper" in execution
    assert "Schedulers own dependencies, barriers, context compilation" in workflow
    assert "they do not perform code-quality review or mutate task write scope" in workflow

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
    planner = read("skills/orch-create-implementation-plan/SKILL.md")
    assert "Split independently owned entry points only when current repository evidence proves distinct ownership or repair seams" in planner
    assert "bounded failure radius" in planner


def test_pd_05_coherent_mechanical_increment_is_not_micro_tasked_by_file_count() -> None:
    for contract in planning_contracts():
        assert "coherent mechanical increment" in contract
        assert "one owner, oracle, and repair frontier" in contract


def test_pd_06_producer_convergence_requires_a_real_barrier_and_owner() -> None:
    planner = read("skills/orch-create-implementation-plan/SKILL.md")
    plan_contract = read("references/assets/orchestration/contract/plan-v1.md")
    assert "actual barrier or convergence boundary" in planner
    assert "explicit barrier ID, readiness evidence, and convergence owner" in planner
    assert "actual barrier or convergence boundary" in plan_contract


def test_pd_07_load_bearing_specification_authority_survives_compaction() -> None:
    specification = read("skills/orch-create-specification/SKILL.md")
    assert "complete, nonredundant authoritative specification" in specification
    assert "Preserve every load-bearing requirement, constraint, interface, acceptance criterion, validation target, and decision" in specification
    assert "Reject duplicate prose that adds no authority" in specification


def test_pd_08_planning_economics_are_derived_without_cardinality_judgment() -> None:
    records = [
        stage_event("phase"),
        stage_event("task-a", task_id="task-a"),
        stage_event("task-b", task_id="task-b"),
        stage_event(
            "accepted",
            stage="integrated_implementation",
            event_type="stage_completed",
            review_id="review-001",
        ),
    ]
    result = derive_planning_economics(records, process_id="process-001", plan_id="plan-001")
    assert result["initial_cardinality"] == {"phases": 1, "tasks": 2}
    assert result["plan_revisions"] == 0
    assert set(result) == {
        "initial_cardinality",
        "plan_revisions",
        "plan_reviews",
        "scope_allocation_repairs",
        "task_review_repairs",
        "validation_reruns",
        "first_green_to_final_accept_ms",
    }


def test_pd_09_under_decomposition_returns_only_the_affected_plan_region() -> None:
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


def test_pd_10_hypothetical_defects_do_not_create_speculative_tasks() -> None:
    for contract in planning_contracts():
        assert "speculative" in contract
        assert "dependency, ownership, validation" in contract
    assert "Do not create speculative splits unsupported by current authority" in planning_contracts()[0]


def test_pd_11_same_owner_pre_mutation_path_amendment_stays_lightweight() -> None:
    lightweight = read("skills/dev-create-task-plan/SKILL.md")
    assert "Before the first write" in lightweight
    assert "exactly one additional path" in lightweight
    assert "same implementation owner" in lightweight
    assert "materially unchanged" in lightweight


def test_pd_12_material_lightweight_scope_pressure_escalates() -> None:
    lightweight = read("skills/dev-create-task-plan/SKILL.md")
    for boundary in (
        "new production or lifecycle owner",
        "independent validation boundary",
        "wide impact",
        "API or workflow decision",
        "second repository",
        "barrier or convergence topology",
    ):
        assert boundary in lightweight
    assert "stop and escalate to full orchestration" in lightweight


def test_pd_13_normal_lightweight_change_remains_one_disposable_plan() -> None:
    lightweight = read("skills/dev-create-task-plan/SKILL.md")
    assert "Keep one disposable `.work-bundle/runtime/dev-plans/` artifact" in lightweight
    for forbidden_import in ("executor-result", "`Completed`", "review package", "archive helper"):
        assert forbidden_import in lightweight
    assert "Do not import" in lightweight


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
    lightweight = read("skills/dev-create-task-plan/SKILL.md")
    assert routed["action"] == "reslice_plan"
    assert routed["silent_expansion_allowed"] is False
    assert "materially under-decomposed" in lightweight
    assert "stop and escalate to full orchestration" in lightweight
    assert "must not be repeated" in lightweight
