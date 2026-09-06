from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


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
    route_review_verdict,
)
from stage_events import StageEventError, validate_stage_event  # noqa: E402


ZERO_SHA = "0" * 64
ZERO_TREE = "0" * 40


def identity(artifact_id: str, revision: str = "1") -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "revision": revision,
        "sha256": ZERO_SHA,
        "source_tree": ZERO_TREE,
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


def event() -> dict[str, object]:
    return {
        "event_id": "event-economics",
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
        "planning_economics": {
            "initial_cardinality": {"phases": 1, "tasks": 6},
            "plan_revisions": 2,
            "plan_reviews": 3,
            "scope_allocation_repairs": 1,
            "task_review_repairs": 2,
            "validation_reruns": 4,
            "first_green_to_final_accept_ms": 1200,
        },
    }


def test_pd_07_returns_only_affected_region_and_preserves_unaffected_evidence() -> None:
    preserved = [identity("task-001"), identity("task-002")]

    routed = route_review_verdict(
        allocation_gap(),
        affected_region=["task-003"],
        unaffected_evidence_identities=preserved,
    )

    assert routed["execution_state"] == "paused_for_reslice"
    assert routed["affected_region"] == ["task-003"]
    assert routed["returned_authority_identity"] == identity("plan-001")
    assert routed["preserved_evidence_identities"] == preserved
    assert routed["resume_requires"] == "accepted_repaired_plan_authority"
    assert routed["preserve_original_binding"] is True
    assert routed["preserve_original_baseline"] is True
    assert routed["silent_expansion_allowed"] is False


def test_pd_07_resume_waits_for_new_authority_and_exact_preserved_evidence() -> None:
    preserved = [identity("task-001")]
    routed = route_review_verdict(
        allocation_gap(),
        affected_region=["task-003"],
        unaffected_evidence_identities=preserved,
    )

    with pytest.raises(ReviewContractError, match="repaired authority"):
        resume_plan_return(
            routed,
            accepted_repaired_authority_identity=identity("plan-001"),
            current_unaffected_evidence_identities=preserved,
        )

    changed = deepcopy(preserved)
    changed[0]["revision"] = "2"
    with pytest.raises(ReviewContractError, match="unaffected evidence"):
        resume_plan_return(
            routed,
            accepted_repaired_authority_identity=identity("plan-001", "2"),
            current_unaffected_evidence_identities=changed,
        )

    resumed = resume_plan_return(
        routed,
        accepted_repaired_authority_identity=identity("plan-001", "2"),
        current_unaffected_evidence_identities=preserved,
    )
    assert resumed["execution_state"] == "ready_from_repaired_authority"
    assert resumed["preserved_evidence_identities"] == preserved


@pytest.mark.parametrize("affected_region", [[], ["task-003", "task-003"], [""]])
def test_pd_07_rejects_unbounded_or_ambiguous_affected_regions(affected_region) -> None:
    with pytest.raises(ReviewContractError, match="affected region"):
        route_review_verdict(allocation_gap(), affected_region=affected_region)


def test_pd_08_emits_closed_nonjudgmental_planning_economics() -> None:
    value = event()
    validated = validate_stage_event(value)

    assert validated.to_dict()["planning_economics"] == value["planning_economics"]

    # Cardinality is observed, not judged: large and zero values remain valid metadata.
    value["planning_economics"]["initial_cardinality"] = {"phases": 0, "tasks": 100_000}
    assert validate_stage_event(value).planning_economics["initial_cardinality"]["tasks"] == 100_000

    schema = json.loads(
        (REPO_ROOT / "references/assets/orchestration/contract/stage-event-v1.schema.json").read_text()
    )
    assert schema["$defs"]["stageEvent"]["properties"]["planning_economics"] == {
        "$ref": "#/$defs/planningEconomics"
    }
    assert schema["$defs"]["planningEconomics"]["additionalProperties"] is False


def test_pd_08_economics_is_closed_and_allows_pending_accept_latency() -> None:
    value = event()
    value["planning_economics"]["first_green_to_final_accept_ms"] = None
    assert validate_stage_event(value).planning_economics["first_green_to_final_accept_ms"] is None

    value["planning_economics"]["task_count_verdict"] = "too-many"
    with pytest.raises(StageEventError, match="WB_STAGE_EVENT_ECONOMICS_INVALID"):
        validate_stage_event(value)
