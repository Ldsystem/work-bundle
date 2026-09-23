from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from artifact_store import family_policy, load_catalog, read_artifact, write_artifact  # noqa: E402
import dispatcher  # noqa: E402
import artifact_store  # noqa: E402
import execution_context  # noqa: E402
import handoffs  # noqa: E402
import plans  # noqa: E402
import review_identity  # noqa: E402
import review_runtime  # noqa: E402


CATALOG = REPO_ROOT / "references/assets/orchestration/contract/artifact-family-catalog-v6.yaml"


def _args(root: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "workspace_root": str(root),
        "project_root": None,
        "id": None,
        "plan_id": None,
        "phase_id": None,
        "task_id": None,
        "state": None,
        "current_state": None,
        "target_state": None,
        "scope": None,
        "content_file": None,
        "source_root": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".work-bundle/orchestration").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "stage5@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Stage 5"], check=True)
    source = tmp_path / "src/current.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('committed')\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".work-bundle/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/current.py", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    monkeypatch.setattr(handoffs, "resolve_workspace_root", lambda _args: tmp_path)
    monkeypatch.setattr(
        review_runtime, "resolve_workspace_root", lambda _args: tmp_path, raising=False
    )
    monkeypatch.setattr(plans, "resolve_workspace_root", lambda _args: tmp_path)
    return tmp_path


def _write_yaml(tmp_path: Path, name: str, data: dict[str, object], *, flow: bool = False) -> Path:
    path = tmp_path / name
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=flow), encoding="utf-8"
    )
    return path


def _executor_semantics() -> dict[str, object]:
    return {
        "result_state": "implemented",
        "summary": "Implemented the bounded task.",
        "changes": [{"path": "src/current.py", "summary": "Added current behavior."}],
        "validation_observations": [
            {"id": "VAL-001", "command": "pytest -q", "result": "passed", "summary": "Focused test passed."}
        ],
        "unresolved_product_blockers": [],
        "task_fit": {"status": "complete", "summary": "The planned task is implemented."},
        "repository_observations": {"repository_id": "source", "baseline": "abc123", "dirty": True},
        "codegraph_observations": {"status": "no-index", "summary": "Repository is not indexed."},
        "delegation": {"agent_id": "worker-1", "role": "implementor"},
        "knowledge_disposition": {"action": "update", "reason": "Stable boundary changed."},
    }


def _candidate(root: Path, *, kind: str = "worktree") -> dict[str, object]:
    base = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    return execution_context.build_implementation_review_candidate(
        source_root=root, kind=kind, base_commit=base, changed_paths=["src/current.py"]
    )


def _review_semantics(
    candidate: dict[str, object],
    *,
    authority_identity: dict[str, str] | None = None,
    verdict: str = "accept",
) -> dict[str, object]:
    return {
        "scope": "task",
        "specification_id": "spec-stage5",
        "authority_identity": authority_identity or {"id": "task-stage5", "sha256": "1" * 64},
        "target": candidate,
        "implementor_agent_id": "worker-1",
        "reviewer": {"agent_id": "reviewer-1"},
        "reviewed_obligations": [
            {"source_id": "REQ-001", "status": "satisfied", "summary": "Source and tests cover the obligation."}
        ],
        "focused_observations": [
            {"id": "VAL-001", "result": "passed", "summary": "Focused behavior passed."}
        ],
        "verdict": verdict,
        "findings": [],
    }


def _write_stage5_plan_tree(
    workspace: Path, *, review_required: bool = True
) -> dict[str, str]:
    anchors = {"workspace_root": workspace}
    today = "2026-09-20"
    specification = {
        "artifact_type": "specification", "schema_version": 1, "id": "spec-stage5",
        "title": "Stage 5", "project": "test", "status": "verified",
        "date_created": today, "last_updated": today,
        "purpose": "Verify finalization", "component": "orchestration", "version": "1",
        "source_knowledge": [], "related_handoffs": [], "tags": ["orchestration"],
        "execution_workspace": {"isolation": "existing", "profile": "test", "cleanup": "manual"},
    }
    write_artifact(
        CATALOG, "specification", anchors, specification, state="active",
        body=(
            "# Stage 5\n\n"
            "- **DEC-001:** Use the direct implementation-review authority model globally.\n"
            "- **DEC-090:** Use an unrelated optional policy.\n"
            "- **REQ-009:** Complete Stage 5 finalization.\n"
            "- **REQ-010:** Implement peer behavior.\n"
        ),
    )
    plan = {
        "artifact_type": "root-plan", "schema_version": 1, "id": "plan-stage5",
        "goal": "Finish Stage 5", "purpose": "Verify finalization", "component": "orchestration",
        "version": "1", "source_spec_id": "spec-stage5", "status": "verified",
        "date_created": today, "last_updated": today,
        "source_coverage": [{"source_id": "REQ-009", "obligation_kind": "requirement", "task_ids": ["task-stage5"]}],
        "authority": {
            "spec": "spec-stage5", "decision_ids": ["DEC-001"],
            "aliases": {
                "DEC-001": "Use the direct implementation-review authority model globally.",
                "DEC-090": "Use an unrelated optional policy.",
            },
        },
        "strategy": {
            "method": "direct",
            "production_owners": {"primary": "task-stage5"},
        },
        "phase_index": [{"id": "phase-stage5", "order": 1}], "dependency_graph": {},
        "risks": [], "validation_strategy": [{"id": "VAL-001", "kind": "process"}],
        "completion_criteria": ["Archived mechanically"], "knowledge_base_update": {"action": "none"},
        "semantic_loop": {"status": "closed"},
        "execution_workspace": {"isolation": "existing", "profile": "test", "cleanup": "manual"},
    }
    plan_written = write_artifact(
        CATALOG, "root-plan", anchors, plan, state="active",
        bindings={"source_spec": "spec-stage5"},
    )
    phase = {
        "artifact_type": "phase", "schema_version": 1, "id": "phase-stage5", "plan_id": "plan-stage5",
        "name": "Stage 5", "status": "planned", "order": 1, "date_created": today, "last_updated": today,
        "source_ids": ["REQ-009"], "depends_on": [], "task_index": [{"id": "task-stage5", "order": 1}],
        "barriers": [], "validation": [{}], "completion_criteria": ["Done"], "allocated_rules": [], "allocated_skills": [],
    }
    write_artifact(
        CATALOG, "phase", anchors, phase, state="active",
        bindings={"plan": "plan-stage5"},
    )
    task = {
        "artifact_type": "task", "schema_version": 2, "id": "task-stage5", "plan_id": "plan-stage5",
        "phase_id": "phase-stage5", "name": "Finalize", "status": "planned", "order": 1,
        "task_type": "implementation", "date_created": today, "last_updated": today,
        "source_ids": ["REQ-009"],
        "source_obligations": [{"source_id": "REQ-009", "semantic": "Complete Stage 5 finalization."}],
        "truth_basis": {"purpose": "finalize", "as_is_evidence": ["current"], "decision_authority": ["spec"], "expected_delta": ["archive"], "conflict_status": "clear"},
        "depends_on": [], "source_files": [], "target_files": ["src/current.py"], "target_symbols": ["main"],
        "interfaces": {}, "steps": ["finalize"], "validation": [{"id": "VAL-001", "kind": "process"}],
        "evidence_capability": {"result": "mapped", "reason": "test", "invariants": []},
        "completion_criteria": ["Done"], "methodology": {"name": "tdd"},
        "executor_profile": {"capability": "implementation", "context_mode": "bounded", "review_capability": "none"},
        "acceptance_review": {"required": review_required}, "allocated_rules": [], "allocated_skills": [],
        "handoff_contract": "executor-result-v1",
    }
    write_artifact(
        CATALOG, "task", anchors, task, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )
    plan_path = Path(str(plan_written["path"]))
    return review_runtime.plan_review_identity(workspace, plan_path)


def _task_authority(workspace: Path, task_id: str = "task-stage5") -> dict[str, str]:
    return review_identity.canonical_task_authority_identity(
        workspace, "plan-stage5", task_id
    )


def _write_peer_task(workspace: Path, *, symbol: str = "peer") -> None:
    anchors = {"workspace_root": workspace}
    phase_record = read_artifact(
        CATALOG, "phase", anchors, identity="phase-stage5", state="active",
        bindings={"plan": "plan-stage5"},
    )
    phase = dict(phase_record["data"])
    if not any(item.get("id") == "task-peer" for item in phase["task_index"]):
        phase["task_index"].append({"id": "task-peer", "order": 2})
        write_artifact(
            CATALOG, "phase", anchors, phase, state="active",
            bindings={"plan": "plan-stage5"},
        )

    primary = read_artifact(
        CATALOG, "task", anchors, identity="task-stage5", state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )["data"]
    peer = json.loads(json.dumps(primary))
    peer.update(
        {
            "id": "task-peer",
            "name": "Peer",
            "order": 2,
            "source_ids": ["REQ-010"],
            "source_obligations": [
                {"source_id": "REQ-010", "semantic": "Implement peer behavior."}
            ],
            "depends_on": [],
            "target_files": ["src/peer.py"],
            "target_symbols": [symbol],
        }
    )
    write_artifact(
        CATALOG, "task", anchors, peer, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )


def _set_primary_dependencies(workspace: Path, dependencies: list[str]) -> None:
    anchors = {"workspace_root": workspace}
    task = dict(read_artifact(
        CATALOG, "task", anchors, identity="task-stage5", state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )["data"])
    task["depends_on"] = dependencies
    write_artifact(
        CATALOG, "task", anchors, task, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )


def test_catalog_v6_registers_exact_stage5_families_and_policies() -> None:
    catalog = load_catalog(CATALOG)
    assert catalog["catalog_id"] == "artifact-family-catalog-v6"
    for family in (
        "executor-result",
        "implementation-review",
        "accepted-task-result",
        "final-workflow-review",
    ):
        policy = family_policy(catalog, family)
        assert policy["representation"] == "yaml"
        assert policy["anchor"] == "workspace_root"
        assert policy["lifecycle"]["authority"] == "location"
        assert policy["index"]["format"] == "jsonl"

    executor = family_policy(catalog, "executor-result")
    assert executor["locator"]["template"] == (
        ".work-bundle/orchestration/result/executor/{state}/{plan}/{task}/{id}.executor-result.yaml"
    )
    assert executor["lifecycle"]["transitions"]["active"] == ["reviewed", "superseded", "archived"]
    assert family_policy(catalog, "implementation-review")["schema"] == {
        "id": "implementation-review-v3",
        "path": "implementation-review-v3.schema.json",
    }
    assert family_policy(catalog, "accepted-task-result")["schema"] == {
        "id": "accepted-task-result-v2",
        "path": "accepted-task-result-v2.schema.json",
    }


def test_executor_result_round_trip_inline_block_index_and_transition(
    workspace: Path, tmp_path: Path,
) -> None:
    first = _write_yaml(tmp_path, "first.yaml", _executor_semantics())
    second = _write_yaml(tmp_path, "second.yaml", _executor_semantics(), flow=True)
    for identity, content in (("result-stage5-a", first), ("result-stage5-b", second)):
        handoffs.cmd_write_executor_result(
            _args(
                workspace,
                id=identity,
                plan_id="plan-stage5",
                task_id="task-stage5",
                content_file=str(content),
            )
        )

    rows = handoffs.list_executor_results(_args(workspace))
    assert [row["id"] for row in rows] == ["result-stage5-a", "result-stage5-b"]
    assert rows[0]["task_id"] == rows[1]["task_id"] == "task-stage5"
    handoffs.cmd_transition_executor_result(
        _args(
            workspace,
            id="result-stage5-a",
            plan_id="plan-stage5",
            task_id="task-stage5",
            current_state="active",
            target_state="reviewed",
        )
    )
    stored = read_artifact(
        CATALOG,
        "executor-result",
        {"workspace_root": workspace},
        identity="result-stage5-a",
        state="reviewed",
        bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    assert stored["data"]["result_state"] == "implemented"


def test_executor_result_rejects_overrides_and_updates_active_identity_in_place(
    workspace: Path, tmp_path: Path,
) -> None:
    bad = _executor_semantics()
    bad["verdict"] = "accept"
    content = _write_yaml(tmp_path, "bad.yaml", bad)
    with pytest.raises(SystemExit, match="forbidden|schema validation"):
        handoffs.cmd_write_executor_result(
            _args(
                workspace,
                id="result-stage5",
                plan_id="plan-stage5",
                task_id="task-stage5",
                content_file=str(content),
            )
        )
    assert not list(workspace.rglob("*.executor-result.yaml"))

    content = _write_yaml(tmp_path, "good.yaml", _executor_semantics())
    args = _args(
        workspace,
        id="result-stage5",
        plan_id="plan-stage5",
        task_id="task-stage5",
        content_file=str(content),
    )
    handoffs.cmd_write_executor_result(args)
    path = next(workspace.rglob("*.executor-result.yaml"))
    created = yaml.safe_load(path.read_text(encoding="utf-8"))["date_created"]
    repaired = _executor_semantics()
    repaired["summary"] = "Implemented the corrected bounded task."
    repaired_input = _write_yaml(tmp_path, "repaired.yaml", repaired)
    handoffs.cmd_write_executor_result(
        _args(
            workspace,
            id="result-stage5",
            plan_id="plan-stage5",
            task_id="task-stage5",
            content_file=str(repaired_input),
        )
    )
    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored["date_created"] == created
    assert stored["summary"] == "Implemented the corrected bounded task."
    assert len(list(workspace.rglob("*.executor-result.yaml"))) == 1


def test_review_accepted_result_and_final_review_form_compact_current_chain(
    workspace: Path, tmp_path: Path,
) -> None:
    plan_identity = _write_stage5_plan_tree(workspace)
    executor_input = _write_yaml(tmp_path, "executor.yaml", _executor_semantics())
    handoffs.cmd_write_executor_result(
        _args(
            workspace,
            id="result-stage5",
            plan_id="plan-stage5",
            task_id="task-stage5",
            content_file=str(executor_input),
        )
    )
    executor_path = next(workspace.rglob("*.executor-result.yaml"))
    executor_digest = hashlib.sha256(executor_path.read_bytes()).hexdigest()

    candidate = _candidate(workspace)
    review_input = _write_yaml(
        tmp_path, "review.yaml",
        _review_semantics(candidate, authority_identity=_task_authority(workspace), verdict="repair"),
    )
    review_runtime.cmd_write_implementation_review(
        _args(
            workspace,
            id="review-stage5",
            plan_id="plan-stage5",
            task_id="task-stage5",
            source_root=str(workspace),
            content_file=str(review_input),
        )
    )
    review_path = next(workspace.rglob("*.implementation-review.yaml"))
    review_digest = hashlib.sha256(review_path.read_bytes()).hexdigest()

    accepted_input = _write_yaml(
        tmp_path,
        "accepted.yaml",
        {
            "product_identity": {"kind": "worktree", "sha256": candidate["sha256"]},
            "executor_result": {"id": "result-stage5", "sha256": executor_digest},
            "implementation_review": {"id": "review-stage5", "sha256": review_digest},
            "validation_outcomes": [{"id": "VAL-001", "result": "passed", "summary": "Focused pass."}],
            "unresolved_material_defects": [],
            "knowledge_disposition": {"action": "update", "reason": "Stable boundary changed."},
        },
    )
    review_runtime.cmd_write_accepted_task_result(
        _args(
            workspace,
            id="accepted-stage5",
            plan_id="plan-stage5",
            task_id="task-stage5",
            content_file=str(accepted_input),
        )
    )
    accepted_path = next(workspace.rglob("*.accepted-task-result.yaml"))
    accepted_digest = hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    accepted_stored = yaml.safe_load(accepted_path.read_text(encoding="utf-8"))
    assert accepted_stored["schema_version"] == 2
    assert accepted_stored["authority_identity"] == _task_authority(workspace)

    final_input = _write_yaml(
        tmp_path,
        "final.yaml",
        {
            "specification_id": "spec-stage5",
            "plan_identity": plan_identity,
            "candidate_identity": {"kind": "worktree", "sha256": candidate["sha256"]},
            "coverage": {"planned": 1, "accepted": 1, "missing": []},
            "accepted_results": [{"id": "accepted-stage5", "task_id": "task-stage5", "sha256": accepted_digest}],
            "accepted_reviews": [{"id": "review-stage5", "sha256": review_digest}],
            "test_outcomes": [{"id": "VAL-001", "result": "passed", "summary": "Focused pass."}],
            "unresolved_material_defects": [],
            "knowledge_disposition": {"action": "update", "reason": "Ready for owner follow-up."},
            "knowledge_return": {"status": "pending", "reference": None},
            "repository_finalization": {
                "repositories": [{
                    "repository_id": "source", "root": str(workspace),
                    "head": subprocess.run(
                        ["git", "-C", str(workspace), "rev-parse", "HEAD"], check=True,
                        capture_output=True, text=True,
                    ).stdout.strip(),
                }]
            },
            "verdict": "accept",
            "archive_ready": False,
            "reasons": ["All planned work has an accepted product review."],
        },
    )
    review_runtime.cmd_write_final_workflow_review(
        _args(
            workspace,
            id="final-stage5",
            plan_id="plan-stage5",
            content_file=str(final_input),
        )
    )

    accepted_repair = yaml.safe_load(accepted_input.read_text(encoding="utf-8"))
    accepted_repair["validation_outcomes"][0]["summary"] = "Focused current pass."
    accepted_repair_input = _write_yaml(tmp_path, "accepted-repaired.yaml", accepted_repair)
    review_runtime.cmd_write_accepted_task_result(
        _args(
            workspace,
            id="accepted-stage5",
            plan_id="plan-stage5",
            task_id="task-stage5",
            content_file=str(accepted_repair_input),
        )
    )
    current_accepted_digest = hashlib.sha256(accepted_path.read_bytes()).hexdigest()
    final_repair = yaml.safe_load(final_input.read_text(encoding="utf-8"))
    final_repair["accepted_results"][0]["sha256"] = current_accepted_digest
    final_repair["reasons"] = ["The current complete workflow is ready."]
    final_repair_input = _write_yaml(tmp_path, "final-repaired.yaml", final_repair)
    review_runtime.cmd_write_final_workflow_review(
        _args(
            workspace,
            id="final-stage5",
            plan_id="plan-stage5",
            content_file=str(final_repair_input),
        )
    )

    assert [row["id"] for row in review_runtime.list_implementation_reviews(_args(workspace))] == ["review-stage5"]
    assert review_runtime.list_implementation_reviews(_args(workspace))[0]["verdict"] == "repair"
    assert [row["id"] for row in review_runtime.list_accepted_task_results(_args(workspace))] == ["accepted-stage5"]
    assert [row["id"] for row in review_runtime.list_final_workflow_reviews(_args(workspace))] == ["final-stage5"]

    final_path = next(workspace.rglob("final-stage5.final-workflow-review.yaml"))
    final_before = final_path.read_bytes()
    changed_executor = _executor_semantics()
    changed_executor["summary"] = "Changed after controller acceptance."
    changed_executor_input = _write_yaml(tmp_path, "executor-changed.yaml", changed_executor)
    handoffs.cmd_write_executor_result(
        _args(
            workspace,
            id="result-stage5",
            plan_id="plan-stage5",
            task_id="task-stage5",
            content_file=str(changed_executor_input),
        )
    )
    with pytest.raises(SystemExit, match="executor reference is stale"):
        review_runtime.cmd_write_final_workflow_review(
            _args(
                workspace,
                id="final-stage5",
                plan_id="plan-stage5",
                content_file=str(final_repair_input),
            )
        )
    assert final_path.read_bytes() == final_before


def test_review_verdict_remains_agent_authored_and_supporting_state_is_not_required(
    workspace: Path, tmp_path: Path,
) -> None:
    plan_identity = _write_stage5_plan_tree(workspace)
    review_input = _write_yaml(
        tmp_path, "review.yaml",
        _review_semantics(
            _candidate(workspace), authority_identity=_task_authority(workspace), verdict="repair"
        ),
    )
    review_runtime.cmd_write_implementation_review(
        _args(
            workspace,
            id="review-omission",
            plan_id="plan-stage5",
            task_id="task-stage5",
            source_root=str(workspace),
            content_file=str(review_input),
        )
    )
    row = review_runtime.list_implementation_reviews(_args(workspace))[0]
    assert row["verdict"] == "repair"
    assert "receipt" not in row and "publication" not in row and "history" not in row


def test_implementation_review_updates_same_active_identity_after_full_rereview(
    workspace: Path, tmp_path: Path,
) -> None:
    plan_identity = _write_stage5_plan_tree(workspace)
    candidate = _candidate(workspace)
    repair_input = _write_yaml(
        tmp_path, "repair-review.yaml",
        _review_semantics(candidate, authority_identity=_task_authority(workspace), verdict="repair"),
    )
    args = _args(
        workspace,
        id="review-current",
        plan_id="plan-stage5",
        task_id="task-stage5",
        source_root=str(workspace),
        content_file=str(repair_input),
    )
    review_runtime.cmd_write_implementation_review(args)
    path = next(workspace.rglob("review-current.implementation-review.yaml"))
    created = yaml.safe_load(path.read_text(encoding="utf-8"))["date_created"]
    before = path.read_bytes()

    integrated = _review_semantics(candidate, authority_identity=plan_identity, verdict="accept")
    integrated["scope"] = "integrated"
    integrated_input = _write_yaml(tmp_path, "integrated-review.yaml", integrated)
    with pytest.raises(SystemExit, match="scope or task binding"):
        review_runtime.cmd_write_implementation_review(
            _args(
                workspace,
                id="review-current",
                plan_id="plan-stage5",
                source_root=str(workspace),
                content_file=str(integrated_input),
            )
        )
    assert path.read_bytes() == before

    with pytest.raises(SystemExit, match="Integrated.*task binding"):
        review_runtime.cmd_write_implementation_review(
            _args(
                workspace,
                id="review-integrated-invalid",
                plan_id="plan-stage5",
                task_id="task-stage5",
                source_root=str(workspace),
                content_file=str(integrated_input),
            )
        )
    assert not list(workspace.rglob("review-integrated-invalid.implementation-review.yaml"))

    accepted = _review_semantics(candidate, authority_identity=_task_authority(workspace), verdict="accept")
    accepted["reviewed_obligations"][0]["summary"] = (
        "The complete repaired candidate satisfies the obligation."
    )
    accept_input = _write_yaml(tmp_path, "accept-review.yaml", accepted)
    review_runtime.cmd_write_implementation_review(
        _args(
            workspace,
            id="review-current",
            plan_id="plan-stage5",
            task_id="task-stage5",
            source_root=str(workspace),
            content_file=str(accept_input),
        )
    )

    stored = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert stored["date_created"] == created
    assert stored["verdict"] == "accept"
    assert len(list(workspace.rglob("review-current.implementation-review.yaml"))) == 1


def test_review_writer_rejects_stale_task_authority_identity_before_mutation(
    workspace: Path, tmp_path: Path,
) -> None:
    _write_finalization_case(workspace)
    content = _write_yaml(
        tmp_path,
        "stale-plan-review.yaml",
        _review_semantics(_candidate(workspace)),
    )

    with pytest.raises(SystemExit, match="authority.*identity.*stale"):
        review_runtime.cmd_write_implementation_review(
            _args(
                workspace,
                id="review-stale-plan",
                plan_id="plan-stage5",
                task_id="task-stage5",
                source_root=str(workspace),
                content_file=str(content),
            )
        )

    assert not list(workspace.rglob("review-stale-plan.implementation-review.yaml"))


def test_task_review_authority_ignores_unrelated_task_content(
    workspace: Path, tmp_path: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace, symbol="before")
    authority = _task_authority(workspace)

    _write_peer_task(workspace, symbol="after")

    content = _write_yaml(
        tmp_path,
        "unrelated-repair-review.yaml",
        _review_semantics(_candidate(workspace), authority_identity=authority),
    )
    review_runtime.cmd_write_implementation_review(
        _args(
            workspace,
            id="review-unrelated-repair",
            plan_id="plan-stage5",
            task_id="task-stage5",
            source_root=str(workspace),
            content_file=str(content),
        )
    )
    assert next(workspace.rglob("review-unrelated-repair.implementation-review.yaml"))


def test_task_review_authority_includes_dependency_closure(
    workspace: Path, tmp_path: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace, symbol="before")
    _set_primary_dependencies(workspace, ["task-peer"])
    authority = _task_authority(workspace)

    _write_peer_task(workspace, symbol="after")

    content = _write_yaml(
        tmp_path,
        "stale-dependency-review.yaml",
        _review_semantics(_candidate(workspace), authority_identity=authority),
    )
    with pytest.raises(SystemExit, match="authority.*identity.*stale"):
        review_runtime.cmd_write_implementation_review(
            _args(
                workspace,
                id="review-stale-dependency",
                plan_id="plan-stage5",
                task_id="task-stage5",
                source_root=str(workspace),
                content_file=str(content),
            )
        )
    assert not list(workspace.rglob("review-stale-dependency.implementation-review.yaml"))


def test_task_review_authority_includes_dependency_specification_sources(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace)
    _set_primary_dependencies(workspace, ["task-peer"])
    authority = _task_authority(workspace)
    record = read_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        identity="spec-stage5", state="active",
    )
    body = str(record["body"]).replace(
        "Implement peer behavior.", "Implement corrected peer behavior."
    )
    write_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        record["data"], state="active", body=body,
    )

    assert _task_authority(workspace) != authority


def test_task_review_authority_ignores_unreferenced_specification_content(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    authority = _task_authority(workspace)
    record = read_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        identity="spec-stage5", state="active",
    )
    write_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        record["data"], state="active",
        body=str(record["body"]) + "\n- **REQ-090:** Clarify unrelated behavior.\n",
    )

    assert _task_authority(workspace) == authority


def test_task_review_authority_includes_referenced_specification_content(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    authority = _task_authority(workspace)
    record = read_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        identity="spec-stage5", state="active",
    )
    body = str(record["body"]).replace(
        "Complete Stage 5 finalization.",
        "Complete Stage 5 finalization with corrected semantics.",
    )
    write_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        record["data"], state="active", body=body,
    )

    assert _task_authority(workspace) != authority


def test_task_review_authority_includes_global_specification_decision(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    authority = _task_authority(workspace)
    record = read_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        identity="spec-stage5", state="active",
    )
    body = str(record["body"]).replace(
        "Use the direct implementation-review authority model globally.",
        "Use the corrected implementation-review authority model globally.",
    )
    write_artifact(
        CATALOG, "specification", {"workspace_root": workspace},
        record["data"], state="active", body=body,
    )

    assert _task_authority(workspace) != authority


def test_task_review_authority_ignores_unrelated_phase_membership(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    authority = _task_authority(workspace)

    _write_peer_task(workspace)

    assert _task_authority(workspace) == authority


def test_task_review_authority_ignores_unrelated_root_allocations(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace)
    authority = _task_authority(workspace)
    anchors = {"workspace_root": workspace}
    plan = dict(read_artifact(
        CATALOG, "root-plan", anchors, identity="plan-stage5", state="active",
        bindings={"source_spec": "spec-stage5"},
    )["data"])
    plan["authority"]["aliases"]["DEC-090"] = "Changed unrelated optional policy."
    plan["strategy"]["production_owners"]["peer"] = "task-peer"
    plan["dependency_graph"]["task-peer"] = ["task-stage5"]
    plan["source_coverage"].append({
        "source_id": "REQ-010", "obligation_kind": "requirement",
        "task_ids": ["task-peer"],
    })
    write_artifact(
        CATALOG, "root-plan", anchors, plan, state="active",
        bindings={"source_spec": "spec-stage5"},
    )

    assert _task_authority(workspace) == authority


def test_task_review_authority_includes_shared_ownership_records(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace)
    authority = _task_authority(workspace)
    peer = dict(read_artifact(
        CATALOG, "task", {"workspace_root": workspace}, identity="task-peer",
        state="active", bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )["data"])
    peer["target_files"] = ["src/current.py"]
    write_artifact(
        CATALOG, "task", {"workspace_root": workspace}, peer, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )

    assert _task_authority(workspace) != authority


def test_task_review_authority_includes_shared_interface_specification_sources(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace)
    anchors = {"workspace_root": workspace}
    primary = dict(read_artifact(
        CATALOG, "task", anchors, identity="task-stage5", state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )["data"])
    peer = dict(read_artifact(
        CATALOG, "task", anchors, identity="task-peer", state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )["data"])
    primary["interfaces"] = {"produces": ["shared-api"]}
    peer["interfaces"] = {"consumes": ["shared-api"]}
    write_artifact(
        CATALOG, "task", anchors, primary, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )
    write_artifact(
        CATALOG, "task", anchors, peer, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )
    authority = _task_authority(workspace)
    specification = read_artifact(
        CATALOG, "specification", anchors, identity="spec-stage5", state="active",
    )
    body = str(specification["body"]).replace(
        "Implement peer behavior.", "Implement corrected peer behavior."
    )
    write_artifact(
        CATALOG, "specification", anchors, specification["data"],
        state="active", body=body,
    )

    assert _task_authority(workspace) != authority


def test_task_review_authority_includes_accepted_dependency_result(
    workspace: Path,
) -> None:
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace)
    _set_primary_dependencies(workspace, ["task-peer"])
    authority = _task_authority(workspace)
    accepted = {
        "artifact_type": "accepted-task-result", "schema_version": 1,
        "id": "accepted-peer", "plan_id": "plan-stage5", "task_id": "task-peer",
        "product_identity": {"kind": "worktree", "sha256": "1" * 64},
        "product_sha256": "1" * 64,
        "executor_result": {"id": "result-peer", "sha256": "2" * 64},
        "implementation_review": None, "validation_outcomes": [],
        "unresolved_material_defects": [],
        "knowledge_disposition": {"action": "none", "reason": "No durable update."},
        "knowledge_action": "none", "date_created": "2026-09-20", "last_updated": "2026-09-20",
    }
    write_artifact(
        CATALOG, "accepted-task-result", {"workspace_root": workspace}, accepted,
        state="active", bindings={"plan": "plan-stage5", "task": "task-peer"},
    )

    assert _task_authority(workspace) != authority


def test_accepted_result_enforces_canonical_task_review_requirement_before_write(
    workspace: Path, tmp_path: Path,
) -> None:
    _write_finalization_case(workspace, review_required=True, review_reference="none")
    executor_path = next(workspace.rglob("result-stage5.executor-result.yaml"))
    candidate = _candidate(workspace)
    content = _write_yaml(
        tmp_path,
        "missing-required-review.yaml",
        {
            "product_identity": {"kind": "worktree", "sha256": candidate["sha256"]},
            "executor_result": {
                "id": "result-stage5",
                "sha256": hashlib.sha256(executor_path.read_bytes()).hexdigest(),
            },
            "implementation_review": None,
            "validation_outcomes": [],
            "unresolved_material_defects": [],
            "knowledge_disposition": {"action": "none", "reason": "No durable update."},
        },
    )

    with pytest.raises(SystemExit, match="requires an implementation review"):
        review_runtime.cmd_write_accepted_task_result(
            _args(
                workspace,
                id="accepted-missing-review",
                plan_id="plan-stage5",
                task_id="task-stage5",
                content_file=str(content),
            )
        )

    assert not list(workspace.rglob("accepted-missing-review.accepted-task-result.yaml"))


def test_final_review_writer_rejects_stale_plan_tree_identity_before_write(
    workspace: Path, tmp_path: Path,
) -> None:
    _write_finalization_case(workspace)
    stored = next(workspace.rglob("final-stage5.final-workflow-review.yaml"))
    semantic = yaml.safe_load(stored.read_text(encoding="utf-8"))
    for field in review_runtime.CURRENT_STRUCTURAL_FIELDS:
        semantic.pop(field, None)
    semantic["plan_identity"] = {"id": "plan-stage5", "sha256": "0" * 64}
    content = _write_yaml(tmp_path, "stale-final-review.yaml", semantic)

    with pytest.raises(SystemExit, match="plan.*identity.*stale"):
        review_runtime.cmd_write_final_workflow_review(
            _args(
                workspace,
                id="final-stale-plan",
                plan_id="plan-stage5",
                content_file=str(content),
            )
        )

    assert not list(workspace.rglob("final-stale-plan.final-workflow-review.yaml"))


def test_final_review_rejects_stale_v2_accepted_task_authority(
    workspace: Path,
) -> None:
    _write_finalization_case(
        workspace, review_required=False, review_reference="none"
    )
    anchors = {"workspace_root": workspace}
    accepted_record = read_artifact(
        CATALOG, "accepted-task-result", anchors, identity="accepted-stage5",
        state="active", bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    accepted = dict(accepted_record["data"])
    accepted["schema_version"] = 2
    accepted["authority_identity"] = _task_authority(workspace)
    accepted_written = write_artifact(
        CATALOG, "accepted-task-result", anchors, accepted, state="active",
        bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )

    task = dict(read_artifact(
        CATALOG, "task", anchors, identity="task-stage5", state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )["data"])
    task["steps"] = [*task["steps"], "changed after acceptance"]
    write_artifact(
        CATALOG, "task", anchors, task, state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )
    final = dict(read_artifact(
        CATALOG, "final-workflow-review", anchors, identity="final-stage5",
        state="active", bindings={"plan": "plan-stage5"},
    )["data"])
    final["plan_identity"] = review_identity.canonical_plan_tree_identity(
        workspace, "plan-stage5"
    )
    final["accepted_results"] = [{
        "id": "accepted-stage5", "task_id": "task-stage5",
        "sha256": accepted_written["digest"],
    }]

    with pytest.raises(SystemExit, match="Accepted task result authority is stale"):
        review_runtime.validate_final_workflow_chain(
            _args(workspace, plan_id="plan-stage5"), final
        )


def test_final_review_preserves_v2_acceptance_after_unrelated_specification_change(
    workspace: Path,
) -> None:
    _write_finalization_case(
        workspace, review_required=False, review_reference="none"
    )
    anchors = {"workspace_root": workspace}
    accepted_record = read_artifact(
        CATALOG, "accepted-task-result", anchors, identity="accepted-stage5",
        state="active", bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    accepted = dict(accepted_record["data"])
    accepted["schema_version"] = 2
    accepted["authority_identity"] = _task_authority(workspace)
    accepted_written = write_artifact(
        CATALOG, "accepted-task-result", anchors, accepted, state="active",
        bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    specification = read_artifact(
        CATALOG, "specification", anchors, identity="spec-stage5", state="active",
    )
    write_artifact(
        CATALOG, "specification", anchors, specification["data"], state="active",
        body=str(specification["body"]) + "\n- **REQ-090:** Unrelated behavior.\n",
    )
    final = dict(read_artifact(
        CATALOG, "final-workflow-review", anchors, identity="final-stage5",
        state="active", bindings={"plan": "plan-stage5"},
    )["data"])
    final["accepted_results"] = [{
        "id": "accepted-stage5", "task_id": "task-stage5",
        "sha256": accepted_written["digest"],
    }]

    review_runtime.validate_final_workflow_chain(
        _args(workspace, plan_id="plan-stage5"), final
    )


def _write_finalization_case(
    workspace: Path,
    *,
    review_required: bool = True,
    review_reference: str = "valid",
) -> None:
    anchors = {"workspace_root": workspace}
    today = "2026-09-20"
    plan_identity = _write_stage5_plan_tree(
        workspace, review_required=review_required
    )

    candidate = _candidate(workspace)
    review_written = None
    if review_reference == "valid":
        review = {
            **_review_semantics(candidate, authority_identity=_task_authority(workspace)), "artifact_type": "implementation-review", "schema_version": 3,
            "id": "review-stage5", "plan_id": "plan-stage5", "task_id": "task-stage5",
            "target_sha256": candidate["sha256"], "date_created": today, "last_updated": today,
        }
        review_written = write_artifact(CATALOG, "implementation-review", anchors, review, state="active", bindings={"plan": "plan-stage5", "task": "task-stage5"})
    executor = {
        **_executor_semantics(), "artifact_type": "executor-result", "schema_version": 1,
        "id": "result-stage5", "plan_id": "plan-stage5", "phase_id": "phase-stage5",
        "task_id": "task-stage5", "date_created": today, "last_updated": today,
    }
    executor_written = write_artifact(CATALOG, "executor-result", anchors, executor, state="active", bindings={"plan": "plan-stage5", "task": "task-stage5"})
    accepted = {
        "artifact_type": "accepted-task-result", "schema_version": 1, "id": "accepted-stage5",
        "plan_id": "plan-stage5", "task_id": "task-stage5",
        "product_identity": {"kind": "worktree", "sha256": candidate["sha256"]}, "product_sha256": candidate["sha256"],
        "executor_result": {"id": "result-stage5", "sha256": executor_written["digest"]},
        "implementation_review": (
            {"id": "review-stage5", "sha256": review_written["digest"]}
            if review_written is not None
            else ({"id": "review-missing", "sha256": "f" * 64} if review_reference == "invalid" else None)
        ),
        "validation_outcomes": [], "unresolved_material_defects": [],
        "knowledge_disposition": {"action": "none", "reason": "No durable update."}, "knowledge_action": "none",
        "date_created": today, "last_updated": today,
    }
    accepted_written = write_artifact(CATALOG, "accepted-task-result", anchors, accepted, state="active", bindings={"plan": "plan-stage5", "task": "task-stage5"})
    head = subprocess.run(["git", "-C", str(workspace), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    final = {
        "artifact_type": "final-workflow-review", "schema_version": 1, "id": "final-stage5", "plan_id": "plan-stage5",
        "specification_id": "spec-stage5", "plan_identity": plan_identity,
        "candidate_identity": {"kind": "worktree", "sha256": candidate["sha256"]}, "target_sha256": candidate["sha256"],
        "coverage": {"planned": 1, "accepted": 1, "missing": []},
        "accepted_results": [{"id": "accepted-stage5", "task_id": "task-stage5", "sha256": accepted_written["digest"]}],
        "accepted_reviews": (
            [{"id": "review-stage5", "sha256": review_written["digest"]}]
            if review_written is not None
            else ([{"id": "review-missing", "sha256": "f" * 64}] if review_reference == "invalid" else [])
        ),
        "test_outcomes": [], "unresolved_material_defects": [],
        "knowledge_disposition": {"action": "none", "reason": "No durable update."},
        "knowledge_return": {"status": "not-needed", "reference": None},
        "repository_finalization": {"repositories": [{"repository_id": "source", "root": str(workspace), "head": head}]},
        "verdict": "accept", "archive_ready": True, "reasons": ["Mechanically ready."],
        "date_created": today, "last_updated": today,
    }
    write_artifact(CATALOG, "final-workflow-review", anchors, final, state="active", bindings={"plan": "plan-stage5"})


def test_finalize_reviewed_plan_verifies_references_clean_git_and_archives(
    workspace: Path,
) -> None:
    _write_finalization_case(workspace)

    dirty = workspace / "untracked.txt"
    dirty.write_text("dirty\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not exact and clean"):
        plans.cmd_finalize_reviewed_plan(_args(workspace, plan_id="plan-stage5", final_review_id="final-stage5"))
    dirty.unlink()
    plans.cmd_finalize_reviewed_plan(_args(workspace, plan_id="plan-stage5", final_review_id="final-stage5"))
    assert list((workspace / ".work-bundle/orchestration/plan/archived").rglob("*.plan.yaml"))
    assert list((workspace / ".work-bundle/orchestration/review/final/archived").rglob("*.final-workflow-review.yaml"))


def test_finalizer_rejects_plan_tree_change_after_final_review(
    workspace: Path,
) -> None:
    _write_finalization_case(workspace)
    task_path = next(workspace.rglob("task-stage5.task.yaml"))
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    task["steps"].append("changed after review")
    write_artifact(
        CATALOG,
        "task",
        {"workspace_root": workspace},
        task,
        state="active",
        bindings={"plan": "plan-stage5", "phase": "phase-stage5"},
    )

    with pytest.raises(SystemExit, match="plan/specification identity is stale"):
        plans.cmd_finalize_reviewed_plan(
            _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
        )

    assert list(
        (workspace / ".work-bundle/orchestration/plan/active").rglob("*.plan.yaml")
    )


def test_finalize_reviewed_plan_allows_null_review_when_task_does_not_require_it(
    workspace: Path,
) -> None:
    _write_finalization_case(
        workspace, review_required=False, review_reference="none"
    )

    plans.cmd_finalize_reviewed_plan(
        _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
    )

    assert list(
        (workspace / ".work-bundle/orchestration/plan/archived").rglob("*.plan.yaml")
    )


def _plan_integrated_review_reference(
    workspace: Path, *, scope: str = "integrated", stale: str | None = None,
) -> dict[str, str]:
    anchors = {"workspace_root": workspace}
    candidate = _candidate(workspace)
    review = {
        **_review_semantics(
            candidate,
            authority_identity=review_identity.canonical_plan_tree_identity(
                workspace, "plan-stage5"
            ),
            verdict="repair",
        ),
        "artifact_type": "implementation-review", "schema_version": 3,
        "id": "review-integrated", "plan_id": "plan-stage5", "task_id": None,
        "scope": scope, "target_sha256": candidate["sha256"],
        "date_created": "2026-09-20", "last_updated": "2026-09-20",
    }
    if stale == "authority":
        review["authority_identity"] = {"id": "plan-stage5", "sha256": "0" * 64}
    elif stale == "candidate":
        review["target_sha256"] = "0" * 64
    stored = write_artifact(
        CATALOG, "implementation-review", anchors, review, state="active",
        bindings={"plan": "plan-stage5"},
    )
    return {"id": "review-integrated", "sha256": stored["digest"]}


def _final_input_with_integrated_review(
    workspace: Path, reference: dict[str, str] | None,
) -> Path:
    final = dict(read_artifact(
        CATALOG, "final-workflow-review", {"workspace_root": workspace},
        identity="final-stage5", state="active", bindings={"plan": "plan-stage5"},
    )["data"])
    for field in review_runtime.CURRENT_STRUCTURAL_FIELDS:
        final.pop(field, None)
    if reference is not None:
        final["accepted_reviews"] = [*final["accepted_reviews"], reference]
    return _write_yaml(workspace / ".work-bundle", "integrated-final.yaml", final)


@pytest.mark.parametrize("task_review_required", [False, True])
def test_plan_bound_integrated_review_is_archived_with_task_review_optional(
    workspace: Path, task_review_required: bool,
) -> None:
    _write_finalization_case(
        workspace, review_required=task_review_required,
        review_reference="valid" if task_review_required else "none",
    )
    plan_identity = review_identity.canonical_plan_tree_identity(workspace, "plan-stage5")
    reference = _plan_integrated_review_reference(workspace)
    review_runtime.cmd_write_final_workflow_review(_args(
        workspace, id="final-stage5", plan_id="plan-stage5",
        content_file=str(_final_input_with_integrated_review(workspace, None)),
    ))
    final = read_artifact(
        CATALOG, "final-workflow-review", {"workspace_root": workspace},
        identity="final-stage5", state="active", bindings={"plan": "plan-stage5"},
    )["data"]
    assert reference in final["accepted_reviews"]
    assert review_identity.canonical_plan_tree_identity(workspace, "plan-stage5") == plan_identity

    plans.cmd_finalize_reviewed_plan(
        _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
    )

    assert list((workspace / ".work-bundle/orchestration/review/implementation/archived"
                 / "plan-stage5").glob("review-integrated.implementation-review.yaml"))
    assert not list((workspace / ".work-bundle/orchestration/review/implementation/active"
                     / "plan-stage5").glob("review-integrated.implementation-review.yaml"))
    if task_review_required:
        assert list((workspace / ".work-bundle/orchestration/review/implementation/archived"
                     / "plan-stage5").glob("review-stage5.implementation-review.yaml"))


@pytest.mark.parametrize("scope,stale,error", [
    ("integrated", "authority", "integrated.*authority"),
    ("integrated", "candidate", "integrated.*candidate"),
    ("task", None, "integrated.*scope"),
])
def test_final_review_rejects_invalid_plan_integrated_reference_before_write(
    workspace: Path, scope: str, stale: str | None, error: str,
) -> None:
    _write_finalization_case(workspace, review_required=False, review_reference="none")
    final_path = next(workspace.rglob("final-stage5.final-workflow-review.yaml"))
    before = final_path.read_bytes()
    reference = _plan_integrated_review_reference(workspace, scope=scope, stale=stale)

    with pytest.raises(SystemExit, match=error):
        review_runtime.cmd_write_final_workflow_review(_args(
            workspace, id="final-stage5", plan_id="plan-stage5",
            content_file=str(_final_input_with_integrated_review(workspace, reference)),
        ))
    assert final_path.read_bytes() == before


@pytest.mark.parametrize("review_reference", ["none", "invalid"])
def test_finalize_reviewed_plan_rejects_missing_or_invalid_required_review(
    workspace: Path,
    review_reference: str,
) -> None:
    _write_finalization_case(
        workspace, review_required=True, review_reference=review_reference
    )

    with pytest.raises(SystemExit, match="implementation review|implementation-review"):
        plans.cmd_finalize_reviewed_plan(
            _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
        )

    assert list(
        (workspace / ".work-bundle/orchestration/plan/active").rglob("*.plan.yaml")
    )


def _ownership(binding_id: str) -> dict[str, object]:
    return {
        "binding_id": binding_id,
        "target_kind": "local_project",
        "state": "active",
        "original_owner": "controller",
        "current_owner": "controller",
        "reason": "task execution",
        "repair_owner": None,
        "rereview_owner": None,
        "releasable": False,
        "history": [{
            "transition_id": f"transition-{binding_id}",
            "from": "active",
            "to": "active",
            "owner": "controller",
            "reason": "task execution",
            "timestamp": "2026-09-20T00:00:00Z",
        }],
    }


def test_finalizer_reports_later_binding_release_partial_effects(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_finalization_case(workspace)
    bindings = [
        {"plan_id": "plan-stage5", "task_id": "task-a", "ownership": _ownership("binding-a")},
        {"plan_id": "plan-stage5", "task_id": "task-b", "ownership": _ownership("binding-b")},
    ]
    monkeypatch.setattr(plans, "_iter_task_bindings", lambda _root: bindings)
    monkeypatch.setattr(plans, "_persist_binding", lambda _binding, _root: None)
    monkeypatch.setattr(
        plans,
        "validate_execution_binding_ownership",
        lambda _root, ownership: ownership,
    )
    calls = 0

    class Released:
        def __init__(self, ownership: dict[str, object]) -> None:
            self.ownership = ownership

        def to_dict(self) -> dict[str, object]:
            return {**self.ownership, "state": "released", "releasable": True}

    def release(_store: object, binding_id: str, *, owner: str) -> Released:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise plans.CompletionProvenanceError("injected later binding failure")
        return Released(_ownership(binding_id))

    monkeypatch.setattr(plans, "release_completion_binding", release)

    with pytest.raises(SystemExit) as captured:
        plans.cmd_finalize_reviewed_plan(
            _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
        )
    payload = json.loads(str(captured.value))
    assert payload["status"] == "partial"
    assert payload["code"] == "WB_FINALIZATION_PARTIAL_EFFECT"
    assert payload["completed_operations"][-1]["task_id"] == "task-a"
    assert payload["failed_operation"] == {
        "operation": "binding-release",
        "task_id": "task-b",
        "binding_id": "binding-b",
    }


def test_finalizer_reports_transition_partial_effects(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_finalization_case(workspace)
    real_transition = artifact_store.transition_artifact
    calls = 0

    def transition(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected later transition failure")
        return real_transition(*args, **kwargs)

    monkeypatch.setattr(artifact_store, "transition_artifact", transition)

    with pytest.raises(SystemExit) as captured:
        plans.cmd_finalize_reviewed_plan(
            _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
        )
    payload = json.loads(str(captured.value))
    assert payload["status"] == "partial"
    assert payload["completed_operations"][-1]["operation"] == "artifact-transition"
    assert payload["failed_operation"]["operation"] == "artifact-transition"
    assert payload["failed_operation"]["family"] == "accepted-task-result"


def test_finalizer_reports_index_rebuild_partial_effects(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_finalization_case(workspace)
    real_transition = artifact_store.transition_artifact
    real_rebuild = plans.rebuild_index
    mutation_started = False

    def transition(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal mutation_started
        result = real_transition(*args, **kwargs)
        mutation_started = True
        return result

    def rebuild(*args: object, **kwargs: object) -> dict[str, object]:
        if mutation_started:
            raise RuntimeError("injected index rebuild failure")
        return real_rebuild(*args, **kwargs)

    monkeypatch.setattr(artifact_store, "transition_artifact", transition)
    monkeypatch.setattr(plans, "rebuild_index", rebuild)

    with pytest.raises(SystemExit) as captured:
        plans.cmd_finalize_reviewed_plan(
            _args(workspace, plan_id="plan-stage5", final_review_id="final-stage5")
        )
    payload = json.loads(str(captured.value))
    assert payload["status"] == "partial"
    assert any(
        operation["operation"] == "artifact-transition"
        for operation in payload["completed_operations"]
    )
    assert payload["failed_operation"]["operation"] == "index-rebuild"


def test_worktree_candidate_identity_is_exact_and_does_not_require_clean_head(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "stage5@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Stage 5"], check=True)
    changed = tmp_path / "changed.py"
    changed.write_text("print('base')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "changed.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    base = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    changed.write_text("print('current')\n", encoding="utf-8")
    candidate = execution_context.build_implementation_review_candidate(
        source_root=tmp_path,
        kind="worktree",
        base_commit=base,
        changed_paths=["changed.py"],
    )
    expected_manifest = [
        {
            "path": "changed.py",
            "state": "present",
            "sha256": hashlib.sha256(changed.read_bytes()).hexdigest(),
        }
    ]
    assert candidate["manifest"] == expected_manifest
    assert candidate["sha256"] == hashlib.sha256(
        f"present {expected_manifest[0]['sha256']}  changed.py\n".encode()
    ).hexdigest()


def test_worktree_candidate_admits_deleted_base_path_with_explicit_state(
    workspace: Path,
) -> None:
    base = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    deleted = workspace / "src/current.py"
    deleted.unlink()

    candidate = execution_context.build_implementation_review_candidate(
        source_root=workspace,
        kind="worktree",
        base_commit=base,
        changed_paths=["src/current.py"],
    )

    assert candidate["manifest"] == [{"path": "src/current.py", "state": "deleted"}]
    assert candidate["sha256"] == hashlib.sha256(
        b"deleted -  src/current.py\n"
    ).hexdigest()
    checked = review_runtime._candidate_validator().validate_current_candidate_and_independence(
        workspace,
        candidate,
        reviewer_agent_id="reviewer-1",
        implementor_agent_id="worker-1",
    )
    assert checked["target"] == candidate


def test_implementation_review_v3_schema_accepts_only_explicit_deletion_state(
    workspace: Path,
) -> None:
    base = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (workspace / "src/current.py").unlink()
    candidate = execution_context.build_implementation_review_candidate(
        source_root=workspace,
        kind="worktree",
        base_commit=base,
        changed_paths=["src/current.py"],
    )
    review = {
        **_review_semantics(candidate),
        "artifact_type": "implementation-review",
        "schema_version": 3,
        "id": "review-deletion",
        "plan_id": "plan-stage5",
        "task_id": "task-stage5",
        "target_sha256": candidate["sha256"],
        "date_created": "2026-09-20",
        "last_updated": "2026-09-20",
    }

    written = write_artifact(
        CATALOG,
        "implementation-review",
        {"workspace_root": workspace},
        review,
        state="active",
        bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    assert written["schema"] == "implementation-review-v3"

    malformed = json.loads(json.dumps(review))
    malformed["id"] = "review-ambiguous-deletion"
    malformed["target"]["manifest"][0]["sha256"] = hashlib.sha256(b"").hexdigest()
    with pytest.raises(SystemExit, match="Artifact schema validation failed"):
        write_artifact(
            CATALOG,
            "implementation-review",
            {"workspace_root": workspace},
            malformed,
            state="active",
            bindings={"plan": "plan-stage5", "task": "task-stage5"},
        )


def test_current_catalog_reads_active_v2_review_without_rewriting_it(
    workspace: Path,
) -> None:
    candidate = _candidate(workspace)
    review = {
        **_review_semantics(candidate),
        "artifact_type": "implementation-review",
        "schema_version": 2,
        "id": "review-active-v2",
        "plan_id": "plan-stage5",
        "task_id": "task-stage5",
        "plan_identity": {"id": "plan-stage5", "sha256": "2" * 64},
        "target_sha256": candidate["sha256"],
        "date_created": "2026-09-20",
        "last_updated": "2026-09-20",
    }
    review.pop("authority_identity")

    write_artifact(
        CATALOG,
        "implementation-review",
        {"workspace_root": workspace},
        review,
        state="active",
        bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    stored = read_artifact(
        CATALOG,
        "implementation-review",
        {"workspace_root": workspace},
        identity="review-active-v2",
        state="active",
        bindings={"plan": "plan-stage5", "task": "task-stage5"},
    )
    assert stored["data"]["schema_version"] == 2
    assert "authority_identity" not in stored["data"]


def test_worktree_candidate_rejects_path_absent_from_worktree_and_base(
    workspace: Path,
) -> None:
    base = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = {
        "kind": "worktree",
        "base_commit": base,
        "manifest": [{"path": "never-existed.py", "state": "deleted"}],
        "sha256": hashlib.sha256(
            b"deleted -  never-existed.py\n"
        ).hexdigest(),
    }

    with pytest.raises(SystemExit, match="unavailable"):
        execution_context.build_implementation_review_candidate(
            source_root=workspace,
            kind="worktree",
            base_commit=base,
            changed_paths=["never-existed.py"],
        )
    validator = review_runtime._candidate_validator()
    with pytest.raises(validator.ReviewerWorkspaceError, match="TARGET_INVALID"):
        validator.validate_current_candidate_and_independence(
            workspace,
            target,
            reviewer_agent_id="reviewer-1",
            implementor_agent_id="worker-1",
        )


def test_worktree_candidate_admits_existing_empty_file_without_base_entry(
    workspace: Path,
) -> None:
    base = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    empty = workspace / "empty.py"
    empty.write_bytes(b"")

    candidate = execution_context.build_implementation_review_candidate(
        source_root=workspace,
        kind="worktree",
        base_commit=base,
        changed_paths=["empty.py"],
    )

    assert candidate["manifest"] == [
        {
            "path": "empty.py",
            "state": "present",
            "sha256": hashlib.sha256(b"").hexdigest(),
        }
    ]
    checked = review_runtime._candidate_validator().validate_current_candidate_and_independence(
        workspace,
        candidate,
        reviewer_agent_id="reviewer-1",
        implementor_agent_id="worker-1",
    )
    assert checked["target"] == candidate


def test_worktree_candidate_distinguishes_deleted_path_from_empty_file(
    workspace: Path,
) -> None:
    base = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    path = workspace / "src/current.py"
    path.unlink()
    deleted = execution_context.build_implementation_review_candidate(
        source_root=workspace,
        kind="worktree",
        base_commit=base,
        changed_paths=["src/current.py"],
    )

    path.write_bytes(b"")
    empty = execution_context.build_implementation_review_candidate(
        source_root=workspace,
        kind="worktree",
        base_commit=base,
        changed_paths=["src/current.py"],
    )

    assert deleted["manifest"] == [{"path": "src/current.py", "state": "deleted"}]
    assert empty["manifest"] == [
        {
            "path": "src/current.py",
            "state": "present",
            "sha256": hashlib.sha256(b"").hexdigest(),
        }
    ]
    assert deleted["sha256"] != empty["sha256"]


@pytest.mark.parametrize(
    ("manifest", "aggregate"),
    [
        (
            [{"path": "src/current.py", "state": "deleted"}],
            hashlib.sha256(b"deleted -  src/current.py\n").hexdigest(),
        ),
        (
            [
                {
                    "path": "src/current.py",
                    "state": "present",
                    "sha256": hashlib.sha256(b"").hexdigest(),
                }
            ],
            hashlib.sha256(
                f"present {hashlib.sha256(b'').hexdigest()}  src/current.py\n".encode()
            ).hexdigest(),
        ),
    ],
)
def test_worktree_candidate_rejects_manifest_state_that_disagrees_with_path(
    workspace: Path,
    manifest: list[dict[str, str]],
    aggregate: str,
) -> None:
    base = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = {
        "kind": "worktree",
        "base_commit": base,
        "manifest": manifest,
        "sha256": aggregate,
    }
    if manifest[0]["state"] == "present":
        (workspace / "src/current.py").unlink()

    validator = review_runtime._candidate_validator()
    with pytest.raises(validator.ReviewerWorkspaceError, match="TARGET_INVALID"):
        validator.validate_current_candidate_and_independence(
            workspace,
            target,
            reviewer_agent_id="reviewer-1",
            implementor_agent_id="worker-1",
        )


def test_commit_candidate_uses_commit_bytes_and_review_recomputes_manifest(
    workspace: Path, tmp_path: Path,
) -> None:
    committed = subprocess.run(
        ["git", "-C", str(workspace), "show", "HEAD:src/current.py"],
        capture_output=True,
        check=True,
    ).stdout
    commit_candidate = _candidate(workspace, kind="commit")
    (workspace / "src/current.py").write_text("print('worktree')\n", encoding="utf-8")
    worktree_candidate = _candidate(workspace, kind="worktree")
    assert commit_candidate["manifest"][0]["sha256"] == hashlib.sha256(committed).hexdigest()
    assert commit_candidate["sha256"] != worktree_candidate["sha256"]

    plan_identity = _write_stage5_plan_tree(workspace)
    tampered = _review_semantics(worktree_candidate, authority_identity=_task_authority(workspace))
    tampered["target"]["manifest"][0]["sha256"] = "0" * 64
    review_input = _write_yaml(tmp_path, "tampered-review.yaml", tampered)
    with pytest.raises(SystemExit, match="DIGEST_MISMATCH"):
        review_runtime.write_implementation_review(
            _args(
                workspace, id="review-tampered", plan_id="plan-stage5",
                task_id="task-stage5", source_root=str(workspace),
                content_file=str(review_input),
            )
        )
    assert not list(workspace.rglob("review-tampered.implementation-review.yaml"))


def test_review_writer_derives_independence_from_concrete_identities(
    workspace: Path, tmp_path: Path,
) -> None:
    plan_identity = _write_stage5_plan_tree(workspace)
    semantics = _review_semantics(_candidate(workspace), authority_identity=_task_authority(workspace))
    semantics["reviewer"] = {"agent_id": "worker-1"}
    content = _write_yaml(tmp_path, "self-review.yaml", semantics)
    with pytest.raises(SystemExit, match="NOT_INDEPENDENT"):
        review_runtime.write_implementation_review(
            _args(
                workspace, id="review-self", plan_id="plan-stage5",
                task_id="task-stage5", source_root=str(workspace),
                content_file=str(content),
            )
        )


def test_work_bundle_dispatcher_has_no_reviewer_process_or_round_commands() -> None:
    source = (REPO_ROOT / "scripts/work-bundle/dispatcher.py").read_text(encoding="utf-8")
    for command in (
        "reviewer-workspace-create", "reviewer-workspace-operation",
        "reviewer-workspace-cleanup", "reviewer-process-run",
        "begin-review-round", "complete-review-round", "review-round-status",
    ):
        assert command not in source


def test_dispatcher_exposes_only_current_stage5_commands() -> None:
    current = {
        "write-executor-result",
        "list-executor-results",
        "transition-executor-result",
        "index-executor-results",
        "build-implementation-review-candidate",
        "write-implementation-review",
        "list-implementation-reviews",
        "write-accepted-task-result",
        "list-accepted-task-results",
        "write-final-workflow-review",
        "list-final-workflow-reviews",
        "finalize-reviewed-plan",
    }
    retired = {
        "write-handoff",
        "list-handoffs",
        "set-handoff-status",
        "index-handoffs",
        "begin-review-round",
        "complete-review-round",
        "review-round-status",
        "finalize-accepted-plan",
        "finalize-with-blockers",
        "build-review-package",
        "validate-executor-result",
        "observe-task-validation",
        "archive-plan",
    }
    assert current <= dispatcher.RECOGNIZED_COMMANDS
    assert retired.isdisjoint(dispatcher.RECOGNIZED_COMMANDS)
    help_text = dispatcher.build_parser().format_help()
    assert "write-executor-result" in help_text
    assert "write-handoff" not in help_text


def test_current_dispatcher_import_graph_omits_retired_authority_modules() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", (
            "import sys; sys.path.insert(0, 'scripts/orchestration'); import dispatcher; "
            "assert 'bounded_closure' not in sys.modules; "
            "assert 'current_review_authority' not in sys.modules"
        )],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_changed_skills_end_with_practical_self_checks() -> None:
    for name in ("orch-execute-plan", "orch-create-handoff", "orch-review-plan"):
        text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        tail = text[-2200:]
        assert "## Self-check" in tail
        assert "- [ ]" in tail


def test_active_stage5_guidance_has_no_receipt_or_review_round_authority() -> None:
    paths = [
        REPO_ROOT / "skills/orch-execute-plan/SKILL.md",
        REPO_ROOT / "skills/orch-create-handoff/SKILL.md",
        REPO_ROOT / "skills/orch-review-plan/SKILL.md",
        REPO_ROOT / "references/assets/orchestration/workflow.md",
        REPO_ROOT / "rules/orchestration/orch-handoff-required.md",
        REPO_ROOT / "rules/orchestration/orch-review-completion.md",
        REPO_ROOT / "rules/orchestration/orch-bounded-closure.md",
    ]
    forbidden = ("review receipt", "publication receipt", "current-authority sidecar", "begin-review-round")
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(value in text for value in forbidden), path
