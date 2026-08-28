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
HYBRID_CONTRACT_NOTES = [
    {
        "id": "note-exact-api",
        "path": "notes/implementation/api/resolve-widget-v2.md",
        "title": "resolveWidgetV2 API",
        "lifecycle_stage": "implementation",
        "perspective": "implementation/api",
        "status": "implemented",
        "source_type": "source_note",
        "updated_at": "2026-08-28",
        "summary": "Exact identifier contract for resolveWidgetV2.",
        "tags": ["resolveWidgetV2", "api"],
        "body": "The resolveWidgetV2 endpoint validates widget identifiers before returning the resolved widget.",
        "sqlite_include": True,
    },
    {
        "id": "note-paraphrase",
        "path": "notes/development-design/retrieval/conceptual-match.md",
        "title": "Conceptual Match Without Shared Wording",
        "lifecycle_stage": "development_design",
        "perspective": "development-design/retrieval",
        "status": "proposed",
        "source_type": "source_note",
        "updated_at": "2026-08-28",
        "summary": "Meaning based recall across vocabulary mismatch.",
        "tags": ["semantic-recall"],
        "body": "A reader asks how to locate advice that means the same thing even when none of the original wording is repeated.",
        "sqlite_include": True,
    },
    {
        "id": "note-hybrid",
        "path": "notes/development-design/retrieval/hybrid-recall.md",
        "title": "Hybrid Recall",
        "lifecycle_stage": "development_design",
        "perspective": "development-design/retrieval",
        "status": "current",
        "source_type": "source_note",
        "updated_at": "2026-08-28",
        "summary": "Hybrid retrieval combines lexical recall with conceptual matching.",
        "tags": ["hybrid-retrieval", "semantic-recall"],
        "body": "Hybrid retrieval preserves literal identifiers while adding meaning-based discovery.",
        "sqlite_include": True,
    },
    {
        "id": "note-noise",
        "path": "notes/operation/facilities/boiler-inspection.md",
        "title": "Boiler Inspection Calendar",
        "lifecycle_stage": "operation",
        "perspective": "operation/facilities",
        "status": "current",
        "source_type": "source_note",
        "updated_at": "2026-08-28",
        "summary": "Quarterly facilities inspection dates.",
        "tags": ["facilities"],
        "body": "Technicians record pressure gauges, relief valves, and combustion readings every quarter.",
        "sqlite_include": True,
    },
]


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


@pytest.fixture
def hybrid_retrieval_root(tmp_path: Path) -> Path:
    root = tmp_path / ".work-bundle" / "knowledge"
    (root / "indexes").mkdir(parents=True)
    indexes.build_sqlite_index(root, HYBRID_CONTRACT_NOTES)
    return root


@pytest.fixture
def hybrid_vector_root(hybrid_retrieval_root: Path) -> Path:
    chunks = [
        {
            "chunk_id": f"{note['id']}#body",
            "document_id": note["id"],
            "path": note["path"],
        }
        for note in HYBRID_CONTRACT_NOTES
    ]
    status = indexes.build_vector_index_status(hybrid_retrieval_root, chunks, "fixture")
    if status["status"] != "rebuilt":
        pytest.skip(f"sqlite-vec fixture backend unavailable: {status.get('reason', 'unknown reason')}")
    return hybrid_retrieval_root


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


def candidate_by_id(candidates: list[dict[str, object]], candidate_id: str) -> dict[str, object]:
    candidate = next((candidate for candidate in candidates if candidate["id"] == candidate_id), None)
    assert candidate is not None, (
        f"expected candidate {candidate_id!r}; got "
        f"{[candidate.get('id') for candidate in candidates]!r}"
    )
    return candidate


def write_vector_status(root: Path, **overrides: object) -> Path:
    status = {
        "status": "rebuilt",
        **indexes.expected_vector_metadata(),
        **overrides,
    }
    status_path = root / "indexes" / indexes.VECTOR_INDEX_STATUS_FILE
    status_path.write_text(json.dumps(status), encoding="utf-8")
    return status_path


def vector_trace_status(trace: dict[str, object]) -> str:
    vector = trace["sources"]["vector"]  # type: ignore[index]
    if isinstance(vector, dict):
        return str(vector.get("status", ""))
    return str(vector)


def vector_trace_reason(trace: dict[str, object]) -> str:
    vector = trace["sources"]["vector"]  # type: ignore[index]
    if isinstance(vector, dict):
        return str(vector.get("reason", ""))
    for key in ("source_reasons", "reasons", "source_details"):
        container = trace.get(key)
        if isinstance(container, dict):
            detail = container.get("vector")
            if isinstance(detail, dict):
                return str(detail.get("reason", ""))
            if detail is not None:
                return str(detail)
    return ""


def test_neutral_candidate_discovery_spans_every_lifecycle_without_stage_gate(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(knowledge_root, capsys)

    assert trace == {
        "policy_hint": None,
        "query_anchors": ["shared", "discovery", "fixture"],
        "sources": {"fts": "queried", "vector": "unavailable", "bfs": "not_configured"},
        "source_details": {"vector": {"reason": "missing vector index status"}},
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


def test_sqlite_vec_availability_probe_reports_import_unavailable_stably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = __import__

    def import_without_sqlite_vec(name: str, *args: object, **kwargs: object) -> object:
        if name == indexes.SQLITE_VEC_IMPORT:
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_without_sqlite_vec)

    assert indexes.sqlite_vec_availability_probe() == {
        "status": "unavailable",
        "reason": "sqlite-vec probe unavailable: import failed",
    }


def test_sqlite_vec_availability_probe_reports_temporary_load_unavailable_stably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnloadableSqliteVec:
        @staticmethod
        def load(_connection: object) -> None:
            raise RuntimeError("runner cannot load extension")

    real_import = __import__

    def import_unloadable_sqlite_vec(name: str, *args: object, **kwargs: object) -> object:
        if name == indexes.SQLITE_VEC_IMPORT:
            return UnloadableSqliteVec()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", import_unloadable_sqlite_vec)

    assert indexes.sqlite_vec_availability_probe() == {
        "status": "unavailable",
        "reason": "sqlite-vec probe unavailable: temporary load failed",
    }


def test_sqlite_vec_availability_probe_does_not_call_production_import_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LoadableSqliteVec:
        @staticmethod
        def load(_connection: object) -> None:
            return None

    def fail_if_called() -> tuple[object | None, str | None]:
        raise AssertionError("availability probe delegated to production import helper")

    real_import = __import__

    def import_loadable_sqlite_vec(name: str, *args: object, **kwargs: object) -> object:
        if name == indexes.SQLITE_VEC_IMPORT:
            return LoadableSqliteVec()
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(indexes, "install_sqlite_vec", fail_if_called)
    monkeypatch.setattr("builtins.__import__", import_loadable_sqlite_vec)

    assert indexes.sqlite_vec_availability_probe() == {
        "status": "available",
        "reason": None,
    }


def test_production_index_rebuild_keeps_proposed_notes_in_vector_discovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    probe = indexes.sqlite_vec_availability_probe()
    if probe["status"] == "unavailable":
        pytest.skip(str(probe["reason"]))
    assert probe == {"status": "available", "reason": None}

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
    proposed = root / "notes" / "development-design" / "retrieval" / "conceptual-match.md"
    proposed.parent.mkdir(parents=True)
    proposed.write_text(
        """---
id: note-proposed-paraphrase
title: Conceptual Match Without Shared Wording
lifecycle_stage: development_design
perspective: development-design/retrieval
status: proposed
source_type: source_note
summary: Meaning based recall across vocabulary mismatch.
tags:
  - semantic-recall
updated_at: 2026-08-28
---

# Conceptual Match Without Shared Wording

A reader asks how to locate advice that means the same thing even when none of the original wording is repeated.
""",
        encoding="utf-8",
    )
    confidential = root / "notes" / "implementation" / "confidential.md"
    confidential.parent.mkdir(parents=True)
    confidential.write_text(
        """---
id: note-confidential
title: Confidential Fixture
lifecycle_stage: implementation
perspective: implementation/security
status: current
source_type: source_note
sensitivity: confidential
summary: This note must not enter vector discovery.
updated_at: 2026-08-28
---

# Confidential Fixture

Confidential discovery material.
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
    assert vector_status["chunks_indexed"] == 2
    assert vector_status["embedding_model"] == indexes.EMBEDDING_MODEL
    assert vector_status["embedding_model_version"] == indexes.EMBEDDING_MODEL_VERSION
    assert vector_status["embedding_package_version"] == indexes.EMBEDDING_PACKAGE_VERSION
    assert vector_status["dimensions"] == indexes.VECTOR_DIMENSIONS
    assert vector_status["chunking"] == indexes.VECTOR_CHUNKING
    assert vector_status["index_schema"] == indexes.VECTOR_INDEX_SCHEMA
    vector_artifact = (root / "indexes" / "vector-index.jsonl").read_text(encoding="utf-8")
    assert vector_artifact
    assert "note-confidential" not in vector_artifact

    trace, candidates = run_query(
        root,
        capsys,
        query="retrieve semantically similar knowledge using different terms",
        limit=4,
    )
    proposed_candidate = candidate_by_id(candidates, "note-proposed-paraphrase")
    assert vector_trace_status(trace) == "queried"
    assert proposed_candidate["status"] == "proposed"
    assert proposed_candidate["mechanical_sources"] == {"fts": False, "vector": True, "bfs": False}


def test_query_output_omits_forbidden_semantic_fields(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(knowledge_root, capsys, target="implementation_spec")

    assert_no_forbidden_script_fields(trace)
    for candidate in candidates:
        assert_no_forbidden_script_fields(candidate)


def test_hybrid_retrieval_contract_exact_identifier_keeps_lexical_win(
    hybrid_retrieval_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, candidates = run_query(hybrid_retrieval_root, capsys, query="resolveWidgetV2", limit=4)

    assert candidates[0]["id"] == "note-exact-api"
    assert candidates[0]["mechanical_sources"]["fts"] is True


def test_hybrid_retrieval_contract_paraphrase_has_vector_provenance_without_lexical_overlap(
    hybrid_vector_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(
        hybrid_vector_root,
        capsys,
        query="retrieve semantically similar knowledge using different terms",
        limit=4,
    )

    paraphrase = candidate_by_id(candidates, "note-paraphrase")
    assert vector_trace_status(trace) == "queried"
    assert paraphrase["mechanical_sources"] == {"fts": False, "vector": True, "bfs": False}
    assert isinstance(paraphrase["mechanical_scores"]["vector_distance"], float)


def test_hybrid_retrieval_contract_deduplicates_both_sources_and_is_deterministic(
    hybrid_vector_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first_trace, first = run_query(hybrid_vector_root, capsys, query="hybrid retrieval semantic recall", limit=4)
    second_trace, second = run_query(hybrid_vector_root, capsys, query="hybrid retrieval semantic recall", limit=4)

    hybrid = candidate_by_id(first, "note-hybrid")
    assert vector_trace_status(first_trace) == vector_trace_status(second_trace) == "queried"
    assert [candidate["id"] for candidate in first] == [candidate["id"] for candidate in second]
    assert len({candidate["id"] for candidate in first}) == len(first)
    assert hybrid["mechanical_sources"] == {"fts": True, "vector": True, "bfs": False}
    assert [candidate["mechanical_scores"]["fusion_rank"] for candidate in first] == list(
        range(1, len(first) + 1)
    )
    assert "note-noise" not in {candidate["id"] for candidate in first}


def test_hybrid_retrieval_contract_uses_reciprocal_rank_fusion_not_source_append(
    hybrid_retrieval_root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def candidate(candidate_id: str, rank: float | None, distance: float | None) -> dict[str, object]:
        return {
            "id": candidate_id,
            "path": f"notes/{candidate_id}.md",
            "title": candidate_id,
            "lifecycle_stage": "implementation",
            "perspective": "implementation/fixture",
            "status": "current",
            "source_type": "source_note",
            "updated_at": "2026-08-28",
            "summary": candidate_id,
            "tags": "[]",
            "body": candidate_id,
            "rank": rank,
            "vector_distance": distance,
        }

    class FakeHybridConnection:
        row_factory: object = None

        def execute(self, sql: str, _parameters: object) -> list[dict[str, object]]:
            if "knowledge_chunk_vec" in sql:
                return [candidate("vector-only", None, 0.1), candidate("both", None, 0.2)]
            if "knowledge_note_fts" in sql:
                return [candidate("fts-only", 0.1, None), candidate("both", 0.2, None)]
            raise AssertionError(f"unexpected hybrid query: {sql}")

        def close(self) -> None:
            return None

    class FakeSqliteVec:
        @staticmethod
        def serialize_float32(_values: object) -> bytes:
            return b"fixture-vector"

    write_vector_status(hybrid_retrieval_root)
    monkeypatch.setattr(query.sqlite3, "connect", lambda _path: FakeHybridConnection())
    monkeypatch.setattr(query, "load_sqlite_vec", lambda _connection: (FakeSqliteVec(), None))
    monkeypatch.setattr(query, "local_text_vector", lambda _text, query: [0.0] * indexes.VECTOR_DIMENSIONS)

    trace, candidates = run_query(hybrid_retrieval_root, capsys, query="fixture fusion", limit=3)

    assert vector_trace_status(trace) == "queried"
    assert [item["id"] for item in candidates] == ["both", "fts-only", "vector-only"]
    assert candidate_by_id(candidates, "both")["mechanical_sources"] == {
        "fts": True,
        "vector": True,
        "bfs": False,
    }


def test_hybrid_retrieval_contract_fallback_reports_reason_and_keeps_fts(
    hybrid_retrieval_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_vector_status(
        hybrid_retrieval_root,
        status="unavailable",
        reason="fixture backend unavailable",
        fallback="sqlite_fts",
    )

    trace, candidates = run_query(hybrid_retrieval_root, capsys, query="resolveWidgetV2", limit=4)

    assert vector_trace_status(trace) in {"unavailable", "failed"}
    assert vector_trace_reason(trace) == "fixture backend unavailable"
    assert candidates[0]["id"] == "note-exact-api"
    assert all(candidate["mechanical_sources"]["vector"] is False for candidate in candidates)


def test_hybrid_retrieval_contract_runtime_has_no_package_manager_shellout() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            KEEP_SUMMARIZING_SCRIPTS / "indexes.py",
            KEEP_SUMMARIZING_SCRIPTS / "query.py",
        )
    )

    assert '"-m", "pip"' not in source
    assert '"-m", "uv"' not in source


def test_hybrid_retrieval_contract_runtime_declares_pinned_uv_dependencies() -> None:
    source = (REPO_ROOT / "scripts" / "ks.py").read_text(encoding="utf-8")

    assert '# /// script' in source
    assert '"pyyaml==6.0.3"' in source
    assert '"sqlite-vec==0.1.9"' in source
    assert '"fastembed==0.8.0"' in source


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_model", "incompatible-model"),
        ("dimensions", 999),
        ("index_schema", "future-schema"),
        ("embedding_model", None),
        ("embedding_model_version", None),
        ("index_schema", None),
    ],
)
def test_hybrid_retrieval_contract_incompatible_rebuilt_index_requires_rebuild(
    hybrid_retrieval_root: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    status_path = write_vector_status(hybrid_retrieval_root)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if value is None:
        status.pop(field, None)
    else:
        status[field] = value
    status_path.write_text(json.dumps(status), encoding="utf-8")

    trace, candidates = run_query(hybrid_retrieval_root, capsys, query="resolveWidgetV2", limit=4)

    assert vector_trace_status(trace) == "failed"
    assert "rebuild" in vector_trace_reason(trace).lower()
    assert candidates[0]["id"] == "note-exact-api"
    assert all(candidate["mechanical_sources"]["vector"] is False for candidate in candidates)


def test_hybrid_retrieval_contract_scores_do_not_classify_or_status_filter(
    hybrid_retrieval_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trace, candidates = run_query(
        hybrid_retrieval_root,
        capsys,
        query="conceptual match vocabulary mismatch",
        target="implementation_plan",
        limit=4,
    )

    paraphrase = candidate_by_id(candidates, "note-paraphrase")
    assert paraphrase["status"] == "proposed"
    assert paraphrase["policy_hint"] == "implementation_plan"
    assert_no_forbidden_script_fields(trace)
    for candidate in candidates:
        assert_no_forbidden_script_fields(candidate)
