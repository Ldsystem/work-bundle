from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Iterable
from urllib.parse import parse_qsl, urlsplit

from core import (
    out,
    read,
    resolve_project_registry_path,
    resolve_work_bundle_root,
    utc_now_rfc3339,
)
from workspace_resources import _load_yaml, ensure_workspace_resources


VERSION = "4"
LOCAL_ONLY_GITIGNORE_REFERENCE = Path("references/wb-control-plane-default-gitignore")
AGENTS_TEMPLATE_REFERENCE = Path("references/assets/template/AGENTS.md")
AGENTS_START = "# ========================\n# Work Bundle RULE START\n# ========================"
AGENTS_END = "# ========================\n# Work Bundle RULE END\n# ========================"
LOCAL_V3_KEYS = {
    "workspace_root",
    "workspace_mode",
    "project_root",
    "source_repository_roles",
    "operation_policy",
    "lifecycle_transaction",
    "migration",
    "source_repositories",
    "metadata_compatibility",
}
RESERVED_V4_KEYS = {"metadata_version", "authority", "workspace", "control_plane", "source_repositories"}


class ControlPlaneError(RuntimeError):
    def __init__(self, code: str, details: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def _local_only_gitignore() -> str:
    toolkit_root = resolve_work_bundle_root()
    path = toolkit_root / LOCAL_ONLY_GITIGNORE_REFERENCE if toolkit_root else None
    if path is None or not path.is_file():
        raise ControlPlaneError("WB_CONTROL_PLANE_GITIGNORE_REFERENCE_MISSING")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n") + "\n"


def _merged_local_only_gitignore(existing: str) -> str:
    required = _local_only_gitignore()
    if not existing:
        return required
    normalized = existing.replace("\r\n", "\n")
    present = {line.strip() for line in normalized.splitlines() if line.strip()}
    missing = [
        line for line in required.splitlines()
        if line and not line.startswith("#") and line not in present
    ]
    if not missing:
        return normalized
    preserved = normalized if normalized.endswith("\n") else normalized + "\n"
    prefix = "# WorkBundle required portable control-plane exclusions\n" + "\n".join(missing) + "\n\n"
    return prefix + preserved


def _agents_template() -> str:
    toolkit_root = resolve_work_bundle_root()
    path = toolkit_root / AGENTS_TEMPLATE_REFERENCE if toolkit_root else None
    if path is None or not path.is_file():
        raise ControlPlaneError("WB_CONTROL_PLANE_AGENTS_REFERENCE_MISSING")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n") + "\n"


def _agents_contract_block() -> str:
    checksum = hashlib.sha256(_agents_template().encode("utf-8")).hexdigest()
    return "\n".join([
        "agents_sync:",
        "  managed_section: work-bundle-rule",
        "  template_path: references/assets/template/AGENTS.md",
        f'  template_checksum_sha256: "{checksum}"',
        "  status: current",
    ])


def _sync_agents(workspace_root: Path) -> list[str]:
    template = _agents_template()
    managed = f"{AGENTS_START}\n{template}{AGENTS_END}\n"
    path = workspace_root / "AGENTS.md"
    current = read(path)
    spans: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = current.find(AGENTS_START, cursor)
        if start < 0:
            break
        end_start = current.find(AGENTS_END, start + len(AGENTS_START))
        if end_start < 0:
            break
        end = end_start + len(AGENTS_END)
        if current.startswith("\n", end):
            end += 1
        spans.append((start, end))
        cursor = end
    if spans:
        pieces: list[str] = []
        previous = 0
        for index, (start, end) in enumerate(spans):
            pieces.append(current[previous:start])
            if index == 0:
                pieces.append(managed)
            previous = end
        pieces.append(current[previous:])
        rendered = "".join(pieces)
    elif current:
        rendered = current.rstrip("\n") + "\n\n" + managed
    else:
        rendered = managed
    return [str(path)] if _atomic_write(path, rendered) else []


def _repository_execution_issues(path: Path, expected_branch: str, repository_id: str) -> list[str]:
    issues: list[str] = []
    actual_branch = _git(path, "branch", "--show-current")
    if expected_branch and expected_branch != "manual" and actual_branch != expected_branch:
        issues.append(f"WB_CONTROL_PLANE_BRANCH_MISMATCH:{repository_id}")
    if _git(path, "status", "--porcelain=v1", "--untracked-files=all"):
        issues.append(f"WB_CONTROL_PLANE_CHECKOUT_DIRTY:{repository_id}")
    return issues


def _top_level_blocks(text: str) -> dict[str, list[str]]:
    lines = text.splitlines()
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s|$)", line)
        if match:
            current = match.group(1)
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    return blocks


def _block(text: str, key: str) -> str:
    return "\n".join(_top_level_blocks(text).get(key, []))


def _parse_bool(value: str, default: bool = False) -> bool:
    normalized = value.strip().strip('"').strip("'").lower()
    if normalized in {"true", "yes", "on", "1"}:
        return True
    if normalized in {"false", "no", "off", "0"}:
        return False
    return default


def _parse_list_items(block: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    nested: dict[str, object] | None = None
    for raw in block.splitlines()[1:]:
        stripped = raw.strip()
        if not stripped:
            continue
        if raw.startswith("  - "):
            if current is not None:
                items.append(current)
            current = {}
            nested = None
            value = stripped[2:]
            if ":" in value:
                key, scalar = value.split(":", 1)
                current[key.strip()] = scalar.strip().strip('"').strip("'")
            continue
        if current is None:
            continue
        if raw.startswith("    ") and not raw.startswith("      ") and ":" in stripped:
            key, scalar = stripped.split(":", 1)
            scalar = scalar.strip()
            if not scalar:
                nested = {}
                current[key] = nested
            else:
                current[key] = scalar.strip('"').strip("'")
                nested = None
            continue
        if raw.startswith("      ") and nested is not None and ":" in stripped:
            key, scalar = stripped.split(":", 1)
            nested[key] = scalar.strip().strip('"').strip("'")
    if current is not None:
        items.append(current)
    return items


def _quote(value: object) -> str:
    text = str(value or "")
    if not text:
        return '""'
    if re.search(r"[\s:#\[\]{},&*?|<>=!%@`\"']", text):
        return json.dumps(text, ensure_ascii=False)
    return text


def canonical_remote(value: object) -> str:
    remote = str(value or "").strip()
    if not remote:
        return ""
    if re.match(r"^[^/@:\s]+@[^/:\s]+:[^\s]+$", remote):
        user_host, path = remote.split(":", 1)
        remote = f"ssh://{user_host}/{path}"
    if remote.startswith("file://"):
        remote = str(Path(remote[7:]).expanduser().resolve())
    elif remote.startswith(("/", "./", "../", "~")):
        remote = str(Path(remote).expanduser().resolve())
    remote = remote.rstrip("/")
    return remote[:-4] if remote.endswith(".git") and "://" in remote else remote


def validated_remote(value: object) -> str:
    raw = str(value or "").strip()
    if "://" in raw:
        parsed = urlsplit(raw)
        sensitive_query = {"token", "access_token", "password", "passwd", "secret", "key", "credential"}
        if parsed.password is not None or (parsed.username is not None and parsed.scheme in {"http", "https"}) or any(
            key.lower() in sensitive_query for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise ControlPlaneError("WB_CONTROL_PLANE_REMOTE_CREDENTIALS_FORBIDDEN")
    return canonical_remote(raw)


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args], check=False, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_remote(path: Path) -> str:
    return validated_remote(_git(path, "remote", "get-url", "origin"))


def _local_remote_path(remote: str, repository_path: Path) -> Path | None:
    raw = remote.strip()
    if raw.startswith("file://"):
        return Path(raw[7:]).expanduser().resolve()
    if raw.startswith(("/", "~")):
        return Path(raw).expanduser().resolve()
    if raw.startswith(("./", "../")):
        return (repository_path / raw).resolve()
    return None


def _resolved_git_remote(path: Path) -> str:
    current = path.expanduser().resolve()
    seen: set[Path] = set()
    for depth in range(12):
        if current in seen:
            raise ControlPlaneError("WB_CONTROL_PLANE_REMOTE_CHAIN_CYCLE")
        seen.add(current)
        raw = _git(current, "remote", "get-url", "origin")
        if not raw:
            if depth:
                return canonical_remote(str(current))
            raise ControlPlaneError("WB_CONTROL_PLANE_REMOTE_REQUIRED")
        validated_remote(raw)
        local = _local_remote_path(raw, current)
        if local is None:
            return canonical_remote(raw)
        if not local.exists():
            raise ControlPlaneError("WB_CONTROL_PLANE_LOCAL_REMOTE_MISSING")
        current = local
    raise ControlPlaneError("WB_CONTROL_PLANE_REMOTE_CHAIN_LIMIT_EXCEEDED")


def _resolved_declared_remote(value: object, repository_path: Path) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    validated_remote(raw)
    local = _local_remote_path(raw, repository_path)
    if local is None:
        return canonical_remote(raw)
    if not local.exists():
        raise ControlPlaneError("WB_CONTROL_PLANE_LOCAL_REMOTE_MISSING")
    if not _git(local, "remote", "get-url", "origin"):
        return canonical_remote(str(local))
    return _resolved_git_remote(local)


def _registry_repository_remotes(workspace_root: Path) -> dict[str, str]:
    registry = resolve_project_registry_path()
    document = _load_yaml(read(registry)) if registry.is_file() else {}
    projects = document.get("projects") if isinstance(document, dict) else None
    if not isinstance(projects, list):
        return {}
    control = (workspace_root / ".work-bundle").resolve()
    matches: list[dict[str, object]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        raw_root = str(project.get("work_bundle_root") or "")
        if raw_root and Path(raw_root).expanduser().resolve() == control:
            matches.append(project)
    if len(matches) > 1:
        raise ControlPlaneError("WB_CONTROL_PLANE_REGISTRY_WORKSPACE_AMBIGUOUS")
    if not matches:
        return {}
    repositories = matches[0].get("repository_origins")
    if not isinstance(repositories, list):
        repositories = matches[0].get("source_repositories")
    if not isinstance(repositories, list):
        return {}
    result: dict[str, str] = {}
    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        repository_id = str(repository.get("id") or "")
        remote = str(repository.get("remote") or "")
        if repository_id and remote:
            result[repository_id] = remote
    return result


def _is_local_remote(remote: str, repository_path: Path) -> bool:
    return _local_remote_path(remote, repository_path) is not None


def _canonical_migration_remote(
    repository_id: str,
    repository_path: Path,
    declared: object,
    registry: object,
    override: object,
) -> str:
    live = _resolved_git_remote(repository_path)
    if override:
        return _resolved_declared_remote(override, repository_path)
    declared_remote = _resolved_declared_remote(declared, repository_path) if declared else ""
    registry_remote = _resolved_declared_remote(registry, repository_path) if registry else ""
    if declared_remote:
        if declared_remote != live:
            raise ControlPlaneError(
                "WB_CONTROL_PLANE_REMOTE_CONFLICT", {"repository_id": repository_id}
            )
        if registry_remote and declared_remote != registry_remote:
            raise ControlPlaneError(
                "WB_CONTROL_PLANE_CANONICAL_REMOTE_CONFLICT", {"repository_id": repository_id}
            )
        return declared_remote
    if registry_remote and registry_remote != live and not _is_local_remote(live, repository_path):
        raise ControlPlaneError(
            "WB_CONTROL_PLANE_CANONICAL_REMOTE_CONFLICT", {"repository_id": repository_id}
        )
    return registry_remote or live


def _workspace_slug(workspace_root: Path, text: str) -> str:
    workspace_block = _block(text, "workspace")
    nested_slug = re.search(r"^\s{2}slug:\s*(.*?)\s*$", workspace_block, re.MULTILINE)
    return (nested_slug.group(1).strip().strip('"').strip("'") if nested_slug else workspace_root.name) or "workspace"


def _workspace_id(text: str) -> str:
    workspace_block = _block(text, "workspace")
    match = re.search(r"^\s{2}id:\s*(.*?)\s*$", workspace_block, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def _workspace_value(text: str, key: str) -> str:
    match = re.search(rf"^\s{{2}}{re.escape(key)}:\s*(.*?)\s*$", _block(text, "workspace"), re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else ""


def _control_plane_remote(text: str) -> str:
    block = _block(text, "control_plane")
    in_repository = False
    for line in block.splitlines():
        if line == "  repository:":
            in_repository = True
            continue
        if in_repository and line.startswith("    remote:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
        if in_repository and line.startswith("  ") and not line.startswith("    "):
            break
    return ""


def _v3_repositories(text: str) -> list[dict[str, object]]:
    repositories = _parse_list_items(_block(text, "source_repositories"))
    for repository in repositories:
        repository["git_repository"] = _parse_bool(str(repository.get("git_repository", "false")))
        repository["remote"] = validated_remote(repository.get("remote"))
    return repositories


def _v4_repositories(text: str) -> list[dict[str, object]]:
    repositories = _parse_list_items(_block(text, "source_repositories"))
    # The generic parser retains remote as a mapping. Normalize its canonical field.
    for repository in repositories:
        remote = repository.get("remote")
        if isinstance(remote, dict):
            repository["canonical_remote"] = validated_remote(remote.get("canonical"))
        else:
            repository["canonical_remote"] = validated_remote(repository.get("canonical"))
        materialization = repository.get("materialization")
        locator = repository.get("locator")
        repository["locator_type"] = str(locator.get("type", "")) if isinstance(locator, dict) else ""
        repository["materialization_raw"] = (
            str(materialization.get("required", "")) if isinstance(materialization, dict) else ""
        )
        repository["required"] = (
            _parse_bool(str(materialization.get("required", "false")))
            if isinstance(materialization, dict)
            else False
        )
        workspace_binding = repository.get("workspace_binding")
        repository["workspace_binding_type"] = (
            str(workspace_binding.get("type", "")) if isinstance(workspace_binding, dict) else ""
        )
        repository["workspace_binding_name"] = (
            str(workspace_binding.get("name", "")) if isinstance(workspace_binding, dict) else ""
        )
        repository["workspace_binding_path"] = (
            str(workspace_binding.get("path", "")) if isinstance(workspace_binding, dict) else ""
        )
    return repositories


def _portable_unknown_blocks(text: str) -> list[str]:
    result: list[str] = []
    for key, lines in _top_level_blocks(text).items():
        if key in LOCAL_V3_KEYS or key in RESERVED_V4_KEYS or key in {"prefer_subagent", "agents_sync"}:
            continue
        result.append("\n".join(lines).rstrip())
    return [item for item in result if item]


def _derive_workspace_id(slug: str, repositories: Iterable[dict[str, object]]) -> str:
    identities = [
        "|".join(
            [
                str(repo.get("id", "")),
                canonical_remote(repo.get("remote")),
                str(repo.get("workspace_binding_type", "")),
                str(repo.get("workspace_binding_name", "")),
            ]
        )
        for repo in repositories
    ]
    payload = "\n".join([slug, *sorted(identities)])
    return "wb-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _render_v4(
    workspace_root: Path,
    v3_text: str,
    remote_overrides: dict[str, str] | None = None,
) -> tuple[str, str, list[dict[str, object]]]:
    mode = _yaml_scalar(v3_text, "workspace_mode") or "single-repository"
    if mode not in {"single-repository", "multi-repository"}:
        raise ControlPlaneError("WB_CONTROL_PLANE_WORKSPACE_MODE_INVALID")
    repositories = _v3_repositories(v3_text)
    if not repositories:
        raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORIES_MISSING")
    if mode == "single-repository" and len(repositories) != 1:
        raise ControlPlaneError("WB_CONTROL_PLANE_SINGLE_REPOSITORY_COUNT_INVALID")
    overrides = remote_overrides or {}
    repository_ids = {str(repository.get("id") or "") for repository in repositories}
    unknown_overrides = sorted(set(overrides) - repository_ids)
    if unknown_overrides:
        raise ControlPlaneError(
            "WB_CONTROL_PLANE_REMOTE_OVERRIDE_UNKNOWN", {"repository_id": unknown_overrides[0]}
        )
    registry_remotes = _registry_repository_remotes(workspace_root)
    for repository in repositories:
        repository_id = str(repository.get("id") or "")
        local_path = Path(str(repository.get("project_root") or "")).expanduser().resolve()
        if mode == "single-repository":
            if local_path != workspace_root:
                raise ControlPlaneError("WB_CONTROL_PLANE_ROOT_BINDING_PATH_MISMATCH")
            repository["workspace_binding_type"] = "root"
            repository["workspace_binding_name"] = ""
        else:
            repository["workspace_binding_type"] = "member"
            repository["workspace_binding_name"] = str(repository.get("id") or "")
        if bool(repository.get("git_repository")):
            try:
                actual_remote = _canonical_migration_remote(
                    repository_id,
                    local_path,
                    repository.get("remote"),
                    registry_remotes.get(repository_id),
                    overrides.get(repository_id),
                )
            except ControlPlaneError as exc:
                raise ControlPlaneError(exc.code, {"repository_id": repository.get("id")}) from exc
            repository["remote"] = actual_remote
    slug = _workspace_slug(workspace_root, v3_text)
    workspace_id = _derive_workspace_id(slug, repositories)
    lines = [
        "metadata_version: 4",
        "authority: canonical",
        "workspace:",
        f"  id: {_quote(workspace_id)}",
        f"  slug: {_quote(slug)}",
        f"  mode: {mode}",
        "control_plane:",
        "  schema_version: 1",
        "  repository:",
        '    remote: ""',
        "  sync_policy:",
        "    mode: manual",
        "source_repositories:",
    ]
    for repository in repositories:
        remote = canonical_remote(repository.get("remote"))
        default_branch = str(repository.get("expected_branch") or "main")
        lines.extend(
            ([
                f"  - id: {_quote(repository.get('id'))}",
                "    role: source",
                "    remote:",
                f"      canonical: {_quote(remote)}",
                "      aliases: []",
                f"    default_branch: {_quote(default_branch)}",
            ] if bool(repository.get("git_repository")) else [
                f"  - id: {_quote(repository.get('id'))}",
                "    role: source",
                "    locator:",
                "      type: manual",
                f"      value: {_quote(repository.get('origin_id') or repository.get('id'))}",
                "    default_branch: manual",
            ]) + ([
                "    workspace_binding:",
                "      type: root",
            ] if mode == "single-repository" else [
                "    workspace_binding:",
                "      type: member",
                f"      name: {_quote(repository.get('workspace_binding_name'))}",
            ]) + [
                "    materialization:",
                "      required: true",
                "    operation_policy: inherit",
            ]
        )
    lines.append(f"prefer_subagent: {str(_parse_bool(_yaml_scalar(v3_text, 'prefer_subagent'))).lower()}")
    lines.append(_agents_contract_block())
    lines.extend(_portable_unknown_blocks(v3_text))
    return "\n".join(lines).rstrip() + "\n", workspace_id, repositories


def _proposal(
    workspace_root: Path, text: str, remote_overrides: dict[str, str] | None = None
) -> dict[str, object]:
    rendered, workspace_id, repositories = _render_v4(workspace_root, text, remote_overrides)
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    digest.update(b"\0")
    digest.update(rendered.encode("utf-8"))
    return {
        "proposal_id": "cp4-" + digest.hexdigest()[:24],
        "workspace_id": workspace_id,
        "rendered": rendered,
        "repositories": repositories,
        "portable_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


def _atomic_write(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if read(path) == text:
        return False
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def _atomic_publish(payloads: dict[Path, str]) -> list[str]:
    before = {path: path.read_bytes() if path.is_file() else None for path in payloads}
    changed: list[str] = []
    try:
        for path, text in payloads.items():
            if _atomic_write(path, text):
                changed.append(str(path))
    except (OSError, ControlPlaneError):
        for path, value in before.items():
            if value is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
        raise ControlPlaneError("WB_CONTROL_PLANE_TRANSACTION_FAILED")
    return changed


def _protected_tracked_paths(workspace_root: Path) -> list[str]:
    control = (workspace_root / ".work-bundle").resolve()
    top_raw = _git(control, "rev-parse", "--show-toplevel")
    if not top_raw:
        return []
    top = Path(top_raw).resolve()
    tracked = _git(top, "ls-files").splitlines()
    protected: list[str] = []
    for tracked_path in tracked:
        relative = tracked_path
        if top != control:
            prefix = ".work-bundle/"
            if not relative.startswith(prefix):
                continue
            relative = relative[len(prefix) :]
        name = Path(relative).name
        if (
            relative == "git" or relative.startswith("git/")
            or relative == "runtime" or relative.startswith("runtime/")
            or relative == "orchestration/execution-state" or relative.startswith("orchestration/execution-state/")
            or relative == "credentials" or relative.startswith("credentials/")
            or name.endswith((".secret", ".key", ".pem", ".log"))
            or name == ".env" or name.startswith(".env.")
        ):
            protected.append(relative)
    return sorted(set(protected))


def _source_tracks_control_plane(workspace_root: Path) -> bool:
    top = _git(workspace_root, "rev-parse", "--show-toplevel")
    return bool(top and Path(top).resolve() == workspace_root and _git(workspace_root, "ls-files", ".work-bundle"))


def _source_exclude_payload(workspace_root: Path) -> tuple[Path, str] | None:
    if not (workspace_root / ".git").exists():
        return None
    ignored = subprocess.run(
        ["git", "-C", str(workspace_root), "check-ignore", "-q", "--no-index", ".work-bundle/project.yaml"],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0
    if ignored:
        return None
    path = workspace_root / ".git/info/exclude"
    current = read(path)
    rendered = current
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"
    rendered += ".work-bundle/\n"
    return path, rendered


def _binding_block_bounds(lines: list[str]) -> tuple[int, int] | None:
    try:
        start = next(i for i, line in enumerate(lines) if line == "device_bindings:")
    except StopIteration:
        return None
    end = start + 1
    while end < len(lines) and (not lines[end] or lines[end].startswith(" ")):
        end += 1
    return start, end


def _parse_bindings(text: str) -> dict[str, dict[str, object]]:
    lines = text.splitlines()
    bounds = _binding_block_bounds(lines)
    if not bounds:
        return {}
    start, end = bounds
    document = _load_yaml("\n".join(lines[start:end]) + "\n")
    if not isinstance(document, dict) or not isinstance(document.get("device_bindings"), dict):
        return {}
    result: dict[str, dict[str, object]] = {}
    for key, value in document["device_bindings"].items():
        if isinstance(value, dict):
            result[str(key)] = value
    return result


def _render_nested(lines: list[str], indent: int, key: str, value: object) -> None:
    prefix = " " * indent
    if isinstance(value, dict):
        lines.append(f"{prefix}{key}:")
        for nested_key, nested_value in value.items():
            _render_nested(lines, indent + 2, str(nested_key), nested_value)
    elif isinstance(value, list):
        if not value:
            lines.append(f"{prefix}{key}: []")
        elif all(not isinstance(item, (dict, list)) for item in value):
            lines.append(f"{prefix}{key}: [{', '.join(_quote(item) for item in value)}]")
        else:
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{prefix}  -")
                    for nested_key, nested_value in item.items():
                        _render_nested(lines, indent + 4, str(nested_key), nested_value)
    elif isinstance(value, bool):
        lines.append(f"{prefix}{key}: {str(value).lower()}")
    elif value is None:
        lines.append(f"{prefix}{key}: null")
    else:
        lines.append(f"{prefix}{key}: {_quote(value)}")


def _render_bindings(bindings: dict[str, dict[str, object]]) -> str:
    lines = ["device_bindings:"]
    for workspace_id in sorted(bindings):
        binding = bindings[workspace_id]
        lines.extend(
            [
                f"  {_quote(workspace_id)}:",
                f"    slug: {_quote(binding.get('slug'))}",
                f"    workspace_root: {_quote(binding.get('workspace_root'))}",
                f"    control_plane_path: {_quote(binding.get('control_plane_path'))}",
                f"    control_plane_remote: {_quote(binding.get('control_plane_remote'))}",
                f"    observed_control_plane_head: {_quote(binding.get('observed_control_plane_head'))}",
            ]
        )
        known_binding_fields = {
            "slug", "workspace_root", "control_plane_path", "control_plane_remote",
            "observed_control_plane_head", "repositories",
        }
        for key in sorted(set(binding) - known_binding_fields):
            value = binding.get(key)
            _render_nested(lines, 4, key, value)
        lines.append("    repositories:")
        repositories = binding.get("repositories")
        if isinstance(repositories, dict):
            for repository_id in sorted(repositories):
                repository = repositories[repository_id]
                if not isinstance(repository, dict):
                    continue
                lines.extend(
                    [
                        f"      {_quote(repository_id)}:",
                        f"        project_root: {_quote(repository.get('project_root'))}",
                        f"        checkout_kind: {_quote(repository.get('checkout_kind'))}",
                        f"        observed_branch: {_quote(repository.get('observed_branch'))}",
                        f"        observed_head: {_quote(repository.get('observed_head'))}",
                        f"        observed_at: {_quote(repository.get('observed_at'))}",
                    ]
                )
                known_repository_fields = {
                    "project_root", "checkout_kind", "observed_branch", "observed_head",
                    "observed_at", "git_common_dir",
                }
                for key in sorted(set(repository) - known_repository_fields):
                    value = repository.get(key)
                    _render_nested(lines, 8, key, value)
                lines.append(f"        git_common_dir: {_quote(repository.get('git_common_dir'))}")
    return "\n".join(lines) + "\n"


def _write_bindings(bindings: dict[str, dict[str, object]]) -> Path:
    registry = resolve_project_registry_path()
    _atomic_write(registry, _bindings_document(bindings, read(registry) or "projects: []\n"))
    return registry


def _bindings_document(bindings: dict[str, dict[str, object]], original: str) -> str:
    lines = original.splitlines()
    bounds = _binding_block_bounds(lines)
    replacement = _render_bindings(bindings).splitlines()
    if bounds:
        start, end = bounds
        lines = lines[:start] + replacement + lines[end:]
    else:
        if lines and lines[-1]:
            lines.append("")
        lines.extend(replacement)
    return "\n".join(lines).rstrip() + "\n"


def _registry_bindings() -> dict[str, dict[str, object]]:
    return _parse_bindings(read(resolve_project_registry_path()))


def _binding_from_v3(
    workspace_root: Path, workspace_id: str, slug: str, repositories: list[dict[str, object]]
) -> dict[str, object]:
    local: dict[str, dict[str, object]] = {}
    for repository in repositories:
        path = Path(str(repository.get("project_root") or "")).expanduser().resolve()
        local[str(repository.get("id") or "")] = {
            "project_root": str(path),
            "checkout_kind": str(repository.get("checkout_kind") or "external"),
            "observed_branch": _git(path, "branch", "--show-current"),
            "observed_head": _git(path, "rev-parse", "HEAD"),
            "observed_at": utc_now_rfc3339(),
            "git_common_dir": _git(path, "rev-parse", "--git-common-dir"),
        }
    control = workspace_root / ".work-bundle"
    return {
        "slug": slug,
        "workspace_root": str(workspace_root),
        "control_plane_path": str(control),
        "control_plane_remote": _git_remote(control),
        "observed_control_plane_head": _git(control, "rev-parse", "HEAD"),
        "repositories": local,
    }


def _portable_failures(text: str) -> list[str]:
    failures: list[str] = []
    if _yaml_scalar(text, "metadata_version") != VERSION:
        failures.append("WB_CONTROL_PLANE_METADATA_VERSION_INVALID")
    workspace_id = _workspace_id(text)
    if not workspace_id.startswith("wb-"):
        failures.append("WB_CONTROL_PLANE_WORKSPACE_ID_INVALID")
    if not _workspace_value(text, "slug"):
        failures.append("WB_CONTROL_PLANE_WORKSPACE_SLUG_MISSING")
    mode = _workspace_value(text, "mode")
    if mode not in {"single-repository", "multi-repository", "composite"}:
        failures.append("WB_CONTROL_PLANE_WORKSPACE_MODE_INVALID")
    control = _block(text, "control_plane")
    if not re.search(r"^\s{2}schema_version:\s*1\s*$", control, re.MULTILINE):
        failures.append("WB_CONTROL_PLANE_SCHEMA_VERSION_INVALID")
    if not re.search(r"^\s{4}mode:\s*manual\s*$", control, re.MULTILINE):
        failures.append("WB_CONTROL_PLANE_SYNC_POLICY_INVALID")
    forbidden = ("workspace_root", "project_root", "observed_head", "observation_time", "git_control_root")
    for key in forbidden:
        if re.search(rf"^\s*{key}:\s*", text, re.MULTILINE):
            failures.append(f"WB_CONTROL_PLANE_PORTABLE_FIELD_FORBIDDEN:{key}")
    try:
        repositories = _v4_repositories(text)
        configured_control_remote = _control_plane_remote(text)
        if configured_control_remote:
            validated_remote(configured_control_remote)
    except ControlPlaneError as exc:
        failures.append(exc.code)
        repositories = []
    if not repositories:
        failures.append("WB_CONTROL_PLANE_REPOSITORIES_MISSING")
    seen_ids: set[str] = set()
    seen_member_names: set[str] = set()
    seen_member_paths: set[str] = set()
    root_bindings = 0
    composite_member_bindings = 0
    for repository in repositories:
        repository_id = str(repository.get("id") or "")
        if not repository.get("id"):
            failures.append("WB_CONTROL_PLANE_REPOSITORY_ID_MISSING")
        elif repository_id in seen_ids:
            failures.append(f"WB_CONTROL_PLANE_REPOSITORY_ID_DUPLICATE:{repository_id}")
        seen_ids.add(repository_id)
        if not repository.get("canonical_remote") and repository.get("locator_type") != "manual":
            failures.append(f"WB_CONTROL_PLANE_REMOTE_REQUIRED:{repository.get('id', '')}")
        if not repository.get("default_branch"):
            failures.append(f"WB_CONTROL_PLANE_DEFAULT_BRANCH_MISSING:{repository_id}")
        if repository.get("materialization_raw") not in {"true", "false", True, False}:
            failures.append(f"WB_CONTROL_PLANE_MATERIALIZATION_INVALID:{repository_id}")
        binding_type = str(repository.get("workspace_binding_type") or "")
        if binding_type == "root":
            root_bindings += 1
            if mode not in {"single-repository", "composite"}:
                failures.append(f"WB_CONTROL_PLANE_ROOT_BINDING_MODE_INVALID:{repository_id}")
        elif binding_type == "member":
            member_name = str(repository.get("workspace_binding_name") or "")
            member_path = str(repository.get("workspace_binding_path") or "")
            if mode == "multi-repository":
                if not member_name:
                    failures.append(f"WB_CONTROL_PLANE_MEMBER_BINDING_INVALID:{repository_id}")
                elif member_name in seen_member_names:
                    failures.append(f"WB_CONTROL_PLANE_MEMBER_BINDING_DUPLICATE:{member_name}")
                seen_member_names.add(member_name)
            elif mode == "composite":
                valid_composite_member = True
                if not member_name:
                    failures.append(f"WB_CONTROL_PLANE_MEMBER_BINDING_INVALID:{repository_id}")
                    valid_composite_member = False
                elif member_name in seen_member_names:
                    failures.append(f"WB_CONTROL_PLANE_MEMBER_BINDING_DUPLICATE:{member_name}")
                    valid_composite_member = False
                seen_member_names.add(member_name)
                if not member_path:
                    failures.append(f"WB_CONTROL_PLANE_MEMBER_BINDING_INVALID:{repository_id}")
                    valid_composite_member = False
                else:
                    try:
                        _validate_member_path(member_path)
                    except ControlPlaneError as exc:
                        failures.append(f"{exc.code}:{repository_id}")
                        valid_composite_member = False
                    if member_path in seen_member_paths:
                        failures.append(f"WB_CONTROL_PLANE_MEMBER_PATH_DUPLICATE:{member_path}")
                        valid_composite_member = False
                    seen_member_paths.add(member_path)
                if valid_composite_member:
                    composite_member_bindings += 1
            else:
                failures.append(f"WB_CONTROL_PLANE_MEMBER_BINDING_INVALID:{repository_id}")
                if member_name:
                    seen_member_names.add(member_name)
        elif binding_type:
            failures.append(f"WB_CONTROL_PLANE_WORKSPACE_BINDING_INVALID:{repository_id}")
    if mode == "single-repository" and (len(repositories) != 1 or root_bindings != 1):
        failures.append("WB_CONTROL_PLANE_SINGLE_REPOSITORY_BINDING_INVALID")
    if mode == "composite" and root_bindings != 1:
        failures.append("WB_CONTROL_PLANE_COMPOSITE_ROOT_BINDING_INVALID")
    if mode == "composite" and composite_member_bindings == 0:
        failures.append("WB_CONTROL_PLANE_COMPOSITE_MEMBER_REQUIRED")
    return failures


def _render_new_v4(slug: str, repositories: list[dict[str, object]]) -> tuple[str, str]:
    return _render_new_v4_for_mode(slug, repositories, "multi-repository")


def _render_new_v4_for_mode(
    slug: str, repositories: list[dict[str, object]], mode: str
) -> tuple[str, str]:
    if mode == "single-repository" and len(repositories) != 1:
        raise ControlPlaneError("WB_CONTROL_PLANE_SINGLE_REPOSITORY_COUNT_INVALID")
    for repository in repositories:
        repository["workspace_binding_type"] = "root" if mode == "single-repository" else "member"
        repository["workspace_binding_name"] = "" if mode == "single-repository" else str(repository.get("id") or "")
    workspace_id = _derive_workspace_id(slug, repositories)
    lines = [
        "metadata_version: 4",
        "authority: canonical",
        "workspace:",
        f"  id: {_quote(workspace_id)}",
        f"  slug: {_quote(slug)}",
        f"  mode: {mode}",
        "control_plane:",
        "  schema_version: 1",
        "  repository:",
        '    remote: ""',
        "  sync_policy:",
        "    mode: manual",
        "source_repositories:",
    ]
    for repository in repositories:
        lines.extend([
            f"  - id: {_quote(repository.get('id'))}",
            "    role: source",
            "    remote:",
            f"      canonical: {_quote(canonical_remote(repository.get('remote')))}",
            "      aliases: []",
            "    default_branch: main",
            "    workspace_binding:",
            f"      type: {'root' if mode == 'single-repository' else 'member'}",
            *([] if mode == "single-repository" else [f"      name: {_quote(repository.get('id'))}"]),
            "    materialization:",
            f"      required: {str(bool(repository.get('required', True))).lower()}",
            "    operation_policy: inherit",
        ])
    lines.append("prefer_subagent: false")
    lines.append(_agents_contract_block())
    return "\n".join(lines) + "\n", workspace_id


def _parse_repository_specs(values: list[str], *, required: bool = True) -> list[dict[str, object]]:
    repositories: list[dict[str, object]] = []
    ids: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORY_SPEC_INVALID")
        repository_id, remote = value.split("=", 1)
        normalized = validated_remote(remote)
        if not repository_id or not normalized or repository_id in ids:
            raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORY_SPEC_INVALID")
        ids.add(repository_id)
        repositories.append({"id": repository_id, "remote": normalized, "required": required})
    return repositories


def cmd_init_workspace(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py init-workspace")
    parser.add_argument("workspace_root")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--mode", choices=["single-repository", "multi-repository"], default="multi-repository")
    parser.add_argument("--repository", action="append", default=[], metavar="ID=REMOTE")
    parser.add_argument("--optional-repository", action="append", default=[], metavar="ID=REMOTE")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parsed = parser.parse_args(args)
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    if parsed.mode == "multi-repository" and (workspace_root / ".git").exists():
        out({"command": "init-workspace", "status": "issues-found", "failure_code": "WB_CONTROL_PLANE_SINGLE_REPOSITORY_TOPOLOGY_UNRESOLVED", "changed_files": []})
        return 1
    metadata = workspace_root / ".work-bundle/project.yaml"
    if metadata.exists():
        out({"command": "init-workspace", "status": "issues-found", "failure_code": "WB_CONTROL_PLANE_ALREADY_INITIALIZED", "changed_files": []})
        return 1
    try:
        repositories = _parse_repository_specs(parsed.repository) + _parse_repository_specs(parsed.optional_repository, required=False)
        if not repositories or len({str(item["id"]) for item in repositories}) != len(repositories):
            raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORIES_MISSING" if not repositories else "WB_CONTROL_PLANE_REPOSITORY_SPEC_INVALID")
        rendered, workspace_id = _render_new_v4_for_mode(parsed.slug, repositories, parsed.mode)
        if parsed.mode == "single-repository" and (workspace_root / ".git").exists():
            actual_remote = _git_remote(workspace_root)
            if actual_remote != canonical_remote(repositories[0].get("remote")):
                raise ControlPlaneError("WB_CONTROL_PLANE_REMOTE_CONFLICT", {"repository_id": repositories[0].get("id")})
        gitignore_text = _merged_local_only_gitignore(read(workspace_root / ".work-bundle/.gitignore"))
    except ControlPlaneError as exc:
        out({"command": "init-workspace", "status": "issues-found", "failure_code": exc.code, "changed_files": []})
        return 1
    if parsed.dry_run:
        out({"command": "init-workspace", "status": "passed", "dry_run": True, "workspace_id": workspace_id, "changed_files": []})
        return 0
    bindings = _registry_bindings()
    control = workspace_root / ".work-bundle"
    bindings[workspace_id] = {
        "slug": parsed.slug,
        "workspace_root": str(workspace_root),
        "control_plane_path": str(control),
        "control_plane_remote": "",
        "observed_control_plane_head": "",
        "repositories": {},
    }
    registry = resolve_project_registry_path()
    changed = _atomic_publish({
        metadata: rendered,
        control / ".gitignore": gitignore_text,
        registry: _bindings_document(bindings, read(registry) or "projects: []\n"),
    })
    for relative in ("knowledge/notes", "knowledge/open-questions", "knowledge/context-packs", "knowledge/indexes", "orchestration/spec/active", "orchestration/plan/active", "orchestration/handoff", "orchestration/docs", "orchestration/principles", "rules", "git", "runtime", "orchestration/execution-state"):
        path = control / relative
        if not path.exists():
            path.mkdir(parents=True)
            changed.append(str(path))
    changed.extend(ensure_workspace_resources(workspace_root))
    changed.extend(_sync_agents(workspace_root))
    if parsed.mode == "single-repository" and (workspace_root / ".git").exists():
        if _ensure_source_local_excludes(workspace_root):
            changed.append(str(workspace_root / ".git/info/exclude"))
    out({"command": "init-workspace", "status": "passed", "dry_run": False, "workspace_id": workspace_id, "changed_files": sorted(set(changed))})
    return 0


def _set_control_plane_remote(text: str, remote: str) -> str:
    lines = text.splitlines()
    in_control = False
    in_repository = False
    for index, line in enumerate(lines):
        if line == "control_plane:":
            in_control = True
            continue
        if in_control and line and not line.startswith(" "):
            break
        if in_control and line == "  repository:":
            in_repository = True
            continue
        if in_repository and line.startswith("    remote:"):
            lines[index] = f"    remote: {_quote(remote)}"
            return "\n".join(lines) + "\n"
    raise ControlPlaneError("WB_CONTROL_PLANE_METADATA_INVALID")


def _run_git_checked(path: Path, *args: str) -> None:
    result = subprocess.run(["git", "-C", str(path), *args], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ControlPlaneError("WB_CONTROL_PLANE_GIT_OPERATION_FAILED", {"git_operation": args[0] if args else "unknown"})


def _publish_evidence(control: Path, payload: dict[str, object]) -> Path:
    stamp = utc_now_rfc3339().replace(":", "").replace("-", "")
    path = control / "runtime/publish" / f"publish-{stamp}.json"
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return path


def cmd_publish_control_plane(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py publish-control-plane")
    parser.add_argument("workspace_root")
    parser.add_argument("--remote", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parsed = parser.parse_args(args)
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    control = workspace_root / ".work-bundle"
    metadata = control / "project.yaml"
    text = read(metadata)
    failures = _portable_failures(text)
    protected = _protected_tracked_paths(workspace_root)
    if failures or protected:
        code = failures[0] if failures else "WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED"
        out({"command": "publish-control-plane", "status": "issues-found", "failure_code": code, "protected_paths": protected, "changed_files": []})
        return 1
    try:
        remote = validated_remote(parsed.remote)
    except ControlPlaneError as exc:
        out({"command": "publish-control-plane", "status": "issues-found", "failure_code": exc.code, "changed_files": []})
        return 1
    if not remote:
        out({"command": "publish-control-plane", "status": "issues-found", "failure_code": "WB_CONTROL_PLANE_REMOTE_REQUIRED", "changed_files": []})
        return 1
    if parsed.dry_run:
        out({"command": "publish-control-plane", "status": "passed", "dry_run": True, "remote": remote, "changed_files": [], "git_actions": ["init", "configure-origin", "commit", "push"]})
        return 0
    metadata_before = text
    git_existed = (control / ".git").exists()
    snapshot_failures: list[str] = []
    previous_origin = ""
    previous_head = ""
    previous_status = ""
    previous_staged = ""
    config_locator = ""
    if git_existed:
        snapshot_commands = {
            "head": ("rev-parse", "--verify", "HEAD"),
            "status": ("status", "--porcelain=v1", "--untracked-files=all"),
            "index": ("diff", "--cached", "--name-status"),
            "config": ("rev-parse", "--git-path", "config"),
            "remotes": ("remote",),
        }
        snapshots: dict[str, subprocess.CompletedProcess[str]] = {
            name: subprocess.run(
                ["git", "-C", str(control), *command],
                check=False,
                capture_output=True,
                text=True,
            )
            for name, command in snapshot_commands.items()
        }
        snapshot_failures.extend(
            f"{name}_snapshot_failed"
            for name, result in snapshots.items()
            if result.returncode != 0
        )
        previous_head = snapshots["head"].stdout.strip() if snapshots["head"].returncode == 0 else ""
        previous_status = snapshots["status"].stdout.strip() if snapshots["status"].returncode == 0 else ""
        previous_staged = snapshots["index"].stdout.strip() if snapshots["index"].returncode == 0 else ""
        config_locator = snapshots["config"].stdout.strip() if snapshots["config"].returncode == 0 else ""
        remotes = snapshots["remotes"].stdout.splitlines() if snapshots["remotes"].returncode == 0 else []
        if "origin" in remotes:
            origin_result = subprocess.run(
                ["git", "-C", str(control), "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
                text=True,
            )
            if origin_result.returncode != 0:
                snapshot_failures.append("origin_snapshot_failed")
            else:
                previous_origin = origin_result.stdout.strip()
    config_path = Path(config_locator)
    if config_locator and not config_path.is_absolute():
        config_path = control / config_path
    config_before = config_path.read_bytes() if git_existed and config_path.is_file() else None
    evidence_base = {
        "operation": "publish-control-plane",
        "workspace_id": _workspace_id(text),
        "previous_head": previous_head,
        "previous_origin_configured": bool(previous_origin),
        "remote": remote,
    }
    if git_existed and (
        snapshot_failures or not previous_head or previous_status or previous_staged or config_before is None
    ):
        evidence = _publish_evidence(
            control,
            {
                **evidence_base,
                "state": "recovery-required",
                "failure_code": "WB_CONTROL_PLANE_PUBLISH_RECOVERY_REQUIRED",
                "snapshot_failures": snapshot_failures,
                "recovery_required": True,
            },
        )
        out({
            "command": "publish-control-plane",
            "status": "issues-found",
            "failure_code": "WB_CONTROL_PLANE_PUBLISH_RECOVERY_REQUIRED",
            "transaction_evidence": str(evidence),
        })
        return 1
    try:
        probe = subprocess.run(["git", "ls-remote", "--", remote], check=False, capture_output=True, text=True)
        if probe.returncode != 0:
            raise ControlPlaneError("WB_CONTROL_PLANE_REMOTE_UNREACHABLE")
        _atomic_write(metadata, _set_control_plane_remote(text, remote))
        if not (control / ".git").exists():
            _run_git_checked(control, "init", "-q", "-b", "main")
        existing = _git(control, "remote", "get-url", "origin")
        _run_git_checked(control, "remote", "set-url" if existing else "add", "origin", remote)
        _run_git_checked(control, "add", ".")
        protected = _protected_tracked_paths(workspace_root)
        if protected:
            raise ControlPlaneError("WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED", {"protected_paths": protected})
        if _git(control, "diff", "--cached", "--name-only"):
            if not _git(control, "config", "user.name"):
                _run_git_checked(control, "config", "user.name", "WorkBundle")
            if not _git(control, "config", "user.email"):
                _run_git_checked(control, "config", "user.email", "work-bundle@local.invalid")
            _run_git_checked(control, "commit", "-q", "-m", "chore: publish WorkBundle control plane")
        _run_git_checked(control, "push", "-q", "-u", "origin", "HEAD:main")
    except ControlPlaneError as exc:
        rollback_failures: list[str] = []
        if not git_existed and (control / ".git").is_dir():
            _atomic_write(metadata, metadata_before)
            shutil.rmtree(control / ".git")
        elif git_existed:
            reset = subprocess.run(
                ["git", "-C", str(control), "reset", "--hard", previous_head],
                check=False,
                capture_output=True,
                text=True,
            )
            if reset.returncode != 0:
                rollback_failures.append("head_reset_failed")
            if config_before is not None:
                config_path.write_bytes(config_before)
            if metadata.read_text(encoding="utf-8") != metadata_before:
                _atomic_write(metadata, metadata_before)
            if _git(control, "rev-parse", "HEAD") != previous_head:
                rollback_failures.append("head_mismatch")
            if metadata.read_text(encoding="utf-8") != metadata_before:
                rollback_failures.append("metadata_mismatch")
            if _git(control, "remote", "get-url", "origin") != previous_origin:
                rollback_failures.append("origin_mismatch")
            if _git(control, "status", "--porcelain=v1", "--untracked-files=all") != previous_status:
                rollback_failures.append("worktree_mismatch")
            if _git(control, "diff", "--cached", "--name-status") != previous_staged:
                rollback_failures.append("index_mismatch")
        recovery_required = bool(rollback_failures)
        failure_code = "WB_CONTROL_PLANE_PUBLISH_RECOVERY_REQUIRED" if recovery_required else exc.code
        evidence = _publish_evidence(control, {
            **evidence_base,
            "state": "recovery-required" if recovery_required else "rolled-back",
            "failure_code": failure_code,
            "original_failure_code": exc.code,
            "rollback_failures": rollback_failures,
            "recovery_required": recovery_required,
        })
        out({"command": "publish-control-plane", "status": "issues-found", "failure_code": failure_code, "transaction_evidence": str(evidence), **exc.details})
        return 1
    evidence = _publish_evidence(control, {**evidence_base, "state": "published", "control_plane_head": _git(control, "rev-parse", "HEAD"), "recovery_required": False})
    out({"command": "publish-control-plane", "status": "passed", "dry_run": False, "remote": remote, "control_plane_head": _git(control, "rev-parse", "HEAD"), "transaction_evidence": str(evidence), "git_actions": ["init", "configure-origin", "commit", "push"]})
    return 0


def apply_layout_v3_to_v4(
    workspace_root: Path,
    remote_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    """Upgrade metadata v3 to portable v4, publishing device bindings atomically with metadata."""
    workspace_root = workspace_root.expanduser().resolve()
    metadata_path = workspace_root / ".work-bundle/project.yaml"
    before = read(metadata_path)
    protected = _protected_tracked_paths(workspace_root)
    if protected:
        raise ControlPlaneError("WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED", {"protected_paths": protected})
    if _source_tracks_control_plane(workspace_root):
        raise ControlPlaneError("WB_CONTROL_PLANE_SOURCE_TRACKS_CONTROL_PLANE")
    proposal = _proposal(workspace_root, before, remote_overrides)
    gitignore_text = _merged_local_only_gitignore(read(workspace_root / ".work-bundle/.gitignore"))
    backup = workspace_root / ".work-bundle/runtime/migrations" / str(proposal["proposal_id"]) / "project-v3.yaml"
    gitignore = workspace_root / ".work-bundle/.gitignore"
    bindings = _registry_bindings()
    workspace_id = str(proposal["workspace_id"])
    repositories = proposal["repositories"]
    assert isinstance(repositories, list)
    bindings[workspace_id] = _binding_from_v3(
        workspace_root, workspace_id, _workspace_slug(workspace_root, before), repositories
    )
    registry = resolve_project_registry_path()
    registry_text = _bindings_document(bindings, read(registry) or "projects: []\n")
    payloads = {
        backup: before,
        metadata_path: str(proposal["rendered"]),
        gitignore: gitignore_text,
        registry: registry_text,
    }
    source_exclusion = _source_exclude_payload(workspace_root)
    if source_exclusion is not None:
        payloads[source_exclusion[0]] = source_exclusion[1]
    changed_files = _atomic_publish(payloads)
    return {
        "status": "passed",
        "from_version": _yaml_scalar(before, "metadata_version"),
        "to_version": VERSION,
        "changed_files": changed_files,
        "failures": [],
        "workspace_id": workspace_id,
        "proposal_id": proposal["proposal_id"],
    }


def cmd_migrate_control_plane(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py migrate-control-plane")
    parser.add_argument("workspace_root")
    parser.add_argument("--accepted-proposal-id")
    parser.add_argument("--repository-remote", action="append", default=[], metavar="ID=REMOTE")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parsed = parser.parse_args(args)
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    metadata_path = workspace_root / ".work-bundle/project.yaml"
    before = read(metadata_path)
    try:
        remote_overrides = {
            str(item["id"]): str(item["remote"])
            for item in _parse_repository_specs(parsed.repository_remote)
        }
    except ControlPlaneError as exc:
        out({"command": "migrate-control-plane", "status": "issues-found", "failure_code": exc.code})
        return 1
    protected = _protected_tracked_paths(workspace_root)
    if protected:
        out({
            "command": "migrate-control-plane", "status": "issues-found",
            "failure_code": "WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED",
            "protected_paths": protected, "changed_files": [],
        })
        return 1
    if _source_tracks_control_plane(workspace_root):
        out({
            "command": "migrate-control-plane", "status": "issues-found",
            "failure_code": "WB_CONTROL_PLANE_SOURCE_TRACKS_CONTROL_PLANE", "changed_files": [],
        })
        return 1
    try:
        proposal = _proposal(workspace_root, before, remote_overrides)
    except ControlPlaneError as exc:
        out({"command": "migrate-control-plane", "status": "issues-found", "failure_code": exc.code, **exc.details})
        return 1
    base = {
        "command": "migrate-control-plane",
        "workspace_root": str(workspace_root),
        "migration": {
            "from_version": _yaml_scalar(before, "metadata_version"),
            "to_version": 4,
            "proposal_id": proposal["proposal_id"],
            "portable_sha256": proposal["portable_sha256"],
        },
        "proposal": {
            "topology": _yaml_scalar(before, "workspace_mode") or "single-repository",
            "portable_fields_to_retain": ["workspace identity", "source repository ids", "canonical remotes", "portable policy", "knowledge", "orchestration"],
            "local_fields_to_move": ["workspace_root", "project_root", "observed_head", "observation_time", "git_control_root", "codegraph observation"],
            "unresolved_fields": [],
            "repositories": [
                {"id": item.get("id"), "canonical_remote": canonical_remote(item.get("remote"))}
                for item in proposal["repositories"] if isinstance(item, dict)
            ],
            "portable_paths": ["project.yaml", "knowledge/", "orchestration/spec/", "orchestration/plan/", "orchestration/handoff/", "orchestration/docs/", "rules/"],
            "local_only_paths": ["git/", "runtime/", "orchestration/execution-state/"],
            "control_plane_git": {
                "currently_initialized": (
                    Path(_git(workspace_root / ".work-bundle", "rev-parse", "--show-toplevel")).resolve()
                    == (workspace_root / ".work-bundle").resolve()
                    if _git(workspace_root / ".work-bundle", "rev-parse", "--show-toplevel")
                    else False
                ),
                "apply_initializes_git": False,
            },
        },
    }
    if parsed.dry_run:
        out({**base, "status": "passed", "dry_run": True, "changed_files": []})
        return 0
    if parsed.accepted_proposal_id != proposal["proposal_id"]:
        out({**base, "status": "issues-found", "failure_code": "WB_CONTROL_PLANE_PROPOSAL_STALE", "changed_files": []})
        return 1
    try:
        applied = apply_layout_v3_to_v4(workspace_root, remote_overrides)
    except ControlPlaneError as exc:
        out({**base, "status": "issues-found", "failure_code": exc.code, "changed_files": [], **exc.details})
        return 1
    out(
        {
            **base,
            "status": "passed",
            "dry_run": False,
            "workspace_id": applied["workspace_id"],
            "changed_files": applied["changed_files"],
            "local_binding_path": str(resolve_project_registry_path()),
        }
    )
    return 0


def _parse_repository_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORY_PATH_INVALID")
        repository_id, raw_path = value.split("=", 1)
        if not repository_id or not raw_path:
            raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORY_PATH_INVALID")
        result[repository_id] = Path(raw_path).expanduser().resolve()
    return result


def _materialize(remote: str, path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ControlPlaneError("WB_CONTROL_PLANE_MATERIALIZATION_PATH_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "clone", "--", remote, str(path)], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)
        raise ControlPlaneError("WB_CONTROL_PLANE_MATERIALIZATION_FAILED")


def _tree_entries_without_control_plane(path: Path) -> set[str]:
    if not path.exists():
        return set()
    entries: set[str] = set()
    for candidate in path.rglob("*"):
        relative = candidate.relative_to(path)
        if relative.parts and relative.parts[0] in {".git", ".work-bundle"}:
            continue
        entries.add(relative.as_posix())
    return entries


NESTED_MEMBER_EXCLUDE_MARKER = "# work-bundle:nested-member:"


def _validate_member_path(raw: str) -> str:
    path = str(raw or "").strip()
    if path == ".work-bundle" or path.startswith(".work-bundle/"):
        raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_PATH_OVERLAPS_CONTROL_PLANE")
    candidate = Path(path)
    if (
        not path
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or candidate.parts[0] in {".", ".."}
        or "/" in path
        or "\\" in path
    ):
        raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_PATH_INVALID")
    return path


def _root_index_tracks(workspace_root: Path, relative: str) -> bool:
    if not (workspace_root / ".git").exists() or not relative:
        return False
    tracked = _git(workspace_root, "ls-files", "--", relative, f"{relative.rstrip('/')}/")
    return bool(tracked.strip())


def _metadata_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _composite_members(text: str) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    for repository in _v4_repositories(text):
        if str(repository.get("workspace_binding_type") or "") != "member":
            continue
        name = str(repository.get("workspace_binding_name") or repository.get("id") or "")
        path = str(repository.get("workspace_binding_path") or name)
        if name and path:
            members.append((name, path))
    return members


def _exclude_text_with_source_and_members(
    current: str, members: Iterable[tuple[str, str]]
) -> str:
    existing = {line.strip() for line in current.splitlines()}
    additions: list[str] = []
    for pattern in (".work-bundle/", "credentials/"):
        if pattern not in existing:
            additions.append(pattern)
            existing.add(pattern)
    for name, path in members:
        pattern = f"{path.rstrip('/')}/"
        marker = f"{NESTED_MEMBER_EXCLUDE_MARKER}{name}"
        if pattern in existing:
            continue
        if marker not in existing:
            additions.append(marker)
        additions.append(pattern)
        existing.add(marker)
        existing.add(pattern)
    if not additions:
        return current if not current or current.endswith("\n") else current + "\n"
    rendered = current
    if rendered and not rendered.endswith("\n"):
        rendered += "\n"
    return rendered + "\n".join(additions) + "\n"


def _ensure_source_local_excludes(
    workspace_root: Path, members: Iterable[tuple[str, str]] = ()
) -> bool:
    exclude = workspace_root / ".git/info/exclude"
    current = read(exclude)
    rendered = _exclude_text_with_source_and_members(current, members)
    if rendered == current:
        return False
    return _atomic_write(exclude, rendered)


def _member_segment(repository: dict[str, object], binding_name: str) -> str:
    return str(repository.get("workspace_binding_path") or binding_name)


def _classify_workspace_member(
    repositories: list[dict[str, object]], member: dict[str, str]
) -> str:
    for repository in repositories:
        repository_id = str(repository.get("id") or "")
        binding_type = str(repository.get("workspace_binding_type") or "")
        name = str(repository.get("workspace_binding_name") or "")
        path = str(repository.get("workspace_binding_path") or "")
        remote = str(repository.get("canonical_remote") or "")
        branch = str(repository.get("default_branch") or "")
        same_id = repository_id == member["repository_id"]
        same_name = bool(name) and name == member["name"]
        same_path = bool(path) and path == member["path"]
        if not same_id and not (binding_type == "member" and (same_name or same_path)):
            continue
        if (
            same_id
            and same_name
            and same_path
            and remote == member["remote"]
            and branch == member["default_branch"]
        ):
            return "match"
        return "collision"
    return "absent"


def _render_member_metadata_block(member: dict[str, str]) -> str:
    return "\n".join(
        [
            f"  - id: {_quote(member['repository_id'])}",
            "    role: source",
            "    remote:",
            f"      canonical: {_quote(member['remote'])}",
            "      aliases: []",
            f"    default_branch: {_quote(member['default_branch'])}",
            "    workspace_binding:",
            "      type: member",
            f"      name: {_quote(member['name'])}",
            f"      path: {_quote(member['path'])}",
            "    materialization:",
            "      required: true",
            "    operation_policy: inherit",
        ]
    ) + "\n"


def _append_member_metadata(text: str, member: dict[str, str]) -> str:
    if _workspace_value(text, "mode") == "single-repository":
        text = re.sub(r"^(\s{2}mode: )single-repository\s*$", r"\1composite", text, count=1, flags=re.MULTILINE)
    block = _render_member_metadata_block(member)
    if "prefer_subagent:" in text:
        return text.replace("prefer_subagent:", block + "prefer_subagent:", 1)
    return text.rstrip() + "\n" + block


def _require_observed_branch(path: Path, expected: str, repository_id: str) -> str:
    actual = _git(path, "branch", "--show-current")
    if actual != expected:
        raise ControlPlaneError(f"WB_CONTROL_PLANE_BRANCH_MISMATCH:{repository_id}")
    return actual


def _add_workspace_member_preflight(workspace_root: Path, text: str) -> dict[str, object]:
    workspace_id = _workspace_id(text)
    binding = _registry_bindings().get(workspace_id)
    if not isinstance(binding, dict):
        raise ControlPlaneError("WB_CONTROL_PLANE_BINDING_MISSING")
    bound_root = str(binding.get("workspace_root") or "")
    if not bound_root or Path(bound_root).expanduser().resolve() != workspace_root:
        raise ControlPlaneError("WB_CONTROL_PLANE_BINDING_ROOT_MISMATCH")
    root = next(
        (item for item in _v4_repositories(text) if str(item.get("workspace_binding_type") or "") == "root"),
        None,
    )
    if root is None:
        raise ControlPlaneError("WB_CONTROL_PLANE_COMPOSITE_ROOT_BINDING_INVALID")
    root_id = str(root.get("id") or "")
    repositories = binding.get("repositories")
    local = repositories.get(root_id) if isinstance(repositories, dict) else None
    if not isinstance(local, dict) or not local.get("project_root"):
        raise ControlPlaneError(f"WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:{root_id}")
    project_root = Path(str(local["project_root"])).expanduser().resolve()
    if project_root != workspace_root:
        raise ControlPlaneError(
            "WB_CONTROL_PLANE_ROOT_BINDING_PATH_MISMATCH",
            {"repository_id": root_id},
        )
    if (
        not project_root.is_dir()
        or not (project_root / ".git").exists()
        or not _git(project_root, "rev-parse", "--git-common-dir")
    ):
        raise ControlPlaneError(f"WB_CONTROL_PLANE_BOUND_GIT_INVALID:{root_id}")
    actual_remote = _resolved_git_remote(project_root)
    expected_remote = str(root.get("canonical_remote") or "")
    if actual_remote != expected_remote:
        raise ControlPlaneError(f"WB_CONTROL_PLANE_BOUND_REMOTE_CONFLICT:{root_id}")
    _require_observed_branch(project_root, str(root.get("default_branch") or ""), root_id)
    return binding


def _require_add_workspace_member_request(member: dict[str, str]) -> None:
    if not member["remote"]:
        raise ControlPlaneError(f"WB_CONTROL_PLANE_REMOTE_REQUIRED:{member['repository_id']}")
    if not member["default_branch"]:
        raise ControlPlaneError(f"WB_CONTROL_PLANE_DEFAULT_BRANCH_MISSING:{member['repository_id']}")


def _require_add_workspace_member_target(text: str, member: dict[str, str], classification: str) -> None:
    _require_add_workspace_member_request(member)
    rendered = text if classification == "match" else _append_member_metadata(text, member)
    failures = _portable_failures(rendered)
    if failures:
        raise ControlPlaneError(failures[0])


def _require_add_workspace_member_replay_state(
    workspace_root: Path, member: dict[str, str], binding: dict[str, object]
) -> None:
    member_path = (workspace_root / member["path"]).resolve()
    if not member_path.is_dir() or not (member_path / ".git").exists():
        raise ControlPlaneError(f"WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:{member['repository_id']}")
    actual_remote = _resolved_git_remote(member_path)
    if actual_remote != member["remote"]:
        raise ControlPlaneError(f"WB_CONTROL_PLANE_BOUND_REMOTE_CONFLICT:{member['repository_id']}")
    _require_observed_branch(member_path, member["default_branch"], member["repository_id"])
    repositories = binding.get("repositories")
    local = repositories.get(member["repository_id"]) if isinstance(repositories, dict) else None
    if not isinstance(local, dict) or not local.get("project_root"):
        raise ControlPlaneError(f"WB_CONTROL_PLANE_MEMBER_DEVICE_BINDING_MISSING:{member['repository_id']}")
    bound_path = Path(str(local["project_root"])).expanduser().resolve()
    if bound_path != member_path or str(local.get("checkout_kind") or "") != "nested-member":
        raise ControlPlaneError(f"WB_CONTROL_PLANE_MEMBER_DEVICE_BINDING_MISMATCH:{member['repository_id']}")
    exclude_lines = {line.strip() for line in read(workspace_root / ".git/info/exclude").splitlines()}
    if f"{member['path'].rstrip('/')}/" not in exclude_lines:
        raise ControlPlaneError(f"WB_CONTROL_PLANE_MEMBER_EXCLUDE_MISSING:{member['path']}")


def _inspect_existing_member_checkout(member_path: Path, member: dict[str, str]) -> None:
    if not member_path.is_dir():
        raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_COLLISION")
    actual_remote = _resolved_git_remote(member_path)
    if actual_remote != member["remote"]:
        raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_COLLISION")
    _require_observed_branch(member_path, member["default_branch"], member["repository_id"])


def _materialize_member_checkout(member_path: Path, member: dict[str, str]) -> None:
    _materialize(member["remote"], member_path)
    current_branch = _git(member_path, "branch", "--show-current")
    if current_branch != member["default_branch"]:
        try:
            _run_git_checked(member_path, "checkout", "-q", member["default_branch"])
        except ControlPlaneError:
            raise ControlPlaneError(f"WB_CONTROL_PLANE_BRANCH_MISMATCH:{member['repository_id']}")
    _require_observed_branch(member_path, member["default_branch"], member["repository_id"])


def _add_workspace_member_proposal(
    workspace_root: Path, text: str, member: dict[str, str]
) -> dict[str, object]:
    repositories = _v4_repositories(text)
    root = next(
        (item for item in repositories if str(item.get("workspace_binding_type") or "") == "root"),
        {},
    )
    facts = {
        "current_mode": _workspace_value(text, "mode"),
        "target_mode": "composite",
        "root": {
            "workspace_id": _workspace_id(text),
            "repository_id": str(root.get("id") or ""),
        },
        "member": dict(member),
        "exclude_patterns": [f"{member['path'].rstrip('/')}/"],
        "device_binding_delta": {
            "repository_id": member["repository_id"],
            "project_root": str(workspace_root / member["path"]),
            "checkout_kind": "nested-member",
        },
        "metadata_digest": _metadata_digest(text),
    }
    encoded = json.dumps(facts, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"proposal_id": "awm-" + hashlib.sha256(encoded).hexdigest()[:24], **facts}


def _rollback_workspace_root_materialization(workspace_root: Path, before: set[str]) -> None:
    after = _tree_entries_without_control_plane(workspace_root)
    for relative in sorted(after - before, key=lambda item: len(Path(item).parts), reverse=True):
        candidate = workspace_root / relative
        if candidate.is_symlink() or candidate.is_file():
            candidate.unlink(missing_ok=True)
        elif candidate.is_dir():
            try:
                candidate.rmdir()
            except OSError:
                pass
    if (workspace_root / ".git").is_dir():
        shutil.rmtree(workspace_root / ".git")


def _materialize_workspace_root(remote: str, workspace_root: Path, default_branch: str) -> set[str]:
    if (workspace_root / ".git").exists():
        raise ControlPlaneError("WB_CONTROL_PLANE_MATERIALIZATION_PATH_EXISTS")
    workspace_root.mkdir(parents=True, exist_ok=True)
    before = _tree_entries_without_control_plane(workspace_root)
    try:
        _run_git_checked(workspace_root, "init", "-q", "-b", default_branch)
        _ensure_source_local_excludes(workspace_root)
        _run_git_checked(workspace_root, "remote", "add", "origin", remote)
        _run_git_checked(
            workspace_root,
            "fetch",
            "--no-tags",
            "origin",
            f"refs/heads/{default_branch}:refs/remotes/origin/{default_branch}",
        )
        tree = set(
            _git(workspace_root, "ls-tree", "-r", "--name-only", f"origin/{default_branch}").splitlines()
        )
        if any(name == ".work-bundle" or name.startswith(".work-bundle/") for name in tree):
            raise ControlPlaneError("WB_CONTROL_PLANE_SOURCE_TRACKS_CONTROL_PLANE")
        conflicts = sorted(
            name
            for name in tree
            if any(
                name == existing or name.startswith(existing + "/") or existing.startswith(name + "/")
                for existing in before
            )
        )
        if conflicts:
            raise ControlPlaneError(
                "WB_CONTROL_PLANE_MATERIALIZATION_PATH_CONFLICT",
                {"conflicting_paths": conflicts},
            )
        _run_git_checked(workspace_root, "checkout", "-q", "-B", default_branch, f"origin/{default_branch}")
        _run_git_checked(workspace_root, "branch", "--set-upstream-to", f"origin/{default_branch}", default_branch)
        _ensure_source_local_excludes(workspace_root)
        return before
    except ControlPlaneError:
        _rollback_workspace_root_materialization(workspace_root, before)
        raise


def _attach(
    workspace_root: Path,
    materialize: str,
    repository_paths: dict[str, Path],
    apply: bool,
    *,
    create_script_index: bool = True,
) -> tuple[dict[str, object], int]:
    metadata_path = workspace_root / ".work-bundle/project.yaml"
    text = read(metadata_path)
    failures = _portable_failures(text)
    if failures:
        return {"status": "issues-found", "failure_code": failures[0], "portable_failures": failures}, 1
    configured_control_remote = validated_remote(_control_plane_remote(text)) if _control_plane_remote(text) else ""
    actual_control_remote = _git_remote(workspace_root / ".work-bundle")
    if configured_control_remote and actual_control_remote != configured_control_remote:
        return {
            "status": "issues-found",
            "failure_code": "WB_CONTROL_PLANE_ORIGIN_CONFLICT",
            "workspace_id": _workspace_id(text),
        }, 1
    workspace_id = _workspace_id(text)
    slug = _workspace_slug(workspace_root, text)
    workspace_mode = _workspace_value(text, "mode")
    repositories = _v4_repositories(text)
    if workspace_mode == "composite":
        for repository in repositories:
            if str(repository.get("workspace_binding_type") or "") != "member":
                continue
            member_path = _member_segment(repository, str(repository.get("workspace_binding_name") or repository.get("id") or ""))
            if member_path and _root_index_tracks(workspace_root, member_path):
                raise ControlPlaneError(
                    "WB_CONTROL_PLANE_MEMBER_PATH_TRACKED",
                    {"repository_id": str(repository.get("id") or "")},
                )
    bindings = _registry_bindings()
    existing_binding = bindings.get(workspace_id, {})
    existing_root = str(existing_binding.get("workspace_root") or "") if isinstance(existing_binding, dict) else ""
    if existing_root and Path(existing_root).expanduser().resolve() != workspace_root:
        return {
            "status": "issues-found",
            "failure_code": "WB_CONTROL_PLANE_DUPLICATE_MATERIALIZATION",
            "workspace_id": workspace_id,
            "existing_workspace_root": existing_root,
            "requested_workspace_root": str(workspace_root),
        }, 1
    protected = _protected_tracked_paths(workspace_root)
    if protected:
        return {
            "status": "issues-found",
            "failure_code": "WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED",
            "protected_paths": protected,
        }, 1
    existing_repositories_value = existing_binding.get("repositories") if isinstance(existing_binding, dict) else {}
    existing_repositories = existing_repositories_value if isinstance(existing_repositories_value, dict) else {}
    states: list[dict[str, object]] = []
    readiness_failures: list[str] = []
    local_repositories: dict[str, dict[str, object]] = {
        key: dict(value) for key, value in existing_repositories.items() if isinstance(value, dict)
    }
    root_materialization_before: set[str] | None = None
    owned_member_paths: list[Path] = []
    agents_path = workspace_root / "AGENTS.md"
    agents_before = agents_path.read_bytes() if agents_path.is_file() else None
    exclude_path = workspace_root / ".git/info/exclude"
    exclude_before = exclude_path.read_bytes() if exclude_path.is_file() else None

    def rollback_attach() -> None:
        for owned_path in reversed(owned_member_paths):
            try:
                relative = owned_path.resolve().relative_to(workspace_root)
            except ValueError:
                continue
            if not relative.parts or relative.parts[0] == ".work-bundle":
                continue
            if owned_path.is_symlink() or owned_path.is_file():
                owned_path.unlink(missing_ok=True)
            elif owned_path.is_dir():
                shutil.rmtree(owned_path)
        if root_materialization_before is not None:
            _rollback_workspace_root_materialization(workspace_root, root_materialization_before)
        if agents_before is None:
            agents_path.unlink(missing_ok=True)
        else:
            agents_path.parent.mkdir(parents=True, exist_ok=True)
            agents_path.write_bytes(agents_before)
        if root_materialization_before is None and (workspace_root / ".git").exists():
            if exclude_before is None:
                exclude_path.unlink(missing_ok=True)
            else:
                exclude_path.parent.mkdir(parents=True, exist_ok=True)
                exclude_path.write_bytes(exclude_before)
    try:
        for repository in repositories:
            repository_id = str(repository.get("id") or "")
            remote = str(repository.get("canonical_remote") or "")
            manual_locator = repository.get("locator_type") == "manual"
            binding_type = str(repository.get("workspace_binding_type") or "")
            binding_name = str(repository.get("workspace_binding_name") or repository_id)
            candidate = repository_paths.get(repository_id)
            if binding_type == "root" and candidate is not None and candidate != workspace_root:
                raise ControlPlaneError(
                    "WB_CONTROL_PLANE_ROOT_BINDING_PATH_MISMATCH",
                    {"repository_id": repository_id},
                )
            existing_repository = local_repositories.get(repository_id, {})
            if candidate is None and existing_repository.get("project_root"):
                bound_path = Path(str(existing_repository["project_root"])).expanduser().resolve()
                if bound_path.exists():
                    candidate = bound_path
            if binding_type == "root" and candidate is None and (workspace_root / ".git").exists():
                candidate = workspace_root
            if binding_type != "root" and candidate is None:
                default_candidate = (workspace_root / _member_segment(repository, binding_name)).resolve()
                if default_candidate.parent != workspace_root or default_candidate.name == ".work-bundle":
                    raise ControlPlaneError(
                        "WB_CONTROL_PLANE_MATERIALIZATION_PATH_INVALID",
                        {"repository_id": repository_id},
                    )
                if default_candidate.exists() or default_candidate.is_symlink():
                    candidate = default_candidate
            if candidate is None and materialize in {"missing", "all"} and not manual_locator:
                if apply:
                    candidate = workspace_root if binding_type == "root" else (workspace_root / _member_segment(repository, binding_name)).resolve()
                    if binding_type == "root":
                        root_materialization_before = _materialize_workspace_root(
                            remote, workspace_root, str(repository.get("default_branch") or "main")
                        )
                    else:
                        if candidate.parent != workspace_root or candidate.name == ".work-bundle":
                            raise ControlPlaneError(
                                "WB_CONTROL_PLANE_MATERIALIZATION_PATH_INVALID",
                                {"repository_id": repository_id},
                            )
                        _materialize(remote, candidate)
                        owned_member_paths.append(candidate)
            state = "absent"
            if candidate is not None and candidate.exists():
                actual_remote = "" if manual_locator else _resolved_git_remote(candidate)
                if not manual_locator and actual_remote != canonical_remote(remote):
                    raise ControlPlaneError(
                        "WB_CONTROL_PLANE_REMOTE_CONFLICT",
                        {"repository_id": repository_id},
                    )
                if manual_locator:
                    state = "manual-existing"
                elif binding_type == "root" and repository_id not in repository_paths and not existing_repository:
                    state = "materialized-root" if apply and materialize in {"missing", "all"} else "compatible-existing"
                else:
                    state = "materialized-managed" if candidate in owned_member_paths else "compatible-existing"
                local_repositories[repository_id] = {
                    **existing_repository,
                    "project_root": str(candidate),
                    "checkout_kind": (
                        "manual"
                        if manual_locator
                        else (
                            "workspace-root"
                            if binding_type == "root"
                            else (
                                "nested-member"
                                if workspace_mode == "composite"
                                else ("managed-worktree" if candidate.parent == workspace_root else "external")
                            )
                        )
                    ),
                    "observed_branch": "" if manual_locator else _git(candidate, "branch", "--show-current"),
                    "observed_head": "" if manual_locator else _git(candidate, "rev-parse", "HEAD"),
                    "observed_at": utc_now_rfc3339(),
                    "git_common_dir": "" if manual_locator else _git(candidate, "rev-parse", "--git-common-dir"),
                }
                if not manual_locator:
                    readiness_failures.extend(
                        _repository_execution_issues(candidate, str(repository.get("default_branch") or ""), repository_id)
                    )
            else:
                local_repositories.pop(repository_id, None)
            states.append({"id": repository_id, "state": state, "required": bool(repository.get("required"))})
    except ControlPlaneError:
        rollback_attach()
        raise
    except OSError as exc:
        rollback_attach()
        raise ControlPlaneError("WB_CONTROL_PLANE_TRANSACTION_FAILED") from exc
    if apply:
        try:
            changed = ensure_workspace_resources(
                workspace_root,
                create_script_index=create_script_index,
            )
            for relative in (".work-bundle/git", ".work-bundle/runtime", ".work-bundle/orchestration/execution-state"):
                path = workspace_root / relative
                if not path.exists():
                    path.mkdir(parents=True)
                    changed.append(str(path))
            changed.extend(_sync_agents(workspace_root))
            if workspace_mode in {"single-repository", "composite"} and (workspace_root / ".git").exists():
                if _ensure_source_local_excludes(workspace_root, _composite_members(text) if workspace_mode == "composite" else ()):
                    changed.append(str(workspace_root / ".git/info/exclude"))
            control = workspace_root / ".work-bundle"
            bindings[workspace_id] = {
                **existing_binding,
                "slug": slug,
                "workspace_root": str(workspace_root),
                "control_plane_path": str(control),
                "control_plane_remote": _git_remote(control),
                "observed_control_plane_head": _git(control, "rev-parse", "HEAD"),
                "repositories": local_repositories,
            }
            readiness_failures = []
            repositories_by_id = {str(item.get("id") or ""): item for item in repositories}
            for repository_id, local in local_repositories.items():
                portable = repositories_by_id.get(repository_id, {})
                if portable.get("locator_type") == "manual":
                    continue
                project_root = Path(str(local.get("project_root") or "")).expanduser().resolve()
                readiness_failures.extend(
                    _repository_execution_issues(
                        project_root, str(portable.get("default_branch") or ""), repository_id
                    )
                )
        except ControlPlaneError:
            rollback_attach()
            raise
        except OSError as exc:
            rollback_attach()
            raise ControlPlaneError("WB_CONTROL_PLANE_TRANSACTION_FAILED") from exc
    else:
        changed = []
    ready = all(not row["required"] or row["state"] != "absent" for row in states) and not readiness_failures
    final_failures: list[str] = []
    if apply:
        final_failures.extend(_portable_failures(read(metadata_path)))
        required_resources = ["credentials/credentials.yaml", "AGENTS.md"]
        if create_script_index:
            required_resources.insert(0, "script/index.yaml")
        final_failures.extend(
            f"WB_CONTROL_PLANE_RESOURCE_MISSING:{relative}"
            for relative in required_resources
            if not (workspace_root / relative).is_file()
        )
        agents_text = read(workspace_root / "AGENTS.md")
        if agents_text.count(AGENTS_START) != 1 or agents_text.count(AGENTS_END) != 1:
            final_failures.append("WB_CONTROL_PLANE_AGENTS_SYNC_INVALID")
        if _protected_tracked_paths(workspace_root):
            final_failures.append("WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED")
    if final_failures:
        rollback_attach()
        raise ControlPlaneError(
            final_failures[0],
            {
                "final_validation_failures": final_failures,
                "changed_files": sorted(set(changed)),
            },
        )
    if apply:
        try:
            registry = _write_bindings(bindings)
            changed.append(str(registry))
        except (ControlPlaneError, OSError):
            rollback_attach()
            raise ControlPlaneError("WB_CONTROL_PLANE_TRANSACTION_FAILED")
    return {
        "status": "passed",
        "portable_status": "passed",
        "workspace_id": workspace_id,
        "repositories": states,
        "execution_ready": ready,
        "execution_readiness_failures": readiness_failures,
        "dry_run": not apply,
        "changed_files": sorted(set(changed)),
    }, 0


def cmd_attach_workspace(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py attach-workspace")
    parser.add_argument("workspace_root")
    parser.add_argument("--materialize", choices=["none", "missing", "all"], default="none")
    parser.add_argument("--repository-path", action="append", default=[], metavar="ID=PATH")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parsed = parser.parse_args(args)
    try:
        paths = _parse_repository_paths(parsed.repository_path)
        result, code = _attach(Path(parsed.workspace_root).expanduser().resolve(), parsed.materialize, paths, parsed.apply)
    except ControlPlaneError as exc:
        result, code = {"status": "issues-found", "failure_code": exc.code, **exc.details}, 1
    out({"command": "attach-workspace", **result})
    return code


def cmd_doctor_workspace(args: list[str], *, command_name: str = "doctor-workspace") -> int:
    parser = argparse.ArgumentParser(prog="wb.py doctor-workspace")
    parser.add_argument("workspace_root")
    parser.add_argument("--repair", action="store_true")
    parsed = parser.parse_args(args)
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    text = read(workspace_root / ".work-bundle/project.yaml")
    portable_failures = _portable_failures(text)
    workspace_id = _workspace_id(text)
    bindings = _registry_bindings()
    binding = bindings.get(workspace_id)
    local_failures: list[str] = []
    if not binding:
        local_failures.append("WB_CONTROL_PLANE_BINDING_MISSING")
    elif Path(str(binding.get("workspace_root") or "")).resolve() != workspace_root:
        local_failures.append("WB_CONTROL_PLANE_BINDING_ROOT_MISMATCH")
    repositories = binding.get("repositories") if isinstance(binding, dict) else {}
    local_repositories = repositories if isinstance(repositories, dict) else {}
    missing_required: list[str] = []
    if not portable_failures and _workspace_value(text, "mode") == "composite":
        for repo in _v4_repositories(text):
            if str(repo.get("workspace_binding_type") or "") != "member":
                continue
            member_path = _member_segment(repo, str(repo.get("workspace_binding_name") or repo.get("id") or ""))
            if member_path and _root_index_tracks(workspace_root, member_path):
                local_failures.append(f"WB_CONTROL_PLANE_MEMBER_PATH_TRACKED:{repo.get('id')}")
    if not portable_failures:
        configured_control_remote = validated_remote(_control_plane_remote(text)) if _control_plane_remote(text) else ""
        actual_control_remote = _git_remote(workspace_root / ".work-bundle")
        if configured_control_remote and configured_control_remote != actual_control_remote:
            local_failures.append("WB_CONTROL_PLANE_ORIGIN_CONFLICT")
        for repo in _v4_repositories(text):
            repository_id = str(repo.get("id") or "")
            local = local_repositories.get(repository_id)
            if not isinstance(local, dict) or not local.get("project_root"):
                if repo.get("required"):
                    missing_required.append(repository_id)
                continue
            project_path = Path(str(local["project_root"])).expanduser().resolve()
            if not project_path.is_dir():
                local_failures.append(f"WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:{repository_id}")
                if repo.get("required"):
                    missing_required.append(repository_id)
                continue
            if repo.get("locator_type") != "manual":
                try:
                    actual_remote = _resolved_git_remote(project_path)
                except ControlPlaneError as exc:
                    local_failures.append(f"{exc.code}:{repository_id}")
                    actual_remote = ""
                if actual_remote != str(repo.get("canonical_remote") or ""):
                    local_failures.append(f"WB_CONTROL_PLANE_BOUND_REMOTE_CONFLICT:{repository_id}")
                    if repo.get("required"):
                        missing_required.append(repository_id)
                if not _git(project_path, "rev-parse", "--git-common-dir"):
                    local_failures.append(f"WB_CONTROL_PLANE_BOUND_GIT_INVALID:{repository_id}")
                readiness_issues = _repository_execution_issues(
                    project_path, str(repo.get("default_branch") or ""), repository_id
                )
                for issue in readiness_issues:
                    if issue not in missing_required:
                        missing_required.append(issue)
    if parsed.repair and not portable_failures:
        try:
            result, code = _attach(
                workspace_root,
                "none",
                {},
                True,
                create_script_index=False,
            )
        except ControlPlaneError as exc:
            local_failures.append(exc.code)
            result, code = {"status": "issues-found"}, 1
        if code == 0:
            bindings = _registry_bindings()
            binding = bindings.get(workspace_id)
            if binding:
                local_failures = [item for item in local_failures if item != "WB_CONTROL_PLANE_BINDING_MISSING"]
    status = "passed" if not portable_failures and not local_failures else "issues-found"
    out(
        {
            "command": command_name,
            "status": status,
            "portable": {"status": "passed" if not portable_failures else "issues-found", "failures": portable_failures},
            "local_binding": {"status": "passed" if not local_failures else "issues-found", "failures": local_failures},
            "execution_readiness": {
                "status": "not-ready" if missing_required else "passed",
                "execution_readiness_failures": missing_required,
            },
            "repair": parsed.repair,
        }
    )
    return 0 if status == "passed" else 1


def cmd_detach_workspace(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py detach-workspace")
    parser.add_argument("workspace_root")
    parser.add_argument("--apply", action="store_true", required=True)
    parsed = parser.parse_args(args)
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    workspace_id = _workspace_id(read(workspace_root / ".work-bundle/project.yaml"))
    bindings = _registry_bindings()
    removed = bindings.pop(workspace_id, None) is not None
    registry = _write_bindings(bindings)
    out(
        {
            "command": "detach-workspace",
            "status": "passed",
            "workspace_id": workspace_id,
            "binding_removed": removed,
            "changed_files": [str(registry)] if removed else [],
            "portable_control_plane_preserved": True,
            "source_checkouts_preserved": True,
        }
    )
    return 0


def _apply_add_workspace_member(
    workspace_root: Path, text: str, member: dict[str, str]
) -> dict[str, object]:
    metadata_path = workspace_root / ".work-bundle/project.yaml"
    exclude_path = workspace_root / ".git/info/exclude"
    registry = resolve_project_registry_path()
    member_path = workspace_root / member["path"]
    workspace_id = _workspace_id(text)
    owned_member = False
    try:
        _add_workspace_member_preflight(workspace_root, text)
        if member_path.exists() or member_path.is_symlink():
            _inspect_existing_member_checkout(member_path, member)
        else:
            owned_member = True
            _materialize_member_checkout(member_path, member)
        rendered = _append_member_metadata(text, member)
        portable = _portable_failures(rendered)
        if portable:
            raise ControlPlaneError(portable[0])
        members = _composite_members(rendered)
        exclude_text = _exclude_text_with_source_and_members(read(exclude_path), members)
        bindings = _registry_bindings()
        existing = bindings.get(workspace_id, {})
        if not isinstance(existing, dict):
            existing = {}
        existing_repositories = existing.get("repositories")
        local_repositories = dict(existing_repositories) if isinstance(existing_repositories, dict) else {}
        current_binding = local_repositories.get(member["repository_id"])
        local_repositories[member["repository_id"]] = {
            **(current_binding if isinstance(current_binding, dict) else {}),
            "project_root": str(member_path.resolve()),
            "checkout_kind": "nested-member",
            "observed_branch": _git(member_path, "branch", "--show-current"),
            "observed_head": _git(member_path, "rev-parse", "HEAD"),
            "observed_at": utc_now_rfc3339(),
            "git_common_dir": _git(member_path, "rev-parse", "--git-common-dir"),
        }
        bindings[workspace_id] = {
            **existing,
            "repositories": local_repositories,
        }
        changed = _atomic_publish(
            {
                metadata_path: rendered,
                exclude_path: exclude_text,
                registry: _bindings_document(bindings, read(registry) or "projects: []\n"),
            }
        )
        return {
            "status": "passed",
            "dry_run": False,
            "replay": False,
            "changed_files": sorted(set(changed)),
            "workspace_id": workspace_id,
        }
    except (ControlPlaneError, OSError) as exc:
        if owned_member and member_path.exists():
            if member_path.is_symlink() or member_path.is_file():
                member_path.unlink(missing_ok=True)
            elif member_path.is_dir():
                shutil.rmtree(member_path)
        if isinstance(exc, ControlPlaneError):
            raise
        raise ControlPlaneError("WB_CONTROL_PLANE_TRANSACTION_FAILED") from exc


def cmd_add_workspace_member(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py add-workspace-member")
    parser.add_argument("workspace_root")
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--default-branch", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parser.add_argument("--accepted-proposal-id")
    parsed = parser.parse_args(args)
    if parsed.apply and not parsed.accepted_proposal_id:
        parser.error("--accepted-proposal-id is required with --apply")
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    try:
        remote = validated_remote(parsed.remote)
        path = _validate_member_path(parsed.path)
        name = str(parsed.name or "").strip()
        if not name:
            raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_BINDING_INVALID")
        if not parsed.repository_id:
            raise ControlPlaneError("WB_CONTROL_PLANE_REPOSITORY_ID_MISSING")
        member = {
            "repository_id": parsed.repository_id,
            "name": name,
            "path": path,
            "remote": remote,
            "default_branch": str(parsed.default_branch or "").strip(),
        }
        metadata_path = workspace_root / ".work-bundle/project.yaml"
        text = read(metadata_path)
        mode = _workspace_value(text, "mode")
        if mode not in {"single-repository", "composite"}:
            raise ControlPlaneError("WB_CONTROL_PLANE_COMPOSITE_SOURCE_MODE_INVALID")
        portable = _portable_failures(text)
        if portable:
            raise ControlPlaneError(portable[0])
        _add_workspace_member_preflight(workspace_root, text)
        if _root_index_tracks(workspace_root, path):
            raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_PATH_TRACKED")
        member_path = workspace_root / path
        if member_path.exists() or member_path.is_symlink():
            _inspect_existing_member_checkout(member_path, member)
        classification = _classify_workspace_member(_v4_repositories(text), member)
        if classification == "collision":
            raise ControlPlaneError("WB_CONTROL_PLANE_MEMBER_COLLISION")
        _require_add_workspace_member_target(text, member, classification)
        proposal = _add_workspace_member_proposal(workspace_root, text, member)
        payload = {
            "command": "add-workspace-member",
            "proposal_id": proposal["proposal_id"],
            "proposal": {key: value for key, value in proposal.items() if key != "proposal_id"},
        }
        if parsed.dry_run:
            out({**payload, "status": "passed", "dry_run": True, "changed_files": []})
            return 0
        live_text = read(metadata_path)
        live_proposal = _add_workspace_member_proposal(workspace_root, live_text, member)
        if parsed.accepted_proposal_id != live_proposal["proposal_id"]:
            out({**payload, "status": "issues-found", "failure_code": "WB_CONTROL_PLANE_PROPOSAL_STALE", "changed_files": []})
            return 1
        if classification == "match":
            live_binding = _add_workspace_member_preflight(workspace_root, live_text)
            _require_add_workspace_member_replay_state(workspace_root, member, live_binding)
            out({**payload, "status": "passed", "dry_run": False, "replay": True, "changed_files": []})
            return 0
        applied = _apply_add_workspace_member(workspace_root, live_text, member)
        out({**payload, **applied})
        return 0
    except ControlPlaneError as exc:
        out(
            {
                "command": "add-workspace-member",
                "status": "issues-found",
                "failure_code": exc.code,
                "changed_files": [],
                **exc.details,
            }
        )
        return 1
