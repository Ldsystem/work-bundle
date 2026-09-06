from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import execution_context  # noqa: E402
import plans  # noqa: E402
from test_wor109_accepted_result import _binding, _handoff, _task, _validated  # noqa: E402


def _dispatcher():
    spec = importlib.util.spec_from_file_location(
        "wor109_dispatcher", ORCHESTRATION / "dispatcher.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_accepted_result_does_not_read_handoff_or_replay_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(tmp_path)
    binding = _binding(tmp_path)
    monkeypatch.setattr(
        execution_context,
        "capture_repository_evidence",
        lambda _root: {"head": "a" * 40, "tree": "b" * 40, "entries": {}, "status": "clean"},
    )
    accepted = execution_context.build_accepted_task_result(
        task, binding, _handoff(), _validated(), accepted_at="2026-09-07T00:00:00Z"
    )
    binding["accepted_result"] = accepted
    monkeypatch.setattr(execution_context, "load_task_execution_binding", lambda *_args: binding)

    current_binding, current = execution_context.load_current_accepted_task_result(
        tmp_path, task
    )

    assert current_binding is binding
    assert current == accepted


def test_task_completion_reuses_current_accepted_result_without_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_path = tmp_path / "task.md"
    task_path.write_text("---\nid: task-001\nplan_id: plan-001\n---\n", encoding="utf-8")
    accepted = {"schema": "accepted-task-result-v1"}
    calls: list[str] = []
    monkeypatch.setattr(plans, "_load_current_task_acceptance", lambda *_args: ({}, accepted))
    monkeypatch.setattr(
        plans,
        "cmd_validate_executor_result",
        lambda _args: calls.append("replayed"),
    )

    assert plans._assert_completed_task_authority(argparse.Namespace(), task_path) == accepted
    assert calls == []


def test_task_completion_does_not_replay_when_persisted_authority_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_path = tmp_path / "task.md"
    task_path.write_text("---\nid: task-001\nplan_id: plan-001\n---\n", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(
        plans,
        "_load_current_task_acceptance",
        lambda *_args: (_ for _ in ()).throw(
            SystemExit("accepted task result is stale: scope authority changed")
        ),
    )
    monkeypatch.setattr(
        plans, "cmd_validate_executor_result", lambda _args: calls.append("replayed")
    )

    with pytest.raises(SystemExit, match="stale: scope"):
        plans._assert_completed_task_authority(
            argparse.Namespace(handoff="historical.yaml"), task_path
        )
    assert calls == []


def test_dependency_and_phase_gates_consume_only_current_accepted_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_path = tmp_path / "task.md"
    task_path.write_text(
        "---\nid: task-002\nplan_id: plan-001\nphase_id: phase-001\n"
        "depends_on: [task-001]\n---\n",
        encoding="utf-8",
    )
    rows = [
        {
            "type": "task",
            "id": "task-001",
            "plan_id": "plan-001",
            "phase_id": "phase-001",
            "status": "Completed",
            "path": "dependency.md",
        },
        {
            "type": "task",
            "id": "task-002",
            "plan_id": "plan-001",
            "phase_id": "phase-001",
            "status": "Completed",
            "path": "task.md",
        },
    ]
    loaded: list[str] = []
    monkeypatch.setattr(plans, "index_plans", lambda _args: rows)
    monkeypatch.setattr(
        plans,
        "_task_brief_at",
        lambda _args, path: {
            "plan_id": "plan-001",
            "task_id": "task-002" if path.name == "task.md" else "task-001",
            "depends_on": ["task-001"] if path.name == "task.md" else [],
        },
    )
    monkeypatch.setattr(
        plans,
        "artifact_path_from_row",
        lambda row, _args: tmp_path / str(row["path"]),
    )
    monkeypatch.setattr(
        plans,
        "_load_current_task_acceptance",
        lambda _args, path: (loaded.append(path.name), ({}, {"schema": "accepted-task-result-v1"}))[1],
    )

    plans._assert_task_dependencies_current(argparse.Namespace(), task_path)
    plans._assert_phase_tasks_accepted(
        argparse.Namespace(), "phase-001", "plan-001"
    )

    assert loaded == ["dependency.md", "dependency.md", "task.md"]


def test_archive_switches_irreversibly_to_accepted_results_without_handoff_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_root = tmp_path / ".work-bundle/orchestration/plan/active"
    task_root = plan_root / "plan" / "phase-001"
    task_root.mkdir(parents=True)
    (plan_root / "plan.md").write_text(
        "---\nid: plan-001\nstatus: Completed\n---\n", encoding="utf-8"
    )
    (task_root / "task.md").write_text(
        "---\nid: task-001\nplan_id: plan-001\nphase_id: phase-001\n"
        "status: Completed\n---\n",
        encoding="utf-8",
    )
    binding_path = (
        tmp_path
        / ".work-bundle/runtime/execution/plan-001/task-001/execution-binding.json"
    )
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text(
        json.dumps({"accepted_result": {"schema": "accepted-task-result-v1"}}),
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr(plans, "require_plan_reviews", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        plans,
        "_accepted_plan_task_results",
        lambda *_args: calls.append("accepted") or [],
    )
    monkeypatch.setattr(
        plans,
        "_validated_plan_task_handoffs",
        lambda *_args: (_ for _ in ()).throw(AssertionError("handoff replayed")),
    )
    monkeypatch.setattr(plans, "_assert_archive_knowledge_gate", lambda *_args: None)
    monkeypatch.setattr(plans, "_assert_archive_plan_acceptance", lambda *_args: None)

    plans.cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-001"))

    assert calls == ["accepted"]
    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan.md").is_file()


def test_recovery_commands_are_not_public_dispatcher_actions() -> None:
    dispatcher = _dispatcher()

    assert "create-accepted-base-absence-receipt" not in dispatcher.RECOGNIZED_COMMANDS
    assert "adopt-existing-recovered-result" not in dispatcher.RECOGNIZED_COMMANDS
    with pytest.raises(SystemExit):
        dispatcher.build_parser().parse_args(["create-accepted-base-absence-receipt"])


def test_wor105_historical_identity_and_release_anchor_are_separate() -> None:
    import yaml

    record = yaml.safe_load(
        (REPO_ROOT / "evals/wor105/components/native-transition-record.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert record["accepted_commit"] == "9dce5df221485174d6179f713e8b179bbc20567a"
    assert record["accepted_tree"] == "5a1f38355eae8068bab528923e807ce54e6f6fe5"
    assert record["release_anchor"] == {
        "commit": "cfa089f0d2ed211b98d049eb37bfcdccb8091516",
        "tree": "12e4a696c3caf991654f0b9ac9ef40594699c8d4",
    }
