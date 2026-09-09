from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from reviewer_run_fixtures import bind_review_receipt


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))
import review_runtime  # noqa: E402

from review_runtime import (  # noqa: E402
    ReviewContractError,
    classify_first_broken_owner,
    publish_review,
    review_evidence_identity,
    route_stored_review_verdict,
    _route_review_finding as route_review_verdict,
    transition_review_finding,
    validate_contract_instance,
    validate_review_sequence,
    validate_stage_review,
    validate_stage_reviews,
    validate_task_acceptance_review,
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


def test_task_repair_review_binds_authoritative_integrated_stage_predecessor() -> None:
    previous = stage_review("integrated_implementation")
    previous.update(
        review_id="review-integrated-finding",
        review_mode="initial",
        review_target_kind="stage",
        repair_frontier=None,
        review_reset=None,
        verdict="repair",
    )
    previous["target_identity"] = {
        "artifact_id": "task-005",
        "revision": "a" * 40,
        "sha256": "1" * 64,
        "source_tree": "b" * 40,
    }
    blocking = finding()
    blocking["finding_id"] = "WOR112-T005-INT-001"
    blocking["target_identity"] = previous["target_identity"]
    evaluator_control = finding("validation_oracle_defect")
    evaluator_control["finding_id"] = "WOR112-EVALUATOR-CONTROL-001"
    evaluator_control["target_identity"] = previous["target_identity"]
    previous["findings"] = [blocking, evaluator_control]
    repaired_identity = {
        "artifact_id": "task-005",
        "revision": "c" * 40,
        "sha256": "2" * 64,
        "source_tree": "d" * 40,
    }
    current = {
        **stage_review("plan"),
        "required": True,
        "reviewer_independent": True,
        "review_id": "review-task-repair",
        "reviewed_head": repaired_identity["revision"],
        "review_mode": "repair",
        "review_target_kind": "task",
        "repair_frontier": {
            "prior_review_id": "review-integrated-finding",
            "blocking_finding_ids": ["WOR112-T005-INT-001"],
            "previous_reviewed_identity": previous["target_identity"],
            "repaired_identity": repaired_identity,
            "affected_boundaries": ["scripts/orchestration/review_runtime.py"],
            "frozen_evidence_reference": review_evidence_identity(previous),
        },
        "review_reset": None,
        "target_identity": repaired_identity,
        "verdict": "accept",
        "findings": [],
        "previous_review": previous,
    }

    validated = validate_task_acceptance_review(current)

    assert validated.review_id == "review-task-repair"
    assert validated.repair_frontier["prior_review_id"] == "review-integrated-finding"

    for finding_ids, message in (
        (["UNKNOWN-FINDING"], "unknown blocking finding IDs"),
        (["WOR112-EVALUATOR-CONTROL-001"], "only task-owned blocking findings"),
        ([], "must be non-empty"),
    ):
        invalid = deepcopy(current)
        invalid["repair_frontier"]["blocking_finding_ids"] = finding_ids
        with pytest.raises(ReviewContractError, match=message):
            validate_task_acceptance_review(invalid)


def test_material_change_reset_allows_same_independent_judgment_reviewer() -> None:
    previous = stage_review("plan")
    previous.update(
        review_mode="initial",
        review_target_kind="stage",
        repair_frontier=None,
        review_reset=None,
    )
    current = deepcopy(previous)
    current["review_id"] = "review-plan-current"
    current["target_identity"] = {
        **previous["target_identity"],
        "revision": "2",
        "sha256": "2" * 64,
    }
    current["review_reset"] = {
        "prior_review_id": previous["review_id"],
        "reason_class": "scope",
        "reason": "The accepted plan scope materially changed.",
    }

    validated = validate_review_sequence(
        current, previous_review=previous, material_change="scope"
    )

    assert validated.reviewer["agent_id"] == previous["reviewer"]["agent_id"]
    assert validated.review_reset["prior_review_id"] == previous["review_id"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("authorship", "present", "accepted review requires reviewer.authorship"),
        ("capability", "standard", "judgment reviewer"),
    ],
)
def test_material_change_reset_still_rejects_nonindependent_or_nonjudgment_reviewer(
    field: str, value: str, message: str
) -> None:
    previous = stage_review("plan")
    previous.update(
        review_mode="initial",
        review_target_kind="stage",
        repair_frontier=None,
        review_reset=None,
    )
    current = deepcopy(previous)
    current["review_id"] = "review-plan-current"
    current["target_identity"] = {
        **previous["target_identity"],
        "revision": "2",
        "sha256": "2" * 64,
    }
    current["review_reset"] = {
        "prior_review_id": previous["review_id"],
        "reason_class": "scope",
        "reason": "The accepted plan scope materially changed.",
    }
    current["reviewer"][field] = value

    with pytest.raises(ReviewContractError, match=message):
        validate_review_sequence(
            current, previous_review=previous, material_change="scope"
        )


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
    route_context = {}
    if finding_class == "allocation_gap":
        route_context = {
            "affected_region": {
                "task_ids": ["task-b01"],
                "paths": [],
                "interfaces": [],
                "validation_oracles": [],
            },
            "original_binding_identity": {"binding_id": "binding-b01", "sha256": "1" * 64},
            "original_baseline_identity": {"head": ZERO_TREE, "tree": ZERO_TREE},
        }
    assert route_review_verdict(record, **route_context)["return_to"] == expected[1]


def test_review_store_is_required_before_public_finding_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = stage_review("integrated_implementation")
    record.update(
        review_id="review-task-publication",
        review_mode="initial",
        review_target_kind="stage",
        repair_frontier=None,
        review_reset=None,
        verdict="repair",
    )
    item = finding()
    item["target_identity"] = record["target_identity"]
    record["findings"] = [item]
    record["reviewer_run"] = {
        "run_id": "reviewer-run-00000000-0000-0000-0000-000000000001",
        "sha256": ZERO_SHA,
    }
    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_: None)

    with pytest.raises(ReviewContractError, match="stored review"):
        route_stored_review_verdict(
            tmp_path, item, current_target_identity=record["target_identity"]
        )
    with pytest.raises(ReviewContractError, match="stored review"):
        review_runtime.route_review_verdict(
            tmp_path, item, current_target_identity=record["target_identity"]
        )

    reference = publish_review(
        tmp_path, record, current_target_identity=record["target_identity"]
    )
    routed = route_stored_review_verdict(
        tmp_path,
        reference,
        current_target_identity=record["target_identity"],
        finding_id=item["finding_id"],
    )
    assert routed["return_to"] == "task_owner"


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


@pytest.mark.parametrize("capability", ["mechanical", "arbitrary", "", None])
def test_stage_reviewer_capability_is_closed(capability):
    record = stage_review("plan")
    record["reviewer"]["capability"] = capability
    with pytest.raises(ReviewContractError, match="capability"):
        validate_stage_review(record)


@pytest.mark.parametrize("mode", ["packet_only", "constrained_direct"])
def test_packet_or_constrained_evidence_cannot_accept(mode):
    record = stage_review("plan")
    record["evidence"]["mode"] = mode
    with pytest.raises(ReviewContractError):
        validate_stage_review(record)


def test_stage_batch_requires_actual_current_targets():
    records = [stage_review(s) for s in ("specification", "plan", "integrated_implementation")]
    with pytest.raises(ReviewContractError, match="current target"):
        validate_stage_reviews(records)


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
    routed = route_review_verdict(
        finding("allocation_gap"),
        previous_scope_expansions=1,
        affected_region={
            "task_ids": ["task-b01"],
            "paths": [],
            "interfaces": [],
            "validation_oracles": [],
        },
        original_binding_identity={"binding_id": "binding-b01", "sha256": "1" * 64},
        original_baseline_identity={"head": ZERO_TREE, "tree": ZERO_TREE},
    )
    assert routed == {
        "finding_id": "finding-allocation_gap",
        "first_broken_artifact": "plan",
        "return_to": "plan_owner",
        "action": "reslice_plan",
        "execution_state": "paused_for_reslice",
        "affected_region": {
            "task_ids": ["task-b01"],
            "paths": [],
            "interfaces": [],
            "validation_oracles": [],
        },
        "returned_authority_identity": {
            "artifact_id": "task-b01",
            "revision": "1",
            "sha256": ZERO_SHA,
            "source_tree": ZERO_TREE,
        },
        "preserved_evidence_identities": [],
        "resume_requires": "accepted_repaired_plan_authority",
        "original_binding_identity": {"binding_id": "binding-b01", "sha256": "1" * 64},
        "original_baseline_identity": {"head": ZERO_TREE, "tree": ZERO_TREE},
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
    current = {review["stage"]: review["target_identity"] for review in reviews}
    assert set(validate_stage_reviews(reviews, current_target_identities=current)) == {
        "specification",
        "plan",
        "integrated_implementation",
    }
    with pytest.raises(ReviewContractError, match="exactly three"):
        validate_stage_reviews(reviews[:2], current_target_identities=current)

    duplicate = deepcopy(reviews[-1])
    duplicate["review_id"] = reviews[0]["review_id"]
    with pytest.raises(ReviewContractError, match="unique"):
        validate_stage_reviews([*reviews, duplicate], current_target_identities=current)


def test_lifecycle_gate_reads_current_artifact_not_claimed_staleness(tmp_path):
    import review_runtime
    root = tmp_path / ".work-bundle/orchestration"
    spec = root / "spec/active/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("---\nid: spec-test\nversion: 1\nstatus: draft\n---\nRequirement A\n")
    with pytest.raises(SystemExit, match="review"):
        review_runtime.require_specification_review(tmp_path, spec)
    review = stage_review("specification")
    review["target_identity"] = review_runtime.artifact_review_identity(spec)
    reviews = root / "reviews"
    reviews.mkdir()
    review = bind_review_receipt(tmp_path, review)
    (reviews / "accepted.json").write_text(json.dumps(review))
    review_runtime.require_specification_review(tmp_path, spec)
    spec.write_text(spec.read_text().replace("draft", "verified"))
    review_runtime.require_specification_review(tmp_path, spec)
    spec.write_text(spec.read_text().replace("Requirement A", "Requirement B"))
    with pytest.raises(SystemExit, match="review"):
        review_runtime.require_specification_review(tmp_path, spec)


def _reviewed_plan_fixture(root, *, provenance=True):
    import review_runtime
    orch = root / ".work-bundle/orchestration"
    metadata = root / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        f"metadata_version: 3\nworkspace_root: {root}\nworkspace_mode: single-repository\n"
    )
    spec = orch / "spec/active/spec.md"
    plan = orch / "plan/active/plan.md"
    for path, text in ((spec, "id: spec-test\nstatus: verified\nrequirements: [{id: REQ-001, requirement: Preserve accepted stage authority.}]"),
                       (plan, "id: plan-test\nstatus: Planned\nsource_spec: [spec-test]")):
        path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            "- **REQ-001**: Preserve accepted stage authority.\nOriginal body\n"
            if path == spec else "Original body\n"
        )
        path.write_text(f"---\n{text}\n---\n{body}")
    reviews = orch / "reviews"
    reviews.mkdir()
    for stage, identity in (("specification", review_runtime.artifact_review_identity(spec)),
                            ("plan", review_runtime.plan_review_identity(root, plan))):
        review = stage_review(stage)
        review["target_identity"] = identity
        if provenance:
            review = bind_review_receipt(root, review)
        (reviews / f"{stage}.json").write_text(json.dumps(review))
    return spec, plan, reviews


def _write_stage_task(plan: Path, *, review_required: bool = False, command: str = "check-claim") -> Path:
    task = plan.parent / "task.md"
    task.write_text(
        "---\n"
        "id: task-test\nplan_id: plan-test\nphase_id: phase-test\ndepends_on: []\n"
        "goal: Preserve accepted stage authority.\n"
        "source_ids: [REQ-001]\n"
        "truth_basis: {purpose: Preserve authority, as_is_evidence: [source.txt], decision_authority: [none-relevant], expected_delta: [stage authority], conflict_status: clear}\n"
        "files: {read: [source.txt], write: [], forbidden: [credentials/**]}\n"
        "methodology: {primary: tdd, skills: [dev-test-driven-development]}\n"
        "allocated_rules: []\n"
        "executor_profile: {capability: standard, context_mode: compiled-brief}\n"
        f"acceptance_review: {{required: {str(review_required).lower()}}}\n"
        "evidence_capability: {result: mapped, reason: Direct command proves the stage claim, invariants: [{id: INV-STAGE, source_ids: [REQ-001], invariant: Accepted authority remains current, boundary: component, oracle: VAL-1, capability_reason: Direct command can falsify drift, freshness: current_task_batch, task_id: task-test, evidence_ids: [VAL-1], closure_result: pending}]}\n"
        f"validation: [{{id: VAL-1, kind: process, command: {json.dumps(command)}, invariant_ids: [INV-STAGE], capability_reason: Direct command can falsify drift, proves: REQ-001, expected: passed}}]\n"
        "---\nTask\n"
    )
    return task


@pytest.mark.parametrize("stage", ["plan", "integrated_implementation"])
def test_target_only_packet_cannot_declare_direct_source(tmp_path, stage):
    import reviewer_workspace
    import review_runtime
    spec, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    spec.write_text(spec.read_text().replace("status: draft", "status: verified"))
    protected = tmp_path / "protected"
    protected.mkdir()
    if stage == "integrated_implementation":
        for args in (["init", "-q"], ["config", "user.name", "Test"], ["config", "user.email", "test@example.com"]):
            subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
        (tmp_path / ".gitignore").write_text(".work-bundle/\nprotected/\n")
        (tmp_path / "source.txt").write_text("claim-relevant source")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "baseline"], check=True)
    locator = "control:" + plan.relative_to(tmp_path).as_posix()
    packet = reviewer_workspace.build_direct_evidence_packet(
        source_root=tmp_path, control_root=tmp_path, protected_roots=[protected],
        artifacts=[locator], search_roots=[], validators=[], sentinels=[], network_state="denied",
        stage_review_context={"stage": stage, "target_locator": locator,
            "target_identity": review_runtime.stage_target_identity(tmp_path, stage, plan, source_root=tmp_path),
            "agent_id": "reviewer", "capability": "judgment", "execution_id": "worker",
            "evidence_mode": "direct_source"})
    assert packet["stage_review_context"]["evidence_mode"] == "packet_only"
    assert packet["stage_evidence_manifest"]["missing"]
    packet["stage_review_context"]["evidence_mode"] = "direct_source"
    with pytest.raises(review_runtime.ReviewContractError, match="complete reproducible snapshot"):
        review_runtime.validate_stage_evidence(tmp_path, packet["stage_review_context"], packet)


@pytest.mark.parametrize("removed", [None, "target", "plan_member", "verified_specification", "source_tree", "accepted_task_result"])
def test_complete_snapshot_gate_rechecks_membership_after_receipt_rehash(tmp_path, removed):
    import hashlib
    import review_runtime
    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = _write_stage_task(plan, command="test -f source.txt")
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/result.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("related: {plan: plan-test, task: task-test}\nvalidation: {commands: [{command: test -f source.txt, result: passed}]}\n")
    _write_compact_accepted_result(tmp_path)
    for args in (["init", "-q"], ["config", "user.name", "Test"], ["config", "user.email", "test@example.com"]):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    (tmp_path / ".gitignore").write_text(".work-bundle/\n")
    (tmp_path / "source.txt").write_text("source")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "executable").write_text("#!/bin/sh\nexit 0\n")
    (nested / "executable").chmod(0o755)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "baseline"], check=True)
    review = stage_review("integrated_implementation")
    review["target_identity"] = review_runtime.stage_target_identity(tmp_path, review["stage"], plan, source_root=tmp_path)
    review = bind_review_receipt(tmp_path, review)
    assert review["evidence"]["mode"] == "reproducible_snapshot"
    review_runtime._validate_reviewer_run(tmp_path, review)
    if removed is None:
        return
    receipt_path = review_runtime.reviewer_runtime_root(tmp_path) / "receipts/reviewer-process" / (review["reviewer_run"]["run_id"] + ".json")
    packet_path = receipt_path.with_suffix(".packet.json")
    packet = json.loads(packet_path.read_text())
    manifest = packet["stage_evidence_manifest"]
    omitted = next(entry["locator"] for entry in manifest["entries"] if entry["role"] == removed)
    manifest["entries"] = [entry for entry in manifest["entries"] if entry["locator"] != omitted]
    packet["artifacts"] = [entry for entry in packet["artifacts"] if entry["locator"] != omitted]
    # Also remove the Git entry: the complete tree identity must still reject it.
    manifest["source_tree"] = [entry for entry in manifest["source_tree"] if entry["locator"] != omitted]
    packet_path.chmod(0o600)
    packet_path.write_text(json.dumps(packet))
    packet_path.chmod(0o400)
    receipt = json.loads(receipt_path.read_text())
    receipt["packet_sha256"] = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    receipt_path.chmod(0o600)
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o400)
    review["reviewer_run"]["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    with pytest.raises(review_runtime.ReviewContractError, match="stage evidence"):
        review_runtime._validate_reviewer_run(tmp_path, review)


def test_plan_snapshot_requires_verified_linked_specification(tmp_path):
    import review_runtime
    spec, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    spec.write_text(spec.read_text().replace("status: verified", "status: draft"))
    _, missing = review_runtime.stage_evidence_requirements(tmp_path, "plan", plan)
    assert any(item.startswith("verified_specification:") for item in missing)


def test_integrated_snapshot_requires_evidence_for_each_declared_check(tmp_path):
    import review_runtime
    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = _write_stage_task(plan)
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/result.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("related: {plan: plan-test, task: task-test}\nvalidation: {commands: [{command: unrelated-check, result: passed}]}\n")
    _, missing = review_runtime.stage_evidence_requirements(tmp_path, "integrated_implementation", plan)
    assert "accepted_task_result_missing:task-test" in missing


def _write_compact_accepted_result(
    root: Path, *, task: Path | None = None, review_id: str | None = None
) -> Path:
    import execution_context

    task = task or _write_stage_task(root / ".work-bundle/orchestration/plan/active/plan.md")
    compiled_task = execution_context.static_task_brief(root, task)
    binding = root / ".work-bundle/runtime/execution/plan-test/task-test/execution-binding.json"
    binding.parent.mkdir(parents=True, exist_ok=True)
    baseline = {"head": "a" * 40, "tree": "b" * 40}
    owner = {"delegated": True, "owner_kind": "subagent", "agent_id": "/root/task", "run_id": "run-1", "mechanism": "host-native"}
    binding_payload = {
        "plan_id": "plan-test", "task_id": "task-test",
        "workspace_id": "workspace-test", "execution_id": "execution-test",
        "repository_id": "repository-test", "execution_path": str(root.resolve()),
        "git_identity": {}, "baseline": baseline,
        "ownership": {"binding_id": "binding:plan-test:task-test", "original_owner": "task-test"},
    }
    accepted_review = {
        "required": review_id is not None, "review_id": review_id,
        "verdict": "accept" if review_id is not None else None,
    }
    authority = execution_context._accepted_authority_projection(
        compiled_task, binding_payload, accepted_review=accepted_review, owner_identity=owner
    )
    knowledge = {"action": "none", "reason": "No durable knowledge delta.", "affected_authority": []}
    accepted = {
        "schema": "accepted-task-result-v1", "plan_id": "plan-test", "task_id": "task-test",
        "binding_id": "binding:plan-test:task-test", "baseline_identity": baseline,
        "accepted_source": {"head": "c" * 40, "tree": "d" * 40},
        "authority_projection": authority, "executor_result_digest": "7" * 64,
        "validation_evidence_ids": ["observation-val-1"], "review_id": review_id,
        "owner_identity": owner,
        "knowledge_disposition": knowledge, "accepted_at": "2026-09-08T00:00:00Z", "invalidation": None,
    }
    accepted["accepted_source"]["state_digest"] = review_runtime.accepted_result_state_digest(accepted)
    binding_payload["accepted_result"] = accepted
    binding.write_text(json.dumps(binding_payload))
    task_brief = binding.with_name("task-brief.yaml")
    task_brief.write_text(
        "\n".join(execution_context._dump_yaml({"task_brief": compiled_task})) + "\n"
    )
    return binding


def test_integrated_snapshot_uses_compact_acceptance_not_handoff_history(tmp_path):
    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = _write_stage_task(plan)
    binding = _write_compact_accepted_result(tmp_path, task=task)
    misleading = tmp_path / ".work-bundle/orchestration/handoff/executor/active/broken.yaml"
    misleading.parent.mkdir(parents=True)
    misleading.write_text("invalid:\n   badly indented\n  historical: true\n")

    required, missing = review_runtime.stage_evidence_requirements(
        tmp_path, "integrated_implementation", plan
    )

    assert missing == []
    assert required["control:" + binding.relative_to(tmp_path).as_posix()] == "accepted_task_result"
    assert not any("handoff" in locator for locator in required)


def test_native_integrated_review_bounds_large_unchanged_tree_to_exact_change_manifest(
    tmp_path: Path, monkeypatch,
) -> None:
    import reviewer_workspace

    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = _write_stage_task(plan)
    protected = tmp_path / ".work-bundle/protected-test"
    protected.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".gitignore").write_text(".work-bundle/\n", encoding="utf-8")
    (tmp_path / "unchanged-large.txt").write_text("x" * 1_100_000, encoding="utf-8")
    (tmp_path / "source.txt").write_text("before\n", encoding="utf-8")
    for arguments in (
        ["init", "-q"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.invalid"],
        ["add", "."],
        ["commit", "-qm", "baseline"],
    ):
        subprocess.run(["git", "-C", str(tmp_path), *arguments], check=True)
    baseline = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    (tmp_path / "source.txt").write_text("after\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "source.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-qm", "claim change"], check=True
    )
    endpoint = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    _write_compact_accepted_result(tmp_path, task=task)
    change_manifest = tmp_path / ".work-bundle/runtime/change-manifest.json"
    change_manifest.parent.mkdir(parents=True, exist_ok=True)
    change_manifest.write_text(
        json.dumps(
            {
                "baseline": {"head": baseline},
                "endpoint": {"head": endpoint, "tree": tree},
                "comparison": {
                    "command": f"git diff --name-status {baseline}..{endpoint}",
                    "path_count": 1,
                    "paths": [{"status": "modified", "path": "source.txt"}],
                },
            }
        ),
        encoding="utf-8",
    )
    identity = review_runtime.stage_target_identity(
        tmp_path, "integrated_implementation", plan, source_root=tmp_path
    )
    locator = "control:" + plan.relative_to(tmp_path).as_posix()
    required, missing = review_runtime.stage_evidence_requirements(
        tmp_path, "integrated_implementation", plan
    )
    assert missing == []
    required.update(
        {entry["locator"]: "source_tree" for entry in review_runtime.source_snapshot_entries(tmp_path)}
    )
    required["control:" + change_manifest.relative_to(tmp_path).as_posix()] = "change_manifest"
    packet = reviewer_workspace.build_direct_evidence_packet(
        source_root=tmp_path,
        control_root=tmp_path,
        protected_roots=[protected],
        artifacts=list(required),
        search_roots=[],
        validators=[],
        sentinels=[],
        network_state="denied",
        stage_review_context={
            "stage": "integrated_implementation",
            "target_locator": locator,
            "target_identity": identity,
            "agent_id": "reviewer-large-tree",
            "capability": "judgment",
            "execution_id": "reviewer-large-tree-run",
            "evidence_mode": "direct_source",
        },
    )
    created = reviewer_workspace.create_reviewer_workspace(
        review_runtime.reviewer_runtime_root(tmp_path), "review-large-tree", packet
    )
    captured: dict[str, str] = {}

    def native_process(_workspace, _argv, request):
        captured["request"] = request
        events = [
            {"type": "thread.started", "thread_id": "01a0821d-f359-7d60-a9bd-90dd0e006166"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "judgment", "type": "agent_message", "text": json.dumps({
                "stage_review": {"target_identity": identity, "verdict": "accepted", "findings": []}
            })}},
            {"type": "turn.completed", "usage": {}},
        ]
        return subprocess.CompletedProcess([], 0, "\n".join(json.dumps(event) for event in events), "")

    monkeypatch.setattr(reviewer_workspace, "_run_native_process", native_process)
    receipt = reviewer_workspace.run_native_reviewer(
        Path(str(created["workspace_path"])),
        Path(sys.executable),
        model="test-model",
        review_instructions="Assess the accepted requirements and exact changed source.",
    )
    request = json.loads(captured["request"])
    supplied = {item["locator"] for item in request["evidence"]}
    assert len(captured["request"]) <= reviewer_workspace.NATIVE_REVIEW_REQUEST_MAX_CHARS
    assert "source:source.txt" in supplied
    assert "source:unchanged-large.txt" not in supplied
    assert request["review_input"]["target_identity"]["source_tree"] == tree
    assert any(
        item["locator"] == "source:unchanged-large.txt"
        for item in request["review_input"]["artifacts"]
    )
    review_runtime._validate_reviewer_run(
        tmp_path,
        {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]},
    )


def test_integrated_snapshot_includes_native_review_when_present_and_rejects_invalid_compact_authority(tmp_path, monkeypatch):
    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = _write_stage_task(plan, review_required=True)
    binding = _write_compact_accepted_result(tmp_path, task=task, review_id="review-task-current")
    accepted = json.loads(binding.read_text())["accepted_result"]
    review = {
        **stage_review("plan"), "required": True, "reviewer_independent": True,
        "review_id": "review-task-current", "reviewed_head": accepted["accepted_source"]["head"],
        "review_mode": "initial", "review_target_kind": "task", "repair_frontier": None,
        "review_reset": None, "target_identity": {
            "artifact_id": "task-test", "revision": accepted["accepted_source"]["head"],
            "sha256": "8" * 64, "source_tree": accepted["accepted_source"]["tree"],
        }, "verdict": "accept",
    }
    review_path = tmp_path / ".work-bundle/orchestration/reviews/review-task-current.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(json.dumps(review))
    review_path.chmod(0o444)
    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_: None)
    required, missing = review_runtime.stage_evidence_requirements(tmp_path, "integrated_implementation", plan)
    assert missing == []
    assert required["control:" + review_path.relative_to(tmp_path).as_posix()] == "accepted_task_review"

    payload = json.loads(binding.read_text())
    payload["accepted_result"]["accepted_source"]["state_digest"] = "0" * 64
    binding.write_text(json.dumps(payload))
    _, missing = review_runtime.stage_evidence_requirements(tmp_path, "integrated_implementation", plan)
    assert "accepted_task_result_invalid:task-test" in missing


@pytest.mark.parametrize("mutation", ["task", "scope", "validation", "binding"])
def test_integrated_snapshot_rejects_self_consistent_accepted_result_after_current_authority_drift(
    tmp_path: Path, mutation: str
) -> None:
    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = _write_stage_task(plan)
    binding = _write_compact_accepted_result(tmp_path, task=task)
    accepted_before = json.loads(binding.read_text())["accepted_result"]
    assert accepted_before["accepted_source"]["state_digest"] == review_runtime.accepted_result_state_digest(
        accepted_before
    )

    if mutation == "task":
        task.write_text(task.read_text().replace("depends_on: []", "depends_on: [task-prior]"))
    elif mutation == "scope":
        task.write_text(task.read_text().replace("read: [source.txt]", "read: [source.txt, other.txt]"))
    elif mutation == "validation":
        task.write_text(task.read_text().replace("command: \"check-claim\"", "command: \"changed-check\""))
    else:
        payload = json.loads(binding.read_text())
        payload["workspace_id"] = "workspace-changed"
        binding.write_text(json.dumps(payload))

    _, missing = review_runtime.stage_evidence_requirements(
        tmp_path, "integrated_implementation", plan
    )
    assert "accepted_task_result_invalid:task-test" in missing


def test_manually_authored_accepted_review_cannot_advance_lifecycle(tmp_path):
    import review_runtime
    spec, _, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    # Valid shape and an exact current target are not reviewer execution proof.
    with pytest.raises(SystemExit, match="provenance|receipt"):
        review_runtime.require_specification_review(tmp_path, spec)


@pytest.mark.skipif(sys.platform != "darwin", reason="native sandbox-exec boundary is macOS-only")
def test_native_reviewer_receipt_advances_lifecycle_and_survives_cleanup(tmp_path):
    import review_runtime
    import reviewer_workspace
    import argparse
    import specs
    spec, _, reviews = _reviewed_plan_fixture(tmp_path, provenance=False)
    spec.write_text(spec.read_text().replace("status: verified", "status: draft"))
    record = json.loads((reviews / "specification.json").read_text())
    bound = bind_review_receipt(tmp_path, record, real_process=True)
    (reviews / "specification.json").write_text(json.dumps(bound))
    runtime = review_runtime.reviewer_runtime_root(tmp_path)
    state = json.loads((runtime / ".state" / f"{bound['review_id']}.json").read_text())
    terminal = {"schema": "reviewer-terminal-review-v1", "review_id": bound["review_id"],
                "verdict": "accepted", **{key: state[key] for key in ("packet_sha256", "evidence_digest", "sentinel_digest")}}
    reviewer_workspace.cleanup_reviewer_workspace(runtime, bound["review_id"], terminal_review=terminal,
        source_root=tmp_path, control_root=tmp_path, protected_roots=[tmp_path / ".work-bundle/protected-test"])
    specs.cmd_set_spec_status(argparse.Namespace(project_root=str(tmp_path), id="spec-test", status="verified"))
    assert "status: verified" in spec.read_text()


@pytest.mark.parametrize("change", ["missing", "digest", "review_id", "target", "result", "mutable", "packet", "profile", "events", "future"])
def test_stage_receipt_integrity_failures_block_acceptance(tmp_path, change):
    import review_runtime
    spec, _, reviews = _reviewed_plan_fixture(tmp_path)
    path = reviews / "specification.json"
    record = json.loads(path.read_text())
    receipt = review_runtime.reviewer_runtime_root(tmp_path) / "receipts/reviewer-process" / f"{record['reviewer_run']['run_id']}.json"
    if change == "missing":
        receipt.unlink()
    elif change == "digest":
        record["reviewer_run"]["sha256"] = ZERO_SHA
    elif change == "review_id":
        record["review_id"] = "forged-review"
    elif change == "target":
        spec.write_text(spec.read_text().replace("Original body", "different target"))
        record["target_identity"] = review_runtime.artifact_review_identity(spec)
    elif change == "result":
        record["evidence"]["capabilities"].append("forged evidence claim")
    elif change == "mutable":
        receipt.chmod(0o600)
    elif change == "future":
        import hashlib
        value = json.loads(receipt.read_text())
        value["completed_at"] = "2999-01-01T00:00:00Z"
        receipt.chmod(0o600)
        receipt.write_text(json.dumps(value))
        receipt.chmod(0o400)
        record["reviewer_run"]["sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    else:
        suffix = {"packet": ".packet.json", "profile": ".profile.sb", "events": ".events.jsonl"}[change]
        receipt.with_suffix(suffix).unlink()
    path.write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="provenance"):
        review_runtime.require_specification_review(tmp_path, spec)


@pytest.mark.parametrize("field", ["author_execution_id", "repair_execution_id"])
def test_known_author_or_repair_execution_cannot_receive_stage_credit(tmp_path, field):
    import review_runtime
    spec, _, reviews = _reviewed_plan_fixture(tmp_path, provenance=False)
    spec.write_text(spec.read_text().replace("status: verified", f"status: draft\n{field}: same-worker"))
    record = stage_review("specification")
    record["target_identity"] = review_runtime.artifact_review_identity(spec)
    record = bind_review_receipt(tmp_path, record, execution_id="same-worker")
    (reviews / "specification.json").write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="overlaps author/repair"):
        review_runtime.require_specification_review(tmp_path, spec)


def test_current_plan_execution_binding_excludes_its_worker_from_review(tmp_path):
    import review_runtime
    _, plan, reviews = _reviewed_plan_fixture(tmp_path)
    record = json.loads((reviews / "plan.json").read_text())
    record = bind_review_receipt(tmp_path, record, execution_id="bound-author")
    (reviews / "plan.json").write_text(json.dumps(record))
    binding = tmp_path / ".work-bundle/runtime/execution/plan-test/task-1/execution-binding.json"
    binding.parent.mkdir(parents=True)
    binding.write_text(json.dumps({"execution_id": "bound-author"}))
    with pytest.raises(SystemExit, match="overlaps author/repair"):
        review_runtime.require_plan_reviews(tmp_path, plan)


def test_old_packet_bytes_cannot_be_relabelled_as_current_target(tmp_path):
    import review_runtime
    import reviewer_workspace
    spec, _, reviews = _reviewed_plan_fixture(tmp_path)
    record = json.loads((reviews / "specification.json").read_text())
    runtime = review_runtime.reviewer_runtime_root(tmp_path)
    workspace = runtime / "reviews" / record["review_id"]
    packet = json.loads((workspace / "packet.json").read_text())
    spec.write_text(spec.read_text().replace("Original body", "new requirement"))
    packet["stage_review_context"]["target_identity"] = review_runtime.artifact_review_identity(spec)
    packet["policy_roots"] = {"source": str(tmp_path), "control": str(tmp_path),
                              "protected": [str(tmp_path / ".work-bundle/protected-test")]}
    with pytest.raises(reviewer_workspace.ReviewerWorkspaceError, match="STAGE_PACKET_STALE"):
        reviewer_workspace.create_reviewer_workspace(runtime, "relabelled", packet)


def _native_spec_receipt(tmp_path, monkeypatch, *, observed_events=None, crlf=False):
    import reviewer_workspace
    spec, _, reviews = _reviewed_plan_fixture(tmp_path)
    record = json.loads((reviews / "specification.json").read_text())
    record.pop("reviewer_run")
    workspace = review_runtime.reviewer_runtime_root(tmp_path) / "reviews" / record["review_id"]
    if crlf:
        spec.write_bytes(spec.read_bytes().replace(b"\n", b"\r\n"))
        previous_packet = json.loads((workspace / "packet.json").read_text())
        packet = reviewer_workspace.build_direct_evidence_packet(
            source_root=tmp_path, control_root=tmp_path, protected_roots=[tmp_path / ".work-bundle/protected-test"],
            artifacts=[item["locator"] for item in previous_packet["artifacts"]], search_roots=[], validators=[],
            sentinels=[], network_state="denied", stage_review_context=previous_packet["stage_review_context"])
        record["review_id"] += "-crlf"
        created = reviewer_workspace.create_reviewer_workspace(review_runtime.reviewer_runtime_root(tmp_path), record["review_id"], packet)
        workspace = Path(created["workspace_path"])
    host_id = "01a0821d-f359-7d60-a9bd-90dd0e006166"
    events = [
        {"type": "thread.started", "thread_id": host_id}, {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "1", "type": "agent_message", "text": json.dumps({
            "stage_review": {key: record[key] for key in ("target_identity", "verdict", "findings")}})}},
        {"type": "turn.completed", "usage": {}},
    ]
    if observed_events is not None:
        events = observed_events
    monkeypatch.setattr(reviewer_workspace, "_run_native_process", lambda *_:
        subprocess.CompletedProcess([], 0, "\n".join(json.dumps(event) for event in events), ""))
    receipt = reviewer_workspace.run_native_reviewer(workspace, Path(sys.executable), model="test-model",
                                                     review_instructions="Assess supplied specification and return its stage judgment.")
    result = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
    return spec, receipt, result


def test_native_crlf_evidence_preserves_exact_bytes_through_publication(tmp_path, monkeypatch):
    spec, receipt, result = _native_spec_receipt(tmp_path, monkeypatch, crlf=True)
    assert b"\r\n" in spec.read_bytes()
    request = json.loads(Path(receipt["receipt_path"]).with_suffix(".request.json").read_text())
    locator = "control:" + spec.relative_to(tmp_path).as_posix()
    supplied = next(item for item in request["evidence"] if item["locator"] == locator)
    assert supplied["content"].encode("utf-8") == spec.read_bytes()
    current = review_runtime.artifact_review_identity(spec)
    reference = publish_review(tmp_path, result, current_target_identity=current)
    loaded, accepted = review_runtime.load_stored_review(tmp_path, reference, current_target_identity=current)
    assert loaded == result and accepted.verdict == "accepted"


def test_failed_native_admission_retains_actual_unadmitted_diagnostics(tmp_path, monkeypatch):
    import reviewer_workspace
    events = [{"type": "thread.started", "thread_id": "01a0821d-f359-7d60-a9bd-90dd0e006166"},
              {"type": "turn.started"},
              {"type": "item.completed", "item": {"id": "tool", "type": "command_execution"}}]
    with pytest.raises(reviewer_workspace.ReviewerWorkspaceError, match="NATIVE_TRANSCRIPT") as failed:
        _native_spec_receipt(tmp_path, monkeypatch, observed_events=events)
    diagnostic = Path(failed.value.result["diagnostic_path"])
    assert diagnostic.is_relative_to(review_runtime.reviewer_runtime_root(tmp_path) / "diagnostics")
    assert [json.loads(line) for line in (diagnostic / "stdout.jsonl").read_text().splitlines()] == events
    assert (diagnostic / "request.json").is_file()
    assert (diagnostic / "stderr.txt").is_file()
    assert (diagnostic / "launch.json").is_file()
    metadata = json.loads((diagnostic / "capture.json").read_text())
    assert metadata["status"] == "unadmitted"
    assert "review_result" not in metadata and "reviewer_run" not in metadata
    assert all(not item.stat().st_mode & 0o222 for item in diagnostic.iterdir())
    assert not (review_runtime.reviewer_runtime_root(tmp_path) / "receipts/reviewer-process" / (metadata["run_id"] + ".json")).exists()


def test_plugin_absent_native_review_publishes_and_consumes_actual_host_identity(tmp_path, monkeypatch):
    spec, receipt, result = _native_spec_receipt(tmp_path, monkeypatch)
    assert result["reviewer"]["agent_id"] == receipt["host_run_id"]
    assert receipt["isolation"]["mechanism"] == "native-host-read-only"
    assert receipt["isolation"]["os_process_isolation"] is False
    request = json.loads(Path(receipt["receipt_path"]).with_suffix(".request.json").read_text())
    assert set(request["review_input"]) == {"stage", "target_identity", "artifacts"}
    assert "execution_id" not in json.dumps(request["review_input"])
    current = review_runtime.artifact_review_identity(spec)
    reference = publish_review(tmp_path, result, current_target_identity=current)
    loaded, accepted = review_runtime.load_stored_review(tmp_path, reference, current_target_identity=current)
    assert loaded == result
    assert accepted.verdict == "accepted"
    spec.write_text(spec.read_text().replace("Original body", "Changed obligation"))
    with pytest.raises(ReviewContractError, match="current"):
        publish_review(tmp_path, result, current_target_identity=review_runtime.artifact_review_identity(spec))


@pytest.mark.parametrize("change", ["isolation", "host_id", "result", "raw_result", "request", "stderr", "argv"])
def test_native_receipt_rejects_resealed_false_provenance(tmp_path, monkeypatch, change):
    import hashlib
    _, receipt, result = _native_spec_receipt(tmp_path, monkeypatch)
    path = Path(receipt["receipt_path"])
    saved = json.loads(path.read_text())
    if change == "isolation":
        saved["isolation"] = {"mechanism": "sandbox-exec", "network": "denied", "write_scope": "scratch"}
    elif change == "host_id":
        saved["host_run_id"] = "author-alias"
    elif change == "result":
        result["verdict"] = "blocked"
        saved["review_result"] = {key: value for key, value in result.items() if key != "reviewer_run"}
        saved["review_result_sha256"] = hashlib.sha256(json.dumps(saved["review_result"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    else:
        suffix = {"raw_result": ".stdout.jsonl", "request": ".request.json", "stderr": ".stderr.txt", "argv": ".launch.json"}[change]
        proof = path.with_suffix(suffix)
        proof.chmod(0o600)
        if change == "raw_result":
            proof.write_text(json.dumps({"verdict": "accepted"}))
            saved["stdout_sha256"] = hashlib.sha256(proof.read_bytes()).hexdigest()
        elif change == "request":
            value = json.loads(proof.read_text())
            value["evidence"][0]["content"] += "changed"
            proof.write_text(json.dumps(value))
            saved["request_sha256"] = hashlib.sha256(proof.read_bytes()).hexdigest()
        elif change == "stderr":
            proof.write_text("ERROR codex_core::tools::router: error=code-mode host is disabled\n")
            saved["stderr_sha256"] = hashlib.sha256(proof.read_bytes()).hexdigest()
        else:
            value = json.loads(proof.read_text())
            value["argv"].remove("--ignore-user-config")
            proof.write_text(json.dumps(value))
            saved["argv_sha256"] = hashlib.sha256(json.dumps(value["argv"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        proof.chmod(0o400)
    path.chmod(0o600)
    path.write_text(json.dumps(saved))
    path.chmod(0o400)
    result["reviewer_run"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ReviewContractError, match="provenance"):
        review_runtime._validate_reviewer_run(tmp_path, result)


@pytest.mark.parametrize("change", ["review_id", "target", "capability", "context_origin", "failed"])
def test_launcher_does_not_publish_acceptance_for_unbound_worker_output(tmp_path, monkeypatch, change):
    import reviewer_workspace
    import review_runtime
    spec, _, reviews = _reviewed_plan_fixture(tmp_path)
    record = json.loads((reviews / "specification.json").read_text())
    workspace = review_runtime.reviewer_runtime_root(tmp_path) / "reviews" / record["review_id"]
    record.pop("reviewer_run")
    if change == "review_id":
        record["review_id"] = "another-review"
    elif change == "target":
        record["target_identity"]["sha256"] = ZERO_SHA
    elif change == "context_origin":
        record["reviewer"]["context_origin"] = "direct_source"
    elif change == "capability":
        record["reviewer"]["capability"] = "standard"
    monkeypatch.setattr(reviewer_workspace, "_run_sandboxed_process",
        lambda *_: subprocess.CompletedProcess(["worker"], 1 if change == "failed" else 0, json.dumps(record), ""))
    if change != "failed":
        with pytest.raises(reviewer_workspace.ReviewerWorkspaceError, match="STAGE_OUTPUT_MISMATCH"):
            reviewer_workspace.run_sandboxed_reviewer(workspace, ["worker"])
    else:
        receipt = reviewer_workspace.run_sandboxed_reviewer(workspace, ["worker"])
        import hashlib
        record["reviewer_run"] = {"run_id": receipt["run_id"], "sha256": hashlib.sha256(Path(receipt["receipt_path"]).read_bytes()).hexdigest()}
        (reviews / "specification.json").write_text(json.dumps(record))
        with pytest.raises(SystemExit, match="provenance"):
            review_runtime.require_specification_review(tmp_path, spec)


def test_plan_execution_transition_and_binding_reject_stale_plan(tmp_path):
    import argparse
    import plans
    import execution_context
    _, plan, reviews = _reviewed_plan_fixture(tmp_path)
    args = argparse.Namespace(project_root=str(tmp_path), id="plan-test", status="In progress")
    plans.cmd_set_plan_status(args)
    plan.write_text(plan.read_text().replace("Original body", "Changed obligation"))
    with pytest.raises(SystemExit, match="review"):
        plans.cmd_set_plan_status(args)
    with pytest.raises(SystemExit, match="review"):
        execution_context.create_or_load_task_execution_binding(control_root=tmp_path,
            plan_id="plan-test", task_id="task-test", workspace_id="ws", execution_id="exec",
            repository_id="repo", runtime_root=tmp_path / "runtime")
    assert not (tmp_path / "runtime").exists()


@pytest.mark.parametrize("kind,status", [("spec", "verified"), ("plan", "In progress"), ("plan", "Completed")])
def test_write_cannot_bypass_stage_gate_with_embedded_status(tmp_path, kind, status):
    import argparse
    import specs
    import plans
    content = tmp_path / "input.md"
    content.write_text(f"---\nid: artifact-test\nstatus: {status}\n---\nBody\n")
    args = argparse.Namespace(project_root=str(tmp_path), content_file=str(content),
        id="artifact-test", title="Test", purpose="upgrade", component="test", version="1",
        filename="artifact.md", status="draft" if kind == "spec" else "Planned")
    with pytest.raises(SystemExit, match="review|source_spec"):
        (specs.cmd_write_spec if kind == "spec" else plans.cmd_write_plan)(args)
    assert not (tmp_path / f".work-bundle/orchestration/{kind}/active/artifact.md").exists()


def test_plan_member_edit_and_forged_fresh_flag_cannot_reuse_review(tmp_path):
    import review_runtime
    _, plan, reviews = _reviewed_plan_fixture(tmp_path)
    task = plan.parent / "plan-test/phase-1/task-1.md"
    task.parent.mkdir(parents=True)
    task.write_text("---\nid: task-1\nplan_id: plan-test\n---\nNew command\n")
    with pytest.raises(SystemExit, match="plan review"):
        review_runtime.require_plan_reviews(tmp_path, plan)
    records = [stage_review(stage) for stage in ("specification", "plan", "integrated_implementation")]
    current = {item["stage"]: deepcopy(item["target_identity"]) for item in records}
    current["plan"]["sha256"] = "a" * 64
    with pytest.raises(ReviewContractError, match="exactly three"):
        validate_stage_reviews(records, current_target_identities=current)


def test_new_spec_review_does_not_refresh_old_plan_review(tmp_path):
    import review_runtime
    spec, plan, reviews = _reviewed_plan_fixture(tmp_path)
    spec.write_text(spec.read_text().replace("Original body", "Changed requirement"))
    replacement = stage_review("specification")
    replacement["target_identity"] = review_runtime.artifact_review_identity(spec)
    replacement = bind_review_receipt(tmp_path, replacement)
    (reviews / "specification.json").write_text(json.dumps(replacement))
    with pytest.raises(SystemExit, match="plan review"):
        review_runtime.require_plan_reviews(tmp_path, plan)


@pytest.mark.parametrize("mode,context,accepted", [
    ("direct_source", "direct_source", True), ("direct", "direct_source", True),
    ("reproducible_snapshot", "reproducible_snapshot", True),
    ("packet_only", "packet_only", False), ("constrained_direct", "direct_source", False),
    ("direct_source", "carried_summary", False),
])
def test_evidence_mode_schema_and_runtime_agree(mode, context, accepted):
    jsonschema = pytest.importorskip("jsonschema")
    record = stage_review("plan")
    record["evidence"]["mode"] = mode
    record["reviewer"]["context_origin"] = context
    if mode == "reproducible_snapshot":
        record["evidence"]["artifacts"] = [{"path": "snapshot.json", "sha256": ZERO_SHA}]
    schema = json.loads((REPO_ROOT / "references/assets/orchestration/contract/stage-review-v1.schema.json").read_text())
    if accepted:
        validate_stage_review(record)
        jsonschema.validate(record, schema)
    else:
        with pytest.raises(ReviewContractError):
            validate_stage_review(record)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(record, schema)


@pytest.mark.parametrize("transition", ["Completed", "archive"])
def test_final_transition_binds_current_source_tree(tmp_path, monkeypatch, transition):
    import argparse
    import plans
    import review_runtime
    _, plan, reviews = _reviewed_plan_fixture(tmp_path)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()
    git("init", "-q")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.com")
    (tmp_path / ".gitignore").write_text(".work-bundle/\n")
    source = tmp_path / "source.txt"
    source.write_text("A")
    git("add", ".")
    git("commit", "-qm", "baseline")
    args = argparse.Namespace(project_root=str(tmp_path), id="plan-test", status="Completed")
    run = (lambda: plans.cmd_archive_plan(args)) if transition == "archive" else (lambda: plans.cmd_set_plan_status(args))
    # Only downstream task/knowledge checks are isolated; stage admission is real.
    monkeypatch.setattr(plans, "_validated_plan_task_handoffs", lambda *_: [])
    monkeypatch.setattr(plans, "_assert_archive_knowledge_gate", lambda *_: None)
    monkeypatch.setattr(plans, "_assert_archive_plan_acceptance", lambda *_: None)
    with pytest.raises(SystemExit, match="integrated_implementation"):
        run()
    review = stage_review("integrated_implementation")
    review["target_identity"] = dict(review_runtime.plan_review_identity(tmp_path, plan),
                                      source_tree=git("rev-parse", "HEAD^{tree}"))
    review = bind_review_receipt(tmp_path, review)
    (reviews / "final.json").write_text(json.dumps(review))
    source.write_text("B")
    with pytest.raises(SystemExit, match="clean"):
        run()
    git("add", "source.txt")
    git("commit", "-qm", "changed source")
    with pytest.raises(SystemExit, match="integrated_implementation"):
        run()
    review["target_identity"]["source_tree"] = git("rev-parse", "HEAD^{tree}")
    review = bind_review_receipt(tmp_path, review)
    (reviews / "final.json").write_text(json.dumps(review))
    run()


def test_api_002_preserves_but_does_not_count_stale_accepted_review() -> None:
    stale = stage_review("plan")
    stale["review_id"] = "review-plan-old"
    stale["staleness"] = {"is_stale": True, "reason": "target digest changed", "supersedes": None}
    assert validate_stage_review(stale).staleness["is_stale"] is True
    reviews = [stage_review(stage) for stage in ("specification", "plan", "integrated_implementation")]
    countable = validate_stage_reviews([stale, *reviews], current_target_identities={review["stage"]: review["target_identity"] for review in reviews})
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
