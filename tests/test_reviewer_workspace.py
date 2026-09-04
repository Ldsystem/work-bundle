from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
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
        [sys.executable, "-c", f"open({str(source_target)!r}).read()"],
    )
    allowed = reviewer_workspace.run_sandboxed_reviewer(
        workspace,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "assert 'return 1' in Path('evidence/source/src/target.py').read_text(); "
            "Path('scratch/result').write_text('passed')",
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
        workspace, [sys.executable, "-c", f"open({str(omitted_file)!r}).read()"]
    )
    event_path = runtime / "events" / "review-sealed-events.jsonl"
    before = event_path.read_bytes()
    second = reviewer_workspace.run_sandboxed_reviewer(
        workspace, [sys.executable, "-c", f"open({str(event_path)!r}, 'w').write('truncated')"]
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
