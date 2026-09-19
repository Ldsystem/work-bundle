from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCH_ROOT))

from artifact_inputs import _resolve_spec_paths
from artifact_store import family_policy, load_catalog, read_artifact
import specs
import execution_context


CATALOG = REPO_ROOT / "references/assets/orchestration/contract/artifact-family-catalog-v2.yaml"


def _args(root: Path, content: Path | None = None, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "workspace_root": str(root),
        "project_root": None,
        "id": "spec-20990101-001a",
        "title": "Canonical specification",
        "purpose": "Prove the current specification family",
        "component": "orchestration",
        "version": "1.0",
        "content_file": str(content) if content else "",
        "status": "draft",
        "filename": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".work-bundle/orchestration/spec/active").mkdir(parents=True)
    (tmp_path / ".work-bundle/orchestration/spec/archived").mkdir(parents=True)
    monkeypatch.setattr(specs, "resolve_workspace_root", lambda _args: tmp_path)
    monkeypatch.setattr(specs, "resolve_working_workspace", lambda _root: None)
    monkeypatch.setattr(specs, "orchestration_root", lambda _args: tmp_path / ".work-bundle/orchestration")
    monkeypatch.setattr(specs, "init_dirs", lambda _args: None)
    monkeypatch.setattr(
        specs,
        "rel",
        lambda path, _args: Path(path).resolve().relative_to(tmp_path.resolve()).as_posix(),
    )
    return tmp_path


def _content(path: Path, *, extra: str = "", body: str = "# Complete semantic specification\n\n- **REQ-001A:** Preserve the suffixed requirement.\n") -> None:
    path.write_text(
        "---\n"
        "project: demo\n"
        "source_knowledge: []\n"
        "related_handoffs: []\n"
        "tags: [orchestration]\n"
        "execution_workspace:\n"
        "  isolation: existing\n"
        "  profile: default\n"
        "  cleanup: manual\n"
        f"{extra}"
        "---\n"
        f"{body}",
        encoding="utf-8",
    )


def test_catalog_v2_registers_canonical_specification_family() -> None:
    policy = family_policy(load_catalog(CATALOG), "specification")
    assert policy["schema"]["id"] == "specification-v1"
    assert policy["locator"]["template"] == (
        ".work-bundle/orchestration/spec/{state}/{id}.spec.md"
    )
    assert policy["index"]["path"] == ".work-bundle/orchestration/spec/index.jsonl"


def test_write_read_index_qualify_archive_and_suffix_round_trip(
    workspace: Path, tmp_path: Path,
) -> None:
    content = tmp_path / "content.md"
    _content(content)
    args = _args(workspace, content)

    specs.cmd_write_spec(args)
    active = workspace / ".work-bundle/orchestration/spec/active/spec-20990101-001a.spec.md"
    assert active.is_file()
    stored = read_artifact(
        CATALOG,
        "specification",
        {"workspace_root": workspace},
        identity="spec-20990101-001a",
        state="active",
    )
    assert stored["data"]["status"] == "draft"
    assert "REQ-001A" in stored["body"]
    assert not hasattr(execution_context, "_source_records")
    rows = specs.index_specs(args)
    assert rows == [
        {
            "type": "spec",
            "id": "spec-20990101-001a",
            "title": "Canonical specification",
            "status": "draft",
            "path": ".work-bundle/orchestration/spec/active/spec-20990101-001a.spec.md",
            "purpose": "Prove the current specification family",
            "component": "orchestration",
            "created_at": stored["data"]["date_created"],
            "updated_at": stored["data"]["last_updated"],
        }
    ]

    specs.cmd_set_spec_status(_args(workspace, id=args.id, status="verified"))
    assert specs.index_specs(args)[0]["status"] == "verified"
    specs.cmd_set_spec_status(_args(workspace, id=args.id, status="archived"))
    assert not active.exists()
    assert (workspace / ".work-bundle/orchestration/spec/archived/spec-20990101-001a.spec.md").is_file()


def test_legacy_markdown_is_ignored_and_only_canonical_identity_lookup_is_supported(
    workspace: Path, tmp_path: Path,
) -> None:
    legacy = workspace / ".work-bundle/orchestration/spec/active/spec-legacy.md"
    legacy.write_text("---\nid: [broken\n---\n", encoding="utf-8")
    content = tmp_path / "content.md"
    _content(content)
    args = _args(workspace, content)
    specs.cmd_write_spec(args)

    assert [row["id"] for row in specs.index_specs(args)] == ["spec-20990101-001a"]
    assert _resolve_spec_paths(
        workspace, {}, {"source_spec_id": "spec-20990101-001a"}
    ) == [workspace / ".work-bundle/orchestration/spec/active/spec-20990101-001a.spec.md"]
    with pytest.raises(SystemExit, match="Legacy source_spec aliases are unsupported"):
        _resolve_spec_paths(workspace, {}, {"source_spec": "spec-20990101-001a"})
    with pytest.raises(SystemExit, match="paths are unsupported"):
        _resolve_spec_paths(
            workspace,
            {},
            {
                "source_spec_id": (
                    ".work-bundle/orchestration/spec/active/"
                    "spec-20990101-001a.spec.md"
                )
            },
        )
    with pytest.raises(SystemExit, match="canonical location"):
        _resolve_spec_paths(workspace, {}, {"source_spec_id": "spec-legacy"})


def test_structural_override_collision_and_filename_override_fail_before_mutation(
    workspace: Path, tmp_path: Path,
) -> None:
    content = tmp_path / "content.md"
    _content(content, extra="id: spec-evil\n")
    args = _args(workspace, content)
    with pytest.raises(SystemExit, match="structural field override"):
        specs.cmd_write_spec(args)
    assert not list((workspace / ".work-bundle/orchestration/spec/active").glob("*.spec.md"))

    _content(content)
    with pytest.raises(SystemExit, match="filename override"):
        specs.cmd_write_spec(_args(workspace, content, filename="custom.md"))
    specs.cmd_write_spec(args)
    before = (workspace / ".work-bundle/orchestration/spec/index.jsonl").read_bytes()
    with pytest.raises(SystemExit, match="collision"):
        specs.cmd_write_spec(args)
    assert (workspace / ".work-bundle/orchestration/spec/index.jsonl").read_bytes() == before


def test_shared_front_matter_mutation_remains_available_to_plan_consumers(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plan.md"
    path.write_text(
        "---\nid: plan-001\nstatus: Planned\nupdated_at: 2020-01-01\n---\nBody\n",
        encoding="utf-8",
    )
    specs.replace_front_matter_value(path, "status", "In progress")
    data, body = specs.parse_markdown_artifact(path.read_text(encoding="utf-8"), source=str(path))
    assert data["status"] == "In progress"
    assert data["updated_at"] != "2020-01-01"
    assert body == "Body\n"


def test_archive_reports_partial_effect_when_index_rebuild_fails(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = tmp_path / "content.md"
    _content(content)
    args = _args(workspace, content)
    specs.cmd_write_spec(args)
    original = specs.rebuild_index
    calls = 0

    def fail_after_move(*values: object, **options: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SystemExit("injected index failure")
        return original(*values, **options)

    monkeypatch.setattr(specs, "rebuild_index", fail_after_move)
    with pytest.raises(SystemExit, match="moved but index rebuild failed.*partial effect"):
        specs.cmd_set_spec_status(_args(workspace, id=args.id, status="archived"))
    assert (workspace / ".work-bundle/orchestration/spec/archived/spec-20990101-001a.spec.md").is_file()


def test_skill_contract_requires_direct_semantic_review_and_self_check() -> None:
    skill = (REPO_ROOT / "skills/orch-create-specification/SKILL.md").read_text(encoding="utf-8")
    for term in [
        "user purpose",
        "accepted authority",
        "requirements, constraints, interfaces, acceptance criteria",
        "material conflicts",
        "scope",
        "## Self-check",
        "Supporting evidence files do not issue the semantic verdict",
    ]:
        assert term in skill
    assert "require_specification_review" not in skill


def test_current_public_entrypoint_writes_canonical_family(tmp_path: Path) -> None:
    workspace_id = "wb-stage3-entrypoint"
    control = tmp_path / ".work-bundle"
    control.mkdir()
    (control / "project.yaml").write_text(
        "metadata_version: 4\nauthority: canonical\n"
        f"workspace: {{id: {workspace_id}, slug: demo, mode: single-repository}}\n"
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
        f"  {workspace_id}:\n    slug: demo\n    workspace_root: {tmp_path}\n"
        f"    control_plane_path: {control}\n    control_plane_remote: ''\n"
        "    observed_control_plane_head: ''\n    repositories:\n      source:\n"
        f"        project_root: {tmp_path}\n        checkout_kind: manual\n"
        "        observed_branch: ''\n        observed_head: ''\n        observed_at: '2026-09-19T00:00:00Z'\n        git_common_dir: ''\n",
        encoding="utf-8",
    )
    content = tmp_path / "content.md"
    _content(content)
    result = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts/orch.py"), "write-spec",
            "--workspace-root", str(tmp_path), "--id", "spec-20990101-002b",
            "--title", "Entrypoint", "--purpose", "Public command",
            "--component", "orchestration", "--content-file", str(content),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(home)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (control / "orchestration/spec/active/spec-20990101-002b.spec.md").is_file()
    doctor = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts/orch.py"), "doctor",
            "--workspace-root", str(tmp_path),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(home)},
        text=True,
        capture_output=True,
        check=False,
    )
    doctor_output = doctor.stdout + doctor.stderr
    assert "invalid current specification family" not in doctor_output
    assert "spec index identity lacks one canonical artifact" not in doctor_output
    assert "spec index does not match canonical current family" not in doctor_output
    assert "index path escapes orchestration root" not in doctor_output
