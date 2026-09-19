from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import review_runtime  # noqa: E402
from artifact_store import transition_artifact, write_artifact  # noqa: E402
from test_orchestration_plans import CATALOG, _create_tree, workspace  # noqa: E402


def _rewrite(path: Path, family: str, root: Path, mutate) -> None:
    data = yaml.safe_load(path.read_text())
    mutate(data)
    bindings = {"source_spec": data["source_spec_id"]} if family == "root-plan" else {"plan": data["plan_id"]}
    if family == "task":
        bindings["phase"] = data["phase_id"]
    write_artifact(CATALOG, family, {"workspace_root": root}, data, state="active", bindings=bindings)


def test_qualification_and_dates_do_not_change_identity(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_tree(workspace, tmp_path)
    original = deepcopy(review_runtime.plan_review_identity(workspace, plan))
    _rewrite(
        plan, "root-plan", workspace,
        lambda data: data.update(status="verified", last_updated="2099-02-02"),
    )
    assert review_runtime.plan_review_identity(workspace, plan) == original


def test_every_substantive_yaml_field_changes_plan_tree_identity(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, task = _create_tree(workspace, tmp_path)
    original = review_runtime.plan_review_identity(workspace, plan)
    _rewrite(
        task, "task", workspace,
        lambda data: data["steps"].append("Run the focused regression test."),
    )

    assert review_runtime.plan_review_identity(workspace, plan) != original


def test_noncanonical_yaml_candidate_does_not_change_plan_tree_identity(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_tree(workspace, tmp_path)
    original = review_runtime.plan_review_identity(workspace, plan)
    stray = plan.parent / "stray.yaml"
    stray.write_text(
        yaml.safe_dump({"plan_id": "plan-stage4", "invented": "not canonical"}),
        encoding="utf-8",
    )

    assert review_runtime.plan_review_identity(workspace, plan) == original


def test_nested_acceptance_allocation_remains_substantive(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, task = _create_tree(workspace, tmp_path)
    original = review_runtime.plan_review_identity(workspace, plan)
    _rewrite(
        task, "task", workspace,
        lambda data: data["acceptance_review"].update(required=True, reviewer_independent=True),
    )

    assert review_runtime.plan_review_identity(workspace, plan) != original


def test_active_to_archived_tree_transition_preserves_semantic_identity(
    workspace: Path, tmp_path: Path,
) -> None:
    plan, _phase, _task = _create_tree(workspace, tmp_path)
    original = review_runtime.plan_review_identity(workspace, plan)
    anchors = {"workspace_root": workspace}
    transition_artifact(
        CATALOG, "task", anchors, identity="task-stage4", current_state="active",
        target_state="archived", bindings={"plan": "plan-stage4", "phase": "phase-stage4"},
    )
    transition_artifact(
        CATALOG, "phase", anchors, identity="phase-stage4", current_state="active",
        target_state="archived", bindings={"plan": "plan-stage4"},
    )
    transition_artifact(
        CATALOG, "root-plan", anchors, identity="plan-stage4", current_state="active",
        target_state="archived", bindings={"source_spec": "spec-stage4"},
    )
    archived = workspace / ".work-bundle/orchestration/plan/archived/plan-stage4.plan.yaml"

    assert review_runtime.plan_review_identity(workspace, archived) == original
