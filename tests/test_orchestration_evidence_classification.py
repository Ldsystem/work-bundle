from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from evaluation_identity import (  # noqa: E402
    EvaluationIdentityError,
    validation_interval_identity,
)
from execution_context import project_validation_evidence  # noqa: E402
from review_runtime import (  # noqa: E402
    ReviewContractError,
    review_remains_current_after_observation,
    validate_evidence_causal_classification,
)


CAUSAL_ROUTES = {
    "claim_relevant_drift": ("claim-owner", "revalidate_claim", "route_current_owner", "claim_relevant"),
    "implementation_defect": ("task-owner", "repair_task", "route_current_owner", "claim_relevant"),
    "authority_plan_gap": ("plan-owner", "repair_authority_plan", "route_current_owner", "claim_relevant"),
    "evaluator_control_defect": ("evaluator-owner", "repair_evaluator_control", "route_evaluator_control_owner", "evaluator_only"),
    "non_claim_relevant": ("controller", "none", "diagnostic_only", "unrelated"),
}


def classification(causal_class: str, *, claim: str = "claim-001") -> dict[str, object]:
    owner, action, disposition, comparison = CAUSAL_ROUTES[causal_class]
    return {
        "observation_reference": "observation-001",
        "accepted_authority_comparison": {
            "authority_identity": "authority-sha256:abc",
            "result": comparison,
            "basis": "Compared the observation with the accepted claim and validation allocation.",
        },
        "causal_class": causal_class,
        "affected_claim": claim,
        "affected_owner": owner,
        "authorized_lifecycle_action": action,
        "disposition": disposition,
    }


@pytest.mark.parametrize("causal_class", list(CAUSAL_ROUTES))
def test_agent_owned_causal_classification_routes_all_five_classes(causal_class: str) -> None:
    record = classification(causal_class)
    validated = validate_evidence_causal_classification(record)
    assert validated.causal_class == causal_class
    assert validated.authorized_lifecycle_action == record["authorized_lifecycle_action"]


def test_raw_or_misrouted_evidence_cannot_manufacture_lifecycle_authority() -> None:
    with pytest.raises(ReviewContractError, match="classification"):
        validate_evidence_causal_classification({"observation_reference": "failed-test"})

    wrong = classification("non_claim_relevant")
    wrong["authorized_lifecycle_action"] = "repair_task"
    with pytest.raises(ReviewContractError, match="action"):
        validate_evidence_causal_classification(wrong)

    projected = project_validation_evidence(
        [{"id": "VAL-001", "command": "false", "result": "failed"}],
        evidence_capability={"invariants": []},
    )
    assert projected[0]["authority_effect"] == "observation_only"
    assert projected[0]["lifecycle_action_authorized"] is False


@pytest.mark.parametrize("causal_class", ["evaluator_control_defect", "non_claim_relevant"])
def test_unrelated_or_evaluator_observation_keeps_independent_review_current(causal_class: str) -> None:
    assert review_remains_current_after_observation(
        classification(causal_class), reviewed_claim="claim-001"
    )


def test_only_claim_relevant_current_owner_class_can_reopen_matching_review_claim() -> None:
    assert not review_remains_current_after_observation(
        classification("implementation_defect"), reviewed_claim="claim-001"
    )
    assert review_remains_current_after_observation(
        classification("implementation_defect", claim="different-claim"),
        reviewed_claim="claim-001",
    )


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], text=True, capture_output=True, check=True
    ).stdout.strip()


def commit(root: Path, name: str, content: str) -> str:
    (root / name).write_text(content, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-qm", content)
    return git(root, "rev-parse", "HEAD")


def test_historical_validation_stays_bound_to_frozen_endpoint_after_later_commits(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    baseline = commit(tmp_path, "product.txt", "baseline")
    endpoint = commit(tmp_path, "product.txt", "accepted endpoint")
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"scope":"accepted"}', encoding="utf-8")

    before = validation_interval_identity(
        tmp_path, baseline_revision=baseline, endpoint_revision=endpoint,
        endpoint_mode="frozen", manifest_path=manifest,
    )
    commit(tmp_path, "later.txt", "future work")
    after = validation_interval_identity(
        tmp_path, baseline_revision=baseline, endpoint_revision=endpoint,
        endpoint_mode="frozen", manifest_path=manifest,
    )
    assert after == before
    assert after["endpoint"]["revision"] == endpoint


def test_live_head_requires_explicit_current_contract(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    baseline = commit(tmp_path, "product.txt", "baseline")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    with pytest.raises(EvaluationIdentityError, match="live HEAD"):
        validation_interval_identity(
            tmp_path, baseline_revision=baseline, endpoint_revision="HEAD",
            endpoint_mode="frozen", manifest_path=manifest,
        )

    current = validation_interval_identity(
        tmp_path, baseline_revision=baseline, endpoint_revision="HEAD",
        endpoint_mode="current", manifest_path=manifest,
    )
    assert current["endpoint"]["revision"] == git(tmp_path, "rev-parse", "HEAD")
