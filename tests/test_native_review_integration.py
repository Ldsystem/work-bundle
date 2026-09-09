from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest
from reviewer_run_fixtures import bind_review_receipt


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"
WORK_BUNDLE = REPO_ROOT / "scripts" / "work-bundle"
for module_root in (WORK_BUNDLE, ORCHESTRATION):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

import execution_context  # noqa: E402
import completion_provenance  # noqa: E402
import execution_workspace  # noqa: E402
import review_runtime  # noqa: E402
import reviewer_workspace  # noqa: E402


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _persist_production_binding(
    control: Path,
    source: Path,
    task: dict[str, object],
    *,
    execution_id: str,
    baseline: dict[str, str],
) -> dict[str, object]:
    plan_id = str(task["plan_id"])
    task_id = str(task["task_id"])
    workspace_id = "workspace-native"
    repository_id = "repo-native"
    runtime_root = control / "execution-workspaces"
    registered = execution_workspace.register_existing(
        source,
        workspace_id=workspace_id,
        execution_id=execution_id,
        repository_id=repository_id,
        created_for=task_id,
        owner="harness",
        runtime_root=runtime_root,
    )
    ownership = completion_provenance.execution_binding_ownership(
        control / ".work-bundle/runtime/completion-provenance",
        binding_id=f"binding:{plan_id}:{task_id}",
        target_kind="git_backed",
        owner=task_id,
    )
    binding = {
        "plan_id": plan_id,
        "task_id": task_id,
        "workspace_id": workspace_id,
        "execution_id": execution_id,
        "repository_id": repository_id,
        "runtime_root": str(runtime_root),
        "execution_path": str(source.resolve()),
        "control_root": str(control.resolve()),
        "state_path": registered["state_path"],
        "git_identity": registered["git_identity"],
        "write_scope": list(task.get("files", {}).get("write", [])),
        "forbidden_scope": list(task.get("files", {}).get("forbidden", [])),
        "ownership": ownership,
        "mutating": True,
        "baseline": baseline,
    }
    execution_context._persist_binding(binding, control)
    return execution_context.load_task_execution_binding(control, plan_id, task_id)


def _establish_reviewed_plan_authority(control: Path, plan_id: str) -> None:
    orchestration = control / ".work-bundle/orchestration"
    metadata = control / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        f"metadata_version: 3\nworkspace_root: {control}\nworkspace_mode: single-repository\n",
        encoding="utf-8",
    )
    specification = orchestration / "spec/active/spec.md"
    plan = orchestration / "plan/active/plan.md"
    specification.parent.mkdir(parents=True, exist_ok=True)
    plan.parent.mkdir(parents=True, exist_ok=True)
    specification.write_text(
        "---\nid: spec-native\nstatus: verified\n"
        "requirements: [{id: REQ-NATIVE, requirement: product.py defines VALUE as 1.}]\n"
        "---\n- **REQ-NATIVE**: product.py defines VALUE as 1.\n",
        encoding="utf-8",
    )
    plan.write_text(
        f"---\nid: {plan_id}\nstatus: Planned\nsource_spec: [spec-native]\n---\nNative test plan.\n",
        encoding="utf-8",
    )
    reviews = orchestration / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    for stage, identity in (
        ("specification", review_runtime.artifact_review_identity(specification)),
        ("plan", review_runtime.plan_review_identity(control, plan)),
    ):
        record = {
            "review_id": f"review-{stage}-{plan_id}",
            "stage": stage,
            "target_identity": identity,
            "review_mode": "initial",
            "review_target_kind": "stage",
            "repair_frontier": None,
            "review_reset": None,
            "reviewer": {
                "agent_id": f"reviewer-{stage}", "capability": "judgment",
                "authorship": "none", "repair_participation": "none",
                "decision_participation": "none", "deliberation_participation": "none",
                "context_origin": "direct_source",
            },
            "evidence": {
                "mode": "direct", "capabilities": ["source inspection"],
                "unavailable_evidence": [], "commands": [], "artifacts": [],
            },
            "verdict": "accepted", "findings": [],
            "started_at": "2026-09-09T00:00:00Z",
            "completed_at": "2026-09-09T00:01:00Z",
            "staleness": {"is_stale": False, "reason": None, "supersedes": None},
        }
        (reviews / f"{stage}.json").write_text(
            json.dumps(bind_review_receipt(control, record)), encoding="utf-8"
        )


def _harness_validation(control: Path, source: Path) -> tuple[dict[str, object], Path]:
    counter = control / "harness-validation-count.txt"
    program = control / "validate-product.py"
    program.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "counter = Path(sys.argv[2])\n"
        "count = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(count + 1))\n"
        "namespace = {}\n"
        "exec(Path(sys.argv[1]).read_text(), namespace)\n"
        "raise SystemExit(0 if namespace.get('VALUE') == 1 else 1)\n",
        encoding="utf-8",
    )
    command = shlex.join(
        [sys.executable, str(program), str(source / "product.py"), str(counter)]
    )
    return {
        "id": "VAL-NATIVE",
        "kind": "process",
        "command": command,
        "invariant_ids": ["INV-NATIVE"],
        "capability_reason": "The harness process directly checks the required product value.",
        "proves": "REQ-NATIVE",
        "expected": "passed",
        "evidence_reuse": {"mode": "deterministic", "max_age_seconds": 3600},
    }, counter


def _validation_capability(task_id: str) -> dict[str, object]:
    return {
        "result": "mapped",
        "reason": "The harness command directly falsifies an incorrect product value.",
        "invariants": [{
            "id": "INV-NATIVE",
            "source_ids": ["REQ-NATIVE"],
            "invariant": "product.py defines VALUE as 1.",
            "boundary": "product.py",
            "oracle": "VAL-NATIVE",
            "capability_reason": "The harness imports and checks the exact value.",
            "freshness": "current_task_batch",
            "task_id": task_id,
            "evidence_ids": ["VAL-NATIVE"],
            "closure_result": "pending",
        }],
    }


def _invocation_counts(
    executor_events: list[dict[str, object]], receipt: dict[str, object], counter: Path,
) -> tuple[int, int, int]:
    review_events = [
        json.loads(line)
        for line in Path(str(receipt["receipt_path"])).with_suffix(".stdout.jsonl").read_text().splitlines()
    ]
    return (
        sum(event.get("type") == "thread.started" for event in executor_events),
        sum(event.get("type") == "thread.started" for event in review_events),
        int(counter.read_text(encoding="utf-8")),
    )


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
    _establish_reviewed_plan_authority(control, "plan-native")
    validation, validation_counter = _harness_validation(control, source)

    task = {
        "plan_id": "plan-native",
        "task_id": "task-native",
        "source_ids": ["REQ-NATIVE"],
        "goal": "Create the requested product constant",
        "requirements": ["product.py must define VALUE with the integer value 1."],
        "constraints": ["The implementation must remain within product.py."],
        "truth_basis": {"decision_authority": []},
        "files": {"read": ["product.py"], "write": ["product.py"], "forbidden": []},
        "validation": [validation],
        "evidence_capability": _validation_capability("task-native"),
        "review_required": True,
        "workspace": {"root": str(control)},
    }
    _persist_production_binding(
        control,
        source,
        task,
        execution_id="executor-run",
        baseline={"head": head, "tree": tree},
    )
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
        "repository": [{
            "root": str(source.resolve()),
            "target_kind": "git-backed",
            "preflight_kind": "git-clean-worktree",
            "baseline": "initial",
            "status": "clean",
        }],
        "codegraph": [{
            "root": str(source.resolve()),
            "applicable": False,
            "up_to_date": False,
            "reason": "no-index",
        }],
        "evidence_closure": {
            "result": "passed",
            "invariants": [{
                "id": "INV-NATIVE",
                "boundary": "product.py",
                "freshness": "current_task_batch",
                "evidence_ids": ["VAL-NATIVE"],
                "closure_result": "passed",
                "repair_owner": None,
            }],
        },
        "validation": {
            "commands": [
                    {
                        "id": "VAL-NATIVE",
                        "command": validation["command"],
                        "invariant_ids": ["INV-NATIVE"],
                        "result": "passed",
                }
            ]
        },
    }
    validated = execution_context.validate_executor_result_for_task(
        original_handoff,
        task,
        observe=True,
        mutation_events=[{"actor_kind": "subagent", "paths": ["product.py"]}],
        preparing_review=True,
    )
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
    authority = control / "task-authority.json"
    authority.write_text(json.dumps(task, sort_keys=True), encoding="utf-8")
    packet = reviewer_workspace.build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[protected],
        artifacts=[
            "source:product.py",
            "control:task-authority.json",
            "control:.work-bundle/runtime/completion-provenance/completion-provenance-v1.json",
        ],
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

    receipt = reviewer_workspace.run_native_reviewer(
        Path(str(created["workspace_path"])),
        Path(sys.executable),
        model="test-model",
        review_instructions=(
            "Judge the task authority, source, and harness-owned validation evidence. Return repair "
            "for unmet requirements; otherwise return accept."
        ),
    )
    review = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
    reference = review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    )
    fixture_executor_events = [{"type": "thread.started", "thread_id": "executor-run"}]
    counts_after_publication = _invocation_counts(
        fixture_executor_events, receipt, validation_counter
    )
    assert review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    ) == reference
    counts_after_publication_retry = _invocation_counts(
        fixture_executor_events, receipt, validation_counter
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
    counts_after_consumption = _invocation_counts(
        fixture_executor_events, receipt, validation_counter
    )
    stored = execution_context.load_task_execution_binding(control, "plan-native", "task-native")

    assert native_calls == 1
    assert counts_after_publication == counts_after_publication_retry == counts_after_consumption == (
        1, 1, 1
    )
    assert original_handoff == handoff_before_review
    assert accepted == consumed == stored["accepted_result"]
    assert accepted["baseline_identity"] == {"head": head, "tree": tree}
    assert accepted["review_id"] == review["review_id"]
    assert accepted["validation_evidence_ids"] == [
        validated["observed_validation"][0]["observation_id"]
    ]
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


def test_incorrect_executor_result_cannot_reach_acceptance_by_matching_review_shape(
    tmp_path: Path, monkeypatch,
) -> None:
    source = tmp_path / "source"
    control = tmp_path / "control"
    source.mkdir()
    control.mkdir()
    (source / "product.py").write_text("VALUE = 0\n", encoding="utf-8")
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
        "incorrect executor output",
    )
    head = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")
    _establish_reviewed_plan_authority(control, "plan-negative")
    validation, validation_counter = _harness_validation(control, source)
    task = {
        "plan_id": "plan-negative",
        "task_id": "task-negative",
        "source_ids": ["REQ-NATIVE"],
        "goal": "Produce the required product value",
        "requirements": ["product.py must define VALUE with the integer value 1."],
        "constraints": [],
        "truth_basis": {"decision_authority": ["REQ-NATIVE is authoritative."]},
        "files": {"read": ["product.py"], "write": ["product.py"], "forbidden": []},
        "validation": [validation],
        "evidence_capability": _validation_capability("task-negative"),
        "review_required": True,
        "workspace": {"root": str(control)},
    }
    _persist_production_binding(
        control,
        source,
        task,
        execution_id="executor-negative",
        baseline={"head": head, "tree": tree},
    )
    handoff = {
        "type": "executor-result",
        "related": {"plan": "plan-negative", "task": "task-negative"},
        "result": {"state": "completed", "summary": "Produced the requested value."},
        "changes": {"files": [{"path": "product.py", "change": "updated"}]},
        "task_fit_check": {"task": "task-negative", "result": "clean"},
        "knowledge_disposition": {
            "action": "none", "reason": "No durable authority changed.", "affected_authority": [],
        },
        "acceptance_review": {"required": True, "verdict": "pending"},
        "delegation_evidence": {
            "delegated": True,
            "owner_kind": "subagent",
            "agent_id": "executor-negative",
            "run_id": "executor-negative",
            "mechanism": "host-native",
        },
        "repository": [{
            "root": str(source.resolve()), "target_kind": "git-backed",
            "preflight_kind": "git-clean-worktree", "baseline": "initial", "status": "clean",
        }],
        "codegraph": [{
            "root": str(source.resolve()), "applicable": False,
            "up_to_date": False, "reason": "no-index",
        }],
        "evidence_closure": {
            "result": "passed",
            "invariants": [{
                "id": "INV-NATIVE", "boundary": "product.py",
                "freshness": "current_task_batch", "evidence_ids": ["VAL-NATIVE"],
                "closure_result": "passed", "repair_owner": None,
            }],
        },
        "validation": {"commands": [{
            "id": "VAL-NATIVE", "command": validation["command"],
            "invariant_ids": ["INV-NATIVE"], "result": "passed",
        }]},
    }
    review_calls = 0

    def unexpected_review(*_args):
        nonlocal review_calls
        review_calls += 1
        raise AssertionError("failed harness validation must block review dispatch")

    monkeypatch.setattr(reviewer_workspace, "_run_native_process", unexpected_review)

    with pytest.raises(SystemExit, match="does not match observed failed"):
        execution_context.validate_executor_result_for_task(
            handoff,
            task,
            observe=True,
            mutation_events=[{"actor_kind": "subagent", "paths": ["product.py"]}],
            preparing_review=True,
        )
    stored = execution_context.load_task_execution_binding(
        control, "plan-negative", "task-negative"
    )
    assert validation_counter.read_text(encoding="utf-8") == "1"
    assert review_calls == 0
    assert "accepted_result" not in stored


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
    _establish_reviewed_plan_authority(control, "plan-native-live")
    validation, validation_counter = _harness_validation(control, source)

    task = {
        "plan_id": "plan-native-live",
        "task_id": "task-native-live",
        "source_ids": ["REQ-NATIVE"],
        "goal": "Create the requested product constant",
        "requirements": ["product.py must define VALUE with the integer value 1."],
        "constraints": ["The implementation must remain within product.py."],
        "truth_basis": {
            "decision_authority": ["The requested VALUE behavior is authoritative."],
        },
        "files": {"read": ["product.py"], "write": ["product.py"], "forbidden": []},
        "validation": [validation],
        "evidence_capability": _validation_capability("task-native-live"),
        "review_required": True,
        "workspace": {"root": str(control)},
    }
    _persist_production_binding(
        control,
        source,
        task,
        execution_id=executor_ids[0],
        baseline={"head": baseline_head, "tree": baseline_tree},
    )
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
        "repository": [{
            "root": str(source.resolve()),
            "target_kind": "git-backed",
            "preflight_kind": "git-clean-worktree",
            "baseline": "initial",
            "status": "clean",
        }],
        "codegraph": [{
            "root": str(source.resolve()),
            "applicable": False,
            "up_to_date": False,
            "reason": "no-index",
        }],
        "evidence_closure": {
            "result": "passed",
            "invariants": [{
                "id": "INV-NATIVE",
                "boundary": "product.py",
                "freshness": "current_task_batch",
                "evidence_ids": ["VAL-NATIVE"],
                "closure_result": "passed",
                "repair_owner": None,
            }],
        },
        "validation": {"commands": [{
            "id": "VAL-NATIVE",
            "command": validation["command"],
            "invariant_ids": ["INV-NATIVE"],
            "result": "passed",
        }]},
    }
    validated = execution_context.validate_executor_result_for_task(
        handoff,
        task,
        observe=True,
        mutation_events=[{"actor_kind": "subagent", "paths": ["product.py"]}],
        preparing_review=True,
    )
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
    authority = control / "task-authority.json"
    authority.write_text(json.dumps(task, sort_keys=True), encoding="utf-8")
    packet = reviewer_workspace.build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[protected],
        artifacts=[
            "source:product.py",
            "control:task-authority.json",
            "control:.work-bundle/runtime/completion-provenance/completion-provenance-v1.json",
        ],
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
            "Independently judge the supplied task source against task-authority.json. Return a "
            "task_review JSON object for the supplied reviewed_head. Set verdict to accept only "
            "when every requirement is satisfied; otherwise set it to repair and report concrete "
            "findings using the required review contract."
        ),
    )
    review = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
    assert review["reviewer"]["agent_id"] != executor_ids[0]
    reference = review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    )
    counts_after_publication = _invocation_counts(
        executor_events, receipt, validation_counter
    )
    assert review_runtime.publish_review(
        control, review, current_target_identity=target_identity
    ) == reference
    counts_after_publication_retry = _invocation_counts(
        executor_events, receipt, validation_counter
    )

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
    counts_after_consumption = _invocation_counts(
        executor_events, receipt, validation_counter
    )
    assert counts_after_publication == counts_after_publication_retry == counts_after_consumption == (
        1, 1, 1
    )
    assert consumed == accepted
    assert accepted["review_id"] == review["review_id"]
    assert accepted["baseline_identity"] == {
        "head": baseline_head,
        "tree": baseline_tree,
    }
