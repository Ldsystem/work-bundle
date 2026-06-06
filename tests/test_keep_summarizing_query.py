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
    ("tender", "confirmed", "background"),
    ("investigation", "proposed", "candidate"),
    ("customer_design", "rejected", "blocked"),
    ("bidding", "current", "background"),
    ("development_design", "confirmed", "authority"),
    ("implementation", "implemented", "authority"),
    ("deployment", "current", "background"),
    ("go_live_delivery", "current", "background"),
    ("operation", "current", "background"),
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
        for lifecycle, status, _ in LIFECYCLE_FIXTURES
    ]
    indexes.build_sqlite_index(root, docs)
    return root


def run_query(knowledge_root: Path, capsys: pytest.CaptureFixture[str], **overrides: object) -> list[dict[str, object]]:
    values: dict[str, object] = {
        "project": "fixture",
        "target": "implementation_plan",
        "query": "shared discovery fixture",
        "limit": 20,
        "include_background": True,
        "knowledge_root": str(knowledge_root),
        "project_root": None,
        "cwd": None,
        "registry_file": None,
    }
    values.update(overrides)
    query.cmd_query(argparse.Namespace(**values))
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_full_candidate_discovery_spans_every_lifecycle_and_role(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = run_query(knowledge_root, capsys)

    roles_by_lifecycle = {result["lifecycle_stage"]: result["retrieval_role"] for result in results}
    assert roles_by_lifecycle == {
        lifecycle: expected_role for lifecycle, _, expected_role in LIFECYCLE_FIXTURES
    }
    assert set(roles_by_lifecycle.values()) == {"authority", "candidate", "background", "blocked"}


def test_target_specific_query_retains_authority_lifecycle_scope(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = run_query(knowledge_root, capsys, include_background=False)

    assert {result["lifecycle_stage"] for result in results} == {
        "development_design",
        "implementation",
    }
    assert {result["retrieval_role"] for result in results} == {"authority"}


def test_full_candidate_discovery_remains_selective(
    knowledge_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    results = run_query(knowledge_root, capsys, limit=3)

    assert len(results) == 3


@pytest.mark.parametrize(
    ("target", "lifecycle", "status", "expected"),
    [
        ("implementation_spec", "development_design", "confirmed", "authority"),
        ("implementation_plan", "operation", "current", "background"),
        ("execution", "implementation", "implemented", "authority"),
        ("customer_spec", "customer_design", "current", "authority"),
        ("bidding", "deployment", "current", "background"),
        ("deployment", "deployment", "confirmed", "authority"),
        ("operation", "operation", "current", "authority"),
        ("operation", "operation", "proposed", "candidate"),
        ("operation", "operation", "deprecated", "blocked"),
    ],
)
def test_retrieval_role_remains_target_specific(
    target: str, lifecycle: str, status: str, expected: str
) -> None:
    assert query.retrieval_role(
        {"lifecycle_stage": lifecycle, "status": status},
        target,
    ) == expected
