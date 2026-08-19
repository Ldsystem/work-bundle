from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests/fixtures/registry-layout"
_WB_SCRIPTS = str(REPO_ROOT / "scripts/work-bundle")
if _WB_SCRIPTS in sys.path:
    sys.path.remove(_WB_SCRIPTS)
sys.path.insert(0, _WB_SCRIPTS)
_core = sys.modules.get("core")
if _core is not None and "orchestration" in str(getattr(_core, "__file__", "")):
    del sys.modules["core"]
    for name in list(sys.modules):
        if name in {"registry_layout", "project", "control_plane"} or name.startswith("registry_layout."):
            del sys.modules[name]

from registry_layout import (  # noqa: E402
    apply_layout_step,
    load_migration_catalog,
    migrate_registered_projects,
    migration_path,
    validate_layout_version,
)


def run_wb(config_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "WB_CONFIG_ROOT": str(config_root),
            "WB_WORK_BUNDLE_ROOT": str(REPO_ROOT),
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
    )
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), *args],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def render_fixture(path: Path, **replacements: str) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"__{key}__", value)
    return text


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
                "prefer_subagent: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (config / "registry/skill-registry.yaml").write_text("skills: []\n", encoding="utf-8")
    return config


def git_workspace(path: Path, remote: Path) -> str:
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    (path / "README.md").write_text(f"# {path.name}\n", encoding="utf-8")
    (path / ".gitignore").write_text(".work-bundle/\nAGENTS.md\ncredentials/\n", encoding="utf-8")
    git(path, "add", "README.md", ".gitignore")
    git(path, "commit", "-q", "-m", "init")
    git(path, "remote", "add", "origin", str(remote))
    git(path, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    return git(path, "rev-parse", "HEAD")


def install_layout(workspace: Path, layout: str, **replacements: str) -> None:
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    (workspace / ".work-bundle/knowledge/notes").mkdir(parents=True, exist_ok=True)
    metadata.write_text(
        render_fixture(FIXTURES / "layouts" / layout, **replacements),
        encoding="utf-8",
    )


def project_block(slug: str, workspace: Path, repo_id: str, remote: str, extra: str = "") -> str:
    rendered = render_fixture(
        FIXTURES / "registry/unversioned.yaml",
        SLUG=slug,
        NAME=slug,
        WORKSPACE_ROOT=str(workspace),
        REPO_ID=repo_id,
        REMOTE=remote,
    )
    start = rendered.index("  - slug:")
    end = rendered.index("device_bindings:")
    block = rendered[start:end].rstrip()
    if extra:
        block += "\n" + extra
    return block


def write_registry(config: Path, blocks: list[str], *, schema: str | None = None) -> Path:
    lines = []
    if schema is not None:
        lines.append(f"registry_schema_version: {schema}")
    lines.extend(
        [
            "source_repository_roles:",
            '  registry: "Locator authority in all versions."',
            '  project_metadata: "Working-state or portable topology depending on layout version."',
            "custom_registry_field: keep-registry",
            "projects:",
        ]
    )
    for block in sorted(blocks):
        lines.append(block.rstrip())
    lines.append("device_bindings: {}")
    path = config / "registry/projects.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def prepare_workspace(
    tmp_path: Path, name: str, layout: str, *, slug: str | None = None
) -> tuple[Path, Path, str, str]:
    workspace = tmp_path / name
    remote = tmp_path / f"{name}.git"
    head = git_workspace(workspace, remote)
    repo_id = f"{name}-main"
    workspace_slug = slug or name
    install_layout(
        workspace,
        layout,
        WORKSPACE_ROOT=str(workspace),
        REPO_ID=repo_id,
        HEAD=head,
        REMOTE=str(remote),
        SLUG=workspace_slug,
        WORKSPACE_ID=f"wb-{workspace_slug}",
    )
    return workspace, remote, head, repo_id


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)


def test_catalog_registers_explicit_version_to_version_steps() -> None:
    catalog = load_migration_catalog(REPO_ROOT)
    assert catalog.layout_current == "4"
    assert catalog.registry_schema_current == "1"
    assert [step.step_id for step in catalog.steps] == ["layout-v2-to-v3", "layout-v3-to-v4"]
    path = migration_path("2", catalog)
    assert path is not None
    assert [(step.from_version, step.to_version) for step in path] == [("2", "3"), ("3", "4")]
    assert migration_path("4", catalog) == []
    assert migration_path("9", catalog) is None


def test_already_current_registry_entry_is_noop(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "current-project", "v4-single.yaml")
    registry = write_registry(
        config,
        [project_block("current-project", workspace, repo_id, str(remote), extra="    layout_version: 4")],
        schema="1",
    )
    before_registry = registry.read_bytes()
    before_metadata = (workspace / ".work-bundle/project.yaml").read_bytes()

    first = run_wb(config, "migrate-registered-projects", "--dry-run")
    second = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert first.returncode == second.returncode == 0, first.stdout + first.stderr
    data = payload(first)
    assert data["projects"][0]["classification"] == "current"
    assert data["projects"][0]["registry_layout_status"] == "current"
    assert data["projects"][0]["steps"] == []
    assert data["plan_id"] == payload(second)["plan_id"]

    applied = run_wb(
        config,
        "migrate-registered-projects",
        "--apply",
        "--accepted-plan-id",
        str(data["plan_id"]),
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    result = payload(applied)
    assert result["status"] == "passed"
    assert result["results"][0]["status"] == "noop"
    assert result["changed_files"] == []
    assert registry.read_bytes() == before_registry
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == before_metadata


def test_populated_device_bindings_do_not_reassign_project_roots(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    alpha, alpha_remote, _, alpha_repo = prepare_workspace(tmp_path, "alpha", "v3-single.yaml")
    beta, beta_remote, _, beta_repo = prepare_workspace(tmp_path, "beta", "v4-single.yaml")
    registry = config / "registry/projects.yaml"
    registry.write_text(
        render_fixture(
            FIXTURES / "registry/mixed-device-bindings.yaml",
            SLUG_A="alpha",
            ROOT_A=str(alpha),
            REPO_A=alpha_repo,
            REMOTE_A=str(alpha_remote),
            SLUG_B="beta",
            ROOT_B=str(beta),
            REPO_B=beta_repo,
            REMOTE_B=str(beta_remote),
        ),
        encoding="utf-8",
    )
    before = registry.read_text(encoding="utf-8")
    assert before.index("wb-beta:") < before.index("wb-unrelated:") < before.index("wb-alpha:")

    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = payload(proposed)
    assert [item["slug"] for item in data["projects"]] == ["alpha", "beta"]
    by_slug = {item["slug"]: item for item in data["projects"]}
    assert by_slug["alpha"]["workspace_root"] == str(alpha.resolve())
    assert by_slug["beta"]["workspace_root"] == str(beta.resolve())
    assert by_slug["alpha"]["classification"] == "migratable"
    assert by_slug["beta"]["classification"] == "current"
    assert registry.read_text(encoding="utf-8") == before

    applied = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(data["plan_id"])
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    results = {item["slug"]: item for item in payload(applied)["results"]}
    assert results["alpha"]["status"] == "passed"
    assert results["beta"]["status"] in {"noop", "reconciled"}
    after = registry.read_text(encoding="utf-8")
    assert "custom_registry_field: keep-registry" in after
    assert "custom_entry_field: keep-entry-a" in after
    assert "custom_entry_field: keep-entry-b" in after
    assert after.index("projects:") < after.index("device_bindings:")
    unrelated_start = after.index("wb-unrelated:")
    next_binding = after.find("\n  wb-", unrelated_start + 1)
    unrelated_block = after[unrelated_start: next_binding if next_binding != -1 else None]
    assert "slug: unrelated-device" in unrelated_block
    assert "workspace_root: /tmp/unrelated-device" in unrelated_block
    assert "custom_binding_field: keep-unrelated" in unrelated_block
    assert "metadata_version: 4" in (alpha / ".work-bundle/project.yaml").read_text(encoding="utf-8")


def test_v4_missing_and_stale_layout_version_are_reconciled(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    missing, missing_remote, _, missing_repo = prepare_workspace(tmp_path, "missing-layout", "v4-single.yaml")
    stale, stale_remote, _, stale_repo = prepare_workspace(tmp_path, "stale-layout", "v4-single.yaml")
    registry = write_registry(
        config,
        [
            project_block("missing-layout", missing, missing_repo, str(missing_remote)),
            project_block(
                "stale-layout",
                stale,
                stale_repo,
                str(stale_remote),
                extra="    layout_version: 3",
            ),
        ],
        schema="1",
    )
    before = registry.read_text(encoding="utf-8")
    assert "layout_version: 4" not in before

    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = payload(proposed)
    by_slug = {item["slug"]: item for item in data["projects"]}
    assert by_slug["missing-layout"]["classification"] == "current"
    assert by_slug["missing-layout"]["registry_layout_status"] == "missing"
    assert by_slug["stale-layout"]["classification"] == "current"
    assert by_slug["stale-layout"]["registry_layout_status"] == "stale"

    applied = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(data["plan_id"])
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    results = {item["slug"]: item for item in payload(applied)["results"]}
    assert results["missing-layout"]["status"] == "reconciled"
    assert results["stale-layout"]["status"] == "reconciled"
    after = registry.read_text(encoding="utf-8")
    assert after.count("layout_version: 4") == 2
    assert "layout_version: 3" not in after
    assert "custom_registry_field: keep-registry" in after
    assert "custom_entry_field: keep-entry" in after
    assert (missing / ".work-bundle/project.yaml").read_text(encoding="utf-8").count("metadata_version: 4")
    assert (stale / ".work-bundle/project.yaml").read_text(encoding="utf-8").count("metadata_version: 4")


def test_one_version_upgrade_v3_to_v4(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "stale-v3", "v3-single.yaml")
    registry = write_registry(config, [project_block("stale-v3", workspace, repo_id, str(remote))])
    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = payload(proposed)
    project = data["projects"][0]
    assert project["classification"] == "migratable"
    assert project["layout_version"] == "3"
    assert [step["id"] for step in project["steps"]] == ["layout-v3-to-v4"]

    applied = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(data["plan_id"])
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "metadata_version: 4" in metadata
    assert "custom_portable:" in metadata
    registry_text = registry.read_text(encoding="utf-8")
    assert "layout_version: 4" in registry_text
    assert "custom_registry_field: keep-registry" in registry_text
    assert "custom_entry_field: keep-entry" in registry_text
    assert "registry_schema_version: 1" in registry_text


def test_multi_version_sequential_upgrade_v2_to_v4(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "legacy-v2", "v2-project.yaml")
    write_registry(config, [project_block("legacy-v2", workspace, repo_id, str(remote))])
    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = payload(proposed)
    project = data["projects"][0]
    assert project["classification"] == "migratable"
    assert [step["id"] for step in project["steps"]] == ["layout-v2-to-v3", "layout-v3-to-v4"]
    assert [step["from_version"] for step in project["steps"]] == ["2", "3"]

    applied = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(data["plan_id"])
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "metadata_version: 4" in metadata
    assert "custom_user_field: keep-me" in metadata
    assert "user_note: preserve-across-layout-migration" in metadata
    assert "layout_version: 4" in (config / "registry/projects.yaml").read_text(encoding="utf-8")


def test_mixed_registry_current_and_stale(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    current, current_remote, _, current_repo = prepare_workspace(tmp_path, "alpha", "v4-single.yaml")
    stale, stale_remote, _, stale_repo = prepare_workspace(tmp_path, "beta", "v3-single.yaml")
    write_registry(
        config,
        [
            project_block("alpha", current, current_repo, str(current_remote), extra="    layout_version: 4"),
            project_block("beta", stale, stale_repo, str(stale_remote)),
        ],
    )
    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = payload(proposed)
    slugs = [item["slug"] for item in data["projects"]]
    assert slugs == ["alpha", "beta"]
    by_slug = {item["slug"]: item for item in data["projects"]}
    assert by_slug["alpha"]["classification"] == "current"
    assert by_slug["beta"]["classification"] == "migratable"
    assert [step["id"] for step in by_slug["beta"]["steps"]] == ["layout-v3-to-v4"]

    applied = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(data["plan_id"])
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    results = {item["slug"]: item for item in payload(applied)["results"]}
    assert results["alpha"]["status"] == "noop"
    assert results["beta"]["status"] == "passed"
    assert "metadata_version: 4" in (stale / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "metadata_version: 4" in (current / ".work-bundle/project.yaml").read_text(encoding="utf-8")


def test_missing_registered_workspace(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    missing = tmp_path / "gone"
    write_registry(
        config,
        [project_block("gone", missing, "gone-main", "/tmp/gone.git")],
    )
    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    project = payload(proposed)["projects"][0]
    assert project["classification"] == "missing"
    assert project["failure_code"] == "WB_REGISTRY_LAYOUT_MISSING_WORKSPACE"


def test_unsupported_unknown_version(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "ancient", "v2-project.yaml")
    (workspace / ".work-bundle/project.yaml").write_text(
        "metadata_version: 9\nauthority: canonical\n",
        encoding="utf-8",
    )
    write_registry(config, [project_block("ancient", workspace, repo_id, str(remote))])
    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    project = payload(proposed)["projects"][0]
    assert project["classification"] == "unsupported"
    assert project["failure_code"] == "WB_REGISTRY_LAYOUT_UNSUPPORTED_VERSION"

    schema = bootstrap_config(tmp_path / "schema")
    write_registry(
        schema,
        [project_block("ancient", workspace, repo_id, str(remote))],
        schema="99",
    )
    blocked = run_wb(schema, "migrate-registered-projects", "--dry-run")
    assert blocked.returncode == 1
    assert payload(blocked)["failure_code"] == "WB_REGISTRY_SCHEMA_UNSUPPORTED"


def test_blocked_multi_repository_v2(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "blocked", "v2-project.yaml")
    extra = tmp_path / "library"
    extra.mkdir()
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(
        metadata.read_text(encoding="utf-8")
        + "\n".join(
            [
                "source_repositories:",
                f"  - id: {repo_id}",
                f"    path: {workspace}",
                "  - id: library",
                f"    path: {extra}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_registry(config, [project_block("blocked", workspace, repo_id, str(remote))])
    proposed = run_wb(config, "migrate-registered-projects", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    project = payload(proposed)["projects"][0]
    assert project["classification"] == "blocked"
    assert project["failure_code"] == "WB_MIGRATION_MULTI_REPOSITORY_WORKFLOW_REQUIRED"


def test_validation_failure_after_transformation_restores_state(tmp_path: Path, monkeypatch) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "validate-fail", "v3-single.yaml")
    registry = write_registry(config, [project_block("validate-fail", workspace, repo_id, str(remote))])
    before_registry = registry.read_bytes()
    before_metadata = (workspace / ".work-bundle/project.yaml").read_bytes()
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config))
    monkeypatch.setenv("WB_WORK_BUNDLE_ROOT", str(REPO_ROOT))

    def failing_validate(root: Path, version: str) -> list[str]:
        if version == "4":
            return ["WB_REGISTRY_LAYOUT_INJECTED_VALIDATION"]
        return validate_layout_version(root, version)

    result = migrate_registered_projects(
        dry_run=False,
        apply=True,
        accepted_plan_id=migrate_registered_projects(dry_run=True, apply=False)["plan_id"],
        validate=failing_validate,
    )
    assert result["status"] == "issues-found"
    diagnostic = result["diagnostics"][0]
    assert diagnostic["slug"] == "validate-fail"
    assert diagnostic["from_version"] == "3"
    assert diagnostic["to_version"] == "4"
    assert diagnostic["failed_step"] == "layout-v3-to-v4"
    assert diagnostic["failure_code"] == "WB_REGISTRY_LAYOUT_VALIDATION_FAILED"
    assert registry.read_bytes() == before_registry
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == before_metadata
    assert "layout_version: 4" not in registry.read_text(encoding="utf-8")


def test_intermediate_step_failure_restores_pre_migration_state(tmp_path: Path, monkeypatch) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "mid-fail", "v2-project.yaml")
    registry = write_registry(config, [project_block("mid-fail", workspace, repo_id, str(remote))])
    before_registry = registry.read_bytes()
    before_metadata = (workspace / ".work-bundle/project.yaml").read_bytes()
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config))
    monkeypatch.setenv("WB_WORK_BUNDLE_ROOT", str(REPO_ROOT))

    def fail_v4(step, root, entry):
        if step.step_id == "layout-v3-to-v4":
            return {
                "status": "failed",
                "failures": ["WB_REGISTRY_LAYOUT_INJECTED_STEP_FAILURE"],
                "changed_files": [],
            }
        return apply_layout_step(step, root, entry)

    plan = migrate_registered_projects(dry_run=True, apply=False)
    result = migrate_registered_projects(
        dry_run=False,
        apply=True,
        accepted_plan_id=str(plan["plan_id"]),
        apply_step=fail_v4,
    )
    assert result["status"] == "issues-found"
    diagnostic = result["diagnostics"][0]
    assert diagnostic["failed_step"] == "layout-v3-to-v4"
    assert diagnostic["from_version"] == "2"
    assert diagnostic["to_version"] == "4"
    assert diagnostic["failure_code"] == "WB_REGISTRY_LAYOUT_INJECTED_STEP_FAILURE"
    assert registry.read_bytes() == before_registry
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == before_metadata
    assert "metadata_version: 2" in before_metadata.decode("utf-8")


def test_idempotent_rerun_after_success(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "rerun", "v3-single.yaml")
    write_registry(config, [project_block("rerun", workspace, repo_id, str(remote))])
    first_plan = payload(run_wb(config, "migrate-registered-projects", "--dry-run"))
    first = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(first_plan["plan_id"])
    )
    assert first.returncode == 0, first.stdout + first.stderr
    metadata_after = (workspace / ".work-bundle/project.yaml").read_bytes()
    registry_after = (config / "registry/projects.yaml").read_bytes()

    second_plan = payload(run_wb(config, "migrate-registered-projects", "--dry-run"))
    assert second_plan["projects"][0]["classification"] == "current"
    second = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", str(second_plan["plan_id"])
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert payload(second)["results"][0]["status"] == "noop"
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == metadata_after
    assert (config / "registry/projects.yaml").read_bytes() == registry_after


def test_dry_run_output_and_migration_ordering_are_deterministic(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    zebra, zebra_remote, _, zebra_repo = prepare_workspace(tmp_path, "zebra", "v2-project.yaml")
    alpha, alpha_remote, _, alpha_repo = prepare_workspace(tmp_path, "alpha", "v3-single.yaml")
    write_registry(
        config,
        [
            project_block("zebra", zebra, zebra_repo, str(zebra_remote)),
            project_block("alpha", alpha, alpha_repo, str(alpha_remote)),
        ],
    )
    first = payload(run_wb(config, "migrate-registered-projects", "--dry-run"))
    second = payload(run_wb(config, "migrate-registered-projects", "--dry-run"))
    assert first["plan_id"] == second["plan_id"]
    assert first["projects"] == second["projects"]
    assert [item["slug"] for item in first["projects"]] == ["alpha", "zebra"]
    assert [step["id"] for step in first["projects"][0]["steps"]] == ["layout-v3-to-v4"]
    assert [step["id"] for step in first["projects"][1]["steps"]] == ["layout-v2-to-v3", "layout-v3-to-v4"]


def test_stale_plan_id_does_not_mutate(tmp_path: Path) -> None:
    config = bootstrap_config(tmp_path)
    workspace, remote, _, repo_id = prepare_workspace(tmp_path, "stale-plan", "v3-single.yaml")
    registry = write_registry(config, [project_block("stale-plan", workspace, repo_id, str(remote))])
    before = registry.read_bytes()
    applied = run_wb(
        config, "migrate-registered-projects", "--apply", "--accepted-plan-id", "rl-not-the-plan"
    )
    assert applied.returncode == 1
    assert payload(applied)["failure_code"] == "WB_REGISTRY_LAYOUT_PLAN_STALE"
    assert registry.read_bytes() == before


def test_historical_layout_fixtures_are_not_current_schema(tmp_path: Path) -> None:
    v2 = (FIXTURES / "layouts/v2-project.yaml").read_text(encoding="utf-8")
    v3 = (FIXTURES / "layouts/v3-single.yaml").read_text(encoding="utf-8")
    v4 = (FIXTURES / "layouts/v4-single.yaml").read_text(encoding="utf-8")
    registry = (FIXTURES / "registry/unversioned.yaml").read_text(encoding="utf-8")
    assert "metadata_version: 2" in v2
    assert "metadata_version: 3" in v3
    assert "metadata_version: 4" in v4
    assert "workspace:" not in v2 and "workspace:" not in v3
    assert "control_plane:" not in v2 and "control_plane:" not in v3
    assert "registry_schema_version:" not in registry
    assert "custom_registry_field: keep-registry" in registry
