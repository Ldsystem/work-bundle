"""Semantic scaffold behavior at the public route and current writer boundaries."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from test_orchestration_stage5_current_path import _write_stage5_plan_tree, workspace
import dispatcher
import artifact_store
import scaffolds
from test_orchestration_writer_repair import _case


FAMILIES = (
    "specification-v1", "plan-v1", "phase-v2", "task-v3", "executor-result-v2",
    "implementation-review-v3", "accepted-task-result-v2", "final-workflow-review-v1",
)


def _argv(family: str) -> list[str]:
    argv = ["scaffold", "--family", family]
    if family == "plan-v1":
        argv += ["--source-spec-id", "spec-stage5"]
    elif family != "specification-v1":
        argv += ["--plan-id", "plan-stage5"]
    if family == "task-v3":
        argv += ["--phase-id", "phase-stage5", "--task-id", "task-new"]
    if family in {"executor-result-v2", "implementation-review-v3", "accepted-task-result-v2"}:
        argv += ["--task-id", "task-stage5"]
    return argv


@pytest.mark.parametrize("family, explicit_status", [
    *((family, False) for family in FAMILIES),
    ("phase-v2", True), ("task-v3", True),
])
def test_each_shell_is_consumed_by_its_actual_writer_after_explicit_authorship(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str, explicit_status: bool,
) -> None:
    owner = scaffolds.SUPPORTED_FAMILIES[family][0]
    path, document, body, writer_args, writer, policy = _case(workspace, tmp_path, monkeypatch, owner)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    scaffold_argv = _argv(family)
    if owner == "task":
        scaffold_argv += ["--task-id", "task-stage5"]
    if explicit_status:
        scaffold_argv += ["--status", "planned"]
    before = {item: item.read_bytes() for item in workspace.rglob("*") if item.is_file()}
    shell = scaffolds.build_scaffold(dispatcher.build_parser().parse_args(scaffold_argv))
    if explicit_status:
        assert shell["invocation_inputs"]["status"] == "planned"
    assert before == {item: item.read_bytes() for item in workspace.rglob("*") if item.is_file()}
    assert set(shell["semantic_input"]).isdisjoint(shell["script_owned_fields"])
    # Populate every emitted editable key with explicitly authored fixture values.
    # A missing/wrong key fails here rather than being hidden by wholesale replacement.
    filled = {key: document[key] for key in shell["semantic_input"]}
    content = Path(writer_args.content_file)
    content.write_bytes(artifact_store.serialize_markdown_mapping(filled, body)
                        if owner == "specification" else yaml.safe_dump(filled).encode())
    # The emitted invocation keys must also be accepted by the public writer CLI.
    argv = [shell["writer_command"], "--content-file", str(content)]
    for key, value in shell["invocation_inputs"].items():
        if isinstance(value, str) and value.startswith("<agent-authored-"):
            value = getattr(writer_args, key)
        argv += ["--" + key.replace("_", "-"), str(value)]
    parsed_writer = dispatcher.build_parser().parse_args(argv)
    writer(parsed_writer)
    bindings = {item["name"]: document[item["field"]]
                for item in policy["relationships"]["bindings"] if document.get(item["field"]) is not None}
    stored = artifact_store.read_artifact(scaffolds.CATALOG, owner, {"workspace_root": workspace},
                                         identity=document["id"], state="active", bindings=bindings)
    assert stored["data"]["id"] == document["id"]
    assert Path(stored["path"]) == path


@pytest.mark.parametrize("options, message", [
    (["--plan-id", "../escape"], "identity"),
    (["--plan-id", "plan-missing"], "canonical"),
    (["--phase-id", "phase-missing"], "not found"),
    (["--task-id", "../escape"], "identity"),
    (["--source-spec-id", "spec-mismatch"], "does not match"),
    (["--source-id", "REQ-009", "--source-id", "REQ-009"], "Duplicate"),
    (["--id", "task-ambiguous"], "Unsupported scaffold invocation binding"),
])
def test_task_binding_failures_have_no_output_or_filesystem_effect(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    options: list[str], message: str,
) -> None:
    _write_stage5_plan_tree(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    args = dispatcher.build_parser().parse_args(_argv("task-v3") + options)
    with pytest.raises(SystemExit, match=message):
        args.func(args)
    assert capsys.readouterr().out == ""
    assert before == {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}


@pytest.mark.parametrize("family", ["phase-v2", "task-v3"])
@pytest.mark.parametrize("status", ["draft", "verified", "blocked"])
def test_phase_and_task_statuses_rejected_by_writers_refuse_before_output(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    family: str, status: str,
) -> None:
    _write_stage5_plan_tree(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    args = dispatcher.build_parser().parse_args(_argv(family) + ["--status", status])
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    with pytest.raises(SystemExit, match="Unsupported writer qualification status"):
        args.func(args)
    assert capsys.readouterr().out == ""
    assert before == {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}


def test_explicit_scope_does_not_grow_with_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tuple(scaffolds.SUPPORTED_FAMILIES) == FAMILIES
    with pytest.raises(SystemExit, match="Unsupported scaffold family"):
        scaffolds.build_scaffold(type("Args", (), {"family": "future-v1"})())
    with pytest.raises(SystemExit):
        dispatcher.build_parser().parse_args(["scaffold", "--family", "future-v1"])


def test_scaffold_does_not_choose_verdicts_or_acceptance(
    workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage5_plan_tree(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    for family in FAMILIES:
        shell = scaffolds.build_scaffold(dispatcher.build_parser().parse_args(_argv(family)))
        semantic = shell["semantic_input"]
        for key in ("verdict", "archive_ready", "acceptance_review", "reviewed_obligations",
                    "validation_outcomes", "coverage", "task_fit", "knowledge_disposition"):
            if key in semantic:
                assert semantic[key].startswith("<agent-authored-")
        assert "writer_command" not in semantic
        assert "resolved_context" not in semantic


@pytest.mark.parametrize("family, options, message", [
    ("plan-v1", ["--source-spec-id", "spec-missing"], "not found"),
    ("executor-result-v2", ["--task-id", "task-missing"], "Unknown canonical task"),
    ("executor-result-v2", ["--phase-id", "phase-mismatch"], "does not match"),
    ("implementation-review-v3", ["--source-root", "/missing-scaffold-source"], "existing repository"),
    ("final-workflow-review-v1", ["--task-id", "task-stage5"], "Unsupported scaffold invocation"),
    ("specification-v1", ["--status", "unknown"], "qualification status"),
    ("specification-v1", ["--id", "../escape"], "identity"),
])
def test_other_family_binding_rejections_before_output(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    family: str, options: list[str], message: str,
) -> None:
    _write_stage5_plan_tree(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    with pytest.raises(SystemExit, match=message):
        dispatcher.build_parser().parse_args(_argv(family) + options).func(
            dispatcher.build_parser().parse_args(_argv(family) + options)
        )
    assert capsys.readouterr().out == ""


def test_resolution_reuses_source_projection_for_authority_aliases_and_multiline_units(
    workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_stage5_plan_tree(workspace)
    source = artifact_store.read_artifact(scaffolds.CATALOG, "specification", {"workspace_root": workspace},
                                         identity="spec-stage5", state="active")
    data = {**source["data"], "source_knowledge": [{"path": "reference-only", "constraint": "An accepted authority constraint."}]}
    artifact_store.write_artifact(scaffolds.CATALOG, "specification", {"workspace_root": workspace}, data,
                                  state="active", body=source["body"] + "\n- **API-020:** A named unit.\n  Continued accepted meaning.\n")
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    args = dispatcher.build_parser().parse_args(_argv("task-v3") + ["--source-id", "AUTH-001", "--source-id", "API-020"])
    shell = scaffolds.build_scaffold(args)
    context = shell["resolved_context"]["source_ids"]
    assert context[0]["semantic"] == "An accepted authority constraint."
    assert context[1]["semantic"] == "API-020: A named unit. Continued accepted meaning."
    assert all(item["semantic"] == "<agent-authored-obligation>" for item in shell["semantic_input"]["source_obligations"])


def test_review_scaffold_exposes_target_contract_without_computing_candidate_or_verdict(
    workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import execution_context
    import review_runtime
    _write_stage5_plan_tree(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    def unexpected(*_args, **_kwargs):
        pytest.fail("A scaffold cannot compute a candidate or issue a review")
    monkeypatch.setattr(execution_context, "build_implementation_review_candidate", unexpected)
    monkeypatch.setattr(review_runtime, "_candidate_validator", unexpected)
    shell = scaffolds.build_scaffold(dispatcher.build_parser().parse_args(_argv("implementation-review-v3")))
    assert shell["semantic_input"]["target"] == {
        "kind": "<agent-authored-kind>",
        "base_commit": "<agent-authored-candidate-commit-or-worktree-baseline>",
        "manifest": "<agent-authored-manifest>",
        "sha256": "<agent-authored-sha256>",
    }
    assert shell["semantic_input"]["verdict"] == "<agent-authored-verdict>"
    assert "target" not in shell["script_owned_fields"]


def test_integrated_review_and_non_delivery_executor_shells_use_current_bindings(
    workspace: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_orchestration_stage5_current_path import _write_peer_task
    _write_stage5_plan_tree(workspace)
    _write_peer_task(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    integrated = scaffolds.build_scaffold(dispatcher.build_parser().parse_args([
        "scaffold", "--family", "implementation-review-v3", "--plan-id", "plan-stage5",
    ]))
    assert "task_id" not in integrated["invocation_inputs"]
    assert integrated["semantic_input"]["scope"] == "<agent-authored-scope>"
    executor = scaffolds.build_scaffold(dispatcher.build_parser().parse_args(
        _argv("executor-result-v2") + ["--task-id", "task-peer"]
    ))
    assert "phase_handoff" not in executor["semantic_input"]


@pytest.mark.parametrize("family", FAMILIES)
def test_structural_overrides_still_refuse_at_the_actual_writer_reader(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, family: str,
) -> None:
    owner = scaffolds.SUPPORTED_FAMILIES[family][0]
    _path, _document, _body, args, writer, _policy = _case(workspace, tmp_path, monkeypatch, owner)
    content = Path(args.content_file)
    if owner == "specification":
        semantic, body = artifact_store.read_markdown_artifact(content)
        content.write_bytes(artifact_store.serialize_markdown_mapping({**semantic, "schema_version": 1}, body))
    else:
        semantic = artifact_store.read_yaml_mapping(content)
        content.write_text(yaml.safe_dump({**semantic, "schema_version": 1}))
    before = {item: item.read_bytes() for item in workspace.rglob("*") if item.is_file()}
    with pytest.raises(SystemExit, match="structural field override"):
        writer(args)
    assert before == {item: item.read_bytes() for item in workspace.rglob("*") if item.is_file()}


def test_unverified_source_and_future_schema_refuse_before_output(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _write_stage5_plan_tree(workspace)
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    source = artifact_store.read_artifact(scaffolds.CATALOG, "specification", {"workspace_root": workspace},
                                         identity="spec-stage5", state="active")
    artifact_store.write_artifact(scaffolds.CATALOG, "specification", {"workspace_root": workspace},
                                  {**source["data"], "status": "draft"}, state="active", body=source["body"])
    with pytest.raises(SystemExit, match="active and verified"):
        args = dispatcher.build_parser().parse_args(_argv("plan-v1"))
        args.func(args)
    original = scaffolds.family_policy
    monkeypatch.setattr(scaffolds, "family_policy", lambda catalog, family:
                        {**original(catalog, family), "schema": {"id": "future-v99"}})
    with pytest.raises(SystemExit, match="explicit supported schema"):
        args.func(args)
    assert capsys.readouterr().out == ""


def test_task_scaffold_resolves_source_without_authoring_obligation(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _write_stage5_plan_tree(workspace)
    args = dispatcher.build_parser().parse_args([
        "scaffold", "--family", "task-v3", "--workspace-root", str(workspace),
        "--plan-id", "plan-stage5", "--phase-id", "phase-stage5",
        "--task-id", "task-new", "--source-id", "REQ-009",
    ])
    import scaffolds
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    args.func(args)
    output = json.loads(capsys.readouterr().out)
    assert output["semantic_input"]["source_ids"] == ["REQ-009"]
    assert output["semantic_input"]["source_obligations"] == [
        {"source_id": "REQ-009", "semantic": "<agent-authored-obligation>"}
    ]
    assert "Complete Stage 5 finalization" in output["resolved_context"]["source_ids"][0]["semantic"]
    assert set(output["semantic_input"]).isdisjoint(output["script_owned_fields"])
    assert before == {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}


def test_unknown_source_id_refuses_before_output(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    _write_stage5_plan_tree(workspace)
    args = dispatcher.build_parser().parse_args([
        "scaffold", "--family", "task-v3", "--plan-id", "plan-stage5",
        "--phase-id", "phase-stage5", "--task-id", "task-new", "--source-id", "REQ-999",
    ])
    import scaffolds
    monkeypatch.setattr(scaffolds, "resolve_workspace_root", lambda _args: workspace)
    with pytest.raises(SystemExit, match="Unknown source ID"):
        args.func(args)
    assert capsys.readouterr().out == ""
