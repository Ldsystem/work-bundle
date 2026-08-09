from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from test_project_initialization import REPO_ROOT, bootstrap_config, git, run_wb


HOOK = REPO_ROOT / "bin" / "work-bundle-session-start.py"


def _init_project(tmp_path: Path) -> tuple[Path, Path]:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")
    init = run_wb(
        config_root,
        "init-project",
        str(project),
        "--mode",
        "single-repository",
        "--name",
        "demo",
    )
    assert init.returncode == 0, init.stdout + init.stderr
    return config_root, project


def _run_hook(config_root: Path, stdin: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(config_root)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_session_start_initialized_project_is_idempotent(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)

    first = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert first.returncode == 0, first.stdout + first.stderr
    first_data = json.loads(first.stdout)
    assert first_data["command"] == "session-start"
    assert first_data["status"] == "passed"
    assert first_data["registry_status"] == "registered"
    assert first_data["agents_status"] == "unchanged"
    assert first_data["changed_files"] == []

    before_agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    before_metadata = (project / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    second = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert second.returncode == 0, second.stdout + second.stderr
    second_data = json.loads(second.stdout)
    assert second_data["agents_status"] == "unchanged"
    assert second_data["changed_files"] == []
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == before_agents
    assert (project / ".work-bundle/project.yaml").read_text(encoding="utf-8") == before_metadata


def test_session_start_uninitialized_project_skips_without_agents_write(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "uninitialized"
    project.mkdir()

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "skipped"
    assert data["project_metadata_status"] == "missing"
    assert data["agents_status"] == "skipped"
    assert data["changed_files"] == []
    assert "wb-initialize-project migrate" in " ".join(data["warnings"])
    assert not (project / "AGENTS.md").exists()


def test_session_start_missing_bootstrap_skips_without_agents_write(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    project = tmp_path / "project"
    project.mkdir()

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "skipped"
    assert data["agents_status"] == "skipped"
    assert data["changed_files"] == []
    assert "bootstrap missing" in " ".join(data["warnings"])
    assert not (project / "AGENTS.md").exists()


def test_session_start_missing_registry_skips_and_preserves_agents(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    registry = config_root / "registry" / "projects.yaml"
    registry.unlink()
    agents_before = (project / "AGENTS.md").read_text(encoding="utf-8")

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "skipped"
    assert data["registry_status"] == "missing"
    assert data["changed_files"] == []
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == agents_before


def test_session_start_unregistered_project_skips_and_preserves_agents(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    (config_root / "registry" / "projects.yaml").write_text("projects: []\n", encoding="utf-8")
    agents_before = (project / "AGENTS.md").read_text(encoding="utf-8")

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "skipped"
    assert data["registry_status"] == "not-registered"
    assert data["changed_files"] == []
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == agents_before


def test_session_start_appends_missing_wrapper_and_preserves_user_content(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    agents_path = project / "AGENTS.md"
    agents_path.write_text("# Project Agents\nkeep this\n", encoding="utf-8")

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    text = agents_path.read_text(encoding="utf-8")
    assert data["status"] == "issues-found"
    assert data["agents_status"] == "updated"
    assert str(agents_path) in data["changed_files"]
    assert text.startswith("# Project Agents\nkeep this\n\n")
    assert text.count("# Work Bundle RULE START") == 1
    assert data["project_agents_checksum"].startswith("sha256:")


def test_session_start_repairs_stale_metadata_without_rewriting_agents(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    agents_path = project / "AGENTS.md"
    metadata_path = project / ".work-bundle/project.yaml"
    agents_before = agents_path.read_text(encoding="utf-8")
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace('status: current', 'status: stale'),
        encoding="utf-8",
    )
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace('template_checksum_sha256: "', 'template_checksum_sha256: "stale-'),
        encoding="utf-8",
    )

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["agents_status"] == "updated"
    assert data["changed_files"] == [str(metadata_path)]
    assert agents_path.read_text(encoding="utf-8") == agents_before
    assert data["project_agents_checksum"].startswith("sha256:")


def test_session_start_wraps_legacy_template(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    agents_path = project / "AGENTS.md"
    agents_path.write_text((REPO_ROOT / "references/assets/template/AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    text = agents_path.read_text(encoding="utf-8")
    assert data["agents_status"] == "updated"
    assert "legacy-template-wrapped" in data["warnings"]
    assert text.count("# Work Bundle RULE START") == 1
    assert text.startswith("# ========================\n# Work Bundle RULE START")


def test_session_start_skips_invalid_project_metadata_with_migration_warning(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    metadata_path.write_text("metadata_version: 1\n", encoding="utf-8")
    agents_before = (project / "AGENTS.md").read_text(encoding="utf-8")

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "skipped"
    assert data["changed_files"] == []
    assert "project metadata missing required fields" in " ".join(data["warnings"])
    assert "wb-initialize-project migrate" in " ".join(data["warnings"])
    assert (project / "AGENTS.md").read_text(encoding="utf-8") == agents_before


def test_hook_uses_json_cwd_and_empty_stdin_cwd(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    json_result = _run_hook(config_root, json.dumps({"cwd": str(project)}), cwd=tmp_path)
    assert json_result.returncode == 0, json_result.stdout + json_result.stderr
    assert json.loads(json_result.stdout)["project_root"] == str(project)

    empty_result = _run_hook(config_root, "", cwd=project)
    assert empty_result.returncode == 0, empty_result.stdout + empty_result.stderr
    data = json.loads(empty_result.stdout)
    assert data["project_root"] == str(project)
    assert data["agents_status"] == "unchanged"


def test_hook_tolerates_malformed_stdin(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    result = _run_hook(config_root, "{not-json", cwd=project)
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["project_root"] == str(project)
    assert "malformed hook JSON stdin" in " ".join(data["warnings"])


def test_hook_started_in_deep_child_syncs_only_workspace_agents(tmp_path: Path) -> None:
    config_root, project = _init_project(tmp_path)
    deep = project / "member-like" / "src" / "feature"
    deep.mkdir(parents=True)

    result = _run_hook(config_root, json.dumps({"cwd": str(deep)}), cwd=deep)

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["project_root"] == str(project)
    assert data["agents_status"] == "unchanged"
    assert not (deep / "AGENTS.md").exists()
