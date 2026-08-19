from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


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
PROJECT_REGISTRY_SOURCE_FIELDS = (
    "id",
    "path",
    "checkout_role",
    "work_dir",
    "remote",
    "git_repository",
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
    script_root = REPO_ROOT / "scripts" / "work-bundle"
    for module_name in ("project", "bootstrap_config", "core"):
        module = sys.modules.get(module_name)
        module_file = Path(getattr(module, "__file__", "")) if module is not None else None
        if module_file is not None and script_root not in module_file.parents:
            sys.modules.pop(module_name, None)
    sys.path.insert(0, str(script_root))
    import project as wb_project  # type: ignore[import-not-found]

    return wb_project


def _cleanup_wb_project_modules() -> None:
    if sys.path and sys.path[0] == str(REPO_ROOT / "scripts" / "work-bundle"):
        sys.path.pop(0)
    for module_name in ("project", "bootstrap_config", "core"):
        sys.modules.pop(module_name, None)


def _init_managed_text_files(project: Path) -> list[Path]:
    candidates = [
        project / ".gitignore",
        project / "AGENTS.md",
        project / ".work-bundle/project.yaml",
        project / ".work-bundle/knowledge/project.yaml",
        project / ".work-bundle/rules/index.yaml",
        project / ".work-bundle/.gitignore",
    ]
    candidates.extend(sorted(project.glob("roles/*.yaml")))
    return [path for path in candidates if path.is_file()]


def test_init_managed_text_files_track_current_rule_store(tmp_path: Path) -> None:
    project = tmp_path / "project"
    current_rule_index = project / ".work-bundle/rules/index.yaml"
    legacy_rule_index = project / "rules/index.yaml"
    current_rule_index.parent.mkdir(parents=True)
    legacy_rule_index.parent.mkdir(parents=True)
    current_rule_index.write_text("rules: []\n", encoding="utf-8")
    legacy_rule_index.write_text("rules: []\n", encoding="utf-8")

    managed_files = _init_managed_text_files(project)

    assert current_rule_index in managed_files
    assert legacy_rule_index not in managed_files


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


def test_init_project_creates_structure_without_git_actions_and_is_idempotent(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")

    init = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo")
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
    assert (project / ".work-bundle/rules/index.yaml").is_file()
    assert (project / ".work-bundle/rules/index.yaml").read_text(encoding="utf-8") == "rules: []\n"
    assert not (project / "rules/index.yaml").exists()
    assert init_data["git_actions"] == []
    assert init_data["transaction"]["state"] == "published"
    assert (project / "script/index.yaml").is_file()
    assert (project / "credentials/credentials.yaml").is_file()
    assert (project / "credentials").stat().st_mode & 0o777 == 0o700
    assert (project / "credentials/credentials.yaml").stat().st_mode & 0o777 == 0o600
    assert "credentials/" in (project / ".gitignore").read_text(encoding="utf-8").splitlines()
    metadata_text = (project / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "workspace_resources:" in metadata_text
    assert subprocess.run(["git", "-C", str(project), "rev-parse", "--verify", "HEAD"], check=False, capture_output=True).returncode != 0
    assert git(project, "diff", "--cached", "--name-only") == ""
    assert not (project / ".work-bundle/knowledge/.git").exists()

    validate = run_wb(config_root, "validate-project", str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    validate_data = json.loads(validate.stdout)
    assert validate_data["status"] == "passed"
    assert validate_data["rules_root_authority"] == ".work-bundle/rules"
    assert validate_data["rule_index"] is True
    assert validate_data["legacy_rule_index"] is False

    time.sleep(1.1)
    rerun = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo")
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert json.loads(rerun.stdout)["changed_files"] == []


def test_new_init_requires_explicit_mode_without_writes(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    head_before = subprocess.run(["git", "-C", str(project), "rev-parse", "--verify", "HEAD"], check=False, capture_output=True).returncode
    result = run_wb(config_root, "init-project", str(project), "--name", "demo")
    data = json.loads(result.stdout)
    assert result.returncode == 1
    assert data["failures"] == ["WB_WORKSPACE_MODE_REQUIRED"]
    assert data["changed_files"] == []
    assert not (project / ".work-bundle").exists()
    assert subprocess.run(["git", "-C", str(project), "rev-parse", "--verify", "HEAD"], check=False, capture_output=True).returncode == head_before
    assert git(project, "diff", "--cached", "--name-only") == ""


def test_metadata_v2_migration_requires_dry_run_then_explicit_apply(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    metadata_path.write_text(
        f"metadata_version: 2\nauthority: canonical\nproject_root: {project.resolve()}\ncustom_user_field: keep-me\n",
        encoding="utf-8",
    )
    before = metadata_path.read_bytes()
    missing_action = run_wb(config_root, "migrate-project", str(project), "--name", "demo")
    assert missing_action.returncode == 1
    assert json.loads(missing_action.stdout)["failures"] == ["WB_MIGRATION_EXPLICIT_ACTION_REQUIRED"]
    dry_run = run_wb(config_root, "migrate-project", str(project), "--dry-run", "--name", "demo")
    assert dry_run.returncode == 0
    assert metadata_path.read_bytes() == before
    proposal_id = json.loads(dry_run.stdout)["migration"]["proposal_id"]
    applied = run_wb(
        config_root,
        "migrate-project",
        str(project),
        "--apply",
        "--name",
        "demo",
        "--accepted-proposal-id",
        proposal_id,
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert "metadata_version: 3" in metadata_path.read_text(encoding="utf-8")
    assert "custom_user_field: keep-me" in metadata_path.read_text(encoding="utf-8")
    assert json.loads(applied.stdout)["git_actions"] == []


def test_metadata_v2_multi_source_routes_to_explicit_workspace_migration(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    extra = tmp_path / "library"
    extra.mkdir()
    git(extra, "init", "-q", "-b", "main")
    metadata = project / ".work-bundle/project.yaml"
    metadata.write_text(
        "\n".join(
            [
                "metadata_version: 2",
                "authority: canonical",
                f"project_root: {project.resolve()}",
                "source_repositories:",
                "  - id: demo-main",
                f"    path: {project.resolve()}",
                "  - id: demo-library",
                f"    path: {extra.resolve()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    registry = config_root / "registry/projects.yaml"
    registry.write_text(
        "\n".join(
            [
                "projects:",
                "  - slug: demo",
                "    name: demo",
                f"    work_bundle_root: {project.resolve() / '.work-bundle'}",
                f"    knowledge_root: {project.resolve() / '.work-bundle/knowledge'}",
                "    aliases: []",
                "    source_repositories:",
                "      - id: demo-main",
                f"        path: {project.resolve()}",
                "        git_repository: true",
                "      - id: demo-library",
                f"        path: {extra.resolve()}",
                "        git_repository: true",
                "    status: active",
                "    updated_at: 2026-08-11",
                "",
            ]
        ),
        encoding="utf-8",
    )
    metadata_before = metadata.read_bytes()
    registry_before = registry.read_bytes()

    result = run_wb(config_root, "migrate-project", str(project), "--dry-run", "--name", "demo")
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["mode"] == "multi-repository-migration-required"
    assert data["failures"] == ["WB_MIGRATION_MULTI_REPOSITORY_WORKFLOW_REQUIRED"]
    assert data["topology_assessment"]["required_command"] == "migrate-to-multi-repository"
    assert metadata.read_bytes() == metadata_before
    assert registry.read_bytes() == registry_before

    forced = run_wb(
        config_root,
        "migrate-project",
        str(project),
        "--apply",
        "--force",
        "--name",
        "demo",
        "--accepted-proposal-id",
        data["migration"]["proposal_id"],
    )
    assert forced.returncode == 1
    assert json.loads(forced.stdout)["failures"] == ["WB_MIGRATION_MULTI_REPOSITORY_WORKFLOW_REQUIRED"]
    assert metadata.read_bytes() == metadata_before
    assert registry.read_bytes() == registry_before


def test_metadata_v2_apply_rejects_stale_proposal(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata = project / ".work-bundle/project.yaml"
    metadata.write_text(
        f"metadata_version: 2\nauthority: canonical\nproject_root: {project.resolve()}\n",
        encoding="utf-8",
    )
    dry_run = run_wb(config_root, "migrate-project", str(project), "--dry-run", "--name", "demo")
    proposal_id = json.loads(dry_run.stdout)["migration"]["proposal_id"]
    metadata.write_text(metadata.read_text(encoding="utf-8") + "user_change: preserve\n", encoding="utf-8")

    applied = run_wb(
        config_root,
        "migrate-project",
        str(project),
        "--apply",
        "--name",
        "demo",
        "--accepted-proposal-id",
        proposal_id,
    )

    assert applied.returncode == 1
    assert json.loads(applied.stdout)["failures"] == ["WB_MIGRATION_PROPOSAL_STALE"]
    assert "user_change: preserve" in metadata.read_text(encoding="utf-8")


def test_metadata_v2_topology_identity_disagreement_blocks(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    conflicting = tmp_path / "conflicting"
    conflicting.mkdir()
    metadata = project / ".work-bundle/project.yaml"
    metadata.write_text(
        "\n".join(
            [
                "metadata_version: 2",
                f"project_root: {project.resolve()}",
                "source_repositories:",
                "  - id: demo-main",
                f"    path: {conflicting.resolve()}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_wb(config_root, "migrate-project", str(project), "--dry-run", "--name", "demo")
    data = json.loads(result.stdout)

    assert result.returncode == 1
    assert data["mode"] == "topology-conflict"
    assert data["failures"] == ["WB_MIGRATION_TOPOLOGY_CONFLICT"]
    assert data["changed_files"] == []


def test_doctor_repair_preserves_head_and_single_repository_resources(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    head_before = git(project, "rev-parse", "HEAD")
    staged_before = git(project, "diff", "--cached", "--name-only")
    script_before = (project / "script/index.yaml").read_bytes()
    credential_before = (project / "credentials/credentials.yaml").read_bytes()
    result = run_wb(config_root, "doctor-project", str(project), "--repair")
    data = json.loads(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert data["git_actions"] == []
    assert (project / "script/index.yaml").read_bytes() == script_before
    assert (project / "credentials/credentials.yaml").read_bytes() == credential_before
    assert git(project, "rev-parse", "HEAD") == head_before
    assert git(project, "diff", "--cached", "--name-only") == staged_before


def test_validate_single_repository_accepts_workspace_resource_directories(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    result = run_wb(config_root, "validate-project", str(project))
    data = json.loads(result.stdout)

    assert result.returncode == 0, result.stdout + result.stderr
    assert data["failures"] == []


def test_migrate_project_writes_report_without_breaking_validation(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "user.name", "Test")
    assert run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo").returncode == 0

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo")
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
    assert first_data["status"] in {"skipped", "updated"}
    entry = first_data["project"]
    assert entry["aliases"] == ["demo", "sample"]
    assert len(entry["source_repositories"]) == 1
    assert entry["source_repositories"][0]["path"] == str(resolved)

    text = registry_path.read_text(encoding="utf-8")
    assert "sample" in text
    assert "id: demo-main" in text
    assert "git_repository:" in text


def test_register_project_adds_repository_to_registry_and_project_metadata(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    extra_repo = tmp_path / "library"
    extra_repo.mkdir()
    git(extra_repo, "init", "-q", "-b", "main")
    git(extra_repo, "config", "user.email", "test@example.com")
    git(extra_repo, "config", "user.name", "Test")
    (extra_repo / "README.md").write_text("# Library\n", encoding="utf-8")
    git(extra_repo, "add", "README.md")
    git(extra_repo, "commit", "-m", "chore: seed library")

    registered = run_wb(config_root, "register-project", str(extra_repo), "--name", "demo")
    assert registered.returncode == 0, registered.stdout + registered.stderr
    data = json.loads(registered.stdout)

    assert data["status"] == "updated"
    assert data["project_metadata_status"] == "updated"
    assert data["source_repository_roles"]["registry"].startswith("Locator only")
    assert data["source_repository_roles"]["project_metadata"].startswith("Working-state authority")
    assert str(config_root / "registry/projects.yaml") in data["changed_files"]
    assert str(project / ".work-bundle/project.yaml") in data["changed_files"]
    assert [source["id"] for source in data["registry_entry"]["source_repositories"]] == ["demo-main", "demo-library"]

    registry_text = (config_root / "registry/projects.yaml").read_text(encoding="utf-8")
    assert "source_repository_roles:" in registry_text
    assert f"path: {extra_repo.resolve()}" in registry_text

    metadata_text = (project / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    wb_project = _import_wb_project()
    try:
        repositories = wb_project._metadata_source_repositories(metadata_text)
    finally:
        _cleanup_wb_project_modules()

    assert "source_repository_roles:" in metadata_text
    assert [repo["path"] for repo in repositories] == [str(project.resolve()), str(extra_repo.resolve())]
    assert repositories[1]["git_repository"] is True
    assert repositories[1]["working_branch"] == "main"
    assert repositories[1]["last_commit_id"] == git(extra_repo, "rev-parse", "HEAD")
    assert repositories[1]["codegraph"]["reason"] == "no-index"


def test_registry_upsert_replaces_aliases_when_explicit(tmp_path: Path, monkeypatch) -> None:
    config_root = bootstrap_config(tmp_path)
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config_root))
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
    (project / "README.md").write_text("# Fixture\n", encoding="utf-8")
    git(project, "add", "README.md")
    git(project, "commit", "-m", "chore: seed fixture")
    assert run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo").returncode == 0
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


def test_validate_project_uses_current_work_bundle_rules_without_root_rules(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    root_rules = project / "rules"
    if root_rules.exists():
        for path in sorted(root_rules.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        root_rules.rmdir()

    result = run_wb(config_root, "validate-project", str(project))
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "passed"
    assert data["rules_root"] is True
    assert data["rule_index"] is True
    assert data["rules_root_authority"] == ".work-bundle/rules"
    assert data["legacy_rules_root"] is False
    assert "rules_root" not in data["failures"]
    assert "rule_index" not in data["failures"]


def test_doctor_repair_does_not_restore_legacy_root_rule_index(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    legacy_rule_index = project / "rules/index.yaml"
    assert not legacy_rule_index.exists()

    repaired = run_wb(config_root, "doctor-project", str(project), "--repair")
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    data = json.loads(repaired.stdout)

    assert data["status"] == "passed"
    assert data["rule_index"] is True
    assert data["rules_root_authority"] == ".work-bundle/rules"
    assert data["legacy_rule_index"] is False
    assert not legacy_rule_index.exists()


def test_init_force_overwrites_init_managed_templates_only(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    agents_path = project / "AGENTS.md"
    custom_agents = "# Custom Agents\n"
    agents_path.write_text(custom_agents, encoding="utf-8")
    role_path = project / "roles" / "project-manager.yaml"
    custom_role = "id: project-manager\ncustom: true\n"
    role_path.write_text(custom_role, encoding="utf-8")

    without_force = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo")
    assert without_force.returncode == 0, without_force.stdout + without_force.stderr
    assert agents_path.read_text(encoding="utf-8").startswith(custom_agents.rstrip() + "\n\n")
    assert role_path.read_text(encoding="utf-8") == custom_role

    agents_path.write_text(custom_agents, encoding="utf-8")
    with_force = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo", "--force")
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

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo")
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
    assert "source_repository_roles:" in template_text
    assert "Locator authority in all versions" in template_text
    assert "metadata v4 device_bindings" in template_text
    assert "Metadata v4 portable project/topology authority" in template_text
    assert "metadata v3 working-state authority" in template_text
    assert "projects:" in template_text
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
                {
                    "id": "demo-main",
                    "path": "/tmp/project",
                    "checkout_role": "truth",
                    "work_dir": True,
                    "remote": "origin",
                    "git_repository": True,
                },
            ],
            "status": "active",
            "updated_at": "2026-06-11",
        }
        rendered = wb_project._render_projects([sample])
        assert rendered.startswith("source_repository_roles:\n")
        assert "\nprojects:\n" in rendered
        registry_file = tmp_path / "projects.yaml"
        registry_file.write_text(rendered, encoding="utf-8")
        parsed = wb_project._project_blocks(registry_file)
        assert len(parsed) == 1
        entry = parsed[0]
        for field in PROJECT_REGISTRY_ENTRY_FIELDS:
            assert field in entry
        for field in PROJECT_REGISTRY_SOURCE_FIELDS:
            assert field in entry["source_repositories"][0]
        assert entry["slug"] == sample["slug"]
        assert entry["aliases"] == sample["aliases"]
        assert entry["source_repositories"] == sample["source_repositories"]
        assert wb_project._registry_entries_equivalent(entry, sample)
    finally:
        _cleanup_wb_project_modules()


def test_project_blocks_do_not_absorb_device_bindings(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        rendered = (
            (REPO_ROOT / "tests/fixtures/registry-layout/registry/mixed-device-bindings.yaml")
            .read_text(encoding="utf-8")
            .replace("__SLUG_A__", "alpha")
            .replace("__ROOT_A__", "/tmp/alpha")
            .replace("__REPO_A__", "alpha-main")
            .replace("__REMOTE_A__", "/tmp/alpha.git")
            .replace("__SLUG_B__", "beta")
            .replace("__ROOT_B__", "/tmp/beta")
            .replace("__REPO_B__", "beta-main")
            .replace("__REMOTE_B__", "/tmp/beta.git")
        )
        registry_file = tmp_path / "projects.yaml"
        registry_file.write_text(rendered, encoding="utf-8")
        parsed = wb_project._project_blocks(registry_file)
        assert [entry["slug"] for entry in parsed] == ["alpha", "beta"]
        assert parsed[0]["work_bundle_root"] == "/tmp/alpha/.work-bundle"
        assert parsed[1]["work_bundle_root"] == "/tmp/beta/.work-bundle"
        assert parsed[1]["slug"] == "beta"
        assert parsed[0]["custom_entry_field"] == "keep-entry-a"
        line_parsed = wb_project._project_blocks_line_scoped(rendered)
        assert [entry["slug"] for entry in line_parsed] == ["alpha", "beta"]
        assert line_parsed[1]["slug"] == "beta"
        assert line_parsed[1]["work_bundle_root"] == "/tmp/beta/.work-bundle"
        assert "workspace_root" not in line_parsed[1]
    finally:
        _cleanup_wb_project_modules()


def test_registry_upsert_preserves_schema_bindings_and_unknown_top_level(tmp_path: Path, monkeypatch) -> None:
    config_root = bootstrap_config(tmp_path)
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config_root))
    project = tmp_path / "project"
    project.mkdir()
    resolved = project.resolve()
    registry_path = config_root / "registry" / "projects.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "registry_schema_version: 1",
                "source_repository_roles:",
                '  registry: "Locator authority in all versions."',
                '  project_metadata: "Working-state authority."',
                "custom_registry_field: keep-registry",
                "projects:",
                "  - slug: demo",
                "    name: demo",
                f"    work_bundle_root: {resolved / '.work-bundle'}",
                f"    knowledge_root: {resolved / '.work-bundle' / 'knowledge'}",
                "    aliases: []",
                "    custom_entry_field: keep-entry",
                "    source_repositories:",
                "      - id: demo-main",
                f"        path: {resolved}",
                "        checkout_role: truth",
                "        work_dir: true",
                '        remote: ""',
                "        git_repository: true",
                "    status: active",
                "    updated_at: 2026-01-01",
                "device_bindings:",
                "  wb-unrelated:",
                "    slug: unrelated-device",
                "    workspace_root: /tmp/unrelated-device",
                "    custom_binding_field: keep-unrelated",
                "    repositories: {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wb_project = _import_wb_project()
    try:
        entry, changed, _ = wb_project.upsert_project_registry(resolved, "demo", ["demo"])
        assert changed is True
        assert entry["aliases"] == ["demo"]
        text = registry_path.read_text(encoding="utf-8")
        assert text.startswith("registry_schema_version: 1\n")
        assert 'registry: "Locator authority in all versions."' in text
        assert 'project_metadata: "Working-state authority."' in text
        assert "custom_registry_field: keep-registry" in text
        assert "custom_entry_field:" in text
        assert "keep-entry" in text
        assert "wb-unrelated:" in text
        assert "custom_binding_field: keep-unrelated" in text
        assert "workspace_root: /tmp/unrelated-device" in text
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

    init = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo")
    assert init.returncode == 1, init.stdout + init.stderr
    data = json.loads(init.stdout)
    assert data["command"] == "init-project"
    assert data["status"] == "issues-found"
    assert data["failures"] == ["WB_REFERENCE_ASSET_MISSING"]
    assert data["missing_reference"].endswith("references/assets/template/project.yaml")


def test_healthy_reinit_reports_empty_changed_files(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    rerun = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo")
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

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo", "--force")
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

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo", "--force")
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

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo")
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


def test_migrate_project_preserves_legacy_root_rule_index_as_non_authority(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    legacy_rule_index = project / "rules/index.yaml"
    legacy_rule_index.parent.mkdir(parents=True, exist_ok=True)
    legacy_text = "id: legacy-root-rule-index\nrules: []\n"
    legacy_rule_index.write_text(legacy_text, encoding="utf-8")
    current_rule_index = project / ".work-bundle/rules/index.yaml"
    current_text = current_rule_index.read_text(encoding="utf-8")

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr

    assert legacy_rule_index.read_text(encoding="utf-8") == legacy_text
    assert current_rule_index.read_text(encoding="utf-8") == current_text

    validate = run_wb(config_root, "validate-project", str(project))
    assert validate.returncode == 0, validate.stdout + validate.stderr
    data = json.loads(validate.stdout)
    assert data["status"] == "passed"
    assert data["rules_root_authority"] == ".work-bundle/rules"
    assert data["legacy_rules_authority"] == "legacy-artifact"
    assert data["legacy_rule_index"] is True


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
    config_root, project = _init_fixture_project(tmp_path)
    metadata_version = ""
    for line in (project / ".work-bundle/project.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("metadata_version:"):
            metadata_version = line.split(":", 1)[1].strip()
            break
    assert metadata_version != "4"
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(config_root)
    env["WB_WORK_BUNDLE_ROOT"] = str(work_bundle_root)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), "show-project", "--project-root", str(project)],
        cwd=project,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert "path_model" in data
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


def test_project_metadata_v3_records_git_and_codegraph_state(tmp_path: Path) -> None:
    wb_project = _import_wb_project()
    try:
        project = tmp_path / "project"
        project.mkdir()
        git(project, "init", "-q", "-b", "main")
        git(project, "config", "user.email", "test@example.com")
        git(project, "config", "user.name", "Test")
        (project / "README.md").write_text("# Demo\n", encoding="utf-8")
        git(project, "add", "README.md")
        git(project, "commit", "-m", "chore: seed")
        head = git(project, "rev-parse", "HEAD")

        rendered = wb_project._render_project_metadata(project, "demo")
        metadata = wb_project._metadata_source_repositories(rendered)

        assert "metadata_version: 3" in rendered
        assert "workspace_mode: single-repository" in rendered
        assert "operation_policy:" in rendered
        assert metadata[0]["id"] == "demo-main"
        assert metadata[0]["git_repository"] is True
        assert metadata[0]["working_branch"] == "main"
        assert metadata[0]["last_commit_id"] == head
        assert metadata[0]["baseline_status"] == "current"
        assert metadata[0]["codegraph"]["status"] == "not-indexed"
        assert metadata[0]["codegraph"]["reason"] == "no-index"
    finally:
        _cleanup_wb_project_modules()


def test_validate_project_reports_metadata_branch_mismatch(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace("expected_branch: main", "expected_branch: wrong-branch"),
        encoding="utf-8",
    )

    result = run_wb(config_root, "validate-project", str(project))
    assert result.returncode == 1, result.stdout + result.stderr
    data = json.loads(result.stdout)

    assert data["status"] == "issues-found"
    assert "WB_PROJECT_METADATA_INVALID" in data["failures"]
    assert "source_repositories[0].branch_mismatch" in data["failures"]


def test_validate_project_reports_stale_metadata_baseline(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    current_head = git(project, "rev-parse", "HEAD")
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8")
        .replace("observed_head:", f"observed_head: {current_head}")
        .replace("baseline_status: unborn", "baseline_status: current"),
        encoding="utf-8",
    )
    git(project, "add", "-f", ".work-bundle/project.yaml")
    git(project, "commit", "-m", "chore: refresh metadata baseline")
    refreshed_head = git(project, "rev-parse", "HEAD")
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace(current_head, refreshed_head),
        encoding="utf-8",
    )
    (project / "README.md").write_text("# Later change\n", encoding="utf-8")
    git(project, "add", "README.md")
    git(project, "commit", "-m", "chore: later change")

    result = run_wb(config_root, "validate-project", str(project))
    assert result.returncode == 1, result.stdout + result.stderr
    data = json.loads(result.stdout)

    assert "WB_PROJECT_METADATA_INVALID" in data["failures"]
    assert "source_repositories[0].baseline_status_stale" in data["failures"]


def test_force_refresh_preserves_truth_and_development_checkouts(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    development = tmp_path / "project-development"
    development.mkdir()
    git(development, "init", "-q", "-b", "feature/demo")
    git(development, "config", "user.email", "test@example.com")
    git(development, "config", "user.name", "Test")
    (development / "README.md").write_text("# Development\n", encoding="utf-8")
    git(development, "add", "README.md")
    git(development, "commit", "-m", "chore: seed development")

    registry_path = config_root / "registry" / "projects.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "projects:",
                "  - slug: demo",
                "    name: demo",
                f"    work_bundle_root: {project.resolve() / '.work-bundle'}",
                f"    knowledge_root: {project.resolve() / '.work-bundle' / 'knowledge'}",
                "    aliases: []",
                "    source_repositories:",
                "      - id: demo-main",
                f"        path: {project.resolve()}",
                "        checkout_role: truth",
                "        work_dir: false",
                '        remote: ""',
                "        git_repository: true",
                "      - id: demo-development",
                f"        path: {development.resolve()}",
                "        checkout_role: development",
                "        work_dir: true",
                '        remote: ""',
                "        git_repository: true",
                "    status: active",
                "    updated_at: 2026-01-01",
                "",
            ]
        ),
        encoding="utf-8",
    )
    metadata_path = project / ".work-bundle/project.yaml"
    metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8").replace(
            "operation_policy:\n",
            "custom_user_field: keep-me\n\noperation_policy:\n",
        ),
        encoding="utf-8",
    )

    refreshed = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo", "--force")
    assert refreshed.returncode == 0, refreshed.stdout + refreshed.stderr
    metadata_text = metadata_path.read_text(encoding="utf-8")
    wb_project = _import_wb_project()
    try:
        repositories = wb_project._metadata_source_repositories(metadata_text)
    finally:
        _cleanup_wb_project_modules()

    assert [repo["id"] for repo in repositories] == ["demo-main", "demo-development"]
    assert [repo["checkout_role"] for repo in repositories] == ["truth", "development"]
    assert repositories[0]["working_branch"] == "main"
    assert repositories[1]["working_branch"] == "feature/demo"
    assert repositories[1]["last_commit_id"] == git(development, "rev-parse", "HEAD")
    assert "custom_user_field: keep-me" in metadata_text


def test_doctor_repair_refreshes_all_registered_checkout_baselines(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    recorded_head = git(project, "rev-parse", "HEAD")
    (project / "README.md").write_text("# Advanced\n", encoding="utf-8")
    git(project, "add", "README.md")
    git(project, "commit", "-m", "chore: advance truth branch")
    actual_head = git(project, "rev-parse", "HEAD")
    assert recorded_head != actual_head
    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata_lines = metadata_text.splitlines()
    baseline_index = next(index for index, line in enumerate(metadata_lines) if line.strip().startswith("observed_head:"))
    metadata_lines[baseline_index] = f"    observed_head: {'0' * 40}"
    metadata_path.write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")

    diagnosed = run_wb(config_root, "doctor-project", str(project))
    assert diagnosed.returncode == 1
    assert "source_repositories[0].baseline_status_stale" in json.loads(diagnosed.stdout)["failures"]

    repaired = run_wb(config_root, "doctor-project", str(project), "--repair")
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    repair_data = json.loads(repaired.stdout)
    assert str(metadata_path) in repair_data["changed_files"]
    repaired_baseline = repair_data["project_source_repositories"][0]["last_commit_id"]
    assert repaired_baseline != "0" * 40
    assert git(project, "merge-base", "--is-ancestor", repaired_baseline, git(project, "rev-parse", "HEAD")) == ""
    assert repair_data["project_source_repositories"][0]["checkout_role"] == "truth"


def test_migrate_project_upgrades_v1_metadata_and_preserves_unknown_fields(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    metadata_path = project / ".work-bundle/project.yaml"
    metadata_path.write_text(
        "\n".join(
            [
                "metadata_version: 1",
                "authority: canonical",
                f"project_root: {project.resolve()}",
                "industry: legacy",
                "custom_user_field: keep-me",
                "migration:",
                "  authority_owner: /wb-initialize-project",
                "",
            ]
        ),
        encoding="utf-8",
    )

    migrated = run_wb(config_root, "migrate-project", str(project), "--apply", "--name", "demo")
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    text = metadata_path.read_text(encoding="utf-8")

    assert "metadata_version: 3" in text
    assert "custom_user_field: keep-me" in text
    assert "operation_policy:" in text
    assert "source_repositories:" in text


def test_migrate_project_routes_registry_multi_source_to_workspace_migration(tmp_path: Path) -> None:
    config_root, project = _init_fixture_project(tmp_path)
    extra_repo = tmp_path / "library"
    extra_repo.mkdir()
    git(extra_repo, "init", "-q", "-b", "main")
    resolved_project = project.resolve()
    resolved_extra = extra_repo.resolve()
    registry_path = config_root / "registry" / "projects.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "projects:",
                "  - slug: demo",
                "    name: demo",
                f"    work_bundle_root: {resolved_project / '.work-bundle'}",
                f"    knowledge_root: {resolved_project / '.work-bundle' / 'knowledge'}",
                "    aliases: []",
                "    repository_origins:",
                "      - id: demo-main",
                f"        origin_path: {resolved_project}",
                "        git_repository: true",
                "      - id: demo-library",
                f"        origin_path: {resolved_extra}",
                "        git_repository: true",
                "    source_repositories:",
                "      - id: demo-main",
                f"        path: {resolved_project}",
                "        work_dir: true",
                '        remote: ""',
                "        git_repository: true",
                "    status: active",
                "    updated_at: 2026-01-01",
                "",
            ]
        ),
        encoding="utf-8",
    )
    metadata_path = project / ".work-bundle/project.yaml"
    metadata_path.write_text(
        "\n".join(
            [
                "metadata_version: 1",
                "authority: canonical",
                f"project_root: {resolved_project}",
                "industry: legacy",
                "",
            ]
        ),
        encoding="utf-8",
    )

    before = metadata_path.read_bytes()
    migrated = run_wb(config_root, "migrate-project", str(project), "--dry-run", "--name", "demo")
    data = json.loads(migrated.stdout)
    assert migrated.returncode == 1
    assert data["mode"] == "multi-repository-migration-required"
    assert data["topology_assessment"]["required_command"] == "migrate-to-multi-repository"
    assert metadata_path.read_bytes() == before


def _seed_committed_repository(path: Path) -> None:
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-q", "-m", "seed")


def _init_multi_workspace(tmp_path: Path) -> tuple[Path, Path]:
    config_root = bootstrap_config(tmp_path)
    workspace = tmp_path / "workspace"
    _seed_committed_repository(workspace)
    initialized = run_wb(
        config_root,
        "init-project",
        str(workspace),
        "--mode",
        "multi-repository",
        "--workspace-root",
        str(workspace),
        "--name",
        "multi",
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    assert (workspace / "script/index.yaml").is_file()
    assert (workspace / "credentials/credentials.yaml").is_file()
    assert "workspace_resources:" in (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    return config_root, workspace


def test_provision_member_cli_publishes_both_authorities_and_replays_idempotently(tmp_path: Path) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    origin = tmp_path / "origin"
    _seed_committed_repository(origin)
    args = (
        "provision-member",
        "--workspace-root",
        str(workspace),
        "--workspace-slug",
        "multi",
        "--origin",
        str(origin),
        "--repository-id",
        "repo-two",
        "--working-branch",
        "feature-two",
        "--base-ref",
        "HEAD",
    )
    proposed = run_wb(config_root, *args, "--dry-run")
    assert proposed.returncode == 0
    assert json.loads(proposed.stdout)["status"] == "proposed"

    metadata = workspace / ".work-bundle/project.yaml"
    registry = config_root / "registry/projects.yaml"
    metadata.write_text(metadata.read_text(encoding="utf-8") + "custom_workspace_field: keep\n", encoding="utf-8")
    registry.write_text(
        registry.read_text(encoding="utf-8").replace("    status: active", "    custom_locator_field: keep\n    status: active", 1),
        encoding="utf-8",
    )
    credential = workspace / "credentials/credentials.yaml"
    credential_stat = (credential.stat().st_mode, credential.stat().st_mtime_ns, credential.stat().st_size)
    origin_head = git(origin, "rev-parse", "HEAD")
    origin_status = git(origin, "status", "--short")

    applied = run_wb(config_root, *args, "--apply")
    data = json.loads(applied.stdout)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert data["status"] == "passed"
    assert data["transaction"]["state"] == "published"
    assert data["transaction"]["metadata_status"] == "published"
    assert data["transaction"]["registry_status"] == "published"
    assert "pending" not in json.dumps(data)
    assert '  - id: "repo-two"\n    project_root:' in metadata.read_text(encoding="utf-8")
    assert "custom_workspace_field: keep" in metadata.read_text(encoding="utf-8")
    assert "repository_origins:" in registry.read_text(encoding="utf-8")
    assert '      - id: "repo-two"' in registry.read_text(encoding="utf-8")
    assert "custom_locator_field: keep" in registry.read_text(encoding="utf-8")
    assert (credential.stat().st_mode, credential.stat().st_mtime_ns, credential.stat().st_size) == credential_stat
    assert git(origin, "rev-parse", "HEAD") == origin_head
    assert git(origin, "status", "--short") == origin_status
    shown = run_wb(config_root, "show-project", "--project-root", str(workspace))
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert {item["id"] for item in json.loads(shown.stdout)["project_source_repositories"]} >= {"repo-two"}
    nested_session = run_wb(
        config_root, "session-start", "--project-root", str(workspace / "repo-two"),
        "--dry-run", "--json",
    )
    assert nested_session.returncode == 0, nested_session.stdout + nested_session.stderr
    assert json.loads(nested_session.stdout)["project_root"] == str(workspace.resolve())
    validated = run_wb(config_root, "validate-project", str(workspace), "--dry-run")
    assert validated.returncode == 0, validated.stdout + validated.stderr

    metadata_bytes = metadata.read_bytes()
    registry_bytes = registry.read_bytes()
    record = workspace / ".work-bundle/transactions/provision-repo-two.json"
    record_bytes = record.read_bytes()
    mtimes = (metadata.stat().st_mtime_ns, registry.stat().st_mtime_ns, record.stat().st_mtime_ns)
    replayed = run_wb(config_root, *args, "--apply")
    replay_data = json.loads(replayed.stdout)
    assert replayed.returncode == 0
    assert replay_data["idempotent"] is True
    assert replay_data["changed_files"] == []
    assert metadata.read_bytes() == metadata_bytes
    assert registry.read_bytes() == registry_bytes
    assert record.read_bytes() == record_bytes
    assert (metadata.stat().st_mtime_ns, registry.stat().st_mtime_ns, record.stat().st_mtime_ns) == mtimes

    record.unlink()
    metadata_mtime = metadata.stat().st_mtime_ns
    registry_mtime = registry.stat().st_mtime_ns
    converged = run_wb(config_root, *args, "--apply")
    converged_data = json.loads(converged.stdout)
    assert converged.returncode == 0, converged.stdout + converged.stderr
    assert converged_data["idempotent"] is True
    assert converged_data["transaction"]["resume_source"] == "converged-authorities"
    assert converged_data["changed_files"] == []
    assert not record.exists()
    assert metadata.stat().st_mtime_ns == metadata_mtime
    assert registry.stat().st_mtime_ns == registry_mtime


def test_provision_member_cli_rejects_unrelated_non_empty_target(tmp_path: Path) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    origin = tmp_path / "origin"
    _seed_committed_repository(origin)
    target = workspace / "repo-two"
    target.mkdir()
    (target / "user-file").write_text("preserve\n", encoding="utf-8")

    applied = run_wb(
        config_root,
        "provision-member",
        "--workspace-root",
        str(workspace),
        "--workspace-slug",
        "multi",
        "--origin",
        str(origin),
        "--repository-id",
        "repo-two",
        "--working-branch",
        "feature-two",
        "--apply",
    )

    assert applied.returncode == 1
    assert json.loads(applied.stdout)["failure_code"] == "WB_WORKTREE_TARGET_COLLISION"
    assert (target / "user-file").read_text(encoding="utf-8") == "preserve\n"
    assert not (workspace / ".work-bundle/git/repo-two.git").exists()


def test_provision_member_adopts_exact_verified_orphan_without_recovery_record(tmp_path: Path) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    origin = tmp_path / "origin"
    _seed_committed_repository(origin)
    script_root = REPO_ROOT / "scripts/work-bundle"
    sys.path.insert(0, str(script_root))
    try:
        import worktree  # type: ignore[import-not-found]

        worktree.provision_member(workspace, origin, "repo-two", "feature-two")
    finally:
        sys.path.remove(str(script_root))
        for module_name in ("worktree", "workspace"):
            sys.modules.pop(module_name, None)
    record = workspace / ".work-bundle/transactions/provision-repo-two.json"
    assert not record.exists()
    args = (
        "provision-member", "--workspace-root", str(workspace),
        "--workspace-slug", "multi", "--origin", str(origin),
        "--repository-id", "repo-two", "--working-branch", "feature-two",
        "--base-ref", "HEAD",
    )
    proposed = run_wb(config_root, *args, "--dry-run")
    proposal_data = json.loads(proposed.stdout)
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    assert proposal_data["transaction"]["state"] == "verified"
    assert proposal_data["transaction"]["resume_source"] == "verified-orphan"
    applied = run_wb(config_root, *args, "--apply")
    data = json.loads(applied.stdout)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert data["status"] == "passed"
    assert data["transaction"]["state"] == "published"
    assert '  - id: "repo-two"' in (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")


def test_cleanup_member_command_removes_only_recorded_unpublished_owned_checkout(tmp_path: Path) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    origin = tmp_path / "origin"
    _seed_committed_repository(origin)
    script_root = REPO_ROOT / "scripts/work-bundle"
    sys.path.insert(0, str(script_root))
    try:
        import member  # type: ignore[import-not-found]
        import worktree  # type: ignore[import-not-found]

        provisioned = worktree.provision_member(workspace, origin, "repo-two", "feature-two")
        transaction_id = member._transaction_id(workspace, origin, "repo-two", "feature-two", "HEAD")
        context = {
            "transaction_id": transaction_id,
            "workspace_root": str(workspace.resolve()),
            "workspace_slug": "multi",
            "origin": str(origin.resolve()),
            "repository_id": "repo-two",
            "branch": "feature-two",
            "base_ref": "HEAD",
        }
        member._write_record(member._record_path(workspace, "repo-two"), {
            "id": transaction_id, "state": "verified", "context": context,
            "checkout_owned": True, "registry_status": "unchanged",
            "metadata_status": "unchanged", "member": member._member_result(provisioned, transaction_id),
        })
    finally:
        sys.path.remove(str(script_root))
        for module_name in ("member", "migration", "worktree", "workspace", "project", "core", "bootstrap_config"):
            sys.modules.pop(module_name, None)
    dry_run = run_wb(
        config_root, "cleanup-member", "--workspace-root", str(workspace),
        "--repository-id", "repo-two", "--dry-run",
    )
    assert dry_run.returncode == 0
    assert (workspace / "repo-two").is_dir()
    applied = run_wb(
        config_root, "cleanup-member", "--workspace-root", str(workspace),
        "--repository-id", "repo-two", "--apply",
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert not (workspace / "repo-two").exists()
    assert not (workspace / ".work-bundle/git/repo-two.git").exists()
    record = json.loads((workspace / ".work-bundle/transactions/provision-repo-two.json").read_text(encoding="utf-8"))
    assert record["state"] == "cleaned"


def test_show_project_accepts_workspace_root_alias(tmp_path: Path) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    shown = run_wb(config_root, "show-project", "--workspace-root", str(workspace))
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert json.loads(shown.stdout)["project_root"] == str(workspace.resolve())


def test_migrate_to_multi_repository_cli_dry_run_accepts_external_origin(tmp_path: Path) -> None:
    config_root = bootstrap_config(tmp_path)
    authority = tmp_path / "authority"
    origin = tmp_path / "origin"
    target = tmp_path / "workspace"
    authority.mkdir()
    (authority / ".work-bundle").mkdir()
    (authority / ".work-bundle/project.yaml").write_text(
        "metadata_version: 2\nauthority: canonical\n", encoding="utf-8"
    )
    _seed_committed_repository(origin)
    proposed = run_wb(
        config_root,
        "migrate-to-multi-repository", str(authority),
        "--target-workspace-root", str(target),
        "--origin", str(origin),
        "--repository-id", "repo-one",
        "--repository-name", "Repository One",
        "--workspace-slug", "workspace-one",
        "--working-branch", "feature/workspace",
        "--base-ref", "HEAD",
        "--dry-run",
    )
    data = json.loads(proposed.stdout)
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    assert data["status"] == "passed"
    assert data["result"]["member_origin_root"] == str(origin.resolve())
    assert data["result"]["changed_files"] == []
    missing_origin = run_wb(
        config_root,
        "migrate-to-multi-repository", str(authority),
        "--target-workspace-root", str(target),
        "--repository-id", "repo-one",
        "--repository-name", "Repository One",
        "--workspace-slug", "workspace-one",
        "--working-branch", "feature/workspace",
        "--dry-run",
    )
    assert missing_origin.returncode == 1
    assert json.loads(missing_origin.stdout)["failure_code"] == "WB_MIGRATION_ORIGIN_REQUIRED"


@pytest.mark.parametrize("stage", ["metadata-publication", "registry-publication"])
def test_provision_member_publication_failure_restores_authorities_and_owned_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    origin = tmp_path / "origin"
    _seed_committed_repository(origin)
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config_root))
    script_root = REPO_ROOT / "scripts/work-bundle"
    sys.path.insert(0, str(script_root))
    try:
        import member  # type: ignore[import-not-found]

        metadata = workspace / ".work-bundle/project.yaml"
        registry = config_root / "registry/projects.yaml"
        metadata_before = metadata.read_bytes()
        registry_before = registry.read_bytes()
        with pytest.raises(member.MemberLifecycleError):
            member.provision_member_lifecycle(
                workspace,
                origin,
                "repo-two",
                "feature-two",
                workspace_slug="multi",
                fail_stage=stage,
            )
        assert metadata.read_bytes() == metadata_before
        assert registry.read_bytes() == registry_before
        assert not (workspace / "repo-two").exists()
        assert not (workspace / ".work-bundle/git/repo-two.git").exists()
        record = workspace / ".work-bundle/transactions/provision-repo-two.json"
        assert json.loads(record.read_text(encoding="utf-8"))["state"] == "failed"
    finally:
        sys.path.remove(str(script_root))
        for module_name in ("member", "migration", "worktree", "project", "core", "bootstrap_config"):
            sys.modules.pop(module_name, None)


def test_provision_member_resumes_matching_verified_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_root, workspace = _init_multi_workspace(tmp_path)
    origin = tmp_path / "origin"
    _seed_committed_repository(origin)
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config_root))
    script_root = REPO_ROOT / "scripts/work-bundle"
    sys.path.insert(0, str(script_root))
    try:
        import member  # type: ignore[import-not-found]
        import worktree  # type: ignore[import-not-found]

        provisioned = worktree.provision_member(workspace, origin, "repo-two", "feature-two")
        transaction_id = member._transaction_id(workspace, origin, "repo-two", "feature-two", "HEAD")
        context = {
            "transaction_id": transaction_id,
            "workspace_root": str(workspace.resolve()),
            "workspace_slug": "multi",
            "origin": str(origin.resolve()),
            "repository_id": "repo-two",
            "branch": "feature-two",
            "base_ref": "HEAD",
        }
        member._write_record(
            member._record_path(workspace, "repo-two"),
            {
                "id": transaction_id,
                "state": "verified",
                "context": context,
                "checkout_owned": True,
                "registry_status": "unchanged",
                "metadata_status": "unchanged",
                "member": member._member_result(provisioned, transaction_id),
            },
        )
    finally:
        sys.path.remove(str(script_root))
        for module_name in ("member", "migration", "worktree", "project", "core", "bootstrap_config"):
            sys.modules.pop(module_name, None)

    resumed = run_wb(
        config_root,
        "provision-member",
        "--workspace-root",
        str(workspace),
        "--workspace-slug",
        "multi",
        "--origin",
        str(origin),
        "--repository-id",
        "repo-two",
        "--working-branch",
        "feature-two",
        "--base-ref",
        "HEAD",
        "--apply",
    )
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert json.loads(resumed.stdout)["transaction"]["state"] == "published"


def test_resolve_effective_prefer_subagent_uses_project_global_default_order(tmp_path: Path, monkeypatch) -> None:
    script_root = REPO_ROOT / "scripts" / "work-bundle"
    module = sys.modules.get("core")
    module_file = Path(getattr(module, "__file__", "")) if module is not None else None
    if module_file is not None and script_root not in module_file.parents:
        sys.modules.pop("core", None)
    sys.path.insert(0, str(script_root))
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

    rerun = run_wb(config_root, "init-project", str(project), "--mode", "single-repository", "--name", "demo")
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
