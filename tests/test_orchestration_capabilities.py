from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_ROOT = REPO_ROOT / "scripts" / "keep-summarizing"
ORCHESTRATION_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(CAPABILITY_ROOT))
try:
    capability_index = importlib.import_module("capability_index")
finally:
    sys.path.remove(str(CAPABILITY_ROOT))
sys.path.insert(0, str(ORCHESTRATION_ROOT))
try:
    execution_context = importlib.import_module("execution_context")
finally:
    sys.path.remove(str(ORCHESTRATION_ROOT))


NEIGHBORS = (
    "production composition",
    "identity replay",
    "owner state",
    "symlink containment",
    "effect boundary",
    "evidence provenance",
    "evaluator context",
)


def _node(node_id: str, title: str, *, lifecycle: str = "accepted", freshness: str = "current", evidence_ids=None):
    return {
        "node_id": node_id,
        "kind": "capability",
        "title": title,
        "summary": f"{title} behavior",
        "actor": "orchestrator",
        "outcome": "safe evaluation",
        "preconditions": [],
        "effects": [],
        "failures": [],
        "policies": [],
        "aliases": [title],
        "lifecycle": lifecycle,
        "freshness": freshness,
        "parent_id": "domain:evaluation",
        "evidence_ids": list(evidence_ids or ["ev:accepted"]),
    }


def _index(extra_nodes=()):
    nodes = [
        {
            **_node("domain:evaluation", "Evaluation", evidence_ids=["ev:accepted"]),
            "kind": "domain",
            "parent_id": None,
        },
        *[
            _node(f"capability:{name.replace(' ', '-')}", name)
            for name in NEIGHBORS
        ],
        *extra_nodes,
    ]
    relations = [
        {
            "relation_id": f"rel:{node['node_id'].split(':')[1]}",
            "from_id": "domain:evaluation",
            "to_id": node["node_id"],
            "type": "contains",
            "evidence_ids": list(node["evidence_ids"]),
        }
        for node in nodes[1:]
    ]
    return capability_index.CapabilityIndex.from_dict(
        {
            "schema_version": "1.0.0",
            "index_id": "index:evaluation",
            "nodes": nodes,
            "relations": relations,
            "evidence": [
                {
                    "evidence_id": "ev:accepted",
                    "kind": "accepted_spec",
                    "locator": "spec.md",
                    "identity": "sha256:spec",
                    "authority": True,
                    "observed_at": "2026-09-05T00:00:00Z",
                },
                {
                    "evidence_id": "ev:lead",
                    "kind": "source",
                    "locator": "lead.py",
                    "identity": "sha256:lead",
                    "authority": False,
                    "observed_at": "2026-09-05T00:00:00Z",
                },
            ],
            "generated_at": "2026-09-05T00:00:00Z",
            "source_digest": "sha256:source",
        }
    )


def test_capability_projection_is_bounded_and_preserves_provenance() -> None:
    stale = _node("capability:stale", "evaluation legacy", freshness="stale")
    advisory = _node("capability:lead", "evaluation proposal", lifecycle="candidate", evidence_ids=["ev:lead"])
    result = execution_context.project_capability_neighborhood(
        _index([stale, advisory]), "evaluate native work", depth="standard", max_nodes=5
    )

    assert len(result["inclusions"]) <= 5
    assert all(item["evidence_ids"] for item in result["inclusions"])
    excluded = {item["node_id"]: item["reason"] for item in result["exclusions"]}
    assert excluded["capability:stale"] == "stale"
    assert excluded["capability:lead"] == "non_authoritative"
    assert result["source_index_digest"].startswith("sha256:")


def test_required_evaluation_neighbors_surface_every_family_early() -> None:
    result = execution_context.project_capability_neighborhood(
        _index(), "evaluate native work", depth="light", max_nodes=20
    )

    assert all(set(item) == {"node_id", "reason", "rank", "evidence_ids"} for item in result["inclusions"])
    prefix = "required_evaluation_neighbor:"
    surfaced = {
        item["reason"].removeprefix(prefix)
        for item in result["inclusions"]
        if item["reason"].startswith(prefix)
    }
    assert surfaced == set(NEIGHBORS)
    assert execution_context.required_evaluation_neighbors() == NEIGHBORS


def test_capability_authority_delta_excludes_advisory_promotions() -> None:
    before = _index()
    accepted = _node("capability:new-accepted", "new accepted behavior")
    candidate = _node("capability:new-lead", "new lead", lifecycle="candidate", evidence_ids=["ev:lead"])
    after = _index([accepted, candidate])

    delta = execution_context.capability_authority_delta(before, after)

    assert delta["added"] == ["capability:new-accepted"]
    assert delta["advisory_only"] == ["capability:new-lead"]
