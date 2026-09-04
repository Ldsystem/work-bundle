"""Append-only, privacy-safe stage telemetry for WorkBundle orchestration."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


EVENT_TYPES = frozenset(
    {
        "stage_started",
        "stage_completed",
        "finding_recorded",
        "work_returned",
        "reslice_recorded",
        "suite_started",
        "suite_reused",
        "suite_completed",
        "evidence_invalidated",
        "reviewer_mutation_denied",
        "control_plane_repaired",
        "binding_retained",
        "binding_released",
    }
)
ENFORCEMENT_MODES = frozenset({"bootstrap_policy", "native"})
FINDING_CLASSES = frozenset(
    {
        "specification_gap",
        "decomposition_gap",
        "allocation_gap",
        "implementation_defect",
        "validation_oracle_defect",
        "environment_failure",
        "advisory_enhancement",
    }
)
JOIN_ID_FIELDS = frozenset(
    {"specification_id", "plan_id", "phase_id", "task_id", "review_id", "evaluation_id"}
)
IDENTITY_FIELDS = frozenset({"product_tree", "artifact_digest", "mutation_epoch"})
CLOCK_FIELDS = frozenset({"wall_ms", "active_ms", "billed_ms"})
EVENT_FIELDS = frozenset(
    {
        "event_id",
        "timestamp",
        "process_id",
        "stage",
        "attempt_id",
        "event_type",
        "enforcement_mode",
        "join_ids",
        "clocks",
        "finding_class",
        "return_reason",
        "owner",
        "identity",
        "privacy",
    }
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_OID_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_SENSITIVE_KEY_RE = re.compile(
    r"(?:prompt|secret|credential|password|token|private.?key|full.?diff|raw.?(?:response|trace|evidence)|"
    r"private.?user.?content|content|path|cwd)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?:^|\s)(?:/Users/|/home/|~/|[A-Za-z]:\\|\.\./|file://|diff --git|@@|Bearer\s+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)|(?:secret|credential|password|token|private.?key|api.?key)",
    re.IGNORECASE,
)


class StageEventError(ValueError):
    """Stable, non-disclosing API-004 validation failure."""


@dataclass(frozen=True)
class StageEventV1:
    event_id: str
    timestamp: str
    process_id: str
    stage: str
    attempt_id: str
    event_type: str
    enforcement_mode: str
    join_ids: dict[str, str | None]
    clocks: dict[str, int | None]
    finding_class: str | None
    return_reason: str | None
    owner: str | None
    identity: dict[str, str | int | None]
    privacy: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _fail(code: str) -> None:
    raise StageEventError(code)


def _is_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not _TIME_RE.fullmatch(value):
        _fail("WB_STAGE_EVENT_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("WB_STAGE_EVENT_TIMESTAMP_INVALID")
    if parsed.utcoffset() is None:
        _fail("WB_STAGE_EVENT_TIMESTAMP_INVALID")
    return parsed


def _scan_for_sensitive_content(value: object, *, key: str | None = None) -> None:
    if key is not None and _SENSITIVE_KEY_RE.search(key):
        _fail("WB_STAGE_EVENT_PRIVACY_INVALID")
    if isinstance(value, Mapping):
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                _fail("WB_STAGE_EVENT_PRIVACY_INVALID")
            _scan_for_sensitive_content(nested_value, key=nested_key)
    elif isinstance(value, list):
        for nested_value in value:
            _scan_for_sensitive_content(nested_value)
    elif isinstance(value, str) and _SENSITIVE_VALUE_RE.search(value):
        _fail("WB_STAGE_EVENT_PRIVACY_INVALID")


def _validate_exact_fields(value: object, expected: frozenset[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        _fail(code)
    return value


def validate_stage_event(payload: Mapping[str, object]) -> StageEventV1:
    """Validate one closed API-004 event without retaining caller-owned containers."""

    _scan_for_sensitive_content(payload)
    value = _validate_exact_fields(payload, EVENT_FIELDS, "WB_STAGE_EVENT_FIELDS_INVALID")
    for field in ("event_id", "process_id", "attempt_id"):
        if not _is_id(value[field]):
            _fail("WB_STAGE_EVENT_ID_INVALID")
    if not isinstance(value["stage"], str) or not value["stage"].strip():
        _fail("WB_STAGE_EVENT_OPERATIONAL_VALUE_INVALID")
    _parse_timestamp(value["timestamp"])
    if not isinstance(value["event_type"], str) or value["event_type"] not in EVENT_TYPES:
        _fail("WB_STAGE_EVENT_TYPE_INVALID")
    if not isinstance(value["enforcement_mode"], str) or value["enforcement_mode"] not in ENFORCEMENT_MODES:
        _fail("WB_STAGE_EVENT_MODE_INVALID")

    join_ids = _validate_exact_fields(value["join_ids"], JOIN_ID_FIELDS, "WB_STAGE_EVENT_JOIN_IDS_INVALID")
    if any(item is not None and not _is_id(item) for item in join_ids.values()):
        _fail("WB_STAGE_EVENT_JOIN_IDS_INVALID")

    clocks = _validate_exact_fields(value["clocks"], CLOCK_FIELDS, "WB_STAGE_EVENT_CLOCK_INVALID")
    if not _is_nonnegative_int(clocks["wall_ms"]) or not _is_nonnegative_int(clocks["active_ms"]):
        _fail("WB_STAGE_EVENT_CLOCK_INVALID")
    if clocks["billed_ms"] is not None and not _is_nonnegative_int(clocks["billed_ms"]):
        _fail("WB_STAGE_EVENT_CLOCK_INVALID")
    if clocks["active_ms"] > clocks["wall_ms"]:
        _fail("WB_STAGE_EVENT_CLOCK_ORDER_INVALID")

    finding_class = value["finding_class"]
    if finding_class is not None and (
        not isinstance(finding_class, str) or finding_class not in FINDING_CLASSES
    ):
        _fail("WB_STAGE_EVENT_FINDING_CLASS_INVALID")
    for field in ("return_reason", "owner"):
        if value[field] is not None and (
            not isinstance(value[field], str) or not value[field].strip()
        ):
            _fail("WB_STAGE_EVENT_OPERATIONAL_VALUE_INVALID")

    identity = _validate_exact_fields(value["identity"], IDENTITY_FIELDS, "WB_STAGE_EVENT_IDENTITY_INVALID")
    if identity["product_tree"] is not None and (
        not isinstance(identity["product_tree"], str) or not _OID_RE.fullmatch(identity["product_tree"])
    ):
        _fail("WB_STAGE_EVENT_IDENTITY_INVALID")
    if identity["artifact_digest"] is not None and (
        not isinstance(identity["artifact_digest"], str) or not _SHA_RE.fullmatch(identity["artifact_digest"])
    ):
        _fail("WB_STAGE_EVENT_IDENTITY_INVALID")
    if identity["mutation_epoch"] is not None and not _is_nonnegative_int(identity["mutation_epoch"]):
        _fail("WB_STAGE_EVENT_IDENTITY_INVALID")
    if value["privacy"] != "operational_metadata_only":
        _fail("WB_STAGE_EVENT_PRIVACY_INVALID")

    return StageEventV1(
        event_id=str(value["event_id"]),
        timestamp=str(value["timestamp"]),
        process_id=str(value["process_id"]),
        stage=str(value["stage"]),
        attempt_id=str(value["attempt_id"]),
        event_type=str(value["event_type"]),
        enforcement_mode=str(value["enforcement_mode"]),
        join_ids={field: join_ids[field] for field in sorted(JOIN_ID_FIELDS)},
        clocks={field: clocks[field] for field in sorted(CLOCK_FIELDS)},
        finding_class=finding_class if isinstance(finding_class, str) else None,
        return_reason=value["return_reason"] if isinstance(value["return_reason"], str) else None,
        owner=value["owner"] if isinstance(value["owner"], str) else None,
        identity={field: identity[field] for field in sorted(IDENTITY_FIELDS)},
        privacy="operational_metadata_only",
    )


def redact_event_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Fail closed on non-operational content and return the closed public record."""

    return validate_stage_event(payload).to_dict()


def _event_store_path(workspace_root: Path, *, create_parent: bool) -> Path:
    root = workspace_root.resolve(strict=True)
    path = root / ".work-bundle" / "runtime" / "stage-events" / "events-v1.jsonl"
    current = root
    for component in path.relative_to(root).parts[:-1]:
        current = current / component
        if current.is_symlink():
            _fail("WB_STAGE_EVENT_STORE_BOUNDARY_INVALID")
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.exists() and path.parent.resolve() != path.parent:
        _fail("WB_STAGE_EVENT_STORE_BOUNDARY_INVALID")
    if path.is_symlink():
        _fail("WB_STAGE_EVENT_STORE_BOUNDARY_INVALID")
    return path


def _load_locked(handle) -> list[StageEventV1]:
    handle.seek(0)
    raw = handle.read()
    if not raw:
        return []
    try:
        text = raw.decode("utf-8")
        if not text.endswith("\n"):
            _fail("WB_STAGE_EVENT_STORE_INVALID")
        records = [validate_stage_event(json.loads(line)) for line in text.splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError, StageEventError, TypeError):
        _fail("WB_STAGE_EVENT_STORE_INVALID")
    if len({record.event_id for record in records}) != len(records):
        _fail("WB_STAGE_EVENT_STORE_INVALID")
    previous_by_attempt: dict[tuple[str, str], tuple[datetime, int]] = {}
    for record in records:
        key = (record.process_id, record.attempt_id)
        current = (_parse_timestamp(record.timestamp), int(record.clocks["wall_ms"]))
        previous = previous_by_attempt.get(key)
        if previous is not None and (current[0] < previous[0] or current[1] < previous[1]):
            _fail("WB_STAGE_EVENT_STORE_INVALID")
        previous_by_attempt[key] = current
    return records


def append_stage_event(workspace_root: Path, payload: Mapping[str, object]) -> StageEventV1:
    """Append one event atomically after validating all existing history."""

    record = validate_stage_event(payload)
    path = _event_store_path(Path(workspace_root), create_parent=True)
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        _fail("WB_STAGE_EVENT_STORE_BOUNDARY_INVALID")
    with os.fdopen(descriptor, "r+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        existing = _load_locked(handle)
        if any(item.event_id == record.event_id for item in existing):
            _fail("WB_STAGE_EVENT_DUPLICATE_ID")
        same_attempt = [
            item
            for item in existing
            if item.process_id == record.process_id and item.attempt_id == record.attempt_id
        ]
        if same_attempt:
            previous = same_attempt[-1]
            if _parse_timestamp(record.timestamp) < _parse_timestamp(previous.timestamp):
                _fail("WB_STAGE_EVENT_TIMESTAMP_ORDER_INVALID")
            if int(record.clocks["wall_ms"]) < int(previous.clocks["wall_ms"]):
                _fail("WB_STAGE_EVENT_WALL_CLOCK_ORDER_INVALID")
        encoded = (json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        handle.seek(0, os.SEEK_END)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return record


def query_stage_events(
    workspace_root: Path,
    *,
    process_id: str | None = None,
    attempt_id: str | None = None,
    event_type: str | None = None,
) -> list[StageEventV1]:
    """Read validated events in append order with bounded operational filters."""

    for value in (process_id, attempt_id):
        if value is not None and not _is_id(value):
            _fail("WB_STAGE_EVENT_QUERY_INVALID")
    if event_type is not None and event_type not in EVENT_TYPES:
        _fail("WB_STAGE_EVENT_QUERY_INVALID")
    path = _event_store_path(Path(workspace_root), create_parent=False)
    if not path.exists():
        return []
    with path.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        records = _load_locked(handle)
    return [
        record
        for record in records
        if (process_id is None or record.process_id == process_id)
        and (attempt_id is None or record.attempt_id == attempt_id)
        and (event_type is None or record.event_type == event_type)
    ]


def export_stage_events(workspace_root: Path) -> str:
    """Return the validated JSONL stream byte-for-byte without mutating it."""

    path = _event_store_path(Path(workspace_root), create_parent=False)
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        raw = handle.read()
        handle.seek(0)
        _load_locked(handle)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("WB_STAGE_EVENT_STORE_INVALID")


def cmd_stage_events(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"wb.py {command}")
    parser.add_argument("--workspace-root", required=True, type=Path)
    if command == "stage-event-append":
        parser.add_argument("--event-file", required=True, type=Path)
    elif command == "stage-event-query":
        parser.add_argument("--process-id")
        parser.add_argument("--attempt-id")
        parser.add_argument("--event-type")
    args = parser.parse_args(argv)
    try:
        if command == "stage-event-append":
            payload = json.loads(args.event_file.read_text(encoding="utf-8"))
            print(json.dumps(append_stage_event(args.workspace_root, payload).to_dict(), sort_keys=True))
        elif command == "stage-event-query":
            records = query_stage_events(
                args.workspace_root,
                process_id=args.process_id,
                attempt_id=args.attempt_id,
                event_type=args.event_type,
            )
            print(json.dumps([record.to_dict() for record in records], sort_keys=True))
        elif command == "stage-event-export":
            sys.stdout.write(export_stage_events(args.workspace_root))
        else:
            _fail("WB_STAGE_EVENT_COMMAND_INVALID")
    except (OSError, TypeError, json.JSONDecodeError, StageEventError):
        print(json.dumps({"status": "blocked", "failure_code": "WB_STAGE_EVENT_OPERATION_FAILED"}))
        return 1
    return 0
