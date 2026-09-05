from __future__ import annotations

from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

from task_ownership import (  # type: ignore[import-not-found]
    OwnershipBlocker,
    TaskCandidate,
    dispatch_ready_wave,
    normalize_subagent_provenance,
    validate_task_acceptance_ownership,
)


def provenance(*, mechanism: str = "host-native") -> dict[str, object]:
    return {
        "delegated": True,
        "owner_kind": "subagent",
        "agent_id": "agent-task-001",
        "run_id": "run-task-001-a",
        "mechanism": mechanism,
    }


def test_sg01_execute_plan_requires_implicit_subagent_ownership() -> None:
    assert normalize_subagent_provenance(provenance())["owner_kind"] == "subagent"
    with pytest.raises(OwnershipBlocker, match="workspace-blocked") as error:
        normalize_subagent_provenance(None)
    assert error.value.code == "workspace-blocked"


def test_sg02_no_subagent_fails_closed_before_mutation() -> None:
    mutations: list[str] = []

    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        dispatch_ready_wave(
            [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
            completed=set(),
            subagents_available=False,
            dispatch=lambda task: mutations.append(task.task_id),
            wait=lambda _handle: None,
        )

    assert mutations == []


@pytest.mark.parametrize("legacy_value", [True, False, None])
def test_sg03_legacy_preference_has_no_behavioral_effect(legacy_value: bool | None) -> None:
    legacy_migration_input = {} if legacy_value is None else {"prefer_subagent": legacy_value}
    events: list[str] = []
    dispatch_ready_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
        completed=set(),
        subagents_available=True,
        dispatch=lambda task: events.append(f"dispatch:{task.task_id}") or provenance(),
        wait=lambda _handle: events.append("wait"),
    )
    assert legacy_migration_input.get("prefer_subagent") is legacy_value
    assert events == ["dispatch:task-001", "wait"]


def test_sg04_controller_task_mutation_is_rejected_even_when_validation_passes() -> None:
    with pytest.raises(OwnershipBlocker, match="review-blocked") as error:
        validate_task_acceptance_ownership(
            delegation_evidence=provenance(),
            mutation_events=[{"actor_kind": "controller", "paths": ["src/a.py"]}],
            write_scope=["src/a.py"],
            validations_passed=True,
        )
    assert error.value.code == "review-blocked"


def test_sg05_independent_disjoint_tasks_dispatch_before_wait() -> None:
    events: list[str] = []
    tasks = [
        TaskCandidate("task-a", (), ("src/a.py",), "workspace-a"),
        TaskCandidate("task-b", (), ("src/b.py",), "workspace-b"),
    ]

    result = dispatch_ready_wave(
        tasks,
        completed=set(),
        subagents_available=True,
        dispatch=lambda task: events.append(f"dispatch:{task.task_id}") or task.task_id,
        wait=lambda handle: events.append(f"wait:{handle}"),
    )

    assert result.dispatched == ("task-a", "task-b")
    assert events == ["dispatch:task-a", "dispatch:task-b", "wait:task-a", "wait:task-b"]


def test_sg06_dependent_or_overlapping_tasks_are_serialized() -> None:
    events: list[str] = []
    tasks = [
        TaskCandidate("task-a", (), ("src/shared.py",), "workspace-a"),
        TaskCandidate("task-b", (), ("src/shared.py",), "workspace-b"),
        TaskCandidate("task-c", ("task-a",), ("src/c.py",), "workspace-c"),
    ]
    result = dispatch_ready_wave(
        tasks,
        completed=set(),
        subagents_available=True,
        dispatch=lambda task: events.append(f"dispatch:{task.task_id}") or task.task_id,
        wait=lambda handle: events.append(f"wait:{handle}"),
    )

    assert result.dispatched == ("task-a",)
    assert events == ["dispatch:task-a", "wait:task-a"]


def test_sg06_same_execution_workspace_is_never_fanned_out() -> None:
    tasks = [
        TaskCandidate("task-a", (), ("src/a.py",), "workspace-shared"),
        TaskCandidate("task-b", (), ("src/b.py",), "workspace-shared"),
    ]
    result = dispatch_ready_wave(
        tasks,
        completed=set(),
        subagents_available=True,
        dispatch=lambda task: task.task_id,
        wait=lambda _handle: None,
    )
    assert result.dispatched == ("task-a",)


def test_sg07_repair_remains_subagent_owned() -> None:
    assert normalize_subagent_provenance(provenance(), operation="repair")["agent_id"] == "agent-task-001"
    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        normalize_subagent_provenance(
            {**provenance(), "owner_kind": "controller"}, operation="repair"
        )


@pytest.mark.parametrize("mechanism", ["host-native", "execution-flow"])
def test_sg08_ownership_is_mechanism_neutral(mechanism: str) -> None:
    normalized = normalize_subagent_provenance(provenance(mechanism=mechanism))
    assert normalized["mechanism"] == mechanism
    assert set(normalized) == {"delegated", "owner_kind", "agent_id", "run_id", "mechanism"}


def test_visibility_specific_provenance_is_rejected() -> None:
    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        normalize_subagent_provenance({**provenance(), "visible_reference": "thread-123"})
