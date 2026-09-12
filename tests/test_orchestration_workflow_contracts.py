from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCH_ROOT))

from doctor import check_active_handoff_contract
from execution_context import (
    build_review_package,
    evaluate_knowledge_closure_state,
    validate_executor_result_for_task,
)
import execution_context
from handoffs import cmd_set_handoff_status, cmd_write_handoff, index_handoffs
import handoffs
from plans import _material_repository_root, _verified_handoff_tree


@pytest.fixture(autouse=True)
def accepted_stage_boundary_for_legacy_archive_unit_tests(monkeypatch):
    """These tests isolate task evidence/knowledge/archive semantics.

    Real stage admission (including missing/stale review and source transitions)
    is tested without this stub in test_orchestration_reviews.py.
    """
    monkeypatch.setattr("plans.require_plan_reviews", lambda *args, **kwargs: None)


@pytest.fixture
def lower_level_handoff_writer(monkeypatch):
    """Isolate lifecycle mechanics from managed creation admission."""
    monkeypatch.setattr("handoffs._managed_creation_admission", lambda *_args: None)


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def load_orchestration_dispatcher():
    previous_core = sys.modules.get("core")
    core_spec = importlib.util.spec_from_file_location("core", ORCH_ROOT / "core.py")
    assert core_spec is not None and core_spec.loader is not None
    core_module = importlib.util.module_from_spec(core_spec)
    sys.modules["core"] = core_module
    try:
        core_spec.loader.exec_module(core_module)
        dispatcher_spec = importlib.util.spec_from_file_location(
            "orchestration_workflow_contracts_dispatcher", ORCH_ROOT / "dispatcher.py"
        )
        assert dispatcher_spec is not None and dispatcher_spec.loader is not None
        dispatcher = importlib.util.module_from_spec(dispatcher_spec)
        dispatcher_spec.loader.exec_module(dispatcher)
        return dispatcher
    finally:
        if previous_core is None:
            sys.modules.pop("core", None)
        else:
            sys.modules["core"] = previous_core


def evals() -> list[dict[str, object]]:
    return json.loads(read("references/evals/orchestration/evals.json"))["evals"]


def handoff_args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "project_root": str(tmp_path),
        "content_file": str(tmp_path / "handoff-content.txt"),
        "type": "executor-result",
        "status": "active",
        "id": "handoff-exec-20990101-001",
        "title": "Task Result",
        "format": None,
        "related_spec": "spec-001",
        "related_plan": "plan-001",
        "related_phase": "phase-001",
        "related_task": "task-001",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def archive_args(project_root: Path, plan_id: str, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "project_root": str(project_root),
        "id": plan_id,
        "mutation_events": [],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _task_brief(*, plan_id: str = "plan-001", task_id: str = "task-001") -> dict[str, object]:
    return {
        "task_id": task_id,
        "plan_id": plan_id,
        "source_ids": [],
        "files": {"read": [], "write": []},
        "truth_basis": {},
        "validation": [],
        "evidence_capability": {
            "result": "no_validation_bearing_obligation",
            "reason": "This structural fixture makes no validation-bearing closure claim.",
            "invariants": [],
        },
        "review_required": False,
    }


def _completed_executor_result(
    *,
    plan: str | None = "plan-001",
    task: str = "task-001",
    acceptance_review: dict[str, object] | None = None,
) -> dict[str, object]:
    related: dict[str, object] = {"task": task}
    if plan is not None:
        related["plan"] = plan
    handoff: dict[str, object] = {
        "type": "executor-result",
        "related": related,
        "result": {"state": "completed"},
        "task_fit_check": {"task": task, "result": "clean"},
        "delegation_evidence": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "workflow-contract-fixture-agent",
            "run_id": "workflow-contract-fixture-run",
            "mechanism": "host-native",
        },
        "knowledge_disposition": {
            "action": "none",
            "reason": "No stable authority changed.",
            "affected_authority": [],
        },
    }
    if acceptance_review is not None:
        handoff["acceptance_review"] = acceptance_review
    return handoff


def test_handoff_helper_rejects_unsupported_unmanaged_executor_creation(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("result:\n  state: completed\n  summary: ok\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="managed WorkBundle workspace"):
        cmd_write_handoff(handoff_args(tmp_path, content_file=str(content)))
    assert not list((tmp_path / ".work-bundle/orchestration/handoff/executor").glob("*/*.yaml"))


def test_managed_handoff_creation_runs_complete_creation_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = tmp_path / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("metadata_version: 4\n", encoding="utf-8")
    task = tmp_path / ".work-bundle/orchestration/plan/active/plan-001/phase-001/task-001.md"
    task.parent.mkdir(parents=True)
    task.write_text("---\nid: task-001\nplan_id: plan-001\n---\n", encoding="utf-8")
    observed: list[tuple[dict[str, object], dict[str, object]]] = []
    monkeypatch.setattr(
        execution_context,
        "_compile_task_brief",
        lambda _args: (task, {"task_brief": {"task_id": "task-001", "plan_id": "plan-001"}}),
    )
    monkeypatch.setattr(
        execution_context,
        "validate_executor_result_creation_for_task",
        lambda result, brief: observed.append((result, brief)),
    )

    handoffs._managed_creation_admission(
        handoff_args(tmp_path),
        "type: executor-result\nrelated: {plan: plan-001, task: task-001}\nresult: {state: completed}\n",
    )

    assert observed[0][0]["result"]["state"] == "completed"
    assert observed[0][1] == {"task_id": "task-001", "plan_id": "plan-001"}


def test_handoff_creation_rejects_conflicting_writer_identity_before_mutation(
    tmp_path: Path,
) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "id: conflicting-id\nresult:\n  state: completed\n  summary: no\n",
        encoding="utf-8",
    )
    args = handoff_args(tmp_path, content_file=str(content))

    with pytest.raises(SystemExit, match="metadata mismatch for id"):
        cmd_write_handoff(args)

    handoff_root = tmp_path / ".work-bundle/orchestration/handoff"
    assert not list((handoff_root / "executor").glob("*/*.yaml"))
    assert not (handoff_root / "index.jsonl").read_text(encoding="utf-8")


def test_handoff_lifecycle_preserves_marked_bytes_and_rebuilds_status(
    tmp_path: Path, lower_level_handoff_writer,
) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("result:\n  state: completed\n  summary: ok\n", encoding="utf-8")
    args = handoff_args(tmp_path, content_file=str(content))
    cmd_write_handoff(args)
    initial = next(item for item in index_handoffs(args) if item["id"] == args.id)
    initial_path = tmp_path / str(initial["path"])
    initial_bytes = initial_path.read_bytes()
    assert b"lifecycle_authority: location-v1" in initial_bytes

    cmd_set_handoff_status(handoff_args(tmp_path, id=args.id, status="reviewed"))
    reviewed = next(item for item in index_handoffs(args) if item["id"] == args.id)
    reviewed_path = tmp_path / str(reviewed["path"])
    assert reviewed["status"] == "reviewed"
    assert "/reviewed/" in reviewed_path.as_posix()
    assert reviewed_path.read_bytes() == initial_bytes

    index_before = (tmp_path / ".work-bundle/orchestration/handoff/index.jsonl").read_bytes()
    cmd_set_handoff_status(handoff_args(tmp_path, id=args.id, status="reviewed"))
    assert reviewed_path.read_bytes() == initial_bytes
    assert (tmp_path / ".work-bundle/orchestration/handoff/index.jsonl").read_bytes() == index_before


def test_legacy_explicit_return_to_active_uses_digest_bound_override(tmp_path: Path) -> None:
    path = (
        tmp_path
        / ".work-bundle/orchestration/handoff/executor/active/legacy-result.yaml"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        "id: legacy-result\ntype: executor-result\nstatus: reviewed\n"
        "related:\n  plan: plan-001\n  task: task-001\n",
        encoding="utf-8",
    )
    original = path.read_bytes()
    args = handoff_args(tmp_path, id="legacy-result")
    assert next(item for item in index_handoffs(args) if item["id"] == "legacy-result")["status"] == "reviewed"

    cmd_set_handoff_status(handoff_args(tmp_path, id="legacy-result", status="active"))
    override = (
        tmp_path
        / ".work-bundle/orchestration/handoff/legacy-status-overrides/legacy-result.json"
    )
    record = json.loads(override.read_text(encoding="utf-8"))
    assert record == {
        "handoff_id": "legacy-result",
        "related_plan": "plan-001",
        "related_task": "task-001",
        "sha256": __import__("hashlib").sha256(original).hexdigest(),
        "status": "active",
        "type": "executor-result",
    }
    assert path.read_bytes() == original
    assert next(item for item in index_handoffs(args) if item["id"] == "legacy-result")["status"] == "active"


def test_handoff_index_fails_closed_on_duplicate_identity(tmp_path: Path) -> None:
    active = tmp_path / ".work-bundle/orchestration/handoff/executor/active/result.yaml"
    reviewed = tmp_path / ".work-bundle/orchestration/handoff/executor/reviewed/result.yaml"
    active.parent.mkdir(parents=True)
    reviewed.parent.mkdir(parents=True)
    content = "id: duplicate\ntype: executor-result\nstatus: active\nlifecycle_authority: location-v1\n"
    active.write_text(content, encoding="utf-8")
    reviewed.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit, match="Duplicate handoff identity"):
        index_handoffs(handoff_args(tmp_path))


def _write_unmarked_legacy_handoff(
    tmp_path: Path,
    *,
    name: str,
    project: str,
    status_location: str = "active",
    phase: str = "phase-legacy",
    task: str = "task-legacy",
) -> Path:
    path = (
        tmp_path
        / f".work-bundle/orchestration/handoff/executor/{status_location}/{name}.yaml"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "id: legacy-duplicate\n"
        "type: executor-result\n"
        "status: active\n"
        f"project: {project}\n"
        "related:\n"
        "  plan: plan-legacy\n"
        f"  phase: {phase}\n"
        f"  task: {task}\n",
        encoding="utf-8",
    )
    return path


def test_handoff_index_preserves_unrelated_colocated_unmarked_legacy_duplicates(
    tmp_path: Path,
) -> None:
    first = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-first", project="project-first"
    )
    second = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-second", project="project-second"
    )

    rows = [
        row
        for row in index_handoffs(handoff_args(tmp_path))
        if row["id"] == "legacy-duplicate"
    ]

    assert {row["project"] for row in rows} == {"project-first", "project-second"}
    assert {tmp_path / str(row["path"]) for row in rows} == {first, second}


def test_handoff_index_preserves_same_project_colocated_unmarked_legacy_duplicate(
    tmp_path: Path,
) -> None:
    first = _write_unmarked_legacy_handoff(
        tmp_path,
        name="legacy-first",
        project="same-project",
        status_location="archived",
        phase="phase-first",
        task="task-first",
    )
    second = _write_unmarked_legacy_handoff(
        tmp_path,
        name="legacy-second",
        project="same-project",
        status_location="archived",
        phase="phase-second",
        task="task-second",
    )

    rows = [
        row
        for row in index_handoffs(handoff_args(tmp_path))
        if row["id"] == "legacy-duplicate"
    ]

    assert {row["project"] for row in rows} == {"same-project"}
    assert {row["related_phase"] for row in rows} == {"phase-first", "phase-second"}
    assert {row["related_task"] for row in rows} == {"task-first", "task-second"}
    assert {tmp_path / str(row["path"]) for row in rows} == {first, second}


def test_handoff_index_rejects_cross_location_unmarked_legacy_duplicate(
    tmp_path: Path,
) -> None:
    _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-first", project="project-first"
    )
    _write_unmarked_legacy_handoff(
        tmp_path,
        name="legacy-second",
        project="project-second",
        status_location="reviewed",
    )

    with pytest.raises(SystemExit, match="Duplicate handoff identity"):
        index_handoffs(handoff_args(tmp_path))


def test_handoff_index_rejects_override_for_unmarked_legacy_duplicates(
    tmp_path: Path,
) -> None:
    first = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-first", project="project-first"
    )
    _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-second", project="project-second"
    )
    override = (
        tmp_path
        / ".work-bundle/orchestration/handoff/legacy-status-overrides/legacy-duplicate.json"
    )
    override.parent.mkdir(parents=True)
    override.write_text(
        json.dumps(
            {
                "handoff_id": "legacy-duplicate",
                "sha256": __import__("hashlib").sha256(first.read_bytes()).hexdigest(),
                "type": "executor-result",
                "related_plan": "plan-legacy",
                "related_task": "task-legacy",
                "status": "active",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Duplicate handoff identity"):
        index_handoffs(handoff_args(tmp_path))


def test_handoff_status_change_rejects_ambiguous_legacy_duplicate(
    tmp_path: Path,
) -> None:
    first = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-first", project="project-first"
    )
    second = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-second", project="project-second"
    )
    originals = {first: first.read_bytes(), second: second.read_bytes()}

    with pytest.raises(SystemExit, match="ambiguous"):
        cmd_set_handoff_status(
            handoff_args(tmp_path, id="legacy-duplicate", status="reviewed")
        )

    assert {path: path.read_bytes() for path in originals} == originals
    assert not (
        tmp_path
        / ".work-bundle/orchestration/handoff/legacy-status-overrides/legacy-duplicate.json"
    ).exists()


def test_handoff_creation_rejects_identity_owned_by_legacy_duplicates(
    tmp_path: Path, lower_level_handoff_writer,
) -> None:
    first = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-first", project="project-first"
    )
    second = _write_unmarked_legacy_handoff(
        tmp_path, name="legacy-second", project="project-second"
    )
    content = tmp_path / "handoff-content.txt"
    content.write_text("result:\n  state: completed\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Duplicate handoff identity"):
        cmd_write_handoff(
            handoff_args(
                tmp_path,
                id="legacy-duplicate",
                content_file=str(content),
            )
        )

    assert first.is_file()
    assert second.is_file()
    assert not list(
        (tmp_path / ".work-bundle/orchestration/handoff/executor/active").glob(
            "legacy-duplicate-task-result.*"
        )
    )


@pytest.mark.parametrize("target_status", ["active", "reviewed", "superseded", "archived"])
def test_marked_handoff_supports_every_target_status(
    tmp_path: Path, target_status: str, lower_level_handoff_writer,
) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("result:\n  state: blocked\n", encoding="utf-8")
    args = handoff_args(tmp_path, content_file=str(content))
    cmd_write_handoff(args)
    original_row = next(item for item in index_handoffs(args) if item["id"] == args.id)
    original = (tmp_path / str(original_row["path"])).read_bytes()

    cmd_set_handoff_status(handoff_args(tmp_path, id=args.id, status=target_status))
    row = next(item for item in index_handoffs(args) if item["id"] == args.id)
    assert row["status"] == target_status
    assert f"/{target_status}/" in f"/{row['path']}"
    assert (tmp_path / str(row["path"])).read_bytes() == original


def test_legacy_nonactive_to_active_survives_reindex_and_restart(tmp_path: Path) -> None:
    path = tmp_path / ".work-bundle/orchestration/handoff/executor/superseded/legacy.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "id: legacy-moved\ntype: executor-result\nstatus: reviewed\n"
        "related:\n  plan: plan-001\n  task: task-001\n",
        encoding="utf-8",
    )
    original = path.read_bytes()
    args = handoff_args(tmp_path, id="legacy-moved")
    assert next(item for item in index_handoffs(args) if item["id"] == "legacy-moved")["status"] == "superseded"

    cmd_set_handoff_status(handoff_args(tmp_path, id="legacy-moved", status="active"))
    active = tmp_path / ".work-bundle/orchestration/handoff/executor/active/legacy.yaml"
    assert active.read_bytes() == original
    assert next(item for item in index_handoffs(args) if item["id"] == "legacy-moved")["status"] == "active"


def test_legacy_override_digest_or_location_contradiction_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / ".work-bundle/orchestration/handoff/executor/active/legacy.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "id: legacy-invalid\ntype: executor-result\nstatus: reviewed\n"
        "related:\n  plan: plan-001\n  task: task-001\n",
        encoding="utf-8",
    )
    override = tmp_path / ".work-bundle/orchestration/handoff/legacy-status-overrides/legacy-invalid.json"
    override.parent.mkdir(parents=True)
    override.write_text(json.dumps({
        "handoff_id": "legacy-invalid", "sha256": "0" * 64,
        "type": "executor-result", "related_plan": "plan-001",
        "related_task": "task-001", "status": "reviewed",
    }), encoding="utf-8")

    with pytest.raises(SystemExit, match="contradicts digest, binding, or location"):
        index_handoffs(handoff_args(tmp_path))


def test_handoff_tree_resolves_recorded_repository_instead_of_control_root(tmp_path: Path) -> None:
    from test_orchestration_execution_context import git

    control_root = tmp_path / "control"
    execution_root = tmp_path / "execution-flow"
    control_root.mkdir()
    execution_root.mkdir()
    git(execution_root, "init", "-q")
    git(execution_root, "config", "user.email", "test@example.com")
    git(execution_root, "config", "user.name", "Test")
    (execution_root / "feature.ts").write_text("export const ready = true;\n", encoding="utf-8")
    git(execution_root, "add", ".")
    git(execution_root, "commit", "-qm", "feature")
    head = git(execution_root, "rev-parse", "HEAD").strip()
    tree = git(execution_root, "rev-parse", "HEAD^{tree}").strip()
    handoff = {
        "repository": [{"root": str(execution_root), "metadata": {"actual_commit": head}}],
    }

    assert _verified_handoff_tree(control_root, handoff) == tree


def test_material_repository_prefers_fresh_terminal_plan_acceptance_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_orchestration_execution_context import git

    control_root = tmp_path / "control"
    earlier_root = tmp_path / "earlier"
    accepted_root = tmp_path / "accepted"
    control_root.mkdir()
    for root, content in ((earlier_root, "old\n"), (accepted_root, "accepted\n")):
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.email", "test@example.com")
        git(root, "config", "user.name", "Test")
        (root / "feature.ts").write_text(content, encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "feature")

    command = "pnpm run ci"
    earlier_head = git(earlier_root, "rev-parse", "HEAD").strip()
    accepted_head = git(accepted_root, "rev-parse", "HEAD").strip()
    validated = [
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(earlier_root), "metadata": {"actual_commit": earlier_head}}],
                "validation": {"commands": []},
            },
            {"task_id": "task-001", "files": {"write": ["feature.ts"]}},
        ),
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(accepted_root), "metadata": {"actual_commit": accepted_head}}],
                "validation": {"commands": [{"command": command, "result": "passed"}]},
            },
            {"task_id": "task-002", "files": {"write": ["feature.ts"]}},
        ),
    ]
    monkeypatch.setattr("plans._plan_task_order", lambda _args, _plan_id: {"task-001": 1, "task-002": 2})

    assert _material_repository_root(
        argparse.Namespace(project_root=str(control_root)), "plan-001", validated, [command]
    ) == accepted_root.resolve()


def test_material_repository_rejects_fresh_acceptance_before_later_material_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_orchestration_execution_context import git

    earlier_root = tmp_path / "earlier"
    later_root = tmp_path / "later"
    for root in (earlier_root, later_root):
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.email", "test@example.com")
        git(root, "config", "user.name", "Test")
        (root / "feature.ts").write_text(f"{root.name}\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "feature")

    command = "pnpm run ci"
    earlier_head = git(earlier_root, "rev-parse", "HEAD").strip()
    later_head = git(later_root, "rev-parse", "HEAD").strip()
    validated = [
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(earlier_root), "metadata": {"actual_commit": earlier_head}}],
                "validation": {"commands": [{"command": command, "result": "passed"}]},
            },
            {"task_id": "task-010", "files": {"write": ["feature.ts"]}},
        ),
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "repository": [{"root": str(later_root), "metadata": {"actual_commit": later_head}}],
                "validation": {"commands": []},
            },
            {"task_id": "task-002", "files": {"write": ["feature.ts"]}},
        ),
    ]
    monkeypatch.setattr("plans._plan_task_order", lambda _args, _plan_id: {"task-010": 1, "task-002": 2})

    with pytest.raises(SystemExit, match="acceptance-blocked: final plan repository is ambiguous"):
        _material_repository_root(
            argparse.Namespace(project_root=str(tmp_path)), "plan-001", validated, [command]
        )


def test_material_repository_rejects_material_handoff_without_repository_provenance(tmp_path: Path) -> None:
    command = "pnpm run ci"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    metadata = tmp_path / ".work-bundle/project.yaml"
    metadata.parent.mkdir()
    metadata.write_text(
        "metadata_version: 3\n"
        "workspace_root: " + str(tmp_path) + "\n"
        "workspace_mode: multi-repository\n"
        "source_repositories:\n"
        "  first:\n"
        "    project_root: " + str(first) + "\n"
        "  second:\n"
        "    project_root: " + str(second) + "\n",
        encoding="utf-8",
    )
    validated = [
        (
            {
                "changes": {"files": [{"path": "feature.ts", "action": "modified"}]},
                "validation": {"commands": [{"command": command, "result": "passed"}]},
            },
            {"task_id": "task-001", "files": {"write": ["feature.ts"]}},
        ),
    ]

    with pytest.raises(
        SystemExit, match="acceptance-blocked: material handoff repository provenance is unavailable"
    ):
        _material_repository_root(
            argparse.Namespace(project_root=str(tmp_path)), "plan-001", validated, [command]
        )


def test_write_handoff_fills_missing_task_plan_from_authorized_args(
    tmp_path: Path, lower_level_handoff_writer,
) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "related:\n  task: task-001\nresult:\n  state: completed\n  summary: ok\n",
        encoding="utf-8",
    )
    cmd_write_handoff(
        handoff_args(tmp_path, content_file=str(content), related_plan="plan-B", related_task="task-001")
    )
    row = next(item for item in index_handoffs(handoff_args(tmp_path)) if item["id"] == "handoff-exec-20990101-001")
    written = (tmp_path / row["path"]).read_text(encoding="utf-8")
    assert "plan: plan-B" in written
    assert "task: task-001" in written


def test_write_handoff_rejects_conflicting_plan_identity(
    tmp_path: Path, lower_level_handoff_writer,
) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "related:\n  plan: plan-A\n  task: task-001\nresult:\n  state: completed\n  summary: ok\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Handoff plan mismatch"):
        cmd_write_handoff(
            handoff_args(tmp_path, content_file=str(content), related_plan="plan-B", related_task="task-001")
        )


def test_write_handoff_rejects_nested_and_flat_plan_conflict(
    tmp_path: Path, lower_level_handoff_writer,
) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text(
        "related:\n  plan: plan-B\n  task: task-001\nrelated_plan: plan-A\n"
        "result:\n  state: completed\n  summary: ok\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Handoff plan identity conflict"):
        cmd_write_handoff(
            handoff_args(tmp_path, content_file=str(content), related_plan="plan-B", related_task="task-001")
        )


def test_handoff_helper_rejects_active_orchestration_handoff(tmp_path: Path) -> None:
    content = tmp_path / "handoff-content.txt"
    content.write_text("# retired\n", encoding="utf-8")
    args = handoff_args(tmp_path, content_file=str(content), type="orchestration", id="handoff-orch-20990101-001")
    with pytest.raises(SystemExit, match="Active orchestration handoff creation is retired"):
        cmd_write_handoff(args)


def test_doctor_rejects_forbidden_executor_fields_and_retired_handoffs(tmp_path: Path) -> None:
    root = tmp_path / ".work-bundle/orchestration/handoff"
    executor = root / "executor/active"
    orchestration = root / "orchestration/active"
    executor.mkdir(parents=True)
    orchestration.mkdir(parents=True)
    (executor / "bad.yaml").write_text("id: bad\nrecommended_next_actions: []\n", encoding="utf-8")
    (orchestration / "bad.md").write_text("# retired\n", encoding="utf-8")
    issues: list[str] = []
    check_active_handoff_contract(issues, tmp_path / ".work-bundle/orchestration")
    assert any("forbidden field recommended_next_actions" in issue for issue in issues)
    assert any("active orchestration handoff is retired" in issue for issue in issues)


def test_specification_contract_uses_semantic_loop_and_workspace_policy() -> None:
    contract = read("references/assets/orchestration/contract/specification-v1.md")
    for token in [
        "Initial User Purpose Evidence",
        "Draft Requirement Breakdown",
        "Source Context",
        "Design Interrogation",
        "Knowledge Base Update",
        "Quality gate: verified|blocked",
        "execution_workspace:",
        "isolation: required|preferred|existing",
        "semantic_loop:",
        "dev-semantic-convergence",
        "front-matter `source_knowledge` contains accepted authority only",
        "Candidate, background, blocked, and superseded",
        "AUTH-NNN: <carried constraint>",
    ]:
        assert token in contract
    assert "Extra evidence loop" not in contract


def test_specification_contract_requires_bounded_impact_decisions() -> None:
    contract = read("references/assets/orchestration/contract/specification-v1.md")
    skill = read("skills/orch-create-specification/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    evals = read("references/evals/orchestration/evals.json")
    for text in (contract, skill, workflow):
        for token in [
            "impact_decisions",
            "accepted | excluded | blocking",
            "none_relevant",
            "stopping_reason",
            "projects_to",
            "current-state evidence",
            "dirty work",
        ]:
            assert token in text
        assert "durable knowledge" in text
        assert "projects_to" in text and "stable" in text
        assert "user-observable or contractual outcome" in text
        assert "measurable quality target" in text
        assert "Stop when further exploration could change none of those surfaces and record the reason" in text
    for text in (contract, skill):
        assert "blocking" in text and "open question" in text.lower()
    assert "blocking relations prevent verification" in workflow
    assert "impact-decision view" in skill
    assert "keep repository traversal out of `dev-semantic-convergence`" in skill
    assert "Git history, prior work artifacts, execution evidence, or durable knowledge" in skill
    assert "user did not mention" in contract
    assert "existing downstream consumer" in evals
    assert "greenfield isolated utility" in evals
    assert "mandatory full-history archaeology" in evals
    assert "prior work artifacts, execution evidence, or durable knowledge" in evals
    assert "related-but-non-material relation" in evals


def test_specification_contract_requires_bounded_excellence_applicability() -> None:
    contract = read("references/assets/orchestration/contract/specification-v1.md")
    skill = read("skills/orch-create-specification/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    evals = read("references/evals/orchestration/evals.json")
    for text in (contract, skill, workflow):
        for token in [
            "excellence_applicability",
            "no_material_opportunity",
            "material_opportunities",
            "accepted | rejected | deferred | not_material",
            "Only accepted proposals",
            "unanswered proposals become deferred",
            "evidence",
            "cost",
            "risk",
            "recommendation",
        ]:
            assert token in text
        assert "universal checklist" in text
        assert "one compact pass" in text
        assert "accepting or rejecting it could change a requirement" in text
        assert "user-observable or contractual outcome" in text
        assert "measurable quality target" in text
        assert "further exploration could change none of those surfaces" in text
    assert "excellence-applicability view" in skill
    plan_skill = read("skills/orch-create-implementation-plan/SKILL.md")
    assert "EXC-*" in plan_skill or "EXC-" in plan_skill
    assert "deferred" in plan_skill and "executor briefs" in plan_skill
    assert "user-visible request with no evidenced adjacent improvement" in evals
    assert "silently implements a deferred proposal" in evals
    assert "accepted proposal" in evals and "stable authoritative" in evals
    assert "universal product-quality checklist" in evals
    assert "related-but-non-material adjacent idea" in evals
    assert "source_ids: [EXC-001]" in evals


def test_planning_contract_allocates_evidence_capability() -> None:
    plan = read("references/assets/orchestration/contract/plan-v1.md")
    task = read("references/assets/orchestration/contract/task-v1.md")
    skill = read("skills/orch-create-implementation-plan/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    for text in (plan, task, skill, workflow):
        assert "evidence_capability" in text
        assert "no_validation_bearing_obligation" in text
    for text in (task, skill, workflow):
        assert "capability_reason" in text
        assert "freshness" in text
        assert "task" in text.lower()
    assert "WOR-61 `none_relevant`" in skill
    assert "lightest capable" in skill
    assert "universal runtime" in workflow


def test_archive_plan_uses_accepted_execution_dispositions_as_knowledge_gate(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Stable authority changed.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_archive_plan_completed_handoff_rejects_missing_harness_mutation_evidence(
    tmp_path: Path,
) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
    )

    with pytest.raises(SystemExit, match="mutation.*evidence|mutation_events"):
        cmd_archive_plan(argparse.Namespace(project_root=str(root), id="plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_archive_plan_cli_accepts_explicit_harness_mutation_evidence() -> None:
    parsed = load_orchestration_dispatcher().build_parser().parse_args(
        [
            "archive-plan",
            "--id",
            "plan-001",
            "--mutation-events",
            "[]",
        ]
    )

    assert parsed.mutation_events == []


def test_archive_plan_rejects_controller_task_scope_mutation_evidence(
    tmp_path: Path,
) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import (
        WRITE_SCOPE_FILE,
        workspace,
        write_executor_handoff,
    )

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
    )

    with pytest.raises(SystemExit, match="controller mutated task-owned implementation scope"):
        cmd_archive_plan(
            archive_args(
                root,
                "plan-001",
                mutation_events=[
                    {"actor_kind": "controller", "paths": [WRITE_SCOPE_FILE]}
                ],
            )
        )

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


@pytest.mark.parametrize(
    ("verdict", "action", "closure_return"),
    [
        ("repair", "update", "missing"),
        ("accept", "none", "missing"),
        ("accept", "reclassify", "completed"),
    ],
)
def test_archive_plan_allows_only_resolved_or_non_triggering_dispositions(
    tmp_path: Path, verdict: str, action: str, closure_return: str
) -> None:
    from plans import cmd_archive_plan

    plan_root = tmp_path / ".work-bundle/orchestration/plan/active"
    handoff_root = tmp_path / ".work-bundle/orchestration/handoff/executor/active"
    plan_root.mkdir(parents=True)
    handoff_root.mkdir(parents=True)
    (plan_root / "plan.md").write_text(
        "---\nid: plan-001\nstatus: Completed\n---\n\n"
        "## 2.1 Knowledge Base Update Carry Forward\n\n"
        "- **Disposition**: not-needed\n"
        f"- **Closure return**: {closure_return}\n",
        encoding="utf-8",
    )
    (handoff_root / "task.yaml").write_text(
        "id: handoff-001\ntype: executor-result\nstatus: active\n"
        "related: {plan: plan-001, task: task-001}\n"
        f"acceptance_review: {{verdict: {verdict}}}\n"
        "knowledge_disposition:\n"
        f"  action: {action}\n"
        "  reason: Task-local evidence.\n"
        f"  affected_authority: {'[]' if action == 'none' else '[AUTH-001]'}\n",
        encoding="utf-8",
    )

    cmd_archive_plan(archive_args(tmp_path, "plan-001"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan.md").is_file()


def _write_archive_plan(
    tmp_path: Path,
    plan_id: str,
    *,
    disposition: str = "not-needed",
    closure_return: str = "missing",
) -> None:
    plan_root = tmp_path / ".work-bundle/orchestration/plan/active"
    plan_root.mkdir(parents=True, exist_ok=True)
    (plan_root / f"{plan_id}.md").write_text(
        f"---\nid: {plan_id}\nstatus: Completed\n---\n\n"
        "## 2.1 Knowledge Base Update Carry Forward\n\n"
        f"- **Disposition**: {disposition}\n"
        f"- **Closure return**: {closure_return}\n",
        encoding="utf-8",
    )
    task = plan_root / f"{plan_id}/phase-001/task.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(
        f"---\nid: task-001\nplan_id: {plan_id}\nphase_id: phase-001\nstatus: Completed\n---\n",
        encoding="utf-8",
    )


FOLLOW_ON_WRITE_SCOPE_FILE = "scripts/orchestration/plans.py"
ARCHIVE_NEUTRAL_COMMAND = "env true"


def _append_plan_knowledge(root: Path, *, closure_return: str = "missing") -> None:
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 2.1 Knowledge Base Update Carry Forward\n\n"
        + "- **Disposition**: not-needed\n"
        + f"- **Closure return**: {closure_return}\n",
        encoding="utf-8",
    )


def _append_plan_integration_command(root: Path, command: str) -> None:
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )


def _write_follow_on_plan_task(
    root: Path, *, task_id: str = "task-005", write_file: str = FOLLOW_ON_WRITE_SCOPE_FILE
) -> Path:
    source = root / ".work-bundle/orchestration/plan/active/plan-001/phase-001/task-004.md"
    task = source.with_name(f"{task_id}.md")
    task.write_text(
        source.read_text(encoding="utf-8")
        .replace("id: task-004\n", f"id: {task_id}\n")
        .replace(
            "write: [scripts/orchestration/execution_context.py]\n",
            f"write: [{write_file}]\n",
        ),
        encoding="utf-8",
    )
    return task


def _git_commit_file(root: Path, relative: str, content: str, message: str) -> str:
    from test_orchestration_execution_context import git

    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(root, "add", "--", relative)
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def _git_write_tree(root: Path) -> str:
    from test_orchestration_execution_context import git

    git(root, "add", "-A")
    return git(root, "write-tree")


def _record_repository_commit(evidence: str, actual_commit: str) -> str:
    marker = "    status: clean\n"
    assert marker in evidence
    return evidence.replace(
        marker,
        marker + "    metadata:\n" + f"      actual_commit: {actual_commit}\n",
        1,
    )


def _complete_evidence_blocks(root: Path, *, actual_commit: str | None = None) -> str:
    from test_orchestration_execution_context import evidence_blocks

    evidence = evidence_blocks(root)
    return evidence if actual_commit is None else _record_repository_commit(evidence, actual_commit)


def _write_follow_on_executor_handoff(
    root: Path,
    *,
    task_id: str,
    created_at: str,
    write_file: str = FOLLOW_ON_WRITE_SCOPE_FILE,
    extra_command: str | None = None,
    extra_result: str = "passed",
    actual_commit: str | None = None,
    reviewed_head: str | None = None,
) -> Path:
    from test_orchestration_execution_context import TASK_VALIDATION_COMMAND

    extra = "" if extra_command is None else f"    - {{command: {extra_command}, result: {extra_result}}}\n"
    review = "" if reviewed_head is None else f"acceptance_review: {{reviewed_head: {reviewed_head}}}\n"
    evidence = _complete_evidence_blocks(root, actual_commit=actual_commit)
    handoff = root / f".work-bundle/orchestration/handoff/executor/active/handoff-{task_id}.yaml"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(
        f"id: handoff-{task_id}\n"
        "type: executor-result\n"
        f"created_at: {created_at}\n"
        f"related: {{plan: plan-001, task: {task_id}}}\n"
        "result: {state: completed}\n"
        f"task_fit_check: {{task: {task_id}, result: clean}}\n"
        "changes:\n"
        "  files:\n"
        f"    - {{path: {write_file}, action: modified}}\n"
        "validation:\n"
        "  commands:\n"
        f"    - {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
        f"{extra}"
        f"{review}"
        f"{evidence}"
        "knowledge_disposition:\n"
        "  action: none\n"
        "  reason: No stable authority changed.\n"
        "  affected_authority: []\n",
        encoding="utf-8",
    )
    return handoff


def _write_earlier_integration_pass(root: Path, command: str, *, created_at: str) -> Path:
    from test_orchestration_execution_context import TASK_VALIDATION_COMMAND, git, write_executor_handoff

    try:
        head = git(root, "rev-parse", "HEAD")
    except subprocess.CalledProcessError:
        git(root, "add", ".")
        git(root, "commit", "-qm", "integration acceptance baseline")
        head = git(root, "rev-parse", "HEAD")

    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    content = (
        handoff.read_text(encoding="utf-8")
        .replace("id: handoff-task-004\n", f"id: handoff-task-004\ncreated_at: {created_at}\n")
        .replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        )
    )
    handoff.write_text(_record_repository_commit(content, head), encoding="utf-8")
    return handoff


def _write_archive_handoff(
    tmp_path: Path,
    filename: str,
    related: str,
    *,
    verdict: str | None = "accept",
    action: str = "update",
    location: str = "active",
    result_state: str | None = None,
) -> None:
    handoff_root = tmp_path / ".work-bundle/orchestration/handoff/executor" / location
    handoff_root.mkdir(parents=True, exist_ok=True)
    affected = "[]" if action == "none" else "[AUTH-001]"
    review_line = "" if verdict is None else f"acceptance_review: {{verdict: {verdict}}}\n"
    result_line = "" if result_state is None else f"result: {{state: {result_state}}}\n"
    (handoff_root / filename).write_text(
        f"id: {filename.rsplit('.', 1)[0]}\ntype: executor-result\nstatus: {location}\n"
        f"related: {related}\n"
        f"{result_line}"
        f"{review_line}"
        "knowledge_disposition:\n"
        f"  action: {action}\n"
        "  reason: Task-local evidence.\n"
        f"  affected_authority: {affected}\n",
        encoding="utf-8",
    )


def test_archive_plan_ignores_foreign_plan_handoff_with_colliding_task_id(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-A")
    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(tmp_path, "plan-a.yaml", "{plan: plan-A, task: task-001}")

    cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()
    assert (tmp_path / ".work-bundle/orchestration/plan/active/plan-A.md").is_file()


def test_archive_plan_skips_unrelated_unparseable_executor_yaml(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-A")
    _write_archive_plan(tmp_path, "plan-B")
    handoff_root = tmp_path / ".work-bundle/orchestration/handoff/executor/active"
    handoff_root.mkdir(parents=True, exist_ok=True)
    (handoff_root / "foreign-block.yaml").write_text(
        "id: foreign\n"
        "type: executor-result\n"
        "related:\n"
        "  plan: plan-A\n"
        "  task: task-001\n"
        "summary: >\n"
        "  unsupported folded scalar\n",
        encoding="utf-8",
    )
    (handoff_root / "foreign-inline.yaml").write_text(
        "id: foreign-inline\n"
        "type: executor-result\n"
        "related: {plan: plan-A, task: task-001}\n"
        "summary: >\n"
        "  unsupported folded scalar\n",
        encoding="utf-8",
    )

    cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()
    assert (tmp_path / ".work-bundle/orchestration/plan/active/plan-A.md").is_file()


def test_archive_plan_ignores_task_only_handoff_with_ambiguous_task_id(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(tmp_path, "task-only.yaml", "{task: task-001}")

    cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_archive_plan_ignores_archived_foreign_handoff_with_colliding_task_id(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-A")
    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(
        tmp_path, "historical.yaml", "{plan: plan-A, task: task-001}", location="archived"
    )

    cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_archive_plan_same_plan_accepted_update_still_blocks_unresolved_closure(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Task-local evidence.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_archive_plan_same_plan_resolved_closure_allows_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-B", closure_return="completed")
    _write_archive_handoff(tmp_path, "plan-b.yaml", "{plan: plan-B, task: task-001}")

    cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_task_contract_compiles_methodology_capability_and_review() -> None:
    contract = read("references/assets/orchestration/contract/task-v1.md")
    for token in [
        "source_ids:",
        "truth_basis:",
        "as_is_evidence:",
        "decision_authority:",
        "expected_delta:",
        "conflict_status: clear|escalate",
        "decision-blocked",
        "semantically distinct from generic `source_ids`",
        "none-relevant",
        "verified specification's accepted `source_knowledge`",
        "AUTH-NNN: <carried constraint>",
        "methodology:",
        "tdd|systematic-debugging|direct|loop-coding",
        "executor_profile:",
        "mechanical|standard|judgment",
        "context_mode: compiled-brief",
        "after_failed_repairs: 2",
        "acceptance_review:",
        "verdict: pending",
        "Fresh task validation evidence exists",
        "acceptance_review.verdict",
        "EXC-*",
        "executor briefs",
    ]:
        assert token in contract


def test_task_contract_defines_material_review_freshness_without_identity_rotation() -> None:
    contract = read("references/assets/orchestration/contract/task-v1.md")

    for token in [
        "`review_reset` bound to the prior review, classified reason, and current target and evidence",
        "may reuse the same agent identity",
        "judgment-capable",
        "authorship/repair/decision/deliberation participation",
        "review provenance",
    ]:
        assert token in contract
    assert "may not reuse the repair reviewer identity" not in contract


def test_executor_result_contract_keeps_review_authority_outside_handoff() -> None:
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    for token in [
        "acceptance_review:",
        "lifecycle_authority: location-v1",
        "wrong-owner fields",
        "accepted-result materialization later joins",
        "complete bytes never change after creation",
        "legacy-status-overrides/<handoff-id>.json",
        "knowledge_disposition:",
        "none | update | supersede | reclassify",
        "review owns any approved persistence follow-up",
        "must not name knowledge paths or any `ks-*` skill",
        "exact paths already present in the compiled task scope",
        "allocated `AUTH-NNN` aliases",
        "related.plan",
        "must equal the assigned task's `plan_id` and `id`",
        "fails closed before `Completed` and before `build-review-package`",
        "current lifecycle status comes from the status-specific location",
    ]:
        assert token in contract


def test_workflow_separates_durable_artifacts_from_runtime_packets() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "Disposable task briefs, review packages, and lightweight development plans",
        ".work-bundle/runtime/",
        "no active/archive/index lifecycle",
        "build-task-brief",
        "Missing source IDs fail closed",
        "Full specification, root-plan, and phase reading is an escalation path",
        "Execution remains no-retrieval",
        "AUTH-NNN: <carried constraint>",
        "same five-field Truth Basis",
        "earliest ordinary task",
        "knowledge disposition",
        "review owns approved persistence",
        "expected total orchestration cost",
        "accepted task dispositions",
    ]:
        assert token in workflow


def test_workflow_assigns_review_ownership_and_repair_loop() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "Product reviewers judge accepted product requirements",
        "Schedulers own dependencies",
        "they do not perform code-quality review",
        "requires a subagent owner for every task",
        "fails closed before task mutation",
        "dispatch before any wait",
        "one scoped rereview",
        "A task becomes `Completed` only when",
        "Review-required tasks additionally require exact stored `accept` authority",
        "optional task review when compiled review_required: true",
        "accepted Truth Basis",
        "normalized validation observations",
    ]:
        assert token in workflow


def test_workflow_uses_accepted_results_without_lifecycle_replay() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "acceptance once",
        "compact accepted result",
        "historical handoff chains",
        "transient acceptance evidence",
        "current harness observation",
        "reviewer infrastructure or provider failure",
        "same immutable review package",
        "previous finding/evidence frontier",
        "status-only or append-only evidence",
        "causal class",
        "first owning layer",
        "exact baseline and endpoint",
        "issue-run artifacts",
    ]:
        assert token in workflow


def test_review_rule_uses_typed_resume_routing() -> None:
    rule = read("rules/orchestration/orch-review-completion.md")
    for token in [
        "knowledge-blocked",
        "repository-blocked",
        "workspace-blocked",
        "Route missing evidence to its first owner",
        "publication-only/control resume",
        "plan repair only for a decomposition defect",
        "specification repair only for a requirement, design, or authority defect",
        "Do not create a repair specification for every failed review gate",
        "accepted `update`, `supersede`, or `reclassify`",
        "rejected dispositions",
        "archive",
        "evidence_capability",
        "INV/VAL",
        "incapable green",
        "pre-closure oracle-capability check",
        "no_validation_bearing_obligation",
        "WOR-59 G9 remains the unchanged post-execution classifier",
    ]:
        assert token in rule


def test_workflow_preserves_repository_codegraph_workspace_and_secret_safety() -> None:
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        ".work-bundle/project.yaml",
        "Never stash, reset, clean, restore, delete, or overwrite user work",
        "CodeGraph first only when a target contains `.codegraph/`",
        "Record `no-index`",
        "Never delete user or harness workspaces",
        "Never copy credential values",
        "credential-inject",
    ]:
        assert token in workflow


def test_evals_cover_twenty_migration_behaviors() -> None:
    cases = evals()
    prompts = "\n".join(str(case["prompt"]) for case in cases)
    expected = "\n".join(str(case["expected_output"]) for case in cases)
    for token in [
        "accepted independent task review",
        "no task-review verdict",
        "wrong API requirement",
        "Knowledge Base Update disposition required",
        "semantic view finds one missing constraint",
        "omits one spec ID",
        "low-judgment two-file implementation",
        "Compile a task brief",
        "changes testable production behavior",
        "configuration-only task",
        "unexpected retry bug",
        "independent task reviewer",
        "second repeated repair rejection",
        "lightweight mechanical plan",
        "provenance owner is user",
        "credential-inject",
        "Hydrate .codegraph",
        "before the final edit",
        "durable knowledge update is unresolved",
        "compiled brief is valid",
        "ordinary characterization task",
        "conflict_status escalate",
        "asks to invoke a ks-* writer",
        "implementation and tests do not match",
        "device-local checkout observations disagree",
    ]:
        assert token in prompts
    for token in [
        "review-blocked",
        "specification repair",
        "knowledge-blocked",
        "semantic_loop",
        "capability mechanical",
        "fails closed on missing IDs",
        "systematic debugging",
        "escalates to full orchestration",
        "Refuses deletion",
        "does not blindly copy or symlink",
        "evidence is stale",
        "full specification, root-plan, and phase reads",
    ]:
        assert token in expected


def test_no_review_completed_handoff_does_not_require_accept_or_reviewer() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    for token in [
        "A review-required task additionally needs exact stored `accept` authority",
        "assign `dev-code-review` only when compiled `review_required: true`",
        "Skip this hop when review is not required",
    ]:
        assert token in execute
    assert "verdict: accept" not in str(_completed_executor_result())

    validated = validate_executor_result_for_task(
        _completed_executor_result(), _task_brief(), mutation_events=[]
    )
    assert validated["result_state"] == "completed"
    assert validated["knowledge_disposition"]["action"] == "none"


def test_execute_plan_requires_bound_observation_and_isolate_or_serialize() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    plan = read("skills/orch-create-implementation-plan/SKILL.md")
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    for token in [
        "harness-owned task execution binding",
        "capture the pre-task baseline once",
        "cannot supply or replace that baseline",
        "bound execution repository",
        "isolate via prepare_worktree or serialize",
        "Git-state-neutral",
        "validate-executor-result",
    ]:
        assert token in execute
    assert "mutating siblings on the same execution path isolate via prepare_worktree or serialize" in plan
    assert "cannot supply or replace that baseline" in contract
    assert "corroboration" in contract
    assert "not independent proof" in contract or "not authority" in contract


def test_optional_review_package_does_not_absorb_sibling_task_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_orchestration_execution_context import (
        WRITE_SCOPE_FILE,
        args as review_args,
        git,
        workspace,
        write_executor_handoff,
    )

    root, _, task_b = workspace(tmp_path)
    scoped = root / WRITE_SCOPE_FILE
    scoped.parent.mkdir(parents=True, exist_ok=True)
    scoped.write_text("def compile_task():\n    return 'old'\n", encoding="utf-8")
    task_a_file = root / "src/task_a.py"
    task_a_file.parent.mkdir(parents=True, exist_ok=True)
    task_a_file.write_text("TASK_A_OLD = 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    scoped.write_text("def compile_task():\n    return 'task-b'\n", encoding="utf-8")
    task_a_file.write_text("TASK_A_NEW = 2\n", encoding="utf-8")
    from test_orchestration_execution_context import _bind_passing_observation

    monkeypatch.setattr("review_runtime.require_plan_reviews", lambda *_args: None)
    handoff = _bind_passing_observation(root, task_b)

    package = build_review_package(
        review_args(root, task_b, handoff=str(handoff), base=base, head="worktree")
    ).read_text(encoding="utf-8")
    diff = package.split("## Diff", 1)[1].split("## Out-of-scope changes", 1)[0]
    diagnostics = package.split("## Out-of-scope changes", 1)[1].split("## ", 1)[0]

    assert "## Out-of-scope changes" in package
    assert "return 'task-b'" in diff
    assert "TASK_A_NEW" not in diff
    assert "src/task_a.py" not in diff
    assert "src/task_a.py" in diagnostics
    assert WRITE_SCOPE_FILE in package.split("## Changed files", 1)[1].split("## ", 1)[0]


def test_failing_declared_plan_acceptance_blocks_archive_without_second_reviewer(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    review = read("skills/orch-review-plan/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    for token in [
        "declared plan-level/integration acceptance observed on the final integrated workspace",
        "do not start another implementation-review agent to produce plan-level acceptance",
        "Archive remains blocked while any required knowledge, validation, review",
    ]:
        assert token in review
    for token in [
        "declared plan-level/integration acceptance is recorded",
        "It does not redo task code review, reread implementation for code quality, or start another implementation-review agent",
        "Missing stored review authority is not a blocker when no compiled task set `review_required: true`",
    ]:
        assert token in workflow

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    _write_archive_plan(tmp_path, "plan-B")
    plan = tmp_path / ".work-bundle/orchestration/plan/active/plan-B.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    _write_archive_handoff(
        tmp_path,
        "plan-b.yaml",
        "{plan: plan-B, task: task-001}",
        verdict=None,
        action="none",
        result_state="completed",
    )
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/plan-b.yaml"
    handoff.write_text(
        handoff.read_text(encoding="utf-8")
        + "validation:\n"
        + "  commands:\n"
        + f"    - {{command: {command}, result: failed}}\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/active/plan-B.md").is_file()


def _mapped_archive_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from test_orchestration_execution_context import (
        PASSING_PROCESS,
        _bind_task_execution,
        _compiled_brief,
        _handoff_for_command,
        _set_task_validation,
        git,
        workspace,
    )

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "evidence_capability:\n"
            "  result: no_validation_bearing_obligation\n"
            "  reason: This shared fixture leaves capability semantics to scenario-specific tests.\n"
            "  invariants: []\n",
            "evidence_capability:\n"
            "  result: mapped\n"
            "  reason: Archive re-entry must observe mapped invariants.\n"
            "  invariants:\n"
            "    - {id: INV-001, source_ids: [REQ-003], invariant: Observable behavior, boundary: integration, oracle: VAL-001, capability_reason: Process oracle distinguishes violation., freshness: current_task_batch, task_id: task-004, evidence_ids: [VAL-001], closure_result: pending}\n",
        ),
        encoding="utf-8",
    )
    _set_task_validation(
        task,
        "validation:\n"
        f"  - {{kind: process, command: {json.dumps(PASSING_PROCESS)}, proves: TEST-004, expected: passed, id: VAL-001, invariant_ids: [INV-001], capability_reason: Process oracle distinguishes violation.}}\n",
    )
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    git(root, "add", ".")
    git(root, "commit", "-qm", "mapped archive workspace")
    brief = _compiled_brief(root, task)
    monkeypatch.setattr("review_runtime.require_plan_reviews", lambda *_args: None)
    binding = _bind_task_execution(root, brief)
    handoff = _handoff_for_command(root, PASSING_PROCESS)
    handoff.write_text(
        handoff.read_text(encoding="utf-8").replace(
            f"- {{command: {json.dumps(PASSING_PROCESS)}, result: passed}}\n",
            f"- {{command: {json.dumps(PASSING_PROCESS)}, result: passed, id: VAL-001, invariant_ids: [INV-001]}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        )
        + "evidence_closure:\n"
        + "  result: passed\n"
        + "  invariants:\n"
        + "    - {id: INV-001, boundary: integration, freshness: current_task_batch, evidence_ids: [VAL-001], closure_result: passed}\n",
        encoding="utf-8",
    )
    return root, binding, command


def test_archive_plan_accepts_mapped_invariant_handoff_with_harness_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plans import cmd_archive_plan

    root, _binding, _command = _mapped_archive_workspace(tmp_path, monkeypatch)

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_archive_plan_does_not_replay_task_validation_from_execution_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plans import cmd_archive_plan

    root, binding, command = _mapped_archive_workspace(tmp_path, monkeypatch)

    cmd_archive_plan(
        archive_args(
            root,
            "plan-001",
            workspace_id=binding["workspace_id"],
            execution_id=binding["execution_id"],
            repository_id=binding["repository_id"],
            execution_runtime_root=binding["runtime_root"],
        )
    )
    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()

    restored = tmp_path / "restored-mapped"
    restored.mkdir()
    restored_root, restored_binding, _command = _mapped_archive_workspace(
        restored, monkeypatch
    )
    cmd_archive_plan(
        archive_args(
            restored_root,
            "plan-001",
            workspace_id="wrong-workspace",
            execution_id=restored_binding["execution_id"],
            repository_id=restored_binding["repository_id"],
            execution_runtime_root=restored_binding["runtime_root"],
        )
    )
    assert (restored_root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_passing_declared_plan_acceptance_allows_archive_without_second_reviewer(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import (
        TASK_VALIDATION_COMMAND,
        git,
        workspace,
        write_executor_handoff,
    )

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    git(root, "add", ".")
    git(root, "commit", "-qm", "final workspace")
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    handoff.write_text(
        handoff.read_text(encoding="utf-8").replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        ),
        encoding="utf-8",
    )

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_unvalidated_handoff_cannot_satisfy_declared_plan_acceptance(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    _write_archive_plan(tmp_path, "plan-B")
    plan = tmp_path / ".work-bundle/orchestration/plan/active/plan-B.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    _write_archive_handoff(
        tmp_path,
        "plan-b.yaml",
        "{plan: plan-B, task: task-001}",
        verdict=None,
        action="none",
        result_state="completed",
    )
    handoff = tmp_path / ".work-bundle/orchestration/handoff/executor/active/plan-b.yaml"
    handoff.write_text(
        handoff.read_text(encoding="utf-8")
        + "validation:\n"
        + "  commands:\n"
        + f"    - {{command: {command}, result: passed}}\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(archive_args(tmp_path, "plan-B"))


def _record_tree_fresh_integration_pass(root: Path, command: str) -> str:
    from test_orchestration_execution_context import TASK_VALIDATION_COMMAND, git, write_executor_handoff

    git(root, "add", ".")
    git(root, "commit", "-qm", "tree-fresh acceptance baseline")
    head = git(root, "rev-parse", "HEAD")
    handoff = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    content = handoff.read_text(encoding="utf-8").replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        )
    handoff.write_text(_record_repository_commit(content, head), encoding="utf-8")
    return head


def test_tree_fresh_executor_pass_without_harness_observation_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    command = "env false"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _record_tree_fresh_integration_pass(root, command)

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_task_worktree_command_pass_cannot_archive_different_final_workspace(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import git, workspace

    command = "test -f worktree-only-marker"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    git(root, "add", ".")
    git(root, "commit", "-qm", "final workspace")
    worktree = tmp_path / "isolated-task-worktree"
    git(root, "worktree", "add", str(worktree), "HEAD")
    (worktree / "worktree-only-marker").write_text("isolated\n", encoding="utf-8")
    _write_earlier_integration_pass(root, command, created_at="2026-08-17")

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()
    assert not (root / "worktree-only-marker").exists()


def test_passing_mutating_integration_command_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    command = "touch mutated-by-acceptance.txt"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _record_tree_fresh_integration_pass(root, command)

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_contradictory_validated_plan_acceptance_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import (
        TASK_VALIDATION_COMMAND,
        workspace,
        write_executor_handoff,
    )

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    plan = root / ".work-bundle/orchestration/plan/active/compiler-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "\n## 7. Tests\n\n"
        + "| ID | Test Type | Target | Related Phase | Can Run With | Command | Expected Result |\n"
        + "|---|---|---|---|---|---|---|\n"
        + f"| TEST-099 | integration | full harness | phase-001 | - | `{command}` | all tests pass |\n",
        encoding="utf-8",
    )
    passed = write_executor_handoff(
        root,
        "  action: none\n  reason: No stable authority changed.\n  affected_authority: []\n",
    )
    passed.write_text(
        passed.read_text(encoding="utf-8").replace(
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n",
            f"- {{command: {TASK_VALIDATION_COMMAND}, result: passed}}\n"
            f"    - {{command: {command}, result: passed}}\n",
        ),
        encoding="utf-8",
    )
    failed = passed.parent / "handoff-task-004-failed.yaml"
    failed.write_text(
        passed.read_text(encoding="utf-8")
        .replace("id: handoff-task-004\n", "id: handoff-task-004-failed\n")
        .replace(f"- {{command: {command}, result: passed}}\n", f"- {{command: {command}, result: failed}}\n"),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="acceptance-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))


def test_stale_plan_acceptance_after_later_material_task_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_earlier_integration_pass(root, command, created_at="2026-08-15")
    _write_follow_on_plan_task(root)
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'later'\n",
        "task-005",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-005",
        created_at="2026-08-16",
        actual_commit=later,
    )

    with pytest.raises(SystemExit, match="acceptance-blocked:.*is failed"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_fresh_plan_acceptance_rerun_after_later_task_allows_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'old'\n", "task-004")
    _write_earlier_integration_pass(root, command, created_at="2026-08-15")
    _write_follow_on_plan_task(root)
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'fresh'\n",
        "task-005",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-005",
        created_at="2026-08-16",
        extra_command=command,
        actual_commit=later,
    )

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_archive_moves_plan_directory_named_for_root_artifact(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    active = root / ".work-bundle/orchestration/plan/active"
    (active / "compiler-plan.md").rename(active / "plan-001-feature.md")
    (active / "plan-001").rename(active / "plan-001-feature")

    cmd_archive_plan(archive_args(root, "plan-001"))

    archived = root / ".work-bundle/orchestration/plan/archived"
    assert (archived / "plan-001-feature.md").is_file()
    assert (archived / "plan-001-feature").is_dir()
    assert not (active / "plan-001-feature").exists()


def test_archive_reconciles_archived_root_with_active_plan_directory(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import workspace

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    plan_root = root / ".work-bundle/orchestration/plan"
    active = plan_root / "active"
    archived = plan_root / "archived"
    archived.mkdir(exist_ok=True)
    (active / "compiler-plan.md").rename(archived / "plan-001-feature.md")
    (active / "plan-001").rename(active / "plan-001-feature")

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (archived / "plan-001-feature.md").is_file()
    assert (archived / "plan-001-feature").is_dir()
    assert not (active / "plan-001-feature").exists()


def test_same_day_out_of_id_order_stale_plan_acceptance_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'first'\n", "task-010")
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'later'\n",
        "task-002",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        actual_commit=later,
    )

    with pytest.raises(SystemExit, match="acceptance-blocked:.*is failed"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_same_day_out_of_id_order_fresh_rerun_allows_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'first'\n", "task-010")
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'later'\n",
        "task-002",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        extra_command=command,
        actual_commit=later,
    )

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_historical_failed_plan_acceptance_does_not_poison_fresh_head_pass(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'broken'\n", "task-010-fail")
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        extra_result="failed",
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    later = _git_commit_file(
        root,
        FOLLOW_ON_WRITE_SCOPE_FILE,
        "def archive_plan():\n    return 'repaired'\n",
        "task-002-pass",
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        extra_command=command,
        actual_commit=later,
    )

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_same_tree_contradictory_plan_acceptance_still_blocks_archive(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, workspace

    command = "uv run --with pytest pytest -q tests/test_plan_acceptance.py"
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    head = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'now'\n", "terminal")
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        extra_result="failed",
        actual_commit=head,
    )
    _write_follow_on_executor_handoff(
        root,
        task_id="task-004",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=head,
    )

    with pytest.raises(SystemExit, match="acceptance-blocked:.*contradictory"):
        cmd_archive_plan(archive_args(root, "plan-001"))


def test_precommit_tree_pass_survives_same_tree_finalization_commit(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import WRITE_SCOPE_FILE, git, workspace

    command = ARCHIVE_NEUTRAL_COMMAND
    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    _append_plan_integration_command(root, command)
    first = _git_commit_file(root, WRITE_SCOPE_FILE, "def compile_task():\n    return 'base'\n", "task-010")
    _write_follow_on_plan_task(root, task_id="task-010", write_file=WRITE_SCOPE_FILE)
    _write_follow_on_executor_handoff(
        root,
        task_id="task-010",
        created_at="2026-08-16",
        write_file=WRITE_SCOPE_FILE,
        extra_command=command,
        actual_commit=first,
    )
    _write_follow_on_plan_task(root, task_id="task-002")
    (root / FOLLOW_ON_WRITE_SCOPE_FILE).write_text("def archive_plan():\n    return 'final'\n", encoding="utf-8")
    tree = _git_write_tree(root)
    _write_follow_on_executor_handoff(
        root,
        task_id="task-002",
        created_at="2026-08-16",
        extra_command=command,
        reviewed_head=tree,
    )
    git(root, "commit", "-qm", "finalize")

    cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/archived/compiler-plan.md").is_file()


def test_archive_plan_no_review_completed_update_blocks_until_closure_return(
    tmp_path: Path,
) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, _ = workspace(tmp_path)
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Task-local evidence.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_archive_plan_ignores_unvalidated_update_handoff(tmp_path: Path) -> None:
    from plans import cmd_archive_plan

    _write_archive_plan(tmp_path, "plan-B")
    _write_archive_handoff(
        tmp_path,
        "plan-b.yaml",
        "{plan: plan-B, task: task-001}",
        verdict=None,
        result_state="completed",
    )

    cmd_archive_plan(archive_args(tmp_path, "plan-B"))

    assert (tmp_path / ".work-bundle/orchestration/plan/archived/plan-B.md").is_file()


def test_archive_plan_review_required_cannot_downgrade_via_omitted_required(tmp_path: Path) -> None:
    from plans import cmd_archive_plan
    from test_orchestration_execution_context import ACCEPTED_AUTHORITY, workspace, write_executor_handoff

    root, _, task = workspace(tmp_path)
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "acceptance_review:\n  required: false\n",
            "acceptance_review:\n  required: true\n",
        ),
        encoding="utf-8",
    )
    _append_plan_knowledge(root, closure_return="missing")
    write_executor_handoff(
        root,
        f"  action: update\n  reason: Task-local evidence.\n  affected_authority: [{ACCEPTED_AUTHORITY}]\n",
    )

    with pytest.raises(SystemExit, match="knowledge-blocked"):
        cmd_archive_plan(archive_args(root, "plan-001"))

    assert (root / ".work-bundle/orchestration/plan/active/compiler-plan.md").is_file()


def test_missing_or_wrong_plan_identity_cannot_complete_without_review_package() -> None:
    missing = _completed_executor_result(plan=None)
    with pytest.raises(SystemExit, match="Handoff plan identity missing"):
        validate_executor_result_for_task(missing, _task_brief())

    mismatched = _completed_executor_result(plan="plan-A")
    with pytest.raises(SystemExit, match="Handoff plan mismatch: expected plan-001, got plan-A"):
        validate_executor_result_for_task(mismatched, _task_brief())


def test_review_required_task_fails_closed_until_independent_accept() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    review = read("skills/orch-review-plan/SKILL.md")
    contract = read("references/assets/orchestration/contract/handoff-executor-result-v1.md")
    for token in [
        "Do not perform acceptance judgment or mark a review-required task complete",
        "A review-required task additionally needs exact stored `accept` authority",
    ]:
        assert token in execute
    for token in [
        "missing stored `accept` review authority blocks only a task whose compiled `review_required` is true",
        "exact stored `accept` authority only for those explicitly required reviews",
    ]:
        assert token in review
    assert "accepted-result materialization later joins it with the exact published review" in contract

    pending = {
        "related": {"plan": "plan-001", "task": "task-001"},
        "result": {"state": "completed"},
        "acceptance_review": {"required": True, "verdict": "pending"},
        "knowledge_disposition": {
            "action": "update",
            "reason": "Task-local evidence.",
            "affected_authority": ["AUTH-001"],
        },
    }
    closure = evaluate_knowledge_closure_state(
        upstream_disposition="not-needed",
        accepted_task_handoffs=[pending],
        closure_return="missing",
    )
    assert (closure["disposition"], closure["archive_blocked"]) == ("not-needed", False)

    review_required_handoff = _completed_executor_result(
        acceptance_review={"required": True, "verdict": "pending"}
    )
    with pytest.raises(SystemExit, match="accept|review"):
        validate_executor_result_for_task(
            review_required_handoff, {**_task_brief(), "review_required": True}
        )

    accepted = _completed_executor_result(
        acceptance_review={"required": True, "verdict": "accept"}
    )
    validated = validate_executor_result_for_task(
        accepted,
        {**_task_brief(), "review_required": True},
        mutation_events=[],
    )
    assert validated["result_state"] == "completed"


def test_workflow_distinguishes_native_and_legacy_process_review_provenance() -> None:
    workflow = read("references/assets/orchestration/workflow.md")

    for token in [
        "`reviewer-native-receipt-v1` for native host runs",
        "`reviewer-process-receipt-v1` for legacy sandboxed process runs",
        "`run_native_reviewer` for the ordinary plugin-independent native path",
        "native host read-only policy is not OS process isolation",
        "provider-specific execution boundary",
        "Publication validates the provider-specific reviewer-run receipt once",
        "Later lifecycle consumers use the immutable direct current-authority binding",
    ]:
        assert token in workflow
    for process_only_claim in [
        "referencing a native `reviewer-process-receipt-v1`",
        "Run the worker with `reviewer-process-run` using that runtime root",
        "completion, sandbox/network/write boundary, and immutable packet/profile/event",
        "recheck its receipt",
    ]:
        assert process_only_claim not in workflow


def test_current_orchestration_instructions_do_not_depend_on_execution_flow() -> None:
    owners = [
        read("references/assets/orchestration/workflow.md"),
        read("skills/orch-execute-plan/SKILL.md"),
        read("skills/orch-review-plan/SKILL.md"),
    ]
    for owner in owners:
        assert "host-native execution is sufficient" in owner
        assert "Execution Flow is optional" in owner


def test_review_contract_owners_use_common_provenance_and_final_knowledge_gate() -> None:
    provenance_owners = [
        "skills/orch-execute-plan/SKILL.md",
        "skills/orch-review-plan/SKILL.md",
        "references/assets/orchestration/contract/task-v1.md",
        "rules/orchestration/orch-review-completion.md",
        "references/assets/orchestration/workflow.md",
    ]
    for owner in provenance_owners:
        assert "provider-specific reviewer-run receipt" in read(owner), owner

    final_gate_owners = [
        "skills/orch-review-plan/SKILL.md",
        "rules/orchestration/orch-review-completion.md",
        "references/assets/orchestration/workflow.md",
    ]
    for owner in final_gate_owners:
        text = read(owner)
        assert "Knowledge closure gates final completion and archive" in text, owner
        assert "never precedes specification, plan, task, or integrated-implementation review" in text, owner


def test_overlapping_writes_are_not_parallelizable() -> None:
    execute = read("skills/orch-execute-plan/SKILL.md")
    create = read("skills/orch-create-implementation-plan/SKILL.md")
    workflow = read("references/assets/orchestration/workflow.md")
    plan = read("references/assets/orchestration/contract/plan-v1.md")
    assert "planner-proven dependencies, write scopes" in execute
    assert "Dispatch every ready independent task with disjoint write scope" in execute
    assert "Serialize dependent, overlapping, or same-workspace mutation" in execute
    assert "disjoint write scopes" in create
    assert "Independent disjoint tasks in distinct execution workspaces dispatch before any wait" in workflow
    assert "disjoint write scopes" in workflow
    assert "assign parallel tasks only when dependencies are satisfied and write scopes are disjoint" in plan
    assert "unsafe parallelization is explicitly blocked by dependency or scope evidence" in plan


def test_plan_contract_has_no_placeholder_markdown_links() -> None:
    plan = read("references/assets/orchestration/contract/plan-v1.md")

    assert "](.work-bundle/orchestration/spec/active/...)" not in plan
    assert "`.work-bundle/orchestration/spec/active/...`" in plan


def test_dev_create_task_plan_tests_omit_heavy_orchestration_requirements() -> None:
    skill = read("skills/dev-create-task-plan/SKILL.md")
    assert "Do not import executor-result, `Completed`, review package, archive helper, or heavy Knowledge Base Update closure" in skill
    tests = read("tests/test_dev_skill_contracts.py")
    assert "dev-create-task-plan" in tests
    assert ".work-bundle/runtime/dev-plans/" in tests
