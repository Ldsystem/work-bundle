from __future__ import annotations

import re
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSITION_RECORD = REPO_ROOT / "evals" / "wor105" / "components" / "native-transition-record.yaml"
EXPECTED_PARTICIPANTS = {
    "task-b01",
    "task-b02",
    "task-b03",
    "task-b03a",
    "task-b04",
    "task-b05",
    "task-b01r",
    "task-b04r",
    "task-b05r",
}
EXPECTED_EXCLUDED_WORK = ["WOR-66", "WOR-79", "WOR-107", "work-bundle-mcp mutation"]
ALLOWED_TRANSITION_FIELDS = {
    "schema",
    "issue",
    "transition_task",
    "enforcement_transition",
    "source_identity",
    "review_path",
    "review_sha256",
    "accepted_commit",
    "accepted_tree",
    "integrated_validation",
    "handoff_validation",
    "participant_handoffs",
    "native_scope",
    "excluded_work",
    "accepted_at",
}


def _yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _validate_transition_record(transition: dict[str, object]) -> None:
    assert set(transition) == ALLOWED_TRANSITION_FIELDS
    assert transition["schema"] == "wor105-native-transition-v1"
    assert transition["issue"] == "WOR-105"
    assert transition["transition_task"] == "task-b06r"
    assert transition["enforcement_transition"] == "bootstrap_policy_to_native"
    assert transition["review_path"] == (
        ".work-bundle/orchestration/reviews/WOR-105-task-b06r-kernel-review-accepted.yaml"
    )
    assert transition["native_scope"] == "subsequent WOR-105 phase-c through phase-f execution only"
    assert transition["excluded_work"] == EXPECTED_EXCLUDED_WORK
    assert re.fullmatch(r"[0-9a-f]{64}", str(transition["review_sha256"]))
    assert re.fullmatch(r"[0-9a-f]{40}", str(transition["accepted_commit"]))
    assert re.fullmatch(r"[0-9a-f]{40}", str(transition["accepted_tree"]))
    assert re.fullmatch(
        rf"{transition['accepted_commit']}\+repository-evidence-sha256:[0-9a-f]{{64}}",
        str(transition["source_identity"]),
    )
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(transition["accepted_at"]))

    integrated = transition["integrated_validation"]
    handoff = transition["handoff_validation"]
    assert isinstance(integrated, dict)
    assert isinstance(handoff, dict)
    assert integrated["id"] == "VAL-B06R-TEST"
    assert integrated["result"] == "passed"
    assert isinstance(integrated["tests"], int) and integrated["tests"] > 0
    assert handoff["id"] == "VAL-B06R-IDENTITY"
    assert handoff["result"] == "passed"
    assert isinstance(handoff["adversarial_cases"], int) and handoff["adversarial_cases"] > 0

    participants = transition["participant_handoffs"]
    assert isinstance(participants, dict)
    assert set(participants) == EXPECTED_PARTICIPANTS
    assert all(re.fullmatch(r"[0-9a-f]{64}", str(digest)) for digest in participants.values())
    assert len(set(participants.values())) == len(EXPECTED_PARTICIPANTS)


def test_repository_frozen_transition_record_is_self_validating() -> None:
    _validate_transition_record(_yaml(TRANSITION_RECORD))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(unrecognized_contract_field=True),
        lambda value: value["participant_handoffs"].pop("task-b01"),
        lambda value: value["participant_handoffs"].update({"task-b01": "not-a-digest"}),
        lambda value: value.update(enforcement_transition="native_to_bootstrap_policy"),
        lambda value: value.update(review_sha256="not-a-digest"),
        lambda value: value["excluded_work"].append("unapproved-work"),
        lambda value: value.update(source_identity="substitute-identity"),
    ],
)
def test_frozen_transition_validation_rejects_incomplete_or_injected_records(mutation) -> None:
    transition = deepcopy(_yaml(TRANSITION_RECORD))
    mutation(transition)

    with pytest.raises(AssertionError):
        _validate_transition_record(transition)


def test_native_transition_binds_accepted_kernel_source_identity() -> None:
    transition = _yaml(TRANSITION_RECORD)
    accepted_commit = transition["accepted_commit"]
    accepted_tree = subprocess.run(
        ["git", "rev-parse", f"{accepted_commit}^{{tree}}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert transition["accepted_tree"] == accepted_tree
    assert re.fullmatch(
        rf"{accepted_commit}\+repository-evidence-sha256:[0-9a-f]{{64}}",
        str(transition["source_identity"]),
    )
