from __future__ import annotations

import json
import sys
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
    publish_review,
    resume_plan_return,
    _route_review_finding as route_review_verdict,
)
import execution_context  # noqa: E402
from test_orchestration_accepted_result import _binding, _handoff, _task, _validated  # noqa: E402

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


def development_case(case_id: str) -> dict[str, object]:
    payload = json.loads(read("references/evals/development/evals.json"))
    return next(case for case in payload["evals"] if case["id"] == case_id)


def orchestration_case(case_id: str) -> dict[str, object]:
    payload = json.loads(read("references/evals/orchestration/evals.json"))
    return next(case for case in payload["evals"] if case["id"] == case_id)


def assert_normative_case(
    case_id: str,
    *,
    prompt: str,
    expected_output: str,
    skill_path: str,
    owning_clause: str,
) -> None:
    assert orchestration_case(case_id) == {
        "id": case_id,
        "prompt": prompt,
        "expected_output": expected_output,
        "files": [],
    }
    assert owning_clause in read(skill_path)


def assert_development_case(
    case_id: str,
    *,
    prompt: str,
    expected_output: str,
    owning_clauses: tuple[str, ...],
) -> None:
    assert development_case(case_id) == {
        "id": case_id,
        "prompt": prompt,
        "expected_output": expected_output,
    }
    skill = read("skills/dev-create-task-plan/SKILL.md")
    for clause in owning_clauses:
        assert clause in skill


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
    assert_normative_case(
        "PD-01",
        prompt="Plan a change whose production seams support six tasks, while a reviewer proposes a three-task target to make the plan shorter.",
        expected_output="Rejects the task-count target and does not optimize task or phase cardinality; it uses the six evidenced ownership, dependency, validation, review, and repair seams when they bound expected total orchestration cost.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="Do not optimize task or phase cardinality. Decompose only at concrete independently owned production, dependency, validation, review, and repair seams so expected total orchestration cost remains bounded",
    )


def test_pd_02_helper_allocation_cannot_leave_production_lifecycle_unowned() -> None:
    assert_normative_case(
        "PD-02",
        prompt="A plan allocates tests and a helper refactor but leaves the authoritative production path with no implementation owner.",
        expected_output="Rejects helper-only allocation until every authoritative production path has a production owner and the production change, validation, and repair responsibility are explicitly allocated.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="Assign every authoritative production path to a production owner; reject helper-only allocation while its production path is unowned.",
    )


def test_pd_03_executor_acceptance_path_has_explicit_controller_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert_normative_case(
        "PD-02",
        prompt="A plan allocates tests and a helper refactor but leaves the authoritative production path with no implementation owner.",
        expected_output="Rejects helper-only allocation until every authoritative production path has a production owner and the production change, validation, and repair responsibility are explicitly allocated.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="Assign every authoritative production path to a production owner; reject helper-only allocation while its production path is unowned.",
    )

    task = _task(tmp_path)
    binding = _binding(tmp_path)
    persisted: list[dict[str, object]] = []
    monkeypatch.setattr(
        execution_context,
        "load_task_execution_binding",
        lambda *_args: binding,
    )
    monkeypatch.setattr(
        execution_context,
        "_persist_binding",
        lambda value, _root: persisted.append(value),
    )
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
    handoff = _handoff()
    stored_review = handoff.pop("acceptance_review")
    accepted = execution_context.materialize_accepted_task_result(
        tmp_path,
        task,
        handoff,
        _validated(),
        accepted_review=stored_review,
        accepted_at="2026-09-07T00:00:00Z",
    )
    assert "acceptance_review" not in handoff
    assert persisted == [{**binding, "accepted_result": accepted}]
    assert accepted["schema"] == "accepted-task-result-v1"
    assert accepted["owner_identity"]["owner_kind"] == "subagent"
    assert "mutation_events" not in repr(accepted)


def test_pd_04_independently_repairable_entry_points_remain_distinct() -> None:
    assert_normative_case(
        "PD-03",
        prompt="A planner groups two changes that have different owners, validation oracles, and independently routable repair outcomes.",
        expected_output="Splits at the evidenced ownership, oracle, and repair frontier so a failure returns to the smallest affected plan region without widening unrelated accepted work.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="preserving independently falsifiable increments, short evidence loops, exact dependencies, disjoint write scopes, bounded failure radius, and review boundaries",
    )


def test_pd_05_coherent_mechanical_increment_is_not_micro_tasked_by_file_count() -> None:
    assert_normative_case(
        "PD-04",
        prompt="A planner proposes splitting one production edit, its direct contract test, and its local documentation merely because three files are involved.",
        expected_output="Keeps the coherent mechanical increment together under one production owner, oracle, and repair frontier; file count is not a decomposition seam.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="Keep one coherent mechanical increment with one owner, oracle, and repair frontier together.",
    )


def test_pd_06_producer_convergence_requires_a_real_barrier_and_owner() -> None:
    assert_normative_case(
        "PD-05",
        prompt="A plan creates a new phase for each lifecycle label even though no dependency barrier or convergence boundary separates the work.",
        expected_output="Rejects lifecycle-label phases and creates a phase only for an actual barrier or convergence boundary with concrete readiness and ownership evidence.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="Create a phase only for an actual barrier or convergence boundary, with explicit barrier ID, readiness evidence, and convergence owner.",
    )


def test_pd_07_load_bearing_specification_authority_survives_compaction() -> None:
    assert_normative_case(
        "PD-06",
        prompt="A specification is shortened by deleting a unique validation target and compatibility constraint while retaining repeated summary prose.",
        expected_output="Restores a complete, nonredundant authority set: preserves every load-bearing field required downstream and removes duplicate prose rather than unique authority.",
        skill_path="skills/orch-create-specification/SKILL.md",
        owning_clause="Preserve every load-bearing requirement, constraint, interface, acceptance criterion, validation target, and decision needed downstream; such authority must not be removed merely to make the artifact smaller. Reject duplicate prose that adds no authority.",
    )


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
            "plan-review",
            stage="plan",
            event_type="stage_completed",
            review_id="review-plan",
        ),
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
    assert result["plan_reviews"] == 1
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
    assert_normative_case(
        "PD-07",
        prompt="Execution proves one task materially under-decomposed after its repair frontier separates into two independently owned regions.",
        expected_output="Stops repeatedly enlarging the task, requires a return to the plan, and reslices only the affected region while preserving the original binding, baseline, accepted unaffected regions, and typed repair route.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="When execution proves a task materially under-decomposed, return to the plan and reslice only the affected region around the newly evidenced seam. Preserve the original binding, baseline, and accepted unaffected regions; do not repeatedly enlarge the task.",
    )
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
    publish_review(tmp_path, review, current_target_identity=review["target_identity"])

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
    assert_normative_case(
        "PD-09",
        prompt="A planner proposes separate hardening, compatibility, and recovery tasks without current authority, repository, dependency, validation, or acceptance evidence for them.",
        expected_output="Rejects speculative fragmentation and adds no tasks until a current material seam proves the scope; it does not create a second review, retry, or recovery subsystem.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="Do not create speculative splits unsupported by current authority, repository, dependency, ownership, validation, or acceptance evidence.",
    )


def test_pd_11_same_owner_pre_mutation_path_amendment_stays_lightweight() -> None:
    assert_development_case(
        "dev-lightweight-pre-mutation-one-file-amendment",
        prompt="Before mutation, source grounding shows that a lightweight plan must add one exact file owned by the same implementation owner; purpose, accepted authority, expected delta, impact radius, ownership, validation boundary, and completion claim are materially unchanged.",
        expected_output="Amends Files.Modify once with the exact additional path and records the supporting evidence before the first write, while keeping the same disposable lightweight plan.",
        owning_clauses=(
            "Before the first write, one explicit plan amendment may add exactly one additional path to `Files.Modify` when it has the same implementation owner and purpose, decision authority, expected delta, impact radius, ownership, validation boundary, and completion claim remain materially unchanged.",
            "Record the exact path and supporting evidence in the existing disposable plan.",
        ),
    )


def test_pd_12_material_lightweight_scope_pressure_escalates() -> None:
    assert_development_case(
        "dev-lightweight-material-under-decomposition",
        prompt="Execution reveals that the proposed extra file introduces a new production owner and an independent validation boundary.",
        expected_output="Treats the task as materially under-decomposed and escalates to full orchestration instead of repeatedly expanding the lightweight plan.",
        owning_clauses=(
            "If new evidence makes the task materially under-decomposed—a new production or lifecycle owner, independent validation boundary, wide impact, API or workflow decision, second repository, or barrier or convergence topology—stop and escalate to full orchestration.",
        ),
    )
    assert_development_case(
        "dev-lightweight-amendment-after-mutation",
        prompt="A lightweight task has already mutated an authorized file when it discovers one more file that would otherwise satisfy the bounded amendment conditions.",
        expected_output="Does not amend the mutation envelope after mutation has begun; stops and escalates to full orchestration with the concrete scope evidence.",
        owning_clauses=(
            "The amendment must not be repeated or made after mutation begins.",
        ),
    )


def test_pd_13_normal_lightweight_change_remains_one_disposable_plan() -> None:
    assert_development_case(
        "dev-lightweight-algorithm-not-settled",
        prompt="Plan a bounded mechanical change whose algorithm is not yet chosen, while purpose, accepted authority, expected delta, and impact radius are settled.",
        expected_output="Allows the disposable lightweight plan because eligibility does not require a settled implementation strategy; it does not import executor-result, Completed, or a review package. Eval JSON stores this as a pressure scenario; presence is not executed agent-behavior proof.",
        owning_clauses=(
            "Create a bounded mechanical plan when purpose, accepted or `none relevant` authority, expected delta, and impact radius are settled even if the internal algorithm is not chosen.",
            "Eligibility does not require the internal implementation strategy to be settled.",
        ),
    )
    assert_development_case(
        "dev-lightweight-amendment-lane-separation",
        prompt="A pre-mutation one-file amendment remains same-owner and mechanically bounded, but the agent proposes adding an executor result, task state, review package, and archive record for assurance.",
        expected_output="Allows only the exact bounded Files.Modify amendment and rejects heavy lifecycle artifacts; the lightweight lane remains one disposable plan.",
        owning_clauses=(
            "Keep one disposable `.work-bundle/runtime/dev-plans/` artifact.",
            "Do not import executor-result, `Completed`, review package, archive helper, or heavy Knowledge Base Update closure into the lightweight lane.",
        ),
    )


def test_pd_14_equivalent_under_decomposition_routes_by_lane_without_widening(
    tmp_path: Path,
) -> None:
    assert_development_case(
        "dev-lightweight-material-under-decomposition",
        prompt="Execution reveals that the proposed extra file introduces a new production owner and an independent validation boundary.",
        expected_output="Treats the task as materially under-decomposed and escalates to full orchestration instead of repeatedly expanding the lightweight plan.",
        owning_clauses=(
            "If new evidence makes the task materially under-decomposed—a new production or lifecycle owner, independent validation boundary, wide impact, API or workflow decision, second repository, or barrier or convergence topology—stop and escalate to full orchestration.",
        ),
    )
    assert_normative_case(
        "PD-07",
        prompt="Execution proves one task materially under-decomposed after its repair frontier separates into two independently owned regions.",
        expected_output="Stops repeatedly enlarging the task, requires a return to the plan, and reslices only the affected region while preserving the original binding, baseline, accepted unaffected regions, and typed repair route.",
        skill_path="skills/orch-create-implementation-plan/SKILL.md",
        owning_clause="When execution proves a task materially under-decomposed, return to the plan and reslice only the affected region around the newly evidenced seam. Preserve the original binding, baseline, and accepted unaffected regions; do not repeatedly enlarge the task.",
    )
    binding = {"binding_id": "binding-task-003", "sha256": "1" * 64}
    baseline = {"head": "2" * 40, "tree": "3" * 40}
    unaffected = [
        {
            "artifact_id": "task-001",
            "revision": "1",
            "sha256": ZERO_SHA,
            "source_tree": ZERO_TREE,
        },
        {
            "artifact_id": "task-002",
            "revision": "1",
            "sha256": "4" * 64,
            "source_tree": "5" * 40,
        },
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
    assert routed["action"] == "reslice_plan"
    assert routed["affected_region"] == region
    assert routed["preserved_evidence_identities"] == unaffected
    assert routed["silent_expansion_allowed"] is False
    assert routed["preserve_valid_work_and_evidence"] is True

    orch = tmp_path / ".work-bundle/orchestration"
    spec = orch / "spec/active/spec.md"
    plan = orch / "plan/active/plan.md"
    spec.parent.mkdir(parents=True)
    plan.parent.mkdir(parents=True)
    spec.write_text("---\nid: spec-test\nstatus: verified\n---\nAuthority\n", encoding="utf-8")
    plan.write_text(
        "---\nid: plan-001\nstatus: Planned\nsource_spec: [spec-test]\n---\nResliced\n",
        encoding="utf-8",
    )
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
        "review_id": "review-plan-pd14",
        "stage": "plan",
        "target_identity": plan_review_identity(tmp_path, plan),
        "reviewer": {
            "agent_id": "reviewer-pd14",
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
    publish_review(tmp_path, review, current_target_identity=review["target_identity"])

    resumed = resume_plan_return(
        routed,
        workspace_root=tmp_path,
        plan_path=plan,
        current_binding_identity=binding,
        current_baseline_identity=baseline,
        current_unaffected_evidence_identities=unaffected,
    )
    assert resumed["execution_state"] == "ready_from_repaired_authority"
    assert resumed["affected_region"] == region
    assert resumed["preserved_evidence_identities"] == unaffected
