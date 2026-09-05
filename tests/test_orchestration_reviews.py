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
    (reviews / "accepted.json").write_text(json.dumps(review))
    review_runtime.require_specification_review(tmp_path, spec)
    spec.write_text(spec.read_text().replace("draft", "verified"))
    review_runtime.require_specification_review(tmp_path, spec)
    spec.write_text(spec.read_text().replace("Requirement A", "Requirement B"))
    with pytest.raises(SystemExit, match="review"):
        review_runtime.require_specification_review(tmp_path, spec)


def _reviewed_plan_fixture(root):
    import review_runtime
    orch = root / ".work-bundle/orchestration"
    spec = orch / "spec/active/spec.md"
    plan = orch / "plan/active/plan.md"
    for path, text in ((spec, "id: spec-test\nstatus: draft"),
                       (plan, "id: plan-test\nstatus: Planned\nsource_spec: [spec-test]")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{text}\n---\nOriginal body\n")
    reviews = orch / "reviews"
    reviews.mkdir()
    for stage, identity in (("specification", review_runtime.artifact_review_identity(spec)),
                            ("plan", review_runtime.plan_review_identity(root, plan))):
        review = stage_review(stage)
        review["target_identity"] = identity
        (reviews / f"{stage}.json").write_text(json.dumps(review))
    return spec, plan, reviews


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
    (reviews / "final.json").write_text(json.dumps(review))
    source.write_text("B")
    with pytest.raises(SystemExit, match="clean"):
        run()
    git("add", "source.txt")
    git("commit", "-qm", "changed source")
    with pytest.raises(SystemExit, match="integrated_implementation"):
        run()
    review["target_identity"]["source_tree"] = git("rev-parse", "HEAD^{tree}")
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
