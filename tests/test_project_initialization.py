from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_wb(config_root: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "WB_CONFIG_ROOT": str(config_root),
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), *args],
        cwd=cwd or REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def bootstrap_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    registry = config_root / "registry"
    registry.mkdir(parents=True)
    (config_root / "bootstrap.yaml").write_text(
        "\n".join(
            [
                "bootstrap_version: v1",
                "authority: canonical",
                f"work_bundle_root: {REPO_ROOT}",
                'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
                'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (registry / "projects.yaml").write_text("projects: []\n", encoding="utf-8")
    return config_root


def test_init_project_creates_structure_commits_and_is_idempotent(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")

    init = run_wb(config_root, "init-project", str(project), "--name", "demo")
    assert init.returncode == 0, init.stdout + init.stderr
    init_data = json.loads(init.stdout)
    assert init_data["status"] == "passed"
    assert init_data["failures"] == []

    for relative in [
        ".work-bundle/knowledge/context-packs",
        ".work-bundle/knowledge/indexes",
        ".work-bundle/knowledge/notes",
        ".work-bundle/knowledge/open-questions",
        ".work-bundle/orchestration/spec/active",
        ".work-bundle/orchestration/spec/archived",
        ".work-bundle/orchestration/plan/active",
        ".work-bundle/orchestration/plan/archived",
        ".work-bundle/orchestration/handoff/orchestration/active",
        ".work-bundle/orchestration/handoff/orchestration/archived",
        ".work-bundle/orchestration/handoff/executor/active",
        ".work-bundle/orchestration/handoff/executor/archived",
        ".work-bundle/orchestration/docs",
    ]:
        assert (project / relative).is_dir()

    assert "initialize work-bundle project" in git(project, "log", "--oneline")
    assert "initialize work-bundle knowledge" in git(project / ".work-bundle/knowledge", "log", "--oneline")

    validate = run_wb(config_root, "validate-project", str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert json.loads(validate.stdout)["status"] == "passed"

    rerun = run_wb(config_root, "init-project", str(project), "--name", "demo")
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert json.loads(rerun.stdout)["changed_files"] == []


def test_migrate_project_writes_report_without_breaking_validation(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")
    assert run_wb(config_root, "init-project", str(project), "--name", "demo").returncode == 0

    migrated = run_wb(config_root, "migrate-project", str(project), "--name", "demo")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    data = json.loads(migrated.stdout)
    assert data["status"] == "passed"
    assert Path(data["migration_report"]).is_file()

    validate = run_wb(config_root, "validate-project", str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
