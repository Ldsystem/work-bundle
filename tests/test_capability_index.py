from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPO_ROOT / "scripts" / "keep-summarizing"


def _load_module() -> object:
    previous = sys.modules.pop("capability_index", None)
    sys.path.insert(0, str(SCRIPT_ROOT))
    try:
        return importlib.import_module("capability_index")
    finally:
        sys.path.remove(str(SCRIPT_ROOT))
        if previous is not None:
            sys.modules["capability_index_previous"] = previous


capability_index = _load_module()


def _evidence() -> list[dict[str, object]]:
    return [
        {
            "evidence_id": "ev:spec",
            "kind": "accepted_spec",
            "locator": "spec.md",
            "identity": "sha256:abc",
            "authority": True,
            "observed_at": "2026-09-05T00:00:00Z",
        }
    ]


def _node(node_id: str, *, kind: str = "capability", parent_id: str | None = "domain:root") -> dict[str, object]:
    return {
        "node_id": node_id,
        "kind": kind,
        "title": node_id,
        "summary": "summary",
        "actor": "orchestrator",
        "outcome": "bounded result",
        "preconditions": [],
        "effects": [],
        "failures": [],
        "policies": [],
        "aliases": [],
        "lifecycle": "accepted",
        "freshness": "current",
        "parent_id": parent_id,
        "evidence_ids": ["ev:spec"],
    }


def _store_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "index_id": "index:main",
        "nodes": [
            _node("domain:root", kind="domain", parent_id=None),
            _node("capability:review"),
        ],
        "relations": [
            {
                "relation_id": "rel:root-review",
                "from_id": "domain:root",
                "to_id": "capability:review",
                "type": "contains",
                "evidence_ids": ["ev:spec"],
            }
        ],
        "evidence": _evidence(),
        "generated_at": "2026-09-05T00:00:00Z",
        "source_digest": "sha256:source",
        "extensions": {"producer": "wor105"},
    }


def test_store_round_trips_stable_units_relations_and_extensions(tmp_path: Path) -> None:
    index = capability_index.CapabilityIndex.from_dict(_store_payload())

    path = tmp_path / "capabilities.json"
    index.save(path)
    restored = capability_index.CapabilityIndex.load(path)

    assert restored.to_dict() == _store_payload()
    assert restored.node("capability:review").node_id == "capability:review"


@pytest.mark.parametrize(
    "mutate, match",
    [
        (lambda payload: payload["nodes"].append(dict(payload["nodes"][1])), "duplicate node_id"),
        (lambda payload: payload["relations"].append(dict(payload["relations"][0])), "duplicate relation_id"),
        (lambda payload: payload["nodes"][1].update({"node_id": "bad id"}), "node_id"),
        (lambda payload: payload["relations"][0].update({"to_id": "capability:missing"}), "unknown to_id"),
        (lambda payload: payload["nodes"][1].update({"unexpected": True}), "unknown fields"),
    ],
)
def test_store_rejects_invalid_or_duplicate_records(mutate, match: str) -> None:
    payload = _store_payload()
    mutate(payload)

    with pytest.raises(capability_index.CapabilityIndexError, match=match):
        capability_index.CapabilityIndex.from_dict(payload)


def test_store_requires_one_parent_except_domain_roots() -> None:
    payload = _store_payload()
    payload["nodes"][1]["parent_id"] = None

    with pytest.raises(capability_index.CapabilityIndexError, match="exactly one parent"):
        capability_index.CapabilityIndex.from_dict(payload)


def test_store_rejects_contains_cycles() -> None:
    payload = _store_payload()
    payload["relations"].clear()
    payload["nodes"].append(_node("capability:child", parent_id="capability:review"))
    payload["nodes"][1]["parent_id"] = "capability:child"
    payload["relations"].extend(
        [
            {
                "relation_id": "rel:review-child",
                "from_id": "capability:review",
                "to_id": "capability:child",
                "type": "contains",
                "evidence_ids": ["ev:spec"],
            },
            {
                "relation_id": "rel:child-review",
                "from_id": "capability:child",
                "to_id": "capability:review",
                "type": "contains",
                "evidence_ids": ["ev:spec"],
            },
        ]
    )

    with pytest.raises(capability_index.CapabilityIndexError, match="contains cycle"):
        capability_index.CapabilityIndex.from_dict(payload)


def test_store_requires_parent_relation_to_match_parent_id() -> None:
    payload = _store_payload()
    payload["relations"].clear()

    with pytest.raises(capability_index.CapabilityIndexError, match="canonical parent relation"):
        capability_index.CapabilityIndex.from_dict(payload)
