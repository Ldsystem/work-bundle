from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
import yaml

from test_orchestration_artifact_foundation import _temporary_catalog
import artifact_store
from artifact_store import (DIAGNOSTIC_LIMIT, family_policy, load_catalog,
                            canonical_artifact_path, rebuild_index, serialize_artifact,
                            validate_artifact, write_artifact)
from test_orchestration_plans import _plan_semantics, _phase_semantics, _task_semantics
from test_orchestration_stage5_current_path import _ordinary_executor_semantics, _review_semantics


CURRENT_CATALOG = Path(__file__).resolve().parents[1] / "references/assets/orchestration/contract/artifact-family-catalog-v7.yaml"


def _current_family_payload(family: str) -> dict:
    reference = {"id": "task-stage5", "sha256": "1" * 64}
    knowledge = {"action": "none", "reason": "Mechanical storage fixture."}
    candidate = {"kind": "worktree", "sha256": "1" * 64}
    common = {"artifact_type": family, "schema_version": 1,
              "date_created": "2099-01-01", "last_updated": "2099-01-01"}
    payloads = {
        "specification": {
            "id": "spec-test", "title": "Storage", "status": "draft", "project": "test",
            "purpose": "Storage boundary", "component": "orchestration", "version": "1",
            "source_knowledge": [], "related_handoffs": [], "tags": [],
            "execution_workspace": {"isolation": "existing", "profile": "test", "cleanup": "manual"},
        },
        "root-plan": {**_plan_semantics(), "id": "plan-stage4", "source_spec_id": "spec-stage4",
                      "goal": "Storage", "purpose": "Storage boundary", "component": "orchestration",
                      "version": "1", "status": "draft"},
        "phase": {**_phase_semantics(), "id": "phase-stage4", "plan_id": "plan-stage4",
                  "name": "Storage", "status": "planned", "schema_version": 2},
        "task": {**_task_semantics(), "id": "task-stage4", "plan_id": "plan-stage4",
                 "phase_id": "phase-stage4", "name": "Storage", "status": "planned", "schema_version": 3},
        "executor-result": {**_ordinary_executor_semantics(), "id": "result-test", "plan_id": "plan-stage5",
                            "phase_id": "phase-stage5", "task_id": "task-stage5", "schema_version": 2},
        "implementation-review": {
            **_review_semantics({**candidate, "base_commit": "1" * 40, "manifest": []}),
            "id": "review-test", "plan_id": "plan-stage5", "task_id": "task-stage5",
            "target_sha256": "1" * 64, "schema_version": 3,
        },
        "accepted-task-result": {
            "id": "accepted-test", "plan_id": "plan-stage5", "task_id": "task-stage5", "schema_version": 2,
            "authority_identity": reference, "product_identity": candidate, "product_sha256": "1" * 64,
            "executor_result": {"id": "result-test", "sha256": "1" * 64}, "implementation_review": None,
            "validation_outcomes": [], "unresolved_material_defects": [],
            "knowledge_disposition": knowledge, "knowledge_action": "none",
        },
        "final-workflow-review": {
            "id": "final-test", "plan_id": "plan-stage5", "specification_id": "spec-stage5",
            "plan_identity": {"id": "plan-stage5", "sha256": "1" * 64}, "candidate_identity": candidate,
            "target_sha256": "1" * 64, "coverage": {"planned": 0, "accepted": 0, "missing": []},
            "accepted_results": [], "accepted_reviews": [], "test_outcomes": [], "unresolved_material_defects": [],
            "knowledge_disposition": knowledge, "knowledge_return": {"status": "not-needed", "reference": None},
            "repository_finalization": {"repositories": [{"repository_id": "source", "root": "fixture", "head": "1" * 40}]},
            "verdict": "accept", "archive_ready": True, "reasons": ["Agent-authored fixture."],
        },
    }
    return {**common, **payloads[family]}


def test_nested_schema_diagnostic_is_actionable_and_safe(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    schema_path = tmp_path / "schemas/note-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    schema["properties"]["value"] = {
        "type": "array", "items": {"type": "object", "required": ["command"]}
    }
    schema_path.write_text(json.dumps(schema))
    policy = family_policy(load_catalog(catalog), "note")
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": [{}]},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    diagnostic = caught.value.diagnostic
    assert diagnostic["code"] == "schema.required"
    assert diagnostic["family"] == "note"
    assert diagnostic["schema"] == "note-v1"
    assert diagnostic["instance_path"] == "/value/0/command"
    assert diagnostic["schema_path"] == "/properties/value/items/required"
    assert diagnostic["expected"] == "command"
    assert "/value/0/command" in str(caught.value)

    secret = "secret-token-NEVER-PRINT\x1b[31m" * 100
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": secret},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    assert "secret-token" not in str(caught.value)
    assert "secret-token" not in json.dumps(caught.value.diagnostic)
    assert len(caught.value.diagnostic["excerpt"]) < 160


def test_union_prefers_deepest_then_fewest_branch_leaves_then_schema_order(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    schema_path = tmp_path / "schemas/note-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    schema["properties"]["value"] = {"anyOf": [
        {"type": "object", "required": ["a", "b"]},
        {"type": "object", "required": ["c"]},
        {"type": "object", "required": ["d"]},
    ]}
    schema_path.write_text(json.dumps(schema))
    policy = family_policy(load_catalog(catalog), "note")
    data = {"id": "note-001", "parent_id": "parent-001", "value": {}}
    errors = []
    for _ in range(2):
        with pytest.raises(SystemExit) as caught:
            validate_artifact(policy, data, catalog_path=catalog, bindings={"parent": "parent-001"})
        errors.append(caught.value.diagnostic)
    assert errors[0] == errors[1]
    assert errors[0]["instance_path"] == "/value/c"
    assert len(errors[0]["alternatives"]) <= 3


def test_unrelated_invalid_siblings_report_stale_index_and_remain_repairable(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    active = tmp_path / "artifacts/active"
    active.mkdir(parents=True)
    (active / "note-002.yaml").write_text("id: note-002\nparent_id: parent-001\nvalue: 42\n")
    (active / "note-003.yaml").write_text("id: [unterminated\n")
    result = write_artifact(catalog, "note", {"workspace_root": tmp_path},
                            {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                            state="active", bindings={"parent": "parent-001"})
    assert result["write_effect"] == "applied"
    assert result["index_effect"] == "stale"
    assert result["partial_effect"] is True
    assert {item["path"] for item in result["index_diagnostics"]} == {
        str(active / "note-002.yaml"), str(active / "note-003.yaml")
    }
    for identity in ("note-002", "note-003"):
        result = write_artifact(catalog, "note", {"workspace_root": tmp_path},
                                {"id": identity, "parent_id": "parent-001", "value": "repaired"},
                                state="active", bindings={"parent": "parent-001"})
    assert result["index_effect"] == "rebuilt"


@pytest.mark.parametrize("sibling", [
    "artifacts/archived/note-001.yaml", "artifacts/active/wrong.yaml",
])
def test_target_identity_conflict_refuses_before_any_write(tmp_path: Path, sibling: str) -> None:
    catalog = _temporary_catalog(tmp_path)
    conflict = tmp_path / sibling
    conflict.parent.mkdir(parents=True)
    conflict.write_text("id: note-001\nparent_id: parent-001\nvalue: 42\n")
    before = conflict.read_bytes()
    with pytest.raises(SystemExit, match="target conflict") as caught:
        write_artifact(catalog, "note", {"workspace_root": tmp_path},
                       {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                       state="active", bindings={"parent": "parent-001"}, rebuild=False)
    assert caught.value.diagnostics[0]["code"] == "target.identity-conflict"
    assert conflict.read_bytes() == before
    assert not (tmp_path / "artifacts/active/note-001.yaml").exists()
    assert not (tmp_path / "artifacts/index.jsonl").exists()


@pytest.mark.parametrize("invalid_bytes", [b"private-payload\xff", b"id: [unterminated\n"])
@pytest.mark.parametrize("existing_target", [False, True])
@pytest.mark.parametrize("exact_bindings", [False, True])
def test_malformed_other_state_locator_conflicts_only_for_exact_target_binding(
    tmp_path: Path, invalid_bytes: bytes, existing_target: bool, exact_bindings: bool,
) -> None:
    catalog = _temporary_catalog(tmp_path)
    document = yaml.safe_load(catalog.read_text())
    document["families"][0]["locator"] = {
        "template": "artifacts/{state}/{parent}/{id}.yaml", "variables": ["state", "parent", "id"],
    }
    catalog.write_text(yaml.safe_dump(document))
    policy = family_policy(load_catalog(catalog), "note")
    anchors = {"workspace_root": tmp_path}
    bindings = {"parent": "parent-001"}
    data = {"id": "note-001", "parent_id": "parent-001", "value": "old"}
    target = canonical_artifact_path(policy, anchors, identity=data["id"], state="active", bindings=bindings)
    index = tmp_path / "artifacts/index.jsonl"
    if existing_target:
        write_artifact(catalog, "note", anchors, data, state="active", bindings=bindings)
    before_target = target.read_bytes() if target.exists() else None
    before_index = index.read_bytes() if index.exists() else None
    sibling_bindings = bindings if exact_bindings else {"parent": "parent-002"}
    sibling = canonical_artifact_path(policy, anchors, identity=data["id"], state="archived", bindings=sibling_bindings)
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(invalid_bytes)
    if exact_bindings:
        with pytest.raises(SystemExit, match="target conflict") as caught:
            write_artifact(catalog, "note", anchors, {**data, "value": "new"}, state="active", bindings=bindings)
        assert caught.value.write_effect == "rejected"
        assert caught.value.partial_effect is False
        assert caught.value.diagnostic["path"] == str(sibling)
        assert (target.read_bytes() if target.exists() else None) == before_target
    else:
        result = write_artifact(catalog, "note", anchors, {**data, "value": "new"}, state="active", bindings=bindings)
        assert (result["write_effect"], result["index_effect"]) == ("applied", "stale")
        assert result["index_diagnostics"][0]["path"] == str(sibling)
    assert sibling.read_bytes() == invalid_bytes
    assert (index.read_bytes() if index.exists() else None) == before_index


@pytest.mark.parametrize("keyword,constraint,value", [
    ("enum", ["allowed"], "private-enum-input"),
    ("pattern", "^ok$", "private-pattern-input"),
    ("minLength", 10, "private"),
    ("minItems", 2, ["private-array-item"]),
    ("minimum", 5, 1),
    ("const", "fixed", "private-const-input"),
])
def test_constraint_diagnostics_expose_schema_and_never_scalar_payload(
    tmp_path: Path, keyword: str, constraint: object, value: object,
) -> None:
    catalog = _temporary_catalog(tmp_path)
    schema_path = tmp_path / "schemas/note-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    schema["properties"]["value"] = {keyword: constraint}
    schema_path.write_text(json.dumps(schema))
    policy = family_policy(load_catalog(catalog), "note")
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": value},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    diagnostic = caught.value.diagnostic
    assert diagnostic["code"] == f"schema.{keyword}"
    assert diagnostic["expected"] == constraint
    assert diagnostic["instance_path"] == "/value"
    assert "private" not in str(caught.value)
    assert "private" not in json.dumps(diagnostic)


def test_deep_union_leaf_wins_over_shallow_branch_with_fewer_failures(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    schema_path = tmp_path / "schemas/note-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    schema["properties"]["value"] = {"oneOf": [
        {"type": "string"},
        {"type": "object", "properties": {"nested": {
            "type": "object", "required": ["first", "second"]}}},
    ]}
    schema_path.write_text(json.dumps(schema))
    policy = family_policy(load_catalog(catalog), "note")
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": {"nested": {}}},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    assert caught.value.diagnostic["instance_path"] == "/value/nested/first"


def test_binding_and_existing_target_identity_conflicts_preserve_all_bytes(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    anchors = {"workspace_root": tmp_path}
    data = {"id": "note-001", "parent_id": "parent-001", "value": "ok"}
    result = write_artifact(catalog, "note", anchors, data, state="active", bindings={"parent": "parent-001"})
    target, index = Path(result["path"]), tmp_path / "artifacts/index.jsonl"
    before, index_before = target.read_bytes(), index.read_bytes()
    with pytest.raises(SystemExit) as caught:
        write_artifact(catalog, "note", anchors, {**data, "parent_id": "parent-002"},
                       state="active", bindings={"parent": "parent-002"})
    assert caught.value.diagnostic["code"] == "target.binding-conflict"
    assert (target.read_bytes(), index.read_bytes()) == (before, index_before)
    target.write_text("id: note-002\nparent_id: parent-001\nvalue: old\n")
    before = target.read_bytes()
    with pytest.raises(SystemExit) as caught:
        write_artifact(catalog, "note", anchors, data, state="active", bindings={"parent": "parent-001"})
    assert caught.value.diagnostic["code"] == "target.identity-conflict"
    assert (target.read_bytes(), index.read_bytes()) == (before, index_before)


@pytest.mark.parametrize("operation", ["writer", "index"])
def test_projection_enumerates_all_invalid_siblings_without_replacing_previous_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    catalog = _temporary_catalog(tmp_path)
    anchors = {"workspace_root": tmp_path}
    result = write_artifact(catalog, "note", anchors,
                            {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                            state="active", bindings={"parent": "parent-001"})
    index = tmp_path / "artifacts/index.jsonl"
    before = index.read_bytes()
    expected = {}
    for number in range(DIAGNOSTIC_LIMIT + 2):
        sibling = tmp_path / f"artifacts/active/note-{number + 2:03d}.yaml"
        if number % 2:
            sibling.write_text(f"id: note-{number + 2:03d}\nparent_id: parent-001\nvalue: 42\n")
            expected[str(sibling)] = "schema.type"
        else:
            sibling.write_text("id: [private-payload-broken\n")
            expected[str(sibling)] = "parse.yaml"
    if operation == "writer":
        result = write_artifact(catalog, "note", anchors,
                                {"id": "note-001", "parent_id": "parent-001", "value": "updated"},
                                state="active", bindings={"parent": "parent-001"})
        assert (result["write_effect"], result["index_effect"]) == ("applied", "stale")
        assert result["partial_effect"] is True
        assert result["index_diagnostic_count"] == len(expected)
        diagnostics = result["index_diagnostics"]
        assert yaml.safe_load(Path(result["path"]).read_text())["value"] == "updated"
    else:
        with pytest.raises(SystemExit) as caught:
            rebuild_index(catalog, "note", anchors)
        diagnostics = caught.value.diagnostics
        assert caught.value.diagnostic_count == len(expected)
        for path, code in expected.items():
            safe_path = json.dumps(path, ensure_ascii=True)[1:-1]
            assert f"{code} at {safe_path}" in str(caught.value)
        assert "\x1b" not in str(caught.value)
        assert "private-payload" not in str(caught.value)
    assert {item["path"]: item["code"] for item in diagnostics} == expected
    assert "private-payload" not in json.dumps(diagnostics)
    for item in diagnostics:
        assert len(item.get("alternatives", [])) <= 3
        assert len(item.get("excerpt", "")) < 160
    assert index.read_bytes() == before
    if operation == "index":
        synthetic = {"path": "artifacts/" + "a" * 450 + "\x1b.yaml", "code": "parse.yaml"}
        monkeypatch.setattr(artifact_store, "_scan_candidates",
                            lambda *_args: [{"diagnostic": synthetic}])
        with pytest.raises(SystemExit) as caught:
            rebuild_index(catalog, "note", anchors)
        assert caught.value.diagnostics == [synthetic]
        safe_path = json.dumps(synthetic["path"], ensure_ascii=True)[1:-1]
        assert str(caught.value) == f"Invalid index candidate(s): parse.yaml at {safe_path}"
        assert "\x1b" not in str(caught.value)
        assert index.read_bytes() == before


def test_union_alternatives_and_order_are_bounded(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    schema_path = tmp_path / "schemas/note-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    schema["properties"]["value"] = {"anyOf": [{"const": number} for number in range(15)]}
    schema_path.write_text(json.dumps(schema))
    policy = family_policy(load_catalog(catalog), "note")
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": "private"},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    assert caught.value.diagnostic["expected"] == 0
    assert [item["expected"] for item in caught.value.diagnostic["alternatives"]] == [1, 2, 3]
    assert caught.value.diagnostic["alternative_count"] == 14


def test_invalid_utf8_sibling_reports_applied_write_and_repairable_projection(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    sibling = tmp_path / "artifacts/active/note-002.yaml"
    sibling.parent.mkdir(parents=True)
    sibling.write_bytes(b"private-payload\xff")
    result = write_artifact(catalog, "note", {"workspace_root": tmp_path},
                            {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                            state="active", bindings={"parent": "parent-001"})
    assert result["write_effect"] == "applied"
    assert result["index_effect"] == "stale"
    assert result["index_diagnostics"][0]["code"] == "parse.encoding"
    assert result["index_diagnostics"][0]["path"] == str(sibling)
    assert "private-payload" not in json.dumps(result)
    assert sibling.read_bytes() == b"private-payload\xff"
    repaired = write_artifact(catalog, "note", {"workspace_root": tmp_path},
                              {"id": "note-002", "parent_id": "parent-001", "value": "ok"},
                              state="active", bindings={"parent": "parent-001"})
    assert repaired["index_effect"] == "rebuilt"


def test_postwrite_integrity_failure_reports_applied_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = _temporary_catalog(tmp_path)
    atomic = artifact_store.atomic_write_bytes

    def corrupt_after_write(path: Path, content: bytes) -> None:
        atomic(path, content + b"unexpected bytes")

    monkeypatch.setattr(artifact_store, "atomic_write_bytes", corrupt_after_write)
    with pytest.raises(SystemExit) as caught:
        write_artifact(catalog, "note", {"workspace_root": tmp_path},
                       {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                       state="active", bindings={"parent": "parent-001"})
    assert caught.value.write_effect == "applied"
    assert caught.value.partial_effect is True
    assert caught.value.index_effect == "not-requested"
    assert caught.value.diagnostic["code"] == "write.integrity"
    assert (tmp_path / "artifacts/active/note-001.yaml").is_file()


def test_additional_property_diagnostic_retains_constraint_and_safe_path(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    policy = family_policy(load_catalog(catalog), "note")
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": "ok",
                                   "unexpected\x1b[31m": "private-payload"},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    diagnostic = caught.value.diagnostic
    assert diagnostic["expected"] == {"additional_properties": False,
                                       "allowed_properties": ["id", "parent_id", "value"]}
    assert diagnostic["instance_path"] == "/unexpected\\u001b[31m"
    assert "private-payload" not in json.dumps(diagnostic)
    assert "\x1b" not in str(caught.value)


def test_required_alternatives_identify_distinct_missing_fields(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    schema_path = tmp_path / "schemas/note-v1.schema.json"
    schema = json.loads(schema_path.read_text())
    schema["properties"]["value"] = {"type": "object", "required": ["first", "second"]}
    schema_path.write_text(json.dumps(schema))
    policy = family_policy(load_catalog(catalog), "note")
    with pytest.raises(SystemExit) as caught:
        validate_artifact(policy, {"id": "note-001", "parent_id": "parent-001", "value": {}},
                          catalog_path=catalog, bindings={"parent": "parent-001"})
    diagnostic = caught.value.diagnostic
    assert diagnostic["instance_path"] == "/value/first"
    assert diagnostic["alternatives"][0]["instance_path"] == "/value/second"


def test_index_io_diagnostic_names_failed_projection(tmp_path: Path) -> None:
    catalog = _temporary_catalog(tmp_path)
    index = tmp_path / "artifacts/index.jsonl"
    index.mkdir(parents=True)
    result = write_artifact(catalog, "note", {"workspace_root": tmp_path},
                            {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                            state="active", bindings={"parent": "parent-001"})
    assert result["write_effect"] == "applied"
    assert result["index_effect"] == "stale"
    assert result["index_diagnostics"][0]["path"] == str(index)
    assert result["index_diagnostics"][0]["code"] == "index.io"


def test_write_result_uses_verified_bytes_without_second_postwrite_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = _temporary_catalog(tmp_path)
    target = tmp_path / "artifacts/active/note-001.yaml"
    read_bytes = Path.read_bytes
    reads = []

    def read_once(path: Path) -> bytes:
        if path == target:
            reads.append(path)
            if len(reads) > 1:
                raise OSError("later target read is unavailable")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_once)
    result = write_artifact(catalog, "note", {"workspace_root": tmp_path},
                            {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
                            state="active", bindings={"parent": "parent-001"}, rebuild=False)
    assert result["write_effect"] == "applied"
    assert result["digest"] == hashlib.sha256(read_bytes(target)).hexdigest()
    assert len(reads) == 1


@pytest.mark.parametrize("family", [
    "specification", "root-plan", "phase", "task", "executor-result",
    "implementation-review", "accepted-task-result", "final-workflow-review",
])
def test_current_catalog_families_create_repair_and_reject_target_conflicts(tmp_path: Path, family: str) -> None:
    policy = family_policy(load_catalog(CURRENT_CATALOG), family)
    anchors = {"workspace_root": tmp_path}
    data = _current_family_payload(family)
    bindings = {item["name"]: data[item["field"]] for item in policy["relationships"]["bindings"]}
    initial = write_artifact(CURRENT_CATALOG, family, anchors, data, state="active", bindings=bindings)
    assert (initial["write_effect"], initial["index_effect"]) == ("applied", "rebuilt")
    target = Path(initial["path"])
    index = tmp_path / policy["index"]["path"]
    sibling_data = {**data, "id": data["id"] + "-sibling"}
    sibling = canonical_artifact_path(policy, anchors, identity=sibling_data["id"], state="active", bindings=bindings)
    sibling.parent.mkdir(parents=True, exist_ok=True)
    malformed = serialize_artifact(policy, {**sibling_data, "schema_version": "invalid-version"})
    sibling.write_bytes(malformed)
    previous_index = index.read_bytes()
    repaired_target = write_artifact(CURRENT_CATALOG, family, anchors, {**data, "last_updated": "2099-01-02"},
                                     state="active", bindings=bindings)
    assert repaired_target["write_effect"] == "applied"
    assert repaired_target["index_effect"] == "stale"
    assert repaired_target["index_diagnostic_count"] == 1
    assert repaired_target["index_diagnostics"][0]["path"] == str(sibling)
    assert (index.read_bytes(), sibling.read_bytes()) == (previous_index, malformed)
    repaired_sibling = write_artifact(CURRENT_CATALOG, family, anchors, sibling_data, state="active", bindings=bindings)
    assert repaired_sibling["index_effect"] == "rebuilt"
    assert len(index.read_text().splitlines()) == 2
    collision = canonical_artifact_path(policy, anchors, identity=data["id"], state="archived", bindings=bindings)
    collision.parent.mkdir(parents=True, exist_ok=True)
    collision.write_bytes(serialize_artifact(policy, {**data, "schema_version": "invalid-version"}))
    before = (target.read_bytes(), sibling.read_bytes(), collision.read_bytes(), index.read_bytes())
    with pytest.raises(SystemExit) as caught:
        write_artifact(CURRENT_CATALOG, family, anchors, data, state="active", bindings=bindings)
    assert caught.value.write_effect == "rejected"
    assert caught.value.diagnostic["code"] == "target.identity-conflict"
    assert (target.read_bytes(), sibling.read_bytes(), collision.read_bytes(), index.read_bytes()) == before
