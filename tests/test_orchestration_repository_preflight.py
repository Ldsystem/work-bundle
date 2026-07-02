from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

from repository_preflight import (  # noqa: E402
    inspect_repository_state,
    repository_preflight,
    resolve_target_repositories,
)


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


def write_project_metadata(project: Path, repo: Path, *, branch: str = "main", commit: str | None = None) -> None:
    head = commit if commit is not None else git(repo, "rev-parse", "HEAD")
    (project / ".work-bundle").mkdir(parents=True, exist_ok=True)
    (project / ".work-bundle" / "project.yaml").write_text(
        "\n".join(
            [
                "metadata_version: 2",
                "source_repositories:",
                "  - id: repo-main",
                f"    path: {repo.resolve()}",
                "    work_dir: true",
                '    remote: ""',
                "    git_repository: true",
                f"    working_branch: {branch}",
                "    branch_required: true",
                "    last_commit_id: " + head,
                "    baseline_status: current",
                "    codegraph:",
                "      supported: false",
                "      index_present: false",
                f"      root: {repo.resolve()}",
                "      status: not-indexed",
                '      synced_commit_id: ""',
                '      last_synced_at: ""',
                "      reason: no-index",
                "",
            ]
        ),
        encoding="utf-8",
    )


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


def test_resolution_prefers_task_write_scopes_then_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = repository(tmp_path, "target")
    fallback = repository(tmp_path, "fallback")
    write_project_metadata(project, fallback)
    task = project / "task.md"
    task.write_text(f"---\ntarget_files:\n  - {target / 'new.py'}\nsource_files:\n  - .work-bundle/project.yaml\n---\n", encoding="utf-8")

    assert resolve_target_repositories(project, [task]) == [
        {"path": str(target.resolve()), "source": "task-write-scope"}
    ]
    assert resolve_target_repositories(project) == [
        {
            "path": str(fallback.resolve()),
            "source": "project-metadata",
            "metadata": {
                "id": "repo-main",
                "path": str(fallback.resolve()),
                "work_dir": True,
                "remote": "",
                "git_repository": True,
                "working_branch": "main",
                "branch_required": True,
                "last_commit_id": git(fallback, "rev-parse", "HEAD"),
                "baseline_status": "current",
                "codegraph": {
                    "supported": False,
                    "index_present": False,
                    "root": str(fallback.resolve()),
                    "status": "not-indexed",
                    "synced_commit_id": "",
                    "last_synced_at": "",
                    "reason": "no-index",
                },
            },
        }
    ]


def test_metadata_preflight_reports_branch_commit_and_codegraph_no_index(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = repository(tmp_path)
    write_project_metadata(project, repo)

    result = repository_preflight(resolve_target_repositories(project))

    payload = result["repository_preflight"]
    assert payload["status"] == "passed"
    row = payload["repositories"][0]
    assert row["metadata"]["repository_id"] == "repo-main"
    assert row["metadata"]["branch_status"] == "matched"
    assert row["metadata"]["commit_status"] == "matched"
    assert row["metadata"]["codegraph"]["actual_index_present"] is False
    assert row["metadata"]["codegraph"]["reason"] == "no-index"


def test_metadata_preflight_blocks_branch_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = repository(tmp_path)
    write_project_metadata(project, repo, branch="wrong")

    result = repository_preflight(resolve_target_repositories(project))
    row = result["repository_preflight"]["repositories"][0]

    assert result["repository_preflight"]["status"] == "blocked"
    assert row["status"] == "branch-mismatch"
    assert row["metadata"]["branch_status"] == "mismatch"


def test_metadata_preflight_blocks_stale_commit(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repo = repository(tmp_path)
    old_head = git(repo, "rev-parse", "HEAD")
    (repo / "tracked.txt").write_text("later\n", encoding="utf-8")
    git(repo, "commit", "-am", "later")
    write_project_metadata(project, repo, commit=old_head)

    result = repository_preflight(resolve_target_repositories(project))
    row = result["repository_preflight"]["repositories"][0]

    assert result["repository_preflight"]["status"] == "blocked"
    assert row["status"] == "stale-baseline"
    assert row["metadata"]["commit_status"] == "stale"


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


def test_cli_outputs_machine_usable_json(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "orch.py"),
        "repository-preflight",
        "--project-root",
        str(tmp_path),
        "--repository",
        str(repo),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["repository_preflight"]["status"] == "passed"
    assert payload["repository_preflight"]["repositories"][0]["status"] == "clean"
