from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_BOOTSTRAP_POINTER = "references/bootstrap"
FULL_ORCHESTRATION_DIRS = [
    ".work-bundle/orchestration/spec/active",
    ".work-bundle/orchestration/spec/archived",
    ".work-bundle/orchestration/plan/active",
    ".work-bundle/orchestration/plan/archived",
    ".work-bundle/orchestration/handoff/orchestration/active",
    ".work-bundle/orchestration/handoff/orchestration/archived",
    ".work-bundle/orchestration/handoff/executor/active",
    ".work-bundle/orchestration/handoff/executor/archived",
    ".work-bundle/orchestration/docs",
    ".work-bundle/orchestration/principles",
    ".work-bundle/orchestration/templates",
    ".work-bundle/orchestration/reviews",
    ".work-bundle/orchestration/execution-state",
]
PROJECT_REGISTRY_ENTRY_FIELDS = (
    "slug",
    "name",
    "work_bundle_root",
    "knowledge_root",
    "aliases",
    "source_repositories",
    "status",
    "updated_at",
)


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


def bootstrap_config(tmp_path: Path, work_bundle_root: Path | None = None) -> Path:
    config_root = tmp_path / "config"
    registry = config_root / "registry"
    registry.mkdir(parents=True)
    (config_root / "bootstrap.yaml").write_text(
        "\n".join(
            [
                "bootstrap_version: v1",
                "authority: canonical",
                f"work_bundle_root: {work_bundle_root or REPO_ROOT}",
                'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
                'skill_registry: "$work_bundle_config_root/registry/skill-registry.yaml"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (registry / "projects.yaml").write_text("projects: []\n", encoding="utf-8")
    return config_root


def _import_wb_project():
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))
    import project as wb_project  # type: ignore[import-not-found]

    return wb_project


def _cleanup_wb_project_modules() -> None:
    if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
        sys.path.pop(0)
    sys.modules.pop("project", None)
    sys.modules.pop("core", None)


def _init_managed_text_files(project: Path) -> list[Path]:
    candidates = [
        project / ".gitignore",
        project / "AGENTS.md",
        project / ".work-bundle/project.yaml",
        project / ".work-bundle/knowledge/project.yaml",
        project / "rules/index.yaml",
        project / ".work-bundle/.gitignore",
    ]
    candidates.extend(sorted(project.glob("roles/*.yaml")))
    return [path for path in candidates if path.is_file()]


def _minimal_work_bundle_root(tmp_path: Path, *, include_project_template: bool = True) -> Path:
    root = tmp_path / "work-bundle-root"
    for relative in [
        "references/wb-initialize-project-default-work-bundle-tree.yaml",
        "references/wb-initialize-project-default-work-bundle-gitignore",
        "references/wb-initialize-project-default-rule-index.yaml",
        "references/assets/template/AGENTS.md",
        "references/assets/template/projects.yaml",
    ]:
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    if include_project_template:
        project_template = REPO_ROOT / "references/assets/template/project.yaml"
        target = root / "references/assets/template/project.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(project_template.read_text(encoding="utf-8"), encoding="utf-8")
    return root


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
        *FULL_ORCHESTRATION_DIRS,
    ]:
        assert (project / relative).is_dir()

    assert not (project / "rules/contract.yaml").exists()
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


def test_registry_upsert_preserves_aliases_and_sources(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    resolved = project.resolve()
    registry_path = config_root / "registry" / "projects.yaml"
    wb_root = str(resolved / ".work-bundle")
    kb_root = str(resolved / ".work-bundle" / "knowledge")
    registry_path.write_text(
        "\n".join(
            [
                "projects:",
                "  - slug: demo",
                "    name: demo",
                f"    work_bundle_root: {wb_root}",
                f"    knowledge_root: {kb_root}",
                "    aliases:",
                "      - demo",
                "      - sample",
                "    source_repositories:",
                f"      - path: {resolved}",
                "        work_dir: true",
                '        remote: ""',
                "    status: active",
                "    updated_at: 2026-01-01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    first = run_wb(config_root, "register-project", str(project), "--name", "demo")
    assert first.returncode == 0, first.stdout + first.stderr
    first_data = json.loads(first.stdout)
    assert first_data["status"] == "skipped"
    entry = first_data["project"]
    assert entry["aliases"] == ["demo", "sample"]
    assert entry["updated_at"] == "2026-01-01"
    assert len(entry["source_repositories"]) == 1
    assert entry["source_repositories"][0]["path"] == str(resolved)

    text = registry_path.read_text(encoding="utf-8")
    assert "sample" in text
    assert "updated_at: 2026-01-01" in text


def test_registry_upsert_replaces_aliases_when_explicit(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    resolved = project.resolve()
    registry_path = config_root / "registry" / "projects.yaml"
    wb_root = str(resolved / ".work-bundle")
    kb_root = str(resolved / ".work-bundle" / "knowledge")
    registry_path.write_text(
        "\n".join(
            [
                "projects:",
                "  - slug: demo",
                "    name: demo",
                f"    work_bundle_root: {wb_root}",
                f"    knowledge_root: {kb_root}",
                "    aliases:",
                "      - demo",
                "      - sample",
                "    source_repositories:",
                f"      - path: {resolved}",
                "        work_dir: true",
                '        remote: ""',
                "    status: active",
                "    updated_at: 2026-01-01",
                "",
            ]
        ),
        encoding="utf-8",
    )

    wb_project = _import_wb_project()
    try:
        entry, changed, _ = wb_project.upsert_project_registry(project.resolve(), "demo", ["only-alias"])
        assert changed is True
        assert entry["aliases"] == ["only-alias"]
        assert entry["updated_at"] != "2026-01-01"
    finally:
        _cleanup_wb_project_modules()


def _init_fixture_project(tmp_path: Path) -> tuple[Path, Path]:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")
    assert run_wb(config_root, "init-project", str(project), "--name", "demo").returncode == 0
    return config_root, project


def test_doctor_project_routed_and_returns_mechanical_json(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    result = run_wb(config_root, "doctor-project", str(project))
    assert result.returncode in {0, 1}, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["command"] == "doctor-project"
    assert "status" in data
    assert "failures" in data
    assert "changed_files" in data


def test_init_force_overwrites_init_managed_templates_only(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    agents_path = project / "AGENTS.md"
    custom_agents = "# Custom Agents\n"
    agents_path.write_text(custom_agents, encoding="utf-8")
    role_path = project / "roles" / "project-manager.yaml"
    custom_role = "id: project-manager\ncustom: true\n"
    role_path.write_text(custom_role, encoding="utf-8")

    without_force = run_wb(config_root, "init-project", str(project), "--name", "demo")
    assert without_force.returncode == 0, without_force.stdout + without_force.stderr
    assert agents_path.read_text(encoding="utf-8") == custom_agents
    assert role_path.read_text(encoding="utf-8") == custom_role

    with_force = run_wb(config_root, "init-project", str(project), "--name", "demo", "--force")
    assert with_force.returncode == 0, with_force.stdout + with_force.stderr
    force_data = json.loads(with_force.stdout)
    assert str(agents_path) in force_data["changed_files"]
    assert agents_path.read_text(encoding="utf-8") != custom_agents
    assert role_path.read_text(encoding="utf-8") == custom_role


def test_migrate_project_retires_legacy_bootstrap_without_force(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    bootstrap_dir = project / "references/bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = bootstrap_dir / "agent-bootstrap.md"
    legacy_file.write_text("# legacy bootstrap\n", encoding="utf-8")

    migrated = run_wb(config_root, "migrate-project", str(project), "--name", "demo")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    migrate_data = json.loads(migrated.stdout)

    assert not bootstrap_dir.exists()
    assert migrate_data["retired_bootstrap"]["archive_root"] is not None
    assert len(migrate_data["retired_bootstrap"]["artifacts"]) == 1
    artifact = migrate_data["retired_bootstrap"]["artifacts"][0]
    assert artifact["source"] == "references/bootstrap/agent-bootstrap.md"
    assert artifact["action"] == "archived-and-removed"
    archive_root = project / migrate_data["retired_bootstrap"]["archive_root"]
    assert (archive_root / "agent-bootstrap.md").is_file()
    assert (archive_root / "agent-bootstrap.md").read_text(encoding="utf-8") == "# legacy bootstrap\n"

    report_text = Path(migrate_data["migration_report"]).read_text(encoding="utf-8")
    assert "## Retired Legacy Bootstrap Artifacts" in report_text
    assert "references/bootstrap/agent-bootstrap.md" in report_text
    assert migrate_data["retired_bootstrap"]["archive_root"] in report_text


def test_init_project_does_not_create_references_bootstrap(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    assert not (project / "references/bootstrap").exists()
    validate = run_wb(config_root, "validate-project", str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert LEGACY_BOOTSTRAP_POINTER not in validate.stdout


def test_init_created_files_contain_no_legacy_bootstrap_pointers(tmp_path: Path) -> None:
    _, project = _init_fixture_project(tmp_path)
    offenders: list[str] = []
    for path in _init_managed_text_files(project):
        if LEGACY_BOOTSTRAP_POINTER in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(project)))
    assert offenders == []


def test_registry_parser_tracks_projects_template_schema(tmp_path: Path) -> None:
    template_path = REPO_ROOT / "references/assets/template/projects.yaml"
    template_text = template_path.read_text(encoding="utf-8")
    assert template_text.strip() == "projects: []"

    wb_project = _import_wb_project()
    try:
        sample: dict[str, object] = {
            "slug": "demo",
            "name": "demo",
            "work_bundle_root": "/tmp/project/.work-bundle",
            "knowledge_root": "/tmp/project/.work-bundle/knowledge",
            "aliases": ["demo", "sample"],
            "source_repositories": [
                {"path": "/tmp/project", "work_dir": True, "remote": "origin"},
            ],
            "status": "active",
            "updated_at": "2026-06-11",
        }
        rendered = wb_project._render_projects([sample])
        assert rendered.startswith("projects:\n")
        registry_file = tmp_path / "projects.yaml"
        registry_file.write_text(rendered, encoding="utf-8")
        parsed = wb_project._project_blocks(registry_file)
        assert len(parsed) == 1
        entry = parsed[0]
        for field in PROJECT_REGISTRY_ENTRY_FIELDS:
            assert field in entry
        assert entry["slug"] == sample["slug"]
        assert entry["aliases"] == sample["aliases"]
        assert entry["source_repositories"] == sample["source_repositories"]
        assert wb_project._registry_entries_equivalent(entry, sample)
    finally:
        _cleanup_wb_project_modules()


def test_init_fails_mechanically_when_required_template_missing(tmp_path: Path) -> None:
    work_bundle_root = _minimal_work_bundle_root(tmp_path, include_project_template=False)
    config_root = bootstrap_config(tmp_path, work_bundle_root=work_bundle_root)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")

    init = run_wb(config_root, "init-project", str(project), "--name", "demo")
    assert init.returncode == 1, init.stdout + init.stderr
    data = json.loads(init.stdout)
    assert data["command"] == "init-project"
    assert data["status"] == "issues-found"
    assert data["failures"] == ["WB_REFERENCE_ASSET_MISSING"]
    assert data["missing_reference"].endswith("references/assets/template/project.yaml")


def test_healthy_reinit_reports_empty_changed_files(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    rerun = run_wb(config_root, "init-project", str(project), "--name", "demo")
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    rerun_data = json.loads(rerun.stdout)
    assert rerun_data["status"] == "passed"
    assert rerun_data["changed_files"] == []


def test_migrate_force_does_not_overwrite_agents_md(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    bootstrap_dir = project / "references/bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    (bootstrap_dir / "agent-bootstrap.md").write_text("# legacy bootstrap\n", encoding="utf-8")
    agents_path = project / "AGENTS.md"
    custom_agents = "# Custom Agents\n"
    agents_path.write_text(custom_agents, encoding="utf-8")

    migrated = run_wb(config_root, "migrate-project", str(project), "--name", "demo", "--force")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    migrate_data = json.loads(migrated.stdout)
    assert agents_path.read_text(encoding="utf-8") == custom_agents
    assert not bootstrap_dir.exists()
    assert any("legacy-bootstrap-archive" in path for path in migrate_data["changed_files"])
    report_text = Path(migrate_data["migration_report"]).read_text(encoding="utf-8")
    assert "## Retired Legacy Bootstrap Artifacts" in report_text
    assert migrate_data["retired_bootstrap"]["archive_root"] in report_text


def test_migrate_project_retires_legacy_rules_contract(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    contract_path = project / "rules/contract.yaml"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text("id: work-bundle-rule-contract\nstatus: current\n", encoding="utf-8")

    migrated = run_wb(config_root, "migrate-project", str(project), "--name", "demo")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    migrate_data = json.loads(migrated.stdout)

    assert not contract_path.exists()
    assert migrate_data["retired_rules_contract"]["archive_root"] is not None
    artifact = migrate_data["retired_rules_contract"]["artifact"]
    assert artifact is not None
    assert artifact["source"] == "rules/contract.yaml"
    assert artifact["action"] == "archived-and-removed"
    archive_root = project / migrate_data["retired_rules_contract"]["archive_root"]
    assert (archive_root / "contract.yaml").is_file()

    report_text = Path(migrate_data["migration_report"]).read_text(encoding="utf-8")
    assert "## Retired Legacy Rules Contract" in report_text
    assert "rules/contract.yaml" in report_text


def test_validate_project_omits_pointer_diagnostics(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    result = run_wb(config_root, "validate-project", str(project))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["path_model"]["work_bundle_root"]
    for key in (
        "work_bundle_root_pointer_path",
        "work_bundle_root_pointer_exists",
        "work_bundle_root_pointer_state",
        "work_bundle_root_pointer_diagnostic",
        "work_bundle_root_pointer_reason",
    ):
        assert key not in data


def test_wb_work_bundle_root_env_overrides_bootstrap(tmp_path: Path) -> None:
    work_bundle_root = _minimal_work_bundle_root(tmp_path)
    config_root = bootstrap_config(tmp_path, work_bundle_root=REPO_ROOT)
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(config_root)
    env["WB_WORK_BUNDLE_ROOT"] = str(work_bundle_root)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), "show-project", "--project-root", str(REPO_ROOT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["path_model"]["work_bundle_root"] == str(work_bundle_root.resolve())


def test_migrate_work_bundle_config_migrates_legacy_bootstrap(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    legacy_bootstrap = "\n".join(
        [
            "bootstrap_version: 1",
            "authority: canonical",
            "work_bundle_config_root: ~/.work-bundle",
            f"root_pointer: {config_root / 'work-bundle-root.yaml'}",
            f"project_registry: {config_root / 'registry/projects.yaml'}",
            f"skill_registry: {config_root / 'skills/skill-registry.yaml'}",
            "",
        ]
    )
    (config_root / "bootstrap.yaml").write_text(legacy_bootstrap, encoding="utf-8")
    (config_root / "work-bundle-root.yaml").write_text(
        "\n".join(
            [
                "pointer_version: 1",
                f"work_bundle_root: {REPO_ROOT}",
                "updated_at: 2026-01-01T00:00:00Z",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (config_root / "skills").mkdir()
    (config_root / "skills" / "skill-registry.yaml").write_text("skills: []\n", encoding="utf-8")
    (config_root / "registry").mkdir()
    (config_root / "registry" / "projects.yaml").write_text("projects: []\n", encoding="utf-8")

    migrated = run_wb(
        config_root,
        "migrate-work-bundle-config",
        "--toolkit-root",
        str(REPO_ROOT),
    )
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    data = json.loads(migrated.stdout)
    assert data["legacy_bootstrap"] is True
    assert data["work_bundle_root"] == str(REPO_ROOT.resolve())
    bootstrap_text = (config_root / "bootstrap.yaml").read_text(encoding="utf-8")
    assert "bootstrap_version: v1" in bootstrap_text
    assert f"work_bundle_root: {REPO_ROOT.resolve()}" in bootstrap_text
    assert "$work_bundle_config_root/registry/skill-registry.yaml" in bootstrap_text
    assert (config_root / "registry" / "skill-registry.yaml").is_file()
    assert (config_root / "archive").is_dir()
    assert not (config_root / "work-bundle-root.yaml").exists()
    if data.get("retired_root_pointer"):
        assert Path(data["retired_root_pointer"]).is_file()


def test_migrate_work_bundle_config_resolves_legacy_pointer_without_toolkit_flag(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    legacy_bootstrap = "\n".join(
        [
            "bootstrap_version: 1",
            "authority: canonical",
            f"root_pointer: {config_root / 'work-bundle-root.yaml'}",
            f"project_registry: {config_root / 'registry/projects.yaml'}",
            f"skill_registry: {config_root / 'skills/skill-registry.yaml'}",
            "",
        ]
    )
    (config_root / "bootstrap.yaml").write_text(legacy_bootstrap, encoding="utf-8")
    (config_root / "work-bundle-root.yaml").write_text(
        "\n".join(
            [
                "pointer_version: 1",
                f"work_bundle_root: {REPO_ROOT}",
                "updated_at: 2026-01-01T00:00:00Z",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (config_root / "skills").mkdir()
    (config_root / "skills" / "skill-registry.yaml").write_text("skills: []\n", encoding="utf-8")
    (config_root / "registry").mkdir()
    (config_root / "registry" / "projects.yaml").write_text("projects: []\n", encoding="utf-8")

    migrated = run_wb(config_root, "migrate-work-bundle-config")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    data = json.loads(migrated.stdout)
    assert data["work_bundle_root"] == str(REPO_ROOT.resolve())
    assert not (config_root / "work-bundle-root.yaml").exists()
