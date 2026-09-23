from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import execution_context  # noqa: E402
from artifact_store import write_artifact  # noqa: E402
from test_orchestration_plans import CATALOG, _create_tree, workspace  # noqa: E402


@pytest.fixture(autouse=True)
def canonical_compiler_root(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_context, "resolve_workspace_root", lambda _args: workspace)


def _bind_v4_members(workspace: Path, monkeypatch: pytest.MonkeyPatch, names: list[str]) -> None:
    core = execution_context._loaded_core

    metadata = {
        "metadata_version": 4, "authority": "canonical",
        "workspace": {"id": "wb-test", "slug": "test", "mode": "multi-repository"},
        "control_plane": {"schema_version": 1, "repository": {"remote": ""}, "sync_policy": {"mode": "manual"}},
        "source_repositories": [
            {"id": name, "role": "source", "remote": {"canonical": f"https://example.com/{name}.git"},
             "default_branch": "main", "workspace_binding": {"type": "member", "name": name},
             "materialization": {"required": True}, "operation_policy": "inherit"}
            for name in names
        ],
    }
    (workspace / ".work-bundle/project.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    bindings = {}
    for name in names:
        member = workspace / name
        member.mkdir()
        bindings[name] = {
            "project_root": str(member), "checkout_kind": "managed-worktree",
            "git_common_dir": str(workspace / ".work-bundle/git" / f"{name}.git"),
            "observed_at": "2026-09-23T00:00:00Z", "observed_branch": "main",
            "observed_head": "0" * 40,
        }
    registry = {"device_bindings": {"wb-test": {
        "slug": "test", "workspace_root": str(workspace), "repositories": bindings,
    }}}
    monkeypatch.setattr(core._infrastructure, "load_project_registry", lambda **_kwargs: registry)
    monkeypatch.setattr(execution_context, "resolve_workspace_root", core.resolve_workspace_root)


@pytest.mark.parametrize("members", [["repo-main"], ["repo-main", "repo-other"]])
def test_v4_static_admission_and_candidate_keep_each_member_scope(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, members: list[str],
) -> None:
    plan, phase, task = _create_tree(workspace, tmp_path)
    _bind_v4_members(workspace, monkeypatch, members)
    first = yaml.safe_load(task.read_text())
    first["source_files"] = ["repo-main/scripts/read.py"]
    first["target_files"] = ["repo-main/scripts/write.py"]
    write_artifact(CATALOG, "task", {"workspace_root": workspace}, first, state="active",
                   bindings={"plan": "plan-stage4", "phase": "phase-stage4"})
    if len(members) > 1:
        phase_data = yaml.safe_load(phase.read_text())
        phase_data["task_index"].append({"id": "task-other", "order": 2})
        write_artifact(CATALOG, "phase", {"workspace_root": workspace}, phase_data,
                       state="active", bindings={"plan": "plan-stage4"})
        other = dict(first)
        other.update(id="task-other", name="Other member", order=2,
                     source_files=["repo-main/scripts/shared.py"],
                     target_files=["repo-other/scripts/write.py"])
        other["evidence_capability"] = yaml.safe_load(yaml.safe_dump(first["evidence_capability"]))
        other["evidence_capability"]["invariants"][0]["task_id"] = "task-other"
        write_artifact(CATALOG, "task", {"workspace_root": workspace}, other, state="active",
                       bindings={"plan": "plan-stage4", "phase": "phase-stage4"})

    admitted = execution_context.static_plan_task_admission(workspace, plan)
    scopes = {item["task_id"]: item["files"] for item in admitted}
    assert scopes["task-stage4"] == {
        "read": ["repo-main/scripts/read.py"], "write": ["repo-main/scripts/write.py"], "forbidden": [],
    }
    if len(members) > 1:
        assert scopes["task-other"] == {
            "read": ["repo-main/scripts/shared.py"], "write": ["repo-other/scripts/write.py"], "forbidden": [],
        }
    candidate = dict(first, target_files=["repo-main/scripts/amended.py"])
    _, compiled = execution_context.compile_task_candidate(workspace, task, candidate)
    assert compiled["task_brief"]["files"]["write"] == ["repo-main/scripts/amended.py"]
    assert yaml.safe_load(task.read_text())["target_files"] == ["repo-main/scripts/write.py"]


def test_static_plan_admission_compiles_canonical_yaml_task(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, task = _create_tree(workspace, tmp_path)

    admitted = execution_context.static_plan_task_admission(workspace, plan)

    assert [item["task_id"] for item in admitted] == ["task-stage4"]
    assert admitted[0]["source_ids"] == ["REQ-001A", "AC-001"]
    assert task.suffixes == [".task", ".yaml"]
    assert not (workspace / ".work-bundle/runtime").exists()


def test_compiler_uses_task_source_obligations_not_specification_body_syntax(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_tree(workspace, tmp_path)
    specification = (
        workspace
        / ".work-bundle/orchestration/spec/active/spec-stage4.spec.md"
    )
    text = specification.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4)
    assert end > 0
    specification.write_text(
        text[: end + 5]
        + "# Prose only\n\nThe body deliberately contains no source-ID headings, bullets, or tables.\n",
        encoding="utf-8",
    )

    admitted = execution_context.static_plan_task_admission(workspace, plan)

    assert admitted[0]["requirements"] == [
        "REQ-001A: Preserve exact specification authority in the compiled task.",
        "AC-001: The canonical YAML task compiles from structured plan authority.",
    ]


def test_static_plan_admission_rejects_unknown_dependency(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, task = _create_tree(workspace, tmp_path)
    data = yaml.safe_load(task.read_text())
    data["depends_on"] = ["task-missing"]
    write_artifact(
        CATALOG, "task", {"workspace_root": workspace}, data, state="active",
        bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )

    with pytest.raises(SystemExit, match="static-admission-blocked.*task-missing"):
        execution_context.static_plan_task_admission(workspace, plan)


def test_static_plan_admission_ignores_obsolete_markdown_candidate(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_tree(workspace, tmp_path)
    legacy = plan.parent / "plan-stage4/phase-stage4/task-shadow.md"
    legacy.write_text("---\nid: task-shadow\nplan_id: plan-stage4\nphase_id: phase-stage4\n---\n")

    admitted = execution_context.static_plan_task_admission(workspace, plan)

    assert [item["task_id"] for item in admitted] == ["task-stage4"]


def test_task_index_is_derived_and_rebuilt_before_compilation(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_tree(workspace, tmp_path)
    index = workspace / ".work-bundle/orchestration/plan/task-index.jsonl"
    row = json.loads(index.read_text())
    row["phase_id"] = "phase-wrong"
    index.write_text(json.dumps(row) + "\n")

    admitted = execution_context.static_plan_task_admission(workspace, plan)

    assert admitted[0]["task_id"] == "task-stage4"


def test_static_plan_admission_rejects_scope_escape(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, task = _create_tree(workspace, tmp_path)
    data = yaml.safe_load(task.read_text())
    data["target_files"] = ["../outside.py"]
    write_artifact(
        CATALOG, "task", {"workspace_root": workspace}, data, state="active",
        bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )

    with pytest.raises(SystemExit, match="static-admission-blocked.*write scope"):
        execution_context.static_plan_task_admission(workspace, plan)


def test_static_plan_admission_rejects_task_dependency_cycle(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, phase, task = _create_tree(workspace, tmp_path)
    phase_data = yaml.safe_load(phase.read_text())
    phase_data["task_index"] = [
        {"id": "task-stage4", "order": 1},
        {"id": "task-stage4-next", "order": 2},
    ]
    write_artifact(
        CATALOG, "phase", {"workspace_root": workspace}, phase_data, state="active",
        bindings={"plan": "plan-stage4"},
    )
    first = yaml.safe_load(task.read_text())
    first["depends_on"] = ["task-stage4-next"]
    write_artifact(
        CATALOG, "task", {"workspace_root": workspace}, first, state="active",
        bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )
    second = yaml.safe_load(task.read_text())
    second.update({"id": "task-stage4-next", "name": "Next task", "order": 2})
    second["depends_on"] = ["task-stage4"]
    second["evidence_capability"]["invariants"][0]["task_id"] = "task-stage4-next"
    write_artifact(
        CATALOG, "task", {"workspace_root": workspace}, second, state="active",
        bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )

    with pytest.raises(SystemExit, match="static-admission-blocked: dependency cycle"):
        execution_context.static_plan_task_admission(workspace, plan)
