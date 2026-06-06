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


def test_resolution_prefers_task_write_scopes_then_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    target = repository(tmp_path, "target")
    fallback = repository(tmp_path, "fallback")
    (project / ".work-bundle").mkdir()
    (project / ".work-bundle" / "project.yaml").write_text(
        f"source_repositories:\n  - path: {fallback}\n", encoding="utf-8"
    )
    task = project / "task.md"
    task.write_text(f"---\ntarget_files:\n  - {target / 'new.py'}\nsource_files:\n  - .work-bundle/project.yaml\n---\n", encoding="utf-8")

    assert resolve_target_repositories(project, [task]) == [
        {"path": str(target.resolve()), "source": "task-write-scope"}
    ]
    assert resolve_target_repositories(project) == [
        {"path": str(fallback.resolve()), "source": "project-metadata"}
    ]


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
