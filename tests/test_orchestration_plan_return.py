from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from reviewer_run_fixtures import bind_review_receipt


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
WORK_BUNDLE = REPO_ROOT / "scripts" / "work-bundle"
for path in (ORCHESTRATION, WORK_BUNDLE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from review_runtime import (  # noqa: E402
    ReviewContractError,
    classify_first_broken_owner,
    resume_plan_return,
    _route_review_finding as route_review_verdict,
)
from stage_events import StageEventError  # noqa: E402


ZERO_SHA = "0" * 64
ZERO_TREE = "0" * 40


def identity(artifact_id: str, revision: str = "1") -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "revision": revision,
        "sha256": ZERO_SHA,
        "source_tree": ZERO_TREE,
    }


def binding_identity() -> dict[str, str]:
    return {"binding_id": "binding-task-003", "sha256": "1" * 64}


def baseline_identity() -> dict[str, str]:
    return {"head": "2" * 40, "tree": "3" * 40}


def affected_region() -> dict[str, list[str]]:
    return {
        "task_ids": ["task-003"],
        "paths": ["scripts/orchestration/review_runtime.py"],
        "interfaces": ["API-PD-001"],
        "validation_oracles": ["VAL-004"],
    }


def allocation_gap() -> dict[str, object]:
    artifact, owner, disposition = classify_first_broken_owner("allocation_gap")
    return {
        "finding_id": "finding-under-decomposed",
        "stage": "implementation",
        "class": "allocation_gap",
        "severity": "blocking",
        "first_broken_artifact": artifact,
        "obligation_basis": "accepted_requirement",
        "evidence": [
            {
                "kind": "runtime",
                "locator": "task-004",
                "digest_or_identity": "repair-frontier-separated",
                "observation": "The task now has two independently owned repair regions.",
            }
        ],
        "target_identity": identity("plan-001"),
        "summary": "The affected task is materially under-decomposed.",
        "recommended_owner": owner,
        "disposition": disposition,
    }


def event(event_id: str = "event-economics", **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "event_id": event_id,
        "timestamp": "2026-09-07T00:00:00Z",
        "process_id": "process-001",
        "stage": "integrated_implementation",
        "attempt_id": "attempt-001",
        "event_type": "stage_completed",
        "enforcement_mode": "native",
        "join_ids": {
            "specification_id": "spec-001",
            "plan_id": "plan-001",
            "phase_id": "phase-001",
            "task_id": None,
            "review_id": "review-001",
            "evaluation_id": None,
        },
        "clocks": {"wall_ms": 13, "active_ms": 8, "billed_ms": None},
        "finding_class": None,
        "return_reason": None,
        "owner": "plan_owner",
        "identity": {
            "product_tree": ZERO_TREE,
            "artifact_digest": ZERO_SHA,
            "mutation_epoch": 2,
        },
        "privacy": "operational_metadata_only",
    }
    value.update(updates)
    return value


def test_pd_07_returns_only_affected_region_and_preserves_unaffected_evidence() -> None:
    preserved = [identity("task-001"), identity("task-002")]

    routed = route_review_verdict(
        allocation_gap(),
        affected_region=affected_region(),
        unaffected_evidence_identities=preserved,
        original_binding_identity=binding_identity(),
        original_baseline_identity=baseline_identity(),
    )

    assert routed["execution_state"] == "paused_for_reslice"
    assert routed["affected_region"] == affected_region()
    assert routed["returned_authority_identity"] == identity("plan-001")
    assert routed["preserved_evidence_identities"] == preserved
    assert routed["resume_requires"] == "accepted_repaired_plan_authority"
    assert routed["original_binding_identity"] == binding_identity()
    assert routed["original_baseline_identity"] == baseline_identity()
    assert routed["silent_expansion_allowed"] is False


def test_pd_07_resume_waits_for_current_accepted_plan_review_and_exact_preserved_state(
    tmp_path: Path,
) -> None:
    orch = tmp_path / ".work-bundle/orchestration"
    spec = orch / "spec/active/spec.md"
    plan = orch / "plan/active/plan.md"
    spec.parent.mkdir(parents=True)
    plan.parent.mkdir(parents=True)
    spec.write_text("---\nid: spec-test\nstatus: verified\n---\nAuthority\n")
    plan.write_text("---\nid: plan-001\nstatus: Planned\nsource_spec: [spec-test]\n---\nOriginal\n")
    preserved = [identity("task-001")]
    routed = route_review_verdict(
        allocation_gap(),
        affected_region=affected_region(),
        unaffected_evidence_identities=preserved,
        original_binding_identity=binding_identity(),
        original_baseline_identity=baseline_identity(),
    )
    plan.write_text(plan.read_text().replace("Original", "Resliced"))

    with pytest.raises(ReviewContractError, match="accepted repaired plan-review authority"):
        resume_plan_return(
            routed,
            workspace_root=tmp_path,
            plan_path=plan,
            current_binding_identity=binding_identity(),
            current_baseline_identity=baseline_identity(),
            current_unaffected_evidence_identities=preserved,
        )

    from review_runtime import plan_review_identity

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
    (reviews / "plan.json").write_text(json.dumps(review))

    changed = deepcopy(preserved)
    changed[0]["revision"] = "2"
    with pytest.raises(ReviewContractError, match="unaffected evidence"):
        resume_plan_return(
            routed,
            workspace_root=tmp_path,
            plan_path=plan,
            current_binding_identity=binding_identity(),
            current_baseline_identity=baseline_identity(),
            current_unaffected_evidence_identities=changed,
        )

    with pytest.raises(ReviewContractError, match="binding identity"):
        resume_plan_return(
            routed,
            workspace_root=tmp_path,
            plan_path=plan,
            current_binding_identity={**binding_identity(), "sha256": "4" * 64},
            current_baseline_identity=baseline_identity(),
            current_unaffected_evidence_identities=preserved,
        )

    with pytest.raises(ReviewContractError, match="baseline identity"):
        resume_plan_return(
            routed,
            workspace_root=tmp_path,
            plan_path=plan,
            current_binding_identity=binding_identity(),
            current_baseline_identity={**baseline_identity(), "tree": "4" * 40},
            current_unaffected_evidence_identities=preserved,
        )

    resumed = resume_plan_return(
        routed,
        workspace_root=tmp_path,
        plan_path=plan,
        current_binding_identity=binding_identity(),
        current_baseline_identity=baseline_identity(),
        current_unaffected_evidence_identities=preserved,
    )
    assert resumed["execution_state"] == "ready_from_repaired_authority"
    assert resumed["preserved_evidence_identities"] == preserved


@pytest.mark.parametrize(
    "region",
    [
        {},
        {**affected_region(), "task_ids": ["task-003", "task-003"]},
        {**affected_region(), "paths": ["../escape"]},
        {**affected_region(), "validation_oracles": [""]},
    ],
)
def test_pd_07_rejects_unbounded_or_ambiguous_affected_regions(region) -> None:
    with pytest.raises(ReviewContractError, match="affected region"):
        route_review_verdict(
            allocation_gap(),
            affected_region=region,
            original_binding_identity=binding_identity(),
            original_baseline_identity=baseline_identity(),
        )


def test_pd_08_stage_event_path_isolates_same_process_different_plan_economics(
    tmp_path: Path,
) -> None:
    from stage_events import append_stage_event, query_stage_events

    events = [
        event("phase", stage="implementation", event_type="stage_started"),
        event(
            "task-a",
            stage="implementation",
            event_type="stage_started",
            join_ids={**event()["join_ids"], "task_id": "task-a"},
        ),
        event(
            "task-b",
            stage="implementation",
            event_type="stage_started",
            join_ids={**event()["join_ids"], "task_id": "task-b"},
        ),
        event(
            "noise-task",
            stage="implementation",
            event_type="stage_started",
            join_ids={
                **event()["join_ids"],
                "plan_id": "plan-noise",
                "phase_id": "phase-noise",
                "task_id": "task-noise",
                "review_id": "review-noise",
            },
        ),
        event(
            "noise-plan-review",
            stage="plan",
            event_type="stage_completed",
            join_ids={
                **event()["join_ids"],
                "plan_id": "plan-noise",
                "review_id": "review-noise",
            },
        ),
        event("plan-review", stage="plan", event_type="stage_completed"),
        event(
            "noise-scope-repair",
            event_type="reslice_recorded",
            finding_class="allocation_gap",
            attempt_id="noise-scope",
            join_ids={**event()["join_ids"], "plan_id": "plan-noise"},
        ),
        event(
            "scope-repair",
            event_type="reslice_recorded",
            finding_class="allocation_gap",
            attempt_id="repair-scope",
        ),
        event(
            "task-repair",
            event_type="work_returned",
            finding_class="implementation_defect",
            attempt_id="repair-task",
            join_ids={**event()["join_ids"], "task_id": "task-a"},
        ),
        event(
            "noise-task-repair",
            event_type="work_returned",
            finding_class="implementation_defect",
            attempt_id="noise-task-repair",
            join_ids={
                **event()["join_ids"],
                "plan_id": "plan-noise",
                "task_id": "task-noise",
                "review_id": "review-noise",
            },
        ),
        event(
            "suite-first",
            event_type="suite_started",
            attempt_id="validation",
            join_ids={**event()["join_ids"], "evaluation_id": "eval-001"},
        ),
        event(
            "suite-rerun",
            event_type="suite_started",
            attempt_id="validation-2",
            join_ids={**event()["join_ids"], "evaluation_id": "eval-001"},
        ),
        event(
            "noise-suite-first",
            event_type="suite_started",
            attempt_id="noise-validation",
            join_ids={
                **event()["join_ids"],
                "plan_id": "plan-noise",
                "evaluation_id": "eval-noise",
            },
        ),
        event(
            "noise-suite-rerun",
            event_type="suite_started",
            attempt_id="noise-validation-2",
            join_ids={
                **event()["join_ids"],
                "plan_id": "plan-noise",
                "evaluation_id": "eval-noise",
            },
        ),
        event(
            "noise-green",
            timestamp="2026-09-07T00:00:00.100Z",
            event_type="suite_completed",
            attempt_id="noise-validation-2",
            join_ids={
                **event()["join_ids"],
                "plan_id": "plan-noise",
                "evaluation_id": "eval-noise",
            },
        ),
        event(
            "green",
            timestamp="2026-09-07T00:00:01Z",
            event_type="suite_completed",
            attempt_id="validation-2",
            join_ids={**event()["join_ids"], "evaluation_id": "eval-001"},
        ),
        event(
            "accepted",
            timestamp="2026-09-07T00:00:02.200Z",
            stage="integrated_implementation",
            event_type="stage_completed",
            attempt_id="final",
        ),
    ]
    result = None
    for item in events:
        result = append_stage_event(tmp_path, item)

    assert result is not None
    assert result.planning_economics == {
        "initial_cardinality": {"phases": 1, "tasks": 2},
        "plan_revisions": 1,
        "plan_reviews": 1,
        "scope_allocation_repairs": 1,
        "task_review_repairs": 1,
        "validation_reruns": 1,
        "first_green_to_final_accept_ms": 1200,
    }
    assert query_stage_events(tmp_path)[-1].planning_economics == result.planning_economics

    schema = json.loads(
        (REPO_ROOT / "references/assets/orchestration/contract/stage-event-v1.schema.json").read_text()
    )
    assert schema["$defs"]["stageEvent"]["properties"]["planning_economics"] == {
        "$ref": "#/$defs/planningEconomics"
    }
    assert schema["$defs"]["planningEconomics"]["additionalProperties"] is False


def test_pd_08_rejects_unbound_integrated_economics_emission(tmp_path: Path) -> None:
    from stage_events import append_stage_event

    unbound = event(
        "unbound-final",
        join_ids={**event()["join_ids"], "plan_id": None},
    )

    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_ECONOMICS_SCOPE_INVALID"):
        append_stage_event(tmp_path, unbound)


def test_pd_08_rejects_caller_injected_economics(tmp_path: Path) -> None:
    from stage_events import append_stage_event

    value = event()
    value["planning_economics"] = {
        "initial_cardinality": {"phases": 0, "tasks": 100_000},
        "plan_revisions": 0,
        "plan_reviews": 0,
        "scope_allocation_repairs": 0,
        "task_review_repairs": 0,
        "validation_reruns": 0,
        "first_green_to_final_accept_ms": None,
    }
    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_ECONOMICS_INVALID"):
        append_stage_event(tmp_path, value)
