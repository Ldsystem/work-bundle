from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

import yaml
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
ORCHESTRATION = WORKSPACE_ROOT / ".work-bundle" / "orchestration"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

from execution_context import _compile_task_brief, validate_executor_result_for_task  # noqa: E402
from repository_preflight import capture_repository_evidence  # noqa: E402


PARTICIPANT_HANDOFFS = {
    "task-b01": ("task-b01-review-routing.md", "handoff-exec-20260904-wor105-b01.yaml"),
    "task-b02": ("task-b02-reviewer-isolation.md", "handoff-exec-20260904-wor105-b02.yaml"),
    "task-b03": ("task-b03-evaluator-identity.md", "handoff-exec-20260904-wor105-b03.yaml"),
    "task-b03a": ("task-b03a-source-record-parser-compatibility.md", "handoff-exec-20260905-wor105-b03a.yaml"),
    "task-b04": ("task-b04-completion-provenance.md", "handoff-exec-20260905-wor105-b04.yaml"),
    "task-b05": ("task-b05-stage-events.md", "handoff-exec-20260905-wor105-b05.yaml"),
    "task-b01r": ("task-b01r-review-contract-repair.md", "handoff-exec-20260905-wor105-b01r.yaml"),
    "task-b04r": ("task-b04r-ownership-id-repair.md", "handoff-exec-20260905-wor105-b04r.yaml"),
    "task-b05r": ("task-b05r-stage-string-repair.md", "handoff-exec-20260905-wor105-b05r.yaml"),
}

ALLOWED_HANDOFF_FIELDS = {
    "id", "type", "status", "project", "created_at", "updated_at", "related", "result",
    "changes", "validation", "evidence_closure", "knowledge_disposition", "contract_decoupling",
    "barrier", "convergence", "defect_closure", "unresolved", "task_fit_check",
    "acceptance_review", "repository", "codegraph", "delegation_evidence", "allocation_evidence",
}


def _yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _source_identity() -> str:
    evidence = capture_repository_evidence(REPO_ROOT)
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{evidence['head']}+repository-evidence-sha256:{digest}"


def _validate_participant_handoff(task_id: str, task_filename: str, handoff: dict[str, object]) -> None:
    task_root = ORCHESTRATION / "plan" / "active" / "plan-20260904-001-wor105-legacy-stabilization" / "phase-b-native-kernel"
    _, compiled = _compile_task_brief(
        Namespace(project_root=str(WORKSPACE_ROOT), task=str(task_root / task_filename))
    )
    task = deepcopy(compiled["task_brief"])
    required_validation_ids = {item["id"] for item in task["validation"]}
    task["validation"] = []
    task["evidence_capability"] = {
        "result": "no_validation_bearing_obligation",
        "reason": "Retrospective structural validation; original harness closure remains in the handoff.",
        "invariants": [],
    }
    validated = validate_executor_result_for_task(handoff, task, observe=False)

    assert set(handoff) <= ALLOWED_HANDOFF_FIELDS
    assert handoff["related"]["plan"] == "plan-20260904-001-wor105-legacy-stabilization"
    assert handoff["related"]["task"] == task_id
    assert validated["result_state"] == "completed"
    assert handoff["evidence_closure"]["result"] == "passed"
    reported = {item["id"]: item for item in handoff["validation"]["commands"]}
    assert required_validation_ids <= set(reported)
    assert all(reported[item_id]["result"] == "passed" for item_id in required_validation_ids)
    closed_evidence_ids = {
        evidence_id
        for invariant in handoff["evidence_closure"]["invariants"]
        for evidence_id in invariant["evidence_ids"]
    }
    assert required_validation_ids <= closed_evidence_ids
    assert handoff["barrier"]["id"] == "BAR-KERNEL"
    assert handoff["barrier"]["readiness"] == "reached"


def test_bar_kernel_handoffs_are_complete_closed_and_ready() -> None:
    handoff_root = ORCHESTRATION / "handoff" / "executor" / "active"
    for task_id, (task_filename, handoff_filename) in PARTICIPANT_HANDOFFS.items():
        handoff = _yaml(handoff_root / handoff_filename)
        _validate_participant_handoff(task_id, task_filename, handoff)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda value: value.update(suggested_durable_conclusions=[]), SystemExit),
        (lambda value: value.pop("knowledge_disposition"), SystemExit),
        (lambda value: value["changes"]["files"].append({"path": "outside.txt"}), SystemExit),
        (lambda value: value["validation"]["commands"].clear(), AssertionError),
        (lambda value: value.update(unrecognized_contract_field=True), AssertionError),
    ],
)
def test_bar_kernel_handoff_validation_rejects_incomplete_or_injected_records(mutation, error) -> None:
    task_filename, handoff_filename = PARTICIPANT_HANDOFFS["task-b01r"]
    handoff = deepcopy(
        _yaml(ORCHESTRATION / "handoff" / "executor" / "active" / handoff_filename)
    )
    mutation(handoff)

    with pytest.raises(error):
        _validate_participant_handoff("task-b01r", task_filename, handoff)


def test_native_transition_binds_current_source_and_independent_review() -> None:
    review_path = ORCHESTRATION / "reviews" / "WOR-105-task-b06r-kernel-review-accepted.yaml"
    transition_path = ORCHESTRATION / "docs" / "wor105" / "native-transition-record.yaml"
    review_bytes = review_path.read_bytes()
    review = yaml.safe_load(review_bytes)
    transition = _yaml(transition_path)
    identity = _source_identity()

    assert review["schema"] == "task-review-v1"
    assert review["task"] == "task-b06r"
    assert review["verdict"] == "accept"
    assert review["reviewer_independent"] is True
    assert review["reviewed_identity"] == identity
    assert review["findings"] == []
    assert transition["schema"] == "wor105-native-transition-v1"
    assert transition["source_identity"] == identity
    assert transition["review_sha256"] == hashlib.sha256(review_bytes).hexdigest()
    assert transition["enforcement_transition"] == "bootstrap_policy_to_native"
    assert transition["transition_task"] == "task-b06r"
