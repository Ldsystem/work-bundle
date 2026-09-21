#!/usr/bin/env python3
"""Workspace admission against portable orchestration blockers.

This module intentionally owns no review rounds, reviewer process, receipts,
publication, or workflow finalization.  Its current surface is limited to
workspace discovery, admission checks, and scoped blocker-exception cleanup.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterator, Mapping

import yaml


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from platform_runtime import (
    atomic_replace_bytes,
    blocking_file_lock,
    contains_link_like_component,
    is_link_like,
)


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ADMISSION_OPERATIONS = frozenset({
    "ordinary_new",
    "reconciliation",
    "read_only",
    "blocker_recording",
    "knowledge_return",
})
MUTATING_ADMISSION_OPERATIONS = frozenset({"ordinary_new", "reconciliation"})


class BoundedClosureError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _workspace_root(value: Path) -> Path:
    unresolved = value.expanduser()
    if is_link_like(unresolved):
        raise BoundedClosureError("WB_POST_EXECUTION_WORKSPACE_INVALID")
    root = unresolved.resolve()
    metadata = root / ".work-bundle/project.yaml"
    if (
        not metadata.is_file()
        or contains_link_like_component(metadata, anchor=root)
    ):
        raise BoundedClosureError("WB_POST_EXECUTION_WORKSPACE_INVALID")
    return root


def resolve_working_workspace(start: Path, *, workspace_id: str | None = None) -> Path | None:
    """Resolve portable authority from a workspace, member, or bound worktree."""

    current = Path(os.path.abspath(start.expanduser()))
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        metadata = candidate / ".work-bundle/project.yaml"
        if metadata.is_file():
            if is_link_like(candidate) or contains_link_like_component(metadata, anchor=candidate):
                return None
            return candidate.resolve()
    config_root = Path(os.environ.get("WB_CONFIG_ROOT", Path.home() / ".work-bundle")).expanduser()
    bootstrap = config_root / "bootstrap.yaml"
    if not bootstrap.is_file():
        return None
    try:
        bootstrap_data = yaml.safe_load(bootstrap.read_text(encoding="utf-8"))
        registry_value = bootstrap_data.get("project_registry") if isinstance(bootstrap_data, Mapping) else None
        if not isinstance(registry_value, str):
            return None
        registry = Path(registry_value.replace("$work_bundle_config_root", str(config_root))).expanduser().resolve()
        registry_data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(registry_data, Mapping):
        return None
    bindings = registry_data.get("device_bindings")
    if not isinstance(bindings, Mapping):
        return None
    candidates = bindings.items() if workspace_id is None else [(workspace_id, bindings.get(workspace_id))]
    for identity, raw in candidates:
        if not isinstance(raw, Mapping):
            continue
        root_value = raw.get("workspace_root")
        if not isinstance(root_value, str):
            continue
        root = Path(root_value).expanduser().resolve()
        repositories = raw.get("repositories", [])
        locators = [root]
        repository_values = repositories.values() if isinstance(repositories, Mapping) else repositories
        if isinstance(repository_values, (list, tuple)) or hasattr(repository_values, "__iter__"):
            locators.extend(
                Path(str(item["project_root"])).expanduser().resolve()
                for item in repository_values
                if isinstance(item, Mapping) and isinstance(item.get("project_root"), str)
            )
        bound_identity = workspace_id or next((part for part in current.parts if part == identity), None)
        if bound_identity == identity and (
            workspace_id is not None
            or any(path == current or path in current.parents for path in locators)
        ):
            return root if (root / ".work-bundle/project.yaml").is_file() else None
    return None


def _metadata_path(root: Path) -> Path:
    return root / ".work-bundle/project.yaml"


def _load_metadata(root: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(_metadata_path(root).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID") from error
    if not isinstance(value, dict):
        raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID")
    return value


def _policy(metadata: Mapping[str, Any], *, required: bool) -> Mapping[str, Any] | None:
    control = metadata.get("orchestration_control")
    if control is None and not required:
        return None
    if not isinstance(control, Mapping) or control.get("schema_version") != 1:
        raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID")
    return control


def _control_list(control: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    value = control.get(field, [])
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID", field)
    return value


def _active_blockers(root: Path, control: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    blockers = _control_list(control, "blockers")
    active: list[Mapping[str, Any]] = []
    store = root.resolve()
    for blocker in blockers:
        if blocker.get("status") != "active":
            continue
        blocker_id = blocker.get("id")
        reference = blocker.get("specification")
        if not isinstance(blocker_id, str) or not blocker_id or not isinstance(reference, str) or not reference:
            raise BoundedClosureError(
                "WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID", str(_metadata_path(root))
            )
        candidate = Path(reference)
        unresolved = candidate if candidate.is_absolute() else root / candidate
        lexical = Path(os.path.abspath(unresolved))
        try:
            lexical.relative_to(store)
        except ValueError:
            valid_boundary = False
        else:
            valid_boundary = not contains_link_like_component(unresolved, anchor=store)
        spec = lexical.resolve(strict=False)
        if not valid_boundary or not spec.is_relative_to(store) or not spec.is_file():
            raise BoundedClosureError(
                "WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID",
                f"metadata={_metadata_path(root)} blocker={blocker_id} specification={spec} "
                "rule=orch-bounded-closure; read the metadata entry and blocking specification",
            )
        active.append(blocker)
    return active


def require_orchestration_admission(
    root: Path, *, operation: str, flow_id: str | None
) -> dict[str, object]:
    """Guard one operation using portable state from the resolved workspace."""

    workspace = _workspace_root(root)
    if operation not in ADMISSION_OPERATIONS:
        raise BoundedClosureError("WB_ORCHESTRATION_OPERATION_INVALID", operation)
    metadata = _load_metadata(workspace)
    raw_control = metadata.get("orchestration_control")
    if raw_control is None:
        return {"status": "admitted", "legacy": True, "workspace": str(workspace)}
    if operation not in MUTATING_ADMISSION_OPERATIONS:
        return {"status": "admitted", "legacy": False, "workspace": str(workspace)}
    control = _policy(metadata, required=False)
    assert control is not None
    blockers = _active_blockers(workspace, control)
    if blockers:
        exemptions = _control_list(control, "implementation_exemptions")
        exempt_ids = {
            item.get("blocker_id")
            for item in exemptions
            if item.get("status") == "active" and item.get("flow_id") == flow_id
        }
        denied = next((item for item in blockers if item.get("id") not in exempt_ids), None)
        if denied is not None:
            spec_ref = str(denied["specification"])
            spec = Path(spec_ref) if Path(spec_ref).is_absolute() else workspace / spec_ref
            raise BoundedClosureError(
                "WB_ORCHESTRATION_ADMISSION_BLOCKED",
                f"metadata={_metadata_path(workspace)} blocker={denied['id']} "
                f"entry=orchestration_control.blockers specification={spec.resolve()} "
                "rule=orch-bounded-closure; read the metadata entry and blocking specification",
            )
    return {"status": "admitted", "legacy": False, "workspace": str(workspace)}


def _lock_path(root: Path) -> Path:
    return root / ".work-bundle/runtime/orchestration-control/.admission.lock"


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    lock_path = _lock_path(root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        with blocking_file_lock(stream):
            yield


def _atomic_write(path: Path, content: bytes) -> None:
    atomic_replace_bytes(path, content)


def restore_implementation_exception(
    root: Path,
    *,
    backup_path: Path,
    backup_sha256: str,
    flow_id: str,
    blocker_id: str,
) -> bool:
    """Retire one scoped exception and merge its exact original blocker back."""

    workspace = _workspace_root(root)
    backup = backup_path.expanduser().resolve()
    try:
        content = backup.read_bytes()
    except OSError as error:
        raise BoundedClosureError("WB_ORCHESTRATION_BACKUP_INVALID") from error
    if not SHA256_RE.fullmatch(backup_sha256) or hashlib.sha256(content).hexdigest() != backup_sha256:
        raise BoundedClosureError("WB_ORCHESTRATION_BACKUP_INVALID")
    try:
        original = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise BoundedClosureError("WB_ORCHESTRATION_BACKUP_INVALID") from error
    if not isinstance(original, Mapping) or not isinstance(original.get("orchestration_control"), Mapping):
        raise BoundedClosureError("WB_ORCHESTRATION_BACKUP_INVALID")
    original_control = original["orchestration_control"]
    original_blockers = _control_list(original_control, "blockers")
    original_blocker = next(
        (dict(item) for item in original_blockers if item.get("id") == blocker_id), None
    )
    if original_blocker is None:
        raise BoundedClosureError("WB_ORCHESTRATION_BACKUP_INVALID", blocker_id)
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        control = _policy(metadata, required=True)
        assert isinstance(control, dict)
        exemptions = _control_list(control, "implementation_exemptions")
        retained = [
            dict(item)
            for item in exemptions
            if not (
                item.get("flow_id") == flow_id
                and item.get("blocker_id") == blocker_id
            )
        ]
        blockers = [
            dict(item)
            for item in _control_list(control, "blockers")
            if item.get("id") != blocker_id
        ]
        blockers.append(original_blocker)
        control["implementation_exemptions"] = retained
        control["blockers"] = blockers
        _atomic_write(
            _metadata_path(workspace),
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).encode("utf-8"),
        )
    return True
