from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
WORK_BUNDLE = REPO_ROOT / "scripts" / "work-bundle"
for module_root in (WORK_BUNDLE, ORCHESTRATION):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

import execution_context  # noqa: E402
import review_runtime  # noqa: E402
import reviewer_workspace  # noqa: E402


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _native_events(result: dict[str, object]) -> str:
    events = [
        {
            "type": "thread.started",
            "thread_id": "01a0821d-f359-7d60-a9bd-90dd0e006166",
        },
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "judgment",
                "type": "agent_message",
                "text": json.dumps(result),
            },
        },
        {"type": "turn.completed", "usage": {}},
    ]
    return "\n".join(json.dumps(event) for event in events)


def test_plugin_absent_native_review_publishes_once_then_materializes_initial_acceptance(
    tmp_path: Path, monkeypatch,
) -> None:
    source = tmp_path / "source"
    control = tmp_path / "control"
    source.mkdir()
    control.mkdir()
    (source / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(source, "init", "-q")
    _git(source, "add", "product.py")
    _git(
        source,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    head = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")

    task = {
        "plan_id": "plan-native",
        "task_id": "task-native",
        "source_ids": ["REQ-NATIVE"],
        "truth_basis": {"decision_authority": []},
        "files": {"read": ["product.py"], "write": ["product.py"], "forbidden": []},
        "validation": [
            {
                "id": "VAL-NATIVE",
                "kind": "process",
                "command": "python -m pytest tests/product.py -q",
                "invariant_ids": ["INV-NATIVE"],
            }
        ],
        "review_required": True,
        "workspace": {"root": str(control)},
    }
    binding = {
        "plan_id": "plan-native",
        "task_id": "task-native",
        "workspace_id": "workspace-native",
        "execution_id": "executor-run",
        "repository_id": "repo-native",
        "execution_path": str(source),
        "control_root": str(control),
        "git_identity": {"branch_ref": "refs/heads/main"},
        "baseline": {"head": head, "tree": tree},
        "ownership": {
            "binding_id": "binding:plan-native:task-native",
            "state": "active",
            "current_owner": "task-native",
            "history": [{"event": "created"}],
        },
    }
    original_handoff = {
        "type": "executor-result",
        "related": {"plan": "plan-native", "task": "task-native"},
        "result": {"state": "completed", "summary": "Implemented native fixture."},
        "changes": {"files": [{"path": "product.py", "change": "updated"}]},
        "task_fit_check": {"task": "task-native", "result": "clean"},
        "knowledge_disposition": {
            "action": "none",
            "reason": "No durable authority changed.",
            "affected_authority": [],
        },
        "acceptance_review": {"required": True, "verdict": "pending"},
        "delegation_evidence": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "executor-agent",
            "run_id": "executor-run",
            "mechanism": "host-native",
        },
        "validation": {
            "commands": [
                {
                    "command": "python -m pytest tests/product.py -q",
                    "result": "passed",
                }
            ]
        },
    }
    validated = {
        "result_state": "completed",
        "knowledge_disposition": original_handoff["knowledge_disposition"],
        "task_ownership": original_handoff["delegation_evidence"],
        "observed_validation": [
            {
                "id": "VAL-NATIVE",
                "observation_id": "observation-native",
                "result": "passed",
            }
        ],
    }
    handoff_before_review = deepcopy(original_handoff)
    target_identity = {
        "artifact_id": "task-native",
        "revision": head,
        "sha256": hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest(),
        "source_tree": tree,
    }
    task_review_context = {
        "target_identity": target_identity,
        "agent_id": "unbound-native-reviewer",
        "capability": "judgment",
        "execution_id": "unbound-native-reviewer",
        "evidence_mode": "reproducible_snapshot",
        "review_mode": "initial",
        "review_target_kind": "task",
        "repair_frontier": None,
        "review_reset": None,
    }
    protected = control / ".protected"
    protected.mkdir()
    packet = reviewer_workspace.build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[protected],
        artifacts=["source:product.py"],
        search_roots=[],
        validators=[],
        sentinels=[],
        network_state="denied",
        task_review_context=task_review_context,
    )
    created = reviewer_workspace.create_reviewer_workspace(
        review_runtime.reviewer_runtime_root(control), "review-native-initial", packet
    )
    judgment = {
        "task_review": {"reviewed_head": head, "verdict": "accept", "findings": []}
    }
    native_calls = 0

    def run_native(*_args):
        nonlocal native_calls
        native_calls += 1
        return subprocess.CompletedProcess([], 0, _native_events(judgment), "")

    monkeypatch.setattr(reviewer_workspace, "_run_native_process", run_native)
    monkeypatch.setattr(
        execution_context,
        "load_task_execution_binding",
        lambda *_args: binding,
    )
    persisted: dict[str, object] = {}

    def persist(value, _root):
        persisted.update(value)
        binding.clear()
        binding.update(value)

    monkeypatch.setattr(
        execution_context,
        "_persist_binding",
        persist,
    )

    receipt = reviewer_workspace.run_native_reviewer(
        Path(str(created["workspace_path"])),
        Path(sys.executable),
        model="test-model",
        review_instructions="Review the supplied task source and return a task judgment.",
    )
    review = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
    reference = review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    )
    assert review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    ) == reference

    monkeypatch.setattr(
        execution_context,
        "_claim_bound_validation_observations",
        lambda *_args, **_kwargs: pytest.fail("current validation must not be replayed"),
    )
    accepted = execution_context.materialize_accepted_task_review(
        control,
        task,
        reference,
        {
            "causal_class": "initial_acceptance",
            "affected_task": "task-native",
            "authorized_lifecycle_action": "materialize_accepted_result",
        },
        executor_handoff=original_handoff,
        validated_executor_result=validated,
    )
    _, consumed = execution_context.load_current_accepted_task_result(control, task)

    assert native_calls == 1
    assert original_handoff == handoff_before_review
    assert accepted == consumed == persisted["accepted_result"]
    assert accepted["baseline_identity"] == {"head": head, "tree": tree}
    assert accepted["review_id"] == review["review_id"]
    assert accepted["validation_evidence_ids"] == ["observation-native"]
    assert accepted["owner_identity"]["agent_id"] == "executor-agent"
    assert review["reviewer"]["agent_id"] != accepted["owner_identity"]["agent_id"]
    request = json.loads(Path(receipt["receipt_path"]).with_suffix(".request.json").read_text())
    assert "execution-flow" not in json.dumps(request).lower()

    task["validation"][0]["command"] = "python -m pytest tests/changed.py -q"
    with pytest.raises(SystemExit, match="validation authority changed"):
        execution_context.load_current_accepted_task_result(control, task)


def test_missing_native_host_capability_fails_before_review_dispatch(
    tmp_path: Path, monkeypatch,
) -> None:
    dispatched = False

    def unexpected_dispatch(*_args):
        nonlocal dispatched
        dispatched = True
        raise AssertionError("review dispatch must not occur")

    monkeypatch.setattr(reviewer_workspace, "_run_native_process", unexpected_dispatch)
    missing = tmp_path / "missing-native-host"
    with pytest.raises(
        reviewer_workspace.ReviewerWorkspaceError,
        match="WB_REVIEW_NATIVE_CAPABILITY_UNAVAILABLE",
    ) as failure:
        reviewer_workspace.run_native_reviewer(
            tmp_path,
            missing,
            model="test-model",
            review_instructions="Review the supplied task.",
        )

    assert failure.value.result == {"capability": "native_reviewer_executable"}
    assert dispatched is False


@pytest.mark.skipif(
    os.environ.get("WB_NATIVE_REVIEW_INTEGRATION") != "1",
    reason="set WB_NATIVE_REVIEW_INTEGRATION=1 for the genuine native host observation",
)
def test_live_plugin_absent_native_execution_review_publication_and_acceptance(
    tmp_path: Path, monkeypatch,
) -> None:
    executable_text = os.environ.get("WB_NATIVE_REVIEW_EXECUTABLE") or shutil.which("codex")
    if not executable_text:
        pytest.fail("native_executor_executable capability is unavailable")
    executable = Path(executable_text).expanduser().resolve()
    model = os.environ.get("WB_NATIVE_REVIEW_MODEL", "gpt-6-astra")
    source = tmp_path / "source"
    control = tmp_path / "control"
    scratch = tmp_path / "scratch"
    source.mkdir()
    control.mkdir()
    scratch.mkdir()
    (source / "README.md").write_text("native integration fixture\n", encoding="utf-8")
    _git(source, "init", "-q")
    _git(source, "add", "README.md")
    _git(
        source,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "baseline",
    )
    baseline_head = _git(source, "rev-parse", "HEAD")
    baseline_tree = _git(source, "rev-parse", "HEAD^{tree}")

    executor_argv = [
        str(executable),
        "exec",
        "--ignore-user-config",
        "--sandbox",
        "workspace-write",
        "--ephemeral",
        "--json",
        "--skip-git-repo-check",
        "-C",
        str(source),
        "-m",
        model,
        "-c",
        'model_reasoning_effort="medium"',
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        'web_search="disabled"',
        "--enable",
        "skip_host_skill_discovery",
        "--disable",
        "remote_plugin",
        "--disable",
        "recommended_plugins",
        "--disable",
        "apps",
        "--disable",
        "multi_agent",
        "-",
    ]
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": str(Path.home()),
        "TMPDIR": str(scratch),
    }
    if os.environ.get("CODEX_HOME"):
        environment["CODEX_HOME"] = os.environ["CODEX_HOME"]
    executor = subprocess.run(
        executor_argv,
        cwd=source,
        env=environment,
        input=(
            "Create product.py in this workspace with exactly this UTF-8 content: "
            "VALUE = 1 followed by one newline. Do not use network access. "
            "Finish only after verifying the file exists."
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=1800,
    )
    assert executor.returncode == 0, executor.stderr
    assert (source / "product.py").read_bytes() == b"VALUE = 1\n"
    executor_events = [json.loads(line) for line in executor.stdout.splitlines()]
    executor_ids = [
        event["thread_id"]
        for event in executor_events
        if event.get("type") == "thread.started"
    ]
    assert len(executor_ids) == 1
    assert sum(event.get("type") == "turn.completed" for event in executor_events) == 1
    _git(source, "add", "product.py")
    _git(
        source,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "native executor result",
    )
    head = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")

    task = {
        "plan_id": "plan-native-live",
        "task_id": "task-native-live",
        "source_ids": ["REQ-NATIVE"],
        "truth_basis": {"decision_authority": []},
        "files": {"read": ["product.py"], "write": ["product.py"], "forbidden": []},
        "validation": [],
        "review_required": True,
        "workspace": {"root": str(control)},
    }
    binding = {
        "plan_id": "plan-native-live",
        "task_id": "task-native-live",
        "workspace_id": "workspace-native-live",
        "execution_id": executor_ids[0],
        "repository_id": "repo-native-live",
        "execution_path": str(source),
        "control_root": str(control),
        "git_identity": {"branch_ref": "refs/heads/main"},
        "baseline": {"head": baseline_head, "tree": baseline_tree},
        "ownership": {
            "binding_id": "binding:plan-native-live:task-native-live",
            "state": "active",
            "current_owner": "task-native-live",
            "history": [{"event": "created"}],
        },
    }
    handoff = {
        "type": "executor-result",
        "related": {"plan": "plan-native-live", "task": "task-native-live"},
        "result": {"state": "completed", "summary": "Created product.py."},
        "changes": {"files": [{"path": "product.py", "change": "created"}]},
        "task_fit_check": {"task": "task-native-live", "result": "clean"},
        "knowledge_disposition": {
            "action": "none",
            "reason": "No durable authority changed.",
            "affected_authority": [],
        },
        "acceptance_review": {"required": True, "verdict": "pending"},
        "delegation_evidence": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": executor_ids[0],
            "run_id": executor_ids[0],
            "mechanism": "host-native",
        },
        "validation": {"commands": []},
    }
    validated = {
        "result_state": "completed",
        "knowledge_disposition": handoff["knowledge_disposition"],
        "task_ownership": handoff["delegation_evidence"],
        "observed_validation": [],
    }
    target_identity = {
        "artifact_id": "task-native-live",
        "revision": head,
        "sha256": hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest(),
        "source_tree": tree,
    }
    context = {
        "target_identity": target_identity,
        "agent_id": "unbound-native-reviewer",
        "capability": "judgment",
        "execution_id": "unbound-native-reviewer",
        "evidence_mode": "reproducible_snapshot",
        "review_mode": "initial",
        "review_target_kind": "task",
        "repair_frontier": None,
        "review_reset": None,
    }
    protected = control / ".protected"
    protected.mkdir()
    packet = reviewer_workspace.build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[protected],
        artifacts=["source:product.py"],
        search_roots=[],
        validators=[],
        sentinels=[],
        network_state="denied",
        task_review_context=context,
    )
    created = reviewer_workspace.create_reviewer_workspace(
        review_runtime.reviewer_runtime_root(control), "review-native-live", packet
    )
    receipt = reviewer_workspace.run_native_reviewer(
        Path(str(created["workspace_path"])),
        executable,
        model=model,
        review_instructions=(
            "Independently review the supplied task source. Return only a final JSON object "
            f'with exactly this shape: {{"task_review":{{"reviewed_head":"{head}",'
            '"verdict":"accept","findings":[]}}}. Accept only if the evidence satisfies the task.'
        ),
    )
    review = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
    assert review["reviewer"]["agent_id"] != executor_ids[0]
    reference = review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    )
    assert review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    ) == reference

    monkeypatch.setattr(
        execution_context, "load_task_execution_binding", lambda *_args: binding
    )

    def persist(value, _root):
        binding.clear()
        binding.update(value)

    monkeypatch.setattr(execution_context, "_persist_binding", persist)
    accepted = execution_context.materialize_accepted_task_review(
        control,
        task,
        reference,
        {
            "causal_class": "initial_acceptance",
            "affected_task": "task-native-live",
            "authorized_lifecycle_action": "materialize_accepted_result",
        },
        executor_handoff=handoff,
        validated_executor_result=validated,
    )
    _, consumed = execution_context.load_current_accepted_task_result(control, task)
    assert consumed == accepted
    assert accepted["review_id"] == review["review_id"]
    assert accepted["baseline_identity"] == {
        "head": baseline_head,
        "tree": baseline_tree,
    }
