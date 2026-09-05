"""Provider-neutral subagent ownership and ready-wave scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence, TypeVar


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
    ready = [task for task in tasks if set(task.dependencies).issubset(completed)]
    wave: list[TaskCandidate] = []
    for task in ready:
        if any(task.execution_workspace == selected.execution_workspace for selected in wave):
            continue
        if any(_scopes_overlap(task.write_scope, selected.write_scope) for selected in wave):
            continue
        wave.append(task)
    return wave


Handle = TypeVar("Handle")


def dispatch_ready_wave(
    tasks: Sequence[TaskCandidate],
    *,
    completed: set[str],
    subagents_available: bool,
    dispatch: Callable[[TaskCandidate], Handle],
    wait: Callable[[Handle], object],
) -> DispatchWaveResult:
    """Dispatch every safe ready task before awaiting any returned handle."""

    if not subagents_available:
        raise OwnershipBlocker("workspace-blocked", "subagent execution is unavailable")
    wave = _ready_wave(tasks, completed)
    handles = [dispatch(task) for task in wave]
    results = tuple(wait(handle) for handle in handles)
    return DispatchWaveResult(tuple(task.task_id for task in wave), results)
