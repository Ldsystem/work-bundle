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
    spec = orch / "spec/active/spec.md"
    plan = orch / "plan/active/plan.md"
    for path, text in ((spec, "id: spec-test\nstatus: verified"),
                       (plan, "id: plan-test\nstatus: Planned\nsource_spec: [spec-test]")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{text}\n---\nOriginal body\n")
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


@pytest.mark.parametrize("removed", [None, "target", "plan_member", "verified_specification", "source_tree", "validation_evidence"])
def test_complete_snapshot_gate_rechecks_membership_after_receipt_rehash(tmp_path, removed):
    import hashlib
    import review_runtime
    _, plan, _ = _reviewed_plan_fixture(tmp_path, provenance=False)
    task = plan.parent / "task.md"
    task.write_text("---\nid: task-test\nplan_id: plan-test\nvalidation: [{kind: process, command: test -f source.txt, expected: exit 0}]\n---\nTask\n")
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/result.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("related: {plan: plan-test, task: task-test}\nvalidation: {commands: [{command: test -f source.txt, result: passed}]}\n")
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
    task = plan.parent / "task.md"
    task.write_text("---\nid: task-test\nplan_id: plan-test\nvalidation: [{command: check-claim}]\n---\nTask\n")
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/result.yaml"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("related: {plan: plan-test, task: task-test}\nvalidation: {commands: [{command: unrelated-check, result: passed}]}\n")
    _, missing = review_runtime.stage_evidence_requirements(tmp_path, "integrated_implementation", plan)
    assert "validation_evidence:task-test" in missing


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
