from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATION = REPO_ROOT / "scripts" / "orchestration"


def test_wor107_policy_is_owned_only_by_narrow_legacy_utility(tmp_path: Path) -> None:
    generic = (ORCHESTRATION / "review_runtime.py").read_text(encoding="utf-8")
    assert "WOR-107" not in generic

    instance = tmp_path / "handoff.json"
    instance.write_text(
        json.dumps(
            {
                "issue": "WOR-107",
                "excluded_work": ["WOR-66", "WOR-107"],
            }
        ),
        encoding="utf-8",
    )
    arguments = [
        "--instance",
        str(instance),
        "--required-excluded",
        "WOR-66",
        "WOR-107",
    ]
    direct = subprocess.run(
        [sys.executable, str(ORCHESTRATION / "legacy_wor107_migration.py"), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    alias = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATION / "review_runtime.py"),
            "assert-migration-stop",
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert direct.returncode == alias.returncode == 0
    assert json.loads(direct.stdout) == json.loads(alias.stdout)
    assert "deprecated" in alias.stderr.lower()
    assert direct.stderr == ""


def test_public_dispatcher_alias_preserves_legacy_result_and_warns(tmp_path: Path) -> None:
    instance = tmp_path / "handoff.json"
    instance.write_text(
        json.dumps({"issue": "WOR-107", "excluded_work": ["WOR-107"]}),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "wb.py"),
            "assert-migration-stop",
            "--instance",
            str(instance),
            "--required-excluded",
            "WOR-107",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "excluded_work": ["WOR-107"],
        "issue": "WOR-107",
        "status": "passed",
    }
    assert "deprecated" in completed.stderr.lower()
