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
    evidence = capture_repository_evidence(root)
    binding = {
        "control_root": str(control_root),
        "execution_path": str(root),
        "workspace_id": "workspace-001",
        "execution_id": "execution-001",
        "repository_id": "repository-001",
        "plan_id": "plan-001",
        "task_id": "task-001",
        "git_identity": {"branch_ref": "refs/heads/master"},
        "baseline": {"head": evidence["head"], "tree": evidence["tree"]},
        "ownership": {
            "binding_id": "binding:plan-001:task-001",
            "state": "active",
            "current_owner": "task-001",
            "original_owner": "task-001",
            "history": [{"event": "created"}],
        },
    }
    observed = completion_provenance.observe_validation(
        binding,
        task,
        item,
        evidence,
        lambda receipt: execution_context._observe_validation_item(item, root, task, receipt),
        lambda: capture_repository_evidence(root),
    )
    accepted = _accepted_result(task, binding, str(observed["observation_id"]))
    monkeypatch.setattr(plans, "load_task_execution_binding", lambda *_: binding)
    return root, control_root, counter, accepted, task, binding, command, observed


def _accepted_result(task: dict, binding: dict, observation_id: str) -> dict:
    ownership = {
        "delegated": True,
        "owner_kind": "subagent",
        "agent_id": "fixture-agent",
        "run_id": f"fixture-{task['task_id']}",
        "mechanism": "host-native",
    }
    return execution_context.build_accepted_task_result(
        task,
        binding,
        {
            "result": {"state": "completed", "summary": "Validated fixture."},
            "changes": {"files": [{"path": "runtime.py", "change": "updated"}]},
            "task_fit_check": {"task": task["task_id"], "result": "clean"},
        },
        {
            "result_state": "completed",
            "task_ownership": ownership,
            "observed_validation": [
                {"id": task["validation"][0]["id"], "observation_id": observation_id, "result": "passed"}
            ],
            "knowledge_disposition": {
                "action": "none",
                "reason": "Fixture changes no durable authority.",
                "affected_authority": [],
            },
        },
        accepted_at="2026-09-13T00:00:00Z",
    )


def _archive(control_root: Path, root: Path, command: str, accepted: dict, task: dict):
    return plans._observe_archive_obligations(
        control_root, command, root, [(accepted, task)]
    )


def _public_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    control_root: Path,
    root: Path,
    command: str,
    accepted: dict,
    task: dict,
):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "## Tests\n\n| Test Type | Command |\n| --- | --- |\n"
        f"| Integration | `{command}` |\n"
    )
    monkeypatch.setattr(plans, "_material_repository_root", lambda *_: root)
    monkeypatch.setattr(plans, "resolve_workspace_root", lambda *_: control_root)
    plans._assert_archive_plan_acceptance(
        type("Args", (), {"project_root": str(control_root), "workspace_root": str(control_root)})(),
        "plan-001",
        plan,
        [(accepted, task)],
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
    root, control, counter, accepted, task, _binding, command, first = _fixture(tmp_path, monkeypatch)

    observed = _archive(control, root, command, accepted, task)

    assert counter.read_text() == "1"
    assert observed == [
        {"id": "VAL-001", "observation_id": first["observation_id"], "result": "passed"}
    ]
    state = json.loads(
        (control / ".work-bundle/runtime/completion-provenance/completion-provenance-v1.json").read_text()
    )
    assert state["consumptions"] == {}


@pytest.mark.parametrize("change", ["source", "dependency", "validation"])
def test_current_authority_rejects_claim_relevant_changes_without_archive_rerun(
    tmp_path, monkeypatch, change
):
    root, _control, counter, accepted, task, binding, _command, _first = _fixture(
        tmp_path, monkeypatch
    )
    changed = deepcopy(task)
    if change == "source":
        accepted["accepted_source"]["tree"] = "f" * 40
        expected = "source authority changed"
    elif change == "dependency":
        changed["depends_on"] = ["task-upstream"]
        expected = "task authority changed"
    else:
        changed["validation"][0]["command"] = "python -m pytest -q"
        expected = "validation authority changed"

    with pytest.raises(SystemExit, match=expected):
        execution_context.assert_accepted_task_result_current(changed, binding, accepted)

    assert counter.read_text() == "1"


def test_changed_validation_allocation_requires_reassessment_without_archive_rerun(tmp_path, monkeypatch):
    root, control, counter, accepted, task, _binding, command, _first = _fixture(tmp_path, monkeypatch)
    changed = deepcopy(task)
    changed["validation"][0]["invariant_ids"] = ["INV-002"]

    with pytest.raises(SystemExit, match="accepted harness observation"):
        _public_archive(tmp_path, monkeypatch, control, root, command, accepted, changed)

    assert counter.read_text() == "1"
    state = json.loads(
        (control / ".work-bundle/runtime/completion-provenance/completion-provenance-v1.json").read_text()
    )
    assert len(state["observations"]) == 1


def test_time_stale_observation_remains_explicitly_bound_after_acceptance(tmp_path, monkeypatch):
    root, control, counter, accepted, task, _binding, command, first = _fixture(tmp_path, monkeypatch)
    store_path = control / ".work-bundle/runtime/completion-provenance/completion-provenance-v1.json"
    state = json.loads(store_path.read_text())
    state["observations"][0]["freshness_deadline"] = "2000-01-01T00:00:00Z"
    store_path.write_text(json.dumps(state))

    observed = _archive(control, root, command, accepted, task)

    assert counter.read_text() == "1"
    assert observed == [
        {"id": "VAL-001", "observation_id": first["observation_id"], "result": "passed"}
    ]


def test_malformed_harness_observation_blocks_without_archive_rerun(tmp_path, monkeypatch):
    root, control, counter, accepted, task, _binding, command, _first = _fixture(tmp_path, monkeypatch)
    store_path = control / ".work-bundle/runtime/completion-provenance/completion-provenance-v1.json"
    state = json.loads(store_path.read_text())
    del state["observations"][0]["result"]["exit_code"]
    store_path.write_text(json.dumps(state))

    with pytest.raises(SystemExit, match="accepted harness observation"):
        _public_archive(tmp_path, monkeypatch, control, root, command, accepted, task)

    assert counter.read_text() == "1"
    assert len(json.loads(store_path.read_text())["observations"]) == 1


def test_distinct_accepted_obligations_each_reuse_without_lifecycle_replay(tmp_path, monkeypatch):
    root, control, counter, accepted, task, _binding, command, _ = _fixture(tmp_path, monkeypatch)
    other = deepcopy(task)
    other["task_id"] = "task-002"
    other["validation"][0]["id"] = "VAL-002"
    evidence = capture_repository_evidence(root)
    binding_two = {
        "control_root": str(control),
        "execution_path": str(root),
        "workspace_id": "workspace-001",
        "execution_id": "execution-001",
        "repository_id": "repository-001",
        "plan_id": "plan-001",
        "task_id": "task-002",
        "git_identity": {"branch_ref": "refs/heads/master"},
        "baseline": {"head": evidence["head"], "tree": evidence["tree"]},
        "ownership": {
            "binding_id": "binding:plan-001:task-002",
            "state": "active",
            "current_owner": "task-002",
            "original_owner": "task-002",
            "history": [{"event": "created"}],
        },
    }
    second = completion_provenance.observe_validation(
        binding_two,
        other,
        other["validation"][0],
        evidence,
        lambda receipt: execution_context._observe_validation_item(other["validation"][0], root, other, receipt),
        lambda: capture_repository_evidence(root),
    )
    accepted_two = _accepted_result(other, binding_two, str(second["observation_id"]))
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
    assert {item["observation_id"] for item in observed} == {
        accepted["validation_evidence_ids"][0],
        accepted_two["validation_evidence_ids"][0],
    }


def test_executor_authored_receipt_id_is_not_independent_archive_proof(tmp_path, monkeypatch):
    root, control, counter, accepted, task, _binding, command, _ = _fixture(tmp_path, monkeypatch)
    accepted["validation_evidence_ids"] = ["executor-forged-observation"]

    with pytest.raises(SystemExit, match="accepted harness observation"):
        _public_archive(tmp_path, monkeypatch, control, root, command, accepted, task)

    assert counter.read_text() == "1"


def test_archive_acceptance_uses_observation_contract_instead_of_direct_runner(tmp_path, monkeypatch):
    root, control, counter, accepted, task, _binding, command, _ = _fixture(tmp_path, monkeypatch)
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
