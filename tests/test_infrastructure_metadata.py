from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts/work-bundle/infrastructure.py"


def load_infrastructure():
    spec = importlib.util.spec_from_file_location("wb_infrastructure_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def portable_metadata(*, workspace_id: str = "wb-example", mode: str = "multi-repository") -> dict[str, object]:
    binding: dict[str, object] = {"type": "root" if mode == "single-repository" else "member"}
    if mode != "single-repository":
        binding["name"] = "source"
    return {
        "metadata_version": 4,
        "authority": "canonical",
        "workspace": {"id": workspace_id, "slug": "example", "mode": mode},
        "control_plane": {
            "schema_version": 1,
            "repository": {"remote": ""},
            "sync_policy": {"mode": "manual"},
        },
        "source_repositories": [
            {
                "id": "source",
                "role": "source",
                "remote": {"canonical": "ssh://git@example.test/source", "aliases": []},
                "default_branch": "main",
                "workspace_binding": binding,
                "materialization": {"required": True},
                "operation_policy": "inherit",
            }
        ],
    }


def registry_document(workspace: Path, member: Path, *, workspace_id: str = "wb-example") -> dict[str, object]:
    branch = subprocess.run(
        ["git", "-C", str(member), "branch", "--show-current"], check=True, capture_output=True, text=True
    ).stdout.strip()
    head = subprocess.run(
        ["git", "-C", str(member), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    common = subprocess.run(
        ["git", "-C", str(member), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return {
        "registry_schema_version": 1,
        "projects": [
            {
                "slug": "example",
                "name": "example",
                "workspace_root": str(workspace),
                "work_bundle_root": str(workspace / ".work-bundle"),
                "knowledge_root": str(workspace / ".work-bundle/knowledge"),
                "aliases": [],
                "status": "active",
            }
        ],
        "device_bindings": {
            workspace_id: {
                "slug": "example",
                "workspace_root": str(workspace),
                "control_plane_path": str(workspace / ".work-bundle"),
                "control_plane_remote": "",
                "observed_control_plane_head": "",
                "repositories": {
                    "source": {
                        "project_root": str(member),
                        "checkout_kind": "managed-worktree",
                        "observed_branch": branch,
                        "observed_head": head,
                        "observed_at": "2026-09-19T00:00:00Z",
                        "git_common_dir": common,
                    }
                },
            }
        },
    }


def write_context(tmp_path: Path, *, member_count: int = 1) -> tuple[Path, Path, Path]:
    workspace = tmp_path / "workspace"
    config = tmp_path / "config"
    registry = config / "registry/projects.yaml"
    workspace.joinpath(".work-bundle").mkdir(parents=True)
    members = [workspace / ("source" if index == 0 else f"source-{index + 1}") for index in range(member_count)]
    for member in members:
        member.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(member)], check=True)
        subprocess.run(["git", "-C", str(member), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(member), "config", "user.name", "Test"], check=True)
        member.joinpath("README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(member), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(member), "commit", "-q", "-m", "fixture"], check=True)
    metadata = portable_metadata()
    if member_count > 1:
        repositories = metadata["source_repositories"]
        assert isinstance(repositories, list)
        repositories.append(
            {
                "id": "source-2",
                "role": "source",
                "remote": {"canonical": "ssh://git@example.test/source-2", "aliases": []},
                "default_branch": "main",
                "workspace_binding": {"type": "member", "name": "source-2"},
                "materialization": {"required": True},
                "operation_policy": "inherit",
            }
        )
    workspace.joinpath(".work-bundle/project.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False))
    registry.parent.mkdir(parents=True)
    registry_data = registry_document(workspace, members[0])
    if member_count > 1:
        bindings = registry_data["device_bindings"]
        assert isinstance(bindings, dict)
        repositories = bindings["wb-example"]["repositories"]
        repositories["source-2"] = registry_document(
            workspace, members[1], workspace_id="unused"
        )["device_bindings"]["unused"]["repositories"]["source"]
    registry.write_text(yaml.safe_dump(registry_data, sort_keys=False))
    config.joinpath("bootstrap.yaml").write_text(
        "\n".join(
            [
                "bootstrap_version: v1",
                "authority: canonical",
                f"work_bundle_root: {REPO_ROOT}",
                'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
                'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"',
                "",
            ]
        )
    )
    return config, workspace, members[0]


def test_catalog_has_separate_immutable_infrastructure_families() -> None:
    infrastructure = load_infrastructure()
    catalog = infrastructure.load_schema_catalog(toolkit_root=REPO_ROOT)
    assert set(catalog["families"]) == {
        "bootstrap-config",
        "workspace-project-metadata",
        "project-registry",
    }
    assert all(item["version"] == 1 for item in catalog["families"].values())


def test_maintained_yaml_equivalence_and_canonical_dump() -> None:
    infrastructure = load_infrastructure()
    inline = infrastructure.parse_yaml_mapping(
        "metadata_version: 4\nauthority: canonical\nworkspace: {id: wb-example, slug: example, mode: multi-repository}\n",
        source="inline",
    )
    block = infrastructure.parse_yaml_mapping(
        "# comment\nmetadata_version: 4\nauthority: 'canonical'\nworkspace:\n  id: wb-example\n  slug: example\n  mode: multi-repository\n",
        source="block",
    )
    assert inline == block
    assert infrastructure.parse_yaml_mapping(
        infrastructure.dump_canonical_yaml(inline), source="round-trip"
    ) == inline


def test_schema_rejects_local_portable_fields_and_duplicate_repository_ids(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    invalid = portable_metadata()
    invalid["workspace_root"] = str(tmp_path)
    with pytest.raises(infrastructure.InfrastructureError) as local:
        infrastructure.validate_infrastructure_document(
            invalid, family="workspace-project-metadata", toolkit_root=REPO_ROOT
        )
    assert local.value.code == "WB_INFRASTRUCTURE_SCHEMA_INVALID"

    duplicate = portable_metadata()
    repositories = duplicate["source_repositories"]
    assert isinstance(repositories, list)
    repositories.append(dict(repositories[0]))
    with pytest.raises(infrastructure.InfrastructureError) as repeated:
        infrastructure.validate_infrastructure_document(
            duplicate, family="workspace-project-metadata", toolkit_root=REPO_ROOT
        )
    assert repeated.value.code == "WB_INFRASTRUCTURE_ID_DUPLICATE"


def test_schema_accepts_extensible_bootstrap_and_manual_repository_locator() -> None:
    infrastructure = load_infrastructure()
    bootstrap = {
        "bootstrap_version": "v1",
        "authority": "canonical",
        "work_bundle_root": "/toolkit",
        "project_registry": "$work_bundle_config_root/registry/projects.yaml",
        "skill_registry": "$work_bundle_config_root/registry/skill-registry.yaml",
        "prefer_subagent": False,
    }
    assert infrastructure.validate_infrastructure_document(
        bootstrap, family="bootstrap-config", toolkit_root=REPO_ROOT
    )["prefer_subagent"] is False

    metadata = portable_metadata()
    repository = metadata["source_repositories"][0]
    del repository["remote"]
    repository["locator"] = {"type": "manual", "value": "source"}
    infrastructure.validate_infrastructure_document(
        metadata, family="workspace-project-metadata", toolkit_root=REPO_ROOT
    )


def test_join_and_anchor_matrix_keep_workspace_and_member_distinct(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    config, workspace, member = write_context(tmp_path)
    nested = member / "nested"
    nested.mkdir()

    workspace_only = infrastructure.resolve_anchor_context(
        cwd=workspace, config_root=config, toolkit_root=REPO_ROOT
    )
    assert workspace_only.workspace_root == workspace.resolve()
    assert workspace_only.project_root is None

    from_member = infrastructure.resolve_anchor_context(
        cwd=nested, config_root=config, toolkit_root=REPO_ROOT
    )
    assert from_member.workspace_root == workspace.resolve()
    assert from_member.project_root == member.resolve()
    assert from_member.repository_id == "source"

    explicit = infrastructure.resolve_anchor_context(
        workspace_root=workspace,
        project_root=member,
        cwd=tmp_path,
        config_root=config,
        toolkit_root=REPO_ROOT,
    )
    assert explicit.workspace_root != explicit.project_root


def test_member_required_is_ambiguous_and_never_selects_first(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    config, workspace, _ = write_context(tmp_path, member_count=2)
    with pytest.raises(infrastructure.InfrastructureError) as failure:
        infrastructure.resolve_anchor_context(
            workspace_root=workspace,
            config_root=config,
            toolkit_root=REPO_ROOT,
            member_required=True,
        )
    assert failure.value.code == "WB_INFRASTRUCTURE_MEMBER_AMBIGUOUS"


def test_missing_binding_and_path_escape_fail_without_locator_fallback(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    metadata = portable_metadata()
    with pytest.raises(infrastructure.InfrastructureError) as missing:
        infrastructure.join_workspace_binding(metadata, {"projects": [], "device_bindings": {}})
    assert missing.value.code == "WB_INFRASTRUCTURE_WORKSPACE_BINDING_MISSING"

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    registry = {
        "projects": [{"slug": "example", "aliases": []}],
        "device_bindings": {"wb-example": {
            "slug": "example",
            "workspace_root": str(workspace),
            "repositories": {"source": {
                "project_root": str(outside),
                "checkout_kind": "managed-worktree",
                "observed_branch": "main",
                "observed_head": "0" * 40,
                "observed_at": "2026-09-19T00:00:00Z",
                "git_common_dir": str(outside / ".git"),
            }},
        }},
    }
    with pytest.raises(infrastructure.InfrastructureError) as escaped:
        infrastructure.join_workspace_binding(
            metadata, registry, expected_workspace_root=workspace
        )
    assert escaped.value.code == "WB_INFRASTRUCTURE_PROJECT_ROOT_ESCAPE"


def test_materialized_binding_requires_complete_observation_evidence(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    config, _, _ = write_context(tmp_path)
    registry = yaml.safe_load((config / "registry/projects.yaml").read_text(encoding="utf-8"))
    local = registry["device_bindings"]["wb-example"]["repositories"]["source"]
    local.pop("observed_head")
    with pytest.raises(infrastructure.InfrastructureError) as invalid:
        infrastructure.validate_infrastructure_document(
            registry, family="project-registry", toolkit_root=REPO_ROOT
        )
    assert invalid.value.code == "WB_INFRASTRUCTURE_SCHEMA_INVALID"


def test_workspace_context_does_not_require_source_observation_fields(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    config, workspace, member = write_context(tmp_path)
    registry_path = config / "registry/projects.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["device_bindings"]["wb-example"]["repositories"]["source"].pop("observed_head")
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    context = infrastructure.resolve_workspace_context(
        cwd=member,
        config_root=config,
        toolkit_root=REPO_ROOT,
    )
    assert context.workspace_root == workspace.resolve()
    assert context.workspace_id == "wb-example"

    with pytest.raises(infrastructure.InfrastructureError) as source_context:
        infrastructure.resolve_anchor_context(
            cwd=member,
            config_root=config,
            toolkit_root=REPO_ROOT,
        )
    assert source_context.value.code == "WB_INFRASTRUCTURE_SCHEMA_INVALID"


def test_explicitly_unmaterialized_binding_carries_no_invented_observations(tmp_path: Path) -> None:
    infrastructure = load_infrastructure()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    metadata = portable_metadata()
    repository = metadata["source_repositories"][0]
    repository["materialization"]["required"] = False
    registry = {
        "registry_schema_version": 1,
        "projects": [{"slug": "example", "aliases": []}],
        "device_bindings": {"wb-example": {
            "slug": "example",
            "workspace_root": str(workspace),
            "repositories": {"source": {
                "project_root": str(workspace / "source"),
                "checkout_kind": "unmaterialized-member",
                "observed_branch": "",
                "observed_head": "",
                "observed_at": "2026-09-19T00:00:00Z",
                "git_common_dir": "",
            }},
        }},
    }
    local = registry["device_bindings"]["wb-example"]["repositories"]["source"]
    local.update({
        "checkout_kind": "unmaterialized-member",
        "observed_branch": "",
        "observed_head": "",
        "git_common_dir": "",
    })
    joined = infrastructure.join_workspace_binding(
        metadata, registry, expected_workspace_root=workspace
    )
    assert joined["repositories"]["source"]["checkout_kind"] == "unmaterialized-member"

    repository["materialization"]["required"] = True
    joined_required = infrastructure.join_workspace_binding(
        metadata, registry, expected_workspace_root=workspace
    )
    assert joined_required["repositories"]["source"]["checkout_kind"] == "unmaterialized-member"


def test_atomic_write_preserves_old_bytes_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    infrastructure = load_infrastructure()
    target = tmp_path / "metadata.yaml"
    target.write_bytes(b"before\n")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("injected")

    monkeypatch.setattr(infrastructure.os, "replace", fail_replace)
    with pytest.raises(infrastructure.InfrastructureError) as failure:
        infrastructure.atomic_write_text(target, "after\n")
    assert failure.value.code == "WB_INFRASTRUCTURE_ATOMIC_WRITE_FAILED"
    assert target.read_bytes() == b"before\n"
