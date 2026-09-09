from __future__ import annotations

import hashlib
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import review_runtime  # noqa: E402
from artifact_inputs import _read_structured, _resolve_spec_paths  # noqa: E402


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
        "---\nid: plan-test\nversion: 1\ndate_created: 2026-09-08\n"
        "last_updated: 2026-09-08\nstatus: Planned\n"
        "source_spec: [.work-bundle/orchestration/spec/active/spec-test.md]\n"
        "---\n\n# Plan\n",
        encoding="utf-8",
    )
    phase.write_text(
        "---\nid: phase-001\nplan_id: plan-test\ndate_created: 2026-09-08\n"
        "last_updated: 2026-09-08\nstatus: Planned\n"
        "task_index:\n  - {id: task-001, status: Planned}\n---\n\n# Phase\n",
        encoding="utf-8",
    )
    task.write_text(
        "---\nid: task-001\nplan_id: plan-test\nphase_id: phase-001\n"
        "date_created: 2026-09-08\nlast_updated: 2026-09-08\n"
        "status: Planned\ndepends_on: []\nsource_ids: [REQ-001]\n"
        "target_files: [implementation.py]\nvalidation: [{id: VAL-001, kind: process}]\n"
        "acceptance_review: {required: true, verdict: pending, reviewed_head: '', findings: []}\n"
        "---\n\n# Task\n",
        encoding="utf-8",
    )
    return plan, phase, task


def _legacy_plan_identity(root: Path, plan: Path) -> dict[str, object]:
    plan_root = root / ".work-bundle/orchestration/plan"
    identity = review_runtime.artifact_review_identity(plan)
    members = {str(plan.relative_to(plan_root)): identity["sha256"]}
    for path in sorted(plan_root.rglob("*.md")):
        if path == plan:
            continue
        data, _ = _read_structured(path)
        if str(data.get("plan_id", "")) == identity["artifact_id"]:
            members[str(path.relative_to(plan_root))] = review_runtime.artifact_review_identity(path)[
                "sha256"
            ]
    plan_data = _read_structured(plan)[0]
    specifications = [
        review_runtime.artifact_review_identity(path)
        for path in _resolve_spec_paths(root, {}, plan_data)
    ]
    identity["sha256"] = hashlib.sha256(
        json.dumps({"members": members, "specifications": specifications}, sort_keys=True).encode()
    ).hexdigest()
    return identity


def test_semantic_projector_preserves_accepted_legacy_baseline_identity(tmp_path: Path) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)

    assert review_runtime.plan_review_identity(tmp_path, plan) == _legacy_plan_identity(tmp_path, plan)


def test_missing_knowledge_closure_preserves_accepted_legacy_identity(tmp_path: Path) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)
    plan.write_text(
        plan.read_text()
        + "\n## Knowledge Base Update Carry Forward\n\n"
        "- Disposition: required\n- Closure return: missing\n"
        "- Source: accepted specification\n- Review Gate: resolve before archive\n",
        encoding="utf-8",
    )

    assert review_runtime.plan_review_identity(tmp_path, plan) == _legacy_plan_identity(tmp_path, plan)


def test_active_to_archived_rotation_preserves_semantic_plan_identity(tmp_path: Path) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)
    original = review_runtime.plan_review_identity(tmp_path, plan)
    archived = plan.parents[1] / "archived"
    archived.mkdir()
    archived_plan = archived / plan.name
    archived_graph = archived / plan.stem

    shutil.move(str(plan), archived_plan)
    shutil.move(str(plan.with_suffix("")), archived_graph)

    assert review_runtime.plan_review_identity(tmp_path, archived_plan) == original


def test_progress_and_append_only_evidence_do_not_change_semantic_plan_identity(tmp_path: Path) -> None:
    plan, phase, task = _plan_graph(tmp_path)
    original = review_runtime.plan_review_identity(tmp_path, plan)

    plan.write_text(
        plan.read_text()
        .replace("status: Planned", "status: In progress")
        .replace("last_updated: 2026-09-08", "last_updated: 2026-09-09")
    )
    phase.write_text(
        phase.read_text()
        .replace("status: Planned", "status: Completed")
        .replace("last_updated: 2026-09-08", "last_updated: 2026-09-09")
        .replace("---\n\n# Phase", "accepted_result_references: [result-phase-001]\n---\n\n# Phase")
    )
    task.write_text(
        task.read_text()
        .replace("status: Planned", "status: Completed")
        .replace("last_updated: 2026-09-08", "last_updated: 2026-09-09")
        .replace(
            "acceptance_review: {required: true, verdict: pending, reviewed_head: '', findings: []}",
            "acceptance_review: {required: true, verdict: accept, reviewed_head: abc, findings: []}",
        )
        .replace(
            "---\n\n# Task",
            "accepted_result: result-task-001\nevidence_references: [VAL-001-observation]\n---\n\n# Task",
        )
    )

    assert review_runtime.plan_review_identity(tmp_path, plan) == original


@pytest.mark.parametrize(
    ("heading", "label"),
    [
        ("## 2.1 Knowledge Base Update Carry Forward", "**Closure return**"),
        ("## Knowledge Base Update Carry Forward", "Closure return"),
    ],
)
def test_knowledge_closure_only_change_preserves_plan_review_identity(
    tmp_path: Path, heading: str, label: str
) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)
    plan.write_text(
        plan.read_text()
        + f"\n{heading}\n\n- **Disposition**: required\n- {label}: missing\n",
        encoding="utf-8",
    )
    original = review_runtime.plan_review_identity(tmp_path, plan)

    plan.write_text(plan.read_text().replace(f"{label}: missing", f"{label}: completed"))

    assert review_runtime.plan_review_identity(tmp_path, plan) == original


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Disposition: not-needed", "Disposition: required"),
        ("Source: no durable update", "Source: accepted task findings"),
        ("Review Gate: no follow-up", "Review Gate: persist accepted findings"),
    ],
)
def test_substantive_knowledge_change_invalidates_plan_review_identity(
    tmp_path: Path, before: str, after: str
) -> None:
    plan, _phase, _task = _plan_graph(tmp_path)
    plan.write_text(
        plan.read_text()
        + "\n## Knowledge Base Update Carry Forward\n\n"
        "- Disposition: not-needed\n- Closure return: missing\n"
        "- Source: no durable update\n- Review Gate: no follow-up\n",
        encoding="utf-8",
    )
    original = review_runtime.plan_review_identity(tmp_path, plan)

    plan.write_text(
        plan.read_text().replace(before, after),
        encoding="utf-8",
    )

    assert review_runtime.plan_review_identity(tmp_path, plan) != original


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
