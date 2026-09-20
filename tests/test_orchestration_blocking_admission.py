from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/orchestration"))
import bounded_closure as bounded  # noqa: E402


def _workspace(tmp_path: Path, *, control: dict[str, object] | None) -> Path:
    wb = tmp_path / ".work-bundle"
    wb.mkdir(parents=True)
    metadata: dict[str, object] = {
        "metadata_version": 4,
        "workspace": {"id": "ws-1"},
    }
    if control is not None:
        metadata["orchestration_control"] = control
    (wb / "project.yaml").write_text(
        yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


def _control() -> dict[str, object]:
    return {
        "schema_version": 1,
        "blockers": [{
            "id": "BLOCK-1",
            "status": "active",
            "origin_plan": "old-flow",
            "specification": ".work-bundle/orchestration/spec/active/block.md",
        }],
        "implementation_exemptions": [{
            "flow_id": "allowed-flow",
            "blocker_id": "BLOCK-1",
            "status": "active",
        }],
    }


def _write_blocker_evidence(root: Path) -> Path:
    spec = root / ".work-bundle/orchestration/spec/active/block.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# unresolved\n", encoding="utf-8")
    return spec


def test_active_blocker_denies_other_flow_and_names_evidence(tmp_path: Path) -> None:
    root = _workspace(tmp_path, control=_control())
    spec = _write_blocker_evidence(root)

    with pytest.raises(bounded.BoundedClosureError) as captured:
        bounded.require_orchestration_admission(
            root, operation="ordinary_new", flow_id="other-flow"
        )

    assert captured.value.code == "WB_ORCHESTRATION_ADMISSION_BLOCKED"
    detail = captured.value.detail or ""
    assert all(value in detail for value in (
        str(root / ".work-bundle/project.yaml"),
        "BLOCK-1",
        str(spec),
        "orch-bounded-closure",
    ))
    assert bounded.require_orchestration_admission(
        root, operation="ordinary_new", flow_id="allowed-flow"
    )["status"] == "admitted"
    assert bounded.require_orchestration_admission(
        root, operation="read_only", flow_id=None
    )["status"] == "admitted"


def test_absent_control_is_allowed_but_malformed_or_missing_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    absent = _workspace(tmp_path / "absent", control=None)
    assert bounded.require_orchestration_admission(
        absent, operation="ordinary_new", flow_id="new"
    )["status"] == "admitted"

    malformed = _workspace(
        tmp_path / "malformed",
        control={"schema_version": 1, "blockers": {}},
    )
    with pytest.raises(bounded.BoundedClosureError, match="WB_POST_EXECUTION_POLICY_INVALID"):
        bounded.require_orchestration_admission(
            malformed, operation="ordinary_new", flow_id="new"
        )

    missing = _workspace(tmp_path / "missing", control=_control())
    with pytest.raises(
        bounded.BoundedClosureError,
        match="WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID",
    ):
        bounded.require_orchestration_admission(
            missing, operation="ordinary_new", flow_id="other"
        )


def test_blocker_evidence_symlink_is_rejected_before_resolution(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace", control=_control())
    real = root / ".work-bundle/orchestration/spec/active/real.md"
    real.parent.mkdir(parents=True)
    real.write_text("# unresolved\n", encoding="utf-8")
    link = real.with_name("block.md")
    try:
        link.symlink_to(real)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(
        bounded.BoundedClosureError,
        match="WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID",
    ):
        bounded.require_orchestration_admission(
            root, operation="ordinary_new", flow_id="other"
        )


def test_workspace_symlink_is_rejected_before_resolution(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace", control=None)
    alias = tmp_path / "workspace-alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(
        bounded.BoundedClosureError,
        match="WB_POST_EXECUTION_WORKSPACE_INVALID",
    ):
        bounded.require_orchestration_admission(
            alias, operation="ordinary_new", flow_id="new"
        )


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction behavior")
def test_blocker_evidence_junction_is_rejected_before_resolution(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace", control=_control())
    target = root / ".work-bundle/real-active"
    target.mkdir(parents=True)
    (target / "block.md").write_text("# unresolved\n", encoding="utf-8")
    active = root / ".work-bundle/orchestration/spec/active"
    active.parent.mkdir(parents=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(active), str(target)],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(
        bounded.BoundedClosureError,
        match="WB_ORCHESTRATION_BLOCKER_EVIDENCE_INVALID",
    ):
        bounded.require_orchestration_admission(
            root, operation="ordinary_new", flow_id="other"
        )


def test_restore_exception_merges_backup_blocker_without_erasing_newer_control(
    tmp_path: Path,
) -> None:
    original = _control()
    original.pop("implementation_exemptions")
    backup = tmp_path / "before.yaml"
    backup.write_text(
        yaml.safe_dump(
            {"metadata_version": 4, "orchestration_control": original},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    current = _control()
    current["newer_field"] = {"preserve": True}
    current["blockers"] = [{
        "id": "OTHER",
        "status": "active",
        "specification": "other.md",
    }]
    root = _workspace(tmp_path / "workspace", control=current)

    bounded.restore_implementation_exception(
        root,
        backup_path=backup,
        backup_sha256=digest,
        flow_id="allowed-flow",
        blocker_id="BLOCK-1",
    )

    restored = yaml.safe_load(
        (root / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    )["orchestration_control"]
    assert restored["newer_field"] == {"preserve": True}
    assert {item["id"] for item in restored["blockers"]} == {"OTHER", "BLOCK-1"}
    assert restored.get("implementation_exemptions", []) == []
