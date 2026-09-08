from __future__ import annotations

import argparse
from copy import deepcopy
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
from test_orchestration_accepted_result import _binding, _handoff, _task, _validated  # noqa: E402


def _dispatcher():
    previous_core = sys.modules.get("core")
    core_spec = importlib.util.spec_from_file_location("core", ORCHESTRATION / "core.py")
    assert core_spec is not None and core_spec.loader is not None
    core_module = importlib.util.module_from_spec(core_spec)
    sys.modules["core"] = core_module
    try:
        core_spec.loader.exec_module(core_module)
        spec = importlib.util.spec_from_file_location(
            "orchestration_accepted_result_dispatcher", ORCHESTRATION / "dispatcher.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_core is None:
            sys.modules.pop("core", None)
        else:
            sys.modules["core"] = previous_core


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
    accepted = [
        (
            {
                "schema": "accepted-task-result-v1",
                "task_id": "task-001",
                "knowledge_disposition": {
                    "action": "none",
                    "reason": "No durable authority changed.",
                    "affected_authority": [],
                },
            },
            {"task_id": "task-001", "review_required": False},
        )
    ]
    calls: list[object] = []
    monkeypatch.setattr(plans, "require_plan_reviews", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        plans,
        "_accepted_plan_task_results",
        lambda *_args: calls.append("accepted") or accepted,
    )
    monkeypatch.setattr(
        plans,
        "_validated_plan_task_handoffs",
        lambda *_args: (_ for _ in ()).throw(AssertionError("handoff replayed")),
    )
    monkeypatch.setattr(
        plans, "_assert_archive_knowledge_gate", lambda *_args: calls.append(_args[-1])
    )
    monkeypatch.setattr(
        plans, "_assert_archive_plan_acceptance", lambda *_args: calls.append(_args[-1])
    )

    plans.cmd_archive_plan(argparse.Namespace(project_root=str(tmp_path), id="plan-001"))

    assert calls == ["accepted", accepted, accepted]
    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan.md").is_file()


def test_archive_knowledge_gate_aggregates_new_results_and_bounds_legacy_bridge(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "plan.md"
    args = argparse.Namespace()
    update = {
        "schema": "accepted-task-result-v1",
        "task_id": "task-001",
        "knowledge_disposition": {
            "action": "update",
            "reason": "Stable authority changed.",
            "affected_authority": ["REQ-001"],
        },
    }
    brief = {"task_id": "task-001", "review_required": True}
    plan.write_text(
        "---\nid: plan-001\n---\n\n## 2.1 Knowledge Base Update Carry Forward\n\n"
        "- **Disposition**: not-needed\n- **Closure return**: missing\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="task-001:update"):
        plans._assert_archive_knowledge_gate(args, "plan-001", plan, [(update, brief)])

    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "Closure return**: missing", "Closure return**: completed"
        ),
        encoding="utf-8",
    )
    plans._assert_archive_knowledge_gate(args, "plan-001", plan, [(update, brief)])

    legacy = deepcopy(update)
    legacy.pop("knowledge_disposition")
    with pytest.raises(SystemExit, match="legacy accepted results require plan-level required/completed"):
        plans._assert_archive_knowledge_gate(args, "plan-001", plan, [(legacy, brief)])
    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "Disposition**: not-needed", "Disposition**: required"
        ),
        encoding="utf-8",
    )
    plans._assert_archive_knowledge_gate(args, "plan-001", plan, [(legacy, brief)])


def test_declared_integration_commands_follow_table_headers() -> None:
    five_columns = (
        "## 7. Tests\n\n"
        "| ID | Test Type | Target | Command | Expected Result |\n"
        "|---|---|---|---|---|\n"
        "| TEST-001 | integration | archive | `env true` | passed |\n"
    )
    reordered = (
        "## Tests\n\n"
        "| Command | Expected Result | Target | Test Type | ID | Can Run With |\n"
        "|---|---|---|---|---|---|\n"
        "| `python -m pytest -q` | passed | archive | integration | TEST-002 | - |\n"
    )

    assert plans._declared_integration_commands(five_columns) == ["env true"]
    assert plans._declared_integration_commands(reordered) == ["python -m pytest -q"]


def test_missing_terminal_plan_proof_executes_once_state_neutrally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("stable\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    plan = tmp_path / "plan.md"
    plan.write_text(
        "---\nid: plan-001\n---\n\n## 7. Tests\n\n"
        "| ID | Test Type | Target | Command | Expected Result |\n"
        "|---|---|---|---|---|\n"
        "| TEST-001 | integration | archive | `env true` | passed |\n",
        encoding="utf-8",
    )
    observed: list[str] = []
    monkeypatch.setattr(plans, "_material_repository_root", lambda *_args: tmp_path)
    monkeypatch.setattr(
        plans,
        "_observe_archive_command",
        lambda command, _workspace: observed.append(command) or "passed",
    )

    plans._assert_archive_plan_acceptance(
        argparse.Namespace(project_root=str(tmp_path)), "plan-001", plan, []
    )

    assert observed == ["env true"]


def test_recovery_commands_are_not_public_dispatcher_actions() -> None:
    dispatcher = _dispatcher()

    assert "create-accepted-base-absence-receipt" not in dispatcher.RECOGNIZED_COMMANDS
    assert "adopt-existing-recovered-result" not in dispatcher.RECOGNIZED_COMMANDS
    with pytest.raises(SystemExit):
        dispatcher.build_parser().parse_args(["create-accepted-base-absence-receipt"])
