from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "orchestration"))

from task_ownership import (  # type: ignore[import-not-found]
    OwnershipBlocker,
    RepairContinuity,
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


class HeldOpenAdapter(RecordingAdapter):
    """Workers remain pending until wait; waiting early exposes lost fan-out."""

    def __init__(self, expected_dispatches: int) -> None:
        super().__init__()
        self.expected_dispatches = expected_dispatches

    def wait(self, handle: object) -> object:
        dispatches = [event for event in self.events if event.startswith("dispatch:")]
        assert len(dispatches) == self.expected_dispatches
        self.events.append(f"wait:{handle}")
        return {"handoff": f"handoff-{handle}", "accepted": True}


def run_wb(config_root: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(config_root)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "wb.py"), *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


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
def test_sg03_legacy_preference_has_no_behavioral_effect(
    tmp_path: Path, legacy_value: bool | None
) -> None:
    config_root = tmp_path / "config"
    registry = config_root / "registry"
    registry.mkdir(parents=True)
    preference = "" if legacy_value is None else f"prefer_subagent: {str(legacy_value).lower()}\n"
    (config_root / "bootstrap.yaml").write_text(
        "bootstrap_version: v1\n"
        f"work_bundle_root: {REPO_ROOT}\n"
        'project_registry: "$work_bundle_config_root/registry/projects.yaml"\n'
        'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"\n'
        + preference,
        encoding="utf-8",
    )
    (registry / "projects.yaml").write_text("projects: []\n", encoding="utf-8")
    (registry / "skill-registry.yaml").write_text("skills: []\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    initialized = run_wb(
        config_root,
        "init-project",
        str(project),
        "--mode",
        "single-repository",
        cwd=project,
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    metadata = project / ".work-bundle" / "project.yaml"
    metadata.write_text(metadata.read_text(encoding="utf-8") + preference, encoding="utf-8")

    shown = run_wb(config_root, "show-project", "--project-root", str(project), cwd=project)
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert "prefer_subagent" not in json.loads(shown.stdout)
    assert "prefer_subagent" not in (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "prefer_subagent" not in json.loads(initialized.stdout)

    adapter = RecordingAdapter()
    TaskOwnershipScheduler(adapter).run_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
        completed=set(),
    )
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


def test_sg05_independent_disjoint_tasks_dispatch_before_wait_and_convergence() -> None:
    adapter = HeldOpenAdapter(expected_dispatches=2)
    tasks = [
        TaskCandidate(
            "task-a", (), ("src/a.py",), "workspace-a",
            common_contract="CG-001", barrier="BAR-001", convergence_owner="task-c",
        ),
        TaskCandidate(
            "task-b", (), ("src/b.py",), "workspace-b",
            common_contract="CG-001", barrier="BAR-001", convergence_owner="task-c",
        ),
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
    assert result.results == (
        {"handoff": "handoff-task-a", "accepted": True},
        {"handoff": "handoff-task-b", "accepted": True},
    )

    convergence = TaskCandidate(
        "task-c", ("task-a", "task-b"), ("tests/integration.py",), "workspace-c",
        common_contract="CG-001", barrier="BAR-001", barrier_participants=("task-a", "task-b"),
    )
    closed = TaskOwnershipScheduler(RecordingAdapter()).run_wave(
        [convergence], completed={"task-a", "task-b"}, accepted_handoffs={"task-a"}
    )
    assert closed.dispatched == ()
    released = TaskOwnershipScheduler(RecordingAdapter()).run_wave(
        [convergence],
        completed={"task-a", "task-b"},
        accepted_handoffs={"task-a", "task-b"},
    )
    assert released.dispatched == ("task-c",)


def test_sg05_rejects_incomplete_common_contract_barrier_topology() -> None:
    incomplete = TaskCandidate(
        "task-a", (), ("src/a.py",), "workspace-a", common_contract="CG-001"
    )
    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        TaskOwnershipScheduler(RecordingAdapter()).run_wave([incomplete], completed=set())


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


def test_sg07_repair_retains_owner_binding_baseline_evidence_and_frontier() -> None:
    adapter = RecordingAdapter()
    continuity = RepairContinuity(
        binding_id="binding-task-001",
        baseline_identity="base-tree-001",
        evidence_identity="evidence-batch-001",
        previous_review_identity="review-head-001",
    )
    result = TaskOwnershipScheduler(adapter).run_wave(
        [TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")],
        completed=set(),
        operation="repair",
        prior_ownership={"task-001": provenance()},
        repair_continuity={"task-001": continuity},
    )
    assert result.operation == "repair"
    assert result.ownership[0]["owner_kind"] == "subagent"
    assert result.ownership[0]["agent_id"] == provenance()["agent_id"]
    assert result.repair_continuity == (continuity,)
    assert adapter.events == ["dispatch:task-001:repair", "wait:task-001"]


def test_sg07_repair_allows_only_an_authorized_replacement_owner() -> None:
    class ReplacementAdapter(RecordingAdapter):
        def dispatch(self, task: TaskCandidate, *, operation: str) -> SubagentDispatch:
            replacement = {**provenance(), "agent_id": "replacement-agent", "run_id": "repair-run"}
            return SubagentDispatch(task.task_id, replacement)

    task = TaskCandidate("task-001", (), ("src/a.py",), "workspace-a")
    continuity = RepairContinuity("binding", "baseline", "evidence", "review-head")
    scheduler = TaskOwnershipScheduler(ReplacementAdapter())
    with pytest.raises(OwnershipBlocker, match="review-blocked"):
        scheduler.run_wave(
            [task], completed=set(), operation="repair",
            prior_ownership={"task-001": provenance()},
            repair_continuity={"task-001": continuity},
        )
    accepted = scheduler.run_wave(
        [task], completed=set(), operation="repair",
        prior_ownership={"task-001": provenance()},
        repair_continuity={"task-001": continuity},
        authorized_replacements={"task-001"},
    )
    assert accepted.repair_continuity == (continuity,)


def test_sg08_native_mechanisms_preserve_task_binding_handoff_and_validation_semantics() -> None:
    observed: list[tuple[object, ...]] = []
    for mechanism in ("host-native", "execution-flow"):
        adapter = HeldOpenAdapter(expected_dispatches=1)
        adapter.mechanism = mechanism
        task = TaskCandidate("task-001", (), ("src/a.py",), "workspace-a", binding_id="binding-001")
        scheduler = TaskOwnershipScheduler(adapter)
        result = scheduler.run_wave([task], completed=set())
        validated = scheduler.validate_acceptance(
            delegation_evidence=result.ownership[0], mutation_events=[],
            write_scope=task.write_scope, validations_passed=True,
        )
        observed.append(
            (result.dispatched, task.binding_id, result.results, validated["owner_kind"], set(validated))
        )
        assert result.ownership[0]["mechanism"] == mechanism
    assert observed[0] == observed[1]


def test_visibility_specific_provenance_is_rejected() -> None:
    with pytest.raises(OwnershipBlocker, match="workspace-blocked"):
        normalize_subagent_provenance({**provenance(), "visible_reference": "thread-123"})
