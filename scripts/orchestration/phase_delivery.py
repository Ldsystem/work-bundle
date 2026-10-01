"""Workspace-owned immutable phase payloads and bounded process-bridge sessions.

This owner reports identity, process and filesystem facts. Callers own acceptance
and explicit release decisions. Project code is invoked only through argv bridges.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from typing import Any

import jsonschema
import psutil
from referencing import Registry, Resource

from artifact_store import canonical_artifact_path, family_policy, load_catalog, read_artifact, read_yaml_mapping
from core import resolve_workspace_root
from execution_context import (
    build_implementation_review_candidate, load_task_execution_binding,
    _validate_delivery_graph, _validate_phase_dependencies,
)
from review_identity import load_canonical_plan_tree, canonical_task_authority_identity
sys.path.append(str(Path(__file__).resolve().parents[1]))
from platform_runtime import atomic_replace_bytes, blocking_file_lock, contains_link_like_component, is_link_like

CONTRACT = Path(__file__).resolve().parents[2] / "references/assets/orchestration/contract"
CATALOG = CONTRACT / "artifact-family-catalog-v7.yaml"
SCHEMA = CONTRACT / "phase-bridge-v1.schema.json"
MESSAGE_LIMIT = 2000


class PhaseDeliveryError(ValueError):
    pass


def _fail(message: str) -> None:
    raise PhaseDeliveryError(message)


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    if is_link_like(path) or not path.is_file():
        _fail("missing or unsafe runtime file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _fail("unreadable runtime JSON")
    if not isinstance(value, dict):
        _fail("runtime JSON must be an object")
    return value


def validate_contract(value: Any, definition: str) -> None:
    schema = json.loads(SCHEMA.read_text())
    registry = Registry().with_resources([
        (name, Resource.from_contents(json.loads((CONTRACT / f"{name}.schema.json").read_text())))
        for name in ("implementation-review-v3", "task-v3", "phase-v2", "executor-result-v2")
    ])
    try:
        jsonschema.Draft202012Validator({**schema, "$ref": f"#/$defs/{definition}"}, registry=registry).validate(value)
    except jsonschema.ValidationError:
        _fail(f"invalid phase-bridge-v1 {definition}")


def _relative(value: str, *, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        _fail("unsafe relative path")
    path = PurePosixPath(value)
    if value == "." and allow_dot:
        return value
    if not value or path.is_absolute() or ":" in value or any(p in {"", ".", "..", "credentials"} for p in value.split("/")):
        _fail("unsafe or protected relative path")
    return value


def _inside(root: Path, relative: str, *, directory: bool = False) -> Path:
    _relative(relative, allow_dot=directory)
    target = root / relative
    if contains_link_like_component(target, anchor=root) or not target.resolve().is_relative_to(root.resolve()):
        _fail("runtime path escapes or traverses a link")
    return target


def runtime_paths(workspace: Path, plan_id: str, phase_id: str) -> dict[str, str]:
    for value, prefix in ((plan_id, "plan"), (phase_id, "phase")):
        if not re.fullmatch(prefix + r"-[a-z0-9][a-z0-9-]*", value):
            _fail("invalid runtime identity")
    relative = f".work-bundle/orchestration/runtime/phase-delivery/{plan_id}/{phase_id}"
    _inside(workspace, relative)
    return {"relative_path": relative, "payload_relative_path": relative + "/payload", "state_relative_path": relative + ".state.json"}


def _artifact(workspace: Path, family: str, identity: str, bindings: dict[str, str]) -> dict[str, Any]:
    return read_artifact(CATALOG, family, {"workspace_root": workspace}, identity=identity, state="active", bindings=bindings)


def _accepted(workspace: Path, plan_id: str, task_id: str) -> dict[str, Any] | None:
    # Navigation hits remain candidates until schema, locator and bindings validate.
    directory = workspace / f".work-bundle/orchestration/result/accepted/active/{plan_id}/{task_id}"
    if contains_link_like_component(directory, anchor=workspace):
        _fail("unsafe accepted-result path")
    matches = []
    for candidate in sorted(directory.glob("*.accepted-task-result.yaml")):
        raw = read_yaml_mapping(candidate)
        record = _artifact(workspace, "accepted-task-result", str(raw.get("id", "")), {"plan": plan_id, "task": task_id})
        if Path(record["path"]).resolve() != candidate.resolve():
            _fail("accepted result is not canonical")
        matches.append(record)
    if len(matches) > 1:
        _fail("ambiguous active accepted result")
    if not matches:
        return None
    record = matches[0]
    if record["data"].get("authority_identity") != canonical_task_authority_identity(workspace, plan_id, task_id):
        _fail("accepted result authority is stale")
    return record


def resolve_phase_authority(workspace: Path, plan_id: str, phase_id: str) -> dict[str, Any]:
    tree = load_canonical_plan_tree(workspace, plan_id, state="active")
    if tree["root"]["status"] != "verified" or phase_id not in tree["phases"]:
        _fail("phase requires a verified active canonical plan")
    phase = tree["phases"][phase_id]
    delivery = phase.get("delivery", {})
    task_id = delivery.get("task_id")
    if not task_id or task_id not in tree["tasks"]:
        _fail("phase has no designated delivery task")
    tasks = tree["tasks"]
    dependencies = {key: list(task["depends_on"]) for key, task in tasks.items()}
    _validate_phase_dependencies(tree["phases"])
    # Canonical admission established DAG/membership; revalidate the live declarations.
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(key: str):
        if key in visiting or key not in tasks:
            _fail("invalid task dependency graph")
        if key in visited:
            return
        visiting.add(key)
        for dependency in dependencies[key]:
            visit(dependency)
        visiting.remove(key)
        visited.add(key)
    for key in tasks:
        visit(key)
    _validate_delivery_graph(tree["root"], tree["phases"], tasks, dependencies)
    predecessor_ids: set[str] = set()
    def collect(key: str):
        for dependency in dependencies[key]:
            if dependency not in predecessor_ids:
                predecessor_ids.add(dependency)
                collect(dependency)
    collect(task_id)
    predecessors = []
    for key in sorted(predecessor_ids):
        accepted = _accepted(workspace, plan_id, key)
        if accepted is None:
            _fail(f"accepted predecessor is missing: {key}")
        predecessors.append({"task_id": key, "id": accepted["data"]["id"], "sha256": accepted["digest"]})
    accepted = _accepted(workspace, plan_id, task_id)
    catalog = []
    for row in delivery["test_catalog"]:
        if row["disposition"] == "executable":
            item = next(item for item in tasks[row["task_id"]]["validation"] if item.get("id") == row["test_id"])
            catalog.append({"task": row["task_id"], "test": row["test_id"], "process": dict(item["process"])})
    return {
        "plan_id": plan_id, "phase_id": phase_id, "task_id": task_id,
        "phase": phase, "catalog": catalog, "predecessors": predecessors,
        "authority_identity": canonical_task_authority_identity(workspace, plan_id, task_id),
        "external_targets": tasks[task_id]["interfaces"].get("external_targets", []),
        "exclusions": [],
        "binding": None if accepted else load_task_execution_binding(workspace, plan_id, task_id),
        "accepted": accepted,
    }


def _binding_identity(binding: dict[str, Any]) -> dict[str, Any]:
    return {key: binding[key] for key in ("execution_path", "repository_id", "execution_id")}


def _candidate(source: Path, binding: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    schema = json.loads((CONTRACT / "implementation-review-v3.schema.json").read_text())
    try:
        jsonschema.Draft202012Validator({**schema["properties"]["target"], "$defs": schema["$defs"]}).validate(target)
    except jsonschema.ValidationError:
        _fail("invalid supplied candidate target")
    for entry in target["manifest"]:
        _relative(entry["path"])
        _inside(source, entry["path"])
    baseline = binding.get("baseline") or {}
    if target["kind"] == "worktree" and baseline.get("head") and baseline["head"] != target["base_commit"]:
        _fail("candidate baseline mismatch")
    commit_input = {"candidate_commit" if target["kind"] == "commit" else "base_commit": target["base_commit"]}
    normalized = build_implementation_review_candidate(source_root=source, kind=target["kind"], changed_paths=[row["path"] for row in target["manifest"]], **commit_input)
    if normalized != target:
        _fail("supplied candidate identity mismatch")
    actual = build_implementation_review_candidate(source_root=source, kind="worktree", base_commit=target["base_commit"], changed_paths=[row["path"] for row in target["manifest"]])
    if actual["sha256"] != normalized["sha256"] or actual["manifest"] != normalized["manifest"]:
        _fail("candidate does not identify current checkout bytes")
    if target["kind"] == "commit":
        head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
        if head.returncode or head.stdout.strip() != target["base_commit"]:
            _fail("commit candidate is not current checkout commit")
    return normalized


def _tree_entries(root: Path, *, source: bool = False) -> list[dict[str, Any]]:
    entries = []
    def scan(directory: Path):
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root).as_posix()
            if source and relative == ".git":
                continue
            if source and relative == ".codegraph":
                ignored = subprocess.run(["git", "-C", str(root), "check-ignore", ".codegraph/"], capture_output=True, check=False)
                if ignored.returncode == 0:
                    continue
            _relative(relative)
            if is_link_like(path):
                _fail("snapshot contains link-like entry")
            mode = path.stat().st_mode
            if path.is_dir():
                entries.append({"path": relative, "kind": "directory", "executable": True})
                scan(path)
            elif stat.S_ISREG(mode):
                entries.append({"path": relative, "kind": "file", "executable": bool(mode & 0o111), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            else:
                _fail("snapshot contains special filesystem entry")
    scan(root)
    return sorted(entries, key=lambda entry: entry["path"])


def _descriptors(source: Path, manifest: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validate_contract(manifest, "bridgeManifest")
    bridges = manifest["bridges"]
    requirements = policy["phase"]["delivery"]["bridges"]
    if any(value == "required" and role not in bridges for role, value in requirements.items()):
        _fail("required bridge is missing")
    for role, descriptor in bridges.items():
        if descriptor["role"] != role:
            _fail("bridge role mismatch")
        cwd = _inside(source, descriptor["working_directory"], directory=True)
        if not cwd.is_dir():
            _fail("bridge cwd is missing")
        executable = Path(descriptor["argv"][0]).name.lower()
        if executable in {"sh", "bash", "zsh", "dash", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
            _fail("shell bridge invocation is forbidden")
        if any("\x00" in argument for argument in descriptor["argv"]):
            _fail("invalid bridge argv")
        if descriptor["ownership"] == "external" and not descriptor["external_targets"]:
            _fail("external ownership requires declared targets")
        for target in descriptor["external_targets"]:
            declaration = next((item for item in policy["external_targets"] if item["target_id"] == target["target_id"]), None)
            expected_ref = f"{policy['task_id']}#external-targets.{target['target_id']}"
            if declaration is None or target["authority_ref"] != expected_ref or not set(target["permitted_actions"]).issubset(declaration["permitted_actions"]) or not set(target["permitted_actions"]).issubset(descriptor["capabilities"]):
                _fail("bridge external target/action authority mismatch")
            if role == "start_snapshot" and not {"start", "readiness", "stop"}.issubset(target["permitted_actions"]):
                _fail("external start requires readiness and stop authority")
    return bridges


def _write(path: Path, value: dict[str, Any]) -> None:
    definition = {"phase-runtime-v1": "runtimeState", "phase-session-lease-v1": "lease", "phase-payload-manifest-v1": "payloadManifest", "phase-snapshot-manifest-v1": "snapshotManifest"}.get(value.get("protocol"))
    if definition:
        validate_contract(value, definition)
    atomic_replace_bytes(path, _bytes(value), mode=0o600)


def _state(workspace: Path, plan_id: str, phase_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    paths = runtime_paths(workspace, plan_id, phase_id)
    state = _json(workspace / paths["state_relative_path"])
    validate_contract(state, "runtimeState")
    if state.get("protocol") != "phase-runtime-v1" or state.get("plan_id") != plan_id or state.get("phase_id") != phase_id or state.get("paths") != paths:
        _fail("runtime state identity mismatch")
    if state["staging_name"] != f".{phase_id}.{state['transaction_id']}.staging":
        _fail("runtime staging identity mismatch")
    if state["runtime_bundle"]["payload_sha256"] != _digest(state["payload_manifest"]):
        _fail("runtime manifest identity mismatch")
    return state, paths


def _remove_tree(path: Path) -> None:
    if is_link_like(path):
        _fail("unsafe cleanup target")
    if not path.exists():
        return
    # Read-only payloads need owner write permissions to remove on Windows too.
    for directory, dirs, files in os.walk(path):
        Path(directory).chmod(0o700)
        for name in files:
            child = Path(directory) / name
            if is_link_like(child):
                _fail("unsafe cleanup entry")
            child.chmod(0o600)
        for name in dirs:
            if is_link_like(Path(directory) / name):
                _fail("unsafe cleanup entry")
    shutil.rmtree(path)


def _freeze(root: Path) -> None:
    for path in root.rglob("*"):
        path.chmod(0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444)
    root.chmod(0o555)


def _verify_payload(bundle: Path, state: dict[str, Any]) -> dict[str, Any]:
    payload = _inside(bundle, "payload")
    manifest = _json(_inside(payload, "payload-manifest.json"))
    validate_contract(manifest, "payloadManifest")
    if _digest(manifest) != state["runtime_bundle"]["payload_sha256"]:
        _fail("payload digest mismatch")
    observed = [item for item in _tree_entries(payload) if item["path"] != "payload-manifest.json"]
    if observed != manifest["entries"]:
        _fail("payload bytes or manifest mismatch")
    snapshot_manifest = _json(payload / "snapshot-manifest.json")
    validate_contract(snapshot_manifest, "snapshotManifest")
    entries = _tree_entries(payload / "snapshot")
    if entries != snapshot_manifest["entries"] or _digest(snapshot_manifest) != state["runtime_bundle"]["snapshot_manifest_sha256"] or _digest(entries) != state["runtime_bundle"]["snapshot_content_sha256"]:
        _fail("snapshot manifest/content digest mismatch")
    metadata = _json(payload / "metadata.json")
    if metadata != state["identity"]:
        _fail("payload/state identity mismatch")
    return metadata


def materialize_phase_handoff(workspace: Path, plan_id: str, phase_id: str, task_id: str, bridge_manifest: str, candidate_file: str | Path | None = None) -> dict[str, Any]:
    workspace = workspace.resolve()
    policy = resolve_phase_authority(workspace, plan_id, phase_id)
    if policy["task_id"] != task_id or policy["accepted"]:
        _fail("materialization requires the unaccepted designated delivery task")
    binding = policy["binding"]
    source = Path(binding["execution_path"]).resolve()
    manifest_path = _inside(source, bridge_manifest)
    supplied = None
    if candidate_file:
        input_path = Path(candidate_file).resolve()
        protected = (workspace / "credentials/credentials.yaml").resolve()
        # Resolve link aliases and compare file identities without reading vault bytes.
        if input_path == protected or (input_path.exists() and protected.exists() and input_path.samefile(protected)):
            _fail("protected candidate input")
        supplied = read_yaml_mapping(input_path)
    if supplied is None:
        _fail("materialization requires a supplied candidate target")
    candidate = _candidate(source, binding, supplied)
    bridges = _descriptors(source, _json(manifest_path), policy)
    entries = _tree_entries(source, source=True)
    snapshot_manifest = {"protocol": "phase-snapshot-manifest-v1", "entries": entries}
    identity = {
        "task_id": task_id, "authority_identity": policy["authority_identity"],
        "predecessors": policy["predecessors"], "binding": _binding_identity(binding),
        "candidate": candidate, "catalog": policy["catalog"],
        "phase_delivery": policy["phase"]["delivery"], "external_targets": policy["external_targets"],
        "bridge_manifest": bridge_manifest,
    }
    paths = runtime_paths(workspace, plan_id, phase_id)
    bundle, state_path = workspace / paths["relative_path"], workspace / paths["state_relative_path"]
    bundle.parent.mkdir(parents=True, exist_ok=True)
    with blocking_file_lock(bundle.parent / f".{phase_id}.lock"):
        if state_path.exists():
            previous, _ = _state(workspace, plan_id, phase_id)
            if previous["state"] == "materializing":
                if previous["identity"] != identity:
                    _fail("materialization transaction identity mismatch")
                staging = bundle.parent / previous["staging_name"]
                if bundle.exists() and staging.exists():
                    _fail("ambiguous materialization transaction")
                if bundle.exists():
                    _verify_payload(bundle, previous)
                    previous["state"] = "active"
                    _write(state_path, previous)
                    return read_bundle(workspace, plan_id, phase_id)
                _remove_tree(staging)
                state_path.unlink()
            elif previous["state"] == "active":
                existing = read_bundle(workspace, plan_id, phase_id)
                comparable = {**identity, "candidate": previous["identity"]["candidate"]}
                if previous["identity"] != comparable or any(candidate[key] != previous["identity"]["candidate"][key] for key in ("sha256", "manifest")):
                    _fail("immutable active payload cannot be replaced")
                return existing
            elif previous["state"] == "cleaned" and previous["reason"] == "explicit_release":
                if bundle.exists():
                    _fail("cleaned state has unexplained payload")
            else:
                _fail("runtime state cannot materialize")
        elif bundle.exists():
            _fail("unexplained canonical bundle")
        transaction = uuid.uuid4().hex
        staging = bundle.parent / f".{phase_id}.{transaction}.staging"
        state = {"protocol": "phase-runtime-v1", "plan_id": plan_id, "phase_id": phase_id,
            "state": "materializing", "reason": None, "transaction_id": transaction,
            "staging_name": staging.name, "paths": paths, "identity": identity,
            "runtime_bundle": {**paths, "payload_sha256": "", "snapshot_manifest_sha256": _digest(snapshot_manifest), "snapshot_content_sha256": _digest(entries), "retained_until": "finalization_or_explicit_release"}}
        # Compute the exact expected payload before provisional state or staging effects.
        payload_entries = [{"path": "bridges", "kind": "directory", "executable": True},
            {"path": "metadata.json", "kind": "file", "executable": False, "sha256": hashlib.sha256(_bytes(identity)).hexdigest()},
            {"path": "snapshot", "kind": "directory", "executable": True},
            {"path": "snapshot-manifest.json", "kind": "file", "executable": False, "sha256": hashlib.sha256(_bytes(snapshot_manifest)).hexdigest()}]
        payload_entries.extend({**entry, "path": "snapshot/" + entry["path"]} for entry in entries)
        payload_entries.extend({"path": f"bridges/{role}.json", "kind": "file", "executable": False, "sha256": hashlib.sha256(_bytes(descriptor)).hexdigest()} for role, descriptor in bridges.items())
        payload_entries.sort(key=lambda entry: entry["path"])
        payload_manifest = {"protocol": "phase-payload-manifest-v1", "entries": payload_entries}
        state["runtime_bundle"]["payload_sha256"] = _digest(payload_manifest)
        state["payload_manifest"] = payload_manifest
        _write(state_path, state)
        try:
            payload = staging / "payload"
            snapshot = payload / "snapshot"
            snapshot.mkdir(parents=True)
            (staging / "sessions").mkdir()
            (payload / "bridges").mkdir()
            for entry in entries:
                destination = snapshot / entry["path"]
                if entry["kind"] == "directory":
                    destination.mkdir()
                else:
                    shutil.copyfile(source / entry["path"], destination)
                    destination.chmod(0o755 if entry["executable"] else 0o644)
            _write(payload / "metadata.json", identity)
            _write(payload / "snapshot-manifest.json", snapshot_manifest)
            for role, descriptor in bridges.items():
                _write(payload / "bridges" / f"{role}.json", descriptor)
            _write(payload / "payload-manifest.json", payload_manifest)
            if _tree_entries(source, source=True) != entries:
                _fail("candidate changed during materialization")
            _verify_payload(staging, state)
            _freeze(payload)
            os.replace(staging, bundle)
            state["state"] = "active"
            _write(state_path, state)
        except Exception:
            # A verified rename is recoverable on entry, never erase published bytes.
            if not bundle.exists():
                _remove_tree(staging)
                state_path.unlink(missing_ok=True)
            raise
        return read_bundle(workspace, plan_id, phase_id)


def _authority_matches(workspace: Path, state: dict[str, Any], policy: dict[str, Any], *, release: bool = False) -> None:
    identity = state["identity"]
    if policy["task_id"] != identity["task_id"] or policy["authority_identity"] != identity["authority_identity"] or policy["predecessors"] != identity["predecessors"] or policy["catalog"] != identity["catalog"]:
        _fail("runtime task/catalog/predecessor identity is stale")
    accepted = policy["accepted"]
    if accepted:
        data = accepted["data"]
        if data["product_identity"]["sha256"] != identity["candidate"]["sha256"]:
            _fail("accepted product identity mismatch")
        reference = data["executor_result"]
        executor = _artifact(workspace, "executor-result", reference["id"], {"plan": state["plan_id"], "task": identity["task_id"]})
        if executor["digest"] != reference["sha256"]:
            _fail("accepted executor reference mismatch")
        handoff = executor["data"].get("phase_handoff")
        if not handoff or handoff["runtime_bundle"] != state["runtime_bundle"] or handoff["phase_id"] != state["phase_id"] or handoff["delivery_task_id"] != identity["task_id"]:
            _fail("accepted phase handoff identity mismatch")
        if state["state"] == "active":
            summaries = _bridge_summaries(workspace / state["paths"]["payload_relative_path"])
            if handoff["bridges"] != summaries:
                _fail("accepted bridge descriptor identity mismatch")
    else:
        if _binding_identity(policy["binding"]) != identity["binding"]:
            _fail("materialization execution binding mismatch")
        if not release:
            source = Path(policy["binding"]["execution_path"])
            # Container kind/commit provenance may advance without changing bytes.
            current = build_implementation_review_candidate(source_root=source, kind="worktree", base_commit=identity["candidate"]["base_commit"], changed_paths=[row["path"] for row in identity["candidate"]["manifest"]])
            if current["sha256"] != identity["candidate"]["sha256"] or _digest(_tree_entries(source, source=True)) != state["runtime_bundle"]["snapshot_content_sha256"]:
                _fail("preacceptance candidate identity is stale")


def _bridge_summaries(payload: Path) -> dict[str, Any]:
    return {path.stem: {"protocol": "phase-bridge-v1", "descriptor_sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted((payload / "bridges").glob("*.json"))}


def read_bundle(workspace: Path, plan_id: str, phase_id: str, *, check_authority: bool = True) -> dict[str, Any]:
    workspace = workspace.resolve()
    state, paths = _state(workspace, plan_id, phase_id)
    if state["state"] != "active":
        _fail(f"runtime bundle is {state['state']}")
    bundle = workspace / paths["relative_path"]
    metadata = _verify_payload(bundle, state)
    bridges = {path.stem: _json(path) for path in sorted((bundle / "payload/bridges").glob("*.json"))}
    if check_authority:
        policy = resolve_phase_authority(workspace, plan_id, phase_id)
        _authority_matches(workspace, state, policy)
        _descriptors(bundle / "payload/snapshot", {"protocol": "phase-bridge-v1", "bridges": bridges}, policy)
    return {"plan_id": plan_id, "phase_id": phase_id, "delivery_task_id": metadata["task_id"],
        "runtime_bundle": deepcopy(state["runtime_bundle"]), "bridges": _bridge_summaries(bundle / "payload"),
        "bridge_descriptors": bridges, "identity": metadata,
        "bundle_root": str(bundle), "snapshot_root": str(bundle / "payload/snapshot"),
        "catalog": metadata["catalog"], "state": state["state"]}


def process_identity(pid: int) -> dict[str, Any]:
    try:
        process = psutil.Process(pid)
        return {"pid": pid, "birth_time": process.create_time()}
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        _fail("process identity unavailable")


def process_status(identity: dict[str, Any]) -> str:
    """Return exact instance facts; a zombie or inaccessible identity is uncertain."""
    validate_contract(identity, "processIdentity")
    try:
        process = psutil.Process(identity["pid"])
        if process.create_time() != identity["birth_time"]:
            return "gone"  # The old instance is absent; never signal the reused PID.
        if process.status() == psutil.STATUS_ZOMBIE:
            return "uncertain"
        return "alive" if process.is_running() else "gone"
    except psutil.NoSuchProcess:
        return "gone"
    except (psutil.AccessDenied, psutil.ZombieProcess):
        return "uncertain"


def _terminate_bridge(process: subprocess.Popen, identity: dict[str, Any], timeout: float) -> bool:
    try:
        if process.poll() is None:
            owned = psutil.Process(identity["pid"])
            if owned.create_time() != identity["birth_time"]:
                return False
            owned.terminate()
        process.wait(timeout=timeout)
        return True
    except (psutil.NoSuchProcess, ProcessLookupError):
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False
    except (psutil.AccessDenied, subprocess.TimeoutExpired):
        # Ordinary bounded bridge processes may be killed, then actually reaped.
        try:
            owned = psutil.Process(identity["pid"])
            if owned.create_time() != identity["birth_time"]:
                return False
            owned.kill()
            process.wait(timeout=timeout)
            return True
        except (psutil.Error, subprocess.TimeoutExpired):
            return False


def _bound_message(value: str | None) -> str | None:
    return value[:MESSAGE_LIMIT] if value else None


class _BridgeSession:
    """One invocation's exact mutable context, never an imported project callback."""
    def __init__(self, facts: dict[str, Any], directory: Path, lease: dict[str, Any]):
        self.facts, self.directory, self.lease = facts, directory, lease
        self.supervisor: subprocess.Popen | None = None
        self.running: tuple[subprocess.Popen, dict[str, Any], float] | None = None
        self.deadline: float | None = None

    def persist(self) -> None:
        _write(self.directory / "lease.json", self.lease)

    def invoke(self, role: str, action: str, selected: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        descriptor = self.facts["bridge_descriptors"][role]
        request = {"protocol": "phase-bridge-v1", "role": role, "action": action,
            "session_id": self.lease["session_id"], "plan_id": self.facts["plan_id"], "phase_id": self.facts["phase_id"],
            **{key: self.facts["runtime_bundle"][key] for key in ("payload_sha256", "snapshot_manifest_sha256", "snapshot_content_sha256")},
            "snapshot_root": self.facts["snapshot_root"], "session_root": str(self.directory),
            "configuration": self.lease["configuration"], "process_token": self.lease["process_token"], "endpoints": self.lease["endpoints"],
            "external_targets": [{**target, "permitted_actions": [action]} for target in descriptor["external_targets"] if action in target["permitted_actions"]]}
        if action == "run":
            request["selected"] = selected or []
        validate_contract(request, "request")
        request_path, response_path = self.directory / f"request-{action}.json", self.directory / f"response-{action}.json"
        if response_path.exists():
            _fail("bridge action cannot overwrite a prior response")
        timeout = descriptor["timeouts"]["invoke_seconds"]
        if action == "start":
            self.deadline = time.monotonic() + descriptor["timeouts"]["session_seconds"]
            timeout = min(timeout, descriptor["timeouts"]["session_seconds"])
        if action in {"readiness", "run"} and self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                _fail("foreground session timeout")
        _write(request_path, request)
        self.lease["pending_action"] = {"role": role, "action": action, "process": None}
        self.persist()
        process = subprocess.Popen([*descriptor["argv"], "--request", str(request_path), "--response", str(response_path)],
            cwd=_inside(Path(self.facts["snapshot_root"]), descriptor["working_directory"], directory=True),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        try:
            child = process_identity(process.pid)
        except PhaseDeliveryError:
            if process.poll() is not None and action != "start":
                child = None
            else:
                raise
        self.lease["pending_action"]["process"] = child
        self.persist()
        if child:
            self.running = (process, child, timeout)
        supervisor = action == "start" and descriptor["ownership"] == "child_process"
        deadline = time.monotonic() + timeout
        try:
            if supervisor:
                while not response_path.exists():
                    if process.poll() is not None:
                        _fail("start supervisor exited before response")
                    if time.monotonic() >= deadline:
                        _fail("start bridge timeout")
                    time.sleep(0.01)
            else:
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    _fail(f"{action} bridge timeout")
                if process.returncode:
                    _fail(f"{action} bridge exited {process.returncode}")
            response = _json(response_path)
            validate_contract(response, "response")
            for key in ("protocol", "role", "action", "session_id", "plan_id", "phase_id", "payload_sha256", "snapshot_manifest_sha256", "snapshot_content_sha256"):
                if response[key] != request[key]:
                    _fail("bridge response binding mismatch")
            if action not in {"configure", "start"} and any(response[key] != request[key] for key in ("configuration", "process_token", "endpoints")):
                _fail("bridge context/token mismatch")
            if action == "configure":
                configuration = response["configuration"]
                if configuration["external_references"] and not request["external_targets"]:
                    _fail("undeclared external configuration")
                for relative in configuration["produced_paths"]:
                    if not _inside(self.directory, relative).is_file():
                        _fail("configuration output is unavailable")
                self.lease["configuration"] = configuration
            if action == "start":
                if response["configuration"] != request["configuration"] or response["ownership"] != descriptor["ownership"]:
                    _fail("start context/ownership mismatch")
                if supervisor:
                    exit_code = process.poll()
                    status = process_status(child) if child is not None else "unavailable"
                    if response["pid"] != process.pid or child is None or exit_code is not None or status != "alive":
                        _fail(f"start response is not the owned supervisor (expected PID {process.pid}, reported PID {response['pid']}, status {status}, exit code {exit_code})")
                    self.supervisor = process
                    self.lease["child_identity"] = child
                self.lease["process_token"] = response["process_token"]
                self.lease["endpoints"] = response["endpoints"]
                self.lease["external_targets"] = request["external_targets"]
            if action == "stop":
                self.lease["stop_verified"] = response["success"] and response["stopped"] is True
            self.lease["last_completed_action"] = action
            self.lease["pending_action"] = None
            self.persist()
            response["message"] = _bound_message(response["message"])
            if not response["success"] and action != "run":
                _fail(response["message"] or f"{action} bridge returned false")
            return response
        finally:
            if not supervisor or self.supervisor is None:
                if child and not _terminate_bridge(process, child, timeout):
                    _fail("bridge termination could not be verified")
                if process.poll() is not None:
                    process.wait()
                self.running = None

    def cleanup(self, *, recovery: bool = False) -> None:
        pending = self.lease["pending_action"]
        if pending:
            # Missing start/configure context cannot prove effects gone.
            if pending["action"] in {"start", "configure"} or not pending["process"]:
                _fail("uncertain interrupted bridge context")
            if process_status(pending["process"]) != "gone":
                _fail("unverified interrupted bridge termination")
        if self.lease["process_token"]:
            descriptor = self.facts["bridge_descriptors"]["start_snapshot"]
            if descriptor["ownership"] == "child_process" and not self.lease["child_identity"]:
                _fail("missing supervisor identity; resource cleanup remains uncertain")
            if not self.lease["stop_verified"]:
                response = self.invoke("start_snapshot", "stop")
                if response["stopped"] is not True:
                    _fail("stop did not verify resource termination")
            child = self.lease["child_identity"]
            if child:
                timeout = self.facts["bridge_descriptors"]["start_snapshot"]["timeouts"]["invoke_seconds"]
                if self.supervisor is not None:
                    try:
                        self.supervisor.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        _fail("supervisor stop/reap timeout")
                else:
                    deadline = time.monotonic() + timeout
                    while process_status(child) != "gone" and time.monotonic() < deadline:
                        time.sleep(0.01)
                if process_status(child) != "gone":
                    _fail("supervisor termination/reap remains uncertain")
        self.lease["state"] = "closed"
        self.persist()
        _remove_tree(self.directory)


def _select(facts: dict[str, Any], selection: str, selector: str | None) -> list[dict[str, Any]]:
    catalog = facts["catalog"]
    if selection == "all":
        return catalog
    if selection == "serve":
        if not facts["identity"]["phase_delivery"]["snapshot"]["start_required"]:
            _fail("serve requires a start-required snapshot")
        return []
    if selection not in {"task", "test"} or not selector:
        _fail("invalid selection")
    selected = [row for row in catalog if row[selection] == selector]
    if not selected:
        _fail("unknown executable selection")
    return selected


def run_phase(workspace: Path, plan_id: str, phase_id: str, *, selection: str, selector: str | None = None, prepare: bool = False) -> dict[str, Any]:
    workspace = workspace.resolve()
    paths = runtime_paths(workspace, plan_id, phase_id)
    bundle = workspace / paths["relative_path"]
    with blocking_file_lock(bundle.parent / f".{phase_id}.lock"):
        facts = read_bundle(workspace, plan_id, phase_id)
        selected = _select(facts, selection, selector)
        descriptors = facts["bridge_descriptors"]
        if selection != "serve" and selected and "test_runner" not in descriptors:
            _fail("test selection requires test runner bridge")
        session_id = "session-" + uuid.uuid4().hex
        sessions = _inside(bundle, "sessions")
        if not sessions.is_dir():
            _fail("missing runtime sessions directory")
        directory = sessions / session_id
        directory.mkdir(mode=0o700)
        lease = {"protocol": "phase-session-lease-v1", "state": "active", "session_id": session_id,
            "plan_id": plan_id, "phase_id": phase_id, "payload_sha256": facts["runtime_bundle"]["payload_sha256"],
            "runner_identity": process_identity(os.getpid()), "configuration": {"produced_paths": [], "external_references": []},
            "process_token": None, "endpoints": [], "child_identity": None, "external_targets": [],
            "last_completed_action": None, "pending_action": None, "stop_verified": False}
        session = _BridgeSession(facts, directory, lease)
        session.persist()
    outcome = {"rows": [], "exit_code": 0, "message": None,
        "bridge_observations": {key: "not-required" for key in ("config_env", "start", "readiness", "stop")}}
    try:
        requirements = facts["identity"]["phase_delivery"]["bridges"]
        if "config_env" in descriptors and (prepare or requirements.get("config_env") == "required"):
            outcome["bridge_observations"]["config_env"] = "failed"
            session.invoke("config_env", "configure")
            outcome["bridge_observations"]["config_env"] = "passed"
        if facts["identity"]["phase_delivery"]["snapshot"]["start_required"]:
            outcome["bridge_observations"]["start"] = "failed"
            session.invoke("start_snapshot", "start")
            outcome["bridge_observations"]["start"] = "passed"
            outcome["bridge_observations"]["readiness"] = "failed"
            session.invoke("start_snapshot", "readiness")
            outcome["bridge_observations"]["readiness"] = "passed"
        if selection == "serve":
            print("snapshot ready", flush=True)
            deadline = session.deadline
            while time.monotonic() < deadline:
                if session.supervisor and session.supervisor.poll() is not None:
                    outcome["message"] = f"supervisor exited {session.supervisor.returncode}"
                    outcome["exit_code"] = int(session.supervisor.returncode != 0)
                    break
                time.sleep(0.05)
            else:
                _fail("foreground session timeout")
        elif selected:
            response = session.invoke("test_runner", "run", selected)
            rows = response["rows"]
            if [(row["task"], row["test"]) for row in rows] != [(row["task"], row["test"]) for row in selected]:
                _fail("test response selection mismatch")
            outcome["rows"] = [{**row, "message": _bound_message(row["message"])} for row in rows]
            outcome["exit_code"] = int(not response["success"] or any(not row["passes"] for row in rows))
    except KeyboardInterrupt:
        outcome.update(exit_code=130, message="interrupted")
    except (PhaseDeliveryError, OSError) as error:
        outcome.update(exit_code=1, message=_bound_message(str(error)))
    finally:
        try:
            session.cleanup()
            if lease["process_token"]:
                outcome["bridge_observations"]["stop"] = "passed"
        except (PhaseDeliveryError, OSError) as error:
            outcome.update(exit_code=1, message=_bound_message("; ".join(filter(None, [outcome["message"], str(error)]))))
            outcome["bridge_observations"]["stop"] = "failed"
    # Payload changes from a bridge invalidate observations without semantic diagnosis.
    try:
        _verify_payload(bundle, _state(workspace, plan_id, phase_id)[0])
    except PhaseDeliveryError as error:
        outcome.update(exit_code=1, message=_bound_message("; ".join(filter(None, [outcome["message"], str(error)]))))
    return outcome


def _lease_preflight(facts: dict[str, Any], sessions: Path) -> list[dict[str, Any]]:
    observations = []
    if not sessions.is_dir():
        _fail("missing sessions directory")
    for directory in sorted(sessions.iterdir()):
        if is_link_like(directory) or not directory.is_dir() or not re.fullmatch(r"session-[a-f0-9]{32}", directory.name):
            _fail("unsafe or unexplained session entry")
        lease = _json(directory / "lease.json")
        validate_contract(lease, "lease")
        if lease.get("protocol") != "phase-session-lease-v1" or lease.get("session_id") != directory.name or lease.get("plan_id") != facts["plan_id"] or lease.get("phase_id") != facts["phase_id"] or lease.get("payload_sha256") != facts["runtime_bundle"]["payload_sha256"]:
            _fail("session lease identity mismatch")
        if lease.get("state") == "closed":
            observations.append({"directory": str(directory), "lease": lease, "recovery": False})
            continue
        if process_status(lease["runner_identity"]) != "gone":
            _fail("live or uncertain runner lease")
        if lease["pending_action"]:
            pending = lease["pending_action"]
            if pending["action"] in {"configure", "start"} or not pending["process"] or process_status(pending["process"]) != "gone":
                _fail("uncertain crashed session resource context")
        if lease["process_token"]:
            descriptor = facts["bridge_descriptors"].get("start_snapshot")
            if not descriptor or not lease["configuration"] or (descriptor["ownership"] == "child_process" and not lease["child_identity"]) or (descriptor["ownership"] == "external" and not lease["external_targets"]):
                _fail("missing crashed session stop context")
            if lease["child_identity"] and process_status(lease["child_identity"]) == "uncertain":
                _fail("uncertain crashed child identity")
        observations.append({"directory": str(directory), "lease": lease, "recovery": True})
    return observations


def preflight_cleanup(workspace: Path, plan_id: str, phase_id: str, *, reason: str = "explicit_release", expected: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure verification for all-target callers; never stop/reap during preflight."""
    if reason not in {"explicit_release", "finalization"}:
        _fail("invalid cleanup reason")
    workspace = workspace.resolve()
    state, paths = _state(workspace, plan_id, phase_id)
    policy = resolve_phase_authority(workspace, plan_id, phase_id)
    _authority_matches(workspace, state, policy, release=True)
    if reason == "finalization" and not policy["accepted"]:
        _fail("finalization requires exact accepted handoff")
    if expected is not None and expected != state["runtime_bundle"]:
        _fail("cleanup expected handoff mismatch")
    bundle = workspace / paths["relative_path"]
    leases = []
    if state["state"] == "cleaned":
        if bundle.exists() or state["reason"] not in {"explicit_release", "finalization"}:
            _fail("unexplained cleaned runtime state")
    elif state["state"] in {"active", "cleaning"}:
        if bundle.exists():
            if state["state"] == "cleaning":
                # Cleanup already verified leases and froze all deletion authority.
                # Validate remaining bytes against that stored manifest, not deleted files.
                expected_entries = [{"path": "payload", "kind": "directory"}, {"path": "sessions", "kind": "directory"}]
                expected_entries.extend({**entry, "path": "payload/" + entry["path"]} for entry in state["payload_manifest"]["entries"])
                expected_entries.append({"path": "payload/payload-manifest.json", "kind": "file", "sha256": hashlib.sha256(_bytes(state["payload_manifest"])).hexdigest()})
                by_path = {entry["path"]: entry for entry in expected_entries}
                for entry in _tree_entries(bundle):
                    expected_entry = by_path.get(entry["path"])
                    if not expected_entry or any(entry.get(key) != expected_entry.get(key) for key in ("kind", "sha256")):
                        _fail("cleaning residue identity mismatch")
            else:
                metadata = _verify_payload(bundle, state)
                facts = {"plan_id": plan_id, "phase_id": phase_id, "runtime_bundle": state["runtime_bundle"],
                    "snapshot_root": str(bundle / "payload/snapshot"), "identity": metadata,
                    "bridge_descriptors": {path.stem: _json(path) for path in sorted((bundle / "payload/bridges").glob("*.json"))}}
                _descriptors(Path(facts["snapshot_root"]), {"protocol": "phase-bridge-v1", "bridges": facts["bridge_descriptors"]}, policy)
                leases = _lease_preflight(facts, _inside(bundle, "sessions"))
        elif state["state"] != "cleaning":
            _fail("unexplained missing active payload")
    else:
        _fail("unpublished runtime cannot be released")
    return {"state": state["state"], "runtime_bundle": state["runtime_bundle"], "leases": leases}


def release_bundle(workspace: Path, plan_id: str, phase_id: str, *, reason: str, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    workspace = workspace.resolve()
    paths = runtime_paths(workspace, plan_id, phase_id)
    bundle = workspace / paths["relative_path"]
    with blocking_file_lock(bundle.parent / f".{phase_id}.lock"):
        checked = preflight_cleanup(workspace, plan_id, phase_id, reason=reason, expected=expected)
        state, _ = _state(workspace, plan_id, phase_id)
        if state["state"] == "cleaned":
            return checked
        if checked["leases"]:
            facts = read_bundle(workspace, plan_id, phase_id, check_authority=False)
            for item in checked["leases"]:
                directory = Path(item["directory"])
                if item["recovery"]:
                    _BridgeSession(facts, directory, item["lease"]).cleanup(recovery=True)
                else:
                    _remove_tree(directory)
        state["state"], state["reason"] = "cleaning", reason
        _write(workspace / paths["state_relative_path"], state)
        _remove_tree(bundle)
        state["state"] = "cleaned"
        _write(workspace / paths["state_relative_path"], state)
        return {"state": "cleaned", "runtime_bundle": state["runtime_bundle"]}


def release_phase_snapshot(workspace: Path, plan_id: str, phase_id: str) -> dict[str, Any]:
    return release_bundle(workspace, plan_id, phase_id, reason="explicit_release")


def read_cleaned_state(workspace: Path, plan_id: str, phase_id: str, *, expected: dict[str, Any]) -> dict[str, Any]:
    """Pure exact-state check; caller verifies its accepted/archive chain."""
    state, paths = _state(workspace.resolve(), plan_id, phase_id)
    if (state["state"] != "cleaned" or state["reason"] not in {"explicit_release", "finalization"}
            or state["runtime_bundle"] != expected or (workspace / paths["relative_path"]).exists()):
        _fail("runtime state is not exactly cleaned")
    return {"state": "cleaned", "runtime_bundle": state["runtime_bundle"]}


def remove_cleaned_state(workspace: Path, plan_id: str, phase_id: str, *, expected: dict[str, Any]) -> None:
    """Post-archive caller owns archive authority; remove only matching cleaned facts."""
    read_cleaned_state(workspace, plan_id, phase_id, expected=expected)
    paths = runtime_paths(workspace.resolve(), plan_id, phase_id)
    parent = (workspace / paths["relative_path"]).parent
    lock = parent / f".{phase_id}.lock"
    # Lifecycle caller has completed all cleanup; lock files are not removed mid-run.
    _inside(workspace, lock.relative_to(workspace).as_posix())
    lock.unlink(missing_ok=True)
    (workspace / paths["state_relative_path"]).unlink()
    prune_removed_runtime(workspace, plan_id, phase_id, expected=expected)


def read_removed_runtime(workspace: Path, plan_id: str, phase_id: str, *, expected: dict[str, Any]) -> dict[str, Any]:
    """Pure post-archive absence facts; caller validates the exact archive chain."""
    workspace = workspace.resolve()
    paths = runtime_paths(workspace, plan_id, phase_id)
    if any(expected.get(key) != value for key, value in paths.items()):
        _fail("removed runtime path mismatch")
    parent = (workspace / paths["relative_path"]).parent
    for relative in (paths["relative_path"], paths["state_relative_path"],
                     (parent / f".{phase_id}.lock").relative_to(workspace).as_posix()):
        if _inside(workspace, relative).exists():
            _fail("removed runtime retains payload, state or unexplained lock")
    return {"state": "removed", "runtime_bundle": expected}


def prune_removed_runtime(workspace: Path, plan_id: str, phase_id: str, *, expected: dict[str, Any]) -> None:
    """Finish only empty canonical parent removal after exact archive validation."""
    workspace = workspace.resolve()
    read_removed_runtime(workspace, plan_id, phase_id, expected=expected)
    parent = (workspace / runtime_paths(workspace, plan_id, phase_id)["relative_path"]).parent
    for directory in (parent, parent.parent):
        try:
            directory.rmdir()
        except OSError as error:
            if error.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
                raise


def _print_rows(rows: list[dict[str, Any]]) -> None:
    print("| Task | Test | Passes | Message |\n| --- | --- | --- | --- |")
    for row in rows:
        values = [row["task"], row["test"], str(row["passes"]).lower(), row["message"] or ""]
        print("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in values) + " |")


def cmd_materialize_phase_handoff(args: argparse.Namespace) -> None:
    try:
        facts = materialize_phase_handoff(resolve_workspace_root(args), args.plan_id, args.phase_id, args.task_id, args.bridge_manifest, args.candidate_file)
        print(json.dumps(facts, sort_keys=True))
    except PhaseDeliveryError as error:
        raise SystemExit(str(error)) from error


def cmd_run_phase(args: argparse.Namespace) -> None:
    selection = "serve" if args.serve else "all" if args.all else "task" if args.task else "test"
    try:
        outcome = run_phase(resolve_workspace_root(args), args.plan_id, args.phase_id, selection=selection, selector=args.task or args.test, prepare=args.prepare)
    except PhaseDeliveryError as error:
        raise SystemExit(str(error)) from error
    if selection != "serve":
        _print_rows(outcome["rows"])
    if outcome["message"]:
        print(outcome["message"])
    if outcome["exit_code"]:
        raise SystemExit(outcome["exit_code"])


def cmd_release_phase_snapshot(args: argparse.Namespace) -> None:
    try:
        print(json.dumps(release_phase_snapshot(resolve_workspace_root(args), args.plan_id, args.phase_id), sort_keys=True))
    except PhaseDeliveryError as error:
        raise SystemExit(str(error)) from error
