from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

from task_ownership import (  # type: ignore[import-not-found]
    OwnershipBlocker,
    SubagentDispatch,
    TaskCandidate,
    TaskOwnershipScheduler,
    normalize_subagent_provenance,
)


def provenance(*, mechanism: str = "host-native") -> dict[str, object]:
    return {
        "delegated": True,
        "owner_kind": "subagent",
        "agent_id": "agent-task-001",
        "run_id": "run-task-001-a",
        "mechanism": mechanism,
    }


class RecordingAdapter:
    def __init__(self, *, available: bool = True, mechanism: str = "host-native") -> None:
        self.is_available = available
        self.mechanism = mechanism
        self.events: list[str] = []

    def available(self) -> bool:
        return self.is_available

    def dispatch(self, task: TaskCandidate, *, operation: str) -> SubagentDispatch:
        self.events.append(f"dispatch:{task.task_id}:{operation}")
        return SubagentDispatch(task.task_id, provenance(mechanism=self.mechanism))

    def wait(self, handle: object) -> object:
        self.events.append(f"wait:{handle}")
        return handle


def test_sg01_execute_plan_requires_implicit_subagent_ownership() -> None:
    adapter = RecordingAdapter()
    result = TaskOwnershipScheduler(adapter).run_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")], completed=set()
    )
    assert result.dispatched == ("task-001",)
    assert result.ownership[0]["owner_kind"] == "subagent"
    assert adapter.events == ["dispatch:task-001:implementation", "wait:task-001"]


def test_sg02_no_subagent_fails_closed_before_mutation() -> None:
    adapter = RecordingAdapter(available=False)

    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        TaskOwnershipScheduler(adapter).run_wave(
            [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
            completed=set(),
        )

    assert adapter.events == []


@pytest.mark.parametrize("legacy_value", [True, False, None])
def test_sg03_legacy_preference_has_no_behavioral_effect(legacy_value: bool | None) -> None:
    legacy_migration_input = {} if legacy_value is None else {"prefer_subagent": legacy_value}
    adapter = RecordingAdapter()
    TaskOwnershipScheduler(adapter).run_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
        completed=set(),
    )
    assert legacy_migration_input.get("prefer_subagent") is legacy_value
    assert adapter.events == ["dispatch:task-001:implementation", "wait:task-001"]


def test_sg04_controller_task_mutation_is_rejected_even_when_validation_passes() -> None:
    scheduler = TaskOwnershipScheduler(RecordingAdapter())
    with pytest.raises(OwnershipBlocker, match="review-blocked") as error:
        scheduler.validate_acceptance(
            delegation_evidence=provenance(),
            mutation_events=[{"actor_kind": "controller", "paths": ["src/a.py"]}],
            write_scope=["src/a.py"],
            validations_passed=True,
        )
    assert error.value.code == "review-blocked"


def test_sg05_independent_disjoint_tasks_dispatch_before_wait() -> None:
    adapter = RecordingAdapter()
    tasks = [
        TaskCandidate("task-a", (), ("src/a.py",), "workspace-a"),
        TaskCandidate("task-b", (), ("src/b.py",), "workspace-b"),
    ]

    result = TaskOwnershipScheduler(adapter).run_wave(
        tasks,
        completed=set(),
    )

    assert result.dispatched == ("task-a", "task-b")
    assert adapter.events == [
        "dispatch:task-a:implementation",
        "dispatch:task-b:implementation",
        "wait:task-a",
        "wait:task-b",
    ]


def test_sg06_dependent_or_overlapping_tasks_are_serialized() -> None:
    adapter = RecordingAdapter()
    tasks = [
        TaskCandidate("task-a", (), ("src/shared.py",), "workspace-a"),
        TaskCandidate("task-b", (), ("src/shared.py",), "workspace-b"),
        TaskCandidate("task-c", ("task-a",), ("src/c.py",), "workspace-c"),
    ]
    result = TaskOwnershipScheduler(adapter).run_wave(
        tasks,
        completed=set(),
    )

    assert result.dispatched == ("task-a",)
    assert adapter.events == ["dispatch:task-a:implementation", "wait:task-a"]


def test_sg06_same_execution_workspace_is_never_fanned_out() -> None:
    tasks = [
        TaskCandidate("task-a", (), ("src/a.py",), "workspace-shared"),
        TaskCandidate("task-b", (), ("src/b.py",), "workspace-shared"),
    ]
    result = TaskOwnershipScheduler(RecordingAdapter()).run_wave(
        tasks,
        completed=set(),
    )
    assert result.dispatched == ("task-a",)


def test_sg06_serialized_tasks_progress_across_successive_waves() -> None:
    tasks = [
        TaskCandidate("task-a", (), ("src/shared.py",), "workspace-a"),
        TaskCandidate("task-b", (), ("src/shared.py",), "workspace-b"),
    ]
    scheduler = TaskOwnershipScheduler(RecordingAdapter())
    first = scheduler.run_wave(
        tasks,
        completed=set(),
    )
    second = scheduler.run_wave(
        tasks,
        completed=set(first.dispatched),
    )

    assert first.dispatched == ("task-a",)
    assert second.dispatched == ("task-b",)


def test_sg07_repair_remains_subagent_owned() -> None:
    adapter = RecordingAdapter()
    result = TaskOwnershipScheduler(adapter).run_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
        completed=set(),
        operation="repair",
    )
    assert result.operation == "repair"
    assert result.ownership[0]["owner_kind"] == "subagent"
    assert adapter.events == ["dispatch:task-001:repair", "wait:task-001"]


@pytest.mark.parametrize("mechanism", ["host-native", "execution-flow"])
def test_sg08_ownership_is_mechanism_neutral(mechanism: str) -> None:
    result = TaskOwnershipScheduler(RecordingAdapter(mechanism=mechanism)).run_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")], completed=set()
    )
    assert result.ownership[0]["mechanism"] == mechanism
    assert set(result.ownership[0]) == {"delegated", "owner_kind", "agent_id", "run_id", "mechanism"}


def test_visibility_specific_provenance_is_rejected() -> None:
    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        normalize_subagent_provenance({**provenance(), "visible_reference": "thread-123"})
