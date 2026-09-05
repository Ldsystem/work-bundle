from __future__ import annotations

import hashlib
import json
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


def review(*, target: dict[str, object], mode: str = "initial", kind: str = "task", agent: str = "reviewer-new") -> dict[str, object]:
    return {
        "review_id": f"review-{mode}-{agent}",
        "review_mode": mode,
        "review_target_kind": kind,
        "repair_frontier": None,
        "review_reset": None,
        "stage": "implementation" if kind == "task" else "plan",
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
    assert (validated.review_mode, validated.review_target_kind, validated.repair_frontier) == ("initial", "task", None)
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


def test_rf_05_reset_rejects_reused_repair_reviewer_identity() -> None:
    prior, repair = repair_pair()
    reset = review(target=repair["target_identity"], agent=prior["reviewer"]["agent_id"])
    reset["review_reset"] = {"prior_review_id": prior["review_id"], "reason_class": "scope", "reason": "scope changed"}
    with pytest.raises(review_runtime.ReviewContractError, match="fresh capable independent reviewer"):
        review_runtime.validate_review_sequence(reset, previous_review=prior, material_change="scope")


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
    for kind in ("task", "stage"):
        current["review_target_kind"] = kind
        current["stage"] = "implementation" if kind == "task" else "plan"
        context = {
            "stage": current["stage"], "target_identity": current["target_identity"], "target_locator": "control:target.md",
            "agent_id": "reviewer-new", "capability": "judgment", "execution_id": "exec-rf",
            "evidence_mode": "reproducible_snapshot", "review_mode": "repair", "review_target_kind": kind,
            "repair_frontier": current["repair_frontier"], "review_reset": None,
        }
        artifact = {"locator": "control:target.md", "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "content_base64": ""}
        manifest = review_runtime.stage_evidence_manifest(tmp_path, tmp_path, context, [artifact])
        assert manifest["missing"] == []
        assert [entry["locator"] for entry in manifest["entries"]] == ["control:target.md"]
        assert manifest["repair_frontier_reference"] == current["repair_frontier"]["frozen_evidence_reference"]
        assert reviewer_workspace._validate_stage_context(context)["review_target_kind"] == kind
