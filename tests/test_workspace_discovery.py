from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


orchestration_core = load_module(
    "workspace_discovery_orchestration_core",
    REPO_ROOT / "scripts" / "orchestration" / "core.py",
)
keep_core = load_module(
    "workspace_discovery_keep_core",
    REPO_ROOT / "scripts" / "keep-summarizing" / "core.py",
)
session_hook = load_module(
    "workspace_discovery_session_hook",
    REPO_ROOT / "bin" / "work-bundle-session-start.py",
)


def write_workspace_metadata(workspace: Path, member: Path, *, mode: str = "multi-repository") -> None:
    metadata = workspace / ".work-bundle" / "project.yaml"
    metadata.parent.mkdir(parents=True)
    binding = {"type": "root"} if mode == "single-repository" else {"type": "member", "name": member.name}
    document = {
        "metadata_version": 4,
        "authority": "canonical",
        "workspace": {"id": "wb-discovery", "slug": "demo", "mode": mode},
        "control_plane": {"schema_version": 1, "repository": {"remote": ""}, "sync_policy": {"mode": "manual"}},
        "source_repositories": [{
            "id": "member-main",
            "role": "source",
            "locator": {"type": "manual", "value": "fixture"},
            "default_branch": "feature/workspace",
            "workspace_binding": binding,
            "materialization": {"required": True},
            "operation_policy": "inherit",
        }],
    }
    metadata.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    config = Path.home() / ".work-bundle"
    registry = config / "registry/projects.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(yaml.safe_dump({
        "registry_schema_version": 1,
        "projects": [{"slug": "demo", "aliases": []}],
        "device_bindings": {"wb-discovery": {
            "slug": "demo",
            "workspace_root": str(workspace.resolve()),
            "control_plane_path": str(metadata.parent.resolve()),
            "control_plane_remote": "",
            "observed_control_plane_head": "",
            "repositories": {"member-main": {
                "project_root": str(member.resolve()),
                "checkout_kind": "manual",
                "observed_branch": "",
                "observed_head": "",
                "observed_at": "2026-09-19T00:00:00Z",
                "git_common_dir": "",
            }},
        }},
    }, sort_keys=False), encoding="utf-8")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    config = home / ".work-bundle"
    config.mkdir(parents=True)
    (config / "bootstrap.yaml").write_text(
        "\n".join([
            "bootstrap_version: v1",
            "authority: canonical",
            f"work_bundle_root: {REPO_ROOT}",
            'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
            'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"',
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))


def test_nested_member_resolves_workspace_and_member_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "service-api"
    deep = member / "src" / "feature"
    deep.mkdir(parents=True)
    write_workspace_metadata(workspace, member)

    monkeypatch.chdir(deep)
    args = argparse.Namespace(workspace_root=None, project_root=None)

    assert orchestration_core.resolve_workspace_root(args) == workspace.resolve()
    assert orchestration_core.resolve_member_project_root(args) == member.resolve()
    assert orchestration_core.work_bundle(args) == workspace.resolve() / ".work-bundle"
    assert session_hook.resolve_workspace_root(deep) == workspace.resolve()


def test_explicit_workspace_root_has_precedence_for_control_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    deep = member / "nested"
    deep.mkdir(parents=True)
    write_workspace_metadata(workspace, member)
    monkeypatch.chdir(deep)

    args = argparse.Namespace(workspace_root=str(workspace), project_root=None)

    assert orchestration_core.resolve_workspace_root(args) == workspace.resolve()
    assert orchestration_core.resolve_member_project_root(args) == member.resolve()


def test_keep_summarizing_uses_workspace_knowledge_from_member_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    deep = member / "nested"
    deep.mkdir(parents=True)
    write_workspace_metadata(workspace, member)

    args = argparse.Namespace(
        knowledge_root=None,
        workspace_root=None,
        project_root=None,
        cwd=str(deep),
        registry_file=None,
    )

    assert keep_core.resolve_workspace_root(deep) == workspace.resolve()
    assert keep_core.resolve_knowledge_base(args) == (
        workspace.resolve() / ".work-bundle" / "knowledge",
        "work-bundle",
    )


def test_keep_summarizing_cwd_requires_matching_device_binding(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    deep = member / "nested"
    deep.mkdir(parents=True)
    write_workspace_metadata(workspace, member)
    registry = Path.home() / ".work-bundle/registry/projects.yaml"
    document = yaml.safe_load(registry.read_text(encoding="utf-8"))
    document["device_bindings"] = {}
    registry.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    args = argparse.Namespace(
        knowledge_root=None,
        workspace_root=None,
        project_root=None,
        cwd=str(deep),
        registry_file=None,
    )

    with pytest.raises(SystemExit, match="WB_INFRASTRUCTURE_WORKSPACE_BINDING_MISSING"):
        keep_core.resolve_knowledge_base(args)


def test_keep_summarizing_resolve_and_doctor_use_v4_anchor_join(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    deep = member / "nested"
    deep.mkdir(parents=True)
    write_workspace_metadata(workspace, member)
    knowledge = workspace / ".work-bundle/knowledge"
    knowledge.mkdir()
    knowledge.joinpath("project.yaml").write_text("slug: demo\n", encoding="utf-8")
    dispatcher = REPO_ROOT / "scripts/keep-summarizing/dispatcher.py"
    env = os.environ.copy()

    resolved = subprocess.run(
        [sys.executable, str(dispatcher), "resolve", "--cwd", str(deep)],
        env=env, check=False, capture_output=True, text=True,
    )
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    assert resolved.stdout.strip() == "demo"

    healthy = subprocess.run(
        [sys.executable, str(dispatcher), "doctor", "--project", "demo", "--cwd", str(deep)],
        env=env, check=False, capture_output=True, text=True,
    )
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert healthy.stdout.strip() == "ok"

    registry = Path.home() / ".work-bundle/registry/projects.yaml"
    document = yaml.safe_load(registry.read_text(encoding="utf-8"))
    document["device_bindings"] = {}
    registry.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    missing = subprocess.run(
        [sys.executable, str(dispatcher), "resolve", "--cwd", str(deep)],
        env=env, check=False, capture_output=True, text=True,
    )
    assert missing.returncode != 0
    assert "WB_INFRASTRUCTURE_WORKSPACE_BINDING_MISSING" in missing.stderr


def test_knowledge_commands_ignore_stale_source_observation_but_source_preflight_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    deep = member / "nested"
    member.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(member)], check=True)
    subprocess.run(["git", "-C", str(member), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(member), "config", "user.name", "Test"], check=True)
    member.joinpath("README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(member), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(member), "commit", "-q", "-m", "fixture"], check=True)
    deep.mkdir()
    write_workspace_metadata(workspace, member)

    metadata_path = workspace / ".work-bundle/project.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    repository = metadata["source_repositories"][0]
    repository.pop("locator")
    repository["remote"] = {
        "canonical": "ssh://git@example.test/member",
        "aliases": [],
    }
    metadata_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")

    registry_path = Path.home() / ".work-bundle/registry/projects.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    local = registry["device_bindings"]["wb-discovery"]["repositories"]["member-main"]
    local.update(
        {
            "checkout_kind": "managed-worktree",
            "observed_branch": "main",
            "observed_head": "0" * 40,
            "git_common_dir": str(member / ".git"),
        }
    )
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    knowledge = workspace / ".work-bundle/knowledge"
    knowledge.mkdir()
    knowledge.joinpath("project.yaml").write_text("slug: demo\n", encoding="utf-8")
    dispatcher = REPO_ROOT / "scripts/keep-summarizing/dispatcher.py"
    env = os.environ.copy()

    indexed = subprocess.run(
        [sys.executable, str(dispatcher), "index", "--project", "demo", "--cwd", str(deep)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert indexed.returncode == 0, indexed.stdout + indexed.stderr
    queried = subprocess.run(
        [
            sys.executable,
            str(dispatcher),
            "query",
            "--project",
            "demo",
            "--query",
            "workspace knowledge",
            "--limit",
            "1",
            "--cwd",
            str(deep),
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert queried.returncode == 0, queried.stdout + queried.stderr

    monkeypatch.chdir(deep)
    args = argparse.Namespace(workspace_root=None, project_root=None)
    with pytest.raises(SystemExit, match="WB_INFRASTRUCTURE_OBSERVATION_STALE"):
        orchestration_core.resolve_member_project_root(args)


def test_single_repository_compatibility_resolves_same_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "single"
    deep = project / "src" / "nested"
    deep.mkdir(parents=True)
    write_workspace_metadata(project, project, mode="single-repository")

    monkeypatch.chdir(deep)
    args = argparse.Namespace(workspace_root=None, project_root=None)
    assert orchestration_core.resolve_workspace_root(args) == project.resolve()
    assert orchestration_core.resolve_member_project_root(args) == project.resolve()


def test_orchestration_does_not_use_registry_origin_as_workspace_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    origin = tmp_path / "origin" / "deep"
    member.mkdir(parents=True)
    origin.mkdir(parents=True)
    write_workspace_metadata(workspace, member)
    monkeypatch.chdir(origin)

    args = argparse.Namespace(workspace_root=None, project_root=None)
    with pytest.raises(SystemExit, match="WB_INFRASTRUCTURE_WORKSPACE_NOT_FOUND"):
        orchestration_core.resolve_workspace_root(args)
