from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))

import review_runtime  # noqa: E402
import reviewer_workspace  # noqa: E402


ZERO_SHA = "0" * 64


def identity(name: str, digest: str) -> dict[str, object]:
    return {"artifact_id": name, "revision": "1", "sha256": digest, "source_tree": None}


def finding(target: dict[str, object], finding_id: str = "RF-FINDING-1") -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "stage": "implementation",
        "class": "implementation_defect",
        "severity": "blocking",
        "first_broken_artifact": "implementation",
        "obligation_basis": "accepted_requirement",
        "evidence": [{"kind": "test", "locator": "RF", "digest_or_identity": "RF-RED", "observation": "failed"}],
        "target_identity": target,
        "summary": "Repair this bounded defect.",
        "recommended_owner": "task_owner",
        "disposition": "repair_task",
    }


def review(*, target: dict[str, object], mode: str = "initial", kind: str = "stage", agent: str = "reviewer-new") -> dict[str, object]:
    return {
        "review_id": f"review-{mode}-{agent}",
        "review_mode": mode,
        "review_target_kind": kind,
        "repair_frontier": None,
        "review_reset": None,
        "stage": "plan",
        "target_identity": target,
        "reviewer": {
            "agent_id": agent,
            "capability": "judgment",
            "authorship": "none",
            "repair_participation": "none",
            "decision_participation": "none",
            "deliberation_participation": "none",
            "context_origin": "direct_source",
        },
        "evidence": {"mode": "direct", "capabilities": ["bounded source inspection"], "unavailable_evidence": [], "commands": [], "artifacts": []},
        "verdict": "accepted",
        "findings": [],
        "started_at": "2026-09-06T00:00:00Z",
        "completed_at": "2026-09-06T00:01:00Z",
        "staleness": {"is_stale": False, "reason": None, "supersedes": None},
    }


def repair_pair() -> tuple[dict[str, object], dict[str, object]]:
    old = identity("task-rf", "1" * 64)
    new = identity("task-rf", "2" * 64)
    prior = review(target=old, agent="reviewer-prior")
    prior["review_id"] = "review-prior"
    prior["verdict"] = "repair"
    prior["findings"] = [finding(old)]
    current = review(target=new, mode="repair")
    current["repair_frontier"] = {
        "prior_review_id": prior["review_id"],
        "blocking_finding_ids": ["RF-FINDING-1"],
        "previous_reviewed_identity": old,
        "repaired_identity": new,
        "affected_boundaries": ["scripts/orchestration/review_runtime.py:validate_stage_review"],
        "frozen_evidence_reference": review_runtime.review_evidence_identity(prior),
    }
    return prior, current


def test_rf_01_initial_and_repair_modes_are_native_and_closed() -> None:
    initial = review(target=identity("task-rf", ZERO_SHA))
    validated = review_runtime.validate_stage_review(initial)
    assert (validated.review_mode, validated.review_target_kind, validated.repair_frontier) == ("initial", "stage", None)
    schema = json.loads((REPO_ROOT / "references/assets/orchestration/contract/stage-review-v1.schema.json").read_text())
    assert schema["$defs"]["reviewMode"]["enum"] == ["initial", "repair"]
    assert schema["$defs"]["reviewTargetKind"]["enum"] == ["task", "stage"]
    initial["repair_frontier"] = {"unexpected": True}
    with pytest.raises(review_runtime.ReviewContractError, match="initial review cannot carry"):
        review_runtime.validate_stage_review(initial)


def test_rf_02_repair_frontier_binds_prior_findings_evidence_and_exact_identities() -> None:
    prior, current = repair_pair()
    validated = review_runtime.validate_review_sequence(current, previous_review=prior)
    assert validated.repair_frontier["previous_reviewed_identity"] == prior["target_identity"]
    schema = json.loads((REPO_ROOT / "references/assets/orchestration/contract/stage-review-v1.schema.json").read_text())
    assert set(schema["$defs"]["repairFrontier"]["required"]) == set(current["repair_frontier"])
    tampered = deepcopy(current)
    tampered["repair_frontier"]["blocking_finding_ids"] = ["UNKNOWN"]
    with pytest.raises(review_runtime.ReviewContractError, match="blocking finding IDs"):
        review_runtime.validate_review_sequence(tampered, previous_review=prior)


def test_rf_03_repair_reuses_frozen_evidence_without_copying_history() -> None:
    prior, current = repair_pair()
    prior["evidence"]["artifacts"] = [{"path": f"history/{index}.json", "sha256": ZERO_SHA} for index in range(100)]
    current["repair_frontier"]["frozen_evidence_reference"] = review_runtime.review_evidence_identity(prior)
    validated = review_runtime.validate_review_sequence(current, previous_review=prior)
    assert validated.evidence["artifacts"] == []
    assert len(json.dumps(validated.repair_frontier)) < len(json.dumps(prior["evidence"]))


@pytest.mark.parametrize("reason_class", ["material_redesign", "authority", "scope", "acceptance", "decomposition", "validation_allocation"])
def test_rf_04_material_change_requires_fresh_initial_review(reason_class: str) -> None:
    prior, repair = repair_pair()
    with pytest.raises(review_runtime.ReviewContractError, match="fresh initial review"):
        review_runtime.validate_review_sequence(repair, previous_review=prior, material_change=reason_class)
    reset = review(target=repair["target_identity"], agent="reviewer-reset")
    reset["review_reset"] = {"prior_review_id": prior["review_id"], "reason_class": reason_class, "reason": "accepted boundary changed"}
    assert review_runtime.validate_review_sequence(reset, previous_review=prior, material_change=reason_class).review_mode == "initial"


def test_rf_05_reset_allows_same_independent_reviewer_and_keeps_safeguards() -> None:
    prior, repair = repair_pair()
    reset = review(target=repair["target_identity"], agent=prior["reviewer"]["agent_id"])
    reset["review_reset"] = {"prior_review_id": prior["review_id"], "reason_class": "scope", "reason": "scope changed"}
    assert review_runtime.validate_review_sequence(
        reset, previous_review=prior, material_change="scope"
    ).reviewer["agent_id"] == prior["reviewer"]["agent_id"]

    participating = deepcopy(reset)
    participating["reviewer"]["repair_participation"] = "present"
    with pytest.raises(review_runtime.ReviewContractError, match="repair_participation"):
        review_runtime.validate_review_sequence(
            participating, previous_review=prior, material_change="scope"
        )

    nonjudgment = deepcopy(reset)
    nonjudgment["reviewer"]["capability"] = "standard"
    with pytest.raises(review_runtime.ReviewContractError, match="judgment reviewer"):
        review_runtime.validate_review_sequence(
            nonjudgment, previous_review=prior, material_change="scope"
        )


def test_rf_06_repair_rejects_stale_or_relabelled_identity() -> None:
    prior, current = repair_pair()
    current["target_identity"] = identity("task-rf", "3" * 64)
    with pytest.raises(review_runtime.ReviewContractError, match="repaired identity"):
        review_runtime.validate_review_sequence(current, previous_review=prior)


def test_rf_07_repair_still_detects_regression_in_affected_boundary() -> None:
    prior, current = repair_pair()
    current["findings"] = [finding(current["target_identity"], "RF-REGRESSION")]
    with pytest.raises(review_runtime.ReviewContractError, match="accepted review cannot contain blocking"):
        review_runtime.validate_review_sequence(current, previous_review=prior)


def test_rf_08_repair_packet_is_bounded_for_task_and_stage_targets(tmp_path: Path) -> None:
    prior, current = repair_pair()
    target = tmp_path / "target.md"
    target.write_text("---\nid: task-rf\n---\nrepaired\n")
    current["target_identity"] = review_runtime.artifact_review_identity(target)
    current["repair_frontier"]["repaired_identity"] = current["target_identity"]
    context = {
        "stage": "plan", "target_identity": current["target_identity"], "target_locator": "control:target.md",
        "agent_id": "reviewer-new", "capability": "judgment", "execution_id": "exec-rf",
        "evidence_mode": "reproducible_snapshot", "review_mode": "repair", "review_target_kind": "stage",
        "repair_frontier": current["repair_frontier"], "review_reset": None,
    }
    artifact = {"locator": "control:target.md", "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "content_base64": ""}
    manifest = review_runtime.stage_evidence_manifest(tmp_path, tmp_path, context, [artifact])
    assert manifest["missing"] == []
    assert [entry["locator"] for entry in manifest["entries"]] == ["control:target.md"]
    assert manifest["repair_frontier_reference"] == current["repair_frontier"]["frozen_evidence_reference"]
    assert reviewer_workspace._validate_stage_context(context)["review_target_kind"] == "stage"

    task_prior = {key: value for key, value in prior.items() if key != "stage"}
    task_prior.update(required=True, reviewer_independent=True, review_target_kind="task")
    task_current = {key: value for key, value in current.items() if key != "stage"}
    task_current.update(required=True, reviewer_independent=True, verdict="accept", review_target_kind="task", previous_review=task_prior)
    assert review_runtime.validate_task_acceptance_review(task_current).target_identity == current["target_identity"]


def test_rf_01_h1_repairs_recorded_a_without_reacquiring_unrecorded_latent_b(tmp_path: Path) -> None:
    target = tmp_path / "repair-a.md"
    latent = tmp_path / "latent-b.md"
    old_content = "---\nid: artifact-rf01\nversion: 1\n---\nA is broken\n"
    new_content = old_content.replace("broken", "repaired")
    target.write_text(new_content)
    latent.write_text("B is latent and outside H1's recorded surface.\n")
    old_identity = review_runtime.artifact_review_identity(target, content=old_content)
    new_identity = review_runtime.artifact_review_identity(target)

    initial_h1 = review(target=old_identity, agent="reviewer-h1")
    initial_h1.update(review_id="review-h1", verdict="repair", findings=[finding(old_identity, "RF-A")])
    repair_a = review(target=new_identity, mode="repair", agent="reviewer-repair-a")
    repair_a["repair_frontier"] = {
        "prior_review_id": "review-h1", "blocking_finding_ids": ["RF-A"],
        "previous_reviewed_identity": old_identity, "repaired_identity": new_identity,
        "affected_boundaries": ["control:repair-a.md"],
        "frozen_evidence_reference": review_runtime.review_evidence_identity(initial_h1),
    }
    assert review_runtime.validate_review_sequence(repair_a, previous_review=initial_h1).verdict == "accepted"

    context = {
        "stage": "plan", "target_identity": new_identity, "target_locator": "control:repair-a.md",
        "agent_id": "reviewer-repair-a", "capability": "judgment", "execution_id": "exec-rf01",
        "evidence_mode": "reproducible_snapshot", "review_mode": "repair", "review_target_kind": "stage",
        "repair_frontier": repair_a["repair_frontier"], "review_reset": None,
    }
    manifest = review_runtime.stage_evidence_manifest(
        tmp_path, tmp_path, context,
        [{"locator": "control:repair-a.md", "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
    )
    assert manifest["missing"] == []
    assert [entry["locator"] for entry in manifest["entries"]] == ["control:repair-a.md"]
    assert "latent-b.md" not in json.dumps(manifest)


@pytest.mark.parametrize(
    ("invariant", "finding_class", "obligation", "first_broken"),
    [
        ("security", "implementation_defect", "essential_safety", "implementation"),
        ("ownership", "implementation_defect", "accepted_requirement", "implementation"),
        ("destructive-safety", "implementation_defect", "essential_safety", "implementation"),
        ("evidence-integrity", "validation_oracle_defect", "evidence_integrity", "validation_oracle"),
    ],
)
def test_rf_03_capable_untouched_invariant_stays_blocking_during_narrow_repair(
    invariant: str, finding_class: str, obligation: str, first_broken: str
) -> None:
    prior, narrow = repair_pair()
    safety = finding(narrow["target_identity"], f"RF-SAFETY-{invariant}")
    safety.update(
        **{
            "class": finding_class,
            "obligation_basis": obligation,
            "first_broken_artifact": first_broken,
            "recommended_owner": review_runtime.classify_first_broken_owner(finding_class)[1],
            "disposition": review_runtime.classify_first_broken_owner(finding_class)[2],
        }
    )
    safety["evidence"] = [{
        "kind": "test", "locator": f"accepted:{invariant}",
        "digest_or_identity": f"RF-03-{invariant}", "observation": "capable evidence still fails",
    }]
    narrow.update(verdict="repair", findings=[safety])
    assert review_runtime.validate_review_sequence(narrow, previous_review=prior).verdict == "repair"
    routed = review_runtime.route_review_verdict(safety)
    assert routed["first_broken_artifact"] == first_broken
    assert routed["preserve_valid_work_and_evidence"] is True


def test_rf_06_final_broad_integrated_review_rediscovers_and_classifies_latent_b(tmp_path: Path) -> None:
    for args in (("init", "-q"), ("config", "user.name", "Test"), ("config", "user.email", "test@example.com")):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True)
    (tmp_path / ".gitignore").write_text(".work-bundle/\n")
    (tmp_path / "direct-a.py").write_text("A = 'repaired'\n")
    (tmp_path / "latent-b.py").write_text("B = 'deferred-non-load-bearing'\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "integrated"], check=True)
    spec = tmp_path / ".work-bundle/orchestration/spec/active/spec-rf06.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("---\nid: spec-rf06\nversion: 1\nstatus: verified\n---\nAccepted scope.\n")
    plan = tmp_path / ".work-bundle/orchestration/plan/active/plan-rf06.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("---\nid: plan-rf06\nversion: 1\nstatus: In progress\nsource_spec: [.work-bundle/orchestration/spec/active/spec-rf06.md]\n---\nFinal broad review.\n")
    target_identity = review_runtime.stage_target_identity(
        tmp_path, "integrated_implementation", plan, source_root=tmp_path
    )
    artifacts = [
        {"locator": "control:.work-bundle/orchestration/plan/active/plan-rf06.md", "sha256": hashlib.sha256(plan.read_bytes()).hexdigest()},
        {"locator": "control:.work-bundle/orchestration/spec/active/spec-rf06.md", "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()},
    ]
    for entry in review_runtime.source_snapshot_entries(tmp_path):
        path = tmp_path / entry["locator"].removeprefix("source:")
        artifacts.append({"locator": entry["locator"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    context = {
        "stage": "integrated_implementation", "target_identity": target_identity,
        "target_locator": "control:.work-bundle/orchestration/plan/active/plan-rf06.md",
        "agent_id": "reviewer-final", "capability": "judgment", "execution_id": "exec-rf06",
        "evidence_mode": "reproducible_snapshot", "review_mode": "initial", "review_target_kind": "stage",
        "repair_frontier": None, "review_reset": None,
    }
    manifest = review_runtime.stage_evidence_manifest(tmp_path, tmp_path, context, artifacts)
    assert manifest["missing"] == []
    assert "source:latent-b.py" in {entry["locator"] for entry in manifest["source_tree"]}
    assert next(entry for entry in manifest["entries"] if entry["locator"] == "source:latent-b.py")["role"] == "source_tree"

    latent_finding = finding(target_identity, "RF-LATENT-B")
    latent_finding.update(
        **{"class": "advisory_enhancement", "severity": "advisory", "obligation_basis": "none",
           "first_broken_artifact": "implementation", "recommended_owner": "backlog_owner", "disposition": "record_advisory"}
    )
    latent_finding["evidence"] = [{
        "kind": "source", "locator": "source:latent-b.py", "digest_or_identity": "RF-06-B",
        "observation": "Final broad review rediscovered deferred non-load-bearing B.",
    }]
    assert review_runtime.validate_review_finding(latent_finding).finding_id == "RF-LATENT-B"
    assert review_runtime.route_review_verdict(latent_finding)["return_to"] == "backlog_owner"
