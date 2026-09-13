from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/orchestration"))
sys.path.insert(0, str(ROOT / "scripts/work-bundle"))

import review_runtime  # noqa: E402
import reviewer_workspace  # noqa: E402


ZERO_SHA = "0" * 64
ZERO_TREE = "0" * 40


def observation() -> dict[str, object]:
    raw = {
        "finding_id": "finding-observed",
        "severity": "blocking",
        "requirement_id": "REQ-ROUTE",
        "boundary": "src/runtime.py:route",
        "evidence": "The current route is fixed by the adapter.",
        "expected": "The controller selects a bounded action.",
        "observed": "Severity selected repair_task.",
        "owner": "reviewer-observed-owner",
    }
    return {
        "schema": "review-finding-v2",
        "finding_id": raw["finding_id"],
        "stage": "implementation",
        "reviewer_observation": raw,
        "evidence": [{
            "kind": "source",
            "locator": raw["boundary"],
            "digest_or_identity": ZERO_SHA,
            "observation": raw["evidence"],
        }],
        "target_identity": {
            "artifact_id": "task-route", "revision": "1", "sha256": ZERO_SHA,
            "source_tree": ZERO_TREE,
        },
        "summary": "REQ-ROUTE: Severity selected repair_task.",
        "controller_decision": None,
    }


def decision(**overrides: object) -> dict[str, object]:
    value = {
        "classification": "implementation_defect",
        "first_broken_artifact": "plan",
        "affected_owner": "plan_owner",
        "action": "repair_plan",
        "obligation_basis": "accepted_requirement",
        "evidence_basis": "The accepted plan owns the missing routing allocation.",
    }
    value.update(overrides)
    return value


def test_v2_controller_decision_routes_without_class_to_remedy_mapping() -> None:
    raw = observation()
    validated = review_runtime.validate_review_finding(raw)
    assert validated.controller_decision is None
    assert validated.reviewer_observation == raw["reviewer_observation"]

    classified = review_runtime.classify_review_observation(raw, decision())
    routed = review_runtime._route_review_finding(classified)
    assert routed["first_broken_artifact"] == "plan"
    assert routed["return_to"] == "plan_owner"
    assert routed["action"] == "repair_plan"


def test_v2_routing_requires_agent_decision_and_rejects_unsafe_representation() -> None:
    with pytest.raises(review_runtime.ReviewContractError, match="controller decision"):
        review_runtime._route_review_finding(observation())
    with pytest.raises(review_runtime.ReviewContractError, match="affected_owner"):
        review_runtime.classify_review_observation(
            observation(), decision(affected_owner="arbitrary_owner")
        )
    terminal = review_runtime.classify_review_observation(
        observation(), decision(action="accepted")
    )
    with pytest.raises(review_runtime.ReviewContractError, match="terminal"):
        review_runtime._route_review_finding(terminal)
    reslice = review_runtime.classify_review_observation(
        observation(), decision(action="reslice_plan")
    )
    with pytest.raises(review_runtime.ReviewContractError, match="affected region"):
        review_runtime._route_review_finding(reslice)


def test_v1_fixed_mapping_remains_legacy_only() -> None:
    legacy = {
        "finding_id": "legacy-finding", "stage": "implementation",
        "class": "implementation_defect", "severity": "blocking",
        "first_broken_artifact": "implementation", "obligation_basis": "accepted_requirement",
        "evidence": [{"kind": "source", "locator": "src/runtime.py", "digest_or_identity": ZERO_SHA,
                      "observation": "Legacy observation."}],
        "target_identity": {"artifact_id": "task-route", "revision": "1", "sha256": ZERO_SHA,
                            "source_tree": ZERO_TREE},
        "summary": "Legacy finding.", "recommended_owner": "task_owner",
        "disposition": "repair_task",
    }
    assert review_runtime._route_review_finding(legacy)["action"] == "repair_task"
    legacy["disposition"] = "repair_plan"
    with pytest.raises(review_runtime.ReviewContractError, match="disposition"):
        review_runtime.validate_review_finding(legacy)


def test_task_adapter_preserves_reviewer_observation_without_routing_decision() -> None:
    identity = {
        "artifact_id": "task-route", "revision": "1", "sha256": ZERO_SHA,
        "source_tree": ZERO_TREE,
    }
    context = {
        "target_identity": identity, "agent_id": "reviewer", "capability": "judgment",
        "execution_id": "reviewer-run", "evidence_mode": "reproducible_snapshot",
        "review_mode": "initial", "review_target_kind": "task", "repair_frontier": None,
        "review_reset": None,
    }
    raw = observation()["reviewer_observation"]
    judgment = {"task_review": {
        "reviewed_head": identity["revision"], "verdict": "repair", "findings": [raw]
    }}
    result = reviewer_workspace._task_product_judgment_review(
        judgment, review_id="review-route", context=context, packet={"artifacts": []},
        started_at="2026-09-13T00:00:00Z", completed_at="2026-09-13T00:01:00Z",
    )
    finding = result["findings"][0]
    assert finding["reviewer_observation"] == raw
    assert finding["controller_decision"] is None
    assert "class" not in finding and "disposition" not in finding


def test_review_finding_v2_schema_matches_runtime_shape() -> None:
    schema = json.loads(
        (ROOT / "references/assets/orchestration/contract/review-finding-v2.schema.json").read_text()
    )
    assert schema["$id"] == "urn:work-bundle:orchestration:review-finding:v2"
    assert set(schema["$defs"]["reviewFindingV2"]["required"]) == set(
        review_runtime.FINDING_V2_KEYS
    )
    assert review_runtime.validate_contract_instance(
        "reviewFindingV2", observation()
    ).finding_id == "finding-observed"
    assert review_runtime.validate_contract_instance(
        "API-001", observation()
    ).finding_id == "finding-observed"
