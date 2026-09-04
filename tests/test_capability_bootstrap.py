from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPO_ROOT / "scripts" / "keep-summarizing"
sys.path.insert(0, str(SCRIPT_ROOT))
try:
    capability_index = importlib.import_module("capability_index")
finally:
    sys.path.remove(str(SCRIPT_ROOT))


def _records() -> list[dict[str, object]]:
    return [
        {
            "id": "note-review-routing",
            "domain": "orchestration",
            "title": "Review routing",
            "summary": "Route findings to the first broken owner",
            "actor": "orchestrator",
            "outcome": "bounded repair",
            "status": "implemented",
            "aliases": ["first broken artifact"],
            "evidence": [
                {
                    "kind": "accepted_spec",
                    "locator": "spec.md#REQ-011",
                    "identity": "sha256:spec",
                    "authority": True,
                    "observed_at": "2026-09-05T00:00:00Z",
                }
            ],
        },
        {
            "id": "note-unproven-helper",
            "domain": "orchestration",
            "title": "Possible helper",
            "summary": "A lead without supporting evidence",
            "actor": "developer",
            "outcome": "unknown",
            "status": "confirmed",
            "source_locator": "notes/helper.md",
            "evidence": [],
        },
    ]


def test_bootstrap_is_idempotent_and_preserves_provenance() -> None:
    first = capability_index.bootstrap_legacy_capabilities(
        _records(), index_id="index:legacy", generated_at="2026-09-05T00:00:00Z"
    )
    second = capability_index.bootstrap_legacy_capabilities(
        list(reversed(_records())), index_id="index:legacy", generated_at="2026-09-05T00:00:00Z"
    )

    assert first.to_dict() == second.to_dict()
    proven = first.node("capability:note-review-routing")
    assert proven.lifecycle == "accepted"
    assert proven.evidence_ids
    evidence = {item.evidence_id: item for item in first.evidence}
    assert evidence[proven.evidence_ids[0]].locator == "spec.md#REQ-011"
    assert evidence[proven.evidence_ids[0]].identity == "sha256:spec"


def test_bootstrap_missing_evidence_cannot_create_authority() -> None:
    index = capability_index.bootstrap_legacy_capabilities(
        _records(), index_id="index:legacy", generated_at="2026-09-05T00:00:00Z"
    )

    unproven = index.node("capability:note-unproven-helper")
    assert unproven.lifecycle == "candidate"
    assert unproven.evidence_ids == ()
    assert capability_index.retrieve_by_intent(index, "possible helper unknown") == ()


def test_bootstrap_stable_ids_do_not_depend_on_source_paths() -> None:
    before = _records()
    after = _records()
    before[0]["source_locator"] = "old/path.md"
    after[0]["source_locator"] = "new/path.md"

    old_index = capability_index.bootstrap_legacy_capabilities(
        before, index_id="index:legacy", generated_at="2026-09-05T00:00:00Z"
    )
    new_index = capability_index.bootstrap_legacy_capabilities(
        after, index_id="index:legacy", generated_at="2026-09-05T00:00:00Z"
    )

    assert {node.node_id for node in old_index.nodes} == {node.node_id for node in new_index.nodes}
