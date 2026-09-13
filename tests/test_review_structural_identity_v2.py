from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import review_runtime  # noqa: E402
from test_orchestration_semantic_plan_identity import _plan_graph  # noqa: E402


def _replace(path: Path, before: str, after: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")


def test_v2_projection_is_explicitly_versioned(tmp_path: Path) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)

    projection = review_runtime.semantic_plan_projection(tmp_path, plan)

    assert projection["schema"] == "plan-structural-projection-v2"
    assert projection == review_runtime.structural_plan_projection_v2(tmp_path, plan)
    assert review_runtime.plan_review_identity(tmp_path, plan) != review_runtime.legacy_plan_review_identity(
        tmp_path, plan
    )


def test_only_documented_lifecycle_locations_are_ignored(tmp_path: Path) -> None:
    plan, phase, task = _plan_graph(tmp_path)
    original = review_runtime.plan_review_identity(tmp_path, plan)

    _replace(plan, "status: Planned", "status: In progress")
    _replace(plan, "last_updated: 2026-09-08", "last_updated: 2026-09-09")
    _replace(phase, "status: Planned", "status: Completed")
    _replace(phase, "last_updated: 2026-09-08", "last_updated: 2026-09-09")
    _replace(phase, "status: Planned}", "status: Completed}")
    _replace(
        task,
        "status: Planned",
        "status: Completed",
    )
    _replace(task, "last_updated: 2026-09-08", "last_updated: 2026-09-09")
    _replace(
        task,
        "acceptance_review: {required: true, verdict: pending, reviewed_head: '', findings: []}",
        "acceptance_review: {required: true, verdict: accepted, reviewed_head: abc, findings: [done]}",
    )
    _replace(task, "---\n\n# Task", "accepted_result: result-task-001\n---\n\n# Task")

    assert review_runtime.plan_review_identity(tmp_path, plan) == original


@pytest.mark.parametrize(
    ("field", "value", "changed"),
    [
        ("status", "draft", "accepted"),
        ("findings", "[one]", "[two]"),
        ("accepted_result", "result-one", "result-two"),
        ("future_contract", "one", "two"),
    ],
)
def test_nested_substantive_and_unknown_fields_affect_v2_identity(
    tmp_path: Path, field: str, value: str, changed: str
) -> None:
    plan, _phase, task = _plan_graph(tmp_path)
    _replace(
        task,
        "---\n\n# Task",
        f"extension:\n  {field}: {value}\n---\n\n# Task",
    )
    original = review_runtime.plan_review_identity(tmp_path, plan)

    _replace(task, f"  {field}: {value}", f"  {field}: {changed}")

    assert review_runtime.plan_review_identity(tmp_path, plan) != original


def test_phase_index_status_is_lifecycle_but_dependencies_are_substantive(tmp_path: Path) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)
    _replace(
        plan,
        "source_spec:",
        "phase_index: [{id: phase-001, status: Planned, depends_on: []}]\nsource_spec:",
    )
    original = review_runtime.plan_review_identity(tmp_path, plan)

    _replace(plan, "status: Planned, depends_on", "status: Completed, depends_on")
    assert review_runtime.plan_review_identity(tmp_path, plan) == original

    _replace(plan, "depends_on: []", "depends_on: [phase-000]")
    assert review_runtime.plan_review_identity(tmp_path, plan) != original


def test_requirement_text_cannot_be_hidden_by_heading_format(tmp_path: Path) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## Knowledge Base Update Carry Forward\n\n- Requirement: preserve evidence\n",
        encoding="utf-8",
    )
    original = review_runtime.plan_review_identity(tmp_path, plan)

    _replace(plan, "Requirement: preserve evidence", "Requirement: discard evidence")

    assert review_runtime.plan_review_identity(tmp_path, plan) != original


def test_legacy_algorithm_remains_directly_callable(tmp_path: Path) -> None:
    plan, _phase, task = _plan_graph(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "---\n\n# Task", "extension: {status: draft}\n---\n\n# Task"
        ),
        encoding="utf-8",
    )
    legacy = review_runtime.legacy_plan_review_identity(tmp_path, plan)
    current = review_runtime.plan_review_identity(tmp_path, plan)

    _replace(task, "extension: {status: draft}", "extension: {status: accepted}")

    assert review_runtime.legacy_plan_review_identity(tmp_path, plan) == legacy
    assert review_runtime.plan_review_identity(tmp_path, plan) != current
