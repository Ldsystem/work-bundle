from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WB = REPO_ROOT / "scripts" / "wb.py"


def run_wb(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    cwd = tmp_path / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(tmp_path / "config")
    return subprocess.run(
        [sys.executable, str(WB), *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def evidence_id(slug: str) -> str:
    return f"evidence-{datetime.now().strftime('%Y%m%d')}-{slug}"


def write_legacy_record(tmp_path: Path, *, status: str = "active", slug: str = "migration-record") -> tuple[Path, bytes]:
    root = tmp_path / "config" / "violation"
    (root / "active").mkdir(parents=True, exist_ok=True)
    (root / "archived").mkdir(parents=True, exist_ok=True)
    action = "null" if status == "active" else "completed"
    content = (
        'deviation: "Legacy evidence must survive migration."\n'
        'occurrence: "Observed before the defect cutover."\n'
        'evidence:\n'
        '  - surface: "visible migration fixture"\n'
        '    role: "first-evidence"\n'
        f'status: {status}\n'
        f'action: {action}\n'
        'severity: p3\n'
    ).encode()
    path = root / status / f"{evidence_id(slug)}.yaml"
    path.write_bytes(content)
    return path, content


def record_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for status in ("active", "archived"):
        for path in sorted((root / status).glob("*.yaml")):
            digest.update(f"{status}/{path.name}".encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\n")
    return digest.hexdigest()


def publish_incomplete_destination(tmp_path: Path, *, mismatch: bool = False) -> tuple[Path, Path]:
    legacy_path, _ = write_legacy_record(tmp_path)
    legacy = legacy_path.parents[1]
    destination = tmp_path / "config" / "defect"
    shutil.copytree(legacy, destination)
    fingerprint = record_fingerprint(destination)
    marker = {
        "schema_version": 1,
        "source_fingerprint": "0" * 64 if mismatch else fingerprint,
        "destination_fingerprint": fingerprint,
    }
    (destination / ".migration-marker.json").write_text(json.dumps(marker), encoding="utf-8")
    (destination / ".staging-owner").write_text("work-bundle:defect-migrate-store:v1\n", encoding="utf-8")
    return legacy, destination


def test_defect_migrate_store_preserves_record_bytes_and_rebuilds_index(tmp_path: Path) -> None:
    legacy_path, original = write_legacy_record(tmp_path)
    (legacy_path.parents[1] / "index.yaml").write_text("stale: true\n", encoding="utf-8")

    result = run_wb(tmp_path, "defect-migrate-store")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["migration_status"] == "migrated"
    defect = tmp_path / "config" / "defect"
    assert not (tmp_path / "config" / "violation").exists()
    assert (defect / "active" / legacy_path.name).read_bytes() == original
    assert legacy_path.stem in (defect / "index.yaml").read_text(encoding="utf-8")
    assert not (defect / ".migration-marker.json").exists()
    assert not (defect / ".staging-owner").exists()


def test_defect_non_migration_command_blocks_before_destination_creation(tmp_path: Path) -> None:
    cases = {
        "defect-ensure-store": [],
        "defect-create-evidence": ["--status", "active", "--short-description", "guarded", "--deviation", "guard", "--occurrence", "guard", "--evidence", "visible", "--severity", "p3"],
        "defect-build-index": [],
        "defect-write-index": [],
        "defect-archive-evidence": [evidence_id("migration-record"), "--action", "completed"],
    }
    for command, arguments in cases.items():
        case = tmp_path / command
        write_legacy_record(case)
        result = run_wb(case, command, *arguments)
        assert result.returncode == 1, command
        assert "defect-migrate-store" in result.stdout
        assert not (case / "config" / "defect").exists()


def test_defect_non_migration_commands_block_on_staging_or_marker(tmp_path: Path) -> None:
    staging_case = tmp_path / "staging"
    staging = staging_case / "config" / ".defect-migration-staging"
    staging.mkdir(parents=True)
    staging_result = run_wb(staging_case, "defect-ensure-store")
    assert staging_result.returncode == 1
    assert staging.exists()

    marker_case = tmp_path / "marker"
    ensured = run_wb(marker_case, "defect-ensure-store")
    assert ensured.returncode == 0
    marker = marker_case / "config" / "defect" / ".migration-marker.json"
    marker.write_text("{}", encoding="utf-8")
    marker_result = run_wb(marker_case, "defect-build-index")
    assert marker_result.returncode == 1
    assert "defect-migrate-store" in marker_result.stdout


def test_defect_migrate_store_fails_closed_when_both_roots_are_unmarked(tmp_path: Path) -> None:
    write_legacy_record(tmp_path)
    defect = tmp_path / "config" / "defect"
    (defect / "active").mkdir(parents=True)
    (defect / "archived").mkdir()
    config = tmp_path / "config"
    before = sorted(path.relative_to(config).as_posix() for path in config.rglob("*"))

    result = run_wb(tmp_path, "defect-migrate-store")

    assert result.returncode == 1
    assert "conflict" in result.stdout
    assert sorted(path.relative_to(config).as_posix() for path in config.rglob("*")) == before


def test_defect_migrate_store_is_noop_when_neither_store_exists(tmp_path: Path) -> None:
    result = run_wb(tmp_path, "defect-migrate-store")

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["migration_status"] == "no-store"
    assert not (tmp_path / "config" / "defect").exists()


def test_defect_migrate_store_rejects_invalid_legacy_without_destination(tmp_path: Path) -> None:
    path, original = write_legacy_record(tmp_path)
    path.write_text("invalid\n", encoding="utf-8")

    result = run_wb(tmp_path, "defect-migrate-store")

    assert result.returncode == 1
    assert path.read_text(encoding="utf-8") == "invalid\n"
    assert not (tmp_path / "config" / "defect").exists()
    assert original != path.read_bytes()


def test_defect_migrate_store_resumes_matching_published_destination(tmp_path: Path) -> None:
    legacy, destination = publish_incomplete_destination(tmp_path)
    result = run_wb(tmp_path, "defect-migrate-store")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["resumed"] is True
    assert not legacy.exists()
    assert destination.exists()
    assert not (destination / ".migration-marker.json").exists()
    assert not (destination / ".staging-owner").exists()


def test_defect_migrate_store_rejects_mismatched_published_destination(tmp_path: Path) -> None:
    legacy, destination = publish_incomplete_destination(tmp_path, mismatch=True)
    result = run_wb(tmp_path, "defect-migrate-store")
    assert result.returncode == 1
    assert "invalid defect migration marker" in result.stdout
    assert legacy.exists()
    assert destination.exists()
    assert (destination / ".migration-marker.json").exists()


def test_defect_migrate_store_finalizes_destination_only_marker(tmp_path: Path) -> None:
    legacy, destination = publish_incomplete_destination(tmp_path)
    shutil.rmtree(legacy)
    result = run_wb(tmp_path, "defect-migrate-store")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["resumed"] is True
    assert not (destination / ".migration-marker.json").exists()


def test_defect_migrate_store_replaces_owned_staging_beside_legacy(tmp_path: Path) -> None:
    write_legacy_record(tmp_path)
    staging = tmp_path / "config" / ".defect-migration-staging"
    staging.mkdir()
    (staging / ".staging-owner").write_text("work-bundle:defect-migrate-store:v1\n", encoding="utf-8")
    (staging / "partial").write_text("partial", encoding="utf-8")
    result = run_wb(tmp_path, "defect-migrate-store")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not staging.exists()
    assert (tmp_path / "config" / "defect").exists()


def test_defect_migrate_store_rejects_unowned_staging(tmp_path: Path) -> None:
    staging = tmp_path / "config" / ".defect-migration-staging"
    staging.mkdir(parents=True)
    (staging / "user-file").write_text("preserve", encoding="utf-8")
    result = run_wb(tmp_path, "defect-migrate-store")
    assert result.returncode == 1
    assert (staging / "user-file").read_text(encoding="utf-8") == "preserve"


def test_defect_migrate_store_is_idempotent_after_success(tmp_path: Path) -> None:
    write_legacy_record(tmp_path)
    first = run_wb(tmp_path, "defect-migrate-store")
    destination = tmp_path / "config" / "defect"
    before = {path.relative_to(destination).as_posix(): path.read_bytes() for path in destination.rglob("*") if path.is_file()}
    second = run_wb(tmp_path, "defect-migrate-store")
    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(second.stdout)["migration_status"] == "already-migrated"
    assert {path.relative_to(destination).as_posix(): path.read_bytes() for path in destination.rglob("*") if path.is_file()} == before


def test_defect_migrate_store_rejects_invalid_destination_only(tmp_path: Path) -> None:
    destination = tmp_path / "config" / "defect"
    destination.mkdir(parents=True)
    sentinel = destination / "preserve"
    sentinel.write_text("user-state", encoding="utf-8")
    result = run_wb(tmp_path, "defect-migrate-store")
    assert result.returncode == 1
    assert "invalid evidence store layout" in result.stdout
    assert sentinel.read_text(encoding="utf-8") == "user-state"


def test_legacy_command_fails_with_guidance_without_store_effects(tmp_path: Path) -> None:
    replacements = {
        "violation-ensure-store": "defect-ensure-store",
        "violation-create-evidence": "defect-create-evidence",
        "violation-build-index": "defect-build-index",
        "violation-write-index": "defect-write-index",
        "violation-archive-evidence": "defect-archive-evidence",
    }
    for command, replacement in replacements.items():
        case = tmp_path / command
        legacy_path, original = write_legacy_record(case)
        result = run_wb(case, command)
        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["diagnostic"] == "WB_LEGACY_COMMAND_REMOVED"
        assert payload["replacement_command"] == replacement
        assert legacy_path.read_bytes() == original
        assert not (case / "config" / "defect").exists()
