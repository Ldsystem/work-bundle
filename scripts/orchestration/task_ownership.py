"""Provider-neutral subagent ownership and ready-wave scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Protocol, Sequence


PROVENANCE_FIELDS = frozenset({"delegated", "owner_kind", "agent_id", "run_id", "mechanism"})
SUBAGENT_MECHANISMS = frozenset({"host-native", "execution-flow"})
MUTATION_EVENT_FIELDS = frozenset({"actor_kind", "paths"})
MUTATION_ACTOR_KINDS = frozenset({"controller", "subagent"})


class OwnershipBlocker(RuntimeError):
    """Typed orchestration blocker raised before mutation or acceptance."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True)
class TaskCandidate:
    task_id: str
    dependencies: tuple[str, ...]
    write_scope: tuple[str, ...]
    execution_workspace: str
    common_contract: str | None = None
    barrier: str | None = None
    convergence_owner: str | None = None
    barrier_participants: tuple[str, ...] = ()
    binding_id: str | None = None

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.write_scope or any(not str(path).strip() for path in self.write_scope):
            raise ValueError("write_scope must contain explicit paths")
        if not self.execution_workspace.strip():
            raise ValueError("execution_workspace must be non-empty")


@dataclass(frozen=True)
class RepairContinuity:
    """Harness-owned identities a repair must carry without reacquisition."""

    binding_id: str
    baseline_identity: str
    evidence_identity: str
    previous_review_identity: str

    def __post_init__(self) -> None:
        for field in (
            "binding_id",
            "baseline_identity",
            "evidence_identity",
            "previous_review_identity",
        ):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"{field} must be non-empty")


@dataclass(frozen=True)
class DispatchWaveResult:
    dispatched: tuple[str, ...]
    results: tuple[object, ...]
    ownership: tuple[dict[str, object], ...]
    operation: str
    repair_continuity: tuple[RepairContinuity, ...] = ()


@dataclass(frozen=True)
class SubagentDispatch:
    handle: object
    delegation_evidence: Mapping[str, object]


class SubagentAdapter(Protocol):
    def available(self) -> bool: ...

    def dispatch(self, task: TaskCandidate, *, operation: str) -> SubagentDispatch: ...

    def wait(self, handle: object) -> object: ...


def _identifier(value: object, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise OwnershipBlocker("workspace-blocked", f"subagent {field} is missing")
    return normalized


def normalize_subagent_provenance(
    evidence: Mapping[str, object] | None,
    *,
    operation: str = "implementation",
) -> dict[str, object]:
    """Validate the closed, provider-neutral task ownership receipt."""

    if operation not in {"implementation", "repair"}:
        raise ValueError("operation must be implementation or repair")
    if not isinstance(evidence, Mapping):
        raise OwnershipBlocker("workspace-blocked", f"{operation} requires subagent ownership")
    if set(evidence) != PROVENANCE_FIELDS:
        raise OwnershipBlocker("workspace-blocked", "subagent ownership provenance is not closed")
    if evidence.get("delegated") is not True or evidence.get("owner_kind") != "subagent":
        raise OwnershipBlocker("workspace-blocked", f"{operation} requires subagent ownership")
    mechanism = _identifier(evidence.get("mechanism"), "mechanism")
    if mechanism not in SUBAGENT_MECHANISMS:
        raise OwnershipBlocker("workspace-blocked", "subagent mechanism is unsupported")
    return {
        "delegated": True,
        "owner_kind": "subagent",
        "agent_id": _identifier(evidence.get("agent_id"), "agent_id"),
        "run_id": _identifier(evidence.get("run_id"), "run_id"),
        "mechanism": mechanism,
    }


def _scope_matches(path: str, scope: str) -> bool:
    left = path.strip().removeprefix("./").rstrip("/")
    right = scope.strip().removeprefix("./").rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _scopes_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    return any(_scope_matches(a, b) for a in left for b in right)


def validate_task_acceptance_ownership(
    *,
    delegation_evidence: Mapping[str, object] | None,
    mutation_events: Iterable[Mapping[str, object]],
    write_scope: Sequence[str],
    validations_passed: bool,
    operation: str = "implementation",
) -> dict[str, object]:
    """Reject controller-authored task-scope changes even after green validation."""

    provenance = normalize_subagent_provenance(delegation_evidence, operation=operation)
    for event in mutation_events:
        if set(event) != MUTATION_EVENT_FIELDS:
            raise OwnershipBlocker("review-blocked", "mutation event fields are not closed and complete")
        actor_kind = event.get("actor_kind")
        if not isinstance(actor_kind, str) or actor_kind not in MUTATION_ACTOR_KINDS:
            raise OwnershipBlocker("review-blocked", "mutation event actor_kind is invalid")
        paths = event.get("paths")
        if not isinstance(paths, list) or not paths:
            raise OwnershipBlocker("review-blocked", "mutation event paths must be a non-empty list")
        changed: list[str] = []
        for path in paths:
            if not isinstance(path, str):
                raise OwnershipBlocker("review-blocked", "mutation event paths must contain strings")
            normalized = path.strip().removeprefix("./")
            parsed = PurePosixPath(normalized)
            if (not normalized or parsed.is_absolute() or ".." in parsed.parts
                    or normalized in {".", "./"} or "\\" in normalized
                    or any(character in normalized for character in "*?[]")):
                raise OwnershipBlocker("review-blocked", "mutation event path is unsafe")
            changed.append(normalized)
        if actor_kind != "controller":
            continue
        if _scopes_overlap(changed, write_scope):
            raise OwnershipBlocker(
                "review-blocked",
                "controller mutated task-owned implementation scope",
            )
    if not validations_passed:
        raise OwnershipBlocker("validation-blocked", "task validation has not passed")
    return provenance


def _validate_topology(task: TaskCandidate) -> None:
    participant_fields = (task.common_contract, task.barrier, task.convergence_owner)
    if any(participant_fields) and not all(participant_fields) and not task.barrier_participants:
        raise OwnershipBlocker(
            "workspace-blocked",
            f"{task.task_id} has incomplete common-contract/barrier topology",
        )
    if task.barrier_participants:
        if not task.common_contract or not task.barrier:
            raise OwnershipBlocker(
                "workspace-blocked",
                f"{task.task_id} convergence admission lacks common contract or barrier",
            )
        if not set(task.barrier_participants).issubset(task.dependencies):
            raise OwnershipBlocker(
                "workspace-blocked",
                f"{task.task_id} convergence dependencies omit barrier participants",
            )


def _ready_wave(
    tasks: Sequence[TaskCandidate],
    completed: set[str],
    accepted_handoffs: set[str],
) -> list[TaskCandidate]:
    for task in tasks:
        _validate_topology(task)
    ready = [
        task
        for task in tasks
        if task.task_id not in completed and set(task.dependencies).issubset(completed)
        and set(task.barrier_participants).issubset(accepted_handoffs)
    ]
    wave: list[TaskCandidate] = []
    for task in ready:
        if any(task.execution_workspace == selected.execution_workspace for selected in wave):
            continue
        if any(_scopes_overlap(task.write_scope, selected.write_scope) for selected in wave):
            continue
        wave.append(task)
    return wave


class TaskOwnershipScheduler:
    """Production admission and scheduling entry for ``orch-execute-plan``."""

    def __init__(self, adapter: SubagentAdapter) -> None:
        self._adapter = adapter

    def run_wave(
        self,
        tasks: Sequence[TaskCandidate],
        *,
        completed: set[str],
        operation: str = "implementation",
        accepted_handoffs: set[str] | None = None,
        prior_ownership: Mapping[str, Mapping[str, object]] | None = None,
        repair_continuity: Mapping[str, RepairContinuity] | None = None,
        authorized_replacements: set[str] | None = None,
    ) -> DispatchWaveResult:
        if operation not in {"implementation", "repair"}:
            raise ValueError("operation must be implementation or repair")
        if not self._adapter.available():
            raise OwnershipBlocker("workspace-blocked", "subagent execution is unavailable")
        wave = _ready_wave(tasks, completed, accepted_handoffs or set())
        if operation == "repair":
            for task in wave:
                if (prior_ownership or {}).get(task.task_id) is None:
                    raise OwnershipBlocker(
                        "review-blocked", f"{task.task_id} repair lacks prior owner"
                    )
                if (repair_continuity or {}).get(task.task_id) is None:
                    raise OwnershipBlocker(
                        "review-blocked", f"{task.task_id} repair lacks continuity identities"
                    )
        dispatched: list[SubagentDispatch] = []
        ownership: list[dict[str, object]] = []
        retained: list[RepairContinuity] = []
        for task in wave:
            receipt = self._adapter.dispatch(task, operation=operation)
            if not isinstance(receipt, SubagentDispatch):
                raise OwnershipBlocker("workspace-blocked", "subagent dispatch receipt is invalid")
            current_owner = normalize_subagent_provenance(
                receipt.delegation_evidence, operation=operation
            )
            if operation == "repair":
                previous = (prior_ownership or {}).get(task.task_id)
                continuity = (repair_continuity or {}).get(task.task_id)
                assert previous is not None and continuity is not None
                previous_owner = normalize_subagent_provenance(previous)
                replaced = current_owner["agent_id"] != previous_owner["agent_id"]
                if replaced and task.task_id not in (authorized_replacements or set()):
                    raise OwnershipBlocker(
                        "review-blocked",
                        f"{task.task_id} repair owner replacement is not authorized",
                    )
                retained.append(continuity)
            ownership.append(current_owner)
            dispatched.append(receipt)
        results = tuple(self._adapter.wait(receipt.handle) for receipt in dispatched)
        return DispatchWaveResult(
            dispatched=tuple(task.task_id for task in wave),
            results=results,
            ownership=tuple(ownership),
            operation=operation,
            repair_continuity=tuple(retained),
        )

    def validate_acceptance(
        self,
        *,
        delegation_evidence: Mapping[str, object] | None,
        mutation_events: Iterable[Mapping[str, object]],
        write_scope: Sequence[str],
        validations_passed: bool,
        operation: str = "implementation",
    ) -> dict[str, object]:
        return validate_task_acceptance_ownership(
            delegation_evidence=delegation_evidence,
            mutation_events=mutation_events,
            write_scope=write_scope,
            validations_passed=validations_passed,
            operation=operation,
        )
