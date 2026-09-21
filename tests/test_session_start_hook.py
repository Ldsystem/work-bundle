from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "bin" / "work-bundle-session-start.py"


def load_work_bundle_project_module():
    module_path = REPO_ROOT / "scripts/work-bundle/project.py"
    module_dir = str(module_path.parent)
    old_core = sys.modules.pop("core", None)
    sys.path.insert(0, module_dir)
    try:
        spec = importlib.util.spec_from_file_location("session_start_project", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if sys.path and sys.path[0] == module_dir:
            sys.path.pop(0)
        if old_core is not None:
            sys.modules["core"] = old_core


def git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def bootstrap_config(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    (config / "registry").mkdir(parents=True)
    (config / "bootstrap.yaml").write_text(
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
    (config / "registry/projects.yaml").write_text("projects: []\n", encoding="utf-8")
    return config


def run_wb(config_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(config_root.parent)
    env["USERPROFILE"] = str(config_root.parent)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), *args],
        cwd=REPO_ROOT, env=env, check=False, capture_output=True, text=True,
    )


def _init_project(tmp_path: Path) -> tuple[Path, Path]:
    generated_config = bootstrap_config(tmp_path)
    config_root = tmp_path / ".work-bundle"
    generated_config.rename(config_root)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")
    remote = tmp_path / "project.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    project.joinpath("README.md").write_text("demo\n", encoding="utf-8")
    git(project, "add", "README.md")
    git(project, "commit", "-q", "-m", "initial")
    git(project, "remote", "add", "origin", str(remote))
    git(project, "push", "-q", "-u", "origin", "main")
    init = run_wb(
        config_root,
        "init-workspace",
        str(project),
        "--mode",
        "single-repository",
        "--slug",
        "demo",
        "--repository",
        f"source={remote}",
        "--apply",
    )
    assert init.returncode == 0, init.stdout + init.stderr
    return config_root, project


def _run_hook(config_root: Path, stdin: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(config_root.parent)
    env["USERPROFILE"] = str(config_root.parent)
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
    assert first_data["status"] == "passed", json.dumps(first_data, indent=2)
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
    generated_config = bootstrap_config(tmp_path)
    config_root = tmp_path / ".work-bundle"
    generated_config.rename(config_root)
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
    assert data["agents_status"] == "unchanged"
    assert data["changed_files"] == [str(metadata_path)]
    assert agents_path.read_text(encoding="utf-8") == agents_before
    assert data["project_agents_checksum"].startswith("sha256:")


def test_session_start_accepts_equivalent_flow_style_agents_sync_without_rewrite(
    tmp_path: Path,
) -> None:
    config_root, project = _init_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    document = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    agents_sync = document.pop("agents_sync")
    rendered = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).rstrip() + "\n"
    rendered += "agents_sync: " + json.dumps(agents_sync, separators=(",", ":")) + "\n"
    metadata_path.write_text(rendered, encoding="utf-8")
    before = metadata_path.read_bytes()

    result = run_wb(config_root, "session-start", "--project-root", str(project), "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "passed"
    assert data["agents_status"] == "unchanged"
    assert data["changed_files"] == []
    assert metadata_path.read_bytes() == before


def test_agents_sync_owner_rejects_invalid_v4_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_root, project = _init_project(tmp_path)
    agents_path = project / "AGENTS.md"
    metadata_path = project / ".work-bundle/project.yaml"
    agents_path.write_text("# User agents content\n", encoding="utf-8")
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace("authority: canonical\n", ""),
        encoding="utf-8",
    )
    agents_before = agents_path.read_bytes()
    metadata_before = metadata_path.read_bytes()
    monkeypatch.setenv("HOME", str(config_root.parent))
    monkeypatch.setenv("USERPROFILE", str(config_root.parent))
    monkeypatch.setenv("WB_WORK_BUNDLE_ROOT", str(REPO_ROOT))
    project_module = load_work_bundle_project_module()

    with pytest.raises(project_module.InfrastructureError) as caught:
        project_module.sync_agents_managed_section(project)

    assert caught.value.code == "WB_INFRASTRUCTURE_SCHEMA_INVALID"
    assert agents_path.read_bytes() == agents_before
    assert metadata_path.read_bytes() == metadata_before


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
    assert "project metadata version unsupported" in " ".join(data["warnings"])
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
