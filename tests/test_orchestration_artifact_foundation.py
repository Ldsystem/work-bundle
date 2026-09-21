from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCH_ROOT))

from artifact_inputs import _read_structured
from artifact_store import (
    atomic_write_bytes,
    canonical_artifact_path,
    family_policy,
    load_catalog,
    read_markdown_artifact,
    read_artifact,
    read_yaml_mapping,
    rebuild_index,
    serialize_artifact,
    transition_artifact,
    validate_artifact,
    write_artifact,
)
from specs import CATALOG_PATH as SPEC_CATALOG, archive_spec_for_forced_finalization, index_specs, replace_front_matter_value


RUNTIME_CATALOG = (
    REPO_ROOT
    / "references/assets/orchestration/contract/artifact-family-catalog-v1.yaml"
)


@pytest.fixture(autouse=True)
def isolated_workspace_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = "wb-artifact-foundation"
    control = tmp_path / ".work-bundle"
    control.mkdir(parents=True, exist_ok=True)
    metadata = {
        "metadata_version": 4,
        "authority": "canonical",
        "workspace": {"id": workspace_id, "slug": "artifact-foundation", "mode": "single-repository"},
        "control_plane": {
            "schema_version": 1,
            "repository": {"remote": ""},
            "sync_policy": {"mode": "manual"},
        },
        "source_repositories": [
            {
                "id": "source",
                "role": "source",
                "locator": {"type": "manual", "value": "test-fixture"},
                "default_branch": "main",
                "workspace_binding": {"type": "root"},
                "materialization": {"required": True},
                "operation_policy": "inherit",
            }
        ],
    }
    (control / "project.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    home = tmp_path / "home"
    config = home / ".work-bundle"
    registry = config / "registry/projects.yaml"
    registry.parent.mkdir(parents=True)
    registry_document = {
        "registry_schema_version": 1,
        "projects": [],
        "device_bindings": {
            workspace_id: {
                "slug": "artifact-foundation",
                "workspace_root": str(tmp_path),
                "control_plane_path": str(control),
                "control_plane_remote": "",
                "observed_control_plane_head": "",
                "repositories": {
                    "source": {
                        "project_root": str(tmp_path),
                        "checkout_kind": "manual",
                        "observed_branch": "",
                        "observed_head": "",
                        "observed_at": "2026-09-19T00:00:00Z",
                        "git_common_dir": "",
                    }
                },
            }
        },
    }
    registry.write_text(yaml.safe_dump(registry_document, sort_keys=False), encoding="utf-8")
    (config / "bootstrap.yaml").write_text(
        "\n".join(
            [
                "bootstrap_version: v1",
                "authority: canonical",
                f"work_bundle_root: {REPO_ROOT}",
                'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
                'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


def _temporary_catalog(tmp_path: Path) -> Path:
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir(parents=True)
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "note-v1",
        "type": "object",
        "required": ["id", "parent_id", "value"],
        "properties": {
            "id": {"type": "string", "pattern": r"^note-[0-9]+[a-z]?$"},
            "parent_id": {"type": "string", "pattern": r"^parent-[0-9]+$"},
            "value": {"type": "string"},
        },
        "additionalProperties": False,
    }
    (schema_dir / "note-v1.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    catalog = {
        "catalog_id": "artifact-family-catalog-test-v1",
        "schema_version": 1,
        "families": [
            {
                "name": "note",
                "schema": {"id": "note-v1", "path": "schemas/note-v1.schema.json"},
                "representation": "yaml",
                "anchor": "workspace_root",
                "locator": {
                    "template": "artifacts/{state}/{id}.yaml",
                    "variables": ["state", "id"],
                },
                "identity": {"field": "id", "pattern": r"^note-[0-9]+[a-z]?$"},
                "relationships": {
                    "bindings": [
                        {"name": "parent", "field": "parent_id", "required": True}
                    ]
                },
                "lifecycle": {
                    "authority": "location",
                    "states": ["active", "archived"],
                    "transitions": {"active": ["archived"], "archived": []},
                },
                "index": {
                    "path": "artifacts/index.jsonl",
                    "source_states": ["active", "archived"],
                    "projection": ["id", "parent_id", "value"],
                    "format": "jsonl",
                },
            }
        ],
    }
    path = tmp_path / "catalog.yaml"
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    return path


def test_runtime_catalog_is_valid_and_registers_only_itself() -> None:
    catalog = load_catalog(RUNTIME_CATALOG)
    assert catalog["catalog_id"] == "artifact-family-catalog-v1"
    assert [item["name"] for item in catalog["families"]] == ["artifact-family-catalog"]
    policy = family_policy(catalog, "artifact-family-catalog")
    assert policy["schema"]["id"] == "artifact-family-catalog-v1"
    assert policy["locator"]["template"] == (
        "references/assets/orchestration/contract/artifact-family-catalog-v1.yaml"
    )
    schema = RUNTIME_CATALOG.with_name("artifact-family-catalog-v1.schema.json")
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == (
        "f7272e56eb04a9c13dd9ba64e24c9e905730abf252a43ca07664f2f35e401935"
    )
    with pytest.raises(SystemExit, match="Unregistered artifact family"):
        family_policy(catalog, "specification")


def test_catalog_rejects_duplicates_schema_escape_and_schema_identity_mismatch(tmp_path: Path) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"].append(dict(content["families"][0]))
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="Duplicate artifact family"):
        load_catalog(catalog_path)

    catalog_path = _temporary_catalog(tmp_path / "escape")
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"][0]["schema"]["path"] = "../outside.json"
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="schema path escapes"):
        load_catalog(catalog_path)

    catalog_path = _temporary_catalog(tmp_path / "identity")
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"][0]["schema"]["id"] = "wrong-v1"
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="schema identity mismatch"):
        load_catalog(catalog_path)

    catalog_path = _temporary_catalog(tmp_path / "locator-escape")
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"][0]["locator"]["template"] = "../artifacts/{state}/{id}.yaml"
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    with pytest.raises(SystemExit, match="locator policy.*canonical relative path"):
        load_catalog(catalog_path)


@pytest.mark.parametrize(
    "template",
    [
        "artifacts//{state}/{id}.yaml",
        "artifacts/./{state}/{id}.yaml",
        "artifacts/*/{state}/{id}.yaml",
        "artifacts/**/{state}/{id}.yaml",
        "artifacts/?/{state}/{id}.yaml",
        "artifacts/[ab]/{state}/{id}.yaml",
    ],
)
def test_catalog_rejects_noncanonical_and_literal_glob_locator_templates(
    tmp_path: Path, template: str
) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"][0]["locator"]["template"] = template
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")

    with pytest.raises(SystemExit, match="Artifact locator policy"):
        load_catalog(catalog_path)


def test_catalog_rejects_noncanonical_and_literal_glob_index_paths(tmp_path: Path) -> None:
    for suffix, index_path in (
        ("alias", "artifacts//index.jsonl"),
        ("glob", "artifacts/*-index.jsonl"),
    ):
        catalog_path = _temporary_catalog(tmp_path / suffix)
        content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        content["families"][0]["index"]["path"] = index_path
        catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")

        with pytest.raises(SystemExit, match="Artifact index policy"):
            load_catalog(catalog_path)


def test_catalog_rejects_locator_variables_without_structural_sources(tmp_path: Path) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"][0]["locator"] = {
        "template": "artifacts/{foo}.yaml",
        "variables": ["foo"],
    }
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")

    with pytest.raises(SystemExit, match="unsupported variables: foo"):
        load_catalog(catalog_path)


@pytest.mark.parametrize(
    ("template", "variables", "missing"),
    [
        ("artifacts/{state}/note.yaml", ["state"], "identity"),
        ("artifacts/{id}.yaml", ["id"], "lifecycle state"),
    ],
)
def test_location_owned_catalog_requires_identity_and_state_distinguishing_locator(
    tmp_path: Path, template: str, variables: list[str], missing: str
) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    content = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    content["families"][0]["locator"] = {"template": template, "variables": variables}
    catalog_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")

    with pytest.raises(SystemExit, match=f"does not distinguish {missing}"):
        load_catalog(catalog_path)


def test_maintained_yaml_and_markdown_readers_preserve_equivalent_structure(tmp_path: Path) -> None:
    inline = tmp_path / "inline.yaml"
    block = tmp_path / "block.yaml"
    inline.write_text("id: spec-20260919-001a\nrelated: {plan: plan-001, task: task-001}\n", encoding="utf-8")
    block.write_text("id: spec-20260919-001a\nrelated:\n  plan: plan-001\n  task: task-001\n", encoding="utf-8")
    assert read_yaml_mapping(inline) == read_yaml_mapping(block)

    markdown = tmp_path / "artifact.md"
    markdown.write_text("---\nid: spec-20260919-001a\nrelated: {plan: plan-001}\n---\nBody\n", encoding="utf-8")
    data, body = read_markdown_artifact(markdown)
    assert data["id"] == "spec-20260919-001a"
    assert data["related"] == {"plan": "plan-001"}
    assert body == "Body\n"
    assert _read_structured(markdown) == (data, body)

    malformed = tmp_path / "bad.yaml"
    malformed.write_text("id: [unterminated\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="Invalid YAML"):
        read_yaml_mapping(malformed)


def test_generic_store_validates_location_bindings_atomicity_and_lifecycle(tmp_path: Path) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    catalog = load_catalog(catalog_path)
    policy = family_policy(catalog, "note")
    anchors = {"workspace_root": tmp_path}
    data = {"id": "note-001a", "parent_id": "parent-001", "value": "ok"}
    bindings = {"parent": "parent-001"}

    assert canonical_artifact_path(policy, anchors, identity="note-001a", state="active") == (
        tmp_path / "artifacts/active/note-001a.yaml"
    )
    assert validate_artifact(policy, data, catalog_path=catalog_path, bindings=bindings) == bindings
    with pytest.raises(SystemExit, match="Missing required artifact binding"):
        validate_artifact(policy, data, catalog_path=catalog_path)
    assert serialize_artifact(policy, data) == serialize_artifact(policy, dict(reversed(list(data.items()))))

    result = write_artifact(
        catalog_path,
        "note",
        anchors,
        data,
        state="active",
        bindings=bindings,
        rebuild=False,
    )
    path = Path(result["path"])
    assert result["identity"] == "note-001a"
    assert result["validated_bindings"] == bindings
    assert result["partial_effect"] is False
    read_result = read_artifact(
        catalog_path, "note", anchors, identity="note-001a", state="active", bindings=bindings
    )
    assert read_result["data"] == data
    original = path.read_bytes()

    with pytest.raises(SystemExit, match="binding mismatch"):
        write_artifact(
            catalog_path,
            "note",
            anchors,
            {**data, "value": "changed"},
            state="active",
            bindings={"parent": "parent-999"},
            rebuild=False,
        )
    assert path.read_bytes() == original

    same = transition_artifact(
        catalog_path, "note", anchors, identity="note-001a", current_state="active", target_state="active", bindings=bindings
    )
    assert same["path"] == str(path)
    assert path.read_bytes() == original

    archived = transition_artifact(
        catalog_path, "note", anchors, identity="note-001a", current_state="active", target_state="archived", bindings=bindings
    )
    archived_path = Path(archived["path"])
    assert archived_path.read_bytes() == original
    assert not path.exists()

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, original)
    with pytest.raises(SystemExit, match="destination collision"):
        transition_artifact(
            catalog_path, "note", anchors, identity="note-001a", current_state="active", target_state="archived", bindings=bindings
        )


def test_atomic_write_preserves_existing_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "artifact.yaml"
    path.write_bytes(b"before\n")
    path.chmod(0o644)

    atomic_write_bytes(path, b"after\n")

    assert path.read_bytes() == b"after\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_atomic_write_uses_normal_creation_mode_for_new_file(tmp_path: Path) -> None:
    ordinary = tmp_path / "ordinary.yaml"
    ordinary.write_bytes(b"ordinary\n")
    atomic = tmp_path / "atomic.yaml"

    atomic_write_bytes(atomic, b"atomic\n")

    assert stat.S_IMODE(atomic.stat().st_mode) == stat.S_IMODE(ordinary.stat().st_mode)


def test_declared_index_rebuild_validates_candidates_and_refuses_duplicates(tmp_path: Path) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    anchors = {"workspace_root": tmp_path}
    for identity, state in [("note-001a", "active"), ("note-002", "archived")]:
        write_artifact(
            catalog_path,
            "note",
            anchors,
            {"id": identity, "parent_id": "parent-001", "value": identity},
            state=state,
            bindings={"parent": "parent-001"},
            rebuild=False,
        )
    result = rebuild_index(catalog_path, "note", anchors)
    rows = [json.loads(line) for line in Path(result["path"]).read_text(encoding="utf-8").splitlines()]
    assert [row["id"] for row in rows] == ["note-001a", "note-002"]

    invalid = tmp_path / "artifacts/active/not-canonical.yaml"
    invalid.write_text("id: note-003\nparent_id: parent-001\nvalue: bad-place\n", encoding="utf-8")
    previous = Path(result["path"]).read_bytes()
    with pytest.raises(SystemExit, match="Invalid index candidate"):
        rebuild_index(catalog_path, "note", anchors)
    assert Path(result["path"]).read_bytes() == previous


def test_declared_index_refuses_duplicate_identity_across_states(tmp_path: Path) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    anchors = {"workspace_root": tmp_path}
    payload = {"id": "note-001", "parent_id": "parent-001", "value": "duplicate"}
    for state in ("active", "archived"):
        write_artifact(
            catalog_path,
            "note",
            anchors,
            payload,
            state=state,
            bindings={"parent": "parent-001"},
            rebuild=False,
        )
    with pytest.raises(SystemExit, match="duplicate identity"):
        rebuild_index(catalog_path, "note", anchors)


def _spec_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(project_root=None, workspace_root=str(root))


def _canonical_spec(root: Path, identity: str = "spec-001a") -> Path:
    data = {
        "artifact_type": "specification", "schema_version": 1, "id": identity,
        "title": "Exact", "status": "draft", "date_created": "2099-01-01",
        "last_updated": "2099-01-01", "purpose": "Foundation regression",
        "component": "orchestration", "version": "1.0", "project": "demo",
        "source_knowledge": [], "related_handoffs": [], "tags": ["test"],
        "execution_workspace": {"isolation": "existing", "profile": "default", "cleanup": "manual"},
    }
    result = write_artifact(
        SPEC_CATALOG, "specification", {"workspace_root": root}, data,
        state="active", body="# Specification\n",
    )
    return Path(str(result["path"]))


def test_spec_index_uses_only_canonical_family_and_ignores_legacy_markdown(tmp_path: Path) -> None:
    root = tmp_path / ".work-bundle/orchestration/spec/active"
    root.mkdir(parents=True)
    _canonical_spec(tmp_path)
    rows = index_specs(_spec_args(tmp_path))
    assert rows[0]["id"] == "spec-001a"

    missing = root / "missing.md"
    missing.write_text("---\ntitle: Legacy\n---\n", encoding="utf-8")
    index_before = (tmp_path / ".work-bundle/orchestration/spec/index.jsonl").read_bytes()
    assert [row["id"] for row in index_specs(_spec_args(tmp_path))] == ["spec-001a"]
    assert (tmp_path / ".work-bundle/orchestration/spec/index.jsonl").read_bytes() == index_before


def test_spec_front_matter_mutation_uses_maintained_yaml_and_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "spec.md"
    path.write_text("---\nid: spec-001a\nrelated: {plan: plan-001}\nstatus: active\nlast_updated: 2020-01-01\n---\nBody\n", encoding="utf-8")
    replace_front_matter_value(path, "status", "reviewed")
    data, body = read_markdown_artifact(path)
    assert data["id"] == "spec-001a"
    assert data["related"] == {"plan": "plan-001"}
    assert data["status"] == "reviewed"
    assert body == "Body\n"


def test_forced_archive_uses_explicit_identity_without_weakening_strict_index(tmp_path: Path) -> None:
    active = _canonical_spec(tmp_path, "spec-origin")
    index_specs(_spec_args(tmp_path))

    archived = archive_spec_for_forced_finalization(_spec_args(tmp_path), "spec-origin")

    assert archived == tmp_path / ".work-bundle/orchestration/spec/archived/spec-origin.spec.md"
    assert archived.read_text(encoding="utf-8").endswith("# Specification\n")
    assert not active.exists()
    rows = [
        json.loads(line)
        for line in (tmp_path / ".work-bundle/orchestration/spec/index.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert rows[0]["id"] == "spec-origin"

    assert archive_spec_for_forced_finalization(_spec_args(tmp_path), "spec-origin") == archived


def test_forced_archive_rejects_incomplete_specification(tmp_path: Path) -> None:
    active = tmp_path / ".work-bundle/orchestration/spec/active/spec-origin.spec.md"
    active.parent.mkdir(parents=True)
    active.write_text("---\nid: spec-origin\n---\nLegacy body\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="schema validation|Artifact schema"):
        archive_spec_for_forced_finalization(_spec_args(tmp_path), "spec-origin")

    assert active.is_file()


def test_write_reports_index_failure_as_partial_effect(tmp_path: Path) -> None:
    catalog_path = _temporary_catalog(tmp_path)
    index_path = tmp_path / "artifacts/index.jsonl"
    index_path.mkdir(parents=True)
    with pytest.raises(SystemExit, match="(?i)artifact was written.*index rebuild failed"):
        write_artifact(
            catalog_path,
            "note",
            {"workspace_root": tmp_path},
            {"id": "note-001", "parent_id": "parent-001", "value": "ok"},
            state="active",
            bindings={"parent": "parent-001"},
            rebuild=True,
        )
    assert (tmp_path / "artifacts/active/note-001.yaml").is_file()


def test_public_spec_dispatcher_paths_use_strict_shared_primitives(tmp_path: Path) -> None:
    content = tmp_path / "content.md"
    content.write_text(
        "---\nproject: demo\nsource_knowledge: []\nrelated_handoffs: []\ntags: [test]\n"
        "execution_workspace: {isolation: existing, profile: default, cleanup: manual}\n"
        "---\n# Specification\n",
        encoding="utf-8",
    )
    base = [sys.executable, str(REPO_ROOT / "scripts/orch.py")]

    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*base, *arguments, "--project-root", str(tmp_path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    written = run(
        "write-spec", "--id", "spec-001a", "--title", "Exact", "--purpose", "test",
        "--component", "foundation", "--content-file", str(content), "--status", "draft",
    )
    assert written.returncode == 0, written.stderr
    assert "spec-001a" in written.stdout

    indexed = run("index-specs")
    assert indexed.returncode == 0, indexed.stderr
    listed = run("list-specs")
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout.splitlines()[-1])["id"] == "spec-001a"

    transitioned = run("set-spec-status", "--id", "spec-001a", "--status", "verified")
    assert transitioned.returncode == 0, transitioned.stderr
    listed_active = run("list-specs", "--status", "verified")
    assert listed_active.returncode == 0, listed_active.stderr
    assert json.loads(listed_active.stdout.splitlines()[-1])["status"] == "verified"
