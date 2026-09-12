#!/usr/bin/env python3
"""Canonical bounded post-execution review-round state owner.

The append-only round ledger is controller state.  Portable metadata receives
only the latest per-flow projection, so plan revisions and review artifacts can
never become the counter authority.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterator, Mapping, Sequence

import yaml


ROUND_LIMIT = 5
LEDGER_SCHEMA = "post-execution-review-ledger-v1"
FLOW_STATES_KEY = "post_execution_review_flows"
TERMINAL_ATTEMPT_STATES = frozenset(
    {"completed", "blocked", "partial", "failed", "cancelled"}
)
ROUND_OUTCOMES = frozenset({"accepted", "findings", "blocked"})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
ADMISSION_OPERATIONS = frozenset({
    "ordinary_new", "reconciliation", "round_completion", "read_only",
    "blocker_recording", "knowledge_return", "finalization",
})
MUTATING_ADMISSION_OPERATIONS = frozenset({"ordinary_new", "reconciliation"})


class BoundedClosureError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", field)
    return value


def _target_identity(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "target_identity")
    required = {"artifact_id", "revision", "sha256", "source_tree"}
    if set(value) != required:
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "target_identity")
    artifact_id = _identifier(value.get("artifact_id"), "target_identity.artifact_id")
    revision = value.get("revision")
    digest = value.get("sha256")
    source_tree = value.get("source_tree")
    if (
        not isinstance(revision, str)
        or not revision
        or not isinstance(digest, str)
        or not SHA256_RE.fullmatch(digest)
        or not isinstance(source_tree, str)
        or not source_tree
    ):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "target_identity")
    return {
        "artifact_id": artifact_id,
        "revision": revision,
        "sha256": digest,
        "source_tree": source_tree,
    }


def _workspace_root(value: Path) -> Path:
    root = value.expanduser().resolve()
    metadata = root / ".work-bundle/project.yaml"
    if not metadata.is_file() or metadata.is_symlink():
        raise BoundedClosureError("WB_POST_EXECUTION_WORKSPACE_INVALID")
    return root


def resolve_working_workspace(start: Path, *, workspace_id: str | None = None) -> Path | None:
    """Resolve portable authority from a workspace, member, or bound worktree."""

    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".work-bundle/project.yaml").is_file():
            return candidate
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
        if bound_identity == identity and (workspace_id is not None or any(path == current or path in current.parents for path in locators)):
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
    if not isinstance(control, Mapping):
        raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID")
    if "review_revision_limit" in control:
        raise BoundedClosureError("WB_POST_EXECUTION_LEGACY_POLICY_REJECTED")
    if (
        control.get("schema_version") != 1
        or control.get("post_execution_review_round_limit") != ROUND_LIMIT
    ):
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
            raise BoundedClosureError("WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID", str(_metadata_path(root)))
        candidate = Path(reference)
        spec = candidate.resolve(strict=False) if candidate.is_absolute() else (root / candidate).resolve(strict=False)
        if not spec.is_relative_to(store) or spec.is_symlink() or not spec.is_file():
            raise BoundedClosureError(
                "WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID",
                f"metadata={_metadata_path(root)} blocker={blocker_id} specification={spec} rule=orch-bounded-closure; read the metadata entry and blocking specification",
            )
        active.append(blocker)
    return active


def require_orchestration_admission(
    root: Path, *, operation: str, flow_id: str | None
) -> dict[str, object]:
    """Guard one operation using portable state from the resolved working workspace."""

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
    flows = _control_list(control, FLOW_STATES_KEY)
    if operation == "reconciliation":
        if not isinstance(flow_id, str) or not flow_id:
            raise BoundedClosureError("WB_ORCHESTRATION_FLOW_REQUIRED")
        state = next((item for item in flows if item.get("flow_id") == flow_id), None)
        if state is not None and state.get("finalization_required") is True:
            raise BoundedClosureError(
                "WB_ORCHESTRATION_FINALIZATION_REQUIRED",
                f"flow={flow_id} metadata={_metadata_path(workspace)} rule=orch-bounded-closure",
            )
    if operation in MUTATING_ADMISSION_OPERATIONS and blockers:
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
                f"metadata={_metadata_path(workspace)} blocker={denied['id']} entry=orchestration_control.blockers specification={spec.resolve()} rule=orch-bounded-closure; read the metadata entry and blocking specification",
            )
    return {"status": "admitted", "legacy": False, "workspace": str(workspace)}


def restore_implementation_exception(
    root: Path, *, backup_path: Path, backup_sha256: str, flow_id: str, blocker_id: str
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
    original_blocker = next((dict(item) for item in original_blockers if item.get("id") == blocker_id), None)
    if original_blocker is None:
        raise BoundedClosureError("WB_ORCHESTRATION_BACKUP_INVALID", blocker_id)
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        control = _policy(metadata, required=True)
        assert isinstance(control, dict)
        exemptions = _control_list(control, "implementation_exemptions")
        retained = [dict(item) for item in exemptions if not (item.get("flow_id") == flow_id and item.get("blocker_id") == blocker_id)]
        blockers = [dict(item) for item in _control_list(control, "blockers") if item.get("id") != blocker_id]
        blockers.append(original_blocker)
        control["implementation_exemptions"] = retained
        control["blockers"] = blockers
        _atomic_write(_metadata_path(workspace), yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).encode("utf-8"))
    return True


def bounded_review_enabled(root: Path) -> bool:
    """Return whether the optional current workspace policy is enabled."""

    workspace = root.expanduser().resolve()
    if not _metadata_path(workspace).is_file():
        return False
    return _policy(_load_metadata(workspace), required=False) is not None


def _state_paths(root: Path) -> tuple[Path, Path]:
    directory = root / ".work-bundle/runtime/orchestration-control"
    return directory / "post-execution-review-rounds-v1.json", directory / ".rounds.lock"


@contextmanager
def _locked(root: Path) -> Iterator[None]:
    state_path, lock_path = _state_paths(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _load_ledger(root: Path) -> dict[str, Any]:
    path, _ = _state_paths(root)
    if not path.exists():
        return {"schema": LEDGER_SCHEMA, "flows": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BoundedClosureError("WB_POST_EXECUTION_LEDGER_INVALID") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != LEDGER_SCHEMA
        or not isinstance(value.get("flows"), dict)
    ):
        raise BoundedClosureError("WB_POST_EXECUTION_LEDGER_INVALID")
    return value


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _write_ledger(root: Path, ledger: Mapping[str, Any]) -> None:
    path, _ = _state_paths(root)
    _atomic_write(path, (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode())


def _flow_projection(flow: Mapping[str, Any]) -> dict[str, Any]:
    rounds = flow["rounds"]
    latest = rounds[-1] if rounds else None
    completed = [item for item in rounds if item["state"] == "completed"]
    projection = {
        "flow_id": flow["flow_id"],
        "execution_complete": flow["execution_complete"],
        "latest_reserved_round_id": latest["round_id"] if latest else None,
        "latest_completed_round_id": completed[-1]["round_id"] if completed else None,
        "frozen_target_identity": latest["target_identity"] if latest else None,
        "outcome": completed[-1]["outcome"] if completed else None,
        "finalization_required": bool(flow.get("finalization_required")),
    }
    finalization = flow.get("finalization")
    if isinstance(finalization, Mapping):
        projection["finalization_state"] = finalization.get("state")
        projection["finalization_outcome"] = finalization.get("outcome")
    return projection


def _write_metadata_projection(root: Path, metadata: dict[str, Any], ledger: Mapping[str, Any]) -> None:
    control = metadata["orchestration_control"]
    assert isinstance(control, dict)
    control[FLOW_STATES_KEY] = [
        _flow_projection(flow)
        for _, flow in sorted(ledger["flows"].items())
    ]
    rendered = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).encode("utf-8")
    _atomic_write(_metadata_path(root), rendered)


def _terminal_attempts(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "executor_attempts")
    attempts: list[dict[str, str]] = []
    identities: set[str] = set()
    for raw in values:
        if not isinstance(raw, Mapping):
            raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "executor_attempts")
        identity = _identifier(raw.get("execution_id"), "executor_attempts.execution_id")
        state = raw.get("state")
        if identity in identities or not isinstance(state, str):
            raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "executor_attempts")
        if state not in TERMINAL_ATTEMPT_STATES:
            raise BoundedClosureError("WB_POST_EXECUTION_NOT_TERMINAL", identity)
        if raw.get("mutation_active") is True or raw.get("active") is True:
            raise BoundedClosureError("WB_POST_EXECUTION_NOT_TERMINAL", identity)
        identities.add(identity)
        attempts.append({"execution_id": identity, "state": state})
    return sorted(attempts, key=lambda item: item["execution_id"])


def _missing_evidence(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "known_missing_evidence")
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "known_missing_evidence")
    return sorted(set(values))


def _stored_review_reference(
    root: Path, reference: Mapping[str, Any]
) -> dict[str, str]:
    if (
        set(reference) != {"review_id", "sha256"}
        or not isinstance(reference.get("review_id"), str)
        or not SHA256_RE.fullmatch(str(reference.get("sha256") or ""))
    ):
        raise BoundedClosureError("WB_POST_EXECUTION_EVIDENCE_INVALID")
    review_id = _identifier(reference["review_id"], "review_reference.review_id")
    store = (root / ".work-bundle/orchestration/reviews").resolve()
    path = (store / f"{review_id}.json").resolve(strict=False)
    if (
        not path.is_relative_to(store)
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_mode & 0o222
        or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]
    ):
        raise BoundedClosureError("WB_POST_EXECUTION_EVIDENCE_INVALID")
    return {"review_id": review_id, "sha256": str(reference["sha256"])}


def _public_round(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in (
            "flow_id", "round_id", "round_number", "request_id", "review_id",
            "target_identity", "execution_complete", "terminal_attempts",
            "known_missing_evidence", "state", "outcome", "finalization_required",
        )
        if key in record
    }


def begin_review_round(
    root: Path,
    *,
    flow_id: str,
    request_id: str,
    review_id: str,
    target_identity: Mapping[str, Any],
    executor_attempts: Sequence[Mapping[str, Any]],
    known_missing_evidence: Sequence[str],
) -> dict[str, Any]:
    """Serialize and persist a post-execution round before review preparation."""

    workspace = _workspace_root(root)
    flow_id = _identifier(flow_id, "flow_id")
    request_id = _identifier(request_id, "request_id")
    review_id = _identifier(review_id, "review_id")
    target = _target_identity(target_identity)
    attempts = _terminal_attempts(executor_attempts)
    missing = _missing_evidence(known_missing_evidence)
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        flows = ledger["flows"]
        flow = flows.get(flow_id)
        if flow is None:
            flow = {
                "flow_id": flow_id,
                "execution_complete": True,
                "terminal_attempts": attempts,
                "known_missing_evidence": missing,
                "finalization_required": False,
                "rounds": [],
            }
            flows[flow_id] = flow
        elif (
            flow.get("terminal_attempts") != attempts
            or flow.get("known_missing_evidence") != missing
        ):
            raise BoundedClosureError("WB_POST_EXECUTION_BOUNDARY_COLLISION")
        rounds = flow["rounds"]
        for existing in rounds:
            if (
                existing["request_id"] == request_id
                and existing["target_identity"] == target
            ):
                if existing["review_id"] != review_id:
                    raise BoundedClosureError("WB_POST_EXECUTION_REQUEST_COLLISION")
                return _public_round(existing)
        if flow.get("finalization_required"):
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_REQUIRED")
        if len(rounds) >= ROUND_LIMIT:
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_REQUIRED")
        number = len(rounds) + 1
        record = {
            "flow_id": flow_id,
            "round_id": f"{flow_id}:round:{number:03d}",
            "round_number": number,
            "request_id": request_id,
            "review_id": review_id,
            "target_identity": target,
            "execution_complete": True,
            "terminal_attempts": attempts,
            "known_missing_evidence": missing,
            "state": "reserved",
            "outcome": None,
            "finalization_required": False,
            "reserved_at": _utc_now(),
        }
        rounds.append(record)
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)
        return _public_round(record)


def _find_round(ledger: Mapping[str, Any], flow_id: str, round_id: str) -> dict[str, Any]:
    flow = ledger["flows"].get(flow_id)
    if not isinstance(flow, dict):
        raise BoundedClosureError("WB_POST_EXECUTION_ROUND_NOT_FOUND")
    for record in flow.get("rounds", []):
        if record.get("round_id") == round_id:
            return record
    raise BoundedClosureError("WB_POST_EXECUTION_ROUND_NOT_FOUND")


def review_round_binding(
    root: Path, *, review_id: str, target_identity: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Resolve a reservation for integrated review, or ``None`` for legacy policy."""

    workspace = root.expanduser().resolve()
    if not _metadata_path(workspace).is_file():
        return None
    metadata = _load_metadata(workspace)
    if _policy(metadata, required=False) is None:
        return None
    review_id = _identifier(review_id, "review_id")
    target = _target_identity(target_identity)
    with _locked(workspace):
        ledger = _load_ledger(workspace)
        matches = [
            record
            for flow in ledger["flows"].values()
            for record in flow.get("rounds", [])
            if record.get("review_id") == review_id
        ]
        if len(matches) != 1:
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_REQUIRED")
        record = matches[0]
        if record.get("target_identity") != target or record.get("state") != "reserved":
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        return _public_round(record)


def mark_review_round_prepared(root: Path, *, flow_id: str, round_id: str) -> dict[str, Any]:
    workspace = _workspace_root(root)
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        record = _find_round(ledger, flow_id, round_id)
        if record["state"] != "reserved":
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        record["state"] = "prepared"
        record["prepared_at"] = _utc_now()
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)
        return _public_round(record)


def require_review_round_execution(
    root: Path, *, binding: Mapping[str, Any]
) -> dict[str, Any]:
    """Admit reviewer execution only for its exact live, unjudged round."""

    workspace = _workspace_root(root)
    if not isinstance(binding, Mapping):
        raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
    flow_id = _identifier(binding.get("flow_id"), "binding.flow_id")
    round_id = _identifier(binding.get("round_id"), "binding.round_id")
    review_id = _identifier(binding.get("review_id"), "binding.review_id")
    request_id = _identifier(binding.get("request_id"), "binding.request_id")
    target = _target_identity(binding.get("target_identity"))
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        record = _find_round(ledger, flow_id, round_id)
        if (
            record.get("review_id") != review_id
            or record.get("request_id") != request_id
            or record.get("target_identity") != target
            or record.get("round_number") != binding.get("round_number")
        ):
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        if record.get("state") == "completed":
            raise BoundedClosureError("WB_POST_EXECUTION_JUDGMENT_ALREADY_RECORDED")
        flow = ledger["flows"][flow_id]
        if flow.get("finalization_required") is True:
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_REQUIRED")
        if record.get("state") != "prepared":
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        return _public_round(record)


def review_round_publication_binding(
    root: Path, *, review_id: str, target_identity: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Fail closed before a bounded integrated review publication writes."""

    workspace = root.expanduser().resolve()
    if not _metadata_path(workspace).is_file():
        return None
    metadata = _load_metadata(workspace)
    if _policy(metadata, required=False) is None:
        return None
    review_id = _identifier(review_id, "review_id")
    target = _target_identity(target_identity)
    with _locked(workspace):
        ledger = _load_ledger(workspace)
        matches = [
            record
            for flow in ledger["flows"].values()
            for record in flow.get("rounds", [])
            if record.get("review_id") == review_id
            and record.get("target_identity") == target
        ]
        if len(matches) != 1:
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_REQUIRED")
        if matches[0].get("state") not in {"prepared", "completed"}:
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        return _public_round(matches[0])


def complete_review_round(
    root: Path,
    *,
    flow_id: str,
    round_id: str,
    outcome: str,
    review_reference: Mapping[str, Any] | None = None,
    audit_block: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Complete one reserved round exactly once with product or audit evidence."""

    workspace = _workspace_root(root)
    flow_id = _identifier(flow_id, "flow_id")
    round_id = _identifier(round_id, "round_id")
    if outcome not in ROUND_OUTCOMES:
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "outcome")
    if (review_reference is None) == (audit_block is None):
        raise BoundedClosureError("WB_POST_EXECUTION_EVIDENCE_INVALID")
    if outcome in {"accepted", "findings"} and review_reference is None:
        raise BoundedClosureError("WB_POST_EXECUTION_EVIDENCE_INVALID")
    if review_reference is not None:
        evidence = {"review_reference": _stored_review_reference(workspace, review_reference)}
    else:
        if not isinstance(audit_block, Mapping) or not audit_block:
            raise BoundedClosureError("WB_POST_EXECUTION_EVIDENCE_INVALID")
        evidence = {"audit_block": dict(audit_block)}
    requested_completion = {"outcome": outcome, **evidence}
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        record = _find_round(ledger, flow_id, round_id)
        if record["state"] == "completed":
            if record.get("completion") != requested_completion:
                raise BoundedClosureError("WB_POST_EXECUTION_JUDGMENT_COLLISION")
            return _public_round(record)
        if record["state"] not in {"reserved", "prepared"}:
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        if review_reference is not None and record["state"] != "prepared":
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_BINDING_INVALID")
        if review_reference is not None and review_reference["review_id"] != record["review_id"]:
            raise BoundedClosureError("WB_POST_EXECUTION_EVIDENCE_INVALID")
        record.update(
            state="completed",
            outcome=outcome,
            completion=requested_completion,
            completed_at=_utc_now(),
        )
        flow = ledger["flows"][flow_id]
        completed_count = sum(item["state"] == "completed" for item in flow["rounds"])
        flow["finalization_required"] = outcome == "accepted" or completed_count >= ROUND_LIMIT
        record["finalization_required"] = flow["finalization_required"]
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)
        return _public_round(record)


def complete_published_review_round(
    root: Path,
    *,
    review_id: str,
    target_identity: Mapping[str, Any],
    outcome: str,
    review_reference: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Bind stored integrated-review authority to its reserved round.

    Legacy workspaces have no bounded policy and therefore return ``None``.
    """

    workspace = root.expanduser().resolve()
    if not _metadata_path(workspace).is_file():
        return None
    metadata = _load_metadata(workspace)
    if _policy(metadata, required=False) is None:
        return None
    review_id = _identifier(review_id, "review_id")
    target = _target_identity(target_identity)
    with _locked(workspace):
        ledger = _load_ledger(workspace)
        matches = [
            record
            for flow in ledger["flows"].values()
            for record in flow.get("rounds", [])
            if record.get("review_id") == review_id
            and record.get("target_identity") == target
        ]
        if len(matches) != 1:
            raise BoundedClosureError("WB_POST_EXECUTION_ROUND_REQUIRED")
        flow_id = str(matches[0]["flow_id"])
        round_id = str(matches[0]["round_id"])
    return complete_review_round(
        workspace,
        flow_id=flow_id,
        round_id=round_id,
        outcome=outcome,
        review_reference=review_reference,
    )


def review_round_status(root: Path, *, flow_id: str) -> dict[str, Any]:
    workspace = _workspace_root(root)
    flow_id = _identifier(flow_id, "flow_id")
    _policy(_load_metadata(workspace), required=True)
    with _locked(workspace):
        ledger = _load_ledger(workspace)
        flow = ledger["flows"].get(flow_id)
        if not isinstance(flow, Mapping):
            return {
                "flow_id": flow_id,
                "execution_complete": False,
                "reserved_rounds": 0,
                "completed_rounds": 0,
                "latest_round": None,
                "finalization_required": False,
            }
        rounds = flow["rounds"]
        return {
            "flow_id": flow_id,
            "execution_complete": bool(flow["execution_complete"]),
            "reserved_rounds": len(rounds),
            "completed_rounds": sum(item["state"] == "completed" for item in rounds),
            "latest_round": _public_round(rounds[-1]) if rounds else None,
            "finalization_required": bool(flow.get("finalization_required")),
        }


def _portable_source_baselines(
    values: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], list[tuple[Path, dict[str, str]]]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "source_baselines")
    portable: list[dict[str, str]] = []
    local: list[tuple[Path, dict[str, str]]] = []
    repository_ids: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {
            "repository_id", "project_root", "commit", "tree"
        }:
            raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "source_baselines")
        repository_id = _identifier(value.get("repository_id"), "source_baselines.repository_id")
        commit = value.get("commit")
        tree = value.get("tree")
        project_root = value.get("project_root")
        if (
            repository_id in repository_ids
            or not isinstance(commit, str)
            or not GIT_OID_RE.fullmatch(commit)
            or not isinstance(tree, str)
            or not GIT_OID_RE.fullmatch(tree)
            or not isinstance(project_root, str)
            or not project_root
        ):
            raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "source_baselines")
        repository_ids.add(repository_id)
        identity = {"repository_id": repository_id, "commit": commit, "tree": tree}
        portable.append(identity)
        local.append((Path(project_root).expanduser().resolve(), identity))
    portable.sort(key=lambda item: item["repository_id"])
    local.sort(key=lambda item: item[1]["repository_id"])
    return portable, local


def _knowledge_return(value: Mapping[str, Any]) -> dict[str, str | None]:
    if not isinstance(value, Mapping) or set(value) != {"status", "evidence_ref"}:
        raise BoundedClosureError("WB_POST_EXECUTION_KNOWLEDGE_RETURN_INVALID")
    status = value.get("status")
    evidence_ref = value.get("evidence_ref")
    if status == "completed":
        evidence_ref = _identifier(evidence_ref, "knowledge_return.evidence_ref")
    elif status == "not-needed":
        if evidence_ref is not None:
            raise BoundedClosureError("WB_POST_EXECUTION_KNOWLEDGE_RETURN_INVALID")
    else:
        raise BoundedClosureError("WB_POST_EXECUTION_KNOWLEDGE_RETURN_INVALID")
    return {"status": str(status), "evidence_ref": evidence_ref}


def _residual_spec_identity(
    workspace: Path, path: Path, residual_spec_id: str
) -> dict[str, str]:
    active_root = (workspace / ".work-bundle/orchestration/spec/active").resolve()
    candidate = path.expanduser().resolve(strict=False)
    if candidate.is_symlink() or not candidate.is_file():
        raise BoundedClosureError("WB_POST_EXECUTION_RESIDUAL_SPEC_INVALID")
    try:
        content = candidate.read_bytes()
        text = content.decode("utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError("front matter")
        raw, body = text[4:].split("\n---\n", 1)
        front_matter = yaml.safe_load(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as error:
        raise BoundedClosureError("WB_POST_EXECUTION_RESIDUAL_SPEC_INVALID") from error
    if (
        not isinstance(front_matter, Mapping)
        or front_matter.get("id") != residual_spec_id
        or front_matter.get("status") != "active"
        or not body.strip()
    ):
        raise BoundedClosureError("WB_POST_EXECUTION_RESIDUAL_SPEC_INVALID")
    target = candidate if candidate.is_relative_to(active_root) else active_root / candidate.name
    if target.exists():
        if target.is_symlink() or not target.is_file() or target.read_bytes() != content:
            raise BoundedClosureError("WB_POST_EXECUTION_RESIDUAL_SPEC_COLLISION")
    else:
        _atomic_write(target, content)
    return {
        "id": residual_spec_id,
        "path": target.relative_to(workspace).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _validate_source_baselines(
    local: Sequence[tuple[Path, Mapping[str, str]]],
) -> None:
    for root, identity in local:
        if not root.is_dir():
            raise BoundedClosureError(
                "WB_POST_EXECUTION_SOURCE_BASELINE_INVALID", identity["repository_id"]
            )
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode != 0:
            raise BoundedClosureError(
                "WB_POST_EXECUTION_SOURCE_BASELINE_INVALID", identity["repository_id"]
            )
        if status.stdout.strip():
            raise BoundedClosureError(
                "WB_POST_EXECUTION_SOURCE_BASELINE_DIRTY", identity["repository_id"]
            )
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        tree = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if (
            head.returncode != 0
            or tree.returncode != 0
            or head.stdout.strip() != identity["commit"]
            or tree.stdout.strip() != identity["tree"]
        ):
            raise BoundedClosureError(
                "WB_POST_EXECUTION_SOURCE_BASELINE_CONFLICT", identity["repository_id"]
            )


def _public_finalization(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in (
            "flow_id", "request_id", "state", "outcome", "authority",
            "blocker_id", "residual_spec", "origin_spec_id", "origin_plan_id",
            "source_baselines", "knowledge_return", "administrative",
        )
        if key in record
    }


def _update_finalization(
    workspace: Path, flow_id: str, **updates: object
) -> dict[str, Any]:
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        flow = ledger["flows"].get(flow_id)
        if not isinstance(flow, dict) or not isinstance(flow.get("finalization"), dict):
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_STATE_INVALID")
        flow["finalization"].update(updates)
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)
        return dict(flow["finalization"])


def _record_finalization_incomplete(
    workspace: Path, flow_id: str, stage: str, detail: str
) -> None:
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        flow = ledger["flows"].get(flow_id)
        if not isinstance(flow, dict) or not isinstance(flow.get("finalization"), dict):
            return
        finalization = flow["finalization"]
        administrative = finalization.setdefault("administrative", {})
        administrative[stage] = "incomplete"
        finalization["state"] = "administrative_incomplete"
        finalization["incomplete"] = {"stage": stage, "detail": detail}
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)


def finalize_with_blockers(
    root: Path,
    *,
    flow_id: str,
    request_id: str,
    blocker_id: str,
    residual_spec_id: str,
    residual_spec: Path,
    origin_spec_id: str,
    origin_plan_id: str,
    source_baselines: Sequence[Mapping[str, Any]],
    knowledge_return: Mapping[str, Any],
    operator_authorized: bool = False,
) -> dict[str, Any]:
    """Administratively close one bounded flow while preserving unresolved truth."""

    workspace = _workspace_root(root)
    flow_id = _identifier(flow_id, "flow_id")
    request_id = _identifier(request_id, "request_id")
    blocker_id = _identifier(blocker_id, "blocker_id")
    residual_spec_id = _identifier(residual_spec_id, "residual_spec_id")
    origin_spec_id = _identifier(origin_spec_id, "origin_spec_id")
    origin_plan_id = _identifier(origin_plan_id, "origin_plan_id")
    if origin_plan_id != flow_id or not isinstance(operator_authorized, bool):
        raise BoundedClosureError("WB_POST_EXECUTION_INPUT_INVALID", "origin_plan_id")
    portable_baselines, local_baselines = _portable_source_baselines(source_baselines)
    portable_request = {
        "flow_id": flow_id,
        "request_id": request_id,
        "blocker_id": blocker_id,
        "residual_spec_id": residual_spec_id,
        "origin_spec_id": origin_spec_id,
        "origin_plan_id": origin_plan_id,
        "source_baselines": portable_baselines,
        "authority": "operator" if operator_authorized else "exhausted-rounds",
    }

    # Persist the closed-to-reconciliation state before validating any supplied
    # administrative input.  Retry may repair those inputs, but may not reopen
    # product review or executor work.
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        flow = ledger["flows"].get(flow_id)
        if flow is None:
            flow = {
                "flow_id": flow_id,
                "execution_complete": True,
                "terminal_attempts": [],
                "known_missing_evidence": [],
                "finalization_required": False,
                "rounds": [],
            }
            ledger["flows"][flow_id] = flow
        if not isinstance(flow, dict):
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_STATE_INVALID")
        if not flow.get("finalization_required") and not operator_authorized:
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_NOT_AUTHORIZED")
        existing = flow.get("finalization")
        if isinstance(existing, Mapping):
            existing_request = {key: existing.get(key) for key in portable_request}
            if existing_request != portable_request:
                raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_COLLISION")
            if existing.get("state") == "closed":
                return _public_finalization(existing)
        elif existing is not None:
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_STATE_INVALID")
        else:
            flow["finalization"] = {
                **portable_request,
                "state": "required",
                "outcome": None,
                "administrative": {},
                "required_at": _utc_now(),
            }
        flow["finalization_required"] = True
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)

    residual = _residual_spec_identity(workspace, residual_spec, residual_spec_id)
    _validate_source_baselines(local_baselines)
    _update_finalization(
        workspace,
        flow_id,
        state="validated",
        residual_spec=residual,
        incomplete=None,
    )

    blocker = {
        "id": blocker_id,
        "status": "active",
        "origin_plan": origin_plan_id,
        "origin_spec": origin_spec_id,
        "specification": residual["path"],
        "source_baselines": portable_baselines,
    }
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        control = _policy(metadata, required=True)
        assert isinstance(control, dict)
        blockers = [dict(item) for item in _control_list(control, "blockers")]
        existing_blocker = next((item for item in blockers if item.get("id") == blocker_id), None)
        if existing_blocker is not None and existing_blocker != blocker:
            raise BoundedClosureError("WB_POST_EXECUTION_BLOCKER_COLLISION", blocker_id)
        if existing_blocker is None:
            blockers.append(blocker)
            control["blockers"] = blockers
            _atomic_write(
                _metadata_path(workspace),
                yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).encode("utf-8"),
            )
    _update_finalization(workspace, flow_id, state="blocker_recorded")
    try:
        knowledge = _knowledge_return(knowledge_return)
    except BoundedClosureError as error:
        _record_finalization_incomplete(workspace, flow_id, "knowledge_return", str(error))
        raise
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        _policy(metadata, required=True)
        ledger = _load_ledger(workspace)
        flow = ledger["flows"].get(flow_id)
        if not isinstance(flow, dict) or not isinstance(flow.get("finalization"), dict):
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_STATE_INVALID")
        finalization = flow["finalization"]
        existing_knowledge = finalization.get("knowledge_return")
        if existing_knowledge is not None and existing_knowledge != knowledge:
            raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_COLLISION")
        finalization.update(
            state="knowledge_finalized", knowledge_return=knowledge, incomplete=None
        )
        _write_ledger(workspace, ledger)
        _write_metadata_projection(workspace, metadata, ledger)

    import argparse
    from plans import (
        archive_plan_for_forced_finalization,
        release_plan_bindings_for_forced_finalization,
    )
    from specs import archive_spec_for_forced_finalization

    args = argparse.Namespace(project_root=str(workspace), workspace_root=str(workspace))
    try:
        archive_spec_for_forced_finalization(args, origin_spec_id)
        _update_finalization(
            workspace, flow_id, administrative={"origin_spec": "completed"}
        )
        archive_plan_for_forced_finalization(args, origin_plan_id)
        _update_finalization(
            workspace,
            flow_id,
            administrative={"origin_spec": "completed", "origin_plan": "completed"},
        )
    except (OSError, SystemExit) as error:
        _record_finalization_incomplete(workspace, flow_id, "archive", str(error))
        raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_INCOMPLETE", str(error)) from error

    try:
        binding_result = release_plan_bindings_for_forced_finalization(workspace, origin_plan_id)
    except (OSError, SystemExit) as error:
        _record_finalization_incomplete(workspace, flow_id, "ownership_release", str(error))
        raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_INCOMPLETE", str(error)) from error
    if binding_result["incomplete"]:
        detail = json.dumps(binding_result["incomplete"], sort_keys=True)
        _record_finalization_incomplete(workspace, flow_id, "ownership_release", detail)
        raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_INCOMPLETE", detail)
    administrative = {
        "origin_spec": "completed",
        "origin_plan": "completed",
        "ownership_release": "completed",
    }
    _update_finalization(workspace, flow_id, administrative=administrative)

    closure = {
        "flow_id": flow_id,
        "outcome": "closed_with_blockers",
        "blocker_id": blocker_id,
        "residual_spec": residual,
        "source_baselines": portable_baselines,
        "knowledge_return": knowledge,
    }
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        control = _policy(metadata, required=True)
        assert isinstance(control, dict)
        closures = [dict(item) for item in _control_list(control, "closed_flows")]
        existing_closure = next((item for item in closures if item.get("flow_id") == flow_id), None)
        if existing_closure is not None:
            comparable = {key: existing_closure.get(key) for key in closure}
            if comparable != closure:
                raise BoundedClosureError("WB_POST_EXECUTION_FINALIZATION_COLLISION")
        else:
            closures.append({**closure, "closed_at": _utc_now()})
            control["closed_flows"] = closures
            _atomic_write(
                _metadata_path(workspace),
                yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).encode("utf-8"),
            )
    record = _update_finalization(
        workspace,
        flow_id,
        state="closed",
        outcome="closed_with_blockers",
        administrative=administrative,
        incomplete=None,
        closed_at=_utc_now(),
    )
    return _public_finalization(record)


CONTROLLER_COMMANDS = frozenset({
    "begin-review-round",
    "complete-review-round",
    "review-round-status",
    "finalize-with-blockers",
})


def _json_argument(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        import argparse
        raise argparse.ArgumentTypeError(f"invalid controller JSON: {error.msg}") from error


def _controller_workspace(args: Any) -> Path:
    raw = getattr(args, "workspace_root", None) or getattr(args, "project_root", None)
    start = Path(raw).expanduser() if raw else Path.cwd()
    workspace = resolve_working_workspace(
        start, workspace_id=getattr(args, "workspace_id", None)
    )
    if workspace is None:
        raise BoundedClosureError("WB_POST_EXECUTION_WORKSPACE_INVALID")
    return workspace


def cmd_begin_review_round(args: Any) -> None:
    result = begin_review_round(
        _controller_workspace(args),
        flow_id=args.flow_id,
        request_id=args.request_id,
        review_id=args.review_id,
        target_identity=args.target_identity,
        executor_attempts=args.executor_attempts,
        known_missing_evidence=args.known_missing_evidence,
    )
    print(json.dumps(result, sort_keys=True))


def cmd_complete_review_round(args: Any) -> None:
    result = complete_review_round(
        _controller_workspace(args),
        flow_id=args.flow_id,
        round_id=args.round_id,
        outcome=args.outcome,
        review_reference=args.review_reference,
        audit_block=args.audit_block,
    )
    print(json.dumps(result, sort_keys=True))


def cmd_review_round_status(args: Any) -> None:
    print(json.dumps(
        review_round_status(_controller_workspace(args), flow_id=args.flow_id),
        sort_keys=True,
    ))


def cmd_finalize_with_blockers(args: Any) -> None:
    result = finalize_with_blockers(
        _controller_workspace(args),
        flow_id=args.flow_id,
        request_id=args.request_id,
        blocker_id=args.blocker_id,
        residual_spec_id=args.residual_spec_id,
        residual_spec=Path(args.residual_spec),
        origin_spec_id=args.origin_spec_id,
        origin_plan_id=args.origin_plan_id,
        source_baselines=args.source_baselines,
        knowledge_return=args.knowledge_return,
        operator_authorized=args.operator_authorized,
    )
    print(json.dumps(result, sort_keys=True))


def configure_begin_review_round_parser(parser: Any) -> None:
    parser.add_argument("--flow-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--target-identity", required=True, type=_json_argument)
    parser.add_argument("--executor-attempts", required=True, type=_json_argument)
    parser.add_argument("--known-missing-evidence", default=[], type=_json_argument)
    parser.set_defaults(func=cmd_begin_review_round)


def configure_complete_review_round_parser(parser: Any) -> None:
    parser.add_argument("--flow-id", required=True)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--outcome", required=True, choices=sorted(ROUND_OUTCOMES))
    parser.add_argument("--review-reference", type=_json_argument)
    parser.add_argument("--audit-block", type=_json_argument)
    parser.set_defaults(func=cmd_complete_review_round)


def configure_review_round_status_parser(parser: Any) -> None:
    parser.add_argument("--flow-id", required=True)
    parser.set_defaults(func=cmd_review_round_status)


def configure_finalize_with_blockers_parser(parser: Any) -> None:
    parser.add_argument("--flow-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--blocker-id", required=True)
    parser.add_argument("--residual-spec-id", required=True)
    parser.add_argument("--residual-spec", required=True)
    parser.add_argument("--origin-spec-id", required=True)
    parser.add_argument("--origin-plan-id", required=True)
    parser.add_argument("--source-baselines", required=True, type=_json_argument)
    parser.add_argument("--knowledge-return", required=True, type=_json_argument)
    parser.add_argument("--operator-authorized", action="store_true")
    parser.set_defaults(func=cmd_finalize_with_blockers)


def migrate_bounded_review_policy(root: Path) -> bool:
    """Rename only the current metadata policy key; history is never inspected."""

    workspace = _workspace_root(root)
    with _locked(workspace):
        metadata = _load_metadata(workspace)
        control = metadata.get("orchestration_control")
        if not isinstance(control, dict) or "review_revision_limit" not in control:
            return False
        if "post_execution_review_round_limit" in control:
            raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID")
        control["post_execution_review_round_limit"] = control.pop("review_revision_limit")
        if control["post_execution_review_round_limit"] != ROUND_LIMIT:
            raise BoundedClosureError("WB_POST_EXECUTION_POLICY_INVALID")
        _atomic_write(
            _metadata_path(workspace),
            yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).encode("utf-8"),
        )
        return True
