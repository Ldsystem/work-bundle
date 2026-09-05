#!/usr/bin/env python3
"""Typed completion ownership and reusable observation provenance."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import platform
import re
import sys
import tempfile
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
CWD_TOKENS = frozenset({"workspace_root", "bound_project_root", "isolated_execution_root"})
TARGET_KINDS = frozenset({"local_project", "git_backed", "isolated_worktree"})
OWNERSHIP_STATES = frozenset({"active", "repair_owned", "rereview_owned", "releasable", "released"})
OWNERSHIP_FIELDS = frozenset({
    "binding_id", "target_kind", "state", "original_owner", "current_owner", "reason",
    "repair_owner", "rereview_owner", "releasable", "history",
})
OBSERVATION_IDENTITY_FIELDS = (
    "command_digest",
    "cwd_token",
    "product_tree",
    "state_digest",
    "oracle_digest",
    "mutation_epoch",
)


class CompletionProvenanceError(ValueError):
    pass


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CompletionProvenanceError(f"{name} must be a non-empty stable identifier")
    return value


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompletionProvenanceError(f"{name} must be a non-empty string")
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CompletionProvenanceError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CompletionProvenanceError(f"{name} must be RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise CompletionProvenanceError(f"{name} must be RFC3339 UTC") from error
    return parsed.astimezone(timezone.utc)


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class ManagedProvenanceStore:
    """One lock-protected store owning IDs, bindings, observations and epochs."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "completion-provenance-v1.json"
        self.lock_path = self.root / ".completion-provenance-v1.lock"

    @contextmanager
    def locked(self):
        self.lock_path.touch(mode=0o600, exist_ok=True)
        with self.lock_path.open("r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "completion-provenance-store-v1", "mutation_epoch": 0,
                    "identities": {}, "bindings": {}, "observations": [], "consumptions": {}}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CompletionProvenanceError("managed provenance store is unreadable") from error
        if state.get("schema") != "completion-provenance-store-v1":
            raise CompletionProvenanceError("managed provenance store schema is invalid")
        return state

    @contextmanager
    def observation_reservation(self, request: Mapping[str, Any]):
        """Identity-local single flight; the OS releases reservations on process death.

        Never remove lock files: unlinking a lock can split waiters across inodes.
        The shared store lock is acquired only inside this reservation, never vice versa.
        """
        identity = _canonical_digest({key: request[key] for key in OBSERVATION_IDENTITY_FIELDS})
        path = self.root / f".observation-{identity}.lock"
        with path.open("a+") as reservation:
            fcntl.flock(reservation.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(reservation.fileno(), fcntl.LOCK_UN)

    def _write_unlocked(self, state: Mapping[str, Any]) -> None:
        payload = json.dumps(state, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        fd, raw_path = tempfile.mkstemp(prefix=".completion-provenance-", dir=self.root)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(raw_path, self.path)
        finally:
            if os.path.exists(raw_path):
                os.unlink(raw_path)

    @staticmethod
    def _register_unlocked(state: dict[str, Any], identity: str, kind: str) -> None:
        _identifier(identity, "identity")
        existing = state["identities"].get(identity)
        if existing is not None:
            raise CompletionProvenanceError(f"identity {identity} is already registered as {existing}")
        state["identities"][identity] = kind

    @property
    def mutation_epoch(self) -> int:
        with self.locked():
            return int(self._read_unlocked()["mutation_epoch"])


def _transition_id() -> str:
    return f"transition-{uuid.uuid4()}"


@dataclass(frozen=True)
class FailureOwnershipV1:
    binding_id: str
    target_kind: str
    state: str
    original_owner: str
    current_owner: str
    reason: str
    repair_owner: str | None
    rereview_owner: str | None
    releasable: bool
    history: tuple[Mapping[str, Any], ...]
    _store: ManagedProvenanceStore = field(repr=False, compare=False)

    @classmethod
    def create(
        cls,
        store: ManagedProvenanceStore,
        binding_id: str,
        target_kind: str,
        owner: str,
        reason: str = "binding created",
    ) -> "FailureOwnershipV1":
        _identifier(binding_id, "binding_id")
        if target_kind not in TARGET_KINDS:
            raise CompletionProvenanceError("target_kind is invalid")
        _identifier(owner, "owner")
        transition = {
            "transition_id": _transition_id(), "from": "active", "to": "active",
            "owner": owner, "reason": reason, "timestamp": _now_text(),
        }
        binding = cls(binding_id, target_kind, "active", owner, owner, reason, None, None, False,
                      (transition,), store)
        with store.locked():
            state = store._read_unlocked()
            store._register_unlocked(state, binding_id, "execution_binding")
            store._register_unlocked(state, transition["transition_id"], "ownership_transition")
            state["bindings"][binding_id] = binding.to_dict()
            store._write_unlocked(state)
        return binding

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id, "target_kind": self.target_kind, "state": self.state,
            "original_owner": self.original_owner, "current_owner": self.current_owner,
            "reason": self.reason, "repair_owner": self.repair_owner,
            "rereview_owner": self.rereview_owner, "releasable": self.releasable,
            "history": deepcopy(list(self.history)),
        }

    def _move(self, *, to: str, owner: str, reason: str, repair_owner: str | None,
              rereview_owner: str | None, releasable: bool, current_owner: str,
              binding_reason: str | None = None) -> "FailureOwnershipV1":
        if to not in OWNERSHIP_STATES:
            raise CompletionProvenanceError("ownership state is invalid")
        _identifier(owner, "owner")
        _identifier(current_owner, "current_owner")
        if repair_owner is not None:
            _identifier(repair_owner, "repair_owner")
        if rereview_owner is not None:
            _identifier(rereview_owner, "rereview_owner")
        transition = {"transition_id": _transition_id(), "from": self.state, "to": to,
                      "owner": owner, "reason": reason, "timestamp": _now_text()}
        updated = replace(self, state=to, current_owner=current_owner,
                          reason=self.reason if binding_reason is None else binding_reason,
                          repair_owner=repair_owner,
                          rereview_owner=rereview_owner, releasable=releasable,
                          history=self.history + (transition,))
        with self._store.locked():
            state = self._store._read_unlocked()
            current = state["bindings"].get(self.binding_id)
            if current != self.to_dict():
                raise CompletionProvenanceError("binding changed concurrently")
            self._store._register_unlocked(state, transition["transition_id"], "ownership_transition")
            state["bindings"][self.binding_id] = updated.to_dict()
            self._store._write_unlocked(state)
        return updated

    def record_failure(self, owner: str, reason: str) -> "FailureOwnershipV1":
        if self.state == "released":
            raise CompletionProvenanceError("released binding is terminal")
        _identifier(owner, "repair owner")
        failure_reason = self.reason if self.state in {"repair_owned", "rereview_owned"} else _nonempty(reason, "reason")
        return self._move(
            to="repair_owned", owner=owner, reason=failure_reason, repair_owner=owner,
            rereview_owner=None, releasable=False, current_owner=owner, binding_reason=failure_reason,
        )

    def complete_repair(self, owner: str, rereview_owner: str) -> "FailureOwnershipV1":
        validate_resume_owner(self, owner)
        if self.state != "repair_owned" or self.repair_owner != owner:
            raise CompletionProvenanceError("repair may only be completed by the repair owner")
        _identifier(rereview_owner, "rereview owner")
        return self._move(to="rereview_owned", owner=owner, reason=self.reason, repair_owner=None,
                          rereview_owner=rereview_owner, releasable=False, current_owner=rereview_owner)

    def complete_rereview(self, owner: str) -> "FailureOwnershipV1":
        validate_resume_owner(self, owner)
        if self.state != "rereview_owned" or self.rereview_owner != owner:
            raise CompletionProvenanceError("rereview may only be completed by the rereview owner")
        return self._move(to="releasable", owner=owner, reason=self.reason, repair_owner=None,
                          rereview_owner=None, releasable=True, current_owner=self.original_owner)

    def mark_releasable(self, owner: str) -> "FailureOwnershipV1":
        if self.repair_owner is not None:
            raise CompletionProvenanceError("repair owner must clear before release")
        if self.rereview_owner is not None:
            raise CompletionProvenanceError("rereview owner must clear before release")
        validate_resume_owner(self, owner)
        return self._move(to="releasable", owner=owner, reason=self.reason, repair_owner=None,
                          rereview_owner=None, releasable=True, current_owner=self.original_owner)

    def release(self, owner: str) -> "FailureOwnershipV1":
        if self.state == "released":
            return self
        if self.state != "releasable" or not self.releasable:
            raise CompletionProvenanceError("binding is not releasable")
        if self.repair_owner is not None or self.rereview_owner is not None:
            raise CompletionProvenanceError("binding owners must clear before release")
        if owner != self.original_owner:
            raise CompletionProvenanceError("release requires original owner")
        return self._move(to="released", owner=owner, reason=self.reason, repair_owner=None,
                          rereview_owner=None, releasable=True, current_owner=self.original_owner)


def validate_resume_owner(binding: FailureOwnershipV1 | Mapping[str, Any], owner: str) -> bool:
    current = binding.current_owner if isinstance(binding, FailureOwnershipV1) else binding.get("current_owner")
    if owner != current:
        raise CompletionProvenanceError(f"resume requires current owner {current}")
    return True


def _validate_ownership_shape(ownership: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(ownership, Mapping) or set(ownership) != OWNERSHIP_FIELDS:
        raise CompletionProvenanceError("execution binding ownership fields are not closed and complete")
    _identifier(ownership["binding_id"], "binding_id")
    if ownership["target_kind"] not in TARGET_KINDS:
        raise CompletionProvenanceError("execution binding ownership target_kind is invalid")
    if ownership["state"] not in OWNERSHIP_STATES:
        raise CompletionProvenanceError("execution binding ownership state is invalid")
    for field_name in ("original_owner", "current_owner"):
        _identifier(ownership[field_name], field_name)
    _nonempty(ownership["reason"], "reason")
    for field_name in ("repair_owner", "rereview_owner"):
        value = ownership[field_name]
        if value is not None:
            _identifier(value, field_name)
    if not isinstance(ownership["releasable"], bool):
        raise CompletionProvenanceError("execution binding ownership releasable must be boolean")
    history = ownership["history"]
    if not isinstance(history, list) or not history:
        raise CompletionProvenanceError("execution binding ownership history must be non-empty")
    transition_fields = {"transition_id", "from", "to", "owner", "reason", "timestamp"}
    for transition in history:
        if not isinstance(transition, Mapping) or set(transition) != transition_fields:
            raise CompletionProvenanceError("execution binding ownership history is invalid")
        _identifier(transition["transition_id"], "transition_id")
        if transition["from"] not in OWNERSHIP_STATES or transition["to"] not in OWNERSHIP_STATES:
            raise CompletionProvenanceError("execution binding ownership transition state is invalid")
        _identifier(transition["owner"], "transition owner")
        _nonempty(transition["reason"], "transition reason")
        _utc(transition["timestamp"], "transition timestamp")
    return deepcopy(dict(ownership))


def validate_ownership_shape(ownership: Mapping[str, Any]) -> dict[str, Any]:
    """Validate API-006 without asserting membership in a particular managed store."""

    return _validate_ownership_shape(ownership)


def _load_failure_ownership(store: ManagedProvenanceStore, binding_id: str) -> FailureOwnershipV1:
    _identifier(binding_id, "binding_id")
    with store.locked():
        state = store._read_unlocked()
        raw = state.get("bindings", {}).get(binding_id)
    if raw is None:
        raise CompletionProvenanceError("execution binding does not exist")
    ownership = _validate_ownership_shape(raw)
    ownership["history"] = tuple(ownership["history"])
    return FailureOwnershipV1(**ownership, _store=store)


_STAGE_EVENTS_MODULE = None


def _stage_events_module():
    global _STAGE_EVENTS_MODULE
    if _STAGE_EVENTS_MODULE is None:
        path = Path(__file__).resolve().parents[1] / "work-bundle" / "stage_events.py"
        spec = importlib.util.spec_from_file_location("_completion_stage_events", path)
        if spec is None or spec.loader is None:
            raise CompletionProvenanceError("stage event API is unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _STAGE_EVENTS_MODULE = module
    return _STAGE_EVENTS_MODULE


def _emit_native_stage_event(
    workspace: str | Path | None,
    template: Mapping[str, Any] | None,
    *,
    event_type: str,
    owner: str | None = None,
    mutation_epoch: int | None = None,
) -> None:
    if workspace is None and template is None:
        return
    if workspace is None or not isinstance(template, Mapping):
        raise CompletionProvenanceError("native stage event workspace and template are both required")
    payload = deepcopy(dict(template))
    payload["event_id"] = f"event-{uuid.uuid4()}"
    payload["event_type"] = event_type
    payload["enforcement_mode"] = "native"
    if owner is not None:
        payload["owner"] = owner
    if mutation_epoch is not None:
        identity = payload.get("identity")
        if not isinstance(identity, Mapping):
            raise CompletionProvenanceError("native stage event identity is required")
        payload["identity"] = {**identity, "mutation_epoch": mutation_epoch}
    try:
        _stage_events_module().append_stage_event(Path(workspace), payload)
    except Exception as error:
        raise CompletionProvenanceError("native stage event emission failed") from error


def resolve_completion_owner(store: ManagedProvenanceStore, binding_id: str) -> str:
    """Return the only owner currently authorized to resume the binding."""

    return _load_failure_ownership(store, binding_id).current_owner


def retain_binding_owner(
    store: ManagedProvenanceStore,
    binding_id: str,
    *,
    repair_owner: str,
    reason: str,
    stage_event_workspace: str | Path | None = None,
    stage_event: Mapping[str, Any] | None = None,
) -> FailureOwnershipV1:
    """Assign typed repair ownership without losing the original lifecycle owner."""

    binding = _load_failure_ownership(store, binding_id)
    if binding.state == "repair_owned" and binding.repair_owner == repair_owner:
        retained = binding
    else:
        retained = binding.record_failure(repair_owner, reason)
    _emit_native_stage_event(
        stage_event_workspace,
        stage_event,
        event_type="binding_retained",
        owner=retained.current_owner,
        mutation_epoch=store.mutation_epoch,
    )
    return retained


def resume_failed_stage(
    store: ManagedProvenanceStore,
    binding_id: str,
    *,
    owner: str,
    stage_event_workspace: str | Path | None = None,
    stage_event: Mapping[str, Any] | None = None,
) -> FailureOwnershipV1:
    """Validate the current repair or rereview owner before resuming work."""

    binding = _load_failure_ownership(store, binding_id)
    validate_resume_owner(binding, owner)
    if binding.state not in {"repair_owned", "rereview_owned"}:
        raise CompletionProvenanceError("resume requires a failed stage owner")
    _emit_native_stage_event(
        stage_event_workspace,
        stage_event,
        event_type="stage_started",
        owner=owner,
        mutation_epoch=store.mutation_epoch,
    )
    return binding


def release_completion_binding(
    store: ManagedProvenanceStore,
    binding_id: str,
    *,
    owner: str,
    stage_event_workspace: str | Path | None = None,
    stage_event: Mapping[str, Any] | None = None,
) -> FailureOwnershipV1:
    """Release only a releasable binding whose repair and rereview owners cleared."""

    binding = _load_failure_ownership(store, binding_id)
    if binding.state == "released":
        return binding
    if binding.state == "active":
        binding = binding.mark_releasable(owner)
    released = binding.release(owner)
    _emit_native_stage_event(
        stage_event_workspace,
        stage_event,
        event_type="binding_released",
        owner=released.original_owner,
        mutation_epoch=store.mutation_epoch,
    )
    return released


@dataclass(frozen=True)
class ObservationIdentityV1:
    observation_id: str
    command_digest: str
    cwd_token: str
    product_tree: str
    state_digest: str
    oracle_digest: str
    freshness_deadline: str
    mutation_epoch: int
    invocation_id: str
    result: Mapping[str, Any]
    reuse_of: str | None
    consumed_by_finalization: str | None

    def to_dict(self) -> dict[str, Any]:
        return {name: deepcopy(getattr(self, name)) for name in self.__dataclass_fields__}


def _validate_observation_request(request: Mapping[str, Any], now: datetime) -> None:
    required = {"observation_id", "command_digest", "cwd_token", "product_tree", "state_digest",
                "oracle_digest", "freshness_deadline", "mutation_epoch", "invocation_id"}
    if set(request) != required:
        raise CompletionProvenanceError("observation request fields are not closed and complete")
    _identifier(request["observation_id"], "observation_id")
    _identifier(request["invocation_id"], "invocation_id")
    _digest(request["command_digest"], "command_digest")
    _digest(request["state_digest"], "state_digest")
    _digest(request["oracle_digest"], "oracle_digest")
    if request["cwd_token"] not in CWD_TOKENS:
        raise CompletionProvenanceError("cwd_token is invalid")
    if not isinstance(request["product_tree"], str) or not GIT_OID_RE.fullmatch(request["product_tree"]):
        raise CompletionProvenanceError("product_tree must be a Git tree id")
    if not isinstance(request["mutation_epoch"], int) or isinstance(request["mutation_epoch"], bool) or request["mutation_epoch"] < 0:
        raise CompletionProvenanceError("mutation_epoch must be a nonnegative integer")
    if _utc(request["freshness_deadline"], "freshness_deadline") < now:
        raise CompletionProvenanceError("observation freshness deadline has expired")


def _validate_result(result: Mapping[str, Any]) -> None:
    required = {"exit_code", "stdout_digest", "stderr_digest", "started_at", "completed_at"}
    if not isinstance(result, Mapping) or set(result) != required:
        raise CompletionProvenanceError("observation result fields are not closed and complete")
    if not isinstance(result["exit_code"], int) or isinstance(result["exit_code"], bool):
        raise CompletionProvenanceError("exit_code must be an integer")
    _digest(result["stdout_digest"], "stdout_digest")
    _digest(result["stderr_digest"], "stderr_digest")
    if _utc(result["completed_at"], "completed_at") < _utc(result["started_at"], "started_at"):
        raise CompletionProvenanceError("observation result timestamps are reversed")


def reuse_observation(
    store: ManagedProvenanceStore,
    request: Mapping[str, Any],
    execute: Callable[[], Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> ObservationIdentityV1:
    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _validate_observation_request(request, observed_at)
    with store.observation_reservation(request):
        with store.locked():
            observed_at = now or datetime.now(timezone.utc)
            _validate_observation_request(request, observed_at)
            state = store._read_unlocked()
            if request["mutation_epoch"] != state["mutation_epoch"]:
                raise CompletionProvenanceError("observation mutation epoch is stale")
            for raw in reversed(state["observations"]):
                if all(raw[field] == request[field] for field in OBSERVATION_IDENTITY_FIELDS) and (
                    _utc(raw["freshness_deadline"], "freshness_deadline") >= observed_at
                ):
                    _validate_result(raw["result"])
                    return ObservationIdentityV1(**{**raw,
                        "invocation_id": request["invocation_id"], "reuse_of": raw["observation_id"],
                        "consumed_by_finalization": state["consumptions"].get(raw["observation_id"]),
                    })
            store._register_unlocked(state, request["observation_id"], "observation")
            # Check collisions now, but persist the ID only with its result.
            # A failed/crashed execution must not strand an unpublished ID.
        # Independent identities and nested store operations are not serialized.
        result = execute()
        _validate_result(result)
        observation = ObservationIdentityV1(
            **request,
            result=deepcopy(dict(result)),
            reuse_of=None,
            consumed_by_finalization=None,
        )
        with store.locked():
            state = store._read_unlocked()
            _validate_observation_request(request, now or datetime.now(timezone.utc))
            if request["mutation_epoch"] != state["mutation_epoch"]:
                raise CompletionProvenanceError("observation mutation epoch changed during execution")
            store._register_unlocked(state, request["observation_id"], "observation")
            state["observations"].append(observation.to_dict())
            store._write_unlocked(state)
        return observation


def validation_reuse_policy(item: Mapping[str, Any]) -> dict[str, Any]:
    """Compile explicit evidence policy; legacy reuse_seconds remains an opt-in."""
    raw = item.get("evidence_reuse", {})
    fields = {"mode", "max_age_seconds", "environment_inputs", "dependency_files", "output_paths", "profile", "include_head"}
    if not isinstance(raw, dict) or set(raw) - fields:
        raise CompletionProvenanceError("evidence_reuse has unknown or invalid fields")
    legacy = item.get("reuse_seconds", 0)
    if type(legacy) is not int or not 0 <= legacy <= 86400:
        raise CompletionProvenanceError("validation reuse_seconds must be an integer from 0 to 86400")
    mode = raw.get("mode", "deterministic" if legacy else "live")
    if not isinstance(mode, str) or mode not in {"deterministic", "live"}:
        raise CompletionProvenanceError("evidence_reuse.mode must be deterministic or live")
    seconds = raw.get("max_age_seconds", legacy if "reuse_seconds" in item else (3600 if mode == "deterministic" else 0))
    if type(seconds) is not int or not 0 <= seconds <= 86400:
        raise CompletionProvenanceError("evidence_reuse.max_age_seconds must be an integer from 0 to 86400")
    if "reuse_seconds" in item and "max_age_seconds" in raw and legacy != seconds:
        raise CompletionProvenanceError("conflicting evidence freshness policies")
    policy = {"mode": mode, "max_age_seconds": seconds}
    for key in ("environment_inputs", "dependency_files", "output_paths"):
        values = raw.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise CompletionProvenanceError(f"evidence_reuse.{key} must be a string list")
        if key == "environment_inputs":
            if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v) for v in values):
                raise CompletionProvenanceError("environment_inputs must name explicit variables")
        elif any(Path(v).is_absolute() or ".." in Path(v).parts or v in {".", "./"} or any(c in v for c in "*?[") for v in values):
            raise CompletionProvenanceError(f"evidence_reuse.{key} must contain exact repository-relative paths")
        policy[key] = sorted(set(values))
    policy["profile"] = raw.get("profile", "")
    policy["include_head"] = raw.get("include_head", "reuse_seconds" in item)
    if not isinstance(policy["profile"], str) or type(policy["include_head"]) is not bool:
        raise CompletionProvenanceError("evidence_reuse profile/include_head has invalid type")
    return policy


def validation_environment_identity(root: Path, policy: Mapping[str, Any]) -> dict[str, Any]:
    """Semantic platform/runtime and declared inputs; never persist environment values."""
    dependencies = {}
    for relative in policy["dependency_files"]:
        path = root / relative
        if "credentials" in path.resolve().parts or path.resolve().name == ".env" or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise CompletionProvenanceError("protected or escaping dependency identity")
        if not path.is_file():
            raise CompletionProvenanceError(f"dependency identity unavailable: {relative}")
        dependencies[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "os": platform.system(), "architecture": platform.machine(),
        "runtime": {"implementation": platform.python_implementation(), "version": platform.python_version(),
                    "executable_digest": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()},
        "dependencies": dependencies, "profile": policy["profile"],
        "environment_digest": _canonical_digest({name: os.environ.get(name) for name in policy["environment_inputs"]}),
    }


class _UnrecordedValidation(Exception):
    """A failed or skipped result must not become reusable positive evidence."""


def observe_validation(
    binding: Mapping[str, Any], task: Mapping[str, Any], item: Mapping[str, Any],
    evidence: Mapping[str, Any], execute: Callable[[dict[str, Any]], dict[str, Any]],
    capture: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Project validation onto the existing source/evidence and observation identities."""
    from evaluation_identity import EvaluationIdentityError, validation_source_identity

    policy = validation_reuse_policy(item)
    if not policy["max_age_seconds"] or str(item.get("expected", "")).lower() in {"skip", "skipped"}:
        return execute({})
    root = Path(binding["execution_path"]).resolve()
    files = task.get("files", {})
    input_paths = [*files.get("read", []), *files.get("write", []), *policy["dependency_files"]]
    # An explicit read/dependency cannot simultaneously be declared output-only.
    for source in [*files.get("read", []), *policy["dependency_files"]]:
        if any(source == output or source.startswith(output.rstrip("/") + "/") for output in policy["output_paths"]):
            raise CompletionProvenanceError("validation input overlaps observation output")

    def source_identity():
        return validation_source_identity(root, input_paths=input_paths, output_paths=policy["output_paths"])

    try:
        source = source_identity()
    except EvaluationIdentityError:
        # Unsupported links/protected inputs are observed afresh, not approximated.
        return execute({})
    environment = validation_environment_identity(root, policy)
    # This is the same managed store already owning execution bindings and epochs.
    store = ManagedProvenanceStore(Path(binding["control_root"]) / ".work-bundle/runtime/completion-provenance")
    bound = {key: binding[key] for key in ("workspace_id", "execution_id", "repository_id", "plan_id", "task_id", "execution_path")}
    definition = {key: item.get(key) for key in ("id", "kind", "command", "mechanism", "expected", "acceptable_results", "invariant_ids", "digest", "proves")}
    helper_dir = Path(__file__).parent
    runners = {name: hashlib.sha256((helper_dir / name).read_bytes()).hexdigest() for name in (
        "completion_provenance.py", "execution_context.py", "evaluation_identity.py", "repository_preflight.py",
    )}
    authority = {key: task.get(key) for key in ("source_ids", "requirements", "constraints", "interfaces", "truth_basis", "files", "evidence_capability")}
    current = datetime.now(timezone.utc)
    request = {
        "observation_id": f"observation-{uuid.uuid4()}", "invocation_id": f"invocation-{uuid.uuid4()}",
        "command_digest": _canonical_digest(definition), "cwd_token": "bound_project_root",
        "product_tree": source["tree"],
        "state_digest": _canonical_digest({"source": source, "environment": environment, "binding": bound,
                                           "head": evidence["head"] if policy["include_head"] else None}),
        "oracle_digest": _canonical_digest({"authority": authority, "check": definition, "runner": runners, "freshness_policy": policy}),
        "freshness_deadline": (current + timedelta(seconds=policy["max_age_seconds"])).isoformat().replace("+00:00", "Z"),
        # Only explicit provenance revocation advances the epoch. Content drift
        # changes the source identity; restoring it can reuse the prior result.
        "mutation_epoch": store.mutation_epoch,
    }
    observed = None

    def run():
        nonlocal observed
        if capture() != evidence or source_identity() != source:
            raise SystemExit("validation-blocked: inputs changed before observation")
        receipt: dict[str, Any] = {}
        started = _now_text()
        observed = execute(receipt)
        if capture() != evidence or source_identity() != source or validation_environment_identity(root, policy) != environment:
            raise SystemExit("validation-blocked: authoritative validation batch mutated inputs or Git-observable state")
        if observed["result"] != "passed":
            raise _UnrecordedValidation()
        if not receipt:  # Named harness inspections use the same closed result shape.
            receipt.update(exit_code=0, stdout_digest=_canonical_digest(observed),
                           stderr_digest=hashlib.sha256(b"").hexdigest(), started_at=started, completed_at=_now_text())
        return receipt

    try:
        record = reuse_observation(store, request, run)
    except _UnrecordedValidation:
        assert observed is not None
        return observed
    if source_identity() != source or validation_environment_identity(root, policy) != environment:
        raise SystemExit("validation-blocked: inputs changed while obtaining evidence")
    if observed is None:
        observed = {key: item.get(key) for key in ("command", "kind", "id", "invariant_ids")}
        if item.get("kind") == "inspection":
            observed["mechanism"] = item["mechanism"]
        observed["result"] = "passed"
    return {**observed, "observation_id": record.observation_id, "reuse_of": record.reuse_of}


def claim_observation_identity(
    store: ManagedProvenanceStore,
    request: Mapping[str, Any],
    execute: Callable[[], Mapping[str, Any]],
    *,
    finalization_id: str,
    now: datetime | None = None,
    stage_event_workspace: str | Path | None = None,
    stage_event: Mapping[str, Any] | None = None,
) -> ObservationIdentityV1:
    """Reuse or execute one exact observation and bind it to one finalization."""

    observation = reuse_observation(store, request, execute, now=now)
    consume_observation(store, observation.observation_id, finalization_id)
    claimed = load_observation(store, observation.observation_id)
    if observation.reuse_of is not None:
        claimed = replace(claimed, invocation_id=observation.invocation_id, reuse_of=observation.reuse_of)
    _emit_native_stage_event(
        stage_event_workspace,
        stage_event,
        event_type="suite_reused" if observation.reuse_of is not None else "suite_completed",
        mutation_epoch=claimed.mutation_epoch,
    )
    return claimed


def consume_observation(store: ManagedProvenanceStore, observation_id: str, finalization_id: str) -> None:
    _identifier(observation_id, "observation_id")
    _identifier(finalization_id, "finalization_id")
    with store.locked():
        state = store._read_unlocked()
        if not any(item["observation_id"] == observation_id for item in state["observations"]):
            raise CompletionProvenanceError("observation does not exist")
        existing = state["consumptions"].get(observation_id)
        if existing == finalization_id:
            return
        if existing is not None:
            raise CompletionProvenanceError(f"observation is already consumed by {existing}")
        store._register_unlocked(state, finalization_id, "finalization")
        state["consumptions"][observation_id] = finalization_id
        store._write_unlocked(state)


def load_observation(store: ManagedProvenanceStore, observation_id: str) -> ObservationIdentityV1:
    """Load one observation with its public single-finalization consumption state."""
    _identifier(observation_id, "observation_id")
    with store.locked():
        state = store._read_unlocked()
        raw = next(
            (item for item in state["observations"] if item["observation_id"] == observation_id),
            None,
        )
        if raw is None:
            raise CompletionProvenanceError("observation does not exist")
        return ObservationIdentityV1(
            **{
                **raw,
                "consumed_by_finalization": state["consumptions"].get(observation_id),
            }
        )


def record_relevant_mutation(store: ManagedProvenanceStore, reason: str) -> int:
    _nonempty(reason, "mutation reason")
    with store.locked():
        state = store._read_unlocked()
        state["mutation_epoch"] += 1
        state["last_mutation"] = {"reason": reason, "timestamp": _now_text()}
        store._write_unlocked(state)
        return int(state["mutation_epoch"])


def validate_predecessor_extension(
    predecessor: Mapping[str, Any],
    extension: Mapping[str, Any],
    *,
    authorized: bool,
    public_contract_validator: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
) -> Mapping[str, Any]:
    if not authorized:
        raise CompletionProvenanceError("predecessor extension is not authorized")
    if not isinstance(predecessor, Mapping) or not isinstance(extension, Mapping):
        raise CompletionProvenanceError("predecessor and extension must be objects")
    try:
        valid = public_contract_validator(predecessor, extension)
    except Exception as error:
        raise CompletionProvenanceError("predecessor public contract validation failed") from error
    if valid is not True:
        raise CompletionProvenanceError("predecessor public contract validation failed")
    return extension


def execution_binding_ownership(
    store_root: str | Path,
    *,
    binding_id: str,
    target_kind: str,
    owner: str,
) -> dict[str, Any]:
    """Narrow execution-context adapter returning the API-006 public contract."""
    return FailureOwnershipV1.create(
        ManagedProvenanceStore(store_root), binding_id, target_kind, owner
    ).to_dict()


def validate_execution_binding_ownership(
    store_root: str | Path,
    ownership: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the closed API-006 shape and equality with the managed ownership store."""
    normalized = _validate_ownership_shape(ownership)
    store = ManagedProvenanceStore(store_root)
    with store.locked():
        state = store._read_unlocked()
        stored = state.get("bindings", {}).get(ownership["binding_id"])
    if stored != normalized:
        raise CompletionProvenanceError("execution binding ownership does not match managed store")
    return normalized
