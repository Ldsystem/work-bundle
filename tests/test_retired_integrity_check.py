from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_wb(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), command],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_integrity_check_runtime_surface_is_retired() -> None:
    retired_paths = [
        REPO_ROOT / "skills/wb-integrity-check",
        REPO_ROOT / "rules/integrity-check",
        REPO_ROOT / "references/integrity-check",
        REPO_ROOT / "scripts/integrity-check",
        REPO_ROOT / "scripts/integrity_check_report.py",
        REPO_ROOT / "scripts/work-bundle/integrity.py",
    ]

    for path in retired_paths:
        assert not path.exists(), f"retired integrity-check path still exists: {path}"

    for command in ("integrity-check-report", "integrity-report"):
        result = run_wb(command)
        assert result.returncode == 2
        assert f"unknown command: {command}" in result.stderr


def test_integrity_check_is_absent_from_rule_authoring_contracts() -> None:
    contract_paths = [
        REPO_ROOT / "rules/index.yaml",
        REPO_ROOT / "references/wb-create-rule-validation.yaml",
        REPO_ROOT / "skills/wb-create-rule/SKILL.md",
        REPO_ROOT / "rules/work-bundle/wb-create-rule.md",
        REPO_ROOT / "scripts/work-bundle/rules.py",
        REPO_ROOT / "scripts/work-bundle/README.md",
    ]

    for path in contract_paths:
        assert "integrity-check" not in path.read_text(encoding="utf-8"), path
