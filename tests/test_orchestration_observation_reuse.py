from __future__ import annotations

import json
import shlex
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
sys.path.insert(0, str(ORCHESTRATION))

import completion_provenance  # noqa: E402
import execution_context  # noqa: E402
import plans  # noqa: E402
from repository_preflight import capture_repository_evidence  # noqa: E402


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    source = root / "runtime.py"
    source.write_text("VALUE = 1\n")
    _git(root, "add", "runtime.py")
    _git(root, "commit", "-qm", "baseline")

    control_root = tmp_path / "control"
    control_root.mkdir()
    counter = tmp_path / "executions.txt"
    script = (
        "from pathlib import Path; "
        f"p=Path({str(counter)!r}); "
        "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1')"
    )
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    item = {
        "id": "VAL-001",
        "kind": "process",
        "command": command,
        "expected": "passed",
        "invariant_ids": ["INV-001"],
        "proves": ["REQ-001"],
        "evidence_reuse": {
            "mode": "deterministic",
            "max_age_seconds": 3600,
            "include_head": False,
        },
    }
    task = {
        "plan_id": "plan-001",
        "task_id": "task-001",
        "source_ids": ["REQ-001"],
        "requirements": ["REQ-001: reuse terminal evidence"],
        "constraints": [],
        "interfaces": {},
        "truth_basis": {"conflict_status": "clear"},
        "files": {"read": ["runtime.py"], "write": ["runtime.py"], "forbidden": []},
        "evidence_capability": {"result": "mapped"},
        "validation": [item],
    }
    binding = {
        "control_root": str(control_root),
        "execution_path": str(root),
        "workspace_id": "workspace-001",
        "execution_id": "execution-001",
        "repository_id": "repository-001",
        "plan_id": "plan-001",
        "task_id": "task-001",
    }
    evidence = capture_repository_evidence(root)
    observed = completion_provenance.observe_validation(
        binding,
        task,
        item,
        evidence,
        lambda receipt: execution_context._observe_validation_item(item, root, task, receipt),
        lambda: capture_repository_evidence(root),
    )
    accepted = {
        "schema": "accepted-task-result-v1",
        "plan_id": "plan-001",
        "task_id": "task-001",
        "validation_evidence_ids": [observed["observation_id"]],
    }
    monkeypatch.setattr(plans, "load_task_execution_binding", lambda *_: binding)
    return root, control_root, counter, accepted, task, command, observed


def _archive(control_root: Path, root: Path, command: str, accepted: dict, task: dict):
    return plans._observe_archive_obligations(
        control_root, command, root, [(accepted, task)]
    )


def test_task_level_reuse_policy_is_applied_to_each_validation_obligation():
    compiled = execution_context._compile_task_validation(
        {
            "validation": [
                {"id": "VAL-001", "kind": "process", "command": "true", "expected": "passed"}
            ],
            "evidence_reuse": {
                "mode": "deterministic",
                "max_age_seconds": 120,
                "include_head": False,
            },
        },
        "",
        [],
        {},
    )

    assert compiled[0]["evidence_reuse"]["max_age_seconds"] == 120


def test_completion_then_archive_reuses_one_current_terminal_observation(tmp_path, monkeypatch):
    root, control, counter, accepted, task, command, first = _fixture(tmp_path, monkeypatch)

    observed = _archive(control, root, command, accepted, task)

    assert counter.read_text() == "1"
    assert observed[0]["observation_id"] == first["observation_id"]
    assert observed[0]["reuse_of"] == first["observation_id"]


@pytest.mark.parametrize("change", ["source", "claim", "epoch"])
def test_archive_executes_once_for_each_exact_invalidation(tmp_path, monkeypatch, change):
    root, control, counter, accepted, task, command, first = _fixture(tmp_path, monkeypatch)
    changed = deepcopy(task)
    if change == "source":
        (root / "runtime.py").write_text("VALUE = 2\n")
    elif change == "claim":
        changed["requirements"] = ["REQ-001: changed semantic claim"]
    else:
        store = completion_provenance.ManagedProvenanceStore(
            control / ".work-bundle/runtime/completion-provenance"
        )
        completion_provenance.record_relevant_mutation(store, "accepted invalidation")

    observed = _archive(control, root, command, accepted, changed)

    assert counter.read_text() == "2"
    assert observed[0]["observation_id"] != first["observation_id"]
    assert observed[0]["reuse_of"] is None


def test_changed_validation_allocation_requires_fresh_accepted_observation(tmp_path, monkeypatch):
    root, control, counter, accepted, task, command, first = _fixture(tmp_path, monkeypatch)
    changed = deepcopy(task)
    changed["validation"][0]["invariant_ids"] = ["INV-002"]
    binding = plans.load_task_execution_binding(control, "plan-001", "task-001")
    evidence = capture_repository_evidence(root)
    replacement = completion_provenance.observe_validation(
        binding,
        changed,
        changed["validation"][0],
        evidence,
        lambda receipt: execution_context._observe_validation_item(
            changed["validation"][0], root, changed, receipt
        ),
        lambda: capture_repository_evidence(root),
    )
    accepted["validation_evidence_ids"] = [replacement["observation_id"]]

    observed = _archive(control, root, command, accepted, changed)

    assert counter.read_text() == "2"
    assert replacement["observation_id"] != first["observation_id"]
    assert observed[0]["reuse_of"] == replacement["observation_id"]


def test_distinct_accepted_obligations_each_reuse_without_lifecycle_replay(tmp_path, monkeypatch):
    root, control, counter, accepted, task, command, _ = _fixture(tmp_path, monkeypatch)
    other = deepcopy(task)
    other["task_id"] = "task-002"
    other["validation"][0]["id"] = "VAL-002"
    binding_two = {
        "control_root": str(control),
        "execution_path": str(root),
        "workspace_id": "workspace-001",
        "execution_id": "execution-001",
        "repository_id": "repository-001",
        "plan_id": "plan-001",
        "task_id": "task-002",
    }
    evidence = capture_repository_evidence(root)
    second = completion_provenance.observe_validation(
        binding_two,
        other,
        other["validation"][0],
        evidence,
        lambda receipt: execution_context._observe_validation_item(other["validation"][0], root, other, receipt),
        lambda: capture_repository_evidence(root),
    )
    accepted_two = {
        "schema": "accepted-task-result-v1",
        "plan_id": "plan-001",
        "task_id": "task-002",
        "validation_evidence_ids": [second["observation_id"]],
    }
    monkeypatch.setattr(
        plans,
        "load_task_execution_binding",
        lambda _root, _plan, task_id: binding_two if task_id == "task-002" else {
            **binding_two, "task_id": "task-001"
        },
    )

    observed = _archive(control, root, command, accepted, task)
    observed += _archive(control, root, command, accepted_two, other)

    assert counter.read_text() == "2"
    assert {item["reuse_of"] for item in observed} == {
        accepted["validation_evidence_ids"][0],
        accepted_two["validation_evidence_ids"][0],
    }


def test_executor_authored_receipt_id_is_not_independent_archive_proof(tmp_path, monkeypatch):
    root, control, counter, accepted, task, command, _ = _fixture(tmp_path, monkeypatch)
    accepted["validation_evidence_ids"] = ["executor-forged-observation"]

    with pytest.raises(SystemExit, match="accepted harness observation"):
        _archive(control, root, command, accepted, task)

    assert counter.read_text() == "1"


def test_archive_acceptance_uses_observation_contract_instead_of_direct_runner(tmp_path, monkeypatch):
    root, control, counter, accepted, task, command, _ = _fixture(tmp_path, monkeypatch)
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Tests\n\n| Test Type | Command |\n| --- | --- |\n"
        f"| Integration | `{command}` |\n"
    )
    monkeypatch.setattr(plans, "_material_repository_root", lambda *_: root)
    monkeypatch.setattr(plans, "resolve_workspace_root", lambda *_: control)
    monkeypatch.setattr(plans, "_assert_archive_command_state_neutral", lambda *_: pytest.fail("direct replay"))
    args = type("Args", (), {"project_root": str(control), "workspace_root": str(control)})()

    plans._assert_archive_plan_acceptance(args, "plan-001", plan, [(accepted, task)])

    assert counter.read_text() == "1"
