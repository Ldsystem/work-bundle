from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from repository_preflight import (  # noqa: E402
    inspect_repository_state,
    repository_preflight,
    resolve_target_repositories,
)
import repository_preflight as preflight_module  # noqa: E402


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def repository(tmp_path: Path, name: str = "repo") -> Path:
    path = tmp_path / name
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(path, "add", "tracked.txt")
    git(path, "commit", "-qm", "initial")
    return path


def test_malformed_accepted_baseline_is_typed(tmp_path: Path) -> None:
    malformed = tmp_path / "baseline.json"
    malformed.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SystemExit, match="Accepted baseline.*valid JSON"):
        preflight_module._load_baselines(str(malformed))


def write_workspace_metadata_v4(workspace: Path, workspace_id: str = "wb-test") -> None:
    (workspace / ".work-bundle").mkdir(parents=True, exist_ok=True)
    (workspace / ".work-bundle" / "project.yaml").write_text(
        "\n".join(
            [
                "metadata_version: 4",
                "authority: canonical",
                "workspace:",
                f"  id: {workspace_id}",
                "  slug: test",
                "  mode: multi-repository",
                "control_plane:",
                "  schema_version: 1",
                "  repository:",
                '    remote: ""',
                "  sync_policy:",
                "    mode: manual",
                "source_repositories:",
                "  - id: repo-main",
                "    role: source",
                "    remote:",
                '      canonical: "https://example.com/repo.git"',
                "    default_branch: main",
                "    workspace_binding:",
                "      type: member",
                "      name: repo-main",
                "    materialization:",
                "      required: true",
                "    operation_policy: inherit",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_v4_registry(
    path: Path,
    workspace: Path,
    repo: Path | None,
    *,
    workspace_id: str = "wb-test",
    observed_branch: str = "main",
    observed_head: str = "",
) -> None:
    repository_lines: list[str] = []
    if repo is not None:
        repository_lines.append("      repo-main:")
        repository_lines.append(f"        project_root: {repo.resolve()}")
        repository_lines.append("        checkout_kind: managed-worktree")
        repository_lines.append(f"        git_common_dir: {repo.resolve() / '.git'}")
        repository_lines.append("        observed_at: 2026-09-20T00:00:00Z")
    if repo is not None and observed_branch:
        repository_lines.append(f"        observed_branch: {observed_branch}")
    if repo is not None and observed_head:
        repository_lines.append(f"        observed_head: {json.dumps(observed_head)}")
    path.write_text(
        "\n".join(
            [
                "registry_schema_version: 1",
                "projects: []",
                "device_bindings:",
                f"  {workspace_id}:",
                "    slug: test",
                f"    workspace_root: {workspace.resolve()}",
                "    repositories:" if repository_lines else "    repositories: {}",
                *repository_lines,
                "",
            ]
        ),
        encoding="utf-8",
    )


def use_registry(monkeypatch: pytest.MonkeyPatch, registry: Path) -> None:
    monkeypatch.setattr(
        preflight_module._infrastructure,
        "load_project_registry",
        lambda: preflight_module._infrastructure.load_infrastructure_document(
            registry, family="project-registry", toolkit_root=REPO_ROOT
        ),
    )


@pytest.mark.parametrize("indentless", [False, True])
def test_v4_repository_entries_accept_yaml_sequence_indentation_and_merge_device_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    indentless: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = repository(workspace, "repo-main")
    registry = tmp_path / "projects.yaml"
    write_workspace_metadata_v4(workspace)
    metadata = workspace / ".work-bundle/project.yaml"
    if indentless:
        text = metadata.read_text(encoding="utf-8")
        start = text.index("source_repositories:\n") + len("source_repositories:\n")
        tail = [line[2:] if line.startswith("  ") else line for line in text[start:].splitlines()]
        metadata.write_text(text[:start] + "\n".join(tail) + "\n", encoding="utf-8")
    head = git(repo, "rev-parse", "HEAD")
    write_v4_registry(registry, workspace, repo, observed_head=head)
    use_registry(monkeypatch, registry)

    entries = preflight_module._metadata_repository_entries(workspace)

    assert len(entries) == 1
    assert entries[0]["id"] == "repo-main"
    assert entries[0]["remote"] == "https://example.com/repo.git"
    assert entries[0]["materialization_required"] is True
    assert entries[0]["project_root"] == str(repo.resolve())
    assert entries[0]["observed_head"] == head


def test_v4_preflight_keeps_missing_device_observation_as_typed_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = tmp_path / "projects.yaml"
    write_workspace_metadata_v4(workspace)
    write_v4_registry(registry, workspace, None)
    use_registry(monkeypatch, registry)

    with pytest.raises(SystemExit, match="WB_INFRASTRUCTURE_REPOSITORY_BINDING_MISSING"):
        resolve_target_repositories(workspace)


def test_v4_preflight_detects_stale_device_head_without_refreshing_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = repository(workspace, "repo-main")
    registry = tmp_path / "projects.yaml"
    write_workspace_metadata_v4(workspace)
    write_v4_registry(registry, workspace, repo, observed_head="0" * 40)
    before = registry.read_text(encoding="utf-8")
    use_registry(monkeypatch, registry)

    result = repository_preflight(resolve_target_repositories(workspace))

    assert result["repository_preflight"]["status"] == "blocked"
    row = result["repository_preflight"]["repositories"][0]
    assert row["status"] == "stale-observation"
    assert row["failure_code"] == "WB_REPOSITORY_OBSERVATION_STALE"
    assert row["metadata"]["observation_head_status"] == "stale"
    assert registry.read_text(encoding="utf-8") == before


def test_v4_yaml_task_preflight_selects_exact_write_and_cross_member_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    members = [repository(workspace, name) for name in ("repo-main", "repo-other", "repo-idle")]
    metadata = workspace / ".work-bundle/project.yaml"
    write_workspace_metadata_v4(workspace)
    document = yaml.safe_load(metadata.read_text())
    for name in ("repo-other", "repo-idle"):
        item = dict(document["source_repositories"][0])
        item.update(id=name, workspace_binding={"type": "member", "name": name})
        document["source_repositories"].append(item)
    metadata.write_text(yaml.safe_dump(document), encoding="utf-8")
    registry = tmp_path / "projects.yaml"
    write_v4_registry(registry, workspace, members[0], observed_head=git(members[0], "rev-parse", "HEAD"))
    registry_doc = yaml.safe_load(registry.read_text())
    for repo in members[1:]:
        local = dict(registry_doc["device_bindings"]["wb-test"]["repositories"]["repo-main"])
        local.update(project_root=str(repo), git_common_dir=str(repo / ".git"),
                     observed_head=git(repo, "rev-parse", "HEAD"))
        registry_doc["device_bindings"]["wb-test"]["repositories"][repo.name] = local
    registry.write_text(yaml.safe_dump(registry_doc), encoding="utf-8")
    use_registry(monkeypatch, registry)
    task = workspace / "task.task.yaml"
    task.write_text(yaml.safe_dump({
        "source_files": ["repo-other/src/read.py"],
        "target_files": ["repo-main/src/write.py"],
    }), encoding="utf-8")

    targets = resolve_target_repositories(workspace, [task])
    assert {row["metadata"]["id"]: row["source"] for row in targets} == {
        "repo-main": "task-write-scope", "repo-other": "referenced-file",
    }
    assert {row["path"] for row in targets} == {str(members[0]), str(members[1])}
    assert resolve_target_repositories(workspace, (path for path in [task]), repositories=[members[2]]) == targets
    assert [(row["path"], row["source"]) for row in resolve_target_repositories(
        workspace, repositories=[members[2]]
    )] == [(str(members[2]), "explicit-repository")]

    other_task = workspace / "other.task.yaml"
    other_task.write_text(yaml.safe_dump({"target_files": ["repo-other/src/write.py"]}), encoding="utf-8")
    assert [(row["metadata"]["id"], row["source"]) for row in resolve_target_repositories(workspace, [other_task])] == [
        ("repo-other", "task-write-scope"),
    ]

    task.write_text(yaml.safe_dump({"target_files": ["unbound/src/write.py"]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="UNBOUND"):
        resolve_target_repositories(workspace, [task])
    with pytest.raises(SystemExit, match="UNBOUND"):
        resolve_target_repositories(workspace, [task], repositories=[members[2]])


def test_v4_yaml_task_files_mapping_selects_bound_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = repository(workspace, "repo-main")
    write_workspace_metadata_v4(workspace)
    registry = tmp_path / "projects.yaml"
    write_v4_registry(registry, workspace, repo, observed_head=git(repo, "rev-parse", "HEAD"))
    use_registry(monkeypatch, registry)
    task = workspace / "task.task.yaml"
    task.write_text(yaml.safe_dump({"files": {
        "read": ["repo-main/src/read.py"], "write": ["repo-main/src/write.py"],
    }}), encoding="utf-8")

    assert [(row["metadata"]["id"], row["source"]) for row in resolve_target_repositories(workspace, [task])] == [
        ("repo-main", "task-write-scope"),
    ]


def test_clean_repository_passes(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    result = inspect_repository_state(repo)
    assert result["status"] == "clean"
    assert result["changes"] == []


def test_dirty_repository_classifies_staged_unstaged_deleted_and_untracked(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "delete.txt").write_text("delete\n", encoding="utf-8")
    git(repo, "add", "delete.txt")
    git(repo, "commit", "-qm", "add delete")
    (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
    git(repo, "add", "staged.txt")
    (repo / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
    (repo / "delete.txt").unlink()
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    result = inspect_repository_state(repo)

    assert result["status"] == "dirty"
    assert result["staged"] == ["A  staged.txt"]
    assert result["unstaged"] == [" D delete.txt", " M tracked.txt"]
    assert result["deleted"] == [" D delete.txt"]
    assert result["untracked"] == ["?? untracked.txt"]


def test_unresolved_repository_blocks(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    git(repo, "checkout", "-qb", "other")
    (repo / "tracked.txt").write_text("other\n", encoding="utf-8")
    git(repo, "commit", "-am", "other")
    git(repo, "checkout", "-q", "main")
    (repo / "tracked.txt").write_text("master\n", encoding="utf-8")
    git(repo, "commit", "-am", "master")
    subprocess.run(["git", "-C", str(repo), "merge", "other"], check=False, capture_output=True, text=True)

    assert inspect_repository_state(repo)["status"] == "unresolved"


def test_non_git_and_inaccessible_targets_block(tmp_path: Path) -> None:
    non_git = tmp_path / "plain"
    non_git.mkdir()
    assert inspect_repository_state(non_git)["status"] == "not-git"
    assert inspect_repository_state(tmp_path / "missing")["status"] == "inaccessible"

    local = inspect_repository_state(non_git, source="explicit-repository", allow_local_project=True)
    assert local["status"] == "clean"
    assert local["target_kind"] == "local-project"
    assert local["preflight_kind"] == "local-project"
    assert local["git_clean_worktree_applicable"] is False
    assert local["local_project_evidence"] == {
        "exists": True,
        "is_dir": True,
        "git_root": None,
        "declared_source": "explicit-repository",
    }


def test_multi_repository_preflight_blocks_without_modifying_repositories(tmp_path: Path) -> None:
    clean = repository(tmp_path, "clean")
    dirty = repository(tmp_path, "dirty")
    (dirty / "untracked.txt").write_text("keep\n", encoding="utf-8")
    before = git(dirty, "status", "--porcelain=v1", "--untracked-files=all")

    result = repository_preflight(
        [
            {"path": str(clean), "source": "task-write-scope"},
            {"path": str(dirty), "source": "task-write-scope"},
        ]
    )

    assert result["repository_preflight"]["status"] == "blocked"
    assert git(dirty, "status", "--porcelain=v1", "--untracked-files=all") == before


def test_mixed_git_backed_and_local_project_targets_pass_with_evidence(tmp_path: Path) -> None:
    git_backed = repository(tmp_path, "git-backed")
    local_project = tmp_path / "plain-project"
    local_project.mkdir()
    (local_project / "config.json").write_text("{}\n", encoding="utf-8")

    result = repository_preflight(
        [
            {"path": str(git_backed), "source": "task-write-scope"},
            {"path": str(local_project), "source": "explicit-repository"},
        ]
    )

    payload = result["repository_preflight"]
    assert payload["status"] == "passed"
    rows = {row["path"]: row for row in payload["repositories"]}
    assert rows[str(git_backed.resolve())]["target_kind"] == "git-backed"
    assert rows[str(git_backed.resolve())]["preflight_kind"] == "git-clean-worktree"
    assert rows[str(local_project.resolve())]["status"] == "clean"
    assert rows[str(local_project.resolve())]["target_kind"] == "local-project"
    assert rows[str(local_project.resolve())]["preflight_kind"] == "local-project"
    assert rows[str(local_project.resolve())]["local_project_evidence"]["declared_source"] == "explicit-repository"


def test_accepted_baseline_allows_only_accepted_changes(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "accepted.txt").write_text("accepted\n", encoding="utf-8")
    accepted = ["?? accepted.txt"]
    result = inspect_repository_state(repo, accepted_changes=accepted)
    assert result["status"] == "clean"
    assert result["baseline"] == "accepted-handoff"

    (repo / "unexplained.txt").write_text("unexplained\n", encoding="utf-8")
    result = inspect_repository_state(repo, accepted_changes=accepted)
    assert result["status"] == "dirty"
    assert result["unexplained_changes"] == ["?? unexplained.txt"]


def test_git_backed_post_sync_style_unexplained_change_blocks(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    accepted = [" M tracked.txt"]
    (repo / "tracked.txt").write_text("accepted baseline edit\n", encoding="utf-8")
    assert inspect_repository_state(repo, accepted_changes=accepted)["status"] == "clean"

    (repo / "codegraph-side-effect.txt").write_text("unexpected sync side effect\n", encoding="utf-8")
    result = repository_preflight(
        [{"path": str(repo.resolve()), "source": "task-write-scope"}],
        accepted_baselines={str(repo.resolve()): accepted},
    )

    row = result["repository_preflight"]["repositories"][0]
    assert result["repository_preflight"]["status"] == "blocked"
    assert row["target_kind"] == "git-backed"
    assert row["preflight_kind"] == "git-clean-worktree"
    assert row["baseline"] == "accepted-handoff"
    assert row["unexplained_changes"] == ["?? codegraph-side-effect.txt"]


def test_resolution_excludes_orchestration_artifacts_and_falls_through_to_source(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifact_repo = repository(project, ".work-bundle")
    source = repository(tmp_path, "source")
    task = project / "task.md"
    task.write_text(
        "---\n"
        "target_files:\n"
        "  - .work-bundle/orchestration/handoff/index.jsonl\n"
        "source_files:\n"
        "  - .work-bundle/orchestration/spec/active/spec.md\n"
        f"  - {source / 'tracked.txt'}\n"
        "---\n",
        encoding="utf-8",
    )

    assert resolve_target_repositories(project, [task]) == [
        {"path": str(source.resolve()), "source": "referenced-file"}
    ]
    assert artifact_repo.resolve() != source.resolve()


def test_resolution_keeps_explicit_source_target_inside_nested_repository(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    nested = repository(project, ".work-bundle")
    task = project / "task.md"
    task.write_text(
        "---\n"
        "target_files:\n"
        "  - .work-bundle/src/runtime.py\n"
        "source_files:\n"
        "  - .work-bundle/orchestration/spec/active/spec.md\n"
        "---\n",
        encoding="utf-8",
    )

    assert resolve_target_repositories(project, [task]) == [
        {"path": str(nested.resolve()), "source": "task-write-scope"}
    ]


def test_repository_preflight_help_describes_accepted_baseline_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "orch.py"),
            "repository-preflight",
            "--help",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--accepted-baseline" in result.stdout
    assert "JSON file" in result.stdout
    assert "accepted repository baselines" in result.stdout
