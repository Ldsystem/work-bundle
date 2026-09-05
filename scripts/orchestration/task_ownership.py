"""Provider-neutral subagent ownership and ready-wave scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence


PROVENANCE_FIELDS = frozenset({"delegated", "owner_kind", "agent_id", "run_id", "mechanism"})
SUBAGENT_MECHANISMS = frozenset({"host-native", "execution-flow"})


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

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must be non-empty")
        if not self.write_scope or any(not str(path).strip() for path in self.write_scope):
            raise ValueError("write_scope must contain explicit paths")
        if not self.execution_workspace.strip():
            raise ValueError("execution_workspace must be non-empty")


@dataclass(frozen=True)
class DispatchWaveResult:
    dispatched: tuple[str, ...]
    results: tuple[object, ...]
    ownership: tuple[dict[str, object], ...]
    operation: str


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
        actor_kind = str(event.get("actor_kind") or "").strip()
        paths = event.get("paths")
        if actor_kind != "controller" or not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
            continue
        changed = [str(path) for path in paths]
        if _scopes_overlap(changed, write_scope):
            raise OwnershipBlocker(
                "review-blocked",
                "controller mutated task-owned implementation scope",
            )
    if not validations_passed:
        raise OwnershipBlocker("validation-blocked", "task validation has not passed")
    return provenance


def _ready_wave(tasks: Sequence[TaskCandidate], completed: set[str]) -> list[TaskCandidate]:
    ready = [
        task
        for task in tasks
        if task.task_id not in completed and set(task.dependencies).issubset(completed)
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
    ) -> DispatchWaveResult:
        if operation not in {"implementation", "repair"}:
            raise ValueError("operation must be implementation or repair")
        if not self._adapter.available():
            raise OwnershipBlocker("workspace-blocked", "subagent execution is unavailable")
        wave = _ready_wave(tasks, completed)
        dispatched: list[SubagentDispatch] = []
        ownership: list[dict[str, object]] = []
        for task in wave:
            receipt = self._adapter.dispatch(task, operation=operation)
            if not isinstance(receipt, SubagentDispatch):
                raise OwnershipBlocker("workspace-blocked", "subagent dispatch receipt is invalid")
            ownership.append(
                normalize_subagent_provenance(receipt.delegation_evidence, operation=operation)
            )
            dispatched.append(receipt)
        results = tuple(self._adapter.wait(receipt.handle) for receipt in dispatched)
        return DispatchWaveResult(
            dispatched=tuple(task.task_id for task in wave),
            results=results,
            ownership=tuple(ownership),
            operation=operation,
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
