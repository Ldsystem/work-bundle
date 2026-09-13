from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import review_runtime  # noqa: E402
from test_orchestration_reviews import stage_review  # noqa: E402


def _reset_pair() -> tuple[dict[str, object], dict[str, object]]:
    previous = stage_review("plan")
    previous.update(
        review_mode="initial",
        review_target_kind="stage",
        repair_frontier=None,
        review_reset=None,
    )
    current = deepcopy(previous)
    current.update(
        review_id="review-plan-current",
        review_reset={
            "prior_review_id": previous["review_id"],
            "reason_class": "scope",
            "reason": "Accepted plan scope changed.",
        },
        previous_review=previous,
    )
    return previous, current


def test_v2_publication_persists_direct_immutable_current_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous, current = _reset_pair()
    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_args: None)
    review_runtime.publish_review(
        tmp_path, previous, current_target_identity=previous["target_identity"]
    )
    reference = review_runtime.publish_review(
        tmp_path, current, current_target_identity=current["target_identity"]
    )

    authority_path = review_runtime.current_review_authority_path(
        tmp_path, str(current["review_id"])
    )
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    assert authority["schema"] == "stage-review-v2"
    assert authority["current_authority"]["record_sha256"] == reference["sha256"]
    assert not authority_path.stat().st_mode & 0o222


def test_current_v2_authority_load_does_not_replay_predecessor_or_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous, current = _reset_pair()
    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_args: None)
    previous_reference = review_runtime.publish_review(
        tmp_path, previous, current_target_identity=previous["target_identity"]
    )
    reference = review_runtime.publish_review(
        tmp_path, current, current_target_identity=current["target_identity"]
    )
    review_runtime._review_store_path(tmp_path, previous_reference["review_id"]).unlink()
    review_runtime.current_review_authority_path(
        tmp_path, previous_reference["review_id"]
    ).unlink()
    monkeypatch.setattr(
        review_runtime,
        "_stored_stage_history",
        lambda *_args: pytest.fail("historical predecessor traversal"),
    )
    monkeypatch.setattr(
        review_runtime,
        "_validate_reviewer_run",
        lambda *_args: pytest.fail("receipt completeness replay"),
    )

    loaded, validated = review_runtime.load_stored_review(
        tmp_path, reference, current_target_identity=current["target_identity"]
    )

    assert loaded == current
    assert validated.review_id == current["review_id"]


def test_current_review_gate_consumes_direct_authority_without_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous, current = _reset_pair()
    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_args: None)
    previous_reference = review_runtime.publish_review(
        tmp_path, previous, current_target_identity=previous["target_identity"]
    )
    review_runtime.publish_review(
        tmp_path, current, current_target_identity=current["target_identity"]
    )
    review_runtime._review_store_path(tmp_path, previous_reference["review_id"]).unlink()
    review_runtime.current_review_authority_path(
        tmp_path, previous_reference["review_id"]
    ).unlink()
    monkeypatch.setattr(
        review_runtime,
        "_stored_stage_history",
        lambda *_args: pytest.fail("current gate traversed history"),
    )
    monkeypatch.setattr(
        review_runtime,
        "_validate_reviewer_run",
        lambda *_args: pytest.fail("current gate replayed receipt"),
    )

    review_runtime._require_current_review(
        tmp_path, "plan", current["target_identity"]
    )


def test_corrupt_direct_binding_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = stage_review("plan")
    monkeypatch.setattr(review_runtime, "_validate_reviewer_run", lambda *_args: None)
    reference = review_runtime.publish_review(
        tmp_path, current, current_target_identity=current["target_identity"]
    )
    authority_path = review_runtime.current_review_authority_path(
        tmp_path, reference["review_id"]
    )
    authority_path.chmod(0o600)
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["authority_sha256"] = "0" * 64
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    authority_path.chmod(0o444)

    with pytest.raises(review_runtime.ReviewContractError, match="authority digest"):
        review_runtime.load_stored_review(
            tmp_path, reference, current_target_identity=current["target_identity"]
        )


def test_legacy_adapter_validates_only_the_current_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous, current = _reset_pair()
    current["reviewer_run"] = {"run_id": "legacy-run", "sha256": "a" * 64}
    path = review_runtime._review_store_path(tmp_path, str(current["review_id"]))
    path.parent.mkdir(parents=True)
    raw = (json.dumps(current, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o444)
    reference = {
        "review_id": current["review_id"],
        "sha256": __import__("hashlib").sha256(raw).hexdigest(),
    }
    monkeypatch.setattr(
        review_runtime,
        "_stored_stage_history",
        lambda *_args: pytest.fail("legacy predecessor traversal"),
    )
    monkeypatch.setattr(
        review_runtime,
        "_validate_reviewer_run",
        lambda *_args: pytest.fail("legacy receipt replay"),
    )

    _loaded, validated = review_runtime.load_stored_review(
        tmp_path, reference, current_target_identity=current["target_identity"]
    )

    assert validated.review_id == current["review_id"]
