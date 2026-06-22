#!/usr/bin/env python3
"""Read-only target repository resolution and cleanliness inspection."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Iterable

from core import project_root


STATUS_COMMAND = ["git", "status", "--porcelain=v1", "--untracked-files=all"]
TASK_SCOPE_KEYS = ("target_files", "source_files", "references")


def _run_git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        check=False,
        text=True,
    )


def _existing_parent(path: Path) -> Path | None:
    candidate = path.resolve()
    while not candidate.exists():
        if candidate == candidate.parent:
            return None
        candidate = candidate.parent
    return candidate if candidate.is_dir() else candidate.parent


def _git_root(path: Path) -> Path | None:
    parent = _existing_parent(path)
    if parent is None:
        return None
    result = _run_git(parent, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _front_matter_lists(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in text[4:end].splitlines():
        if line and not line.startswith(" "):
            current = line.split(":", 1)[0] if ":" in line else None
            continue
        stripped = line.strip()
        if current in TASK_SCOPE_KEYS and stripped.startswith("- "):
            result.setdefault(current, []).append(stripped[2:].strip().strip("'\""))
    return result


def _metadata_repositories(root: Path) -> list[Path]:
    metadata = root / ".work-bundle" / "project.yaml"
    if not metadata.exists():
        return []
    repositories: list[Path] = []
    in_source_repositories = False
    for line in metadata.read_text(encoding="utf-8").splitlines():
        if line == "source_repositories:":
            in_source_repositories = True
            continue
        if in_source_repositories and line and not line.startswith(" "):
            break
        stripped = line.strip()
        if in_source_repositories and stripped.startswith("- path:"):
            raw = stripped.split(":", 1)[1].strip().strip("'\"")
            repositories.append(Path(raw).expanduser().resolve())
    return repositories


def _is_orchestration_artifact(root: Path, path: Path) -> bool:
    absolute = path if path.is_absolute() else root / path
    try:
        absolute.resolve().relative_to((root / ".work-bundle" / "orchestration").resolve())
    except ValueError:
        return False
    return True


def _resolve_candidates(
    root: Path, candidates: Iterable[tuple[Path, str]]
) -> list[dict[str, str]]:
    repositories: dict[str, dict[str, str]] = {}
    for candidate, source in candidates:
        absolute = candidate if candidate.is_absolute() else root / candidate
        repository = _git_root(absolute)
        target = repository or absolute.resolve()
        key = str(target)
        if key not in repositories:
            repositories[key] = {"path": key, "source": source}
    return [repositories[key] for key in sorted(repositories)]


def resolve_target_repositories(
    root: Path,
    task_files: Iterable[Path] = (),
    referenced_files: Iterable[Path] = (),
    repositories: Iterable[Path] = (),
) -> list[dict[str, str]]:
    """Resolve exact repository targets without changing filesystem or Git state."""
    root = root.resolve()
    explicit = [(path, "explicit-repository") for path in repositories]
    if explicit:
        return _resolve_candidates(root, explicit)

    write_scopes: list[tuple[Path, str]] = []
    references: list[tuple[Path, str]] = [
        (path, "referenced-file")
        for path in referenced_files
        if not _is_orchestration_artifact(root, path)
    ]
    for task_file in task_files:
        scopes = _front_matter_lists(task_file)
        write_scopes.extend(
            (candidate, "task-write-scope")
            for path in scopes.get("target_files", [])
            if not _is_orchestration_artifact(root, candidate := Path(path))
        )
        for key in ("source_files", "references"):
            references.extend(
                (candidate, "referenced-file")
                for path in scopes.get(key, [])
                if not _is_orchestration_artifact(root, candidate := Path(path))
            )

    resolved = _resolve_candidates(root, write_scopes)
    if resolved:
        return resolved
    resolved = _resolve_candidates(root, references)
    if resolved:
        return resolved
    return _resolve_candidates(root, ((path, "project-metadata") for path in _metadata_repositories(root)))


def _classify_changes(changes: list[str]) -> dict[str, list[str]]:
    classifications = {"staged": [], "unstaged": [], "deleted": [], "untracked": []}
    for change in changes:
        status = change[:2]
        if status == "??":
            classifications["untracked"].append(change)
            continue
        if status[0] not in {" ", "?"}:
            classifications["staged"].append(change)
        if status[1] not in {" ", "?"}:
            classifications["unstaged"].append(change)
        if "D" in status:
            classifications["deleted"].append(change)
    return classifications


def compare_accepted_baseline(current: Iterable[str], accepted: Iterable[str]) -> list[str]:
    """Return current changes not proven by the accepted executor-result baseline."""
    accepted_set = set(accepted)
    return sorted(change for change in current if change not in accepted_set)


def inspect_repository_state(
    repository: Path,
    *,
    source: str = "explicit-repository",
    accepted_changes: Iterable[str] | None = None,
    allow_local_project: bool = False,
) -> dict[str, object]:
    """Inspect one repository using porcelain v1 without invoking mutation commands."""
    path = repository.resolve()
    baseline = "accepted-handoff" if accepted_changes is not None else "initial"
    result: dict[str, object] = {
        "path": str(path),
        "source": source,
        "target_kind": "git-backed",
        "preflight_kind": "git-clean-worktree",
        "status": "clean",
        "baseline": baseline,
        "changes": [],
    }
    if not path.exists():
        result["status"] = "inaccessible"
        return result
    git_root = _git_root(path)
    if not path.is_dir() or git_root != path:
        if allow_local_project and path.is_dir() and git_root is None:
            result["target_kind"] = "local-project"
            result["preflight_kind"] = "local-project"
            result["git_clean_worktree_applicable"] = False
            result["local_project_evidence"] = {
                "exists": True,
                "is_dir": True,
                "git_root": None,
                "declared_source": source,
            }
            return result
        result["status"] = "not-git"
        return result

    status = _run_git(path, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        result["status"] = "inaccessible"
        result["error"] = status.stderr.strip()
        return result

    changes = sorted(line for line in status.stdout.splitlines() if line)
    result["changes"] = changes
    result.update(_classify_changes(changes))
    if any("U" in change[:2] or change[:2] in {"AA", "DD"} for change in changes):
        result["status"] = "unresolved"
        return result
    if accepted_changes is None:
        result["status"] = "dirty" if changes else "clean"
        return result

    unexplained = compare_accepted_baseline(changes, accepted_changes)
    result["unexplained_changes"] = unexplained
    result["status"] = "dirty" if unexplained else "clean"
    return result


def repository_preflight(
    targets: Iterable[dict[str, str]],
    accepted_baselines: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    accepted_baselines = accepted_baselines or {}
    repositories = [
        inspect_repository_state(
            Path(target["path"]),
            source=target["source"],
            accepted_changes=accepted_baselines.get(target["path"]),
            allow_local_project=True,
        )
        for target in targets
    ]
    return {
        "repository_preflight": {
            "status": "passed" if repositories and all(row["status"] == "clean" for row in repositories) else "blocked",
            "command": "git status --porcelain=v1 --untracked-files=all",
            "repositories": repositories,
        }
    }


def _load_baselines(path: str | None) -> dict[str, list[str]]:
    if not path:
        return {}
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(item, list) for item in value.values()):
        raise SystemExit("Accepted baseline must be a JSON object mapping repository paths to change lists.")
    return {str(Path(key).resolve()): [str(change) for change in changes] for key, changes in value.items()}


def cmd_repository_preflight(args: argparse.Namespace) -> None:
    root = project_root(args)
    targets = resolve_target_repositories(
        root,
        task_files=((Path(path) if Path(path).is_absolute() else root / path).resolve() for path in args.task_file),
        referenced_files=(Path(path) for path in args.reference),
        repositories=(Path(path) for path in args.repository),
    )
    print(json.dumps(repository_preflight(targets, _load_baselines(args.accepted_baseline)), ensure_ascii=False, sort_keys=True))
