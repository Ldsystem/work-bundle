"""Bounded, source-state reuse of harness-owned process observations."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def reuse_seconds(item: dict[str, Any]) -> int:
    seconds = item.get("reuse_seconds", 0)
    if type(seconds) is not int or not 0 <= seconds <= 86400:
        raise SystemExit("validation reuse_seconds must be an integer from 0 to 86400")
    if seconds and item.get("kind") != "process":
        raise SystemExit("validation reuse_seconds is supported only for process checks")
    return seconds


class _FailedObservation(Exception):
    """Abort provenance persistence without changing acceptable-result semantics."""


def observe(
    cp: Any, binding: dict[str, Any], task: dict[str, Any], item: dict[str, Any],
    evidence: dict[str, Any], execute: Callable, capture: Callable,
) -> dict[str, Any]:
    """Only successful, Git-neutral opt-in checks can produce reusable evidence.

    The declaration asserts that ignored/external state is not an input. Environment
    values are hashed, never persisted. The store belongs to one execution/task.
    """
    seconds = reuse_seconds(item)
    if not seconds or item.get("expected") in {"skip", "skipped"}:
        return execute({})
    identity = {key: binding.get(key) for key in (
        "workspace_id", "execution_id", "repository_id", "plan_id", "task_id",
        "execution_path", "baseline",
    )}
    store = cp.ManagedProvenanceStore(
        Path(binding["runtime_root"]) / "validation-observations" / digest(identity)
    )
    state_digest = digest({
        "repository": evidence,
        "environment": {k: v for k, v in os.environ.items() if k not in {"_", "SHLVL"}},
        "runtime": [sys.executable, sys.version, platform.platform()],
    })
    # Seeing a different state invalidates earlier observations even after a revert.
    with store.locked():
        state = store._read_unlocked()
        if state.get("validation_state") != state_digest:
            state["mutation_epoch"] += 1
            state["validation_state"] = state_digest
            store._write_unlocked(state)
        epoch = state["mutation_epoch"]
    helper_dir = Path(__file__).parent
    helper_digests = {
        name: hashlib.sha256((helper_dir / name).read_bytes()).hexdigest()
        for name in ("validation_observation.py", "execution_context.py", "completion_provenance.py", "repository_preflight.py")
    }
    current = now_utc()
    request = {
        "observation_id": f"observation-{uuid.uuid4()}",
        "invocation_id": f"invocation-{uuid.uuid4()}",
        "command_digest": digest(item["command"]),
        "cwd_token": "bound_project_root",
        "product_tree": evidence["tree"],
        "state_digest": state_digest,
        "oracle_digest": digest({"task": task, "check": item, "helpers": helper_digests}),
        "freshness_deadline": (current + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
        "mutation_epoch": epoch,
    }
    observed = None

    def run():
        nonlocal observed
        # Recheck after taking the provenance lock, including time spent waiting.
        if capture() != evidence:
            raise SystemExit("validation-blocked: inputs changed before observation")
        receipt = {}
        observed = execute(receipt)
        if capture() != evidence:
            raise SystemExit("validation-blocked: authoritative validation batch mutated Git-observable state")
        if observed["result"] != "passed":
            raise _FailedObservation()
        return receipt

    try:
        record = cp.reuse_observation(store, request, run, now=current)
    except _FailedObservation:
        assert observed is not None
        return observed
    if observed is None:
        observed = {key: item.get(key) for key in ("command", "kind", "id", "invariant_ids")}
        observed["result"] = "passed"
    return {**observed, "observation_id": record.observation_id, "reuse_of": record.reuse_of}
