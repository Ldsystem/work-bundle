#!/usr/bin/env python3
"""Read-only target repository resolution and cleanliness inspection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

from core import project_registry_path, resolve_workspace_root


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


def _parse_value(value: str) -> object:
    value = value.strip().strip("'\"")
    if value == "true":
        return True
    if value == "false":
        return False
    return value


def _metadata_scalar(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1).strip().strip("'\"") if match else ""


def _workspace_id(text: str) -> str:
    in_workspace = False
    for line in text.splitlines():
        if line == "workspace:":
            in_workspace = True
            continue
        if in_workspace and line and not line.startswith(" "):
            break
        if in_workspace and line.strip().startswith("id:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""


def _device_binding_repositories(workspace_id: str) -> dict[str, dict[str, object]]:
    registry = project_registry_path()
    if not registry.is_file() or not workspace_id:
        return {}
    in_bindings = False
    in_workspace = False
    in_repositories = False
    current_repository = ""
    repositories: dict[str, dict[str, object]] = {}
    for line in registry.read_text(encoding="utf-8").splitlines():
        if line == "device_bindings:":
            in_bindings = True
            continue
        if in_bindings and line and not line.startswith(" "):
            break
        if not in_bindings:
            continue
        if re.match(r"^  [^\s].*:$", line):
            current_id = line.strip()[:-1].strip("'\"")
            in_workspace = current_id == workspace_id
            in_repositories = False
            current_repository = ""
            continue
        if not in_workspace:
            continue
        if line == "    repositories:":
            in_repositories = True
            continue
        if in_repositories and re.match(r"^      [^\s].*:$", line):
            current_repository = line.strip()[:-1].strip("'\"")
            repositories[current_repository] = {"id": current_repository}
            continue
        if in_repositories and current_repository and line.startswith("        ") and ":" in line:
            key, value = line.strip().split(":", 1)
            repositories[current_repository][key] = _parse_value(value)
    return repositories


def _v4_metadata_repository_entries(root: Path, text: str) -> list[dict[str, object]]:
    local = _device_binding_repositories(_workspace_id(text))
    entries: list[dict[str, object]] = []
    in_repositories = False
    current: dict[str, object] | None = None
    nested_key = ""
    for line in text.splitlines():
        if line == "source_repositories:":
            in_repositories = True
            continue
        if in_repositories and line and not line.startswith(" "):
            break
        if not in_repositories or not line.strip():
            continue
        if line.startswith("  - "):
            if current is not None:
                entries.append(current)
            current = {}
            nested_key = ""
            key, value = line.strip()[2:].split(":", 1)
            current[key] = _parse_value(value)
            continue
        if current is None:
            continue
        if line.startswith("    ") and not line.startswith("      ") and ":" in line:
            key, value = line.strip().split(":", 1)
            nested_key = key if not value.strip() else ""
            if value.strip():
                current[key] = _parse_value(value)
            continue
        if line.startswith("      ") and ":" in line:
            key, value = line.strip().split(":", 1)
            if nested_key == "remote" and key == "canonical":
                current["remote"] = _parse_value(value)
            elif nested_key == "materialization" and key == "required":
                current["materialization_required"] = _parse_value(value)
    if current is not None:
        entries.append(current)
    resolved: list[dict[str, object]] = []
    for entry in entries:
        repository_id = str(entry.get("id") or "")
        binding = local.get(repository_id)
        if not binding or not binding.get("project_root"):
            continue
        entry.update(binding)
        entry["project_root"] = binding["project_root"]
        entry["path"] = binding["project_root"]
        entry["git_repository"] = True
        entry["expected_branch"] = entry.get("default_branch") or binding.get("observed_branch") or ""
        # A device observation is current evidence, never the expected task baseline.
        entry["observed_head"] = ""
        entry["baseline_status"] = "local-observation"
        project_path = Path(str(binding["project_root"])).expanduser().resolve()
        codegraph_present = (project_path / ".codegraph").is_dir()
        entry["codegraph"] = {
            "supported": codegraph_present,
            "index_present": codegraph_present,
            "status": "indexed" if codegraph_present else "not-indexed",
            "reason": "" if codegraph_present else "no-index",
        }
        resolved.append(entry)
    return resolved


def _metadata_repository_entries(root: Path) -> list[dict[str, object]]:
    metadata = root / ".work-bundle" / "project.yaml"
    if not metadata.exists():
        return []
    text = metadata.read_text(encoding="utf-8")
    if _metadata_scalar(text, "metadata_version") == "4":
        return _v4_metadata_repository_entries(root, text)
    repositories: list[dict[str, object]] = []
    in_source_repositories = False
    current: dict[str, object] | None = None
    current_nested: dict[str, object] | None = None
    nested_key: str | None = None
    for line in text.splitlines():
        if line == "source_repositories:":
            in_source_repositories = True
            continue
        if in_source_repositories and line and not line.startswith(" "):
            break
        stripped = line.strip()
        if not in_source_repositories or not stripped:
            continue
        if line.startswith("  - "):
            if current is not None:
                repositories.append(current)
            current = {}
            current_nested = None
            nested_key = None
            item = stripped[2:]
            if ":" in item:
                key, value = item.split(":", 1)
                current[key.strip()] = _parse_value(value)
            continue
        if current is None:
            continue
        if line.startswith("    ") and not line.startswith("      ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_nested = None
            nested_key = None
            if value == "" and key in {"branch_check", "codegraph"}:
                current[key] = {}
                current_nested = current[key]  # type: ignore[assignment]
                nested_key = key
            else:
                current[key] = _parse_value(value)
            continue
        if line.startswith("      ") and current_nested is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_nested[key.strip()] = _parse_value(value)
            continue
    if current is not None:
        repositories.append(current)
    return repositories


def _metadata_repositories(root: Path) -> list[Path]:
    repositories: list[Path] = []
    for entry in _metadata_repository_entries(root):
        raw = entry.get("project_root") or entry.get("path")
        if raw:
            repositories.append(Path(str(raw)).expanduser().resolve())
    return repositories


def _enrich_with_metadata(root: Path, targets: list[dict[str, str]]) -> list[dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for entry in _metadata_repository_entries(root):
        raw = entry.get("project_root") or entry.get("path")
        if raw:
            entries[str(Path(str(raw)).expanduser().resolve())] = entry
    enriched: list[dict[str, object]] = []
    for target in targets:
        row: dict[str, object] = dict(target)
        metadata = entries.get(str(Path(target["path"]).resolve()))
        if metadata:
            row["metadata"] = metadata
            row["source"] = "project-metadata" if target["source"] == "project-metadata" else target["source"]
        enriched.append(row)
    return enriched


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
) -> list[dict[str, object]]:
    """Resolve exact repository targets without changing filesystem or Git state."""
    root = root.resolve()
    explicit = [(path, "explicit-repository") for path in repositories]
    if explicit:
        return _enrich_with_metadata(root, _resolve_candidates(root, explicit))

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
        return _enrich_with_metadata(root, resolved)
    resolved = _resolve_candidates(root, references)
    if resolved:
        return _enrich_with_metadata(root, resolved)
    return _enrich_with_metadata(
        root,
        _resolve_candidates(root, ((path, "project-metadata") for path in _metadata_repositories(root))),
    )


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


def _porcelain_paths(line: str) -> list[str]:
    if len(line) < 4:
        return []
    rest = line[3:]
    if " -> " in rest:
        old, new = rest.split(" -> ", 1)
        return [old, new]
    return [rest]


def _path_digest(root: Path, relative: str) -> str:
    target = root / relative
    if not target.exists():
        return "missing"
    if not target.is_file() or target.is_symlink():
        return "non-file"
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _index_entries(ls_files_output: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in ls_files_output.splitlines():
        if "\t" not in line:
            continue
        meta, relative = line.split("\t", 1)
        parts = meta.split()
        if len(parts) < 2:
            continue
        stage = parts[2] if len(parts) > 2 else "0"
        entries[relative] = f"{parts[0]} {parts[1]} {stage}"
    return entries


def capture_repository_evidence(repository: Path) -> dict[str, object]:
    """Capture HEAD/tree, index identity, and content state for dirty/untracked paths."""
    path = repository.resolve()
    inspected = inspect_repository_state(path)
    head = _run_git(path, "rev-parse", "HEAD")
    tree = _run_git(path, "rev-parse", "HEAD^{tree}")
    ls_files = _run_git(path, "ls-files", "-s")
    if head.returncode != 0 or tree.returncode != 0:
        raise RuntimeError("Git identity is unavailable for repository evidence")
    index_entries = _index_entries(ls_files.stdout)
    entries: dict[str, dict[str, str]] = {}
    for line in inspected.get("changes") or []:
        text = str(line)
        for relative in _porcelain_paths(text):
            entries[relative] = {
                "porcelain": text[:2],
                "digest": _path_digest(path, relative),
                "index": index_entries.get(relative, ""),
            }
    return {
        "head": head.stdout.strip(),
        "tree": tree.stdout.strip(),
        "index_digest": hashlib.sha256(ls_files.stdout.encode("utf-8")).hexdigest(),
        "index_entries": index_entries,
        "entries": entries,
        "status": inspected.get("status"),
    }


def task_caused_paths(
    baseline: dict[str, object],
    terminal: dict[str, object],
    repository: Path,
) -> list[str]:
    """Paths whose HEAD/tree, index, or dirty/untracked identity changed after the baseline."""
    caused: set[str] = set()
    if baseline.get("head") != terminal.get("head") or baseline.get("tree") != terminal.get("tree"):
        diff = _run_git(
            repository.resolve(),
            "diff",
            "--name-status",
            f"{baseline['head']}..{terminal['head']}",
        )
        for line in diff.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) > 1:
                caused.update(parts[1:])
    base_entries = baseline.get("entries") if isinstance(baseline.get("entries"), dict) else {}
    term_entries = terminal.get("entries") if isinstance(terminal.get("entries"), dict) else {}
    for relative in set(base_entries) | set(term_entries):
        if base_entries.get(relative) != term_entries.get(relative):
            caused.add(str(relative))
    base_index = baseline.get("index_entries") if isinstance(baseline.get("index_entries"), dict) else {}
    term_index = terminal.get("index_entries") if isinstance(terminal.get("index_entries"), dict) else {}
    for relative in set(base_index) | set(term_index):
        if base_index.get(relative) != term_index.get(relative):
            caused.add(str(relative))
    return sorted(caused)


def inspect_repository_state(
    repository: Path,
    *,
    source: str = "explicit-repository",
    metadata: dict[str, object] | None = None,
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

    if metadata:
        actual_branch = _run_git(path, "branch", "--show-current").stdout.strip()
        actual_head = _run_git(path, "rev-parse", "HEAD").stdout.strip()
        expected_branch = str(metadata.get("expected_branch") or metadata.get("working_branch") or "")
        expected_head = str(metadata.get("observed_head") or metadata.get("last_commit_id") or "")
        branch_status = "not-applicable"
        commit_status = "not-applicable"
        if bool(metadata.get("git_repository")):
            branch_status = "matched" if expected_branch == actual_branch else "mismatch"
            if str(metadata.get("baseline_status") or "") == "local-observation":
                commit_status = "current-observation"
            elif expected_head:
                commit_status = "matched" if expected_head == actual_head else "stale"
            elif str(metadata.get("baseline_status") or "") == "unborn":
                commit_status = "unborn"
            else:
                commit_status = "missing"
        codegraph_metadata = metadata.get("codegraph") if isinstance(metadata.get("codegraph"), dict) else {}
        codegraph_index_present = (path / ".codegraph").is_dir()
        result["metadata"] = {
            "repository_id": metadata.get("id"),
            "expected_branch": expected_branch or None,
            "actual_branch": actual_branch or None,
            "branch_status": branch_status,
            "expected_commit": expected_head or None,
            "actual_commit": actual_head or None,
            "commit_status": commit_status,
            "baseline_status": metadata.get("baseline_status"),
            "codegraph": {
                "supported": bool(codegraph_metadata.get("supported")),
                "index_present": bool(codegraph_metadata.get("index_present")),
                "actual_index_present": codegraph_index_present,
                "status": codegraph_metadata.get("status") or ("indexed" if codegraph_index_present else "not-indexed"),
                "synced_commit_id": codegraph_metadata.get("synced_commit_id") or "",
                "reason": codegraph_metadata.get("reason") or ("" if codegraph_index_present else "no-index"),
            },
        }
        if branch_status == "mismatch":
            result["status"] = "branch-mismatch"
            return result
        if commit_status in {"stale", "missing"}:
            result["status"] = "stale-baseline"
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
    targets: Iterable[dict[str, object]],
    accepted_baselines: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    accepted_baselines = accepted_baselines or {}
    repositories = [
        inspect_repository_state(
            Path(str(target["path"])),
            source=str(target["source"]),
            metadata=target.get("metadata") if isinstance(target.get("metadata"), dict) else None,
            accepted_changes=accepted_baselines.get(str(target["path"])),
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
    root = resolve_workspace_root(args)
    targets = resolve_target_repositories(
        root,
        task_files=((Path(path) if Path(path).is_absolute() else root / path).resolve() for path in args.task_file),
        referenced_files=(Path(path) for path in args.reference),
        repositories=(Path(path) for path in args.repository),
    )
    print(json.dumps(repository_preflight(targets, _load_baselines(args.accepted_baseline)), ensure_ascii=False, sort_keys=True))
