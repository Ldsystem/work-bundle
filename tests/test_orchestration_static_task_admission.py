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
import plans  # noqa: E402
from artifact_store import read_artifact, write_artifact  # noqa: E402
from test_orchestration_plans import CATALOG, _args, _write_yaml, _create_tree as _create_snapshot_tree, workspace  # noqa: E402


def _create_tree(workspace: Path, tmp_path: Path) -> tuple[Path, Path, Path]:
    plan, phase_path, task = _create_snapshot_tree(workspace, tmp_path)
    phase = yaml.safe_load(phase_path.read_text())
    phase["delivery"] = {
        "mode": "final", "task_id": None, "snapshot": None,
        "bridges": {}, "test_catalog": [],
    }
    write_artifact(CATALOG, "phase", {"workspace_root": workspace}, phase, state="active",
                   bindings={"plan": "plan-stage4"})
    return plan, phase_path, task


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


def _clone_task(
    task: dict[str, object], *, task_id: str, phase_id: str, order: int,
    validation_id: str, depends_on: list[str],
) -> dict[str, object]:
    cloned = yaml.safe_load(yaml.safe_dump(task))
    cloned.update(
        id=task_id, phase_id=phase_id, name=task_id, order=order,
        depends_on=depends_on, target_files=[f"scripts/{task_id}.py"],
    )
    cloned["validation"][0]["id"] = validation_id
    cloned["evidence_capability"]["invariants"][0].update(
        task_id=task_id, oracle=validation_id, evidence_ids=[validation_id]
    )
    return cloned


def _store_multiphase_delivery_tree(
    workspace: Path, tmp_path: Path,
) -> tuple[Path, dict[str, Path]]:
    plan_path, phase_path, task_path = _create_snapshot_tree(workspace, tmp_path)
    anchors = {"workspace_root": workspace}
    plan = read_artifact(
        CATALOG, "root-plan", anchors, identity="plan-stage4", state="active",
        bindings={"source_spec": "spec-stage4"},
    )["data"]
    plan["phase_index"] = [
        {"id": "phase-stage4", "order": 1},
        {"id": "phase-final", "order": 2},
    ]
    write_artifact(
        CATALOG, "root-plan", anchors, plan, state="active",
        bindings={"source_spec": "spec-stage4"},
    )

    first = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    converge = _clone_task(
        first, task_id="task-converge", phase_id="phase-stage4", order=2,
        validation_id="VAL-CONVERGE", depends_on=["task-stage4"],
    )
    final_task = _clone_task(
        first, task_id="task-final", phase_id="phase-final", order=1,
        validation_id="VAL-FINAL", depends_on=["task-converge"],
    )
    phase = yaml.safe_load(phase_path.read_text(encoding="utf-8"))
    phase["task_index"] = [
        {"id": "task-stage4", "order": 1},
        {"id": "task-converge", "order": 2},
    ]
    phase["delivery"]["task_id"] = "task-converge"
    phase["delivery"]["test_catalog"].append(
        {
            "task_id": "task-converge", "disposition": "executable",
            "test_id": "VAL-CONVERGE", "purpose": "Exercise convergence.",
        }
    )
    write_artifact(
        CATALOG, "phase", anchors, phase, state="active",
        bindings={"plan": "plan-stage4"},
    )
    write_artifact(
        CATALOG, "task", anchors, converge, state="active",
        bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )

    final_phase = yaml.safe_load(yaml.safe_dump(phase))
    final_phase.update(
        id="phase-final", name="Final phase", order=2,
        depends_on=["phase-stage4"],
        task_index=[{"id": "task-final", "order": 1}],
        delivery={
            "mode": "final", "task_id": None, "snapshot": None,
            "bridges": {}, "test_catalog": [],
        },
    )
    write_artifact(
        CATALOG, "phase", anchors, final_phase, state="active",
        bindings={"plan": "plan-stage4"},
    )
    write_artifact(
        CATALOG, "task", anchors, final_task, state="active",
        bindings={"plan": "plan-stage4", "phase": "phase-final"},
    )
    return plan_path, {
        "phase": phase_path,
        "first": task_path,
        "converge": phase_path.parent / "phase-stage4/task-converge.task.yaml",
        "final_phase": phase_path.parent / "phase-final.phase.yaml",
        "final": phase_path.parent / "phase-final/task-final.task.yaml",
    }


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
        phase_data["delivery"] = {
            "mode": "final", "task_id": None, "snapshot": None,
            "bridges": {}, "test_catalog": [],
        }
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


def test_static_delivery_admission_accepts_transitive_phase_coverage_and_progression(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _paths = _store_multiphase_delivery_tree(workspace, tmp_path)

    admitted = execution_context.static_plan_task_admission(workspace, plan)

    assert {item["task_id"] for item in admitted} == {
        "task-stage4", "task-converge", "task-final",
    }


def test_static_delivery_admission_rejects_single_final_phase_snapshot_mode(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_snapshot_tree(workspace, tmp_path)

    with pytest.raises(SystemExit, match="final phase delivery mode must be final"):
        execution_context.static_plan_task_admission(workspace, plan)


@pytest.mark.parametrize("case", ["final-mode", "progression", "missing-phase"])
def test_plan_qualification_refuses_invalid_complete_graph_before_mutation(
    workspace: Path, tmp_path: Path, case: str,
) -> None:
    if case == "final-mode":
        _create_snapshot_tree(workspace, tmp_path)
        message = "final phase delivery mode"
    else:
        plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
        if case == "progression":
            task = yaml.safe_load(paths["final"].read_text())
            task["depends_on"] = []
            write_artifact(CATALOG, "task", {"workspace_root": workspace}, task,
                           state="active", bindings={"plan": "plan-stage4", "phase": "phase-final"})
            message = "entry task.*upstream delivery"
        else:
            data = yaml.safe_load(plan.read_text())
            data["phase_index"].append({"id": "phase-missing", "order": 3})
            write_artifact(CATALOG, "root-plan", {"workspace_root": workspace}, data,
                           state="active", bindings={"source_spec": "spec-stage4"})
            message = "phase_index does not match"
    store = workspace / ".work-bundle/orchestration"
    before = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}
    with pytest.raises(SystemExit, match=message):
        plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="verified"))
    assert {path: path.read_bytes() for path in store.rglob("*") if path.is_file()} == before


def test_plan_qualification_accepts_valid_final_delivery_graph(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="verified"))
    assert yaml.safe_load(plan.read_text())["status"] == "verified"


def test_new_verified_plan_refuses_missing_canonical_graph_before_write(
    workspace: Path, tmp_path: Path,
) -> None:
    from test_orchestration_plans import _plan_semantics

    content = _write_yaml(tmp_path / "new-plan.yaml", _plan_semantics())
    store = workspace / ".work-bundle/orchestration"
    before = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}
    with pytest.raises(SystemExit, match="draft.*qualif"):
        plans.cmd_write_plan(_args(workspace, content_file=str(content), status="verified"))
    assert {path: path.read_bytes() for path in store.rglob("*") if path.is_file()} == before


def test_static_delivery_admission_preserves_legacy_phase_read_continuity(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, phase_path, _task = _create_tree(workspace, tmp_path)
    phase = yaml.safe_load(phase_path.read_text())
    phase["schema_version"] = 1
    phase.pop("delivery")
    write_artifact(CATALOG, "phase", {"workspace_root": workspace}, phase, state="active",
                   bindings={"plan": "plan-stage4"})
    before = phase_path.read_bytes()

    assert len(execution_context.static_plan_task_admission(workspace, plan)) == 1
    assert phase_path.read_bytes() == before


@pytest.mark.parametrize("case", ["coverage", "progression", "catalog-reference"])
def test_complete_delivery_candidate_refuses_invalid_writes_without_changing_store(
    workspace: Path, tmp_path: Path, case: str,
) -> None:
    _plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    plans.index_plans(_args(workspace))
    store = workspace / ".work-bundle/orchestration/plan"
    before = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}
    if case in {"coverage", "catalog-reference"}:
        candidate = yaml.safe_load(paths["phase"].read_text())
        if case == "coverage":
            candidate["delivery"]["task_id"] = "task-stage4"
        else:
            candidate["delivery"]["test_catalog"][0]["test_id"] = "VAL-UNKNOWN"
        semantic = {key: value for key, value in candidate.items() if key not in plans.PHASE_STRUCTURAL_INPUT_FIELDS}
        content = _write_yaml(tmp_path / "invalid-phase-write.yaml", semantic)
        operation = plans.cmd_write_phase
        args = _args(workspace, plan_id="plan-stage4", phase_id="phase-stage4",
                     title=candidate["name"], content_file=str(content), status="planned")
        message = "transitively cover" if case == "coverage" else "unknown process validation"
    else:
        candidate = yaml.safe_load(paths["final"].read_text())
        candidate["depends_on"] = []
        semantic = {key: value for key, value in candidate.items() if key not in plans.TASK_STRUCTURAL_INPUT_FIELDS}
        content = _write_yaml(tmp_path / "invalid-task-write.yaml", semantic)
        operation = plans.cmd_write_task
        args = _args(workspace, plan_id="plan-stage4", phase_id="phase-final", task_id="task-final",
                     title=candidate["name"], content_file=str(content), status="planned")
        message = "entry task.*upstream delivery"

    with pytest.raises(SystemExit, match=message):
        operation(args)

    assert {path: path.read_bytes() for path in store.rglob("*") if path.is_file()} == before


def test_static_delivery_coverage_accepts_indirect_predecessors(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    first = yaml.safe_load(paths["first"].read_text())
    middle = _clone_task(first, task_id="task-middle", phase_id="phase-stage4", order=3,
                         validation_id="VAL-MIDDLE", depends_on=["task-stage4"])
    phase = yaml.safe_load(paths["phase"].read_text())
    phase["task_index"].append({"id": "task-middle", "order": 3})
    phase["delivery"]["test_catalog"].append({
        "task_id": "task-middle", "disposition": "executable",
        "test_id": "VAL-MIDDLE", "purpose": "Exercise the indirect dependency.",
    })
    converge = yaml.safe_load(paths["converge"].read_text())
    converge["depends_on"] = ["task-middle"]
    for family, value, bindings in [
        ("phase", phase, {"plan": "plan-stage4"}),
        ("task", middle, {"plan": "plan-stage4", "phase": "phase-stage4"}),
        ("task", converge, {"plan": "plan-stage4", "phase": "phase-stage4"}),
    ]:
        write_artifact(CATALOG, family, {"workspace_root": workspace}, value, state="active", bindings=bindings)

    assert len(execution_context.static_plan_task_admission(workspace, plan)) == 4


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("nonmember", "delivery task.*member"),
        ("incomplete", "transitively cover"),
        ("mode", "final phase.*mode|non-final phase.*mode"),
        ("non-final-mode", "non-final phase.*mode"),
        ("progression", "entry task.*upstream delivery"),
    ],
)
def test_static_delivery_admission_rejects_invalid_phase_graph(
    workspace: Path, tmp_path: Path, case: str, message: str,
) -> None:
    plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    anchors = {"workspace_root": workspace}
    if case in {"nonmember", "incomplete"}:
        phase = yaml.safe_load(paths["phase"].read_text(encoding="utf-8"))
        if case == "nonmember":
            phase["delivery"]["task_id"] = "task-final"
        else:
            phase["delivery"]["task_id"] = "task-stage4"
        write_artifact(
            CATALOG, "phase", anchors, phase, state="active",
            bindings={"plan": "plan-stage4"},
        )
    elif case == "non-final-mode":
        phase = yaml.safe_load(paths["phase"].read_text())
        phase["delivery"] = {
            "mode": "final", "task_id": None, "snapshot": None,
            "bridges": {}, "test_catalog": [],
        }
        write_artifact(CATALOG, "phase", anchors, phase, state="active", bindings={"plan": "plan-stage4"})
    elif case == "mode":
        final_phase = yaml.safe_load(paths["final_phase"].read_text(encoding="utf-8"))
        first_phase = yaml.safe_load(paths["phase"].read_text(encoding="utf-8"))
        final_phase["delivery"] = first_phase["delivery"]
        final_phase["delivery"]["task_id"] = "task-final"
        final_phase["delivery"]["test_catalog"] = [
            {
                "task_id": "task-final", "disposition": "executable",
                "test_id": "VAL-FINAL", "purpose": "Exercise final task.",
            }
        ]
        write_artifact(
            CATALOG, "phase", anchors, final_phase, state="active",
            bindings={"plan": "plan-stage4"},
        )
    else:
        final_task = yaml.safe_load(paths["final"].read_text(encoding="utf-8"))
        final_task["depends_on"] = []
        write_artifact(
            CATALOG, "task", anchors, final_task, state="active",
            bindings={"plan": "plan-stage4", "phase": "phase-final"},
        )

    with pytest.raises(SystemExit, match=message):
        execution_context.static_plan_task_admission(workspace, plan)


def test_static_catalog_accepts_reasoned_not_applicable_without_semantic_inference(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    phase = yaml.safe_load(paths["phase"].read_text())
    phase["delivery"]["test_catalog"][0] = {
        "task_id": "task-stage4", "disposition": "not_applicable",
        "reason": "Controller assesses the meaningful validation allocation.",
    }
    write_artifact(CATALOG, "phase", {"workspace_root": workspace}, phase, state="active",
                   bindings={"plan": "plan-stage4"})

    admitted = execution_context.static_plan_task_admission(workspace, plan)

    assert len(admitted) == 3


@pytest.mark.parametrize("repository_id", ["work-bundle-main", "unknown-member"])
def test_static_catalog_process_binds_declared_v4_repository(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repository_id: str,
) -> None:
    plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    for key, phase_id in [("first", "phase-stage4"), ("converge", "phase-stage4"), ("final", "phase-final")]:
        task = yaml.safe_load(paths[key].read_text())
        task["source_files"] = ["work-bundle-main/" + path for path in task["source_files"]]
        task["target_files"] = ["work-bundle-main/" + path for path in task["target_files"]]
        if key == "first":
            task["validation"][0]["process"]["repository_id"] = repository_id
        write_artifact(CATALOG, "task", {"workspace_root": workspace}, task, state="active",
                       bindings={"plan": "plan-stage4", "phase": phase_id})
    _bind_v4_members(workspace, monkeypatch, ["work-bundle-main"])

    if repository_id == "work-bundle-main":
        assert len(execution_context.static_plan_task_admission(workspace, plan)) == 3
    else:
        with pytest.raises(SystemExit, match="unknown repository.*unknown-member"):
            execution_context.static_plan_task_admission(workspace, plan)
        candidate = yaml.safe_load(paths["first"].read_text())
        semantic = {key: value for key, value in candidate.items() if key not in plans.TASK_STRUCTURAL_INPUT_FIELDS}
        content = _write_yaml(tmp_path / "unknown-repository-task.yaml", semantic)
        before = paths["first"].read_bytes()
        with pytest.raises(SystemExit, match="unknown repository.*unknown-member"):
            plans.cmd_write_task(_args(workspace, plan_id="plan-stage4", phase_id="phase-stage4",
                                      task_id="task-stage4", title=candidate["name"],
                                      content_file=str(content), status="planned"))
        assert paths["first"].read_bytes() == before


@pytest.mark.parametrize("case", ["legacy-command", "unsafe-cwd", "missing-timeout", "duplicate-validation-id"])
def test_static_catalog_rejects_unsafe_or_ambiguous_process_reference(
    workspace: Path, tmp_path: Path, case: str,
) -> None:
    plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    task = yaml.safe_load(paths["first"].read_text())
    task["schema_version"] = 2
    task["handoff_contract"] = "executor-result-v1"
    validation = task["validation"][0]
    if case == "legacy-command":
        validation.pop("process")
        validation["command"] = "pytest -q"
    elif case == "unsafe-cwd":
        validation["process"]["working_directory"] = "../escape"
    elif case == "missing-timeout":
        validation["process"].pop("timeout_seconds")
    else:
        task["validation"].append(yaml.safe_load(yaml.safe_dump(validation)))
    write_artifact(CATALOG, "task", {"workspace_root": workspace}, task, state="active",
                   bindings={"plan": "plan-stage4", "phase": "phase-stage4"})
    before = paths["first"].read_bytes()

    with pytest.raises(SystemExit):
        execution_context.static_plan_task_admission(workspace, plan)

    assert paths["first"].read_bytes() == before
    assert not (workspace / ".work-bundle/runtime").exists()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown-test", "unknown process validation"),
        ("unknown-task", "unknown task"),
        ("duplicate-test", "duplicate executable test ID"),
        ("missing-accounting", "account for every task"),
        ("mixed-accounting", "mixes executable and not_applicable"),
        ("duplicate-not-applicable", "multiple not_applicable"),
        ("blank-reason", "not_applicable reason is empty"),
        ("inspection", "must reference a process validation"),
    ],
)
def test_static_catalog_accounting_rejects_invalid_rows(
    workspace: Path, tmp_path: Path, case: str, message: str,
) -> None:
    plan, paths = _store_multiphase_delivery_tree(workspace, tmp_path)
    anchors = {"workspace_root": workspace}
    phase = yaml.safe_load(paths["phase"].read_text(encoding="utf-8"))
    catalog = phase["delivery"]["test_catalog"]
    if case == "unknown-test":
        catalog[0]["test_id"] = "VAL-UNKNOWN"
    elif case == "unknown-task":
        catalog[0]["task_id"] = "task-unknown"
    elif case == "blank-reason":
        catalog[0] = {"task_id": "task-stage4", "disposition": "not_applicable", "reason": "   "}
    elif case == "duplicate-test":
        catalog[1]["test_id"] = "VAL-001"
    elif case == "missing-accounting":
        phase["delivery"]["test_catalog"] = catalog[:1]
    elif case in {"mixed-accounting", "duplicate-not-applicable"}:
        if case == "duplicate-not-applicable":
            phase["delivery"]["test_catalog"] = [
                {"task_id": "task-stage4", "disposition": "not_applicable", "reason": "No run."},
                {"task_id": "task-stage4", "disposition": "not_applicable", "reason": "Still none."},
                catalog[1],
            ]
        else:
            catalog.insert(
                1,
                {"task_id": "task-stage4", "disposition": "not_applicable", "reason": "No run."},
            )
    else:
        task = yaml.safe_load(paths["first"].read_text(encoding="utf-8"))
        task["validation"] = [
            {
                "id": "VAL-001", "kind": "inspection",
                "mechanism": "Inspect generated bytes.", "invariant_ids": ["INV-001"],
                "capability_reason": "Direct inspection observes the generated bytes.",
            }
        ]
        write_artifact(
            CATALOG, "task", anchors, task, state="active",
            bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
        )
    write_artifact(
        CATALOG, "phase", anchors, phase, state="active",
        bindings={"plan": "plan-stage4"},
    )

    with pytest.raises(SystemExit, match=message):
        execution_context.static_plan_task_admission(workspace, plan)
