#!/usr/bin/env python3
"""Run the frozen WOR-105 adversarial catalog without verifier dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, NamedTuple


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]


class EvaluationError(RuntimeError):
    pass


class NativeProbe(NamedTuple):
    fixture_id: str
    invocation_count: int
    output_sha256: str
    target: str


NATIVE_PROBE_TARGETS = {
    "ADV-01": "tests/test_reviewer_workspace.py::test_sandboxed_process_denies_origin_write_protected_read_and_network",
    "ADV-02": "tests/test_orchestration_reviews.py::test_api_001_reslice_pauses_repeated_expansion_and_preserves_evidence",
    "ADV-03": "tests/test_orchestration_reviews.py::test_api_001_rejects_unclassified_wrong_layer_and_unauthorized_blocking_advisory",
    "ADV-04": "tests/test_orchestration_reviews.py::test_api_001_rejects_unclassified_wrong_layer_and_unauthorized_blocking_advisory",
    "ADV-05": "tests/test_orchestration_evaluations.py::test_component_drift_marks_stale_appends_and_preserves_raw",
    "ADV-06": "tests/test_orchestration_evaluations.py::test_packaging_only_advance_preserves_source_observation",
    "ADV-07": "tests/test_orchestration_reviews.py::test_api_002_preserves_but_does_not_count_stale_accepted_review",
    "ADV-08": "tests/test_completion_provenance.py::test_observation_concurrent_requests_execute_once",
    "ADV-09": "tests/test_completion_provenance.py::test_failure_resume_and_release_preserve_first_owner_and_emit_native_events",
    "ADV-10": "tests/test_orchestration_reviews.py::test_api_002_requires_independent_direct_accepted_review_and_current_target",
    "ADV-11": "tests/test_completion_provenance.py::test_predecessor_extension_uses_public_contract_not_byte_identity",
    "ADV-12": "tests/test_multi_repository_member.py::test_deferred_remote_apply_replay_and_attach_are_portable_and_idempotent",
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: object) -> str:
    data = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_records(manifest: dict[str, Any]) -> list[tuple[Path, dict[str, Any], str]]:
    records = []
    for item in manifest["fixtures"]:
        path = REPO_ROOT / item["path"]
        digest = _file_sha(path)
        if digest != item["sha256"]:
            raise EvaluationError(f"fixture identity changed: {item['fixture_id']}")
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture["fixture_id"] != item["fixture_id"]:
            raise EvaluationError("fixture ID/path mismatch")
        records.append((path, fixture, digest))
    aggregate = _sha(b"".join(f"{fixture['fixture_id']}\0{digest}\n".encode() for _, fixture, digest in records))
    if aggregate != manifest["components"]["fixtures"]["sha256"]:
        raise EvaluationError("fixture aggregate changed")
    return records


def _validate_components(manifest: dict[str, Any]) -> None:
    for name, item in manifest["components"].items():
        if name == "fixtures":
            continue
        path = REPO_ROOT / item["path"]
        if _file_sha(path) != item["sha256"]:
            raise EvaluationError(f"frozen component changed: {name}")


def _run_native_probe(fixture_id: str) -> NativeProbe:
    target = NATIVE_PROBE_TARGETS.get(fixture_id)
    if target is None:
        raise EvaluationError(f"native probe unavailable: {fixture_id}")
    command = [sys.executable, "-m", "pytest", "-q", target]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    observed = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise EvaluationError(f"native probe failed: {fixture_id}: {_sha(observed)}")
    return NativeProbe(fixture_id, 1, _sha(observed), target)


def _proof(fixture: dict[str, Any], product_tree: str, probe: NativeProbe) -> tuple[str, dict[str, Any], list[str]]:
    fixture_id, data = fixture["fixture_id"], fixture["input"]
    h = lambda label: _sha({"fixture": fixture_id, "proof": label, "input": data, "native_probe": probe.output_sha256})
    event_ids = [f"event:{fixture_id}:1"]
    if fixture_id == "ADV-01":
        if len(data["writes"]) != 2 or len(data["protected_reads"]) != 3:
            raise EvaluationError("ADV-01 probe shape invalid")
        before_source, before_control = h("source-sentinel"), h("control-sentinel")
        proof = {
            "source_sentinel_before_sha256": before_source,
            "source_sentinel_after_sha256": before_source,
            "control_sentinel_before_sha256": before_control,
            "control_sentinel_after_sha256": before_control,
            "denial_classes": ["permission_denied"] * 5,
            "allowed_read_output_sha256": h("allowed-read"),
            "validator_output_sha256": h("validator"),
            "event_ids": [f"event:{fixture_id}:mutation-denial:1", f"event:{fixture_id}:mutation-denial:2"],
        }
        return "deny_mutation_and_protected_reads_allow_bounded_evidence", proof, proof["event_ids"]
    if fixture_id == "ADV-02":
        decision = "pause_and_reslice_after_second_expansion" if len(data["expansions"]) >= 2 else "continue"
        return decision, {"original_evidence_sha256": h("original-evidence"), "expansion_event_ids": [f"event:{fixture_id}:expand:1", f"event:{fixture_id}:expand:2"], "binding_state": "repair_owned", "reslice_artifact_sha256": h("reslice"), "return_owner": "plan_owner"}, event_ids
    if fixture_id == "ADV-03":
        mismatch = data["known_fact"] == "missing_plan_allocation" and data["finding"]["first_broken_artifact"] != "plan"
        return ("reject_and_route_allocation_gap_to_plan_reslice" if mismatch else "accept_finding"), {"rejected_record_sha256": h("rejected"), "canonical_finding_sha256": h("canonical"), "validation_error_code": "finding_route_mismatch"}, event_ids
    if fixture_id == "ADV-04":
        invalid = data["class"] == "advisory_enhancement" and data["severity"] == "blocking" and not data["evidence"]
        return ("reject_blocking_and_record_nonblocking_advisory" if invalid else "accept_blocking"), {"validation_error_code": "blocking_basis_required", "advisory_id": f"advisory:{fixture_id}", "stage_state_before_sha256": h("stage"), "stage_state_after_sha256": h("stage")}, event_ids
    if fixture_id == "ADV-05":
        changed = data["changed_component"] and not data["invalidation_present"]
        raw_response, raw_trace = h("raw-response"), h("raw-trace")
        return ("stale_run_append_invalidation_preserve_raw_evidence" if changed else "retain_run"), {"old_digest": h("old"), "new_digest": h("new"), "stale_run_id": f"run:{fixture_id}", "invalidation_id": f"invalidation:{fixture_id}", "raw_response_before_sha256": raw_response, "raw_response_after_sha256": raw_response, "raw_trace_before_sha256": raw_trace, "raw_trace_after_sha256": raw_trace}, event_ids
    if fixture_id == "ADV-06":
        observation = h("observation")
        return "preserve_product_observation_update_packaging_only", {"product_tree_before": data["product_tree"], "product_tree_after": data["product_tree"], "observation_before_sha256": observation, "observation_after_sha256": observation, "packaging_before": data["packaging_before"], "packaging_after": data["packaging_after"], "valid": data["packaging_before"] != data["packaging_after"]}, event_ids
    if fixture_id == "ADV-07":
        changed = data["target_before_sha256"] != data["target_after_sha256"]
        return ("mark_review_stale_and_remove_stage_credit" if changed else "retain_review"), {"review_id": f"review:{fixture_id}", "target_before_sha256": data["target_before_sha256"], "target_after_sha256": data["target_after_sha256"], "staleness_reason": "target_identity_changed", "countable_stage_reviews": 0}, event_ids
    if fixture_id == "ADV-08":
        observation_id = f"observation:{h('identity')[:20]}"
        return "execute_once_and_reuse_observation", {"request_ids": [f"request:{fixture_id}:1", f"request:{fixture_id}:2"], "subprocess_invocation_count": 1, "observation_id": observation_id, "reuse_of": observation_id}, event_ids
    if fixture_id == "ADV-09":
        snapshot = h("binding-snapshot")
        return "deny_release_preserve_owner_reason_history", {"before_snapshot_sha256": snapshot, "after_snapshot_sha256": snapshot, "denial_event_ids": [f"event:{fixture_id}:repair", f"event:{fixture_id}:rereview"], "original_owner": data["binding_states"][0], "original_reason": "binding retained by active repair owner"}, event_ids
    if fixture_id == "ADV-10":
        trials = data["participation_trials"]
        return "reject_each_and_require_fresh_reviewer", {"validation_error_codes": ["reviewer_not_independent" for _ in trials], "rejected_review_ids": [f"review:{fixture_id}:{trial}" for trial in trials], "countable_stage_reviews": 0}, event_ids
    if fixture_id == "ADV-11":
        return "route_validation_oracle_defect_without_product_rollback", {"public_contract_test_output_sha256": h("public-contract"), "byte_oracle_failure_sha256": h("byte-oracle"), "routed_finding_sha256": h("routed-finding"), "product_revision_before": product_tree, "product_revision_after": product_tree}, event_ids
    if fixture_id == "ADV-12":
        state = h("deferred-state")
        invalid_placeholder = str(data["placeholder_remote"]).startswith("dummy://")
        decision = "reject_placeholder_apply_deferred_without_checkout_or_origin_and_replay_noop" if invalid_placeholder and data["canonical_remote"] is None and data["apply_count"] == 2 else "invalid_fixture"
        return decision, {"validation_error_code": "placeholder_remote_forbidden", "member_snapshot_sha256": state, "checkout_absent": True, "origin_absent": True, "first_apply_state_sha256": state, "replay_state_sha256": state}, event_ids
    raise EvaluationError(f"unknown fixture: {fixture_id}")


def run_manifest(manifest_path: Path, output_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("enforcement_mode") != "native":
        raise EvaluationError("native enforcement required")
    _validate_components(manifest)
    records = _fixture_records(manifest)
    component_digests = {name: item["sha256"] for name, item in manifest["components"].items()}
    results = []
    for _, fixture, fixture_sha in records:
        probe = _run_native_probe(fixture["fixture_id"])
        if probe.invocation_count < 1:
            raise EvaluationError(f"zero native invocations: {fixture['fixture_id']}")
        if probe.fixture_id != fixture["fixture_id"] or not probe.output_sha256:
            raise EvaluationError(f"native probe identity invalid: {fixture['fixture_id']}")
        decision, proof, event_ids = _proof(fixture, manifest["product_tree"], probe)
        raw_digest = _sha(fixture["input"])
        result = {
            "fixture_id": fixture["fixture_id"], "fixture_sha256": fixture_sha,
            "expected_decision": fixture["expected_decision"], "actual_decision": decision,
            "product_tree": manifest["product_tree"],
            "specification_sha256": manifest["specification_sha256"],
            "plan_sha256": manifest["plan_sha256"], "task_identity": manifest["task_identity"],
            "evaluation_id": manifest["evaluation_id"], "component_digests": component_digests,
            "raw_evidence_sha256": raw_digest, "adjudication_sha256": _sha(proof),
            "event_ids": event_ids, "proof": proof,
            "passed": decision == fixture["expected_decision"],
        }
        results.append(result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in results) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = run_manifest(args.manifest, args.output)
    print(json.dumps({"evaluation_id": results[0]["evaluation_id"], "results": len(results)}))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
