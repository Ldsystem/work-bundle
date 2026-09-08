from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import execution_context  # noqa: E402
import review_runtime  # noqa: E402
from test_orchestration_execution_context import workspace  # noqa: E402


def _plan(root: Path) -> Path:
    return root / ".work-bundle/orchestration/plan/active/compiler-plan.md"


def test_static_plan_admission_compiles_every_task_without_runtime_state(tmp_path: Path) -> None:
    root, _spec, first = workspace(tmp_path)
    second = first.with_name("task-005.md")
    second.write_text(
        first.read_text()
        .replace("id: task-004", "id: task-005")
        .replace("phase_id: phase-001\n", "phase_id: phase-001\ndepends_on: [task-004]\n")
        .replace("task_id: task-004", "task_id: task-005"),
        encoding="utf-8",
    )
    first.write_text(
        first.read_text().replace(
            "---\n\n# Task",
            "accepted_result: result-task-004\nevidence_references: [VAL-004-observation]\n---\n\n# Task",
        ),
        encoding="utf-8",
    )

    admitted = execution_context.static_plan_task_admission(root, _plan(root))

    assert [item["task_id"] for item in admitted] == ["task-004", "task-005"]
    assert not (root / ".work-bundle/runtime").exists()


def test_static_plan_admission_rejects_missing_dependency(tmp_path: Path) -> None:
    root, _spec, task = workspace(tmp_path)
    task.write_text(
        task.read_text().replace(
            "phase_id: phase-001\n", "phase_id: phase-001\ndepends_on: [task-missing]\n"
        )
    )

    with pytest.raises(SystemExit, match="static-admission-blocked.*task-missing"):
        execution_context.static_plan_task_admission(root, _plan(root))


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("id: task-004", "id: task-004\nunsupported_contract: true", "unsupported"),
        (
            "write: [scripts/orchestration/execution_context.py]",
            "write: [orchestration/executions/plan-test/result.yaml]",
            "execution artifact",
        ),
    ],
)
def test_static_plan_admission_rejects_known_static_contract_errors(
    tmp_path: Path, needle: str, replacement: str, message: str
) -> None:
    root, _spec, task = workspace(tmp_path)
    task.write_text(task.read_text().replace(needle, replacement), encoding="utf-8")

    with pytest.raises(SystemExit, match=message):
        execution_context.static_plan_task_admission(root, _plan(root))


def test_plan_review_gate_runs_static_admission_before_acceptance(tmp_path: Path, monkeypatch) -> None:
    root, _spec, task = workspace(tmp_path)
    task.write_text(
        task.read_text().replace(
            "phase_id: phase-001\n", "phase_id: phase-001\ndepends_on: [task-missing]\n"
        )
    )
    monkeypatch.setattr(review_runtime, "require_specification_review", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        review_runtime,
        "_require_current_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("review accepted before admission")),
    )

    with pytest.raises(SystemExit, match="static-admission-blocked"):
        review_runtime.require_plan_reviews(root, _plan(root))
