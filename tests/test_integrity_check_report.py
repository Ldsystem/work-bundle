from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "integrity_check_report.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def create_report(tmp_path: Path) -> Path:
    output_root = tmp_path / "reports"
    result = run_cli(
        "new",
        "--template",
        str(REPO_ROOT / "references" / "integrity-check" / "integrity-check-template.md"),
        "--output-root",
        str(output_root),
        "--title",
        "fixture-report",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    return Path(payload["report_path"])


def test_lifecycle_flow_and_validate_report(tmp_path: Path) -> None:
    report = create_report(tmp_path)
    add = run_cli(
        "add-issue",
        "--report",
        str(report),
        "--severity",
        "high",
        "--type",
        "compression_loading",
        "--summary",
        "Startup load is too broad",
        "--recommended-fix",
        "Gate heavy docs behind conditional load",
        "--evidence",
        "agent-observation:startup-eager-load",
        "--requires-human-decision",
    )
    assert add.returncode == 0, add.stderr

    update = run_cli(
        "update-status",
        "--report",
        str(report),
        "--issue-id",
        "WBI-001",
        "--status",
        "fixed",
        "--reason",
        "Boundary-safe guard implemented",
        "--evidence",
        "pytest:test_integrity_check_report",
    )
    assert update.returncode == 0, update.stderr

    summarize = run_cli("summarize-status", "--report", str(report))
    assert summarize.returncode == 0, summarize.stderr
    summary_payload = json.loads(summarize.stdout)
    assert summary_payload["decision_authority"] == "human"
    assert summary_payload["fixed_count"] == 1
    assert summary_payload["open_count"] == 0

    validate = run_cli("validate-report", "--report", str(report))
    assert validate.returncode == 0, validate.stderr
    validate_payload = json.loads(validate.stdout)
    assert validate_payload["status"] == "passed"


def test_boundary_guard_rejects_policy_authority_flag(tmp_path: Path) -> None:
    report = create_report(tmp_path)
    result = run_cli("validate-report", "--report", str(report), "--check-finding-correctness")
    assert result.returncode == 2
    assert "structure" in result.stderr


def test_update_status_requires_evidence_for_fixed(tmp_path: Path) -> None:
    report = create_report(tmp_path)
    add = run_cli(
        "add-issue",
        "--report",
        str(report),
        "--severity",
        "medium",
        "--type",
        "other",
        "--summary",
        "Need source update",
        "--recommended-fix",
        "Add source update",
        "--evidence",
        "agent-observation",
    )
    assert add.returncode == 0, add.stderr
    update = run_cli(
        "update-status",
        "--report",
        str(report),
        "--issue-id",
        "WBI-001",
        "--status",
        "fixed",
        "--reason",
        "fixed",
    )
    assert update.returncode == 1
    assert "requires --evidence" in update.stderr

