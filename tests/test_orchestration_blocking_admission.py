from __future__ import annotations

import hashlib
import argparse
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/orchestration"))
import bounded_closure as bounded  # noqa: E402
import plans  # noqa: E402


@pytest.mark.parametrize("writer", [plans.cmd_write_task, plans.cmd_write_phase])
@pytest.mark.parametrize("condition", ["blocker", "exhausted", "exempt", "legacy"])
@pytest.mark.parametrize("from_member", [False, True])
def test_direct_plan_writers_enforce_admission_before_mutation(
    tmp_path: Path, writer, condition: str, from_member: bool,
) -> None:
    control = None if condition == "legacy" else _control()
    if condition == "exhausted":
        control["blockers"] = []
        control["post_execution_review_flows"] = [
            {"flow_id": "allowed-flow", "finalization_required": True}
        ]
    root = _workspace(tmp_path, control=control)
    spec = root / ".work-bundle/orchestration/spec/active/block.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# unresolved\n", encoding="utf-8")
    content = root / "input.md"
    content.write_text("# Writer input\n", encoding="utf-8")
    member = root / "member"
    member.mkdir()
    args = argparse.Namespace(
        project_root=str(member if from_member else root),
        content_file=str(content), plan_id="other-flow" if condition == "blocker" else "allowed-flow",
        phase_id="phase-001", task_id="task-001", title="Direct", status="Planned",
    )

    def snapshot():
        return {
            str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
            for path in root.rglob("*")
        }

    before = snapshot()
    if condition in {"blocker", "exhausted"}:
        code = "WB_ORCHESTRATION_ADMISSION_BLOCKED" if condition == "blocker" else "WB_ORCHESTRATION_FINALIZATION_REQUIRED"
        with pytest.raises(bounded.BoundedClosureError, match=code):
            writer(args)
        assert snapshot() == before
    else:
        writer(args)
        outputs = list((root / ".work-bundle/orchestration/plan/active").rglob("*-direct.md"))
        assert len(outputs) == 1
        assert "Writer input" in outputs[0].read_text()
        assert (root / ".work-bundle/orchestration/plan/index.jsonl").is_file()


def _workspace(tmp_path: Path, *, control: dict[str, object] | None) -> Path:
    wb = tmp_path / ".work-bundle"
    wb.mkdir(parents=True)
    metadata: dict[str, object] = {"metadata_version": 4, "workspace": {"id": "ws-1"}}
    if control is not None:
        metadata["orchestration_control"] = control
    (wb / "project.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    return tmp_path


def _control() -> dict[str, object]:
    return {
        "schema_version": 1,
        "post_execution_review_round_limit": 5,
        "blockers": [{
            "id": "BLOCK-1", "status": "active", "origin_plan": "old-flow",
            "specification": ".work-bundle/orchestration/spec/active/block.md",
        }],
        "implementation_exemptions": [{
            "flow_id": "allowed-flow", "blocker_id": "BLOCK-1", "status": "active",
        }],
    }


def test_active_blocker_denies_other_flow_and_names_evidence(tmp_path: Path) -> None:
    root = _workspace(tmp_path, control=_control())
    spec = root / ".work-bundle/orchestration/spec/active/block.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# unresolved\n", encoding="utf-8")

    with pytest.raises(bounded.BoundedClosureError) as captured:
        bounded.require_orchestration_admission(root, operation="ordinary_new", flow_id="other-flow")

    assert captured.value.code == "WB_ORCHESTRATION_ADMISSION_BLOCKED"
    detail = captured.value.detail or ""
    assert all(value in detail for value in (str(root / ".work-bundle/project.yaml"), "BLOCK-1", str(spec), "orch-bounded-closure"))
    assert bounded.require_orchestration_admission(root, operation="ordinary_new", flow_id="allowed-flow")["status"] == "admitted"
    assert bounded.require_orchestration_admission(root, operation="read_only", flow_id=None)["status"] == "admitted"


def test_legacy_absence_is_allowed_but_malformed_or_missing_evidence_fails_closed(tmp_path: Path) -> None:
    legacy = _workspace(tmp_path / "legacy", control=None)
    assert bounded.require_orchestration_admission(legacy, operation="ordinary_new", flow_id="new")["legacy"] is True

    malformed = _workspace(tmp_path / "malformed", control={"schema_version": 1})
    with pytest.raises(bounded.BoundedClosureError, match="WB_POST_EXECUTION_POLICY_INVALID"):
        bounded.require_orchestration_admission(malformed, operation="ordinary_new", flow_id="new")

    missing = _workspace(tmp_path / "missing", control=_control())
    with pytest.raises(bounded.BoundedClosureError, match="WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID"):
        bounded.require_orchestration_admission(missing, operation="ordinary_new", flow_id="other")


def test_exhausted_flow_denies_reconciliation_before_blocker_exists(tmp_path: Path) -> None:
    control = _control()
    control["blockers"] = []
    control["implementation_exemptions"] = []
    control["post_execution_review_flows"] = [{"flow_id": "flow-1", "finalization_required": True}]
    root = _workspace(tmp_path, control=control)
    with pytest.raises(bounded.BoundedClosureError, match="WB_ORCHESTRATION_FINALIZATION_REQUIRED"):
        bounded.require_orchestration_admission(root, operation="reconciliation", flow_id="flow-1")
    assert bounded.require_orchestration_admission(root, operation="finalization", flow_id="flow-1")["status"] == "admitted"


def test_restore_exception_merges_backup_blocker_without_erasing_newer_control(tmp_path: Path) -> None:
    original = _control()
    original["review_revision_limit"] = original.pop("post_execution_review_round_limit")
    original.pop("implementation_exemptions")
    backup = tmp_path / "before.yaml"
    backup.write_text(yaml.safe_dump({"metadata_version": 4, "orchestration_control": original}, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    current = _control()
    current["newer_field"] = {"preserve": True}
    current["blockers"] = [{"id": "OTHER", "status": "active", "specification": "other.md"}]
    root = _workspace(tmp_path / "workspace", control=current)

    bounded.restore_implementation_exception(root, backup_path=backup, backup_sha256=digest,
                                             flow_id="allowed-flow", blocker_id="BLOCK-1")
    restored = yaml.safe_load((root / ".work-bundle/project.yaml").read_text(encoding="utf-8"))["orchestration_control"]
    assert restored["post_execution_review_round_limit"] == 5
    assert restored["newer_field"] == {"preserve": True}
    assert {item["id"] for item in restored["blockers"]} == {"OTHER", "BLOCK-1"}
    assert restored.get("implementation_exemptions", []) == []


def test_public_dispatcher_refuses_before_creating_spec_files(tmp_path: Path) -> None:
    control = _control()
    control["implementation_exemptions"] = []
    root = _workspace(tmp_path, control=control)
    spec = root / ".work-bundle/orchestration/spec/active/block.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# unresolved\n", encoding="utf-8")
    content = root / "input.md"
    content.write_text("# candidate\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts/orchestration/dispatcher.py"),
            "write-spec", "--project-root", str(root), "--title", "Denied",
            "--purpose", "test", "--component", "test", "--content-file", str(content),
            "--id", "spec-denied",
        ],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert all(value in result.stderr for value in ("BLOCK-1", "block.md", "orch-bounded-closure")), result.stderr
    assert not (root / ".work-bundle/orchestration/spec/active/spec-denied-denied.md").exists()


def test_controller_observation_uses_bound_plan_for_current_scoped_exception(tmp_path: Path) -> None:
    root = _workspace(tmp_path, control=_control())
    spec = root / ".work-bundle/orchestration/spec/active/block.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# unresolved\n", encoding="utf-8")
    task = root / ".work-bundle/orchestration/plan/active/plan-current/task-002.md"
    task.parent.mkdir(parents=True)
    task.write_text("---\nid: task-002\nplan_id: allowed-flow\n---\n", encoding="utf-8")
    resolver = (
        "import argparse,sys; "
        f"sys.path.insert(0, {str(REPO_ROOT / 'scripts/orchestration')!r}); "
        "from execution_context import task_flow_id; "
        f"print(task_flow_id(argparse.Namespace(project_root={str(root)!r}, task={task.relative_to(root).as_posix()!r})))"
    )
    resolved = subprocess.run(
        [sys.executable, "-c", resolver], text=True, capture_output=True, check=True
    ).stdout.strip()
    bounded.require_orchestration_admission(root, operation="reconciliation", flow_id=resolved)
    task.write_text("---\nid: task-002\nplan_id: unrelated-flow\n---\n", encoding="utf-8")
    unrelated = subprocess.run(
        [sys.executable, "-c", resolver], text=True, capture_output=True, check=True
    ).stdout.strip()
    with pytest.raises(bounded.BoundedClosureError, match="WB_ORCHESTRATION_ADMISSION_BLOCKED"):
        bounded.require_orchestration_admission(root, operation="reconciliation", flow_id=unrelated)
