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
                "prefer_subagent: false",
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
    assert agents_path.read_text(encoding="utf-8").startswith(custom_agents.rstrip() + "\n\n")
    assert role_path.read_text(encoding="utf-8") == custom_role

    agents_path.write_text(custom_agents, encoding="utf-8")
    with_force = run_wb(config_root, "init-project", str(project), "--name", "demo", "--force")
    assert with_force.returncode == 0, with_force.stdout + with_force.stderr
    force_data = json.loads(with_force.stdout)
    assert str(agents_path) in force_data["changed_files"]
    assert force_data["agents_status"] == "updated"
    assert force_data["agents_sync"]["template_checksum_sha256"]
    assert force_data["agents_sync"]["changed_files"] == [str(project / ".work-bundle/project.yaml"), str(agents_path)]
    assert agents_path.read_text(encoding="utf-8").startswith(custom_agents.rstrip() + "\n\n")
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
    assert template_text.startswith("projects:")
    for field in PROJECT_REGISTRY_ENTRY_FIELDS:
        assert field in template_text

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
    assert agents_path.read_text(encoding="utf-8").startswith(custom_agents.rstrip() + "\n\n")
    assert migrate_data["agents_status"] == "updated"
    assert migrate_data["agents_sync"]["template_checksum_sha256"]
    assert str(agents_path) in migrate_data["agents_sync"]["changed_files"]
    assert not bootstrap_dir.exists()
    assert any("legacy-bootstrap-archive" in path for path in migrate_data["changed_files"])
    report_text = Path(migrate_data["migration_report"]).read_text(encoding="utf-8")
    assert "## Retired Legacy Bootstrap Artifacts" in report_text
    assert migrate_data["retired_bootstrap"]["archive_root"] in report_text


def test_migrate_force_wraps_legacy_agents_template_without_duplicate(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    agents_path = project / "AGENTS.md"
    template = (REPO_ROOT / "references/assets/template/AGENTS.md").read_text(encoding="utf-8")
    agents_path.write_text(template, encoding="utf-8")

    migrated = run_wb(config_root, "migrate-project", str(project), "--name", "demo", "--force")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    data = json.loads(migrated.stdout)
    text = agents_path.read_text(encoding="utf-8")

    assert data["agents_status"] == "updated"
    assert data["agents_sync"]["warnings"] == ["legacy-template-wrapped"]
    assert text.count("# Work Bundle RULE START") == 1
    assert text.count("# Work Bundle RULE END") == 1
    assert text.startswith("# ========================\n# Work Bundle RULE START")


def test_doctor_repair_refreshes_agents_section_and_preserves_user_content(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    agents_path = project / "AGENTS.md"
    agents_path.write_text(
        "\n".join(
            [
                "# User Rules",
                "keep this before",
                "# ========================",
                "# Work Bundle RULE START",
                "# ========================",
                "stale managed body",
                "# ========================",
                "# Work Bundle RULE END",
                "# ========================",
                "keep this after",
                "",
            ]
        ),
        encoding="utf-8",
    )

    repaired = run_wb(config_root, "doctor-project", str(project), "--repair")
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    data = json.loads(repaired.stdout)
    text = agents_path.read_text(encoding="utf-8")

    assert data["agents_status"] == "updated"
    assert data["agents_sync"]["template_checksum_sha256"]
    assert str(agents_path) in data["agents_sync"]["changed_files"]
    assert "stale managed body" not in text
    assert "keep this before" in text
    assert "keep this after" in text
    assert text.count("# Work Bundle RULE START") == 1


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
    assert data["prefer_subagent"]["prefer_subagent"] is False
    assert data["prefer_subagent"]["source"] == "project"
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


def test_templates_include_layered_prefer_subagent_defaults() -> None:
    bootstrap_text = (REPO_ROOT / "references/assets/template/bootstrap.yaml").read_text(encoding="utf-8")
    project_text = (REPO_ROOT / "references/assets/template/project.yaml").read_text(encoding="utf-8")
    agents_text = (REPO_ROOT / "references/assets/template/AGENTS.md").read_text(encoding="utf-8")

    assert "prefer_subagent: false" in bootstrap_text
    assert "prefer_subagent: false" in project_text
    assert "agents_sync:" in project_text
    assert "template_checksum_sha256: \"\"" in project_text
    assert "status: never-synced" in project_text
    assert ".work-bundle/project.yaml` -> `prefer_subagent`" in agents_text
    assert "then `$work_bundle_config_root/bootstrap.yaml` -> `prefer_subagent`, then `false`" in agents_text
    assert "bypass repository preflight" in agents_text


def test_resolve_effective_prefer_subagent_uses_project_global_default_order(tmp_path: Path, monkeypatch) -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))
    try:
        import core  # type: ignore[import-not-found]

        config_root = tmp_path / "config"
        config_root.mkdir()
        monkeypatch.setenv("WB_CONFIG_ROOT", str(config_root))
        project_root = tmp_path / "project"
        metadata_path = project_root / ".work-bundle/project.yaml"
        metadata_path.parent.mkdir(parents=True)

        assert core.resolve_effective_prefer_subagent(project_root)["prefer_subagent"] is False
        assert core.resolve_effective_prefer_subagent(project_root)["source"] == "default"

        (config_root / "bootstrap.yaml").write_text("prefer_subagent: true\n", encoding="utf-8")
        assert core.resolve_effective_prefer_subagent(project_root)["prefer_subagent"] is True
        assert core.resolve_effective_prefer_subagent(project_root)["source"] == "global"

        metadata_path.write_text("prefer_subagent: false\n", encoding="utf-8")
        resolved = core.resolve_effective_prefer_subagent(project_root)
        assert resolved["prefer_subagent"] is False
        assert resolved["source"] == "project"

        metadata_path.write_text("prefer_subagent: true\n", encoding="utf-8")
        assert core.resolve_effective_prefer_subagent(project_root)["prefer_subagent"] is True
    finally:
        if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
            sys.path.pop(0)
        sys.modules.pop("core", None)


def test_agents_sync_creates_missing_agents_md_and_updates_metadata(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        project = tmp_path / "project"
        metadata = project / ".work-bundle/project.yaml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(wb_project._render_project_metadata(project), encoding="utf-8")

        result = wb_project.sync_agents_managed_section(project)
        agents_text = (project / "AGENTS.md").read_text(encoding="utf-8")
        metadata_text = metadata.read_text(encoding="utf-8")

        assert result["agents_status"] == "created"
        assert wb_project.AGENTS_RULE_START_MARKER in agents_text
        assert wb_project.AGENTS_RULE_END_MARKER in agents_text
        managed = agents_text.split(wb_project.AGENTS_RULE_START_MARKER, 1)[1].split(
            wb_project.AGENTS_RULE_END_MARKER, 1
        )[0]
        assert "checksum" not in managed.lower()
        assert f'template_checksum_sha256: "{result["template_checksum_sha256"]}"' in metadata_text
        assert "status: current" in metadata_text
    finally:
        _cleanup_wb_project_modules()


def test_agents_sync_appends_to_existing_agents_without_section(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        project = tmp_path / "project"
        metadata = project / ".work-bundle/project.yaml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(wb_project._render_project_metadata(project), encoding="utf-8")
        agents = project / "AGENTS.md"
        agents.write_text("# User Rules\nkeep this\n", encoding="utf-8")

        result = wb_project.sync_agents_managed_section(project)
        text = agents.read_text(encoding="utf-8")

        assert result["agents_status"] == "updated"
        assert text.startswith("# User Rules\nkeep this\n\n")
        assert text.count(wb_project.AGENTS_RULE_START_MARKER) == 1
    finally:
        _cleanup_wb_project_modules()


def test_agents_sync_replaces_stale_managed_section(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        project = tmp_path / "project"
        metadata = project / ".work-bundle/project.yaml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(wb_project._render_project_metadata(project), encoding="utf-8")
        stale_block = (
            f"{wb_project.AGENTS_RULE_START_MARKER}\n"
            "old managed body\n"
            f"{wb_project.AGENTS_RULE_END_MARKER}\n"
        )
        agents = project / "AGENTS.md"
        agents.write_text(f"# User\n{stale_block}tail\n", encoding="utf-8")

        result = wb_project.sync_agents_managed_section(project)
        text = agents.read_text(encoding="utf-8")

        assert result["agents_status"] == "updated"
        assert "old managed body" not in text
        assert text.startswith("# User\n")
        assert text.endswith("tail\n")
        assert result["template_checksum_sha256"] in metadata.read_text(encoding="utf-8")
    finally:
        _cleanup_wb_project_modules()


def test_agents_sync_current_section_is_idempotent(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        project = tmp_path / "project"
        metadata = project / ".work-bundle/project.yaml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(wb_project._render_project_metadata(project), encoding="utf-8")

        first = wb_project.sync_agents_managed_section(project)
        agents_before = (project / "AGENTS.md").read_text(encoding="utf-8")
        metadata_before = metadata.read_text(encoding="utf-8")
        second = wb_project.sync_agents_managed_section(project)

        assert first["agents_status"] == "created"
        assert second["agents_status"] == "unchanged"
        assert second["changed_files"] == []
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == agents_before
        assert metadata.read_text(encoding="utf-8") == metadata_before
    finally:
        _cleanup_wb_project_modules()


def test_agents_sync_consolidates_multiple_managed_sections(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        project = tmp_path / "project"
        metadata = project / ".work-bundle/project.yaml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(wb_project._render_project_metadata(project), encoding="utf-8")
        block = (
            f"{wb_project.AGENTS_RULE_START_MARKER}\n"
            "old managed body\n"
            f"{wb_project.AGENTS_RULE_END_MARKER}\n"
        )
        agents = project / "AGENTS.md"
        agents.write_text(f"top\n{block}middle\n{block}bottom\n", encoding="utf-8")

        result = wb_project.sync_agents_managed_section(project)
        text = agents.read_text(encoding="utf-8")

        assert result["agents_status"] == "updated"
        assert result["warnings"] == ["multiple-managed-sections-consolidated"]
        assert text.count(wb_project.AGENTS_RULE_START_MARKER) == 1
        assert "top\n" in text
        assert "middle\n" in text
        assert "bottom\n" in text
    finally:
        _cleanup_wb_project_modules()


def test_init_project_metadata_records_agents_sync_checksum(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata = project / ".work-bundle/project.yaml"
    agents_text = (project / "AGENTS.md").read_text(encoding="utf-8")
    metadata_text = metadata.read_text(encoding="utf-8")

    assert "agents_sync:" in metadata_text
    assert "status: current" in metadata_text
    assert "template_checksum_sha256: \"\"" not in metadata_text
    assert "# Work Bundle RULE START" in agents_text
    assert "# Work Bundle RULE END" in agents_text
    managed = agents_text.split("# Work Bundle RULE START", 1)[1].split("# Work Bundle RULE END", 1)[0]
    assert "checksum" not in managed.lower()

    rerun = run_wb(config_root, "init-project", str(project), "--name", "demo")
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert json.loads(rerun.stdout)["changed_files"] == []


def test_set_prefer_subagent_updates_global_bootstrap(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)

    result = run_wb(config_root, "set-prefer-subagent", "enable", "--scope", "global", "--project-root", str(project))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)

    assert data["command"] == "set-prefer-subagent"
    assert data["scope"] == "global"
    assert data["prefer_subagent"] is True
    assert data["status"] == "updated"
    assert data["target_path"] == str((config_root / "bootstrap.yaml").resolve())
    assert "prefer_subagent: true" in (config_root / "bootstrap.yaml").read_text(encoding="utf-8")
    assert data["effective_prefer_subagent"]["prefer_subagent"] is False
    assert data["effective_prefer_subagent"]["source"] == "project"

    project_text = (project / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "prefer_subagent: false" in project_text


def test_set_prefer_subagent_updates_current_workspace_override(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    assert run_wb(config_root, "set-prefer-subagent", "enable", "--scope", "global", "--project-root", str(project)).returncode == 0

    result = run_wb(config_root, "set-prefer-subagent", "disable", "--scope", "project", "--project-root", str(project))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)

    assert data["scope"] == "project"
    assert data["prefer_subagent"] is False
    assert data["target_path"] == str((project / ".work-bundle/project.yaml").resolve())
    assert data["effective_prefer_subagent"]["prefer_subagent"] is False
    assert data["effective_prefer_subagent"]["source"] == "project"
    assert "prefer_subagent: false" in (project / ".work-bundle/project.yaml").read_text(encoding="utf-8")

    show = run_wb(config_root, "show-project", "--project-root", str(project))
    assert show.returncode == 0, show.stdout + show.stderr
    show_data = json.loads(show.stdout)
    assert show_data["prefer_subagent"]["global_prefer_subagent"] is True
    assert show_data["prefer_subagent"]["project_prefer_subagent"] is False


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
