from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from review_runtime import (  # noqa: E402
    ReviewContractError,
    classify_first_broken_owner,
    route_review_verdict,
    transition_review_finding,
    validate_contract_instance,
    validate_stage_review,
    validate_stage_reviews,
)


ZERO_SHA = "0" * 64
ZERO_TREE = "0" * 40


def finding(finding_class: str = "implementation_defect") -> dict[str, object]:
    artifact, owner, disposition = classify_first_broken_owner(finding_class)
    return {
        "finding_id": f"finding-{finding_class}",
        "stage": "implementation",
        "class": finding_class,
        "severity": "blocking",
        "first_broken_artifact": artifact,
        "obligation_basis": "accepted_requirement",
        "evidence": [
            {
                "kind": "test",
                "locator": "tests/test_orchestration_reviews.py",
                "digest_or_identity": "VAL-B01",
                "observation": "The focused oracle observed the contract failure.",
            }
        ],
        "target_identity": {
            "artifact_id": "task-b01",
            "revision": "1",
            "sha256": ZERO_SHA,
            "source_tree": ZERO_TREE,
        },
        "summary": "A classified review finding.",
        "recommended_owner": owner,
        "disposition": disposition,
    }


def stage_review(stage: str) -> dict[str, object]:
    return {
        "review_id": f"review-{stage}",
        "stage": stage,
        "target_identity": {
            "artifact_id": f"artifact-{stage}",
            "revision": "1",
            "sha256": ZERO_SHA,
            "source_tree": None if stage != "integrated_implementation" else ZERO_TREE,
        },
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
        "started_at": "2026-09-04T00:00:00Z",
        "completed_at": "2026-09-04T00:01:00Z",
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }


@pytest.mark.parametrize(
    ("finding_class", "expected"),
    [
        ("specification_gap", ("specification", "specification_owner", "reopen_specification")),
        ("decomposition_gap", ("plan", "plan_owner", "repair_plan")),
        ("allocation_gap", ("plan", "plan_owner", "reslice_plan")),
        ("implementation_defect", ("implementation", "task_owner", "repair_task")),
        ("validation_oracle_defect", ("validation_oracle", "oracle_owner", "repair_oracle")),
        ("environment_failure", ("environment", "environment_owner", "recover_environment")),
        ("advisory_enhancement", ("implementation", "backlog_owner", "record_advisory")),
    ],
)
def test_api_001_routes_every_class_to_first_broken_owner(
    finding_class: str, expected: tuple[str, str, str]
) -> None:
    assert classify_first_broken_owner(finding_class) == expected
    record = finding(finding_class)
    if finding_class == "advisory_enhancement":
        record["severity"] = "advisory"
        record["obligation_basis"] = "none"
    validated = validate_contract_instance("reviewFinding", record)
    assert validated.finding_class == finding_class
    assert route_review_verdict(record)["return_to"] == expected[1]


@pytest.mark.parametrize("field", ["capabilities", "unavailable_evidence"])
def test_api_002_rejects_empty_evidence_strings(field: str) -> None:
    review = stage_review("specification")
    review["evidence"][field] = [""]

    with pytest.raises(ReviewContractError, match=field):
        validate_stage_review(review)

    schema = json.loads(
        (REPO_ROOT / "references/assets/orchestration/contract/stage-review-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$defs"]["stageReview"]["properties"]["evidence"]["properties"][field]["items"][
        "minLength"
    ] == 1


def test_api_001_rejects_unclassified_wrong_layer_and_unauthorized_blocking_advisory() -> None:
    with pytest.raises(ReviewContractError, match="class"):
        classify_first_broken_owner("unknown")

    wrong_layer = finding("implementation_defect")
    wrong_layer["recommended_owner"] = "plan_owner"
    with pytest.raises(ReviewContractError, match="routing"):
        validate_contract_instance("reviewFinding", wrong_layer)

    advisory = finding("advisory_enhancement")
    with pytest.raises(ReviewContractError, match="advisory_enhancement"):
        validate_contract_instance("reviewFinding", advisory)


def test_api_001_reslice_pauses_repeated_expansion_and_preserves_evidence() -> None:
    routed = route_review_verdict(finding("allocation_gap"), previous_scope_expansions=1)
    assert routed == {
        "finding_id": "finding-allocation_gap",
        "first_broken_artifact": "plan",
        "return_to": "plan_owner",
        "action": "reslice_plan",
        "execution_state": "paused_for_reslice",
        "preserve_valid_work_and_evidence": True,
        "silent_expansion_allowed": False,
    }


def test_api_001_finding_lifecycle_allows_only_adjudication_after_routing() -> None:
    record = finding("implementation_defect")
    accepted = transition_review_finding(record, "accepted")
    assert accepted.disposition == "accepted"
    with pytest.raises(ReviewContractError, match="terminal"):
        transition_review_finding({**record, "disposition": "accepted"}, "rejected")
    with pytest.raises(ReviewContractError, match="adjudicator"):
        transition_review_finding(record, "repair_plan")


def test_api_002_requires_independent_direct_accepted_review_and_current_target() -> None:
    record = stage_review("plan")
    validated = validate_stage_review(record, current_target_identity=record["target_identity"])
    assert validated.stage == "plan"

    coauthored = deepcopy(record)
    coauthored["reviewer"]["authorship"] = "present"  # type: ignore[index]
    with pytest.raises(ReviewContractError, match="authorship"):
        validate_stage_review(coauthored)

    changed_target = deepcopy(record["target_identity"])
    changed_target["sha256"] = "1" * 64  # type: ignore[index]
    with pytest.raises(ReviewContractError, match="stale"):
        validate_stage_review(record, current_target_identity=changed_target)


def test_api_002_counts_exactly_three_mandatory_stage_identities() -> None:
    reviews = [stage_review(stage) for stage in ("specification", "plan", "integrated_implementation")]
    assert set(validate_stage_reviews(reviews)) == {
        "specification",
        "plan",
        "integrated_implementation",
    }
    with pytest.raises(ReviewContractError, match="exactly three"):
        validate_stage_reviews(reviews[:2])

    duplicate = deepcopy(reviews[-1])
    duplicate["review_id"] = reviews[0]["review_id"]
    with pytest.raises(ReviewContractError, match="unique"):
        validate_stage_reviews([*reviews, duplicate])


def test_api_002_preserves_but_does_not_count_stale_accepted_review() -> None:
    stale = stage_review("plan")
    stale["review_id"] = "review-plan-old"
    stale["staleness"] = {"is_stale": True, "reason": "target digest changed", "supersedes": None}
    assert validate_stage_review(stale).staleness["is_stale"] is True
    reviews = [stage_review(stage) for stage in ("specification", "plan", "integrated_implementation")]
    countable = validate_stage_reviews([stale, *reviews])
    assert countable["plan"].review_id == "review-plan"


def test_validate_contract_and_migration_stop_cli(tmp_path: Path) -> None:
    instance = tmp_path / "finding.json"
    instance.write_text(json.dumps(finding()), encoding="utf-8")
    schema = REPO_ROOT / "references/assets/orchestration/contract/review-finding-v1.schema.json"
    direct = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATION / "review_runtime.py"),
            "validate-contract",
            "--schema",
            str(schema),
            "--definition",
            "reviewFinding",
            "--instance",
            str(instance),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert direct.returncode == 0, direct.stdout + direct.stderr
    assert json.loads(direct.stdout)["status"] == "passed"

    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps({"issue": "WOR-107", "excluded_work": ["WOR-66", "WOR-79", "WOR-107", "work-bundle-mcp mutation"]}),
        encoding="utf-8",
    )
    dispatched = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/wb.py"),
            "assert-migration-stop",
            "--instance",
            str(handoff),
            "--required-excluded",
            "WOR-66",
            "WOR-79",
            "WOR-107",
            "work-bundle-mcp mutation",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert dispatched.returncode == 0, dispatched.stdout + dispatched.stderr
    assert json.loads(dispatched.stdout)["status"] == "passed"
