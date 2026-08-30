from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WB = REPO_ROOT / "scripts" / "wb.py"
CATALOG = (REPO_ROOT / "references" / "wb-defect-evidence.yaml").read_text(encoding="utf-8")


def prepare_cwd(tmp_path: Path, catalog: str = CATALOG) -> Path:
    cwd = tmp_path / "cwd"
    (cwd / "references").mkdir(parents=True, exist_ok=True)
    (cwd / "references" / "wb-defect-evidence.yaml").write_text(catalog, encoding="utf-8")
    return cwd


def run_wb(tmp_path: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(tmp_path / "config")
    return subprocess.run(
        [sys.executable, str(WB), *args],
        cwd=cwd or prepare_cwd(tmp_path),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def create_active(tmp_path: Path, slug: str = "contract-conflict", *evidence: str) -> dict[str, object]:
    result = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "active",
        "--short-description",
        slug,
        "--deviation",
        "Planning contract asks for executor-result forbidden fields.",
        "--occurrence",
        "Observed while executing a work-bundle task.",
        "--severity",
        "p3",
        *(item for value in (evidence or ("visible runtime surface",)) for item in ("--evidence", value)),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def evidence_id(slug: str) -> str:
    return f"evidence-{datetime.now().strftime('%Y%m%d')}-{slug}"


def test_defect_ensure_store_creates_directories(tmp_path: Path) -> None:
    result = run_wb(tmp_path, "defect-ensure-store")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert Path(payload["active"]).is_dir()
    assert Path(payload["archived"]).is_dir()
    assert Path(payload["root"]) == tmp_path / "config" / "defect"
    assert not (Path.home() / ".work-bundle" / "defect" / "active" / "__pytest_marker__").exists()


def test_defect_catalog_is_cwd_independent(tmp_path: Path) -> None:
    external_cwd = tmp_path / "external-cwd"
    external_cwd.mkdir()

    result = run_wb(tmp_path, "defect-build-index", cwd=external_cwd)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "active:" in result.stdout
    assert "archived:" in result.stdout


def test_defect_create_evidence_writes_active_record_with_supplied_evidence_only(tmp_path: Path) -> None:
    cwd = prepare_cwd(tmp_path)
    supplied = cwd / "visible.txt"
    supplied.write_text("visible", encoding="utf-8")
    (cwd / "not-supplied.txt").write_text("should not be discovered", encoding="utf-8")

    result = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "active",
        "--short-description",
        "visible-only",
        "--deviation",
        "Only supplied evidence should be recorded.",
        "--occurrence",
        "A visible file was provided explicitly.",
        "--evidence",
        "visible.txt",
        "--evidence",
        "runtime output already visible",
        "--severity",
        "p2",
        cwd=cwd,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    text = Path(payload["path"]).read_text(encoding="utf-8")
    assert 'path: "visible.txt"' in text
    assert 'surface: "runtime output already visible"' in text
    assert "not-supplied.txt" not in text


def test_defect_create_evidence_rejects_invalid_severity(tmp_path: Path) -> None:
    result = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "active",
        "--short-description",
        "bad-severity",
        "--deviation",
        "Invalid severity is rejected.",
        "--occurrence",
        "Shape validation.",
        "--evidence",
        "visible",
        "--severity",
        "p11",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "invalid severity: p11" in payload["error"]


def test_defect_create_evidence_rejects_archived_without_action(tmp_path: Path) -> None:
    result = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "archived",
        "--short-description",
        "missing-action",
        "--deviation",
        "Archived records require action.",
        "--occurrence",
        "Shape validation.",
        "--evidence",
        "visible",
        "--severity",
        "p3",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "archived evidence requires --action" in payload["error"]


def test_defect_create_evidence_rejects_status_directory_mismatch(tmp_path: Path) -> None:
    create_active(tmp_path, "status-mismatch")
    path = tmp_path / "config" / "defect" / "active" / f"{evidence_id('status-mismatch')}.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("status: active", "status: archived"), encoding="utf-8")

    result = run_wb(tmp_path, "defect-build-index")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "status archived does not match directory active" in payload["error"]


def test_defect_build_index_outputs_active_and_archived_maps(tmp_path: Path) -> None:
    create_active(tmp_path, "active-contract")
    archived = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "archived",
        "--short-description",
        "archived-contract",
        "--deviation",
        "Archived work-bundle defect.",
        "--occurrence",
        "Created as archived.",
        "--evidence",
        "visible",
        "--severity",
        "p7",
        "--action",
        "dismiss",
    )
    assert archived.returncode == 0, archived.stdout + archived.stderr

    result = run_wb(tmp_path, "defect-build-index")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{evidence_id('active-contract')}:" in result.stdout
    assert f"{evidence_id('archived-contract')}:" in result.stdout
    assert 'deviation: "Planning contract asks for executor-result forbidden fields."' in result.stdout
    assert 'deviation: "Archived work-bundle defect."' in result.stdout
    assert "action: dismiss" in result.stdout


def test_defect_write_index_writes_deterministic_index(tmp_path: Path) -> None:
    create_active(tmp_path, "write-index")
    built = run_wb(tmp_path, "defect-build-index")
    assert built.returncode == 0, built.stdout + built.stderr

    result = run_wb(tmp_path, "defect-write-index")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["active"] == 1
    assert payload["archived"] == 0
    assert Path(payload["path"]).read_text(encoding="utf-8") == built.stdout


def test_defect_archive_evidence_moves_record(tmp_path: Path) -> None:
    created = create_active(tmp_path, "archive-me")

    result = run_wb(tmp_path, "defect-archive-evidence", str(created["id"]), "--action", "completed")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "completed"
    assert payload["changed"] is True
    assert not Path(str(payload["source_path"])).exists()
    archived = Path(payload["archived_path"])
    assert archived.exists()
    text = archived.read_text(encoding="utf-8")
    assert "status: archived" in text
    assert "action: completed" in text


def test_defect_duplicate_identical_create_reports_changed_false(tmp_path: Path) -> None:
    first = create_active(tmp_path, "duplicate")
    second = create_active(tmp_path, "duplicate")

    assert first["path"] == second["path"]
    assert first["changed"] is True
    assert second["changed"] is False


def test_defect_conflicting_duplicate_fails_without_overwrite(tmp_path: Path) -> None:
    first = create_active(tmp_path, "collision")
    original = Path(str(first["path"])).read_text(encoding="utf-8")

    result = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "active",
        "--short-description",
        "collision",
        "--deviation",
        "Different deviation.",
        "--occurrence",
        "Same id should collide.",
        "--evidence",
        "visible runtime surface",
        "--severity",
        "p3",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "evidence file collision" in payload["error"]
    assert Path(str(first["path"])).read_text(encoding="utf-8") == original


def test_defect_dispatcher_routes_all_commands_and_command_help(tmp_path: Path) -> None:
    for command in [
        "defect-ensure-store",
        "defect-create-evidence",
        "defect-build-index",
        "defect-write-index",
        "defect-archive-evidence",
        "defect-migrate-store",
    ]:
        result = run_wb(tmp_path, command, "--help")
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"usage: wb.py {command}" in result.stdout


def test_defect_catalog_ignores_cwd_shadow(tmp_path: Path) -> None:
    custom_catalog = CATALOG.replace("  - p3\n", "")
    cwd = prepare_cwd(tmp_path, custom_catalog)

    result = run_wb(
        tmp_path,
        "defect-create-evidence",
        "--status",
        "active",
        "--short-description",
        "catalog-severity",
        "--deviation",
        "Catalog controls severity.",
        "--occurrence",
        "The reference catalog omits p3.",
        "--evidence",
        "visible",
        "--severity",
        "p3",
        cwd=cwd,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"


def test_defect_evidence_rule_remains_minimal_storage_after_evaluation() -> None:
    rule = (REPO_ROOT / "rules/work-bundle/wb-defect-evidence.md").read_text(encoding="utf-8")

    assert "Record only the minimal first-observed evidence" in rule
    assert "Record only files, artifacts, UI output, terminal output, or runtime surfaces already visible" in rule
    assert "Do not perform additional file search, repository browsing, historical tracing, or contract exploration" in rule
    assert "Do not delay or widen plan execution to enrich a defect record" in rule
    assert "Do not record project business logic, project implementation" in rule
    assert "Do not expand evidence capture into evaluation, root-cause investigation, or exhaustive workflow-chain tracing" in rule
    assert "Use `defect-migrate-store` explicitly when the legacy store remains" in rule
    assert "Do not make a non-migration defect command migrate, merge, or initialize beside legacy authority" in rule


def test_retired_violation_vocabulary_is_limited_to_fail_only_surfaces() -> None:
    roots = ["AGENTS.md", "references", "rules", "scripts", "skills", "tests"]
    tokens = (
        "wb-violation",
        "violation_closure",
        "REQ-VIOL-001",
        "violation-ensure-store",
        "violation-create-evidence",
        "violation-build-index",
        "violation-write-index",
        "violation-archive-evidence",
        "wb-violation-evidence.yaml",
        "work-bundle/violations.py",
        "test_work_bundle_violation_evidence",
    )
    allowed = {
        REPO_ROOT / "scripts/work-bundle/dispatcher.py",
        Path(__file__).resolve(),
        REPO_ROOT / "tests/test_work_bundle_defect_migration.py",
    }
    offenders: list[str] = []
    for root_name in roots:
        root = REPO_ROOT / root_name
        paths = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(token in text for token in tokens) and path.resolve() not in allowed:
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
    assert not (REPO_ROOT / "scripts/work-bundle/violations.py").exists()
    assert not (REPO_ROOT / "references/wb-violation-evidence.yaml").exists()
    assert not (REPO_ROOT / "rules/work-bundle/wb-violation-evidence.md").exists()
    assert not (REPO_ROOT / "rules/work-bundle/wb-violation-evaluation.md").exists()
    assert not (REPO_ROOT / "tests/test_work_bundle_violation_evidence.py").exists()
    assert "## On Violation" in (REPO_ROOT / "rules/repository-boundary.md").read_text(encoding="utf-8")
