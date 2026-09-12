from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DARWIN_SANDBOX_SHELL = "/bin/sh"
WORK_BUNDLE_SCRIPTS = REPO_ROOT / "scripts" / "work-bundle"
if str(WORK_BUNDLE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WORK_BUNDLE_SCRIPTS))

from reviewer_workspace import (  # noqa: E402
    ReviewerWorkspaceError,
    build_direct_evidence_packet,
    cleanup_reviewer_workspace,
    create_reviewer_workspace,
    enforce_reviewer_write_scope,
    execute_reviewer_request,
)
import reviewer_workspace  # noqa: E402

ORCHESTRATION_SCRIPTS = REPO_ROOT / "scripts" / "orchestration"
if str(ORCHESTRATION_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATION_SCRIPTS))
import bounded_closure  # noqa: E402


def native_events(result, *, thread_id="01a0821d-f359-7d60-a9bd-90dd0e006166"):
    return "\n".join(json.dumps(event) for event in [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item-1", "type": "agent_message", "text": json.dumps(result)}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 10}},
    ])


def test_native_transcript_requires_one_actual_fresh_completed_judgment():
    run, result = reviewer_workspace.parse_native_reviewer_transcript(native_events({"verdict": "repair"}))
    assert run == "01a0821d-f359-7d60-a9bd-90dd0e006166"
    assert result == {"verdict": "repair"}
    for forged in [json.dumps({"verdict": "accept"}), native_events({}) + "\n" + native_events({}),
                   native_events({}).rsplit("\n", 1)[0]]:
        with pytest.raises(ReviewerWorkspaceError, match="NATIVE_TRANSCRIPT"):
            reviewer_workspace.parse_native_reviewer_transcript(forged)


def test_native_observed_catalog_notice_is_initialization_only():
    notice = {"type": "item.completed", "item": {"id": "warning", "type": "error", "message":
        "Skill descriptions were shortened to fit the skills context budget. Codex can still see every skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room for the rest."}}
    events = native_events({"verdict": "repair"}).splitlines()
    events.insert(2, json.dumps(notice))
    assert reviewer_workspace.parse_native_reviewer_transcript("\n".join(events))[1] == {"verdict": "repair"}
    events.pop(2)
    events.insert(3, json.dumps(notice))
    with pytest.raises(ReviewerWorkspaceError, match="NATIVE_TRANSCRIPT"):
        reviewer_workspace.parse_native_reviewer_transcript("\n".join(events))
    events.pop(3)
    notice["item"]["message"] += " A tool also failed."
    events.insert(2, json.dumps(notice))
    with pytest.raises(ReviewerWorkspaceError, match="NATIVE_TRANSCRIPT"):
        reviewer_workspace.parse_native_reviewer_transcript("\n".join(events))


@pytest.mark.parametrize("kind", ["command_execution", "mcp_tool_call", "collab_tool_call", "error", "file_change"])
def test_native_transcript_rejects_all_observed_tool_or_failure_activity(kind):
    events = native_events({}).splitlines()
    events.insert(2, json.dumps({"type": "item.completed", "item": {"id": "tool", "type": kind}}))
    with pytest.raises(ReviewerWorkspaceError, match="NATIVE_TRANSCRIPT"):
        reviewer_workspace.parse_native_reviewer_transcript("\n".join(events))


def test_native_process_does_not_inherit_author_transport_or_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_APP_TOOLS_PIPE_PATH", "caller-transport")
    monkeypatch.setenv("CODEX_THREAD_ID", "author-thread")
    monkeypatch.setenv("CODEX_SESSION_ID", "author-session")
    monkeypatch.setenv("BASH_ENV", "/host/instructions")
    with patch.object(reviewer_workspace.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as launch:
        reviewer_workspace._run_native_process(tmp_path, ["/bin/codex"], "bounded packet")
    kwargs = launch.call_args.kwargs
    assert set(kwargs["env"]) <= {"PATH", "HOME", "TMPDIR", "CODEX_HOME"}
    assert kwargs["input"] == "bounded packet"
    assert kwargs["timeout"] > 0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def review_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    (source / "src").mkdir(parents=True)
    (source / "src" / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    (source / ".wor105-review-sentinel").write_text("immutable-source-sentinel-v1\n", encoding="utf-8")
    (control / "orchestration" / "reviews").mkdir(parents=True)
    (control / "orchestration" / "reviews" / "target.json").write_text('{"valid": true}\n', encoding="utf-8")
    (control / "orchestration" / "docs" / "wor105").mkdir(parents=True)
    (control / "orchestration" / "docs" / "wor105" / ".review-sentinel").write_text(
        "immutable-control-sentinel-v1\n", encoding="utf-8"
    )
    (control / "credentials").mkdir()
    (control / "credentials" / "credentials.yaml").write_text("secret-value\n", encoding="utf-8")
    return source, control, runtime


def packet(source: Path, control: Path) -> dict[str, object]:
    return build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[control / "credentials"],
        artifacts=["source:src/target.py", "control:orchestration/reviews/target.json"],
        search_roots=["source:src"],
        validators=[
            {"validator_id": "target-json", "kind": "json", "artifact": "control:orchestration/reviews/target.json"},
            {"validator_id": "source-digest", "kind": "sha256", "artifact": "source:src/target.py"},
        ],
        sentinels=["source:.wor105-review-sentinel", "control:orchestration/docs/wor105/.review-sentinel"],
        network_state="denied",
    )


def test_reviewer_dispatch_rechecks_live_round_before_launch(
    review_roots: tuple[Path, Path, Path],
) -> None:
    source, control, runtime = review_roots
    metadata = control / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "metadata_version: 4\n"
        "workspace: {id: workspace-review, slug: review, mode: single-repository}\n"
        "orchestration_control:\n"
        "  schema_version: 1\n"
        "  post_execution_review_round_limit: 5\n",
        encoding="utf-8",
    )
    target = {
        "artifact_id": "plan-live-round",
        "revision": "a" * 40,
        "sha256": "b" * 64,
        "source_tree": "c" * 40,
    }
    reserved = bounded_closure.begin_review_round(
        control,
        flow_id="plan-live-round",
        request_id="request-live-round",
        review_id="review-live-round",
        target_identity=target,
        executor_attempts=[{"execution_id": "executor-1", "state": "completed"}],
        known_missing_evidence=[],
    )
    bounded_closure.mark_review_round_prepared(
        control,
        flow_id="plan-live-round",
        round_id=str(reserved["round_id"]),
    )
    created = create_reviewer_workspace(runtime, "review-live-round", packet(source, control))
    state_path = Path(str(created["state_path"]))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["admission_workspace"] = str(control)
    state["post_execution_review"] = reserved
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    bounded_closure.complete_review_round(
        control,
        flow_id="plan-live-round",
        round_id=str(reserved["round_id"]),
        outcome="blocked",
        audit_block={"code": "repair-required"},
    )

    with patch.object(reviewer_workspace, "_run_sandboxed_process") as launch:
        with pytest.raises(
            ReviewerWorkspaceError,
            match="WB_POST_EXECUTION_JUDGMENT_ALREADY_RECORDED",
        ):
            reviewer_workspace.run_sandboxed_reviewer(
                Path(str(created["workspace_path"])), ["reviewer"]
            )
    launch.assert_not_called()


def test_packet_rejects_protected_and_outside_reads(review_roots: tuple[Path, Path, Path]) -> None:
    source, control, _ = review_roots

    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_PROTECTED_READ_DENIED"):
        build_direct_evidence_packet(
            source_root=source,
            control_root=control,
            protected_roots=[control / "credentials"],
            artifacts=["control:credentials/credentials.yaml"],
            search_roots=[],
            validators=[],
            sentinels=[],
            network_state="denied",
        )
    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_PATH_ESCAPE_DENIED"):
        build_direct_evidence_packet(
            source_root=source,
            control_root=control,
            protected_roots=[control / "credentials"],
            artifacts=["source:../host-config"],
            search_roots=[],
            validators=[],
            sentinels=[],
            network_state="denied",
        )


def test_workspace_contains_copied_direct_evidence_and_declares_network_denied(
    review_roots: tuple[Path, Path, Path]
) -> None:
    source, control, runtime = review_roots

    result = create_reviewer_workspace(runtime, "review-001", packet(source, control))

    workspace = Path(str(result["workspace_path"]))
    state = json.loads(Path(str(result["state_path"])).read_text(encoding="utf-8"))
    assert state["owner"] == "work-bundle"
    assert state["review_id"] == "review-001"
    assert state["network"] == {"state": "denied", "mechanism": "sandbox-exec-deny-network"}
    assert state["sandbox"]["mechanism"] == "sandbox-exec"
    assert state["source_evidence_digest"]
    assert state["control_evidence_digest"]
    assert (workspace / "evidence" / "source" / "src" / "target.py").is_file()
    assert (workspace / "evidence" / "control" / "orchestration" / "reviews" / "target.json").is_file()
    assert not (workspace / "evidence" / "control" / "credentials").exists()
    assert "source_root" not in json.dumps(state)
    assert "control_root" not in json.dumps(state)


@pytest.mark.parametrize("transport", ["sandbox", "native"])
def test_task_review_worker_output_receives_native_bound_receipt(
    review_roots: tuple[Path, Path, Path], transport: str
) -> None:
    source, control, _runtime = review_roots
    review_runtime = reviewer_workspace._review_runtime()
    runtime = review_runtime.reviewer_runtime_root(control)
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "src/target.py", ".wor105-review-sentinel"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
        check=True,
    )
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], text=True).strip()
    identity = {"artifact_id": "task-006", "revision": head, "sha256": "1" * 64, "source_tree": tree}
    context = {
        "target_identity": identity,
        "agent_id": "reviewer-task",
        "capability": "judgment",
        "execution_id": "review-execution-task",
        "evidence_mode": "reproducible_snapshot",
        "review_mode": "initial",
        "review_target_kind": "task",
        "repair_frontier": None,
        "review_reset": None,
    }
    direct = build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[control / "credentials"],
        artifacts=["source:src/target.py"],
        search_roots=[], validators=[], sentinels=[], network_state="denied",
        task_review_context=context,
    )
    created = create_reviewer_workspace(runtime, "review-task-native", direct)
    judgment = {"task_review": {
        "reviewed_head": head,
        "verdict": "repair",
        "findings": [{
            "finding_id": "finding-product-value",
            "severity": "blocking",
            "requirement_id": "REQ-VALUE",
            "boundary": "src/target.py:target",
            "evidence": "The returned value violates the requirement.",
            "expected": "Return the accepted value.",
            "observed": "A different value is returned.",
            "owner": "task_owner",
        }],
    }}
    if transport == "native":
        with patch.object(reviewer_workspace, "_run_native_process",
                          return_value=subprocess.CompletedProcess([], 0, native_events(judgment), "")):
            receipt = reviewer_workspace.run_native_reviewer(Path(str(created["workspace_path"])), Path(sys.executable),
                model="test-model", review_instructions="Assess the accepted product requirements against the source.")
        request = json.loads(Path(receipt["receipt_path"]).with_suffix(".request.json").read_text())
        assert set(request["review_input"]) == {"target_identity", "artifacts"}
        assert "task_review_context" not in json.dumps(request)
    else:
        with patch.object(reviewer_workspace, "_run_sandboxed_process",
                          return_value=subprocess.CompletedProcess(["reviewer"], 0, json.dumps(judgment), "")):
            receipt = reviewer_workspace.run_sandboxed_reviewer(Path(str(created["workspace_path"])), ["reviewer"])

    assert receipt["status"] == "passed"
    assert receipt["task_review_context"]["target_identity"] == identity
    assert set(receipt["reviewer_run"]) == {"run_id", "sha256"}
    assert receipt["review_result"]["reviewer"]["agent_id"] == (
        receipt["host_run_id"] if transport == "native" else "reviewer-task")
    assert receipt["review_result"]["verdict"] == "repair"
    finding = receipt["review_result"]["findings"][0]
    assert finding["finding_id"] == "finding-product-value"
    assert finding["evidence"][0]["locator"] == "src/target.py:target"
    assert "The returned value violates the requirement." in finding["evidence"][0]["observation"]
    reference = review_runtime.publish_review(
        control, receipt["review_result"] | {"reviewer_run": receipt["reviewer_run"]},
        current_target_identity=identity,
    )
    stored, validated = review_runtime.load_stored_review(
        control, reference, current_target_identity=identity
    )
    assert stored["findings"] == receipt["review_result"]["findings"]
    assert validated.findings[0].finding_id == "finding-product-value"

    empty_repair = {"task_review": {
        "reviewed_head": head,
        "verdict": "repair",
        "findings": [],
    }}
    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_TASK_OUTPUT_INVALID"):
        reviewer_workspace._task_product_judgment_review(
            empty_repair,
            review_id="review-empty-repair",
            context=context,
            packet=direct,
            started_at="2026-09-09T00:00:00Z",
            completed_at="2026-09-09T00:01:00Z",
        )


def test_compact_task_judgment_composes_repair_and_reset_predecessors() -> None:
    runtime = reviewer_workspace
    old_identity = {"artifact_id": "task-006", "revision": "a" * 40, "sha256": "1" * 64, "source_tree": "b" * 40}
    base_context = {
        "target_identity": old_identity, "agent_id": "reviewer-task", "capability": "judgment",
        "execution_id": "review-execution-task", "evidence_mode": "direct_source",
        "review_mode": "initial", "review_target_kind": "task", "repair_frontier": None,
        "review_reset": None,
    }
    blocking = {"task_review": {"reviewed_head": old_identity["revision"], "verdict": "repair", "findings": [{
        "finding_id": "finding-product", "severity": "blocking", "requirement_id": "REQ-1",
        "boundary": "src/product.py:run", "evidence": "return value differs", "expected": "one",
        "observed": "zero", "owner": "task_owner",
    }]}}
    previous = runtime._task_product_judgment_review(
        blocking, review_id="review-prior", context=base_context, packet={"artifacts": []},
        started_at="2026-09-08T00:00:00Z", completed_at="2026-09-08T00:01:00Z",
    )
    new_identity = {"artifact_id": "task-006", "revision": "c" * 40, "sha256": "2" * 64, "source_tree": "d" * 40}
    repair_context = {**base_context, "target_identity": new_identity, "review_mode": "repair", "repair_frontier": {
        "prior_review_id": "review-prior", "blocking_finding_ids": ["finding-product"],
        "previous_reviewed_identity": old_identity, "repaired_identity": new_identity,
        "affected_boundaries": ["src/product.py:run"],
        "frozen_evidence_reference": reviewer_workspace._review_runtime().review_evidence_identity(previous),
    }}
    repaired = runtime._task_product_judgment_review(
        {"task_review": {"reviewed_head": new_identity["revision"], "verdict": "accept", "findings": []}},
        review_id="review-repaired", context=repair_context, packet={"artifacts": []},
        started_at="2026-09-08T00:02:00Z", completed_at="2026-09-08T00:03:00Z",
        previous_review=previous,
    )
    assert reviewer_workspace._review_runtime().validate_task_acceptance_review(repaired).verdict == "accepted"

    reset_context = {
        **base_context, "target_identity": new_identity,
        "review_reset": {"prior_review_id": "review-prior", "reason_class": "scope", "reason": "Accepted scope changed."},
    }
    reset = runtime._task_product_judgment_review(
        {"task_review": {"reviewed_head": new_identity["revision"], "verdict": "accept", "findings": []}},
        review_id="review-reset", context=reset_context, packet={"artifacts": []},
        started_at="2026-09-08T00:02:00Z", completed_at="2026-09-08T00:03:00Z",
        previous_review=previous,
    )
    assert reviewer_workspace._review_runtime().validate_task_acceptance_review(reset).verdict == "accepted"


def test_compact_integrated_product_judgment_gets_controller_owned_stage_envelope() -> None:
    identity = {"artifact_id": "plan-006", "revision": "6", "sha256": "1" * 64, "source_tree": "b" * 40}
    context = {
        "stage": "integrated_implementation", "target_identity": identity,
        "target_locator": "control:.work-bundle/orchestration/plan/active/plan.md",
        "agent_id": "reviewer-integrated", "capability": "judgment",
        "execution_id": "review-execution-integrated", "evidence_mode": "direct_source",
    }
    review = reviewer_workspace._task_product_judgment_review(
        {"task_review": {"reviewed_head": identity["source_tree"], "verdict": "accept", "findings": []}},
        review_id="review-integrated", context=context, packet={"artifacts": []},
        started_at="2026-09-08T00:00:00Z", completed_at="2026-09-08T00:01:00Z",
        integrated_stage=True,
    )
    validated = reviewer_workspace._review_runtime().validate_stage_review(review)
    assert validated.stage == "integrated_implementation"
    assert validated.verdict == "accepted"


def test_native_compact_integrated_repair_keeps_exact_predecessor_controller_only(
    review_roots: tuple[Path, Path, Path],
) -> None:
    source, control, _ = review_roots
    runtime = reviewer_workspace._review_runtime()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(source), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    tree = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    specification = control / ".work-bundle" / "orchestration" / "spec" / "verified" / "spec.md"
    specification.parent.mkdir(parents=True)
    specification.write_text(
        "---\nid: spec-repair\nstatus: verified\n---\n# Specification\n",
        encoding="utf-8",
    )
    target = control / ".work-bundle" / "orchestration" / "plan" / "active" / "plan.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "---\nid: plan-repair\nstatus: active\nsource_spec: [spec-repair]\n---\n# Plan\n",
        encoding="utf-8",
    )
    current_identity = runtime.stage_target_identity(
        control, "integrated_implementation", target, source_root=source
    )
    previous_identity = {**current_identity, "source_tree": "a" * 40}
    previous_context = {
        "stage": "integrated_implementation",
        "target_identity": previous_identity,
        "target_locator": "control:.work-bundle/orchestration/plan/active/plan.md",
        "agent_id": "reviewer-previous",
        "capability": "judgment",
        "execution_id": "reviewer-previous-run",
        "evidence_mode": "reproducible_snapshot",
        "review_mode": "initial",
        "review_target_kind": "stage",
        "repair_frontier": None,
        "review_reset": None,
    }
    previous = reviewer_workspace._task_product_judgment_review(
        {"task_review": {
            "reviewed_head": previous_identity["source_tree"],
            "verdict": "repair",
            "findings": [{
                "finding_id": "finding-live-oracle",
                "severity": "blocking",
                "requirement_id": "AC-009",
                "boundary": "tests/test_native_review_integration.py",
                "evidence": "validation invocation is not observed",
                "expected": "one harness-owned validation",
                "observed": "zero harness-owned validations",
                "owner": "task_owner",
            }],
        }},
        review_id="review-integrated-previous",
        context=previous_context,
        packet={"artifacts": []},
        started_at="2026-09-09T00:00:00Z",
        completed_at="2026-09-09T00:01:00Z",
        integrated_stage=True,
    )
    frontier = {
        "prior_review_id": previous["review_id"],
        "blocking_finding_ids": ["finding-live-oracle"],
        "previous_reviewed_identity": previous_identity,
        "repaired_identity": current_identity,
        "affected_boundaries": ["tests/test_native_review_integration.py"],
        "frozen_evidence_reference": runtime.review_evidence_identity(previous),
    }
    context = {
        **previous_context,
        "target_identity": current_identity,
        "agent_id": "reviewer-current",
        "execution_id": "reviewer-current-run",
        "review_mode": "repair",
        "repair_frontier": frontier,
        "previous_review": previous,
    }
    packet = build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[control / "credentials"],
        artifacts=["control:.work-bundle/orchestration/plan/active/plan.md"],
        search_roots=[], validators=[], sentinels=[], network_state="denied",
        stage_review_context=context,
    )
    created = create_reviewer_workspace(
        runtime.reviewer_runtime_root(control), "review-integrated-repair", packet
    )
    judgment = {"task_review": {
        "reviewed_head": current_identity["source_tree"],
        "verdict": "accept",
        "findings": [],
    }}
    with patch.object(
        reviewer_workspace,
        "_run_native_process",
        return_value=subprocess.CompletedProcess([], 0, native_events(judgment), ""),
    ):
        receipt = reviewer_workspace.run_native_reviewer(
            Path(str(created["workspace_path"])), Path(sys.executable),
            model="test-model", review_instructions="Review only the repaired product frontier.",
        )
    request = json.loads(Path(receipt["receipt_path"]).with_suffix(".request.json").read_text())
    assert "previous_review" not in request["review_input"]
    assert request["review_input"]["repair_frontier"] == frontier
    review = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
    assert review["previous_review"] == previous
    assert review["repair_frontier"] == frontier
    history = control / ".work-bundle" / "orchestration" / "reviews"
    history.mkdir(parents=True, exist_ok=True)
    (history / f"{previous['review_id']}.json").write_text(
        json.dumps(previous), encoding="utf-8"
    )
    reference = runtime.publish_review(control, review, current_target_identity=current_identity)
    stored, _ = runtime.load_stored_review(
        control, reference, current_target_identity=current_identity
    )
    assert stored["previous_review"] == previous
    runtime._require_current_review(control, "integrated_implementation", current_identity)

    (source / "src" / "target.py").write_text(
        "def target():\n    return 2\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(source), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "accepted reset",
        ],
        check=True,
    )
    reset_identity = runtime.stage_target_identity(
        control, "integrated_implementation", target, source_root=source
    )
    reset_context = {
        **previous_context,
        "target_identity": reset_identity,
        "agent_id": "reviewer-reset",
        "execution_id": "reviewer-reset-run",
        "review_mode": "initial",
        "repair_frontier": None,
        "review_reset": {
            "prior_review_id": review["review_id"],
            "reason_class": "acceptance",
            "reason": "Accepted source identity changed.",
        },
        "previous_review": runtime._bounded_stage_predecessor(review),
    }
    nested_context = {**reset_context, "previous_review": review}
    with pytest.raises(ReviewerWorkspaceError, match="STAGE_CONTEXT_INVALID"):
        build_direct_evidence_packet(
            source_root=source,
            control_root=control,
            protected_roots=[control / "credentials"],
            artifacts=["control:.work-bundle/orchestration/plan/active/plan.md"],
            search_roots=[], validators=[], sentinels=[], network_state="denied",
            stage_review_context=nested_context,
        )
    required, missing = runtime.stage_evidence_requirements(
        control, "integrated_implementation", target
    )
    assert missing == []
    required.update({
        item["locator"]: "source_tree"
        for item in runtime.source_snapshot_entries(source)
    })
    reset_packet = build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[control / "credentials"],
        artifacts=list(required),
        search_roots=[], validators=[], sentinels=[], network_state="denied",
        stage_review_context=reset_context,
    )
    reset_created = create_reviewer_workspace(
        runtime.reviewer_runtime_root(control), "review-integrated-reset", reset_packet
    )
    reset_judgment = {"task_review": {
        "reviewed_head": reset_identity["source_tree"],
        "verdict": "accept",
        "findings": [],
    }}
    with patch.object(
        reviewer_workspace,
        "_run_native_process",
        return_value=subprocess.CompletedProcess([], 0, native_events(reset_judgment), ""),
    ):
        reset_receipt = reviewer_workspace.run_native_reviewer(
            Path(str(reset_created["workspace_path"])), Path(sys.executable),
            model="test-model", review_instructions="Review the current accepted product evidence.",
        )
    reset_request = json.loads(
        Path(reset_receipt["receipt_path"]).with_suffix(".request.json").read_text()
    )
    assert "previous_review" not in reset_request["review_input"]
    reset_review = {
        **reset_receipt["review_result"],
        "reviewer_run": reset_receipt["reviewer_run"],
    }
    assert reset_review["previous_review"] == runtime._bounded_stage_predecessor(review)
    reset_reference = runtime.publish_review(
        control, reset_review, current_target_identity=reset_identity
    )
    runtime.load_stored_review(
        control, reset_reference, current_target_identity=reset_identity
    )
    runtime._require_current_review(
        control, "integrated_implementation", reset_identity
    )

    chain = {
        previous["review_id"]: previous,
        review["review_id"]: review,
        reset_review["review_id"]: reset_review,
    }
    forged = json.loads(json.dumps(reset_review))
    forged["previous_review"]["reviewer"]["agent_id"] = "forged-reviewer"
    with pytest.raises(
        runtime.ReviewContractError, match="projection does not match"
    ):
        runtime._validate_stored_stage_chain(forged, chain)
    with pytest.raises(runtime.ReviewContractError, match="predecessor is missing"):
        runtime._validate_stored_stage_chain(
            reset_review, {previous["review_id"]: previous}
        )
    cyclic = json.loads(json.dumps(reset_review))
    cyclic["review_reset"]["prior_review_id"] = cyclic["review_id"]
    cyclic["previous_review"] = runtime._bounded_stage_predecessor(cyclic)
    with pytest.raises(runtime.ReviewContractError, match="contains a cycle"):
        runtime._validate_stored_stage_chain(
            cyclic, {cyclic["review_id"]: cyclic}
        )

    malformed = {
        **reset_review,
        "review_id": "review-integrated-extra-history",
        "previous_review": {**review, "previous_review": previous},
    }
    (history / "review-integrated-extra-history.json").write_text(
        json.dumps(malformed), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="exactly one previous_review"):
        runtime._require_current_review(control, "integrated_implementation", reset_identity)


def test_incomplete_stage_snapshot_fails_before_reviewer_process_launch(
    review_roots: tuple[Path, Path, Path]
) -> None:
    source, control, runtime = review_roots
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "src/target.py", ".wor105-review-sentinel"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
        check=True,
    )
    plan = control / ".work-bundle/orchestration/plan/active/plan.md"
    plan.parent.mkdir(parents=True)
    spec = control / ".work-bundle/orchestration/spec/active/spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("---\nid: spec-preflight\nstatus: verified\n---\nSpec\n", encoding="utf-8")
    plan.write_text("---\nid: plan-preflight\nstatus: Planned\nsource_spec: [spec-preflight]\n---\nPlan\n", encoding="utf-8")
    task = plan.parent / "task.md"
    task.write_text(
        "---\nid: task-preflight\nplan_id: plan-preflight\nvalidation: [{id: VAL-1, command: true}]\n---\nTask\n",
        encoding="utf-8",
    )
    locator = "control:" + plan.relative_to(control).as_posix()
    context = {
        "stage": "integrated_implementation",
        "target_identity": reviewer_workspace._review_runtime().stage_target_identity(
            control, "integrated_implementation", plan, source_root=source
        ),
        "target_locator": locator,
        "agent_id": "reviewer-preflight",
        "capability": "judgment",
        "execution_id": "reviewer-preflight-run",
        "evidence_mode": "direct_source",
    }
    incomplete = build_direct_evidence_packet(
        source_root=source, control_root=control,
        protected_roots=[control / "credentials"], artifacts=[locator], search_roots=[],
        validators=[], sentinels=[], network_state="denied", stage_review_context=context,
    )
    assert incomplete["stage_evidence_manifest"]["missing"]
    created = create_reviewer_workspace(runtime, "review-preflight", incomplete)
    with patch.object(reviewer_workspace, "_run_sandboxed_process") as launch:
        with pytest.raises(ReviewerWorkspaceError, match="STAGE_EVIDENCE_INCOMPLETE"):
            reviewer_workspace.run_sandboxed_reviewer(
                Path(str(created["workspace_path"])), ["reviewer"]
            )
    launch.assert_not_called()


def test_stage_evidence_survives_plan_lifecycle_markers_but_not_product_changes(
    review_roots: tuple[Path, Path, Path]
) -> None:
    source, control, _runtime = review_roots
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(source), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    plan = control / ".work-bundle/orchestration/plan/active/plan-lifecycle.md"
    task = control / ".work-bundle/orchestration/plan/active/plan-lifecycle/task-001.md"
    spec = control / ".work-bundle/orchestration/spec/active/spec-lifecycle.md"
    task.parent.mkdir(parents=True)
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "---\nid: spec-lifecycle\nstatus: verified\n---\n\n# Specification\n",
        encoding="utf-8",
    )
    plan.write_text(
        "---\nid: plan-lifecycle\nstatus: In progress\n"
        "accepted_results: [result-task-001]\n"
        "source_spec: [.work-bundle/orchestration/spec/active/spec-lifecycle.md]\n"
        "---\n\n# Plan\n\n"
        "## Knowledge Base Update Carry Forward\n\n"
        "- Disposition: required\n- Closure return: missing\n"
        "- Source: accepted specification\n- Review Gate: resolve before archive\n",
        encoding="utf-8",
    )
    task.write_text(
        "---\nid: task-001\nplan_id: plan-lifecycle\nphase_id: phase-001\n"
        "status: In progress\n---\n\n# Task\n",
        encoding="utf-8",
    )
    runtime = reviewer_workspace._review_runtime()
    metadata = control / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        "metadata_version: 4\n"
        "workspace: {id: workspace-review, slug: review, mode: single-repository}\n"
        "orchestration_control:\n"
        "  schema_version: 1\n"
        "  post_execution_review_round_limit: 5\n",
        encoding="utf-8",
    )
    identity = runtime.stage_target_identity(
        control, "integrated_implementation", plan, source_root=source
    )
    locator = "control:" + plan.relative_to(control).as_posix()
    context = {
        "stage": "integrated_implementation",
        "target_identity": identity,
        "target_locator": locator,
        "agent_id": "reviewer-lifecycle",
        "capability": "judgment",
        "execution_id": "reviewer-lifecycle-run",
        "evidence_mode": "direct_source",
    }
    required, missing = runtime.stage_evidence_requirements(
        control, "integrated_implementation", plan
    )
    assert missing == []
    required.update(
        {item["locator"]: "source_tree" for item in runtime.source_snapshot_entries(source)}
    )
    def legacy_stage_identity(path: Path, **kwargs: object) -> dict[str, object]:
        return runtime.artifact_review_identity(path, content=kwargs.get("content"))

    with patch.object(runtime, "_stage_authority_identity", side_effect=legacy_stage_identity):
        packet = build_direct_evidence_packet(
            source_root=source,
            control_root=control,
            protected_roots=[control / "credentials"],
            artifacts=list(required),
            search_roots=[],
            validators=[],
            sentinels=[],
            network_state="denied",
            stage_review_context=context,
        )
        with pytest.raises(
            ReviewerWorkspaceError, match="WB_POST_EXECUTION_ROUND_REQUIRED"
        ):
            create_reviewer_workspace(
                runtime.reviewer_runtime_root(control), "review-lifecycle", packet
            )
        reserved = bounded_closure.begin_review_round(
            control,
            flow_id="plan-lifecycle",
            request_id="integrated-review-request-1",
            review_id="review-lifecycle",
            target_identity=identity,
            executor_attempts=[
                {"execution_id": "task-001-attempt-1", "state": "completed"}
            ],
            known_missing_evidence=[],
        )
        created = create_reviewer_workspace(
            runtime.reviewer_runtime_root(control), "review-lifecycle", packet
        )
        assert bounded_closure.review_round_status(
            control, flow_id="plan-lifecycle"
        )["latest_round"]["state"] == "prepared"
        judgment = {
            "task_review": {
                "reviewed_head": identity["source_tree"],
                "verdict": "accept",
                "findings": [],
            }
        }
        with patch.object(
            reviewer_workspace,
            "_run_native_process",
            return_value=subprocess.CompletedProcess([], 0, native_events(judgment), ""),
        ):
            receipt = reviewer_workspace.run_native_reviewer(
                Path(str(created["workspace_path"])),
                Path(sys.executable),
                model="test-model",
                review_instructions="Review the frozen product evidence.",
            )
        with pytest.raises(
            ReviewerWorkspaceError, match="WB_POST_EXECUTION_JUDGMENT_ALREADY_RECORDED"
        ):
            reviewer_workspace.run_native_reviewer(
                Path(str(created["workspace_path"])),
                Path(sys.executable),
                model="test-model",
                review_instructions="Review the frozen product evidence again.",
            )
        review = {**receipt["review_result"], "reviewer_run": receipt["reviewer_run"]}
        reference = runtime.publish_review(control, review, current_target_identity=identity)
        assert runtime.publish_review(
            control, review, current_target_identity=identity
        ) == reference
        completed_round = bounded_closure.review_round_status(
            control, flow_id="plan-lifecycle"
        )["latest_round"]
        assert completed_round["round_id"] == reserved["round_id"]
        assert completed_round["state"] == "completed"
        assert completed_round["outcome"] == "accepted"

    request = json.loads(
        Path(receipt["receipt_path"]).with_suffix(".request.json").read_text()
    )
    assert locator in {item["locator"] for item in request["evidence"]}
    controller_path = Path(receipt["receipt_path"]).with_suffix(".controller.json")
    controller_evidence = json.loads(controller_path.read_text())
    assert locator not in {item["locator"] for item in controller_evidence}

    plan.write_text(
        plan.read_text(encoding="utf-8")
        .replace("status: In progress", "status: Completed")
        .replace("Closure return: missing", "Closure return: completed"),
        encoding="utf-8",
    )
    task.write_text(
        task.read_text(encoding="utf-8").replace("status: In progress", "status: Completed"),
        encoding="utf-8",
    )
    assert runtime.stage_target_identity(
        control, "integrated_implementation", plan, source_root=source
    ) == identity
    runtime._require_current_review(control, "integrated_implementation", identity)

    plan.write_text(
        plan.read_text(encoding="utf-8").replace(
            "Review Gate: resolve before archive", "Review Gate: bypass product review"
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="authority identity changed"):
        runtime._require_current_review(control, "integrated_implementation", identity)


def test_bounded_read_search_and_validators_are_allowed(review_roots: tuple[Path, Path, Path]) -> None:
    source, control, runtime = review_roots
    created = create_reviewer_workspace(runtime, "review-002", packet(source, control))
    workspace = Path(str(created["workspace_path"]))

    read = execute_reviewer_request(workspace, {"operation": "read", "artifact": "source:src/target.py"})
    search = execute_reviewer_request(workspace, {"operation": "search", "pattern": "return 1"})
    valid = execute_reviewer_request(workspace, {"operation": "validate", "validator_id": "target-json"})
    digest = execute_reviewer_request(workspace, {"operation": "validate", "validator_id": "source-digest"})

    assert read["status"] == "allowed" and "def target" in str(read["content"])
    assert search["status"] == "allowed" and search["matches"] == ["source:src/target.py:2:return 1"]
    assert valid == {"status": "allowed", "validator_id": "target-json", "result": "passed"}
    assert digest["result"] == sha256(source / "src" / "target.py")


@pytest.mark.parametrize(
    ("operation_request", "code"),
    [
        ({"operation": "write", "artifact": "source:.wor105-review-sentinel", "content": "changed"}, "WB_REVIEW_SOURCE_WRITE_DENIED"),
        ({"operation": "write", "artifact": "control:orchestration/docs/wor105/.review-sentinel", "content": "changed"}, "WB_REVIEW_CONTROL_WRITE_DENIED"),
        ({"operation": "read", "artifact": "control:credentials/credentials.yaml"}, "WB_REVIEW_PROTECTED_READ_DENIED"),
        ({"operation": "read", "artifact": "host:~/.gitconfig"}, "WB_REVIEW_HOST_CONFIG_READ_DENIED"),
        ({"operation": "network", "target": "https://example.invalid"}, "WB_REVIEW_NETWORK_DENIED"),
    ],
)
def test_reviewer_operations_mechanically_deny_forbidden_effects(
    review_roots: tuple[Path, Path, Path], operation_request: dict[str, str], code: str
) -> None:
    source, control, runtime = review_roots
    source_before = sha256(source / ".wor105-review-sentinel")
    control_before = sha256(control / "orchestration" / "docs" / "wor105" / ".review-sentinel")
    created = create_reviewer_workspace(runtime, "review-003", packet(source, control))

    with pytest.raises(ReviewerWorkspaceError, match=code) as exc:
        execute_reviewer_request(Path(str(created["workspace_path"])), operation_request)

    assert exc.value.result["classification"] == "denied"
    assert sha256(source / ".wor105-review-sentinel") == source_before
    assert sha256(control / "orchestration" / "docs" / "wor105" / ".review-sentinel") == control_before


def test_write_scope_denies_origin_tokens_and_cleanup_requires_owned_terminal_state(
    review_roots: tuple[Path, Path, Path]
) -> None:
    source, control, runtime = review_roots
    created = create_reviewer_workspace(runtime, "review-004", packet(source, control))
    workspace = Path(str(created["workspace_path"]))
    state_path = Path(str(created["state_path"]))

    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_SOURCE_WRITE_DENIED"):
        enforce_reviewer_write_scope("source:src/target.py")
    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_TERMINAL_RECORD_INVALID"):
        cleanup_reviewer_workspace(runtime, "review-004", terminal_evidence="")

    terminal = {
        "schema": "reviewer-terminal-review-v1",
        "review_id": "review-004",
        "packet_sha256": created["packet_sha256"],
        "verdict": "accepted",
        "evidence_digest": created["evidence_digest"],
        "sentinel_digest": created["sentinel_digest"],
    }
    cleaned = cleanup_reviewer_workspace(
        runtime,
        "review-004",
        terminal_review=terminal,
        source_root=source,
        control_root=control,
        protected_roots=[control / "credentials"],
    )

    assert cleaned["status"] == "cleaned"
    assert cleaned["terminal_review_sha256"]
    assert not workspace.exists()
    assert not state_path.exists()
    assert source.exists() and control.exists()


def test_dispatcher_exposes_reviewer_workspace_commands() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "wb.py"), "reviewer-workspace-create", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--packet" in result.stdout
    dispatcher = (REPO_ROOT / "scripts" / "work-bundle" / "dispatcher.py").read_text(encoding="utf-8")
    assert "reviewer-workspace-operation" in dispatcher
    assert "reviewer-workspace-cleanup" in dispatcher


def test_exact_protected_roots_block_nonheuristic_private_path(review_roots: tuple[Path, Path, Path]) -> None:
    source, control, _ = review_roots
    protected = control / "opaque-store"
    protected.mkdir()
    (protected / "material.txt").write_text("private\n", encoding="utf-8")

    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_PROTECTED_READ_DENIED"):
        build_direct_evidence_packet(
            source_root=source,
            control_root=control,
            protected_roots=[protected],
            artifacts=["control:opaque-store/material.txt"],
            search_roots=[],
            validators=[],
            sentinels=[],
            network_state="denied",
        )


@pytest.mark.skipif(platform.system() != "Darwin", reason="sandbox-exec is the accepted macOS process boundary")
def test_sandboxed_process_denies_origin_write_protected_read_and_network(
    review_roots: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    source, control, runtime = review_roots
    registry = tmp_path / "opaque-live-registry"
    registry.mkdir()
    protected_file = registry / "store.data"
    protected_file.write_text("private registry\n", encoding="utf-8")
    source_sentinel = source / ".wor105-review-sentinel"
    source_before = sha256(source_sentinel)
    direct_packet = build_direct_evidence_packet(
        source_root=source,
        control_root=control,
        protected_roots=[registry, control / "credentials"],
        artifacts=["source:src/target.py"],
        search_roots=["source:src"],
        validators=[
            {
                "validator_id": "write-probe",
                "kind": "command",
                "argv": [sys.executable, "-c", f"open({str(source_sentinel)!r}, 'w').write('changed')"],
            },
            {
                "validator_id": "read-probe",
                "kind": "command",
                "argv": [sys.executable, "-c", f"open({str(protected_file)!r}).read()"],
            },
            {
                "validator_id": "network-probe",
                "kind": "command",
                "argv": [sys.executable, "-c", "import socket; socket.socket().connect(('127.0.0.1', 9))"],
            },
            {
                "validator_id": "bounded-read",
                "kind": "command",
                "argv": ["/bin/cat", "evidence/source/src/target.py"],
            },
            {
                "validator_id": "bounded-search",
                "kind": "command",
                "argv": ["/usr/bin/grep", "return 1", "evidence/source/src/target.py"],
            },
        ],
        sentinels=["source:.wor105-review-sentinel", "control:orchestration/docs/wor105/.review-sentinel"],
        network_state="denied",
    )
    created = create_reviewer_workspace(
        runtime,
        "review-sandbox",
        direct_packet,
        source_root=source,
        control_root=control,
        protected_roots=[registry, control / "credentials"],
    )
    workspace = Path(str(created["workspace_path"]))

    for validator_id in ("write-probe", "read-probe", "network-probe"):
        with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_SANDBOX_DENIED"):
            execute_reviewer_request(workspace, {"operation": "validate", "validator_id": validator_id})

    assert execute_reviewer_request(
        workspace, {"operation": "validate", "validator_id": "bounded-read"}
    )["result"] == "passed"
    assert execute_reviewer_request(
        workspace, {"operation": "validate", "validator_id": "bounded-search"}
    )["result"] == "passed"
    assert sha256(source_sentinel) == source_before


def test_every_denied_request_appends_unique_privacy_safe_event(review_roots: tuple[Path, Path, Path]) -> None:
    source, control, runtime = review_roots
    created = create_reviewer_workspace(runtime, "review-events", packet(source, control))
    workspace = Path(str(created["workspace_path"]))

    for operation in ({"operation": "network", "target": "secret-target"}, {"operation": "write", "artifact": "source:x"}):
        with pytest.raises(ReviewerWorkspaceError):
            execute_reviewer_request(workspace, operation)

    events_path = runtime / "events" / "review-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 2
    assert len({event["event_id"] for event in events}) == 2
    assert all(event["privacy"] == "operational_metadata_only" for event in events)
    serialized = json.dumps(events)
    assert "secret-target" not in serialized
    assert "source:x" not in serialized


def test_sandbox_denial_requires_a_failed_process() -> None:
    incidental = subprocess.CompletedProcess(
        ["reviewer"], 0, stdout="", stderr="sandbox violation: harmless probe denied"
    )
    denied = subprocess.CompletedProcess(
        ["reviewer"], 1, stdout="", stderr="sandbox violation: operation not permitted"
    )
    ordinary_failure = subprocess.CompletedProcess(
        ["reviewer"], 1, stdout="", stderr="reviewer assertion failed"
    )

    assert reviewer_workspace._sandbox_denied(incidental) is False
    assert reviewer_workspace._sandbox_denied(denied) is True
    assert reviewer_workspace._sandbox_denied(ordinary_failure) is False


def test_sandbox_profile_allows_split_environment_and_base_runtime_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment_prefix = tmp_path / "uv-environment"
    base_prefix = tmp_path / "python-framework"
    executable = environment_prefix / "bin" / "python"
    policy = {
        "source": str(tmp_path / "source"),
        "control": str(tmp_path / "control"),
        "protected": [str(tmp_path / "control" / "credentials")],
    }
    monkeypatch.setattr(reviewer_workspace.sys, "prefix", str(environment_prefix))
    monkeypatch.setattr(reviewer_workspace.sys, "exec_prefix", str(environment_prefix / "exec"))
    monkeypatch.setattr(reviewer_workspace.sys, "base_prefix", str(base_prefix))
    monkeypatch.setattr(reviewer_workspace.sys, "base_exec_prefix", str(base_prefix / "exec"))
    monkeypatch.setattr(reviewer_workspace.sys, "executable", str(executable))

    profile = reviewer_workspace._sandbox_profile(tmp_path / "review", policy, [])

    for root in (environment_prefix, environment_prefix / "exec", base_prefix, base_prefix / "exec"):
        assert f'(subpath "{root}")' in profile


def test_cleanup_rejects_arbitrary_terminal_text(review_roots: tuple[Path, Path, Path]) -> None:
    source, control, runtime = review_roots
    create_reviewer_workspace(runtime, "review-terminal", packet(source, control))

    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_TERMINAL_RECORD_INVALID"):
        cleanup_reviewer_workspace(runtime, "review-terminal", terminal_evidence="accepted")


@pytest.mark.parametrize("mutate", ["evidence", "sentinel"])
def test_cleanup_rejects_changed_evidence_or_origin_sentinel(
    review_roots: tuple[Path, Path, Path], mutate: str
) -> None:
    source, control, runtime = review_roots
    review_id = f"review-changed-{mutate}"
    created = create_reviewer_workspace(runtime, review_id, packet(source, control))
    workspace = Path(str(created["workspace_path"]))
    terminal = {
        "schema": "reviewer-terminal-review-v1",
        "review_id": review_id,
        "packet_sha256": created["packet_sha256"],
        "verdict": "accepted",
        "evidence_digest": created["evidence_digest"],
        "sentinel_digest": created["sentinel_digest"],
    }
    if mutate == "evidence":
        target = workspace / "evidence" / "source" / "src" / "target.py"
        target.chmod(0o644)
        target.write_text("changed\n", encoding="utf-8")
    else:
        (source / ".wor105-review-sentinel").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_TERMINAL_EVIDENCE_CHANGED"):
        cleanup_reviewer_workspace(
            runtime,
            review_id,
            terminal_review=terminal,
            source_root=source,
            control_root=control,
            protected_roots=[control / "credentials"],
        )


@pytest.mark.skipif(platform.system() != "Darwin", reason="sandbox-exec is the accepted macOS process boundary")
def test_entire_reviewer_process_is_deny_default_and_receipted(
    review_roots: tuple[Path, Path, Path]
) -> None:
    source, control, runtime = review_roots
    created = create_reviewer_workspace(runtime, "review-process", packet(source, control))
    workspace = Path(str(created["workspace_path"]))
    source_target = source / "src" / "target.py"

    denied = reviewer_workspace.run_sandboxed_reviewer(
        workspace,
        [DARWIN_SANDBOX_SHELL, "-c", 'IFS= read -r line < "$1"', "reviewer", str(source_target)],
    )
    allowed = reviewer_workspace.run_sandboxed_reviewer(
        workspace,
        [
            DARWIN_SANDBOX_SHELL,
            "-c",
            "{ IFS= read -r first; IFS= read -r second; } < evidence/source/src/target.py; "
            "[ \"$second\" = '    return 1' ] && printf passed > scratch/result",
        ],
    )

    assert denied["status"] == "denied"
    assert allowed["status"] == "passed"
    receipt = json.loads(Path(str(allowed["receipt_path"])).read_text(encoding="utf-8"))
    assert receipt["packet_sha256"] == created["packet_sha256"]
    assert receipt["sandbox_profile_sha256"]
    assert receipt["argv_sha256"]


@pytest.mark.skipif(platform.system() != "Darwin", reason="sandbox-exec is the accepted macOS process boundary")
def test_deny_default_blocks_omitted_host_root_and_event_truncation(
    review_roots: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    source, control, runtime = review_roots
    omitted_host_root = tmp_path / "host-config-not-listed"
    omitted_host_root.mkdir()
    omitted_file = omitted_host_root / "opaque"
    omitted_file.write_text("host private\n", encoding="utf-8")
    created = create_reviewer_workspace(runtime, "review-sealed-events", packet(source, control))
    workspace = Path(str(created["workspace_path"]))

    first = reviewer_workspace.run_sandboxed_reviewer(
        workspace,
        [DARWIN_SANDBOX_SHELL, "-c", 'IFS= read -r line < "$1"', "reviewer", str(omitted_file)],
    )
    event_path = runtime / "events" / "review-sealed-events.jsonl"
    before = event_path.read_bytes()
    second = reviewer_workspace.run_sandboxed_reviewer(
        workspace,
        [DARWIN_SANDBOX_SHELL, "-c", 'printf truncated > "$1"', "reviewer", str(event_path)],
    )

    assert first["status"] == second["status"] == "denied"
    assert event_path.read_bytes().startswith(before)
    assert event_path.stat().st_mode & 0o777 == 0o400
    assert second["event_log_sha256"] == sha256(event_path)
    assert b"truncated" not in event_path.read_bytes()


def test_cleanup_rejects_substitute_roots_with_identical_sentinels(
    review_roots: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    source, control, runtime = review_roots
    created = create_reviewer_workspace(runtime, "review-root-identity", packet(source, control))
    substitute = tmp_path / "substitute-source"
    (substitute / "src").mkdir(parents=True)
    (substitute / "src" / "target.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    (substitute / ".wor105-review-sentinel").write_text("immutable-source-sentinel-v1\n", encoding="utf-8")
    terminal = {
        "schema": "reviewer-terminal-review-v1",
        "review_id": "review-root-identity",
        "packet_sha256": created["packet_sha256"],
        "verdict": "accepted",
        "evidence_digest": created["evidence_digest"],
        "sentinel_digest": created["sentinel_digest"],
    }

    with pytest.raises(ReviewerWorkspaceError, match="WB_REVIEW_ROOT_IDENTITY_MISMATCH"):
        cleanup_reviewer_workspace(
            runtime,
            "review-root-identity",
            terminal_review=terminal,
            source_root=substitute,
            control_root=control,
            protected_roots=[control / "credentials"],
        )


def test_dispatcher_exposes_whole_reviewer_process_launcher() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "wb.py"), "reviewer-process-run", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--argv-json" in result.stdout
