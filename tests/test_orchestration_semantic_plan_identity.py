from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import review_runtime  # noqa: E402


def _plan_graph(root: Path) -> tuple[Path, Path, Path]:
    spec = root / ".work-bundle/orchestration/spec/active/spec-test.md"
    plan_root = root / ".work-bundle/orchestration/plan/active"
    plan = plan_root / "plan-test.md"
    phase = plan_root / "plan-test/phase-001.md"
    task = plan_root / "plan-test/phase-001/task-001.md"
    task.parent.mkdir(parents=True)
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "---\nid: spec-test\nversion: 1\nstatus: verified\n---\n\n# Specification\n",
        encoding="utf-8",
    )
    plan.write_text(
        "---\nid: plan-test\nversion: 1\nstatus: Planned\n"
        "source_spec: [.work-bundle/orchestration/spec/active/spec-test.md]\n"
        "---\n\n# Plan\n",
        encoding="utf-8",
    )
    phase.write_text(
        "---\nid: phase-001\nplan_id: plan-test\nstatus: Planned\n"
        "task_index:\n  - {id: task-001, status: Planned}\n---\n\n# Phase\n",
        encoding="utf-8",
    )
    task.write_text(
        "---\nid: task-001\nplan_id: plan-test\nphase_id: phase-001\n"
        "status: Planned\ndepends_on: []\nsource_ids: [REQ-001]\n"
        "target_files: [implementation.py]\nvalidation: [{id: VAL-001, kind: process}]\n"
        "acceptance_review: {required: true}\n---\n\n# Task\n",
        encoding="utf-8",
    )
    return plan, phase, task


def test_progress_and_append_only_evidence_do_not_change_semantic_plan_identity(tmp_path: Path) -> None:
    plan, phase, task = _plan_graph(tmp_path)
    original = review_runtime.plan_review_identity(tmp_path, plan)

    plan.write_text(plan.read_text().replace("status: Planned", "status: In progress"))
    phase.write_text(
        phase.read_text()
        .replace("status: Planned", "status: Completed")
        .replace("---\n\n# Phase", "accepted_result_references: [result-phase-001]\n---\n\n# Phase")
    )
    task.write_text(
        task.read_text()
        .replace("status: Planned", "status: Completed")
        .replace(
            "---\n\n# Task",
            "accepted_result: result-task-001\nevidence_references: [VAL-001-observation]\n---\n\n# Task",
        )
    )

    assert review_runtime.plan_review_identity(tmp_path, plan) == original


@pytest.mark.parametrize(
    ("field", "before", "after"),
    [
        ("dependency", "depends_on: []", "depends_on: [task-000]"),
        ("source authority", "source_ids: [REQ-001]", "source_ids: [REQ-002]"),
        ("scope", "target_files: [implementation.py]", "target_files: [other.py]"),
        ("validation", "id: VAL-001", "id: VAL-002"),
        ("review allocation", "required: true", "required: false"),
    ],
)
def test_executable_task_contract_changes_semantic_plan_identity(
    tmp_path: Path, field: str, before: str, after: str
) -> None:
    plan, _phase, task = _plan_graph(tmp_path)
    original = deepcopy(review_runtime.plan_review_identity(tmp_path, plan))

    task.write_text(task.read_text().replace(before, after), encoding="utf-8")

    assert review_runtime.plan_review_identity(tmp_path, plan) != original, field
