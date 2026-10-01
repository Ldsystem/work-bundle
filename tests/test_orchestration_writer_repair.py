"""Writer-only active repair and truthful family projection observations."""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import pytest
import yaml

from test_orchestration_stage5_current_path import (
    CATALOG, _args, _write_finalization_case, workspace,
)
from test_orchestration_plans import (
    _args as planning_args, _create_tree, workspace as planning_workspace,
)
import artifact_store
import handoffs
import plans
import review_runtime
import specs


FAMILIES = ("specification", "root-plan", "phase", "task", "executor-result",
            "implementation-review", "accepted-task-result", "final-workflow-review")


def _case(workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str):
    _write_finalization_case(workspace)
    monkeypatch.setattr(specs, "resolve_workspace_root", lambda _args: workspace)
    monkeypatch.setattr(specs, "resolve_working_workspace", lambda _root: None)
    for module in (specs, plans):
        monkeypatch.setattr(module, "rel", lambda path, _args: Path(path).relative_to(workspace).as_posix())
    policy = artifact_store.family_policy(artifact_store.load_catalog(CATALOG), family)
    path = next(workspace.glob(artifact_store._candidate_pattern(policy, "active")))
    document, body = (artifact_store.read_markdown_artifact(path) if family == "specification"
                      else (artifact_store.read_yaml_mapping(path), ""))
    if family in {"phase", "task"}:
        plan_path = next(workspace.rglob("*.plan.yaml"))
        plan = artifact_store.read_yaml_mapping(plan_path)
        artifact_store.write_artifact(CATALOG, "root-plan", {"workspace_root": workspace},
                                     {**plan, "status": "draft"}, state="active",
                                     bindings={"source_spec": "spec-stage5"})
    structural = {
        "specification": specs.STRUCTURAL_INPUT_FIELDS,
        "root-plan": plans.PLAN_STRUCTURAL_INPUT_FIELDS,
        "phase": plans.PHASE_STRUCTURAL_INPUT_FIELDS,
        "task": plans.TASK_STRUCTURAL_INPUT_FIELDS,
        "executor-result": handoffs.STRUCTURAL_FIELDS,
    }.get(family, review_runtime.CURRENT_STRUCTURAL_FIELDS)
    semantic = {key: value for key, value in document.items() if key not in structural}
    if family == "accepted-task-result":
        semantic.pop("authority_identity", None)
    content = tmp_path / "writer-repair-input.txt"
    content.write_bytes(artifact_store.serialize_markdown_mapping(semantic, body)
                        if family == "specification" else yaml.safe_dump(semantic).encode())
    args = argparse.Namespace(
        workspace_root=str(workspace), project_root=None, id=document["id"],
        plan_id="plan-stage5", phase_id="phase-stage5", task_id="task-stage5",
        source_spec_id="spec-stage5", title="Repaired canonical artifact",
        purpose="Exercise canonical repair", component="orchestration", version="1",
        status="planned" if family in {"phase", "task"} else "draft",
        filename=None, content_file=str(content), source_root=str(workspace),
    )
    if family in {"specification", "root-plan", "final-workflow-review"}:
        args.task_id = None
    writer = {
        "specification": specs.cmd_write_spec, "root-plan": plans.cmd_write_plan,
        "phase": plans.cmd_write_phase, "task": plans.cmd_write_task,
        "executor-result": handoffs.write_executor_result,
        "implementation-review": review_runtime.write_implementation_review,
        "accepted-task-result": review_runtime.write_accepted_task_result,
        "final-workflow-review": review_runtime.write_final_workflow_review,
    }[family]
    return path, document, body, args, writer, policy


def _store(path: Path, family: str, document: dict, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(artifact_store.serialize_markdown_mapping(document, body)
                     if family == "specification" else yaml.safe_dump(document).encode())


def _list(args: argparse.Namespace, family: str) -> list[dict]:
    if family == "specification":
        return specs.index_specs(args)
    if family in plans.PLAN_FAMILIES:
        return plans.index_plans(args)
    if family == "executor-result":
        return handoffs.list_executor_results(args)
    return review_runtime._rows(args, family)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("damage", ["missing", "schema", "parse", "invalid-date"])
def test_all_canonical_writers_create_and_repair_active_targets(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str, damage: str,
) -> None:
    path, document, body, args, writer, _policy = _case(workspace, tmp_path, monkeypatch, family)
    if damage == "missing":
        path.unlink()
    elif damage == "parse":
        path.write_text("---\n[invalid\n---\n" if family == "specification" else "[invalid\n")
    elif damage == "invalid-date":
        _store(path, family, {**document, "date_created": "invalid-date"}, body)
    else:
        # Omit all editable content while keeping recoverable immutable metadata.
        kept = {key: value for key, value in document.items()
                if key in {"id", "plan_id", "phase_id", "task_id", "source_spec_id",
                           "date_created", "status", "scope"}}
        _store(path, family, kept, body)
    writer(args)
    bindings = {binding["name"]: document[binding["field"]]
                for binding in _policy["relationships"]["bindings"]
                if document.get(binding["field"]) is not None}
    repaired = artifact_store.read_artifact(CATALOG, family, {"workspace_root": workspace},
                                            identity=document["id"], state="active", bindings=bindings)
    assert repaired["data"]["id"] == document["id"]
    if damage == "schema":
        assert repaired["data"]["date_created"] == document["date_created"]


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("conflict", ["identity", "binding", "lifecycle", "archived-only"])
def test_recoverable_target_conflicts_refuse_without_changing_bytes(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str, conflict: str,
) -> None:
    path, document, body, args, writer, policy = _case(workspace, tmp_path, monkeypatch, family)
    altered = dict(document)
    if conflict == "identity":
        altered["id"] = document["id"] + "-other"
    elif conflict == "binding":
        if not policy["relationships"]["bindings"]:
            pytest.skip("Specification has no declared parent binding")
        altered[policy["relationships"]["bindings"][0]["field"]] += "-other"
    else:
        bindings = {binding["name"]: document[binding["field"]]
                    for binding in policy["relationships"]["bindings"]
                    if document.get(binding["field"]) is not None}
        archived = artifact_store.canonical_artifact_path(policy, {"workspace_root": workspace},
                    identity=document["id"], state="archived", bindings=bindings)
        _store(archived, family, document, body)
    if conflict == "archived-only":
        path.unlink()
        before = None
    else:
        _store(path, family, altered, body)
        before = path.read_bytes()
    with pytest.raises(artifact_store.ArtifactError) as raised:
        writer(args)
    assert raised.value.write_effect == "rejected"
    assert raised.value.diagnostic["code"].startswith("target.")
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize("family", FAMILIES)
def test_all_families_list_and_repair_unrelated_siblings_until_index_converges(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], family: str,
) -> None:
    path, document, body, args, writer, policy = _case(workspace, tmp_path, monkeypatch, family)
    capsys.readouterr()
    identities = [document["id"] + "-peer-one", document["id"] + "-peer-two"]
    bindings = {binding["name"]: document[binding["field"]]
                for binding in policy["relationships"]["bindings"]
                if document.get(binding["field"]) is not None}
    siblings = []
    for identity in identities:
        sibling = artifact_store.canonical_artifact_path(policy, {"workspace_root": workspace},
                        identity=identity, state="active", bindings=bindings)
        _store(sibling, family, {**document, "id": identity, "schema_version": "invalid"}, body)
        siblings.append(sibling)
    index_path = workspace / policy["index"]["path"]
    index_before = index_path.read_bytes()
    result = writer(args)
    reports = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    if result is not None:
        reports.append(result)
    stale = [report for report in reports if report["index_effect"] == "stale"]
    assert stale
    assert any({item["path"] for item in report["index_diagnostics"]} == set(map(str, siblings))
               for report in stale)
    assert index_path.read_bytes() == index_before
    rows = _list(args, family)
    assert document["id"] in {row["id"] for row in rows}
    assert not set(identities).intersection(row["id"] for row in rows)
    listed = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert any({item["path"] for item in report["index_diagnostics"]} == set(map(str, siblings))
               for report in listed)
    if family == "specification":
        specs.cmd_set_spec_status(argparse.Namespace(**{**vars(args), "status": "verified"}))
    for identity in identities:
        args.id = identity
        if family == "phase":
            args.phase_id = identity
        elif family == "task":
            args.task_id = identity
            # Distinct draft tasks do not allocate the same source write paths.
            semantic = artifact_store.read_yaml_mapping(Path(args.content_file))
            semantic["target_files"] = ["src/" + identity + ".py"]
            Path(args.content_file).write_text(yaml.safe_dump(semantic))
        writer(args)
    indexed = artifact_store.rebuild_index(CATALOG, family, {"workspace_root": workspace})
    assert indexed["count"] == 3


@pytest.mark.parametrize("family", FAMILIES)
def test_listing_reports_duplicate_lifecycle_identity_without_first_file_abort(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], family: str,
) -> None:
    path, document, body, args, _writer, policy = _case(workspace, tmp_path, monkeypatch, family)
    bindings = {binding["name"]: document[binding["field"]]
                for binding in policy["relationships"]["bindings"]
                if document.get(binding["field"]) is not None}
    duplicate = artifact_store.canonical_artifact_path(policy, {"workspace_root": workspace},
                            identity=document["id"], state="archived", bindings=bindings)
    _store(duplicate, family, document, body)
    capsys.readouterr()
    rows = _list(args, family)
    assert document["id"] in {row["id"] for row in rows}
    reports = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert any(item["code"] == "identity.duplicate" and item["path"] == str(duplicate)
               for report in reports for item in report["index_diagnostics"])


@pytest.mark.parametrize("family", ["specification", "root-plan", "phase", "task"])
def test_index_command_does_not_claim_stale_projection_was_indexed(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], family: str,
) -> None:
    path, document, body, args, _writer, _policy = _case(workspace, tmp_path, monkeypatch, family)
    _store(path, family, {**document, "schema_version": "invalid"}, body)
    capsys.readouterr()
    command = specs.cmd_index_specs if family == "specification" else plans.cmd_index_plans
    with pytest.raises(artifact_store.ArtifactError):
        command(args)
    assert "indexed" not in capsys.readouterr().out


def test_planning_index_reports_malformed_siblings_across_all_families(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, document, body, args, _writer, _policy = _case(workspace, tmp_path, monkeypatch, "root-plan")
    phase = next(workspace.rglob("*.phase.yaml"))
    _store(root, "root-plan", {**document, "schema_version": "invalid"})
    _store(phase, "phase", {**artifact_store.read_yaml_mapping(phase), "schema_version": "invalid"})
    with pytest.raises(artifact_store.ArtifactError) as raised:
        plans.cmd_index_plans(args)
    assert {item["path"] for item in raised.value.diagnostics} == {str(root), str(phase)}


@pytest.mark.parametrize("damage", ["schema", "parse"])
def test_focused_amendment_repairs_malformed_existing_task(
    planning_workspace: Path, tmp_path: Path,
    capsys: pytest.CaptureFixture[str], damage: str,
) -> None:
    _root, _phase, path = _create_tree(planning_workspace, tmp_path)
    document = artifact_store.read_yaml_mapping(path)
    args = planning_args(planning_workspace, id=None, plan_id="plan-stage4",
                         phase_id="phase-stage4", task_id="task-stage4",
                         content_file=str(tmp_path / "task.yaml"), status="planned")
    if damage == "schema":
        _store(path, "task", {**document, "steps": "invalid"})
    else:
        path.write_text("[invalid\n")
    capsys.readouterr()
    plans.cmd_amend_task(args)
    output = json.loads(capsys.readouterr().out)
    assert output["write_effect"] == "applied"
    assert output["index_effect"] == "rebuilt"
    assert output["semantic_impact"] == "controller-assessment-required"
    assert artifact_store.read_yaml_mapping(path)["date_created"] == document["date_created"]
    compiled = artifact_store.read_yaml_mapping(planning_workspace / output["brief"])
    assert compiled["task_brief"]["task_id"] == "task-stage4"


@pytest.mark.parametrize("conflict", ["identity", "binding", "lifecycle"])
def test_amendment_target_conflicts_do_not_publish_a_brief(
    planning_workspace: Path, tmp_path: Path, conflict: str,
) -> None:
    _root, _phase, path = _create_tree(planning_workspace, tmp_path)
    document = artifact_store.read_yaml_mapping(path)
    altered = dict(document)
    if conflict == "identity":
        altered["id"] = "task-other"
    elif conflict == "binding":
        altered["phase_id"] = "phase-other"
    else:
        policy = artifact_store.family_policy(artifact_store.load_catalog(CATALOG), "task")
        duplicate = artifact_store.canonical_artifact_path(policy, {"workspace_root": planning_workspace},
                    identity=document["id"], state="archived", bindings={"plan": "plan-stage4", "phase": "phase-stage4"})
        _store(duplicate, "task", document)
    _store(path, "task", altered)
    before = path.read_bytes()
    args = planning_args(planning_workspace, id=None, plan_id="plan-stage4",
                         phase_id="phase-stage4", task_id="task-stage4",
                         content_file=str(tmp_path / "task.yaml"), status="planned")
    with pytest.raises(artifact_store.ArtifactError) as raised:
        plans.cmd_amend_task(args)
    assert raised.value.write_effect == "rejected"
    assert path.read_bytes() == before
    assert not (planning_workspace / ".work-bundle/runtime/execution").exists()


def test_ordinary_compiler_read_remains_strict_for_malformed_task(
    planning_workspace: Path, tmp_path: Path,
) -> None:
    import execution_context

    _root, _phase, path = _create_tree(planning_workspace, tmp_path)
    document = artifact_store.read_yaml_mapping(path)
    _store(path, "task", {**document, "steps": "invalid"})
    args = argparse.Namespace(workspace_root=str(planning_workspace), task=str(path),
                              _resolved_root=str(planning_workspace))
    with pytest.raises(artifact_store.ArtifactError):
        execution_context.build_task_brief(args)


def _review_case(workspace: Path, tmp_path: Path):
    _write_finalization_case(workspace)
    path = next(workspace.rglob("review-stage5.implementation-review.yaml"))
    document = yaml.safe_load(path.read_text())
    semantic = {key: value for key, value in document.items()
                if key not in review_runtime.CURRENT_STRUCTURAL_FIELDS}
    content = tmp_path / "review-repair-input.yaml"
    content.write_text(yaml.safe_dump(semantic))
    args = _args(workspace, id="review-stage5", plan_id="plan-stage5",
                 task_id="task-stage5", source_root=str(workspace), content_file=str(content))
    return path, document, args


def test_review_repairs_editable_target_and_reports_all_unrelated_siblings(
    workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    path, document, args = _review_case(workspace, tmp_path)
    malformed = {**document, "focused_observations": "invalid"}
    path.write_text(yaml.safe_dump(malformed))
    siblings = []
    for number in range(22):
        identity = f"review-peer-{number:02d}"
        sibling = path.with_name(identity + ".implementation-review.yaml")
        sibling.write_text(yaml.safe_dump({**malformed, "id": identity}))
        siblings.append(sibling)
    expected_diagnostics = {(str(sibling), "schema.type") for sibling in siblings}
    result = review_runtime.write_implementation_review(args)
    assert result["write_effect"] == "applied"
    assert result["index_effect"] == "stale"
    assert result["index_diagnostic_count"] == len(siblings)
    assert {(item["path"], item["code"]) for item in result["index_diagnostics"]} == expected_diagnostics
    repaired = yaml.safe_load(path.read_text())
    assert repaired["date_created"] == document["date_created"]
    assert isinstance(repaired["focused_observations"], list)
    rows = review_runtime.list_implementation_reviews(_args(workspace))
    assert [row["id"] for row in rows] == ["review-stage5"]
    report = json.loads(capsys.readouterr().err)
    assert report["index_effect"] == "stale"
    assert report["index_diagnostic_count"] == len(siblings)
    assert {(item["path"], item["code"]) for item in report["index_diagnostics"]} == expected_diagnostics
    for sibling in siblings:
        args.id = sibling.name.removesuffix(".implementation-review.yaml")
        result = review_runtime.write_implementation_review(args)
    assert result["index_effect"] == "rebuilt"
    assert len(review_runtime.list_implementation_reviews(_args(workspace))) == len(siblings) + 1
