from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
if str(ORCHESTRATION) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATION))

import bounded_closure  # noqa: E402


def _workspace(tmp_path: Path, *, limit: int = 5) -> Path:
    metadata = tmp_path / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "metadata_version: 4\n"
        "workspace:\n"
        "  id: workspace-test\n"
        "  slug: test\n"
        "  mode: single-repository\n"
        "orchestration_control:\n"
        "  schema_version: 1\n"
        f"  post_execution_review_round_limit: {limit}\n",
        encoding="utf-8",
    )
    return tmp_path


def _target(revision: str = "a" * 40) -> dict[str, object]:
    return {
        "artifact_id": "plan-flow",
        "revision": revision,
        "sha256": "b" * 64,
        "source_tree": "c" * 40,
    }


def _begin(root: Path, number: int = 1, **overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "flow_id": "flow-stable",
        "request_id": f"request-{number}",
        "review_id": f"review-{number}",
        "target_identity": _target(chr(96 + number) * 40),
        "executor_attempts": [
            {"execution_id": "executor-1", "state": "completed"},
        ],
        "known_missing_evidence": [],
    }
    arguments.update(overrides)
    return bounded_closure.begin_review_round(root, **arguments)


@pytest.mark.parametrize(
    "missing",
    ["accepted_result", "validation_receipt", "reviewer_provenance"],
)
def test_round_one_allows_each_known_missing_evidence_but_refuses_active_executor(
    tmp_path: Path, missing: str,
) -> None:
    root = _workspace(tmp_path)

    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_NOT_TERMINAL",
    ):
        _begin(
            root,
            executor_attempts=[{"execution_id": "executor-active", "state": "running"}],
        )

    reserved = _begin(
        root,
        known_missing_evidence=[missing],
    )

    assert reserved["round_number"] == 1
    assert reserved["execution_complete"] is True
    assert reserved["known_missing_evidence"] == [missing]
    assert reserved["state"] == "reserved"


def test_begin_is_idempotent_only_for_exact_request_and_target(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    first = _begin(root)

    assert _begin(root) == first
    changed = _begin(
        root,
        review_id="review-2",
        target_identity=_target("d" * 40),
    )

    assert changed["round_number"] == 2
    assert changed["round_id"] != first["round_id"]


def test_completed_rounds_survive_plan_revision_and_fifth_requires_finalization(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)

    for number in range(1, 6):
        reserved = _begin(root, number)
        completed = bounded_closure.complete_review_round(
            root,
            flow_id="flow-stable",
            round_id=str(reserved["round_id"]),
            outcome="blocked",
            audit_block={
                "code": "missing-evidence",
                "missing": ["accepted_result"],
            },
        )
        assert completed["round_number"] == number
        assert completed["state"] == "completed"

    status = bounded_closure.review_round_status(root, flow_id="flow-stable")
    assert status["completed_rounds"] == 5
    assert status["finalization_required"] is True
    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_FINALIZATION_REQUIRED",
    ):
        _begin(root, 6)


def test_duplicate_completion_does_not_increment_or_change_judgment(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    reserved = _begin(root)
    arguments = {
        "flow_id": "flow-stable",
        "round_id": str(reserved["round_id"]),
        "outcome": "blocked",
        "audit_block": {"code": "preparation-failed", "missing": ["review"]},
    }

    first = bounded_closure.complete_review_round(root, **arguments)
    assert bounded_closure.complete_review_round(root, **arguments) == first
    assert bounded_closure.review_round_status(root, flow_id="flow-stable")[
        "completed_rounds"
    ] == 1
    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_JUDGMENT_COLLISION",
    ):
        bounded_closure.complete_review_round(
            root,
            **{**arguments, "audit_block": {"code": "different", "missing": []}},
        )


def test_accepted_round_stops_further_review_before_limit(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    reserved = _begin(root)
    bounded_closure.mark_review_round_prepared(
        root,
        flow_id="flow-stable",
        round_id=str(reserved["round_id"]),
    )
    review_path = root / ".work-bundle/orchestration/reviews/review-1.json"
    review_path.parent.mkdir(parents=True)
    review_path.write_text('{"verdict":"accepted"}\n', encoding="utf-8")
    review_path.chmod(0o444)
    bounded_closure.complete_review_round(
        root,
        flow_id="flow-stable",
        round_id=str(reserved["round_id"]),
        outcome="accepted",
        review_reference={
            "review_id": "review-1",
            "sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        },
    )

    assert bounded_closure.review_round_status(
        root, flow_id="flow-stable"
    )["finalization_required"] is True
    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_FINALIZATION_REQUIRED",
    ):
        _begin(root, 2)


def test_product_outcome_requires_store_owned_immutable_review_reference(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    reserved = _begin(root)
    bounded_closure.mark_review_round_prepared(
        root,
        flow_id="flow-stable",
        round_id=str(reserved["round_id"]),
    )

    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_EVIDENCE_INVALID",
    ):
        bounded_closure.complete_review_round(
            root,
            flow_id="flow-stable",
            round_id=str(reserved["round_id"]),
            outcome="accepted",
            review_reference={"review_id": "review-1", "sha256": "e" * 64},
        )


def test_competing_reservations_cannot_create_round_six(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    def reserve(number: int) -> str:
        try:
            return str(_begin(root, number)["round_id"])
        except bounded_closure.BoundedClosureError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=10) as pool:
        outcomes = list(pool.map(reserve, range(1, 11)))

    round_ids = {value for value in outcomes if value.startswith("flow-stable:round:")}
    assert round_ids == {
        f"flow-stable:round:{number:03d}" for number in range(1, 6)
    }
    assert outcomes.count("WB_POST_EXECUTION_FINALIZATION_REQUIRED") == 5


def test_current_metadata_migration_renames_legacy_policy_only(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    metadata = root / ".work-bundle/project.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "post_execution_review_round_limit", "review_revision_limit"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        bounded_closure.BoundedClosureError,
        match="WB_POST_EXECUTION_LEGACY_POLICY_REJECTED",
    ):
        _begin(root)
    assert bounded_closure.migrate_bounded_review_policy(root) is True
    assert "review_revision_limit" not in metadata.read_text(encoding="utf-8")
    assert _begin(root)["round_number"] == 1
