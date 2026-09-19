from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from artifact_store import family_policy, load_catalog, read_artifact  # noqa: E402
import plans  # noqa: E402
import specs  # noqa: E402
import bounded_closure  # noqa: E402


CATALOG = REPO_ROOT / "references/assets/orchestration/contract/artifact-family-catalog-v5.yaml"


def _args(root: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "workspace_root": str(root),
        "project_root": None,
        "id": "plan-stage4",
        "title": "Stage 4 plan",
        "purpose": "Create executable planning semantics",
        "component": "orchestration",
        "version": "1.0",
        "content_file": "",
        "status": "draft",
        "filename": None,
        "source_spec_id": "spec-stage4",
        "plan_id": None,
        "phase_id": None,
        "task_id": None,
        "kind": None,
        "handoff": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative in [
        ".work-bundle/orchestration/spec/active",
        ".work-bundle/orchestration/spec/archived",
        ".work-bundle/orchestration/plan/active",
        ".work-bundle/orchestration/plan/archived",
    ]:
        (tmp_path / relative).mkdir(parents=True)
    monkeypatch.setattr(bounded_closure, "resolve_working_workspace", lambda _root: None)
    for module in (plans, specs):
        monkeypatch.setattr(module, "resolve_workspace_root", lambda _args: tmp_path)
        if hasattr(module, "resolve_working_workspace"):
            monkeypatch.setattr(module, "resolve_working_workspace", lambda _root: None)
        monkeypatch.setattr(
            module,
            "orchestration_root",
            lambda _args: tmp_path / ".work-bundle/orchestration",
        )
        monkeypatch.setattr(module, "init_dirs", lambda _args: None)
        monkeypatch.setattr(
            module,
            "rel",
            lambda path, _args: Path(path).resolve().relative_to(tmp_path.resolve()).as_posix(),
        )
    spec_input = tmp_path / "spec-input.md"
    spec_input.write_text(
        "---\nproject: demo\nsource_knowledge: []\nrelated_handoffs: []\ntags: [orchestration]\n"
        "execution_workspace: {isolation: existing, profile: default, cleanup: manual}\n---\n"
        "# Specification\n\n- **REQ-001A:** Preserve the exact suffixed source identifier.\n"
        "- **AC-001:** Compile the canonical task.\n",
        encoding="utf-8",
    )
    specs.cmd_write_spec(
        argparse.Namespace(
            workspace_root=str(tmp_path), project_root=None, id="spec-stage4",
            title="Stage 4 source", purpose="Drive Stage 4", component="orchestration",
            version="1.0", content_file=str(spec_input), status="verified", filename=None,
        )
    )
    return tmp_path


def _write_yaml(path: Path, value: dict[str, object]) -> Path:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def _plan_semantics() -> dict[str, object]:
    return {
        "source_coverage": [
            {
                "source_id": "REQ-001A",
                "obligation_kind": "requirement",
                "phase_ids": ["phase-stage4"],
                "task_ids": ["task-stage4"],
                "validation_ids": ["VAL-001"],
            }
        ],
        "authority": {"decision_authority": ["none-relevant"]},
        "strategy": {"summary": "One coherent phase and task."},
        "phase_index": [{"id": "phase-stage4", "order": 1}],
        "dependency_graph": {"edges": []},
        "risks": [],
        "validation_strategy": [{"id": "VAL-001", "kind": "process"}],
        "completion_criteria": ["REQ-001A and AC-001 are validated."],
        "knowledge_base_update": {"action": "update"},
        "semantic_loop": {"result": "converged"},
        "execution_workspace": {"isolation": "existing", "profile": "default", "cleanup": "manual"},
    }


def _phase_semantics() -> dict[str, object]:
    return {
        "order": 1,
        "source_ids": ["REQ-001A", "AC-001"],
        "depends_on": [],
        "task_index": [{"id": "task-stage4", "order": 1}],
        "barriers": [],
        "validation": [{"id": "VAL-001", "kind": "process"}],
        "completion_criteria": ["The task compiles."],
        "allocated_rules": [],
        "allocated_skills": ["dev-test-driven-development"],
    }


def _task_semantics() -> dict[str, object]:
    return {
        "order": 1,
        "task_type": "implementation",
        "source_ids": ["REQ-001A", "AC-001"],
        "source_obligations": [
            {
                "source_id": "REQ-001A",
                "semantic": "Preserve exact specification authority in the compiled task.",
            },
            {
                "source_id": "AC-001",
                "semantic": "The canonical YAML task compiles from structured plan authority.",
            },
        ],
        "truth_basis": {
            "purpose": "Preserve exact specification authority.",
            "as_is_evidence": ["Current compiler consumes structured tasks."],
            "decision_authority": ["none-relevant"],
            "expected_delta": ["Canonical YAML task compiles."],
            "conflict_status": "clear",
        },
        "depends_on": [],
        "source_files": ["scripts/orchestration/execution_context.py"],
        "target_files": ["scripts/orchestration/execution_context.py"],
        "target_symbols": ["_task_context"],
        "interfaces": {"consumes": ["REQ-001A"], "produces": []},
        "steps": ["Adapt the canonical reader."],
        "validation": [
            {
                "id": "VAL-001", "kind": "process", "command": "pytest -q",
                "proves": ["AC-001"], "expected": "passed",
                "invariant_ids": ["INV-001"],
                "capability_reason": "The focused process check exercises compilation.",
            }
        ],
        "evidence_capability": {
            "result": "mapped",
            "reason": "The process check exercises compilation.",
            "invariants": [
                {
                    "id": "INV-001", "source_ids": ["AC-001"],
                    "invariant": "The canonical task compiles.", "boundary": "component",
                    "oracle": "VAL-001", "capability_reason": "The compiler is invoked directly.",
                    "freshness": "current_task_batch", "task_id": "task-stage4",
                    "evidence_ids": ["VAL-001"], "closure_result": "pending",
                }
            ],
        },
        "completion_criteria": ["The canonical task compiles."],
        "methodology": {"primary": "tdd", "required_skills": ["dev-test-driven-development"]},
        "executor_profile": {"capability": "judgment", "context_mode": "compiled-brief", "review_capability": "judgment"},
        "acceptance_review": {"required": False, "reviewer_independent": False, "verdict": "pending", "reviewed_head": "", "findings": []},
        "allocated_rules": [],
        "allocated_skills": ["dev-test-driven-development"],
        "handoff_contract": "executor-result-v1",
    }


def _create_tree(workspace: Path, tmp_path: Path) -> tuple[Path, Path, Path]:
    plan_input = _write_yaml(tmp_path / "plan.yaml", _plan_semantics())
    plans.cmd_write_plan(_args(workspace, content_file=str(plan_input)))
    phase_input = _write_yaml(tmp_path / "phase.yaml", _phase_semantics())
    plans.cmd_write_phase(
        _args(
            workspace, id=None, plan_id="plan-stage4", phase_id="phase-stage4",
            title="Stage 4 phase", content_file=str(phase_input), status="planned",
        )
    )
    task_input = _write_yaml(tmp_path / "task.yaml", _task_semantics())
    plans.cmd_write_task(
        _args(
            workspace, id=None, plan_id="plan-stage4", phase_id="phase-stage4",
            task_id="task-stage4", title="Stage 4 task", content_file=str(task_input),
            status="planned",
        )
    )
    root = workspace / ".work-bundle/orchestration/plan/active"
    return (
        root / "plan-stage4.plan.yaml",
        root / "plan-stage4/phase-stage4.phase.yaml",
        root / "plan-stage4/phase-stage4/task-stage4.task.yaml",
    )


def test_catalog_v5_registers_distinct_canonical_yaml_planning_families() -> None:
    assert load_catalog(CATALOG)["catalog_id"] == "artifact-family-catalog-v5"
    catalog = load_catalog(CATALOG)
    for family, suffix in (
        ("root-plan", ".plan.yaml"),
        ("phase", ".phase.yaml"),
        ("task", ".task.yaml"),
    ):
        policy = family_policy(catalog, family)
        assert policy["representation"] == "yaml"
        assert policy["locator"]["template"].endswith(suffix)
        assert policy["index"]["path"].endswith(f"{family}-index.jsonl")


def test_write_read_and_index_canonical_plan_tree(workspace: Path, tmp_path: Path) -> None:
    root_path, phase_path, task_path = _create_tree(workspace, tmp_path)
    assert root_path.is_file() and phase_path.is_file() and task_path.is_file()
    assert not list(root_path.parent.rglob("*.md"))

    rows = plans.index_plans(_args(workspace))
    assert [(row["artifact_type"], row["id"]) for row in rows] == [
        ("phase", "phase-stage4"),
        ("root-plan", "plan-stage4"),
        ("task", "task-stage4"),
    ]
    assert not (workspace / ".work-bundle/orchestration/plan/index.jsonl").exists()
    task = read_artifact(
        CATALOG, "task", {"workspace_root": workspace}, identity="task-stage4",
        state="active", bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )["data"]
    assert task["source_ids"] == ["REQ-001A", "AC-001"]


def test_structural_override_and_unverified_source_fail_before_mutation(
    workspace: Path, tmp_path: Path,
) -> None:
    bad = _plan_semantics()
    bad["id"] = "plan-evil"
    content = _write_yaml(tmp_path / "bad-plan.yaml", bad)
    with pytest.raises(SystemExit, match="structural field override"):
        plans.cmd_write_plan(_args(workspace, content_file=str(content)))
    assert not list((workspace / ".work-bundle/orchestration/plan/active").glob("*.plan.yaml"))

    specs.cmd_set_spec_status(
        argparse.Namespace(workspace_root=str(workspace), project_root=None, id="spec-stage4", status="draft")
    )
    content = _write_yaml(tmp_path / "plan.yaml", _plan_semantics())
    with pytest.raises(SystemExit, match="verified"):
        plans.cmd_write_plan(_args(workspace, content_file=str(content)))
    assert not list((workspace / ".work-bundle/orchestration/plan/active").glob("*.plan.yaml"))


def test_collision_and_wrong_parent_preserve_existing_bytes(workspace: Path, tmp_path: Path) -> None:
    root_path, phase_path, task_path = _create_tree(workspace, tmp_path)
    before = {path: path.read_bytes() for path in (root_path, phase_path, task_path)}
    with pytest.raises(SystemExit, match="collision"):
        plans.cmd_write_plan(_args(workspace, content_file=str(tmp_path / "plan.yaml")))
    wrong = _write_yaml(tmp_path / "wrong-task.yaml", _task_semantics())
    with pytest.raises(SystemExit, match="parent|phase|canonical"):
        plans.cmd_write_task(
            _args(
                workspace, plan_id="plan-stage4", phase_id="phase-missing",
                task_id="task-other", title="Wrong", content_file=str(wrong), status="planned",
            )
        )
    assert {path: path.read_bytes() for path in before} == before


def test_schema_invalid_task_fails_before_mutation(workspace: Path, tmp_path: Path) -> None:
    _root_path, _phase_path, task_path = _create_tree(workspace, tmp_path)
    task_path.unlink()
    plans.index_plans(_args(workspace))
    invalid = _task_semantics()
    invalid["validation"] = "pytest -q"
    content = _write_yaml(tmp_path / "invalid-task.yaml", invalid)

    with pytest.raises(SystemExit, match="schema validation failed"):
        plans.cmd_write_task(
            _args(
                workspace, id=None, plan_id="plan-stage4", phase_id="phase-stage4",
                task_id="task-stage4", title="Invalid task", content_file=str(content),
                status="planned",
            )
        )

    assert not task_path.exists()


def test_task_source_obligations_must_exactly_bind_source_ids_before_write(
    workspace: Path, tmp_path: Path,
) -> None:
    _root_path, _phase_path, task_path = _create_tree(workspace, tmp_path)
    task_path.unlink()
    plans.index_plans(_args(workspace))
    invalid = _task_semantics()
    invalid["source_obligations"] = invalid["source_obligations"][:1]
    content = _write_yaml(tmp_path / "invalid-obligations.yaml", invalid)

    with pytest.raises(SystemExit, match="exactly bind source_ids"):
        plans.cmd_write_task(
            _args(
                workspace, id=None, plan_id="plan-stage4", phase_id="phase-stage4",
                task_id="task-stage4", title="Invalid task", content_file=str(content),
                status="planned",
            )
        )

    assert not task_path.exists()


def test_status_is_planning_only_and_phase_task_execution_state_is_deferred(
    workspace: Path, tmp_path: Path,
) -> None:
    root_path, _phase_path, _task_path = _create_tree(workspace, tmp_path)
    plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="verified"))
    assert yaml.safe_load(root_path.read_text())["status"] == "verified"
    with pytest.raises(SystemExit, match="stage5-required"):
        plans.cmd_set_plan_status(
            _args(workspace, id="task-stage4", kind="task", plan_id="plan-stage4", status="Completed")
        )


def test_plan_qualification_transitions_are_monotonic(
    workspace: Path, tmp_path: Path,
) -> None:
    root_path, _phase_path, _task_path = _create_tree(workspace, tmp_path)
    plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="verified"))
    with pytest.raises(SystemExit, match="Invalid plan qualification transition"):
        plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="draft"))
    assert yaml.safe_load(root_path.read_text())["status"] == "verified"

    plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="superseded"))
    with pytest.raises(SystemExit, match="Invalid plan qualification transition"):
        plans.cmd_set_plan_status(_args(workspace, id="plan-stage4", status="verified"))
    assert yaml.safe_load(root_path.read_text())["status"] == "superseded"


def test_automatic_plan_ids_advance_without_collision(
    workspace: Path, tmp_path: Path,
) -> None:
    first = _write_yaml(tmp_path / "plan-one.yaml", _plan_semantics())
    second = _write_yaml(tmp_path / "plan-two.yaml", _plan_semantics())
    plans.cmd_write_plan(_args(workspace, id=None, content_file=str(first)))
    plans.cmd_write_plan(_args(workspace, id=None, content_file=str(second)))

    ids = [
        row["id"] for row in plans.index_plans(_args(workspace))
        if row["artifact_type"] == "root-plan"
    ]
    date = plans.now_date().replace("-", "")
    assert ids == [f"plan-{date}-001", f"plan-{date}-002"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["source_coverage"][0].update(phase_ids=[], task_ids=[]),
        lambda value: value.update(
            execution_workspace={
                "isolation": "invented", "profile": "default", "cleanup": "manual",
            }
        ),
    ],
)
def test_root_plan_schema_rejects_empty_coverage_and_unknown_workspace_policy(
    workspace: Path, tmp_path: Path, mutate,
) -> None:
    semantic = _plan_semantics()
    mutate(semantic)
    content = _write_yaml(tmp_path / "invalid-plan.yaml", semantic)
    with pytest.raises(SystemExit, match="schema validation failed"):
        plans.cmd_write_plan(_args(workspace, content_file=str(content)))
    assert not list((workspace / ".work-bundle/orchestration/plan/active").glob("*.plan.yaml"))


def test_per_family_indexes_are_deterministic_and_contain_no_fallback_fields(
    workspace: Path, tmp_path: Path,
) -> None:
    _create_tree(workspace, tmp_path)
    first = {
        path.name: path.read_bytes()
        for path in (workspace / ".work-bundle/orchestration/plan").glob("*-index.jsonl")
    }
    plans.index_plans(_args(workspace))
    second = {
        path.name: path.read_bytes()
        for path in (workspace / ".work-bundle/orchestration/plan").glob("*-index.jsonl")
    }
    assert first == second
    for payload in second.values():
        for line in payload.decode().splitlines():
            row = json.loads(line)
            assert row["id"]
            assert "path" not in row


def test_corrupt_derived_index_is_rebuilt_from_canonical_artifacts(
    workspace: Path, tmp_path: Path,
) -> None:
    root_path, _phase_path, _task_path = _create_tree(workspace, tmp_path)
    index = workspace / ".work-bundle/orchestration/plan/root-plan-index.jsonl"
    index.write_text("not-json\n", encoding="utf-8")

    rows = plans.index_plans(_args(workspace))

    assert root_path.is_file()
    assert any(row["id"] == "plan-stage4" for row in rows)
    assert json.loads(index.read_text().strip())["id"] == "plan-stage4"


def test_public_entrypoint_writes_and_lists_canonical_plan_tree(tmp_path: Path) -> None:
    workspace_id = "wb-stage4-entrypoint"
    control = tmp_path / ".work-bundle"
    control.mkdir()
    (control / "project.yaml").write_text(
        "metadata_version: 4\nauthority: canonical\n"
        f"workspace: {{id: {workspace_id}, slug: stage4, mode: single-repository}}\n"
        "control_plane: {schema_version: 1, repository: {remote: ''}, sync_policy: {mode: manual}}\n"
        "source_repositories:\n"
        "  - id: source\n    role: source\n    locator: {type: manual, value: fixture}\n"
        "    default_branch: main\n    workspace_binding: {type: root}\n"
        "    materialization: {required: true}\n    operation_policy: inherit\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    config = home / ".work-bundle"
    (config / "registry").mkdir(parents=True)
    (config / "bootstrap.yaml").write_text(
        "bootstrap_version: v1\nauthority: canonical\n"
        f"work_bundle_root: {REPO_ROOT}\n"
        'project_registry: "$work_bundle_config_root/registry/projects.yaml"\n'
        'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"\n',
        encoding="utf-8",
    )
    (config / "registry/projects.yaml").write_text(
        "registry_schema_version: 1\nprojects: []\ndevice_bindings:\n"
        f"  {workspace_id}:\n    slug: stage4\n    workspace_root: {tmp_path}\n"
        f"    control_plane_path: {control}\n    control_plane_remote: ''\n"
        "    observed_control_plane_head: ''\n    repositories:\n      source:\n"
        f"        project_root: {tmp_path}\n        checkout_kind: manual\n"
        "        observed_branch: ''\n        observed_head: ''\n"
        "        observed_at: '2099-01-01T00:00:00Z'\n        git_common_dir: ''\n",
        encoding="utf-8",
    )
    spec_input = tmp_path / "spec.md"
    spec_input.write_text(
        "---\nproject: demo\nsource_knowledge: []\nrelated_handoffs: []\ntags: [stage4]\n"
        "execution_workspace: {isolation: existing, profile: default, cleanup: manual}\n---\n"
        "# Specification\n\n- **REQ-001A:** Preserve the exact ID.\n",
        encoding="utf-8",
    )
    plan_input = _write_yaml(tmp_path / "plan.yaml", _plan_semantics())
    env = {**os.environ, "HOME": str(home)}
    entry = str(REPO_ROOT / "scripts/orch.py")
    create_spec = subprocess.run(
        [
            sys.executable, entry, "write-spec", "--workspace-root", str(tmp_path),
            "--id", "spec-stage4", "--title", "Source", "--purpose", "Stage 4",
            "--component", "orchestration", "--status", "verified",
            "--content-file", str(spec_input),
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert create_spec.returncode == 0, create_spec.stderr
    create_plan = subprocess.run(
        [
            sys.executable, entry, "write-plan", "--workspace-root", str(tmp_path),
            "--id", "plan-stage4", "--source-spec-id", "spec-stage4",
            "--title", "Plan", "--purpose", "Stage 4", "--component", "orchestration",
            "--content-file", str(plan_input),
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert create_plan.returncode == 0, create_plan.stderr
    phase_input = _write_yaml(tmp_path / "phase.yaml", _phase_semantics())
    create_phase = subprocess.run(
        [
            sys.executable, entry, "write-phase", "--workspace-root", str(tmp_path),
            "--plan-id", "plan-stage4", "--phase-id", "phase-stage4",
            "--title", "Phase", "--content-file", str(phase_input),
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert create_phase.returncode == 0, create_phase.stderr
    task_input = _write_yaml(tmp_path / "task.yaml", _task_semantics())
    create_task = subprocess.run(
        [
            sys.executable, entry, "write-task", "--workspace-root", str(tmp_path),
            "--plan-id", "plan-stage4", "--phase-id", "phase-stage4",
            "--task-id", "task-stage4", "--title", "Task",
            "--content-file", str(task_input),
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert create_task.returncode == 0, create_task.stderr
    listed = subprocess.run(
        [sys.executable, entry, "list-plans", "--workspace-root", str(tmp_path)],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert listed.returncode == 0, listed.stderr
    rows = [json.loads(line) for line in listed.stdout.strip().splitlines()]
    assert [(row["artifact_type"], row["id"]) for row in rows] == [
        ("phase", "phase-stage4"),
        ("root-plan", "plan-stage4"),
        ("task", "task-stage4"),
    ]
    assert {row["path"] for row in rows} == {
        ".work-bundle/orchestration/plan/active/plan-stage4.plan.yaml",
        ".work-bundle/orchestration/plan/active/plan-stage4/phase-stage4.phase.yaml",
        ".work-bundle/orchestration/plan/active/plan-stage4/phase-stage4/task-stage4.task.yaml",
    }
    doctor = subprocess.run(
        [sys.executable, entry, "doctor", "--workspace-root", str(tmp_path)],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert "invalid current planning families" not in doctor.stdout + doctor.stderr
