from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
KEEP_SUMMARIZING_SCRIPTS = REPO_ROOT / "scripts" / "keep-summarizing"


def load_keep_summarizing_modules() -> tuple[object, object]:
    module_names = ("core", "indexes", "query")
    previous = {name: sys.modules.get(name) for name in module_names}
    for name in module_names:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(KEEP_SUMMARIZING_SCRIPTS))
    try:
        indexes_module = importlib.import_module("indexes")
        query_module = importlib.import_module("query")
    finally:
        sys.path.remove(str(KEEP_SUMMARIZING_SCRIPTS))
        for name in module_names:
            sys.modules.pop(name, None)
            if previous[name] is not None:
                sys.modules[name] = previous[name]
    return indexes_module, query_module


indexes, query = load_keep_summarizing_modules()

LIFECYCLE_FIXTURES = [
    ("tender", "confirmed"),
    ("investigation", "proposed"),
    ("customer_design", "rejected"),
    ("bidding", "current"),
    ("development_design", "confirmed"),
    ("implementation", "implemented"),
    ("deployment", "current"),
    ("go_live_delivery", "current"),
    ("operation", "current"),
]
FORBIDDEN_SCRIPT_FIELDS = {
    "supports_current_purpose",
    "opposes_current_purpose",
    "conflict",
    "semantic_relevance",
    "authority_decision",
    "truth_confidence",
    "recommended_action",
    "should_block",
    "retrieval_role",
}


@pytest.fixture
def knowledge_root(tmp_path: Path) -> Path:
    root = tmp_path / ".work-bundle" / "knowledge"
    (root / "indexes").mkdir(parents=True)
    docs = [
        {
            "id": f"note-{lifecycle}",
            "path": f"notes/{lifecycle}/note.md",
            "title": f"Lifecycle discovery {lifecycle}",
            "lifecycle_stage": lifecycle,
            "perspective": f"{lifecycle}/fixture",
            "status": status,
            "source_type": "source_note",
            "updated_at": "2026-06-06",
            "summary": "shared discovery fixture",
            "tags": ["discovery"],
            "body": "shared discovery fixture body",
            "sqlite_include": True,
        }
        for lifecycle, status in LIFECYCLE_FIXTURES
    ]
    indexes.build_sqlite_index(root, docs)
    return root


def run_query(knowledge_root: Path, capsys: pytest.CaptureFixture[str], **overrides: object) -> tuple[dict[str, object], list[dict[str, object]]]:
    values: dict[str, object] = {
        "project": "fixture",
        "target": None,
        "query": "shared discovery fixture",
        "limit": 20,
        "include_background": False,
        "knowledge_root": str(knowledge_root),
        "project_root": None,
        "cwd": None,
        "registry_file": None,
    }
    values.update(overrides)
    query.cmd_query(argparse.Namespace(**values))
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows
    trace = rows[0]["query_trace"]
    candidates = rows[1:]
    return trace, candidates


def assert_no_forbidden_script_fields(payload: object) -> None:
    if isinstance(payload, dict):
        forbidden = FORBIDDEN_SCRIPT_FIELDS.intersection(payload)
        assert forbidden == set()
        for value in payload.values():
            assert_no_forbidden_script_fields(value)
    elif isinstance(payload, list):
        for value in payload:
            assert_no_forbidden_script_fields(value)


def test_neutral_candidate_discovery_spans_every_lifecycle_without_stage_gate(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(knowledge_root, capsys)

    assert trace == {
        "policy_hint": None,
        "query_anchors": ["shared", "discovery", "fixture"],
        "sources": {"fts": "queried", "vector": "unavailable", "bfs": "not_configured"},
    }
    assert {candidate["lifecycle_stage"] for candidate in candidates} == {
        lifecycle for lifecycle, _ in LIFECYCLE_FIXTURES
    }
    assert len(candidates) == len(LIFECYCLE_FIXTURES)


def test_target_policy_hint_is_optional_and_does_not_filter_discovery(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(knowledge_root, capsys, target="implementation_spec")

    assert trace["policy_hint"] == "implementation_spec"
    assert {candidate["policy_hint"] for candidate in candidates} == {"implementation_spec"}
    assert {candidate["lifecycle_stage"] for candidate in candidates} == {
        lifecycle for lifecycle, _ in LIFECYCLE_FIXTURES
    }


def test_full_candidate_discovery_remains_selective(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, candidates = run_query(knowledge_root, capsys, limit=3)

    assert len(candidates) == 3


def test_candidate_records_use_hybrid_mechanical_shape(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, candidates = run_query(knowledge_root, capsys, limit=1)

    candidate = candidates[0]
    assert {
        "id",
        "path",
        "title",
        "lifecycle_stage",
        "perspective",
        "status",
        "source_type",
        "updated_at",
        "summary",
        "tags",
        "mechanical_sources",
        "mechanical_scores",
        "trace",
        "policy_hint",
    } <= candidate.keys()
    assert candidate["mechanical_sources"] == {"fts": True, "vector": False, "bfs": False}
    assert set(candidate["mechanical_scores"]) == {
        "fts_rank",
        "vector_distance",
        "fusion_rank",
        "bfs_depth",
    }
    assert isinstance(candidate["mechanical_scores"]["fts_rank"], float)
    assert candidate["mechanical_scores"]["vector_distance"] is None
    assert candidate["mechanical_scores"]["fusion_rank"] == 1
    assert candidate["mechanical_scores"]["bfs_depth"] is None
    assert candidate["trace"] == {
        "query_anchors": ["shared", "discovery", "fixture"],
        "seed_candidate_id": None,
        "expansion_path": [],
    }


def test_query_trace_reports_vector_unavailable_status(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    indexes.build_vector_index_status(knowledge_root, [], "fixture", install_missing=False)

    trace, _ = run_query(knowledge_root, capsys)

    assert trace["sources"]["vector"] == "unavailable"


def test_index_rebuild_installs_and_loads_sqlite_vec_when_available(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / ".work-bundle" / "knowledge"
    note = root / "notes" / "development-design" / "architecture" / "source-of-truth" / "vector-index.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        """---
id: note-vector-index
title: Vector Index
lifecycle_stage: development_design
perspective: development-design/architecture/source-of-truth
status: current
source_type: source_code
summary: Vector index fixture.
tags:
  - vector
updated_at: 2026-06-28
---

# Vector Index

Vector index fixture body.
""",
        encoding="utf-8",
    )

    indexes.cmd_index(
        argparse.Namespace(
            project="fixture",
            knowledge_root=str(root),
            project_root=None,
            cwd=None,
            registry_file=None,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    vector_status = payload["vector_status"]
    assert vector_status["status"] == "rebuilt"
    assert vector_status["extension"] == "sqlite-vec"
    assert vector_status["chunks_indexed"] == 1
    assert (root / "indexes" / "vector-index.jsonl").read_text(encoding="utf-8")


def test_query_output_omits_forbidden_semantic_fields(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(knowledge_root, capsys, target="implementation_spec")

    assert_no_forbidden_script_fields(trace)
    for candidate in candidates:
        assert_no_forbidden_script_fields(candidate)
