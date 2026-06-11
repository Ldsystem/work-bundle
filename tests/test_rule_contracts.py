from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_wb(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), *args],
        cwd=cwd or REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_validate_current_rules_passes() -> None:
    result = run_wb("validate-rules", "rules")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "passed"


def test_create_rules_migrates_legacy_yaml_to_markdown(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    root.mkdir()
    (root / "legacy.yaml").write_text(
        "\n".join(
            [
                "id: rule-legacy",
                "status: current",
                "scope: work-bundle",
                "enable_when: [legacy activation]",
                "severity: must",
                "required_behavior: [do required work]",
                "prohibited_behavior: [do not do prohibited work]",
                "validation: [inspect migrated rule]",
                "source_authority: [legacy source]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    created = run_wb("create-rules", str(root))
    assert created.returncode == 0, created.stdout + created.stderr
    assert not (root / "legacy.yaml").exists()
    assert (root / "legacy.md").exists()
    text = (root / "legacy.md").read_text(encoding="utf-8")
    assert "severity:" not in text
    assert "source_authority:" not in text

    validated = run_wb("validate-rules", str(root))
    assert validated.returncode == 0, validated.stdout + validated.stderr


def test_validate_rules_rejects_prohibited_front_matter(tmp_path: Path) -> None:
    root = tmp_path / "rules"
    root.mkdir()
    (root / "bad.md").write_text(
        "---\n"
        "id: bad-rule\n"
        "scope: work-bundle\n"
        "applies_when:\n"
        "  - bad activation\n"
        "enforcement: must\n"
        "load: conditional\n"
        "requires: []\n"
        "---\n\n"
        "# Bad Rule\n\n"
        "## Purpose\n\n- purpose\n\n"
        "## Must\n\n- must\n\n"
        "## Must Not\n\n- must not\n\n"
        "## Validation\n\n- validate\n\n"
        "## On Violation\n\n- stop\n",
        encoding="utf-8",
    )
    (root / "index.yaml").write_text(
        "rules:\n"
        "  - id: bad-rule\n"
        "    path: rules/bad.md\n"
        "    applies_when:\n"
        "      - bad activation\n"
        "    enforcement: must\n"
        "    load: conditional\n"
        "    requires: []\n",
        encoding="utf-8",
    )

    result = run_wb("validate-rules", str(root))
    assert result.returncode == 1
    failures = json.loads(result.stdout)["failures"]
    assert "bad.md:prohibited_front_matter:scope" in failures
