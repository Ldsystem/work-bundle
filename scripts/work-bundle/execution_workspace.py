from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

# Load the sibling module by path: both script families expose a top-level
# `core.py`, and shared Python harnesses must not bind this helper to the other one.
_core_spec = importlib.util.spec_from_file_location("_work_bundle_core", Path(__file__).with_name("core.py"))
if _core_spec is None or _core_spec.loader is None:
    raise ImportError("cannot load Work-Bundle core")
_work_bundle_core = importlib.util.module_from_spec(_core_spec)
_core_spec.loader.exec_module(_work_bundle_core)
out = _work_bundle_core.out
utc_now_rfc3339 = _work_bundle_core.utc_now_rfc3339
work_bundle_config_root = _work_bundle_core.work_bundle_config_root
from workspace_resources import _load_yaml


OWNERS = frozenset({"work-bundle", "harness", "user"})
KINDS = frozenset({"worktree", "existing"})
CLEANUP_POLICIES = frozenset({"after_integration", "manual"})
HYDRATION_STRATEGIES = frozenset({"regenerate", "copy", "credential-inject", "symlink-readonly", "omit"})
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SECRET_SUFFIXES = frozenset({".key", ".pem", ".secret", ".p12", ".pfx"})


class ExecutionWorkspaceError(RuntimeError):
    def __init__(self, code: str, result: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.result = result or {}


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise ExecutionWorkspaceError(
            "WB_EXECUTION_GIT_FAILED",
            {"git_exit_code": result.returncode, "git_error": (result.stderr.strip() or "git failed")[:300]},
        )
    return result.stdout.strip()


def _safe_component(value: str, field: str) -> str:
    if not SAFE_COMPONENT.fullmatch(value):
        raise ExecutionWorkspaceError("WB_EXECUTION_ID_INVALID", {"field": field})
    return value


def _relative_path(value: object) -> Path:
    raw = str(value or "").strip()
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts or candidate == Path("."):
        raise ExecutionWorkspaceError("WB_EXECUTION_HYDRATION_PATH_INVALID", {"path": raw})
    return candidate


def default_runtime_root() -> Path:
    return work_bundle_config_root() / "worktrees"


def _inside(root: Path, candidate: Path) -> bool:
    root = root.resolve()
    candidate = candidate.resolve(strict=False)
    return candidate == root or root in candidate.parents


def workspace_path(
    runtime_root: Path,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
) -> Path:
    parts = (
        _safe_component(workspace_id, "workspace_id"),
        _safe_component(execution_id, "execution_id"),
        _safe_component(repository_id, "repository_id"),
    )
    root = runtime_root.expanduser().resolve()
    candidate = root / parts[0] / parts[1] / parts[2]
    if not _inside(root, candidate):
        raise ExecutionWorkspaceError("WB_EXECUTION_RUNTIME_PATH_ESCAPE")
    return candidate.resolve(strict=False)


def state_path(
    runtime_root: Path,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
) -> Path:
    target = workspace_path(runtime_root, workspace_id, execution_id, repository_id)
    root = runtime_root.expanduser().resolve()
    candidate = target.parent / ".state" / f"{target.name}.json"
    if not _inside(root, candidate):
        raise ExecutionWorkspaceError("WB_EXECUTION_RUNTIME_PATH_ESCAPE")
    return candidate.resolve(strict=False)


def _is_secret_copy_path(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    name = path.name.lower()
    return (
        any(part in {"credential", "credentials", "secret", "secrets"} for part in lowered)
        or name == ".env"
        or name.startswith(".env.")
        or path.suffix.lower() in SECRET_SUFFIXES
    )


def hydrate_workspace(source_root: Path, target_root: Path, profile: dict[str, object]) -> list[dict[str, str]]:
    """Apply only explicitly safe hydration and classify deferred strategies.

    Credential-inject entries are deliberately never opened. Regeneration is
    reported for the owning tool/project setup to perform in the isolated root.
    """
    source_root = source_root.expanduser().resolve()
    target_root = target_root.expanduser().resolve()
    entries = profile.get("hydrate", [])
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ExecutionWorkspaceError("WB_EXECUTION_HYDRATION_PROFILE_INVALID")
    report: list[dict[str, str]] = []
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise ExecutionWorkspaceError("WB_EXECUTION_HYDRATION_ENTRY_INVALID", {"index": index})
        relative = _relative_path(raw_entry.get("path"))
        strategy = str(raw_entry.get("strategy") or "")
        if strategy not in HYDRATION_STRATEGIES:
            raise ExecutionWorkspaceError("WB_EXECUTION_HYDRATION_STRATEGY_INVALID", {"index": index})
        public = {"path": relative.as_posix(), "strategy": strategy}
        if strategy == "regenerate":
            report.append({**public, "classification": "regenerate-required"})
            continue
        if strategy == "credential-inject":
            report.append({**public, "classification": "credential-boundary-required"})
            continue
        if strategy == "omit":
            report.append({**public, "classification": "omitted"})
            continue

        sensitivity = str(raw_entry.get("sensitivity") or "")
        if sensitivity != "non-secret" or _is_secret_copy_path(relative):
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_HYDRATION_SECRET_COPY_FORBIDDEN",
                {"index": index, "path": relative.as_posix()},
            )
        if relative.parts[0] == ".codegraph":
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_CODEGRAPH_SHARED_STATE_FORBIDDEN",
                {"index": index, "path": relative.as_posix()},
            )
        source = source_root / relative
        destination = target_root / relative
        if not _inside(source_root, source) or not _inside(target_root, destination):
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_HYDRATION_PATH_ESCAPE",
                {"index": index, "path": relative.as_posix()},
            )
        if not source.is_file() or source.is_symlink():
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_HYDRATION_SOURCE_INVALID",
                {"index": index, "path": relative.as_posix()},
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_HYDRATION_COLLISION",
                {"index": index, "path": relative.as_posix()},
            )
        if strategy == "copy":
            shutil.copy2(source, destination, follow_symlinks=False)
            report.append({**public, "classification": "copied-non-secret"})
            continue
        if raw_entry.get("concurrent_safe") is not True:
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_SYMLINK_SAFETY_UNPROVEN",
                {"index": index, "path": relative.as_posix()},
            )
        if source.stat().st_mode & 0o222:
            raise ExecutionWorkspaceError(
                "WB_EXECUTION_SYMLINK_SOURCE_WRITABLE",
                {"index": index, "path": relative.as_posix()},
            )
        destination.symlink_to(source)
        report.append({**public, "classification": "symlinked-readonly"})
    return report


def load_hydration_profile(workspace_root: Path, profile_name: str) -> dict[str, object]:
    metadata_path = workspace_root.expanduser().resolve() / ".work-bundle" / "project.yaml"
    if not metadata_path.is_file():
        raise ExecutionWorkspaceError("WB_PROJECT_METADATA_MISSING")
    try:
        document = _load_yaml(metadata_path.read_text(encoding="utf-8"))
    except (ValueError, TypeError, SyntaxError):
        raise ExecutionWorkspaceError("WB_PROJECT_METADATA_INVALID") from None
    if not isinstance(document, dict):
        raise ExecutionWorkspaceError("WB_PROJECT_METADATA_INVALID")
    profiles = document.get("execution_workspace_profiles")
    if not isinstance(profiles, dict) or not isinstance(profiles.get(profile_name), dict):
        raise ExecutionWorkspaceError("WB_EXECUTION_HYDRATION_PROFILE_MISSING", {"profile": profile_name})
    return dict(profiles[profile_name])


def _worktree_entries(source_repository: Path) -> list[dict[str, str]]:
    output = _git("-C", str(source_repository), "worktree", "list", "--porcelain")
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return entries


def _git_identity(source_repository: Path, target: Path) -> dict[str, str]:
    target = target.resolve()
    entry = next(
        (item for item in _worktree_entries(source_repository) if Path(item.get("worktree", "")).resolve() == target),
        None,
    )
    if entry is None:
        raise ExecutionWorkspaceError("WB_EXECUTION_GIT_IDENTITY_MISMATCH")
    return {
        "source_repository": str(source_repository.resolve()),
        "git_common_dir": str(Path(_git("-C", str(target), "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()),
        "git_dir": str(Path(_git("-C", str(target), "rev-parse", "--path-format=absolute", "--git-dir")).resolve()),
        "head": _git("-C", str(target), "rev-parse", "HEAD"),
        "branch_ref": entry.get("branch", ""),
    }


def _write_state(path: Path, state: dict[str, object], identity: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"execution_workspace_state": state, "git_identity": identity}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prepare_worktree(
    source_repository: Path,
    *,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
    branch: str,
    created_for: str,
    runtime_root: Path | None = None,
    cleanup_policy: str = "after_integration",
    hydration_profile: str = "default",
    profile: dict[str, object] | None = None,
) -> dict[str, object]:
    source_repository = source_repository.expanduser().resolve()
    runtime_root = (runtime_root or default_runtime_root()).expanduser().resolve()
    target = workspace_path(runtime_root, workspace_id, execution_id, repository_id)
    record = state_path(runtime_root, workspace_id, execution_id, repository_id)
    if cleanup_policy not in CLEANUP_POLICIES:
        raise ExecutionWorkspaceError("WB_EXECUTION_CLEANUP_POLICY_INVALID")
    if not source_repository.is_dir():
        raise ExecutionWorkspaceError("WB_EXECUTION_SOURCE_MISSING")
    if target.exists() or target.is_symlink() or record.exists():
        raise ExecutionWorkspaceError("WB_EXECUTION_WORKSPACE_COLLISION", {"path": str(target)})
    branch_exists = subprocess.run(
        ["git", "-C", str(source_repository), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        text=True,
        capture_output=True,
        check=False,
    ).returncode == 0
    if branch_exists or any(item.get("branch") == f"refs/heads/{branch}" for item in _worktree_entries(source_repository)):
        raise ExecutionWorkspaceError("WB_EXECUTION_BRANCH_CONFLICT", {"branch": branch})
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git("-C", str(source_repository), "worktree", "add", "-b", branch, str(target), "HEAD")
        identity = _git_identity(source_repository, target)
        hydration = hydrate_workspace(source_repository, target, profile or {"hydrate": []})
        state: dict[str, object] = {
            "id": execution_id,
            "kind": "worktree",
            "owner": "work-bundle",
            "repository_id": repository_id,
            "path": str(target),
            "branch": branch,
            "created_for": created_for,
            "cleanup_policy": cleanup_policy,
            "hydration_profile": hydration_profile,
            "created_at": utc_now_rfc3339(),
        }
        _write_state(record, state, identity)
    except Exception:
        if target.exists():
            subprocess.run(
                ["git", "-C", str(source_repository), "worktree", "remove", "--force", str(target)],
                text=True,
                capture_output=True,
                check=False,
            )
        subprocess.run(
            ["git", "-C", str(source_repository), "branch", "-D", branch],
            text=True,
            capture_output=True,
            check=False,
        )
        record.unlink(missing_ok=True)
        raise
    return {
        "status": "prepared",
        "execution_workspace_state": state,
        "git_identity": identity,
        "hydration": hydration,
        "setup": list((profile or {}).get("setup", [])) if isinstance((profile or {}).get("setup", []), list) else [],
        "baseline": list((profile or {}).get("baseline", [])) if isinstance((profile or {}).get("baseline", []), list) else [],
        "state_path": str(record),
    }


def register_existing(
    path: Path,
    *,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
    created_for: str,
    owner: str,
    runtime_root: Path | None = None,
    cleanup_policy: str = "manual",
    hydration_profile: str = "default",
) -> dict[str, object]:
    """Record an existing harness/user workspace without taking cleanup ownership."""
    if owner not in {"harness", "user"}:
        raise ExecutionWorkspaceError("WB_EXECUTION_EXISTING_OWNER_INVALID")
    if cleanup_policy not in CLEANUP_POLICIES:
        raise ExecutionWorkspaceError("WB_EXECUTION_CLEANUP_POLICY_INVALID")
    path = path.expanduser().resolve()
    runtime_root = (runtime_root or default_runtime_root()).expanduser().resolve()
    record = state_path(runtime_root, workspace_id, execution_id, repository_id)
    if record.exists():
        raise ExecutionWorkspaceError("WB_EXECUTION_WORKSPACE_COLLISION", {"state_path": str(record)})
    identity = _git_identity(path, path)
    branch_ref = identity.get("branch_ref", "")
    branch = branch_ref.removeprefix("refs/heads/")
    state: dict[str, object] = {
        "id": execution_id,
        "kind": "existing",
        "owner": owner,
        "repository_id": repository_id,
        "path": str(path),
        "branch": branch,
        "created_for": created_for,
        "cleanup_policy": cleanup_policy,
        "hydration_profile": hydration_profile,
        "created_at": utc_now_rfc3339(),
    }
    _write_state(record, state, identity)
    return {
        "status": "registered",
        "execution_workspace_state": state,
        "git_identity": identity,
        "hydration": [],
        "state_path": str(record),
    }


def _read_record(path: Path) -> tuple[dict[str, object], dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_MISSING")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_INVALID") from None
    state = document.get("execution_workspace_state") if isinstance(document, dict) else None
    identity = document.get("git_identity") if isinstance(document, dict) else None
    required = {
        "id", "kind", "owner", "repository_id", "path", "branch", "created_for",
        "cleanup_policy", "hydration_profile", "created_at",
    }
    if not isinstance(state, dict) or not required.issubset(state) or not isinstance(identity, dict):
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_INVALID")
    if state.get("kind") not in KINDS or state.get("owner") not in OWNERS:
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_INVALID")
    return state, {str(key): str(value) for key, value in identity.items()}


def _identity_matches(state: dict[str, object], expected: dict[str, str]) -> bool:
    if state.get("kind") not in KINDS:
        return False
    target = Path(str(state["path"]))
    source_raw = expected.get("source_repository", "")
    if not target.is_dir() or not source_raw:
        return False
    try:
        actual = _git_identity(Path(source_raw), target)
    except ExecutionWorkspaceError:
        return False
    # HEAD is creation provenance, not stable identity: task commits may advance it.
    keys = {"source_repository", "git_common_dir", "git_dir", "branch_ref"}
    return all(actual.get(key) == expected.get(key) for key in keys)


def workspace_status(
    runtime_root: Path,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
) -> dict[str, object]:
    record = state_path(runtime_root, workspace_id, execution_id, repository_id)
    state, identity = _read_record(record)
    target = Path(str(state["path"]))
    matched = _identity_matches(state, identity)
    status = "active" if matched else ("stale-missing" if not target.exists() else "identity-mismatch")
    return {
        "status": status,
        "git_identity": "matched" if matched else "mismatched",
        "execution_workspace_state": state,
        "state_path": str(record),
    }


def _remove_empty_runtime_parents(record: Path, runtime_root: Path) -> None:
    runtime_root = runtime_root.resolve()
    for candidate in (record.parent, record.parent.parent, record.parent.parent.parent):
        if candidate == runtime_root or runtime_root not in candidate.resolve().parents:
            break
        try:
            candidate.rmdir()
        except OSError:
            pass


def cleanup_owned(
    runtime_root: Path,
    workspace_id: str,
    execution_id: str,
    repository_id: str,
) -> dict[str, object]:
    runtime_root = runtime_root.expanduser().resolve()
    record = state_path(runtime_root, workspace_id, execution_id, repository_id)
    state, identity = _read_record(record)
    if state.get("owner") != "work-bundle" or state.get("kind") != "worktree":
        raise ExecutionWorkspaceError("WB_EXECUTION_WORKSPACE_NOT_OWNED")
    if state.get("id") != execution_id or state.get("repository_id") != repository_id:
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_IDENTITY_MISMATCH")
    if identity.get("branch_ref") != f"refs/heads/{state.get('branch', '')}":
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_IDENTITY_MISMATCH")
    expected_target = workspace_path(runtime_root, workspace_id, execution_id, repository_id)
    if Path(str(state.get("path", ""))).resolve() != expected_target:
        raise ExecutionWorkspaceError("WB_EXECUTION_PROVENANCE_PATH_MISMATCH")
    if not _identity_matches(state, identity):
        raise ExecutionWorkspaceError("WB_EXECUTION_GIT_IDENTITY_MISMATCH")
    dirty = _git("-C", str(expected_target), "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise ExecutionWorkspaceError(
            "WB_EXECUTION_WORKSPACE_DIRTY",
            {"changed_paths": [line[3:] for line in dirty.splitlines() if len(line) > 3]},
        )
    source_repository = Path(identity["source_repository"])
    _git("-C", str(source_repository), "worktree", "remove", "--force", str(expected_target))
    if expected_target.exists():
        raise ExecutionWorkspaceError("WB_EXECUTION_CLEANUP_INCOMPLETE")
    record.unlink()
    _remove_empty_runtime_parents(record, runtime_root)
    return {"status": "cleaned", "path": str(expected_target), "state_path": str(record)}


def _state_records(runtime_root: Path) -> list[Path]:
    root = runtime_root.expanduser().resolve()
    return sorted(path for path in root.glob("*/*/.state/*.json") if path.is_file() and not path.is_symlink())


def doctor_stale(runtime_root: Path, *, max_age_hours: int = 168, cleanup: bool = False) -> dict[str, object]:
    if max_age_hours < 0:
        raise ExecutionWorkspaceError("WB_EXECUTION_STALE_AGE_INVALID")
    runtime_root = runtime_root.expanduser().resolve()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stale: list[dict[str, object]] = []
    cleaned = 0
    for record in _state_records(runtime_root):
        try:
            state, _ = _read_record(record)
            created = datetime.fromisoformat(str(state["created_at"]).replace("Z", "+00:00"))
        except (ExecutionWorkspaceError, TypeError, ValueError):
            stale.append({"state_path": str(record), "reason": "invalid-provenance", "cleaned": False})
            continue
        if state.get("owner") != "work-bundle" or created > cutoff:
            continue
        item: dict[str, object] = {
            "state_path": str(record),
            "path": str(state["path"]),
            "created_at": str(state["created_at"]),
            "reason": "age-threshold-exceeded",
            "cleaned": False,
        }
        if cleanup and state.get("cleanup_policy") == "after_integration":
            workspace_id = record.parents[2].name
            execution_id = record.parents[1].name
            repository_id = record.stem
            try:
                cleanup_owned(runtime_root, workspace_id, execution_id, repository_id)
                item["cleaned"] = True
                cleaned += 1
            except ExecutionWorkspaceError as exc:
                item["cleanup_failure_code"] = exc.code
        stale.append(item)
    return {
        "status": "reported",
        "runtime_root": str(runtime_root),
        "max_age_hours": max_age_hours,
        "cleanup_permitted": cleanup,
        "stale_count": len(stale),
        "cleaned_count": cleaned,
        "stale": stale,
    }


def cmd_execution_workspace(action: str, argv: list[str]) -> int:
    prog = f"wb.py execution-workspace-{action}"
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--runtime-root", type=Path, default=default_runtime_root())
    if action == "prepare":
        parser.add_argument("--workspace-root", type=Path)
        parser.add_argument("--source-repository", type=Path, required=True)
        parser.add_argument("--workspace-id", required=True)
        parser.add_argument("--execution-id", required=True)
        parser.add_argument("--repository-id", required=True)
        parser.add_argument("--branch")
        parser.add_argument("--created-for", required=True)
        parser.add_argument("--profile", default="default")
        parser.add_argument("--cleanup-policy", choices=sorted(CLEANUP_POLICIES))
        parser.add_argument("--kind", choices=sorted(KINDS), default="worktree")
        parser.add_argument("--owner", choices=sorted(OWNERS), default="work-bundle")
    elif action in {"status", "cleanup-owned"}:
        parser.add_argument("--workspace-id", required=True)
        parser.add_argument("--execution-id", required=True)
        parser.add_argument("--repository-id", required=True)
    elif action == "doctor-stale":
        parser.add_argument("--max-age-hours", type=int, default=168)
        parser.add_argument("--cleanup", action="store_true")
    else:
        raise ValueError("unsupported execution workspace action")
    parsed = parser.parse_args(argv)
    try:
        if action == "prepare":
            if parsed.kind == "existing":
                result = register_existing(
                    parsed.source_repository,
                    workspace_id=parsed.workspace_id,
                    execution_id=parsed.execution_id,
                    repository_id=parsed.repository_id,
                    created_for=parsed.created_for,
                    owner=parsed.owner,
                    runtime_root=parsed.runtime_root,
                    cleanup_policy=parsed.cleanup_policy or "manual",
                    hydration_profile=parsed.profile,
                )
            else:
                if parsed.owner != "work-bundle":
                    raise ExecutionWorkspaceError("WB_EXECUTION_WORKTREE_OWNER_INVALID")
                if parsed.workspace_root is None:
                    raise ExecutionWorkspaceError("WB_EXECUTION_WORKSPACE_ROOT_REQUIRED")
                if not parsed.branch:
                    raise ExecutionWorkspaceError("WB_EXECUTION_BRANCH_REQUIRED")
                profile = load_hydration_profile(parsed.workspace_root, parsed.profile)
                result = prepare_worktree(
                    parsed.source_repository,
                    workspace_id=parsed.workspace_id,
                    execution_id=parsed.execution_id,
                    repository_id=parsed.repository_id,
                    branch=parsed.branch,
                    created_for=parsed.created_for,
                    runtime_root=parsed.runtime_root,
                    cleanup_policy=parsed.cleanup_policy or "after_integration",
                    hydration_profile=parsed.profile,
                    profile=profile,
                )
        elif action == "status":
            result = workspace_status(
                parsed.runtime_root, parsed.workspace_id, parsed.execution_id, parsed.repository_id
            )
        elif action == "cleanup-owned":
            result = cleanup_owned(
                parsed.runtime_root, parsed.workspace_id, parsed.execution_id, parsed.repository_id
            )
        else:
            result = doctor_stale(
                parsed.runtime_root, max_age_hours=parsed.max_age_hours, cleanup=parsed.cleanup
            )
    except ExecutionWorkspaceError as exc:
        out({"command": f"execution-workspace-{action}", "status": "blocked", "failure_code": exc.code, **exc.result})
        return 1
    out({"command": f"execution-workspace-{action}", **result})
    return 0
