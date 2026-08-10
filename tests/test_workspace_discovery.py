from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


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


def write_workspace_metadata(workspace: Path, member: Path) -> None:
    metadata = workspace / ".work-bundle" / "project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "\n".join(
            [
                "metadata_version: 3",
                f"workspace_root: {workspace.resolve()}",
                "workspace_mode: multi-repository",
                "source_repositories:",
                "  - id: member-main",
                f"    project_root: {member.resolve()}",
                "    origin_id: origin-main",
                "    checkout_kind: managed-worktree",
                "    expected_branch: feature/workspace",
                "    observed_head: abc123",
                "    baseline_status: current",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_nested_member_resolves_workspace_and_member_independently(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "service-api"
    deep = member / "src" / "feature"
    deep.mkdir(parents=True)
    write_workspace_metadata(workspace, member)

    args = argparse.Namespace(workspace_root=None, project_root=str(deep))

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
        project_root=str(deep),
        cwd=None,
        registry_file=None,
    )

    assert keep_core.resolve_workspace_root(deep) == workspace.resolve()
    assert keep_core.resolve_member_project_root(workspace, deep) == member.resolve()
    assert keep_core.resolve_knowledge_base(args) == (
        workspace.resolve() / ".work-bundle" / "knowledge",
        "work-bundle",
    )


def test_single_repository_compatibility_resolves_same_root(tmp_path: Path) -> None:
    project = tmp_path / "single"
    deep = project / "src" / "nested"
    deep.mkdir(parents=True)
    metadata = project / ".work-bundle" / "project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "\n".join(
            [
                "metadata_version: 2",
                "source_repositories:",
                "  - id: single-main",
                f"    path: {project.resolve()}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    args = argparse.Namespace(workspace_root=None, project_root=str(deep))
    assert orchestration_core.resolve_workspace_root(args) == project.resolve()
    assert orchestration_core.resolve_member_project_root(args) == project.resolve()


def test_orchestration_registry_fallback_maps_origin_to_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    origin = tmp_path / "origin" / "deep"
    member.mkdir(parents=True)
    origin.mkdir(parents=True)
    write_workspace_metadata(workspace, member)
    config = tmp_path / "config"
    registry = config / "registry" / "projects.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        "\n".join(
            [
                "projects:",
                "  - slug: demo",
                f"    workspace_root: {workspace.resolve()}",
                "    repository_origins:",
                "      - id: origin-main",
                f"        origin_path: {(tmp_path / 'origin').resolve()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (config / "bootstrap.yaml").write_text(
        f"project_registry: {registry.resolve()}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config))
    monkeypatch.chdir(origin)

    args = argparse.Namespace(workspace_root=None, project_root=None)
    assert orchestration_core.resolve_workspace_root(args) == workspace.resolve()
