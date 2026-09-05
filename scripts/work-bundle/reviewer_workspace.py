from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import uuid


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SCOPES = frozenset({"source", "control"})
NETWORK_STATES = frozenset({"denied"})
VALIDATOR_KINDS = frozenset({"json", "sha256", "command"})
TERMINAL_VERDICTS = frozenset({"accepted", "repair", "blocked"})


class ReviewerWorkspaceError(RuntimeError):
    def __init__(self, code: str, result: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.result = result or {}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _sha256_bytes(encoded)


def _safe_id(value: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise ReviewerWorkspaceError("WB_REVIEW_ID_INVALID")
    return value


def _split_locator(locator: object) -> tuple[str, Path]:
    text = str(locator or "")
    scope, separator, raw_path = text.partition(":")
    if not separator or scope not in SCOPES:
        if scope == "host":
            raise ReviewerWorkspaceError(
                "WB_REVIEW_HOST_CONFIG_READ_DENIED", {"classification": "denied", "scope": "host"}
            )
        raise ReviewerWorkspaceError("WB_REVIEW_LOCATOR_INVALID", {"classification": "denied"})
    relative = Path(raw_path)
    if not raw_path or relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        raise ReviewerWorkspaceError("WB_REVIEW_PATH_ESCAPE_DENIED", {"classification": "denied"})
    return scope, relative


def _inside(root: Path, candidate: Path) -> bool:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve(strict=False)
    return resolved_candidate == resolved_root or resolved_root in resolved_candidate.parents


def _normalized_roots(values: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for value in values:
        root = Path(value).expanduser().resolve()
        if not root.exists() or root.is_symlink():
            raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_ROOT_INVALID")
        roots.append(root)
    if not roots:
        raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_ROOTS_REQUIRED")
    return roots


def _source_path(
    source_root: Path,
    control_root: Path,
    protected_roots: list[Path],
    locator: object,
) -> tuple[str, Path, Path]:
    scope, relative = _split_locator(locator)
    root = source_root if scope == "source" else control_root
    root = root.expanduser().resolve()
    candidate = root / relative
    if not _inside(root, candidate):
        raise ReviewerWorkspaceError("WB_REVIEW_PATH_ESCAPE_DENIED", {"classification": "denied"})
    if any(_inside(protected, candidate) for protected in protected_roots):
        raise ReviewerWorkspaceError(
            "WB_REVIEW_PROTECTED_READ_DENIED", {"classification": "denied", "scope": scope}
        )
    if not candidate.is_file() or candidate.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_DIRECT_EVIDENCE_MISSING", {"locator": f"{scope}:{relative.as_posix()}"})
    return scope, relative, candidate


def build_direct_evidence_packet(
    *,
    source_root: Path,
    control_root: Path,
    protected_roots: list[Path],
    artifacts: list[str],
    search_roots: list[str],
    validators: list[dict[str, object]],
    sentinels: list[str],
    network_state: str,
) -> dict[str, object]:
    """Copy only named direct evidence into a location-free packet.

    Origin roots are used while compiling the packet and are deliberately not
    serialized. Review operations therefore have no path capability back to
    source, control-plane, registry, credentials, or host configuration.
    """
    if network_state not in NETWORK_STATES:
        raise ReviewerWorkspaceError("WB_REVIEW_NETWORK_STATE_REQUIRED")
    source_root = source_root.expanduser().resolve()
    control_root = control_root.expanduser().resolve()
    protected = _normalized_roots(protected_roots)
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for locator in artifacts:
        scope, relative, candidate = _source_path(source_root, control_root, protected, locator)
        normalized = f"{scope}:{relative.as_posix()}"
        if normalized in seen:
            raise ReviewerWorkspaceError("WB_REVIEW_ARTIFACT_DUPLICATE", {"locator": normalized})
        seen.add(normalized)
        content = candidate.read_bytes()
        records.append(
            {
                "locator": normalized,
                "sha256": _sha256_bytes(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
    normalized_search: list[str] = []
    for locator in search_roots:
        scope, relative = _split_locator(locator)
        root = source_root if scope == "source" else control_root
        candidate = root / relative
        if not _inside(root, candidate) or not candidate.is_dir() or candidate.is_symlink():
            raise ReviewerWorkspaceError("WB_REVIEW_SEARCH_ROOT_INVALID", {"locator": locator})
        if any(_inside(item, candidate) for item in protected):
            raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_READ_DENIED", {"classification": "denied"})
        normalized_search.append(f"{scope}:{relative.as_posix()}")
    normalized_validators: list[dict[str, object]] = []
    validator_ids: set[str] = set()
    for raw in validators:
        validator_id = _safe_id(str(raw.get("validator_id") or ""))
        kind = str(raw.get("kind") or "")
        locator = str(raw.get("artifact") or "")
        argv = raw.get("argv")
        command_valid = kind == "command" and isinstance(argv, list) and bool(argv) and all(
            isinstance(item, str) and item for item in argv
        )
        artifact_valid = kind in {"json", "sha256"} and locator in seen
        if validator_id in validator_ids or kind not in VALIDATOR_KINDS or not (command_valid or artifact_valid):
            raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_INVALID", {"validator_id": validator_id})
        validator_ids.add(validator_id)
        normalized = {"validator_id": validator_id, "kind": kind}
        if command_valid:
            normalized["argv"] = list(argv)
        else:
            normalized["artifact"] = locator
        normalized_validators.append(normalized)
    sentinel_records: list[dict[str, str]] = []
    for locator in sentinels:
        scope, relative, candidate = _source_path(source_root, control_root, protected, locator)
        sentinel_records.append(
            {"locator": f"{scope}:{relative.as_posix()}", "sha256": _sha256_bytes(candidate.read_bytes())}
        )
    return {
        "schema": "review-direct-evidence-packet-v1",
        "artifacts": records,
        "search_roots": normalized_search,
        "validators": normalized_validators,
        "sentinels": sentinel_records,
        "network": {"state": network_state, "mechanism": "sandbox-exec-deny-network"},
        "policy_roots": {
            "source": str(source_root),
            "control": str(control_root),
            "protected": [str(item) for item in protected],
        },
    }


def _workspace_paths(runtime_root: Path, review_id: str) -> tuple[Path, Path]:
    root = runtime_root.expanduser().resolve()
    review_id = _safe_id(review_id)
    workspace = (root / "reviews" / review_id).resolve(strict=False)
    state = (root / ".state" / f"{review_id}.json").resolve(strict=False)
    if not _inside(root, workspace) or not _inside(root, state):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    return workspace, state


def _public_packet(packet: dict[str, object]) -> dict[str, object]:
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
    return {
        **{key: value for key, value in packet.items() if key != "policy_roots"},
        "artifacts": [
            {key: value for key, value in item.items() if key != "content_base64"}
            for item in artifacts
            if isinstance(item, dict)
        ],
    }


def _sb_quote(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _sandbox_profile(workspace: Path, policy: dict[str, object], validators: list[object]) -> str:
    roots = [Path(str(policy["source"])), Path(str(policy["control"]))]
    roots.extend(Path(str(value)) for value in policy.get("protected", []) if isinstance(value, str))
    denied_reads = " ".join(f"(subpath {_sb_quote(path.resolve())})" for path in roots)
    runtime_reads = " ".join(
        f"(subpath {_sb_quote(path)})"
        for path in {Path(sys.prefix).resolve(), Path(sys.executable).resolve().parents[1]}
    )
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            '(import "system.sb")',
            "(allow process*)",
            f"(allow file-read* (subpath {_sb_quote(workspace)}) {runtime_reads})",
            f"(deny file-read* {denied_reads})",
            f"(allow file-write* (subpath {_sb_quote(workspace / 'scratch')}))",
            "(allow file-write-data (literal \"/dev/null\"))",
            f"(deny file-write* {denied_reads})",
            "(deny network*)",
            "",
        ]
    )


def _path_identity_digest(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or resolved.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_POLICY_ROOT_INVALID")
    stat = resolved.stat()
    return _canonical_digest(
        {
            "path": str(resolved),
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "mode": stat.st_mode,
            "kind": "directory" if resolved.is_dir() else "file",
        }
    )


def _root_identity_digests(source: Path, control: Path, protected: list[Path]) -> dict[str, object]:
    return {
        "source": _path_identity_digest(source),
        "control": _path_identity_digest(control),
        "protected": sorted(_path_identity_digest(path) for path in protected),
    }


def _artifact_digest(workspace: Path, packet: dict[str, object]) -> str:
    current: list[dict[str, str]] = []
    for item in packet.get("artifacts", []):
        if not isinstance(item, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
        locator = str(item.get("locator") or "")
        target = _evidence_path(workspace, locator)
        current.append({"locator": locator, "sha256": _sha256_bytes(target.read_bytes())})
    return _canonical_digest(current)


def _sentinel_digest(
    source_root: Path,
    control_root: Path,
    protected_roots: list[Path],
    sentinels: list[object],
) -> str:
    current: list[dict[str, str]] = []
    for item in sentinels:
        if not isinstance(item, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_SENTINEL_INVALID")
        locator = str(item.get("locator") or "")
        _, _, target = _source_path(source_root, control_root, protected_roots, locator)
        current.append({"locator": locator, "sha256": _sha256_bytes(target.read_bytes())})
    return _canonical_digest(current)


def create_reviewer_workspace(
    runtime_root: Path,
    review_id: str,
    packet: dict[str, object],
    *,
    source_root: Path | None = None,
    control_root: Path | None = None,
    protected_roots: list[Path] | None = None,
) -> dict[str, object]:
    if packet.get("schema") != "review-direct-evidence-packet-v1":
        raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
    network = packet.get("network")
    if not isinstance(network, dict) or network.get("state") not in NETWORK_STATES:
        raise ReviewerWorkspaceError("WB_REVIEW_NETWORK_STATE_REQUIRED")
    workspace, state_path = _workspace_paths(runtime_root, review_id)
    if workspace.exists() or workspace.is_symlink() or state_path.exists():
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_COLLISION")
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, list):
        raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
    public_packet = _public_packet(packet)
    policy = packet.get("policy_roots")
    if not isinstance(policy, dict):
        raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_ROOTS_REQUIRED")
    effective_source = Path(str(source_root or policy.get("source") or "")).expanduser().resolve()
    effective_control = Path(str(control_root or policy.get("control") or "")).expanduser().resolve()
    effective_protected = _normalized_roots(
        protected_roots or [Path(str(value)) for value in policy.get("protected", []) if isinstance(value, str)]
    )
    if effective_source != Path(str(policy.get("source"))).resolve() or effective_control != Path(str(policy.get("control"))).resolve():
        raise ReviewerWorkspaceError("WB_REVIEW_POLICY_ROOT_MISMATCH")
    try:
        workspace.mkdir(parents=True)
        scope_digests: dict[str, list[str]] = {"source": [], "control": []}
        for raw in artifacts:
            if not isinstance(raw, dict):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID")
            scope, relative = _split_locator(raw.get("locator"))
            try:
                content = base64.b64decode(str(raw.get("content_base64") or ""), validate=True)
            except (ValueError, TypeError):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_INVALID") from None
            digest = _sha256_bytes(content)
            if digest != raw.get("sha256"):
                raise ReviewerWorkspaceError("WB_REVIEW_PACKET_DIGEST_MISMATCH")
            target = workspace / "evidence" / scope / relative
            if not _inside(workspace, target):
                raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o444)
            scope_digests[scope].append(f"{relative.as_posix()}\0{digest}")
        packet_path = workspace / "packet.json"
        packet_path.write_text(json.dumps(public_packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        packet_path.chmod(0o444)
        (workspace / "scratch").mkdir()
        sandbox_profile = workspace / "sandbox.sb"
        sandbox_profile.write_text(
            _sandbox_profile(workspace, policy, list(public_packet.get("validators", []))), encoding="utf-8"
        )
        sandbox_profile.chmod(0o444)
        evidence_digest = _artifact_digest(workspace, public_packet)
        sentinel_digest = _sentinel_digest(
            effective_source, effective_control, effective_protected, list(public_packet.get("sentinels", []))
        )
        state = {
            "schema": "reviewer-workspace-state-v1",
            "owner": "work-bundle",
            "review_id": review_id,
            "workspace_token": f"reviews/{review_id}",
            "packet_sha256": _canonical_digest(public_packet),
            "source_evidence_digest": _sha256_bytes("\n".join(sorted(scope_digests["source"])).encode("utf-8")),
            "control_evidence_digest": _sha256_bytes("\n".join(sorted(scope_digests["control"])).encode("utf-8")),
            "network": dict(network),
            "sandbox": {"mechanism": "sandbox-exec", "profile_sha256": _sha256_bytes(sandbox_profile.read_bytes())},
            "evidence_digest": evidence_digest,
            "sentinel_digest": sentinel_digest,
            "root_identity_digests": _root_identity_digests(
                effective_source, effective_control, effective_protected
            ),
            "status": "active",
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        state_path.unlink(missing_ok=True)
        raise
    return {
        "status": "prepared",
        "workspace_path": str(workspace),
        "state_path": str(state_path),
        "network": network,
        "packet_sha256": state["packet_sha256"],
        "evidence_digest": state["evidence_digest"],
        "sentinel_digest": state["sentinel_digest"],
    }


def _load_workspace(workspace: Path) -> tuple[dict[str, object], dict[str, object]]:
    workspace = workspace.expanduser().resolve()
    packet_path = workspace / "packet.json"
    if not packet_path.is_file() or packet_path.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID") from None
    artifacts = packet.get("artifacts")
    validators = packet.get("validators")
    if not isinstance(artifacts, list) or not isinstance(validators, list):
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
    by_locator = {str(item.get("locator")): item for item in artifacts if isinstance(item, dict)}
    by_validator = {str(item.get("validator_id")): item for item in validators if isinstance(item, dict)}
    return packet, {"artifacts": by_locator, "validators": by_validator}


def _evidence_path(workspace: Path, locator: object) -> Path:
    scope, relative = _split_locator(locator)
    target = workspace / "evidence" / scope / relative
    if not _inside(workspace, target):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    return target


def enforce_reviewer_write_scope(locator: object) -> None:
    text = str(locator or "")
    if text.startswith("source:"):
        raise ReviewerWorkspaceError("WB_REVIEW_SOURCE_WRITE_DENIED", {"classification": "denied"})
    if text.startswith("control:"):
        raise ReviewerWorkspaceError("WB_REVIEW_CONTROL_WRITE_DENIED", {"classification": "denied"})
    raise ReviewerWorkspaceError("WB_REVIEW_WRITE_DENIED", {"classification": "denied"})


def _runtime_identity(workspace: Path) -> tuple[Path, str, dict[str, object]]:
    workspace = workspace.expanduser().resolve()
    if workspace.parent.name != "reviews":
        raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
    runtime_root = workspace.parent.parent
    review_id = _safe_id(workspace.name)
    state_path = runtime_root / ".state" / f"{review_id}.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID") from None
    if not isinstance(state, dict) or state.get("review_id") != review_id or state.get("owner") != "work-bundle":
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID")
    return runtime_root, review_id, state


def _append_denial_event(workspace: Path, error: ReviewerWorkspaceError, operation: object) -> None:
    runtime_root, review_id, state = _runtime_identity(workspace)
    events_path = (runtime_root / "events" / f"{review_id}.jsonl").resolve(strict=False)
    if not _inside(runtime_root, events_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    events_path.parent.mkdir(parents=True, exist_ok=True)
    if events_path.exists():
        events_path.chmod(0o600)
    operation_name = str(operation or "unknown")
    if operation_name not in {"read", "write", "search", "validate", "network"}:
        operation_name = "unknown"
    event = {
        "schema": "reviewer-denial-event-v1",
        "event_id": f"review-denial-{uuid.uuid4()}",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "review_id": review_id,
        "packet_sha256": state.get("packet_sha256"),
        "event_type": "reviewer_operation_denied",
        "denial_code": error.code,
        "operation": operation_name,
        "privacy": "operational_metadata_only",
    }
    descriptor = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)
    events_path.chmod(0o400)


def _seal_event_log(runtime_root: Path, review_id: str) -> dict[str, object]:
    events_path = (runtime_root / "events" / f"{review_id}.jsonl").resolve(strict=False)
    if not _inside(runtime_root, events_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    events_path.parent.mkdir(parents=True, exist_ok=True)
    if not events_path.exists():
        descriptor = os.open(events_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        os.close(descriptor)
    events_path.chmod(0o400)
    return {
        "event_log_path": str(events_path),
        "event_log_sha256": _sha256_bytes(events_path.read_bytes()),
        "event_log_mode": "0400",
    }


def _sandbox_denied(completed: subprocess.CompletedProcess[str]) -> bool:
    if completed.returncode == 0:
        return False
    detail = f"{completed.stdout}\n{completed.stderr}".lower()
    return (
        completed.returncode < 0
        or "operation not permitted" in detail
        or "sandbox violation" in detail
        or "permissionerror" in detail
    )


def _run_sandboxed_process(workspace: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    workspace = workspace.expanduser().resolve()
    _, _, state = _runtime_identity(workspace)
    if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        raise ReviewerWorkspaceError("WB_REVIEW_SANDBOX_UNAVAILABLE", {"classification": "denied"})
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID", {"classification": "denied"})
    executable = Path(argv[0]).expanduser()
    if not executable.is_absolute() or not executable.is_file():
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID", {"classification": "denied"})
    allowed_runtime_roots = [
        Path("/System"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path(sys.prefix).resolve(),
        Path(sys.executable).resolve().parents[1],
    ]
    if not any(_inside(root, executable) for root in allowed_runtime_roots):
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID", {"classification": "denied"})
    profile = workspace / "sandbox.sb"
    sandbox_state = state.get("sandbox") if isinstance(state.get("sandbox"), dict) else {}
    if not profile.is_file() or profile.is_symlink() or _sha256_bytes(profile.read_bytes()) != sandbox_state.get("profile_sha256"):
        raise ReviewerWorkspaceError("WB_REVIEW_SANDBOX_PROFILE_INVALID", {"classification": "denied"})
    scratch = workspace / "scratch"
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    (scratch / "home").mkdir(parents=True, exist_ok=True)
    (scratch / "tmp").mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), *argv],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def run_sandboxed_validator(workspace: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one frozen validator argv inside the macOS process sandbox."""
    return _run_sandboxed_process(workspace, argv)


def run_sandboxed_reviewer(workspace: Path, argv: list[str]) -> dict[str, object]:
    """Launch the entire reviewer under the frozen deny-default profile."""
    workspace = workspace.expanduser().resolve()
    runtime_root, review_id, state = _runtime_identity(workspace)
    completed = _run_sandboxed_process(workspace, argv)
    denied = _sandbox_denied(completed)
    if denied:
        _append_denial_event(
            workspace,
            ReviewerWorkspaceError("WB_REVIEW_SANDBOX_DENIED", {"classification": "denied"}),
            "validate",
        )
    sealed = _seal_event_log(runtime_root, review_id)
    sandbox_state = state.get("sandbox") if isinstance(state.get("sandbox"), dict) else {}
    run_id = f"reviewer-run-{uuid.uuid4()}"
    receipt = {
        "schema": "reviewer-process-receipt-v1",
        "run_id": run_id,
        "review_id": review_id,
        "status": "denied" if denied else ("passed" if completed.returncode == 0 else "failed"),
        "packet_sha256": state.get("packet_sha256"),
        "sandbox_profile_sha256": sandbox_state.get("profile_sha256"),
        "argv_sha256": _canonical_digest(argv),
        "exit_code": completed.returncode,
        "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
        "event_log_sha256": sealed["event_log_sha256"],
        "event_log_mode": sealed["event_log_mode"],
    }
    receipt_path = (runtime_root / "receipts" / "reviewer-process" / f"{run_id}.json").resolve(strict=False)
    if not _inside(runtime_root, receipt_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt_path.chmod(0o400)
    return {**receipt, "receipt_path": str(receipt_path), "event_log_path": sealed["event_log_path"]}


def _execute_reviewer_request(workspace: Path, request: dict[str, object]) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    packet, indexes = _load_workspace(workspace)
    operation = str(request.get("operation") or "")
    if operation == "write":
        enforce_reviewer_write_scope(request.get("artifact"))
    if operation == "network":
        raise ReviewerWorkspaceError("WB_REVIEW_NETWORK_DENIED", {"classification": "denied"})
    if operation == "read":
        locator = str(request.get("artifact") or "")
        _split_locator(locator)
        record = indexes["artifacts"].get(locator)
        if not isinstance(record, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_PROTECTED_READ_DENIED", {"classification": "denied"})
        target = _evidence_path(workspace, locator)
        if _sha256_bytes(target.read_bytes()) != record.get("sha256"):
            raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
        return {"status": "allowed", "artifact": locator, "content": target.read_text(encoding="utf-8")}
    if operation == "search":
        pattern = str(request.get("pattern") or "")
        if not pattern or len(pattern) > 256 or "\n" in pattern:
            raise ReviewerWorkspaceError("WB_REVIEW_SEARCH_PATTERN_INVALID")
        allowed_roots = packet.get("search_roots")
        if not isinstance(allowed_roots, list):
            raise ReviewerWorkspaceError("WB_REVIEW_WORKSPACE_INVALID")
        matches: list[str] = []
        for locator, record in sorted(indexes["artifacts"].items()):
            if not isinstance(record, dict) or not any(
                locator == root or locator.startswith(f"{root.rstrip('/')}/") for root in allowed_roots
            ):
                continue
            target = _evidence_path(workspace, locator)
            if _sha256_bytes(target.read_bytes()) != record.get("sha256"):
                raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
            for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern in line:
                    matches.append(f"{locator}:{number}:{line.strip()}")
        return {"status": "allowed", "matches": matches}
    if operation == "validate":
        validator_id = str(request.get("validator_id") or "")
        validator = indexes["validators"].get(validator_id)
        if not isinstance(validator, dict):
            raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_DENIED", {"classification": "denied"})
        if validator.get("kind") == "command":
            argv = validator.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
                raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_DENIED", {"classification": "denied"})
            completed = run_sandboxed_validator(workspace, argv)
            if completed.returncode:
                if _sandbox_denied(completed):
                    raise ReviewerWorkspaceError(
                        "WB_REVIEW_SANDBOX_DENIED",
                        {"classification": "denied", "validator_id": validator_id, "exit_code": completed.returncode},
                    )
                return {
                    "status": "allowed",
                    "validator_id": validator_id,
                    "result": "failed",
                    "exit_code": completed.returncode,
                    "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
                    "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
                }
            return {
                "status": "allowed",
                "validator_id": validator_id,
                "result": "passed",
                "exit_code": 0,
                "stdout_sha256": _sha256_bytes(completed.stdout.encode("utf-8")),
                "stderr_sha256": _sha256_bytes(completed.stderr.encode("utf-8")),
            }
        locator = str(validator.get("artifact") or "")
        record = indexes["artifacts"].get(locator)
        target = _evidence_path(workspace, locator)
        if not isinstance(record, dict) or _sha256_bytes(target.read_bytes()) != record.get("sha256"):
            raise ReviewerWorkspaceError("WB_REVIEW_EVIDENCE_MUTATED")
        if validator.get("kind") == "json":
            try:
                json.loads(target.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"status": "allowed", "validator_id": validator_id, "result": "failed"}
            result = "passed"
        elif validator.get("kind") == "sha256":
            result = str(record["sha256"])
        else:
            raise ReviewerWorkspaceError("WB_REVIEW_VALIDATOR_DENIED", {"classification": "denied"})
        return {"status": "allowed", "validator_id": validator_id, "result": result}
    raise ReviewerWorkspaceError("WB_REVIEW_OPERATION_DENIED", {"classification": "denied"})


def execute_reviewer_request(workspace: Path, request: dict[str, object]) -> dict[str, object]:
    try:
        return _execute_reviewer_request(workspace, request)
    except ReviewerWorkspaceError as error:
        _append_denial_event(workspace, error, request.get("operation"))
        raise


def cleanup_reviewer_workspace(
    runtime_root: Path,
    review_id: str,
    *,
    terminal_review: dict[str, object] | None = None,
    source_root: Path | None = None,
    control_root: Path | None = None,
    protected_roots: list[Path] | None = None,
    terminal_evidence: str | None = None,
) -> dict[str, object]:
    workspace, state_path = _workspace_paths(runtime_root, review_id)
    if terminal_evidence is not None or not isinstance(terminal_review, dict):
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_RECORD_INVALID")
    if not state_path.is_file() or state_path.is_symlink():
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_MISSING")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID") from None
    if (
        not isinstance(state, dict)
        or state.get("owner") != "work-bundle"
        or state.get("review_id") != review_id
        or state.get("workspace_token") != f"reviews/{review_id}"
        or not workspace.is_dir()
        or workspace.is_symlink()
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID")
    required_terminal = {"schema", "review_id", "packet_sha256", "verdict", "evidence_digest", "sentinel_digest"}
    if (
        set(terminal_review) != required_terminal
        or terminal_review.get("schema") != "reviewer-terminal-review-v1"
        or terminal_review.get("review_id") != review_id
        or terminal_review.get("packet_sha256") != state.get("packet_sha256")
        or terminal_review.get("verdict") not in TERMINAL_VERDICTS
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_RECORD_INVALID")
    packet_path = workspace / "packet.json"
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID") from None
    if _canonical_digest(packet) != state.get("packet_sha256"):
        raise ReviewerWorkspaceError("WB_REVIEW_PROVENANCE_INVALID")
    evidence_digest = _artifact_digest(workspace, packet)
    if source_root is None or control_root is None:
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_RECORD_INVALID")
    protected = _normalized_roots(protected_roots or [])
    supplied_root_identities = _root_identity_digests(
        source_root.expanduser().resolve(), control_root.expanduser().resolve(), protected
    )
    if supplied_root_identities != state.get("root_identity_digests"):
        raise ReviewerWorkspaceError("WB_REVIEW_ROOT_IDENTITY_MISMATCH")
    sentinel_digest = _sentinel_digest(
        source_root.expanduser().resolve(),
        control_root.expanduser().resolve(),
        protected,
        list(packet.get("sentinels", [])),
    )
    if (
        evidence_digest != state.get("evidence_digest")
        or sentinel_digest != state.get("sentinel_digest")
        or terminal_review.get("evidence_digest") != evidence_digest
        or terminal_review.get("sentinel_digest") != sentinel_digest
    ):
        raise ReviewerWorkspaceError("WB_REVIEW_TERMINAL_EVIDENCE_CHANGED")
    terminal_record_digest = _canonical_digest(terminal_review)
    receipt = {
        "schema": "reviewer-workspace-cleanup-v1",
        "review_id": review_id,
        "owner": "work-bundle",
        "packet_sha256": state["packet_sha256"],
        "terminal_review_sha256": terminal_record_digest,
        "evidence_digest": evidence_digest,
        "sentinel_digest": sentinel_digest,
        "status": "cleaned",
    }
    resolved_runtime = runtime_root.expanduser().resolve()
    receipt_path = (resolved_runtime / "receipts" / f"{review_id}.json").resolve(strict=False)
    if not _inside(resolved_runtime, receipt_path):
        raise ReviewerWorkspaceError("WB_REVIEW_RUNTIME_PATH_ESCAPE")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    pending = {**receipt, "status": "cleanup-pending"}
    receipt_path.write_text(json.dumps(pending, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.rmtree(workspace)
    state_path.unlink()
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": str(receipt_path)}


def cmd_reviewer_workspace(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"wb.py {command}")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--review-id", required=True)
    if command == "reviewer-workspace-create":
        parser.add_argument("--packet", required=True)
    elif command == "reviewer-process-run":
        parser.add_argument("--argv-json", required=True)
    elif command == "reviewer-workspace-operation":
        parser.add_argument("--request", required=True)
    elif command == "reviewer-workspace-cleanup":
        parser.add_argument("--terminal-review", required=True)
        parser.add_argument("--source-root", required=True)
        parser.add_argument("--control-root", required=True)
        parser.add_argument("--protected-root", action="append", required=True)
    else:
        raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID")
    args = parser.parse_args(argv)
    runtime_root = Path(args.runtime_root)
    if command == "reviewer-workspace-create":
        result = create_reviewer_workspace(runtime_root, args.review_id, json.loads(Path(args.packet).read_text(encoding="utf-8")))
    elif command == "reviewer-process-run":
        argv_value = json.loads(Path(args.argv_json).read_text(encoding="utf-8"))
        if not isinstance(argv_value, list):
            raise ReviewerWorkspaceError("WB_REVIEW_COMMAND_INVALID")
        workspace, _ = _workspace_paths(runtime_root, args.review_id)
        result = run_sandboxed_reviewer(workspace, argv_value)
    elif command == "reviewer-workspace-operation":
        workspace, _ = _workspace_paths(runtime_root, args.review_id)
        result = execute_reviewer_request(workspace, json.loads(Path(args.request).read_text(encoding="utf-8")))
    else:
        result = cleanup_reviewer_workspace(
            runtime_root,
            args.review_id,
            terminal_review=json.loads(Path(args.terminal_review).read_text(encoding="utf-8")),
            source_root=Path(args.source_root),
            control_root=Path(args.control_root),
            protected_roots=[Path(value) for value in args.protected_root],
        )
    print(json.dumps(result, sort_keys=True))
    return 0
