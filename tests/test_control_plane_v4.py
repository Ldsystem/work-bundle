from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts/work-bundle"))
from workspace_resources import CREDENTIAL_TEMPLATE, SCRIPT_INDEX_TEMPLATE
from control_plane import (
    ControlPlaneError,
    deferred_remote_task_identity,
    validate_deferred_remote_independent_review_identity,
)


def run_wb(config_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(config_root)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/wb.py"), *args],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def run_orch(config_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WB_CONFIG_ROOT"] = str(config_root)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/orch.py"), *args],
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


def config_root(tmp_path: Path) -> Path:
    root = tmp_path / "config"
    (root / "registry").mkdir(parents=True)
    (root / "bootstrap.yaml").write_text(
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
    (root / "registry/projects.yaml").write_text("bindings: []\n", encoding="utf-8")
    return root


def make_remote(tmp_path: Path, name: str) -> tuple[Path, Path, str]:
    remote = tmp_path / f"{name}.git"
    checkout = tmp_path / name
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(checkout)], check=True)
    git(checkout, "config", "user.email", "test@example.com")
    git(checkout, "config", "user.name", "Test")
    (checkout / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    git(checkout, "add", "README.md")
    git(checkout, "commit", "-q", "-m", "init")
    git(checkout, "remote", "add", "origin", str(remote))
    git(checkout, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    return remote, checkout, git(checkout, "rev-parse", "HEAD")


def make_v3_workspace(tmp_path: Path) -> tuple[Path, Path, str]:
    remote, checkout, head = make_remote(tmp_path, "source")
    workspace = tmp_path / "workspace-a"
    control = workspace / ".work-bundle"
    (control / "knowledge/notes").mkdir(parents=True)
    (control / "orchestration/spec/active").mkdir(parents=True)
    (control / "knowledge/notes/decision.md").write_text("portable decision\n", encoding="utf-8")
    (control / "project.yaml").write_text(
        "\n".join(
            [
                "metadata_version: 3",
                "authority: canonical",
                f"workspace_root: {workspace}",
                "workspace_mode: multi-repository",
                f"project_root: {checkout}",
                "prefer_subagent: false",
                "custom_portable:",
                "  retained: yes",
                "source_repositories:",
                "  - id: source-main",
                f"    project_root: {checkout}",
                "    origin_id: source-main",
                "    checkout_kind: local-project",
                f"    git_control_root: {checkout / '.git'}",
                "    git_control_scope: project",
                "    worktree_name: source-main",
                "    git_repository: true",
                "    expected_branch: main",
                "    base_ref: HEAD",
                f"    observed_head: {head}",
                "    observation_time: 2026-08-13T00:00:00Z",
                "    baseline_status: current",
                "    lifecycle_status: active",
                "    operation_policy: inherit",
                f"    remote: {remote}",
                "    codegraph:",
                "      supported: false",
                "      status: not-indexed",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return workspace, remote, head


def make_v3_single_workspace(tmp_path: Path, *, tracked_agents: bool = False) -> tuple[Path, Path, str]:
    remote = tmp_path / "single-source.git"
    workspace = tmp_path / "single-workspace"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(workspace)], check=True)
    git(workspace, "config", "user.email", "test@example.com")
    git(workspace, "config", "user.name", "Test")
    (workspace / "README.md").write_text("# same-root source\n", encoding="utf-8")
    (workspace / "script").mkdir()
    (workspace / "script/index.yaml").write_text(SCRIPT_INDEX_TEMPLATE, encoding="utf-8")
    (workspace / ".gitignore").write_text(".work-bundle/\nAGENTS.md\n", encoding="utf-8")
    source_paths = ["README.md", ".gitignore", "script/index.yaml"]
    if tracked_agents:
        (workspace / "AGENTS.md").write_text("user-owned agent guidance\n", encoding="utf-8")
        source_paths.append("AGENTS.md")
        git(workspace, "add", "-f", *source_paths)
    else:
        git(workspace, "add", *source_paths)
    git(workspace, "commit", "-q", "-m", "init")
    git(workspace, "remote", "add", "origin", str(remote))
    git(workspace, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
    head = git(workspace, "rev-parse", "HEAD")
    control = workspace / ".work-bundle"
    (control / "knowledge/notes").mkdir(parents=True)
    (control / "orchestration/spec/active").mkdir(parents=True)
    (control / "knowledge/notes/decision.md").write_text("portable decision\n", encoding="utf-8")
    (control / "project.yaml").write_text(
        "\n".join(
            [
                "metadata_version: 3",
                "authority: canonical",
                f"workspace_root: {workspace}",
                "workspace_mode: single-repository",
                f"project_root: {workspace}",
                "prefer_subagent: false",
                "source_repositories:",
                "  - id: source-main",
                f"    project_root: {workspace}",
                "    origin_id: source-main",
                "    checkout_kind: local-project",
                f"    git_control_root: {workspace / '.git'}",
                "    git_control_scope: project",
                "    worktree_name: source-main",
                "    git_repository: true",
                "    expected_branch: main",
                "    base_ref: HEAD",
                f"    observed_head: {head}",
                "    observation_time: 2026-08-13T00:00:00Z",
                "    baseline_status: current",
                "    lifecycle_status: active",
                "    operation_policy: inherit",
                f"    remote: {remote}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return workspace, remote, head


def migrate(config: Path, workspace: Path) -> dict[str, object]:
    proposed = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    proposal = json.loads(proposed.stdout)
    applied = run_wb(
        config,
        "migrate-control-plane",
        str(workspace),
        "--apply",
        "--accepted-proposal-id",
        str(proposal["migration"]["proposal_id"]),
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    return json.loads(applied.stdout)


def portable_multi_workspace(
    tmp_path: Path, repositories: list[tuple[str, Path]]
) -> tuple[Path, bytes]:
    source_config = config_root(tmp_path / "source-config")
    source_workspace = tmp_path / "source-workspace"
    args: list[str] = [
        "init-workspace",
        str(source_workspace),
        "--mode",
        "multi-repository",
        "--slug",
        "portable-multi",
    ]
    for repository_id, remote in repositories:
        args.extend(["--repository", f"{repository_id}={remote}"])
    args.append("--apply")
    initialized = run_wb(source_config, *args)
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr

    workspace = tmp_path / "attached-workspace"
    shutil.copytree(source_workspace / ".work-bundle", workspace / ".work-bundle")
    marker = workspace / ".work-bundle/knowledge/notes/control-marker.md"
    marker.write_text("control plane preserved\n", encoding="utf-8")
    return workspace, (workspace / ".work-bundle/project.yaml").read_bytes()


def test_v3_to_v4_migration_is_deterministic_and_splits_local_state(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, remote, _ = make_v3_workspace(tmp_path)

    first = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    second = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert first.returncode == second.returncode == 0
    first_data = json.loads(first.stdout)
    assert first_data["migration"]["proposal_id"] == json.loads(second.stdout)["migration"]["proposal_id"]
    assert first_data["proposal"]["topology"] == "multi-repository"
    assert "workspace_root" in first_data["proposal"]["local_fields_to_move"]
    assert first_data["proposal"]["repositories"][0]["id"] == "source-main"
    assert "runtime/" in first_data["proposal"]["local_only_paths"]

    applied = run_wb(
        config,
        "migrate-control-plane",
        str(workspace),
        "--apply",
        "--accepted-proposal-id",
        first_data["migration"]["proposal_id"],
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "metadata_version: 4" in metadata
    assert "workspace:\n  id: wb-" in metadata
    assert f"canonical: {remote}" in metadata
    assert "custom_portable:" in metadata
    for forbidden in ("workspace_root:", "project_root:", "observed_head:", "observation_time:", "git_control_root:"):
        assert forbidden not in metadata
    registry = (config / "registry/projects.yaml").read_text(encoding="utf-8")
    assert str(workspace) in registry
    assert "source-main:" in registry
    assert "observed_head:" in registry
    assert (workspace / ".work-bundle/.gitignore").is_file()


def test_v3_migration_traces_local_origin_chain_to_network_remote(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, network_remote, _ = make_v3_workspace(tmp_path)
    checkout = tmp_path / "source"
    local_origin = tmp_path / "local-origin"
    subprocess.run(["git", "clone", "-q", "--", str(network_remote), str(local_origin)], check=True)
    git(local_origin, "remote", "set-url", "origin", "ssh://git@example.test/team/source.git")
    git(checkout, "remote", "set-url", "origin", str(local_origin))
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(
        "\n".join(
            line for line in metadata.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("remote:")
        ) + "\n",
        encoding="utf-8",
    )

    proposed = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = json.loads(proposed.stdout)
    assert data["proposal"]["repositories"] == [
        {"id": "source-main", "canonical_remote": "ssh://git@example.test/team/source"}
    ]


def test_v3_migration_records_live_checkout_observations_in_local_binding(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, old_head = make_v3_workspace(tmp_path)
    checkout = tmp_path / "source"
    (checkout / "later.txt").write_text("later\n", encoding="utf-8")
    git(checkout, "add", "later.txt")
    git(checkout, "commit", "-q", "-m", "later")
    live_head = git(checkout, "rev-parse", "HEAD")
    assert live_head != old_head

    migrate(config, workspace)
    registry = (config / "registry/projects.yaml").read_text(encoding="utf-8")
    assert f"observed_head: {live_head}" in registry
    assert f"observed_head: {old_head}" not in registry
    assert "observed_branch: main" in registry


def test_migration_uses_registry_remote_when_live_origin_chain_ends_locally(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(
        "\n".join(
            line for line in metadata.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("remote:")
        ) + "\n",
        encoding="utf-8",
    )
    custom_registry = config / "custom" / "project-locators.yaml"
    custom_registry.parent.mkdir(parents=True)
    bootstrap = config / "bootstrap.yaml"
    bootstrap.write_text(
        bootstrap.read_text(encoding="utf-8").replace(
            'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
            'project_registry: "$work_bundle_config_root/custom/project-locators.yaml"',
        ),
        encoding="utf-8",
    )
    custom_registry.write_text(
        "\n".join([
            "projects:",
            "  - slug: unrelated-workspace",
            "    work_bundle_root: /Volumes/ext/project/DTM&RPG/.work-bundle",
            "    repository_origins: []",
            "  - slug: workspace-a",
            f"    work_bundle_root: {workspace / '.work-bundle'}",
            "    repository_origins:",
            "      - id: source-main",
            "        origin_path: /device-local/source",
            "        remote: ssh://git@example.test/team/source.git",
            "        git_repository: true",
            "",
        ]),
        encoding="utf-8",
    )

    proposed = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    assert json.loads(proposed.stdout)["proposal"]["repositories"][0]["canonical_remote"] == "ssh://git@example.test/team/source"


def test_fallback_yaml_scalar_rejects_yaml_indicators_but_allows_mid_scalar_ampersand() -> None:
    script = """
import json
import workspace_resources

workspace_resources.yaml = None
values = {}
for label, scalar in {
    "anchor": "&anchor value",
    "alias": "*alias",
    "core_tag": "!!str value",
    "custom_tag": "!custom value",
    "verbatim_tag": "!<tag:example.com,2026:x> value",
}.items():
    try:
        workspace_resources._load_yaml(f"value: {scalar}\\n")
    except ValueError as exc:
        values[label] = str(exc)
values["path"] = workspace_resources._load_yaml("value: /Volumes/ext/DTM&RPG\\n")["value"]
print(json.dumps(values, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT / "scripts/work-bundle",
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "alias": "unsupported YAML token",
        "anchor": "unsupported YAML token",
        "core_tag": "unsupported YAML token",
        "custom_tag": "unsupported YAML token",
        "path": "/Volumes/ext/DTM&RPG",
        "verbatim_tag": "unsupported YAML token",
    }


def test_migration_preserves_existing_control_plane_gitignore_content(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    gitignore = workspace / ".work-bundle/.gitignore"
    original = "# user policy\n.idea/\n!.env.example\n"
    gitignore.write_text(original, encoding="utf-8")

    proposal = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert proposal.returncode == 0, proposal.stdout + proposal.stderr
    proposal_id = json.loads(proposal.stdout)["migration"]["proposal_id"]
    applied = run_wb(
        config,
        "migrate-control-plane",
        str(workspace),
        "--accepted-proposal-id",
        proposal_id,
        "--apply",
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    migrated = gitignore.read_text(encoding="utf-8")
    assert migrated.endswith(original)
    assert ".idea/" in migrated
    assert "!.env.example" in migrated
    for required in ("git/", "runtime/", "orchestration/execution-state/", "*.secret"):
        assert required in migrated


def test_migration_preserves_metadata_live_conflict_code_when_registry_also_disagrees(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    checkout = tmp_path / "source"
    git(checkout, "remote", "set-url", "origin", "ssh://git@example.test/live/source.git")
    (config / "registry/projects.yaml").write_text(
        "\n".join([
            "projects:",
            "  - slug: workspace-a",
            f"    work_bundle_root: {workspace / '.work-bundle'}",
            "    repository_origins:",
            "      - id: source-main",
            "        remote: ssh://git@example.test/registry/source.git",
            "        git_repository: true",
            "",
        ]),
        encoding="utf-8",
    )

    blocked = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CONFLICT"


def test_migration_explicit_remote_override_is_deterministic_and_resolves_conflict(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    override = "source-main=ssh://git@example.test/team/authoritative.git"

    first = run_wb(config, "migrate-control-plane", str(workspace), "--repository-remote", override, "--dry-run")
    second = run_wb(config, "migrate-control-plane", str(workspace), "--repository-remote", override, "--dry-run")
    assert first.returncode == second.returncode == 0, first.stdout + first.stderr
    first_data = json.loads(first.stdout)
    assert first_data["migration"]["proposal_id"] == json.loads(second.stdout)["migration"]["proposal_id"]
    assert first_data["proposal"]["repositories"][0]["canonical_remote"] == "ssh://git@example.test/team/authoritative"


def test_migration_blocks_registry_and_live_network_remote_conflict_without_override(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    checkout = tmp_path / "source"
    git(checkout, "remote", "set-url", "origin", "ssh://git@example.test/live/source.git")
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(
        "\n".join(
            line for line in metadata.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("remote:")
        ) + "\n",
        encoding="utf-8",
    )
    (config / "registry/projects.yaml").write_text(
        "\n".join([
            "projects:",
            "  - slug: workspace-a",
            f"    work_bundle_root: {workspace / '.work-bundle'}",
            "    source_repositories:",
            "      - id: source-main",
            "        remote: ssh://git@example.test/registry/source.git",
            "        git_repository: true",
            "",
        ]),
        encoding="utf-8",
    )

    blocked = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_CANONICAL_REMOTE_CONFLICT"


def test_attach_and_doctor_resolve_local_source_origin_chain(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace, network_remote, _ = make_v3_workspace(tmp_path / "fixture")
    checkout = tmp_path / "fixture/source"
    local_origin = tmp_path / "local-origin"
    subprocess.run(["git", "clone", "-q", "--", str(network_remote), str(local_origin)], check=True)
    git(local_origin, "remote", "set-url", "origin", "ssh://git@example.test/team/source.git")
    git(checkout, "remote", "set-url", "origin", str(local_origin))
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(
        "\n".join(
            line for line in metadata.read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("remote:")
        ) + "\n",
        encoding="utf-8",
    )
    migrate(config_a, workspace)

    config_b = config_root(tmp_path / "device-b")
    attached = run_wb(
        config_b,
        "attach-workspace",
        str(workspace),
        "--materialize",
        "none",
        "--repository-path",
        f"source-main={checkout}",
        "--apply",
    )
    assert attached.returncode == 0, attached.stdout + attached.stderr
    doctor = run_wb(config_b, "doctor-workspace", str(workspace))
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert json.loads(doctor.stdout)["local_binding"]["status"] == "passed"


def test_legacy_project_commands_accept_v4_and_doctor_repair_preserves_portable_metadata(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    migrate(config, workspace)
    checkout = tmp_path / "source"
    attached = run_wb(
        config,
        "attach-workspace",
        str(workspace),
        "--repository-path",
        f"source-main={checkout}",
        "--materialize",
        "none",
        "--apply",
    )
    assert attached.returncode == 0, attached.stdout + attached.stderr
    portable_before = (workspace / ".work-bundle/project.yaml").read_bytes()

    shown = run_wb(config, "show-project", "--workspace-root", str(workspace))
    validated = run_wb(config, "validate-project", str(workspace), "--dry-run")
    repaired = run_wb(config, "doctor-project", str(workspace), "--repair", "--force")
    assert shown.returncode == validated.returncode == repaired.returncode == 0
    assert json.loads(shown.stdout)["status"] == "passed"
    assert json.loads(validated.stdout)["status"] == "passed"
    assert json.loads(repaired.stdout)["status"] == "passed"
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == portable_before


def test_migration_rejects_stale_proposal(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    proposal = json.loads(run_wb(config, "migrate-control-plane", str(workspace), "--dry-run").stdout)
    with (workspace / ".work-bundle/project.yaml").open("a", encoding="utf-8") as stream:
        stream.write("changed_after_proposal: true\n")
    stale = run_wb(
        config,
        "migrate-control-plane",
        str(workspace),
        "--apply",
        "--accepted-proposal-id",
        proposal["migration"]["proposal_id"],
    )
    assert stale.returncode == 1
    assert json.loads(stale.stdout)["failure_code"] == "WB_CONTROL_PLANE_PROPOSAL_STALE"



def test_single_repository_migration_keeps_same_root_and_preserves_tracked_agents(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, remote, _ = make_v3_single_workspace(tmp_path, tracked_agents=True)
    agents_before = (workspace / "AGENTS.md").read_bytes()

    first = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    second = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert first.returncode == second.returncode == 0, first.stdout + first.stderr
    proposal = json.loads(first.stdout)
    assert proposal["migration"]["proposal_id"] == json.loads(second.stdout)["migration"]["proposal_id"]
    assert proposal["proposal"]["topology"] == "single-repository"

    applied = run_wb(
        config,
        "migrate-control-plane",
        str(workspace),
        "--apply",
        "--accepted-proposal-id",
        proposal["migration"]["proposal_id"],
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "mode: single-repository" in metadata
    assert "workspace_binding:\n      type: root" in metadata
    assert f"canonical: {remote}" in metadata
    assert "project_root:" not in metadata
    registry = (config / "registry/projects.yaml").read_text(encoding="utf-8")
    assert f"project_root: {workspace}" in registry
    assert (workspace / "AGENTS.md").read_bytes() == agents_before
    assert git(workspace, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert git(workspace, "check-ignore", "--no-index", ".work-bundle/project.yaml") == ".work-bundle/project.yaml"


def test_single_repository_init_creates_workspace_resources(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    remote, workspace, _ = make_remote(tmp_path / "source-fixture", "source")

    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--mode",
        "single-repository",
        "--slug",
        "single-demo",
        "--repository",
        f"source-main={remote}",
        "--apply",
    )

    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    assert (workspace / "script/index.yaml").read_text(encoding="utf-8") == SCRIPT_INDEX_TEMPLATE
    credential_file = workspace / "credentials/credentials.yaml"
    assert credential_file.read_text(encoding="utf-8") == CREDENTIAL_TEMPLATE
    assert credential_file.parent.stat().st_mode & 0o777 == 0o700
    assert credential_file.stat().st_mode & 0o777 == 0o600


def test_single_repository_init_preserves_workspace_resources(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    remote, workspace, _ = make_remote(tmp_path / "source-fixture", "source")
    script_index = workspace / "script/index.yaml"
    credential_file = workspace / "credentials/credentials.yaml"
    script_index.parent.mkdir(parents=True)
    script_index.write_text(SCRIPT_INDEX_TEMPLATE + "# preserve-script\n", encoding="utf-8")
    credential_file.parent.mkdir(parents=True)
    credential_file.write_text(CREDENTIAL_TEMPLATE + "# preserve-credential\n", encoding="utf-8")
    script_before = script_index.read_bytes()
    credential_before = credential_file.read_bytes()
    exclude = workspace / ".git/info/exclude"
    exclude.write_text("# preserve-existing-exclude\n", encoding="utf-8")

    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--mode",
        "single-repository",
        "--slug",
        "single-demo",
        "--repository",
        f"source-main={remote}",
        "--apply",
    )

    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    assert script_index.read_bytes() == script_before
    assert credential_file.read_bytes() == credential_before
    assert credential_file.parent.stat().st_mode & 0o777 == 0o700
    assert credential_file.stat().st_mode & 0o777 == 0o600
    exclude_text = exclude.read_text(encoding="utf-8")
    assert "# preserve-existing-exclude" in exclude_text
    assert ".work-bundle/" in exclude_text
    assert "credentials/" in exclude_text
    metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert "workspace_root:" not in metadata
    assert "project_root:" not in metadata
    assert "git_control_root:" not in metadata
    assert git(workspace, "check-ignore", "--no-index", ".work-bundle/project.yaml") == ".work-bundle/project.yaml"
    assert git(workspace, "check-ignore", "--no-index", "credentials/credentials.yaml") == "credentials/credentials.yaml"
    assert subprocess.run(
        ["git", "-C", str(workspace), "check-ignore", "--no-index", "script/index.yaml"],
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 1
    new_utility = workspace / "script/new-utility.py"
    new_utility.write_text("print('visible')\n", encoding="utf-8")
    assert "script/new-utility.py" in git(workspace, "status", "--porcelain=v1", "--untracked-files=all")


def test_single_repository_attach_creates_resources_without_topology_drift(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "config-a")
    workspace, _, _ = make_v3_single_workspace(tmp_path / "fixture")
    (workspace / "script/index.yaml").unlink()
    git(workspace, "add", "script/index.yaml")
    git(workspace, "commit", "-q", "-m", "remove workspace resources for attach repair")
    migrate(config_a, workspace)
    script_index = workspace / "script/index.yaml"
    credential_file = workspace / "credentials/credentials.yaml"
    assert not script_index.exists()
    assert not credential_file.exists()

    config_b = config_root(tmp_path / "config-b")
    attached = run_wb(config_b, "attach-workspace", str(workspace), "--materialize", "none", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    assert script_index.read_text(encoding="utf-8") == SCRIPT_INDEX_TEMPLATE
    assert credential_file.read_text(encoding="utf-8") == CREDENTIAL_TEMPLATE
    assert credential_file.parent.stat().st_mode & 0o777 == 0o700
    assert credential_file.stat().st_mode & 0o777 == 0o600
    assert "credentials/" in (workspace / ".git/info/exclude").read_text(encoding="utf-8")
    doctor = run_wb(config_b, "doctor-workspace", str(workspace))
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert json.loads(doctor.stdout)["portable"]["failures"] == []


def test_single_repository_fresh_attach_materializes_source_into_workspace_root(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace_a, source_remote, _ = make_v3_single_workspace(tmp_path / "source-fixture")
    migrate(config_a, workspace_a)
    control_remote = tmp_path / "control-plane.git"
    subprocess.run(["git", "init", "--bare", "-q", str(control_remote)], check=True)
    published = run_wb(
        config_a,
        "publish-control-plane",
        str(workspace_a),
        "--remote",
        str(control_remote),
        "--apply",
    )
    assert published.returncode == 0, published.stdout + published.stderr
    subprocess.run(["git", "-C", str(control_remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)

    workspace_b = tmp_path / "device-b/workspace"
    workspace_b.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "-q", "--", str(control_remote), str(workspace_b / ".work-bundle")],
        check=True,
    )
    control_head = git(workspace_b / ".work-bundle", "rev-parse", "HEAD")
    config_b = config_root(tmp_path / "device-b-config")
    attached = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "missing", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    data = json.loads(attached.stdout)
    assert data["execution_ready"] is True
    assert data["repositories"][0]["state"] == "materialized-root"
    assert (workspace_b / "README.md").is_file()
    assert not (workspace_b / "source-main").exists()
    assert git(workspace_b, "remote", "get-url", "origin") == str(source_remote)
    assert git(workspace_b, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert git(workspace_b / ".work-bundle", "rev-parse", "HEAD") == control_head
    registry = (config_b / "registry/projects.yaml").read_text(encoding="utf-8")
    assert f"project_root: {workspace_b}" in registry
    preflight = run_orch(config_b, "repository-preflight", "--project-root", str(workspace_b))
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    repositories = json.loads(preflight.stdout)["repository_preflight"]["repositories"]
    assert [row["path"] for row in repositories] == [str(workspace_b.resolve())]
    control_change = workspace_b / ".work-bundle/knowledge/notes/device-b.md"
    control_change.write_text("control-only change\n", encoding="utf-8")
    assert git(workspace_b, "status", "--porcelain=v1", "--untracked-files=all") == ""
    control_status = git(workspace_b / ".work-bundle", "status", "--porcelain=v1", "--untracked-files=all")
    assert "knowledge/notes/device-b.md" in control_status
    (workspace_b / "README.md").write_text("# source-only change\n", encoding="utf-8")
    assert git(workspace_b / ".work-bundle", "status", "--porcelain=v1", "--untracked-files=all") == control_status


def test_single_repository_attach_adopts_compatible_existing_root_and_rejects_conflict(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace, _, _ = make_v3_single_workspace(tmp_path / "fixture")
    migrate(config_a, workspace)
    portable_before = (workspace / ".work-bundle/project.yaml").read_bytes()
    config_b = config_root(tmp_path / "device-b")

    adopted = run_wb(config_b, "attach-workspace", str(workspace), "--materialize", "none", "--apply")
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    assert json.loads(adopted.stdout)["repositories"][0]["state"] == "compatible-existing"
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == portable_before
    assert f"project_root: {workspace}" in (config_b / "registry/projects.yaml").read_text(encoding="utf-8")

    original_remote = git(workspace, "remote", "get-url", "origin")
    conflicting_remote = tmp_path / "conflicting.git"
    subprocess.run(["git", "init", "--bare", "-q", str(conflicting_remote)], check=True)
    git(workspace, "remote", "set-url", "origin", str(conflicting_remote))
    config_c = config_root(tmp_path / "device-c")
    rejected = run_wb(config_c, "attach-workspace", str(workspace), "--materialize", "none", "--apply")
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CONFLICT"
    assert git(workspace, "remote", "get-url", "origin") == str(conflicting_remote)
    assert original_remote != str(conflicting_remote)


def test_single_repository_failed_root_materialization_rolls_back_source_git_only(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace_a, _, _ = make_v3_single_workspace(tmp_path / "source-fixture")
    migrate(config_a, workspace_a)
    control_remote = tmp_path / "control-plane.git"
    subprocess.run(["git", "init", "--bare", "-q", str(control_remote)], check=True)
    published = run_wb(config_a, "publish-control-plane", str(workspace_a), "--remote", str(control_remote), "--apply")
    assert published.returncode == 0, published.stdout + published.stderr
    subprocess.run(["git", "-C", str(control_remote), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)

    workspace_b = tmp_path / "device-b/workspace"
    workspace_b.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--", str(control_remote), str(workspace_b / ".work-bundle")], check=True)
    metadata = workspace_b / ".work-bundle/project.yaml"
    metadata.write_text(metadata.read_text(encoding="utf-8").replace("default_branch: main", "default_branch: missing"), encoding="utf-8")
    marker = workspace_b / ".work-bundle/knowledge/notes/marker.md"
    marker.write_text("preserve me\n", encoding="utf-8")
    config_b = config_root(tmp_path / "device-b-config")

    attached = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "missing", "--apply")
    assert attached.returncode == 1
    assert json.loads(attached.stdout)["failure_code"] == "WB_CONTROL_PLANE_GIT_OPERATION_FAILED"
    assert not (workspace_b / ".git").exists()
    assert marker.read_text(encoding="utf-8") == "preserve me\n"
    assert not (workspace_b / "README.md").exists()
    assert "device_bindings:" not in (config_b / "registry/projects.yaml").read_text(encoding="utf-8")


def test_single_repository_fresh_attach_dry_run_reports_absent_without_remote_conflict(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace_a, _, _ = make_v3_single_workspace(tmp_path / "source-fixture")
    migrate(config_a, workspace_a)
    workspace_b = tmp_path / "device-b/workspace"
    (workspace_b / ".work-bundle").mkdir(parents=True)
    (workspace_b / ".work-bundle/project.yaml").write_bytes(
        (workspace_a / ".work-bundle/project.yaml").read_bytes()
    )
    config_b = config_root(tmp_path / "device-b-config")

    proposed = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "missing", "--dry-run")
    assert proposed.returncode == 0, proposed.stdout + proposed.stderr
    data = json.loads(proposed.stdout)
    assert data["portable_status"] == "passed"
    assert data["repositories"][0]["state"] == "absent"
    assert data["execution_ready"] is False
    assert not (workspace_b / ".git").exists()


def test_single_repository_post_checkout_failure_rolls_back_entire_root_materialization(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace_a, _, _ = make_v3_single_workspace(tmp_path / "source-fixture")
    migrate(config_a, workspace_a)
    workspace_b = tmp_path / "device-b/workspace"
    control_b = workspace_b / ".work-bundle"
    control_b.mkdir(parents=True)
    (control_b / "project.yaml").write_bytes((workspace_a / ".work-bundle/project.yaml").read_bytes())
    marker = control_b / "knowledge/notes/marker.md"
    marker.parent.mkdir(parents=True)
    marker.write_text("preserve me\n", encoding="utf-8")
    config_b = config_root(tmp_path / "device-b-config")
    bootstrap = config_b / "bootstrap.yaml"
    bootstrap.write_text(
        bootstrap.read_text(encoding="utf-8").replace(str(REPO_ROOT), str(tmp_path / "missing-toolkit")),
        encoding="utf-8",
    )

    attached = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "missing", "--apply")
    assert attached.returncode == 1
    assert json.loads(attached.stdout)["failure_code"] == "WB_CONTROL_PLANE_AGENTS_REFERENCE_MISSING"
    assert not (workspace_b / ".git").exists()
    assert not (workspace_b / "README.md").exists()
    assert marker.read_text(encoding="utf-8") == "preserve me\n"
    assert "device_bindings:" not in (config_b / "registry/projects.yaml").read_text(encoding="utf-8")


def test_single_repository_migration_rejects_source_owned_control_plane(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_single_workspace(tmp_path)
    git(workspace, "add", "-f", ".work-bundle/project.yaml")
    git(workspace, "commit", "-q", "-m", "incorrectly track control plane")

    blocked = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_SOURCE_TRACKS_CONTROL_PLANE"


def test_attach_reconstructs_distinct_device_binding_without_portable_diff(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace_a, _, _ = make_v3_workspace(tmp_path / "origin-fixture")
    migrate(config_a, workspace_a)
    portable = (workspace_a / ".work-bundle/project.yaml").read_bytes()

    workspace_b = tmp_path / "device-b/workspace-renamed"
    control_b = workspace_b / ".work-bundle"
    control_b.mkdir(parents=True)
    (control_b / "project.yaml").write_bytes(portable)
    (control_b / "knowledge").mkdir()
    config_b = config_root(tmp_path / "device-b-config")
    attached = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "none", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    data = json.loads(attached.stdout)
    assert data["portable_status"] == "passed"
    assert data["execution_ready"] is False
    assert data["repositories"][0]["state"] == "absent"
    assert (control_b / "project.yaml").read_bytes() == portable
    assert str(workspace_b) in (config_b / "registry/projects.yaml").read_text(encoding="utf-8")
    assert (workspace_b / "script/index.yaml").is_file()
    credential = workspace_b / "credentials/credentials.yaml"
    assert credential.is_file()
    assert credential.stat().st_mode & 0o777 == 0o600
    agents = (workspace_b / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("# Work Bundle RULE START") == 1


def test_attach_adopts_only_matching_remote_and_detach_is_local_only(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "device-a")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config_a, workspace)
    portable_before = (workspace / ".work-bundle/project.yaml").read_bytes()
    config_b = config_root(tmp_path / "device-b")

    _, compatible, _ = make_remote(tmp_path / "matching", "compatible")
    git(compatible, "remote", "set-url", "origin", str(remote))
    attached = run_wb(
        config_b,
        "attach-workspace",
        str(workspace),
        "--materialize",
        "none",
        "--repository-path",
        f"source-main={compatible}",
        "--apply",
    )
    assert attached.returncode == 0, attached.stdout + attached.stderr
    assert json.loads(attached.stdout)["repositories"][0]["state"] == "compatible-existing"

    _, conflict, _ = make_remote(tmp_path / "conflict", "wrong")
    rejected = run_wb(
        config_b,
        "attach-workspace",
        str(workspace),
        "--materialize",
        "none",
        "--repository-path",
        f"source-main={conflict}",
        "--apply",
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CONFLICT"

    detached = run_wb(config_b, "detach-workspace", str(workspace), "--apply")
    assert detached.returncode == 0
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == portable_before
    assert str(workspace) not in (config_b / "registry/projects.yaml").read_text(encoding="utf-8")


def test_doctor_reports_portable_local_and_readiness_layers(tmp_path: Path) -> None:
    config = config_root(tmp_path)
    workspace, _, _ = make_v3_workspace(tmp_path)
    migrate(config, workspace)
    doctor = run_wb(config, "doctor-workspace", str(workspace))
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    data = json.loads(doctor.stdout)
    assert data["portable"]["status"] == "passed"
    assert data["local_binding"]["status"] == "passed"
    assert data["execution_readiness"]["status"] in {"passed", "not-ready"}


def test_orchestration_preflight_resolves_v4_local_binding(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    _, checkout, _ = make_remote(tmp_path / "attached", "checkout")
    git(checkout, "remote", "set-url", "origin", str(remote))
    attached = run_wb(
        config,
        "attach-workspace",
        str(workspace),
        "--repository-path",
        f"source-main={checkout}",
        "--materialize",
        "none",
        "--apply",
    )
    assert attached.returncode == 0, attached.stdout + attached.stderr

    preflight = run_orch(config, "repository-preflight", "--project-root", str(workspace))
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    repositories = json.loads(preflight.stdout)["repository_preflight"]["repositories"]
    assert [row["path"] for row in repositories] == [str(checkout.resolve())]
    assert repositories[0]["metadata"]["repository_id"] == "source-main"


def test_v4_attach_doctor_and_preflight_share_bootstrap_resolved_registry(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    custom_registry = config / "custom/device-bindings.yaml"
    custom_registry.parent.mkdir(parents=True)
    custom_registry.write_text("projects: []\n", encoding="utf-8")
    bootstrap = config / "bootstrap.yaml"
    bootstrap.write_text(
        bootstrap.read_text(encoding="utf-8").replace(
            'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
            'project_registry: "$work_bundle_config_root/custom/device-bindings.yaml"',
        ),
        encoding="utf-8",
    )
    default_registry = config / "registry/projects.yaml"
    default_before = default_registry.read_bytes()
    remote, _, _ = make_remote(tmp_path / "source-fixture", "source-main")
    workspace = tmp_path / "workspace"

    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--mode",
        "multi-repository",
        "--slug",
        "custom-registry",
        "--repository",
        f"source-main={remote}",
        "--apply",
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    attached = run_wb(config, "attach-workspace", str(workspace), "--materialize", "missing", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    doctor = run_wb(config, "doctor-workspace", str(workspace))
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    preflight = run_orch(config, "repository-preflight", "--project-root", str(workspace))
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr

    registry_text = custom_registry.read_text(encoding="utf-8")
    workspace_id = json.loads(initialized.stdout)["workspace_id"]
    assert workspace_id in registry_text
    assert str((workspace / "source-main").resolve()) in registry_text
    assert default_registry.read_bytes() == default_before
    repositories = json.loads(preflight.stdout)["repository_preflight"]["repositories"]
    assert [row["path"] for row in repositories] == [str((workspace / "source-main").resolve())]
    assert repositories[0]["metadata"]["baseline_status"] == "local-observation"


def test_multi_attach_remote_conflict_rolls_back_only_created_members(tmp_path: Path) -> None:
    remote_a, _, _ = make_remote(tmp_path / "remote-a", "repo-a")
    remote_b, _, _ = make_remote(tmp_path / "remote-b", "repo-b")
    workspace, metadata_before = portable_multi_workspace(
        tmp_path / "portable", [("repo-a", remote_a), ("repo-b", remote_b)]
    )
    config = config_root(tmp_path / "device-config")
    wrong_remote, _, _ = make_remote(tmp_path / "existing", "existing-b")
    existing = workspace / "repo-b"
    subprocess.run(["git", "clone", str(wrong_remote), str(existing)], check=True, capture_output=True)
    existing_head = git(existing, "rev-parse", "HEAD")

    attached = run_wb(
        config,
        "attach-workspace",
        str(workspace),
        "--materialize",
        "missing",
        "--apply",
    )

    assert attached.returncode == 1
    assert json.loads(attached.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CONFLICT"
    assert not (workspace / "repo-a").exists()
    assert existing.is_dir()
    assert git(existing, "rev-parse", "HEAD") == existing_head
    assert git(existing, "remote", "get-url", "origin") == str(wrong_remote)
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == metadata_before
    assert (workspace / ".work-bundle/knowledge/notes/control-marker.md").read_text(encoding="utf-8") == "control plane preserved\n"
    assert "device_bindings:" not in (config / "registry/projects.yaml").read_text(encoding="utf-8")


def test_multi_attach_late_validation_failure_rolls_back_created_members(tmp_path: Path) -> None:
    remote_a, _, _ = make_remote(tmp_path / "remote-a", "repo-a")
    remote_b, _, _ = make_remote(tmp_path / "remote-b", "repo-b")
    workspace, metadata_before = portable_multi_workspace(
        tmp_path / "portable", [("repo-a", remote_a), ("repo-b", remote_b)]
    )
    config = config_root(tmp_path / "device-config")
    fake_toolkit = tmp_path / "fake-toolkit"
    template = fake_toolkit / "references/assets/template/AGENTS.md"
    template.parent.mkdir(parents=True)
    template.write_text(
        "# ========================\n# Work Bundle RULE START\n# ========================\n"
        "nested invalid section\n"
        "# ========================\n# Work Bundle RULE END\n# ========================\n",
        encoding="utf-8",
    )
    bootstrap = config / "bootstrap.yaml"
    bootstrap.write_text(
        bootstrap.read_text(encoding="utf-8").replace(str(REPO_ROOT), str(fake_toolkit)),
        encoding="utf-8",
    )

    attached = run_wb(config, "attach-workspace", str(workspace), "--materialize", "missing", "--apply")

    assert attached.returncode == 1
    data = json.loads(attached.stdout)
    assert data["failure_code"] == "WB_CONTROL_PLANE_AGENTS_SYNC_INVALID"
    assert not (workspace / "repo-a").exists()
    assert not (workspace / "repo-b").exists()
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == metadata_before
    assert (workspace / ".work-bundle/knowledge/notes/control-marker.md").is_file()
    assert "device_bindings:" not in (config / "registry/projects.yaml").read_text(encoding="utf-8")


def test_multi_attach_registry_publication_failure_rolls_back_created_members(tmp_path: Path) -> None:
    remote_a, _, _ = make_remote(tmp_path / "remote-a", "repo-a")
    remote_b, _, _ = make_remote(tmp_path / "remote-b", "repo-b")
    workspace, metadata_before = portable_multi_workspace(
        tmp_path / "portable", [("repo-a", remote_a), ("repo-b", remote_b)]
    )
    config = config_root(tmp_path / "device-config")
    blocked_parent = config / "blocked-registry"
    blocked_parent.write_text("not a directory\n", encoding="utf-8")
    bootstrap = config / "bootstrap.yaml"
    bootstrap.write_text(
        bootstrap.read_text(encoding="utf-8").replace(
            'project_registry: "$work_bundle_config_root/registry/projects.yaml"',
            'project_registry: "$work_bundle_config_root/blocked-registry/projects.yaml"',
        ),
        encoding="utf-8",
    )
    default_registry = config / "registry/projects.yaml"
    default_before = default_registry.read_bytes()

    attached = run_wb(config, "attach-workspace", str(workspace), "--materialize", "missing", "--apply")

    assert attached.returncode == 1
    assert json.loads(attached.stdout)["failure_code"] == "WB_CONTROL_PLANE_TRANSACTION_FAILED"
    assert not (workspace / "repo-a").exists()
    assert not (workspace / "repo-b").exists()
    assert (workspace / ".work-bundle/project.yaml").read_bytes() == metadata_before
    assert (workspace / ".work-bundle/knowledge/notes/control-marker.md").is_file()
    assert default_registry.read_bytes() == default_before


def test_doctor_repair_preserves_existing_and_unknown_local_binding_fields(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    _, checkout, _ = make_remote(tmp_path / "attached", "checkout")
    git(checkout, "remote", "set-url", "origin", str(remote))
    attached = run_wb(
        config,
        "attach-workspace",
        str(workspace),
        "--repository-path",
        f"source-main={checkout}",
        "--materialize",
        "none",
        "--apply",
    )
    assert attached.returncode == 0, attached.stdout + attached.stderr
    registry = config / "registry/projects.yaml"
    registry_text = registry.read_text(encoding="utf-8")
    registry_text = registry_text.replace("    repositories:\n", "    device_label: keep-me\n    repositories:\n")
    registry_text = registry_text.replace("    repositories:\n", "    custom_nested:\n      values: [one, two]\n    repositories:\n")
    registry_text = registry_text.replace(
        "        git_common_dir:", "        custom_observation: keep-repo\n        git_common_dir:"
    )
    registry.write_text(registry_text, encoding="utf-8")

    repaired = run_wb(config, "doctor-workspace", str(workspace), "--repair")
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    after = registry.read_text(encoding="utf-8")
    assert "device_label: keep-me" in after
    assert "custom_nested:" in after
    assert "values:" in after
    assert "custom_observation: keep-repo" in after
    assert str(checkout.resolve()) in after


def test_doctor_workspace_repair_does_not_create_script_index(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, _, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    script_index = workspace / "script/index.yaml"
    script_index.unlink(missing_ok=True)

    repaired = run_wb(config, "doctor-workspace", str(workspace), "--repair")

    assert repaired.returncode == 0, repaired.stdout + repaired.stderr
    assert not script_index.exists()
    assert (workspace / "credentials/credentials.yaml").is_file()


def test_attach_rejects_second_active_materialization_on_same_device(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace_a, _, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace_a)
    workspace_b = tmp_path / "second/workspace"
    (workspace_b / ".work-bundle").mkdir(parents=True)
    (workspace_b / ".work-bundle/project.yaml").write_bytes(
        (workspace_a / ".work-bundle/project.yaml").read_bytes()
    )
    blocked = run_wb(config, "attach-workspace", str(workspace_b), "--materialize", "none", "--apply")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_DUPLICATE_MATERIALIZATION"


def test_init_and_publish_control_plane_lifecycle(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    control_remote = tmp_path / "control-plane.git"
    subprocess.run(["git", "init", "--bare", "-q", str(control_remote)], check=True)
    workspace = tmp_path / "portable-workspace"

    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--slug",
        "portable-demo",
        "--repository",
        f"source-main={source_remote}",
        "--apply",
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    assert "metadata_version: 4" in (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
    assert not (workspace / ".git").exists()

    published = run_wb(
        config,
        "publish-control-plane",
        str(workspace),
        "--remote",
        str(control_remote),
        "--apply",
    )
    assert published.returncode == 0, published.stdout + published.stderr
    assert (workspace / ".work-bundle/.git").is_dir()
    assert git(workspace / ".work-bundle", "remote", "get-url", "origin") == str(control_remote)
    assert git(workspace / ".work-bundle", "status", "--short") == ""
    assert git(workspace / ".work-bundle", "rev-parse", "HEAD")


def test_migration_rejects_tracked_protected_control_plane_paths(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, _, _ = make_v3_workspace(tmp_path / "fixture")
    git(workspace.parent / "source", "status", "--short")
    subprocess.run(["git", "init", "-q", "-b", "main", str(workspace)], check=True)
    git(workspace, "config", "user.email", "test@example.com")
    git(workspace, "config", "user.name", "Test")
    runtime_file = workspace / ".work-bundle/runtime/should-not-track.txt"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("local\n", encoding="utf-8")
    git(workspace, "add", "-f", ".work-bundle/runtime/should-not-track.txt")
    git(workspace, "commit", "-q", "-m", "track protected path")
    blocked = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED"


def test_orchestration_blocks_when_current_local_head_outgrows_device_observation(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    _, checkout, _ = make_remote(tmp_path / "attached", "checkout")
    git(checkout, "remote", "set-url", "origin", str(remote))
    attached = run_wb(
        config,
        "attach-workspace",
        str(workspace),
        "--repository-path",
        f"source-main={checkout}",
        "--materialize",
        "none",
        "--apply",
    )
    assert attached.returncode == 0
    registry = config / "registry/projects.yaml"
    before = registry.read_text(encoding="utf-8")
    (checkout / "later.txt").write_text("later\n", encoding="utf-8")
    git(checkout, "add", "later.txt")
    git(checkout, "commit", "-q", "-m", "later local commit")
    preflight = run_orch(config, "repository-preflight", "--project-root", str(workspace))
    payload = json.loads(preflight.stdout)["repository_preflight"]
    row = payload["repositories"][0]
    assert payload["status"] == "blocked"
    assert row["status"] == "stale-observation"
    assert row["failure_code"] == "WB_REPOSITORY_OBSERVATION_STALE"
    assert row["metadata"]["commit_status"] == "stale"
    assert row["metadata"]["observation_head_status"] == "stale"
    assert registry.read_text(encoding="utf-8") == before


def test_attach_materializes_missing_repository_idempotently_without_portable_mutation(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "config-a")
    workspace_a, _, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config_a, workspace_a)
    portable = (workspace_a / ".work-bundle/project.yaml").read_bytes()
    workspace_b = tmp_path / "device-b/workspace"
    (workspace_b / ".work-bundle").mkdir(parents=True)
    (workspace_b / ".work-bundle/project.yaml").write_bytes(portable)
    config_b = config_root(tmp_path / "config-b")
    first = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "missing", "--apply")
    assert first.returncode == 0, first.stdout + first.stderr
    assert json.loads(first.stdout)["repositories"][0]["state"] == "materialized-managed"
    second = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "missing", "--apply")
    assert second.returncode == 0, second.stdout + second.stderr
    assert (workspace_b / ".work-bundle/project.yaml").read_bytes() == portable


def test_optional_remote_only_repository_is_portable_valid_and_ready(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    remote, _, _ = make_remote(tmp_path / "source-fixture", "optional")
    workspace = tmp_path / "workspace"
    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--slug",
        "optional-demo",
        "--optional-repository",
        f"optional-main={remote}",
        "--apply",
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    attached = run_wb(config, "attach-workspace", str(workspace), "--materialize", "none", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    data = json.loads(attached.stdout)
    assert data["repositories"][0] == {"id": "optional-main", "required": False, "state": "absent"}
    assert data["execution_ready"] is True


def test_attach_rejects_conflicting_control_plane_origin(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    expected_control = tmp_path / "expected-control.git"
    wrong_control = tmp_path / "wrong-control.git"
    subprocess.run(["git", "init", "--bare", "-q", str(expected_control)], check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(wrong_control)], check=True)
    workspace = tmp_path / "workspace"
    assert run_wb(config, "init-workspace", str(workspace), "--slug", "demo", "--repository", f"source-main={source_remote}", "--apply").returncode == 0
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(metadata.read_text(encoding="utf-8").replace('    remote: ""', f"    remote: {expected_control}"), encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(workspace / ".work-bundle")], check=True)
    git(workspace / ".work-bundle", "remote", "add", "origin", str(wrong_control))
    blocked = run_wb(config, "attach-workspace", str(workspace), "--materialize", "none", "--apply")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_ORIGIN_CONFLICT"


def test_doctor_reports_deleted_bound_checkout_not_ready(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    _, checkout, _ = make_remote(tmp_path / "attached", "checkout")
    git(checkout, "remote", "set-url", "origin", str(remote))
    assert run_wb(config, "attach-workspace", str(workspace), "--repository-path", f"source-main={checkout}", "--materialize", "none", "--apply").returncode == 0
    checkout.rename(checkout.with_name("checkout-moved"))
    doctor = run_wb(config, "doctor-workspace", str(workspace))
    data = json.loads(doctor.stdout)
    assert doctor.returncode == 1
    assert "WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:source-main" in data["local_binding"]["failures"]
    assert data["execution_readiness"]["status"] == "not-ready"


def test_migration_rejects_metadata_checkout_remote_mismatch(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, _, _ = make_v3_workspace(tmp_path / "fixture")
    wrong_remote = tmp_path / "wrong.git"
    subprocess.run(["git", "init", "--bare", "-q", str(wrong_remote)], check=True)
    metadata = workspace / ".work-bundle/project.yaml"
    text = metadata.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^    remote: .+$", f"    remote: {wrong_remote}", text)
    metadata.write_text(text, encoding="utf-8")
    blocked = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert blocked.returncode == 1
    assert json.loads(blocked.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CONFLICT"


def test_credential_bearing_remote_is_rejected_without_echo(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace = tmp_path / "workspace"
    secret_remote = "https://user:super-secret@example.com/repo.git"
    result = run_wb(config, "init-workspace", str(workspace), "--slug", "demo", "--repository", f"source-main={secret_remote}", "--dry-run")
    assert result.returncode == 1
    assert json.loads(result.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CREDENTIALS_FORBIDDEN"
    assert "super-secret" not in result.stdout + result.stderr


def test_v4_schema_rejects_duplicate_repository_ids_and_invalid_mode(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    workspace = tmp_path / "workspace"
    assert run_wb(config, "init-workspace", str(workspace), "--slug", "demo", "--repository", f"source-main={remote}", "--apply").returncode == 0
    metadata = workspace / ".work-bundle/project.yaml"
    text = metadata.read_text(encoding="utf-8")
    duplicate = text[text.index("  - id: source-main"):text.index("prefer_subagent:")]
    metadata.write_text(text.replace("  mode: multi-repository", "  mode: invalid").replace("prefer_subagent:", duplicate + "prefer_subagent:"), encoding="utf-8")
    doctor = run_wb(config, "doctor-workspace", str(workspace))
    failures = json.loads(doctor.stdout)["portable"]["failures"]
    assert "WB_CONTROL_PLANE_WORKSPACE_MODE_INVALID" in failures
    assert "WB_CONTROL_PLANE_REPOSITORY_ID_DUPLICATE:source-main" in failures


def test_non_git_v3_member_migrates_with_manual_locator(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace = tmp_path / "workspace"
    local = workspace / "manual-source"
    local.mkdir(parents=True)
    control = workspace / ".work-bundle"
    control.mkdir(parents=True)
    (control / "project.yaml").write_text(
        "\n".join([
            "metadata_version: 3", f"workspace_root: {workspace}", "workspace_mode: multi-repository",
            f"project_root: {local}", "source_repositories:", "  - id: manual-main",
            f"    project_root: {local}", "    origin_id: manual-main", "    git_repository: false",
            '    remote: ""', "    checkout_kind: local-project", "",
        ]), encoding="utf-8"
    )
    proposal = run_wb(config, "migrate-control-plane", str(workspace), "--dry-run")
    assert proposal.returncode == 0, proposal.stdout + proposal.stderr
    proposal_id = json.loads(proposal.stdout)["migration"]["proposal_id"]
    applied = run_wb(config, "migrate-control-plane", str(workspace), "--apply", "--accepted-proposal-id", proposal_id)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    metadata = (control / "project.yaml").read_text(encoding="utf-8")
    assert "locator:\n      type: manual" in metadata
    assert run_wb(config, "doctor-workspace", str(workspace)).returncode == 0


def test_existing_checkout_credential_remote_is_rejected_without_echo(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    _, checkout, _ = make_remote(tmp_path / "attached", "checkout")
    secret = "https://user:existing-secret@example.com/repo.git"
    git(checkout, "remote", "set-url", "origin", secret)
    result = run_wb(config, "attach-workspace", str(workspace), "--repository-path", f"source-main={checkout}", "--materialize", "none", "--apply")
    assert result.returncode == 1
    assert json.loads(result.stdout)["failure_code"] == "WB_CONTROL_PLANE_REMOTE_CREDENTIALS_FORBIDDEN"
    assert "existing-secret" not in result.stdout + result.stderr


def test_publish_failure_restores_metadata_and_writes_recovery_evidence(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    workspace = tmp_path / "workspace"
    assert run_wb(config, "init-workspace", str(workspace), "--slug", "demo", "--repository", f"source-main={source_remote}", "--apply").returncode == 0
    metadata = workspace / ".work-bundle/project.yaml"
    before = metadata.read_bytes()
    missing_remote = tmp_path / "missing-control.git"
    failed = run_wb(config, "publish-control-plane", str(workspace), "--remote", str(missing_remote), "--apply")
    assert failed.returncode == 1
    data = json.loads(failed.stdout)
    assert data["failure_code"] == "WB_CONTROL_PLANE_REMOTE_UNREACHABLE"
    assert metadata.read_bytes() == before
    assert not (workspace / ".work-bundle/.git").exists()
    assert Path(data["transaction_evidence"]).is_file()


def test_publish_push_failure_restores_exact_existing_control_plane_git_state(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    workspace = tmp_path / "workspace"
    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--slug",
        "demo",
        "--repository",
        f"source-main={source_remote}",
        "--apply",
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    control = workspace / ".work-bundle"
    old_remote = tmp_path / "old-control.git"
    rejecting_remote = tmp_path / "rejecting-control.git"
    subprocess.run(["git", "init", "--bare", "-q", str(old_remote)], check=True)
    subprocess.run(["git", "init", "--bare", "-q", str(rejecting_remote)], check=True)
    hook = rejecting_remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    git(control, "init", "-q", "-b", "main")
    git(control, "config", "user.email", "test@example.com")
    git(control, "config", "user.name", "Test")
    git(control, "remote", "add", "origin", str(old_remote))
    git(control, "add", ".")
    git(control, "commit", "-q", "-m", "baseline")
    head_before = git(control, "rev-parse", "HEAD")
    metadata = control / "project.yaml"
    metadata_before = metadata.read_bytes()
    origin_before = git(control, "remote", "get-url", "origin")
    status_before = git(control, "status", "--porcelain=v1", "--untracked-files=all")
    staged_before = git(control, "diff", "--cached", "--name-status")

    failed = run_wb(
        config,
        "publish-control-plane",
        str(workspace),
        "--remote",
        str(rejecting_remote),
        "--apply",
    )

    assert failed.returncode == 1
    data = json.loads(failed.stdout)
    assert data["failure_code"] == "WB_CONTROL_PLANE_GIT_OPERATION_FAILED"
    assert git(control, "rev-parse", "HEAD") == head_before
    assert metadata.read_bytes() == metadata_before
    assert git(control, "remote", "get-url", "origin") == origin_before
    assert git(control, "status", "--porcelain=v1", "--untracked-files=all") == status_before == ""
    assert git(control, "diff", "--cached", "--name-status") == staged_before == ""
    evidence = Path(data["transaction_evidence"])
    assert evidence.is_file()
    evidence_data = json.loads(evidence.read_text(encoding="utf-8"))
    assert evidence_data["state"] == "rolled-back"
    assert evidence_data["recovery_required"] is False


def test_publish_existing_dirty_control_plane_fails_closed_without_mutation(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    workspace = tmp_path / "workspace"
    assert run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--slug",
        "demo",
        "--repository",
        f"source-main={source_remote}",
        "--apply",
    ).returncode == 0
    control = workspace / ".work-bundle"
    remote = tmp_path / "control.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(control, "init", "-q", "-b", "main")
    git(control, "config", "user.email", "test@example.com")
    git(control, "config", "user.name", "Test")
    git(control, "add", ".")
    git(control, "commit", "-q", "-m", "baseline")
    dirty = control / "knowledge/notes/dirty.md"
    dirty.write_text("user change\n", encoding="utf-8")
    head_before = git(control, "rev-parse", "HEAD")
    metadata_before = (control / "project.yaml").read_bytes()
    status_before = git(control, "status", "--porcelain=v1", "--untracked-files=all")

    failed = run_wb(
        config,
        "publish-control-plane",
        str(workspace),
        "--remote",
        str(remote),
        "--apply",
    )

    assert failed.returncode == 1
    data = json.loads(failed.stdout)
    assert data["failure_code"] == "WB_CONTROL_PLANE_PUBLISH_RECOVERY_REQUIRED"
    assert git(control, "rev-parse", "HEAD") == head_before
    assert (control / "project.yaml").read_bytes() == metadata_before
    assert git(control, "status", "--porcelain=v1", "--untracked-files=all") == status_before
    assert dirty.read_text(encoding="utf-8") == "user change\n"
    evidence = json.loads(Path(data["transaction_evidence"]).read_text(encoding="utf-8"))
    assert evidence["state"] == "recovery-required"
    assert evidence["recovery_required"] is True


def test_publish_rejects_nested_gitlink_before_staging(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    workspace = tmp_path / "workspace"
    assert run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--slug",
        "demo",
        "--repository",
        f"source-main={source_remote}",
        "--apply",
    ).returncode == 0
    control = workspace / ".work-bundle"
    nested = control / "knowledge/notes/nested-repository"
    nested.mkdir(parents=True)
    git(nested, "init", "-q", "-b", "main")
    git(nested, "config", "user.email", "test@example.com")
    git(nested, "config", "user.name", "Test")
    (nested / "README.md").write_text("nested\n", encoding="utf-8")
    git(nested, "add", "README.md")
    git(nested, "commit", "-q", "-m", "nested")
    remote = tmp_path / "control.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)

    failed = run_wb(
        config,
        "publish-control-plane",
        str(workspace),
        "--remote",
        str(remote),
        "--apply",
    )

    assert failed.returncode == 1
    data = json.loads(failed.stdout)
    assert data["failure_code"] == "WB_CONTROL_PLANE_GITLINK_FORBIDDEN"
    assert data["gitlink_paths"] == ["knowledge/notes/nested-repository"]
    assert not (control / ".git").exists()
    assert (nested / ".git").is_dir()


def test_publish_failed_git_snapshot_fails_closed_without_mutation(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    source_remote, _, _ = make_remote(tmp_path / "source-fixture", "source")
    workspace = tmp_path / "workspace"
    assert run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--slug",
        "demo",
        "--repository",
        f"source-main={source_remote}",
        "--apply",
    ).returncode == 0
    control = workspace / ".work-bundle"
    remote = tmp_path / "control.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(control, "init", "-q", "-b", "main")
    git(control, "config", "user.email", "test@example.com")
    git(control, "config", "user.name", "Test")
    git(control, "add", ".")
    git(control, "commit", "-q", "-m", "baseline")
    head_before = git(control, "rev-parse", "HEAD")
    metadata_before = (control / "project.yaml").read_bytes()
    index = control / ".git/index"
    index.write_bytes(b"not-a-git-index\n")
    index_before = index.read_bytes()

    failed = run_wb(
        config,
        "publish-control-plane",
        str(workspace),
        "--remote",
        str(remote),
        "--apply",
    )

    assert failed.returncode == 1
    data = json.loads(failed.stdout)
    assert data["failure_code"] == "WB_CONTROL_PLANE_PUBLISH_RECOVERY_REQUIRED"
    assert git(control, "rev-parse", "HEAD") == head_before
    assert (control / "project.yaml").read_bytes() == metadata_before
    assert index.read_bytes() == index_before
    evidence = json.loads(Path(data["transaction_evidence"]).read_text(encoding="utf-8"))
    assert "status_snapshot_failed" in evidence["snapshot_failures"]
    assert "index_snapshot_failed" in evidence["snapshot_failures"]
    assert evidence["recovery_required"] is True


def test_attach_and_doctor_report_wrong_branch_and_dirty_checkout_not_ready(tmp_path: Path) -> None:
    config = config_root(tmp_path / "config-root")
    workspace, remote, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config, workspace)
    _, checkout, _ = make_remote(tmp_path / "attached", "checkout")
    git(checkout, "remote", "set-url", "origin", str(remote))
    git(checkout, "checkout", "-q", "-b", "wrong")
    (checkout / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    attached = run_wb(config, "attach-workspace", str(workspace), "--repository-path", f"source-main={checkout}", "--materialize", "none", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    attach_data = json.loads(attached.stdout)
    assert attach_data["execution_ready"] is False
    assert "WB_CONTROL_PLANE_BRANCH_MISMATCH:source-main" in attach_data["execution_readiness_failures"]
    assert "WB_CONTROL_PLANE_CHECKOUT_DIRTY:source-main" in attach_data["execution_readiness_failures"]
    doctor = run_wb(config, "doctor-workspace", str(workspace))
    doctor_data = json.loads(doctor.stdout)
    assert doctor_data["execution_readiness"]["status"] == "not-ready"


def test_attach_converges_duplicate_agents_sections(tmp_path: Path) -> None:
    config_a = config_root(tmp_path / "config-a")
    workspace_a, _, _ = make_v3_workspace(tmp_path / "fixture")
    migrate(config_a, workspace_a)
    workspace_b = tmp_path / "device-b/workspace"
    (workspace_b / ".work-bundle").mkdir(parents=True)
    (workspace_b / ".work-bundle/project.yaml").write_bytes((workspace_a / ".work-bundle/project.yaml").read_bytes())
    template = (REPO_ROOT / "references/assets/template/AGENTS.md").read_text(encoding="utf-8")
    block = f"# ========================\n# Work Bundle RULE START\n# ========================\n{template}# ========================\n# Work Bundle RULE END\n# ========================\n"
    (workspace_b / "AGENTS.md").write_text("user-before\n" + block + "user-middle\n" + block + "user-after\n", encoding="utf-8")
    config_b = config_root(tmp_path / "config-b")
    attached = run_wb(config_b, "attach-workspace", str(workspace_b), "--materialize", "none", "--apply")
    assert attached.returncode == 0, attached.stdout + attached.stderr
    agents = (workspace_b / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.count("# Work Bundle RULE START") == 1
    assert all(value in agents for value in ("user-before", "user-middle", "user-after"))


def init_single_v4(
    tmp_path: Path, *, slug: str = "single-demo", attach: bool = True
) -> tuple[Path, Path, Path, str]:
    config = config_root(tmp_path / "config-root")
    remote, workspace, _ = make_remote(tmp_path / "source-fixture", "source")
    initialized = run_wb(
        config,
        "init-workspace",
        str(workspace),
        "--mode",
        "single-repository",
        "--slug",
        slug,
        "--repository",
        f"source-main={remote}",
        "--apply",
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    workspace_id = json.loads(initialized.stdout)["workspace_id"]
    if attach:
        attached = run_wb(
            config,
            "attach-workspace",
            str(workspace),
            "--materialize",
            "none",
            "--apply",
        )
        assert attached.returncode == 0, attached.stdout + attached.stderr
    return config, workspace, remote, workspace_id


def add_workspace_member_args(
    workspace: Path,
    remote: Path | str,
    *,
    repository_id: str = "execution-flow",
    name: str = "execution-flow",
    path: str = "execution-flow",
    default_branch: str = "main",
) -> list[str]:
    return [
        "add-workspace-member",
        str(workspace),
        "--repository-id",
        repository_id,
        "--remote",
        str(remote),
        "--name",
        name,
        "--path",
        path,
        "--default-branch",
        default_branch,
    ]


def write_composite_metadata(workspace: Path, *, include_root: bool = True, member_name: str = "execution-flow", member_path: str = "execution-flow") -> None:
    metadata = workspace / ".work-bundle/project.yaml"
    text = metadata.read_text(encoding="utf-8")
    text = text.replace("  mode: single-repository", "  mode: composite")
    if not include_root:
        text = text.replace("      type: root", "      type: member\n      name: relocated-root")
    member = "\n".join(
        [
            "  - id: execution-flow",
            "    role: source",
            "    remote:",
            '      canonical: "https://example.com/execution-flow"',
            "      aliases: []",
            "    default_branch: main",
            "    workspace_binding:",
            "      type: member",
            *([f"      name: {member_name}"] if member_name else []),
            *([f"      path: {member_path}"] if member_path else []),
            "    materialization:",
            "      required: true",
            "    operation_policy: inherit",
            "",
        ]
    )
    text = text.replace("prefer_subagent:", member + "prefer_subagent:")
    metadata.write_text(text, encoding="utf-8")


def test_deferred_remote_independent_review_identity() -> None:
    if not os.environ.get("WOR105_C02_REVIEW"):
        raise unittest.SkipTest("WOR105_C02_REVIEW selects the real independent review artifact")
    validated = validate_deferred_remote_independent_review_identity(REPO_ROOT, task_id="task-c02")
    assert validated["reviewed_tree"] == git(REPO_ROOT, "rev-parse", "HEAD^{tree}")


def canonical_repository_identity(repository: Path) -> dict[str, str]:
    orchestration = REPO_ROOT / "scripts/orchestration"
    command = "\n".join(
        [
            "import hashlib, json, sys",
            "from pathlib import Path",
            f"sys.path.insert(0, {str(orchestration)!r})",
            "from repository_preflight import capture_repository_evidence",
            "evidence = capture_repository_evidence(Path(sys.argv[1]))",
            "digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()",
            "print(json.dumps({'head': evidence['head'], 'tree': evidence['tree'], 'digest': digest}))",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", command, str(repository)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_deferred_remote_task_identity_equals_canonical_repository_evidence(tmp_path) -> None:
    _, repository, _ = make_remote(tmp_path, "canonical-identity-source")
    canonical = canonical_repository_identity(repository)
    identity = deferred_remote_task_identity(repository)
    bespoke_evidence = {
        "repository": repository.resolve().name,
        "branch": git(repository, "branch", "--show-current"),
        "head": canonical["head"],
        "tree": canonical["tree"],
        "status": "clean",
    }
    bespoke_digest = hashlib.sha256(
        json.dumps(bespoke_evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert identity["repository_evidence_sha256"] == canonical["digest"]
    assert identity["repository_evidence_sha256"] != bespoke_digest


def test_deferred_remote_review_identity_contract_rejects_mismatch(tmp_path, monkeypatch) -> None:
    _, repository, _ = make_remote(tmp_path, "identity-source")
    canonical = canonical_repository_identity(repository)
    identity = deferred_remote_task_identity(repository)
    assert identity["repository_evidence_sha256"] == canonical["digest"]
    review_path = tmp_path / "review.yaml"
    accepted = {
        "task_id": "task-c02",
        "reviewer_independent": True,
        "verdict": "accept",
        "reviewed_head": identity["reviewed_head"],
        "reviewed_tree": identity["reviewed_tree"],
    }
    review_path.write_text(json.dumps(accepted), encoding="utf-8")
    monkeypatch.setenv("WOR105_C02_REVIEW", str(review_path))
    assert validate_deferred_remote_independent_review_identity(
        repository, task_id="task-c02"
    )["reviewed_head"] == identity["reviewed_head"]

    for key, value in (
        ("task_id", "task-c01"),
        ("reviewer_independent", False),
        ("verdict", "repair"),
        ("reviewed_head", "0" * 40 + "+repository-evidence-sha256:" + "0" * 64),
        ("reviewed_tree", "0" * 40),
    ):
        review_path.write_text(json.dumps({**accepted, key: value}), encoding="utf-8")
        with unittest.TestCase().assertRaisesRegex(ControlPlaneError, "REVIEW_IDENTITY_MISMATCH"):
            validate_deferred_remote_independent_review_identity(repository, task_id="task-c02")

    bespoke_evidence = {
        "repository": repository.resolve().name,
        "branch": git(repository, "branch", "--show-current"),
        "head": canonical["head"],
        "tree": canonical["tree"],
        "status": "clean",
    }
    bespoke_digest = hashlib.sha256(
        json.dumps(bespoke_evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    review_path.write_text(
        json.dumps(
            {
                **accepted,
                "reviewed_head": f"{canonical['head']}+repository-evidence-sha256:{bespoke_digest}",
            }
        ),
        encoding="utf-8",
    )
    with unittest.TestCase().assertRaisesRegex(ControlPlaneError, "REVIEW_IDENTITY_MISMATCH"):
        validate_deferred_remote_independent_review_identity(repository, task_id="task-c02")


class CompositeMemberLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_v4_composite_schema_accepts_root_plus_named_members(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        write_composite_metadata(workspace)
        doctor = run_wb(config, "doctor-workspace", str(workspace))
        failures = json.loads(doctor.stdout)["portable"]["failures"]
        self.assertNotIn("WB_CONTROL_PLANE_WORKSPACE_MODE_INVALID", failures)
        self.assertNotIn("WB_CONTROL_PLANE_ROOT_BINDING_MODE_INVALID:source-main", failures)
        self.assertNotIn("WB_CONTROL_PLANE_MEMBER_BINDING_INVALID:execution-flow", failures)

    def test_v4_composite_schema_requires_exactly_one_named_root(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        write_composite_metadata(workspace, include_root=False)
        doctor = run_wb(config, "doctor-workspace", str(workspace))
        failures = json.loads(doctor.stdout)["portable"]["failures"]
        self.assertIn("WB_CONTROL_PLANE_COMPOSITE_ROOT_BINDING_INVALID", failures)

    def test_v4_composite_schema_requires_at_least_one_named_member(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        metadata = workspace / ".work-bundle/project.yaml"
        metadata.write_text(
            metadata.read_text(encoding="utf-8").replace(
                "  mode: single-repository", "  mode: composite"
            ),
            encoding="utf-8",
        )

        doctor = run_wb(config, "doctor-workspace", str(workspace))
        failures = json.loads(doctor.stdout)["portable"]["failures"]

        self.assertIn("WB_CONTROL_PLANE_COMPOSITE_MEMBER_REQUIRED", failures)

    def test_v4_composite_schema_rejects_duplicate_member_paths(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        write_composite_metadata(workspace)
        metadata = workspace / ".work-bundle/project.yaml"
        extra = "\n".join(
            [
                "  - id: other-flow",
                "    role: source",
                "    remote:",
                '      canonical: "https://example.com/other-flow"',
                "      aliases: []",
                "    default_branch: main",
                "    workspace_binding:",
                "      type: member",
                "      name: other-flow",
                "      path: execution-flow",
                "    materialization:",
                "      required: true",
                "    operation_policy: inherit",
                "",
            ]
        )
        metadata.write_text(
            metadata.read_text(encoding="utf-8").replace("prefer_subagent:", extra + "prefer_subagent:"),
            encoding="utf-8",
        )
        doctor = run_wb(config, "doctor-workspace", str(workspace))
        failures = json.loads(doctor.stdout)["portable"]["failures"]
        self.assertIn("WB_CONTROL_PLANE_MEMBER_PATH_DUPLICATE:execution-flow", failures)

    def test_v4_existing_modes_still_reject_crossed_bindings(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        metadata = workspace / ".work-bundle/project.yaml"
        text = metadata.read_text(encoding="utf-8")
        metadata.write_text(
            text.replace("prefer_subagent:", "\n".join([
                "  - id: extra-member",
                "    role: source",
                "    remote:",
                '      canonical: "https://example.com/extra"',
                "      aliases: []",
                "    default_branch: main",
                "    workspace_binding:",
                "      type: member",
                "      name: extra-member",
                "    materialization:",
                "      required: true",
                "    operation_policy: inherit",
                "prefer_subagent:",
            ])),
            encoding="utf-8",
        )
        doctor = run_wb(config, "doctor-workspace", str(workspace))
        failures = json.loads(doctor.stdout)["portable"]["failures"]
        self.assertIn("WB_CONTROL_PLANE_MEMBER_BINDING_INVALID:extra-member", failures)
        self.assertIn("WB_CONTROL_PLANE_SINGLE_REPOSITORY_BINDING_INVALID", failures)

    def test_add_workspace_member_dry_run_emits_digest_bound_proposal_without_writes(self) -> None:
        config, workspace, _, workspace_id = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        metadata = workspace / ".work-bundle/project.yaml"
        metadata_before = metadata.read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = (workspace / ".git/info/exclude").read_bytes()
        digest = hashlib.sha256(metadata_before).hexdigest()

        proposed = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(proposed.returncode, 0, proposed.stdout + proposed.stderr)
        self.assertNotIn("unknown command", proposed.stderr)
        data = json.loads(proposed.stdout)
        proposal = data["proposal"]
        self.assertEqual(data["status"], "passed")
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["changed_files"], [])
        self.assertTrue(data["proposal_id"])
        self.assertEqual(proposal["current_mode"], "single-repository")
        self.assertEqual(proposal["target_mode"], "composite")
        self.assertEqual(proposal["root"]["workspace_id"], workspace_id)
        self.assertEqual(proposal["root"]["repository_id"], "source-main")
        self.assertEqual(proposal["member"]["repository_id"], "execution-flow")
        self.assertEqual(proposal["member"]["name"], "execution-flow")
        self.assertEqual(proposal["member"]["path"], "execution-flow")
        self.assertEqual(proposal["member"]["remote"], str(member_remote.resolve()))
        self.assertEqual(proposal["member"]["default_branch"], "main")
        self.assertIn("execution-flow/", proposal["exclude_patterns"])
        self.assertEqual(proposal["device_binding_delta"]["checkout_kind"], "nested-member")
        self.assertEqual(
            Path(str(proposal["device_binding_delta"]["project_root"])).resolve(),
            (workspace / "execution-flow").resolve(),
        )
        self.assertEqual(proposal["metadata_digest"], digest)
        self.assertEqual(metadata.read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual((workspace / ".git/info/exclude").read_bytes(), exclude_before)
        self.assertFalse((workspace / "execution-flow").exists())

    def test_add_workspace_member_apply_rejects_digest_drift(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        proposed = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(proposed.returncode, 0, proposed.stdout + proposed.stderr)
        proposal_id = json.loads(proposed.stdout)["proposal_id"]
        metadata = workspace / ".work-bundle/project.yaml"
        metadata.write_text(metadata.read_text(encoding="utf-8").replace("slug: single-demo", "slug: drifted"), encoding="utf-8")

        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            proposal_id,
            "--apply",
        )
        self.assertEqual(applied.returncode, 1)
        data = json.loads(applied.stdout)
        self.assertEqual(data["failure_code"], "WB_CONTROL_PLANE_PROPOSAL_STALE")
        self.assertIn("  mode: single-repository", metadata.read_text(encoding="utf-8"))
        self.assertFalse((workspace / "execution-flow").exists())

    def test_add_workspace_member_first_apply_converts_and_publishes_recoverably(self) -> None:
        config, workspace, source_remote, workspace_id = init_single_v4(self.tmp_path)
        member_remote, _, member_head = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        root_readme = (workspace / "README.md").read_bytes()
        proposed = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(proposed.returncode, 0, proposed.stdout + proposed.stderr)
        proposal_id = json.loads(proposed.stdout)["proposal_id"]

        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            proposal_id,
            "--apply",
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        data = json.loads(applied.stdout)
        self.assertEqual(data["status"], "passed")
        self.assertIsNot(data.get("replay"), True)
        metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
        self.assertIn("  mode: composite", metadata)
        self.assertIn(workspace_id, metadata)
        self.assertIn("  - id: source-main", metadata)
        self.assertIn("      type: root", metadata)
        self.assertIn("  - id: execution-flow", metadata)
        self.assertIn("      type: member", metadata)
        self.assertIn("      name: execution-flow", metadata)
        self.assertIn("      path: execution-flow", metadata)
        self.assertNotIn("workspace_root:", metadata)
        self.assertNotIn("project_root:", metadata)
        self.assertTrue((workspace / "execution-flow/README.md").is_file())
        self.assertEqual(git(workspace / "execution-flow", "rev-parse", "HEAD"), member_head)
        self.assertEqual(
            Path(git(workspace / "execution-flow", "remote", "get-url", "origin")).resolve(),
            member_remote.resolve(),
        )
        self.assertEqual(git(workspace, "check-ignore", "--no-index", "execution-flow/README.md"), "execution-flow/README.md")
        self.assertEqual(git(workspace, "ls-files", "--", "execution-flow"), "")
        self.assertEqual((workspace / "README.md").read_bytes(), root_readme)
        self.assertEqual(git(workspace, "remote", "get-url", "origin"), str(source_remote))
        registry = (config / "registry/projects.yaml").read_text(encoding="utf-8")
        self.assertIn(str((workspace / "execution-flow").resolve()), registry)
        self.assertIn("checkout_kind: nested-member", registry)
        self.assertEqual(git(member_remote, "rev-parse", "HEAD"), member_head)

    def test_add_workspace_member_later_apply_is_add_only(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        first_remote, _, _ = make_remote(self.tmp_path / "member-a", "execution-flow")
        second_remote, _, _ = make_remote(self.tmp_path / "member-b", "second-flow")
        first = json.loads(run_wb(config, *add_workspace_member_args(workspace, first_remote), "--dry-run").stdout)
        self.assertEqual(
            run_wb(
                config,
                *add_workspace_member_args(workspace, first_remote),
                "--accepted-proposal-id",
                first["proposal_id"],
                "--apply",
            ).returncode,
            0,
        )
        second = json.loads(
            run_wb(
                config,
                *add_workspace_member_args(
                    workspace,
                    second_remote,
                    repository_id="second-flow",
                    name="second-flow",
                    path="second-flow",
                ),
                "--dry-run",
            ).stdout
        )
        self.assertEqual(second["proposal"]["current_mode"], "composite")
        self.assertEqual(second["proposal"]["target_mode"], "composite")
        applied = run_wb(
            config,
            *add_workspace_member_args(
                workspace,
                second_remote,
                repository_id="second-flow",
                name="second-flow",
                path="second-flow",
            ),
            "--accepted-proposal-id",
            second["proposal_id"],
            "--apply",
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        metadata = (workspace / ".work-bundle/project.yaml").read_text(encoding="utf-8")
        self.assertEqual(metadata.count("  - id: source-main"), 1)
        self.assertEqual(metadata.count("  - id: execution-flow"), 1)
        self.assertEqual(metadata.count("  - id: second-flow"), 1)
        self.assertIn("  mode: composite", metadata)
        self.assertTrue((workspace / "execution-flow/README.md").is_file())
        self.assertTrue((workspace / "second-flow/README.md").is_file())

    def test_add_workspace_member_matching_replay_is_idempotent(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        first = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        self.assertEqual(
            run_wb(
                config,
                *add_workspace_member_args(workspace, member_remote),
                "--accepted-proposal-id",
                first["proposal_id"],
                "--apply",
            ).returncode,
            0,
        )
        metadata_before = (workspace / ".work-bundle/project.yaml").read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        replay_proposal = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        replayed = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            replay_proposal["proposal_id"],
            "--apply",
        )
        self.assertEqual(replayed.returncode, 0, replayed.stdout + replayed.stderr)
        data = json.loads(replayed.stdout)
        self.assertEqual(data["status"], "passed")
        self.assertTrue(data["replay"])
        self.assertEqual(data["changed_files"], [])
        self.assertEqual((workspace / ".work-bundle/project.yaml").read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)

    def test_add_workspace_member_different_remote_or_path_collides(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        other_remote, _, _ = make_remote(self.tmp_path / "other-fixture", "other-flow")
        first = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        self.assertEqual(
            run_wb(
                config,
                *add_workspace_member_args(workspace, member_remote),
                "--accepted-proposal-id",
                first["proposal_id"],
                "--apply",
            ).returncode,
            0,
        )
        remote_collision = run_wb(config, *add_workspace_member_args(workspace, other_remote), "--dry-run")
        self.assertEqual(remote_collision.returncode, 1)
        self.assertEqual(json.loads(remote_collision.stdout)["failure_code"], "WB_CONTROL_PLANE_MEMBER_COLLISION")
        path_collision = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote, path="other-flow"),
            "--dry-run",
        )
        self.assertEqual(path_collision.returncode, 1)
        self.assertEqual(json.loads(path_collision.stdout)["failure_code"], "WB_CONTROL_PLANE_MEMBER_COLLISION")

    def test_add_workspace_member_rollback_restores_owned_state_only(self) -> None:
        config, workspace, source_remote, _ = init_single_v4(self.tmp_path)
        member_remote, _, member_head = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        user_exclude = workspace / ".git/info/exclude"
        user_exclude.write_text(user_exclude.read_text(encoding="utf-8") + "# keep-user-exclude\n", encoding="utf-8")
        metadata_before = (workspace / ".work-bundle/project.yaml").read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = user_exclude.read_bytes()
        proposed = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        os.chmod(config / "registry", 0o555)
        try:
            applied = run_wb(
                config,
                *add_workspace_member_args(workspace, member_remote),
                "--accepted-proposal-id",
                proposed["proposal_id"],
                "--apply",
            )
        finally:
            os.chmod(config / "registry", 0o755)
        self.assertEqual(applied.returncode, 1)
        self.assertEqual(json.loads(applied.stdout)["failure_code"], "WB_CONTROL_PLANE_TRANSACTION_FAILED")
        self.assertEqual((workspace / ".work-bundle/project.yaml").read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual(user_exclude.read_bytes(), exclude_before)
        self.assertFalse((workspace / "execution-flow").exists())
        self.assertEqual(git(workspace, "remote", "get-url", "origin"), str(source_remote))
        self.assertEqual(git(member_remote, "rev-parse", "HEAD"), member_head)

    def test_add_workspace_member_rejects_invalid_paths_and_tracked_root_index(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        for invalid in ("foo/bar", "../escape", ".work-bundle", "."):
            result = run_wb(config, *add_workspace_member_args(workspace, member_remote, path=invalid), "--dry-run")
            self.assertEqual(result.returncode, 1, invalid)
            code = json.loads(result.stdout)["failure_code"]
            self.assertIn(
                code,
                {
                    "WB_CONTROL_PLANE_MEMBER_PATH_INVALID",
                    "WB_CONTROL_PLANE_MEMBER_PATH_OVERLAPS_CONTROL_PLANE",
                },
            )
        tracked = workspace / "tracked-member"
        tracked.mkdir()
        (tracked / "README.md").write_text("owned by root\n", encoding="utf-8")
        git(workspace, "add", "tracked-member/README.md")
        git(workspace, "commit", "-q", "-m", "track nested path")
        tracked_result = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote, path="tracked-member", name="tracked-member"),
            "--dry-run",
        )
        self.assertEqual(tracked_result.returncode, 1)
        self.assertEqual(json.loads(tracked_result.stdout)["failure_code"], "WB_CONTROL_PLANE_MEMBER_PATH_TRACKED")

    def test_add_workspace_member_rejects_credential_remote_without_echo(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        secret_remote = "https://user:super-secret@example.com/execution-flow.git"
        result = run_wb(config, *add_workspace_member_args(workspace, secret_remote), "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["failure_code"], "WB_CONTROL_PLANE_REMOTE_CREDENTIALS_FORBIDDEN")
        self.assertNotIn("super-secret", result.stdout + result.stderr)

    def test_attach_and_doctor_reapply_composite_excludes_and_fail_closed_when_tracked(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        proposed = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            proposed["proposal_id"],
            "--apply",
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        exclude = workspace / ".git/info/exclude"
        kept = "\n".join(line for line in exclude.read_text(encoding="utf-8").splitlines() if "execution-flow" not in line)
        exclude.write_text(kept + "\n", encoding="utf-8")
        ignored = subprocess.run(
            ["git", "-C", str(workspace), "check-ignore", "--no-index", "execution-flow/README.md"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(ignored.returncode, 0)

        repaired = run_wb(config, "doctor-workspace", str(workspace), "--repair")
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertEqual(git(workspace, "check-ignore", "--no-index", "execution-flow/README.md"), "execution-flow/README.md")

        shutil.rmtree(workspace / "execution-flow" / ".git")
        git(workspace, "add", "-f", "execution-flow/README.md")
        git(workspace, "commit", "-q", "-m", "accidentally track member")
        doctor = run_wb(config, "doctor-workspace", str(workspace))
        self.assertEqual(doctor.returncode, 1)
        payload = json.loads(doctor.stdout)
        failures = payload["portable"]["failures"] + payload["local_binding"]["failures"]
        self.assertTrue(any("WB_CONTROL_PLANE_MEMBER_PATH_TRACKED" in item for item in failures))

    def test_add_workspace_member_rejects_unmaterialized_required_multi_source(self) -> None:
        config = config_root(self.tmp_path / "config-root")
        remote, _, _ = make_remote(self.tmp_path / "source-fixture", "source")
        workspace = self.tmp_path / "multi"
        initialized = run_wb(
            config,
            "init-workspace",
            str(workspace),
            "--mode",
            "multi-repository",
            "--slug",
            "multi-demo",
            "--repository",
            f"source-main={remote}",
            "--apply",
        )
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        result = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["failure_code"], "WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:source-main")

    def test_add_workspace_member_preflight_rejects_absent_binding_and_non_git_root(self) -> None:
        config, workspace, _, workspace_id = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        registry = config / "registry/projects.yaml"
        registry.write_text("projects: []\nbindings: []\n", encoding="utf-8")
        shutil.rmtree(workspace / ".git")
        metadata = workspace / ".work-bundle/project.yaml"
        metadata_before = metadata.read_bytes()
        registry_before = registry.read_bytes()

        dry = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(dry.returncode, 1, dry.stdout + dry.stderr)
        dry_payload = json.loads(dry.stdout)
        self.assertEqual(dry_payload["failure_code"], "WB_CONTROL_PLANE_BINDING_MISSING")
        self.assertNotIn("super-secret", dry.stdout + dry.stderr)

        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            "awm-unaccepted",
            "--apply",
        )
        self.assertEqual(applied.returncode, 1, applied.stdout + applied.stderr)
        applied_payload = json.loads(applied.stdout)
        self.assertEqual(applied_payload["failure_code"], "WB_CONTROL_PLANE_BINDING_MISSING")
        self.assertNotIn("super-secret", applied.stdout + applied.stderr)
        self.assertEqual(metadata.read_bytes(), metadata_before)
        self.assertEqual(registry.read_bytes(), registry_before)
        self.assertNotIn(workspace_id, registry.read_text(encoding="utf-8"))
        self.assertFalse((workspace / ".git/info/exclude").exists())
        self.assertFalse((workspace / "execution-flow").exists())

    def test_add_workspace_member_preflight_rejects_mismatched_or_incomplete_root_binding(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        registry = config / "registry/projects.yaml"
        original = registry.read_text(encoding="utf-8")
        bound_root = workspace.resolve()
        self.assertIn(f"workspace_root: {bound_root}", original)
        registry.write_text(
            original.replace(f"workspace_root: {bound_root}", f"workspace_root: {bound_root}-elsewhere"),
            encoding="utf-8",
        )
        mismatched = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(mismatched.returncode, 1, mismatched.stdout + mismatched.stderr)
        self.assertEqual(json.loads(mismatched.stdout)["failure_code"], "WB_CONTROL_PLANE_BINDING_ROOT_MISMATCH")

        incomplete = init_single_v4(self.tmp_path / "incomplete", slug="incomplete-demo", attach=False)
        incomplete_config, incomplete_workspace, _, _ = incomplete
        missing_root = run_wb(
            incomplete_config,
            *add_workspace_member_args(incomplete_workspace, member_remote),
            "--dry-run",
        )
        self.assertEqual(missing_root.returncode, 1, missing_root.stdout + missing_root.stderr)
        self.assertEqual(
            json.loads(missing_root.stdout)["failure_code"],
            "WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:source-main",
        )

        invalid_config, invalid_workspace, _, _ = init_single_v4(self.tmp_path / "invalid-git", slug="invalid-git")
        shutil.rmtree(invalid_workspace / ".git")
        invalid = run_wb(
            invalid_config,
            *add_workspace_member_args(invalid_workspace, member_remote),
            "--accepted-proposal-id",
            "awm-unaccepted",
            "--apply",
        )
        self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
        self.assertEqual(
            json.loads(invalid.stdout)["failure_code"],
            "WB_CONTROL_PLANE_BOUND_GIT_INVALID:source-main",
        )
        self.assertFalse((invalid_workspace / ".git/info/exclude").exists())
        self.assertFalse((invalid_workspace / "execution-flow").exists())

    def test_add_workspace_member_rejects_existing_wrong_branch_without_mutation(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        member_path = workspace / "execution-flow"
        subprocess.run(["git", "clone", "-q", str(member_remote), str(member_path)], check=True)
        git(member_path, "checkout", "-q", "-b", "other")
        metadata = workspace / ".work-bundle/project.yaml"
        metadata_before = metadata.read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = (workspace / ".git/info/exclude").read_bytes()

        dry = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(dry.returncode, 1, dry.stdout + dry.stderr)
        self.assertEqual(json.loads(dry.stdout)["failure_code"], "WB_CONTROL_PLANE_BRANCH_MISMATCH:execution-flow")
        self.assertEqual(git(member_path, "branch", "--show-current"), "other")

        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            "awm-unaccepted",
            "--apply",
        )
        self.assertEqual(applied.returncode, 1, applied.stdout + applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["failure_code"], "WB_CONTROL_PLANE_BRANCH_MISMATCH:execution-flow")
        self.assertEqual(git(member_path, "branch", "--show-current"), "other")
        self.assertEqual(metadata.read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual((workspace / ".git/info/exclude").read_bytes(), exclude_before)
        self.assertIn("  mode: single-repository", metadata.read_text(encoding="utf-8"))

    def test_add_workspace_member_verifies_branch_after_owned_clone(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        metadata = workspace / ".work-bundle/project.yaml"
        metadata_before = metadata.read_bytes()
        proposed = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote, default_branch="develop"),
            "--dry-run",
        )
        self.assertEqual(proposed.returncode, 0, proposed.stdout + proposed.stderr)
        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote, default_branch="develop"),
            "--accepted-proposal-id",
            json.loads(proposed.stdout)["proposal_id"],
            "--apply",
        )
        self.assertEqual(applied.returncode, 1, applied.stdout + applied.stderr)
        self.assertEqual(json.loads(applied.stdout)["failure_code"], "WB_CONTROL_PLANE_BRANCH_MISMATCH:execution-flow")
        self.assertEqual(metadata.read_bytes(), metadata_before)
        self.assertFalse((workspace / "execution-flow").exists())
        self.assertIn("  mode: single-repository", metadata.read_text(encoding="utf-8"))

    def _apply_first_member(self, config: Path, workspace: Path, member_remote: Path) -> None:
        proposed = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        applied = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            proposed["proposal_id"],
            "--apply",
        )
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)

    def test_add_workspace_member_preflight_rejects_root_remote_or_branch_drift(self) -> None:
        config, workspace, source_remote, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        other_remote, _, _ = make_remote(self.tmp_path / "other-root", "other-root")
        metadata = workspace / ".work-bundle/project.yaml"
        metadata_before = metadata.read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = (workspace / ".git/info/exclude").read_bytes()

        git(workspace, "remote", "set-url", "origin", str(other_remote))
        remote_dry = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(remote_dry.returncode, 1, remote_dry.stdout + remote_dry.stderr)
        self.assertEqual(json.loads(remote_dry.stdout)["failure_code"], "WB_CONTROL_PLANE_BOUND_REMOTE_CONFLICT:source-main")
        remote_apply = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            "awm-unaccepted",
            "--apply",
        )
        self.assertEqual(remote_apply.returncode, 1, remote_apply.stdout + remote_apply.stderr)
        self.assertEqual(json.loads(remote_apply.stdout)["failure_code"], "WB_CONTROL_PLANE_BOUND_REMOTE_CONFLICT:source-main")
        git(workspace, "remote", "set-url", "origin", str(source_remote))

        git(workspace, "checkout", "-q", "-b", "drifted")
        branch_dry = run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run")
        self.assertEqual(branch_dry.returncode, 1, branch_dry.stdout + branch_dry.stderr)
        self.assertEqual(json.loads(branch_dry.stdout)["failure_code"], "WB_CONTROL_PLANE_BRANCH_MISMATCH:source-main")
        branch_apply = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            "awm-unaccepted",
            "--apply",
        )
        self.assertEqual(branch_apply.returncode, 1, branch_apply.stdout + branch_apply.stderr)
        self.assertEqual(json.loads(branch_apply.stdout)["failure_code"], "WB_CONTROL_PLANE_BRANCH_MISMATCH:source-main")
        self.assertEqual(git(workspace, "branch", "--show-current"), "drifted")
        self.assertEqual(metadata.read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual((workspace / ".git/info/exclude").read_bytes(), exclude_before)
        self.assertFalse((workspace / "execution-flow").exists())
        self.assertIn("  mode: single-repository", metadata.read_text(encoding="utf-8"))

    def test_add_workspace_member_dry_run_rejects_invalid_target_proposal(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        metadata = workspace / ".work-bundle/project.yaml"
        metadata_before = metadata.read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = (workspace / ".git/info/exclude").read_bytes()

        empty_remote = run_wb(config, *add_workspace_member_args(workspace, ""), "--dry-run")
        self.assertEqual(empty_remote.returncode, 1, empty_remote.stdout + empty_remote.stderr)
        empty_remote_payload = json.loads(empty_remote.stdout)
        self.assertEqual(empty_remote_payload["failure_code"], "WB_CONTROL_PLANE_REMOTE_REQUIRED:execution-flow")
        self.assertNotIn("proposal_id", empty_remote_payload)
        self.assertNotIn("proposal", empty_remote_payload)

        empty_branch = run_wb(
            config,
            *add_workspace_member_args(workspace, "https://example.com/execution-flow", default_branch=""),
            "--dry-run",
        )
        self.assertEqual(empty_branch.returncode, 1, empty_branch.stdout + empty_branch.stderr)
        empty_branch_payload = json.loads(empty_branch.stdout)
        self.assertEqual(empty_branch_payload["failure_code"], "WB_CONTROL_PLANE_DEFAULT_BRANCH_MISSING:execution-flow")
        self.assertNotIn("proposal_id", empty_branch_payload)
        self.assertNotIn("proposal", empty_branch_payload)

        empty_branch_apply = run_wb(
            config,
            *add_workspace_member_args(workspace, "https://example.com/execution-flow", default_branch=""),
            "--accepted-proposal-id",
            "awm-unaccepted",
            "--apply",
        )
        self.assertEqual(empty_branch_apply.returncode, 1, empty_branch_apply.stdout + empty_branch_apply.stderr)
        self.assertEqual(
            json.loads(empty_branch_apply.stdout)["failure_code"],
            "WB_CONTROL_PLANE_DEFAULT_BRANCH_MISSING:execution-flow",
        )
        self.assertEqual(metadata.read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual((workspace / ".git/info/exclude").read_bytes(), exclude_before)
        self.assertFalse((workspace / "execution-flow").exists())
        self.assertIn("  mode: single-repository", metadata.read_text(encoding="utf-8"))

    def test_add_workspace_member_replay_rejects_missing_member_checkout(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        self._apply_first_member(config, workspace, member_remote)
        shutil.rmtree(workspace / "execution-flow")
        metadata_before = (workspace / ".work-bundle/project.yaml").read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = (workspace / ".git/info/exclude").read_bytes()

        replay_proposal = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        replayed = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            replay_proposal["proposal_id"],
            "--apply",
        )
        self.assertEqual(replayed.returncode, 1, replayed.stdout + replayed.stderr)
        payload = json.loads(replayed.stdout)
        self.assertEqual(payload["failure_code"], "WB_CONTROL_PLANE_BOUND_CHECKOUT_MISSING:execution-flow")
        self.assertIsNot(payload.get("replay"), True)
        self.assertEqual(payload["changed_files"], [])
        self.assertEqual((workspace / ".work-bundle/project.yaml").read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual((workspace / ".git/info/exclude").read_bytes(), exclude_before)
        self.assertFalse((workspace / "execution-flow").exists())

    def test_add_workspace_member_replay_rejects_missing_or_mismatched_member_device_binding(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        self._apply_first_member(config, workspace, member_remote)
        registry = config / "registry/projects.yaml"
        original_registry = registry.read_text(encoding="utf-8")
        metadata_before = (workspace / ".work-bundle/project.yaml").read_bytes()
        exclude_before = (workspace / ".git/info/exclude").read_bytes()
        member_head = git(workspace / "execution-flow", "rev-parse", "HEAD")

        registry.write_text(re.sub(r"      execution-flow:\n(?:        .*\n)+", "", original_registry), encoding="utf-8")
        missing_proposal = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        missing = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            missing_proposal["proposal_id"],
            "--apply",
        )
        self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(missing_payload["failure_code"], "WB_CONTROL_PLANE_MEMBER_DEVICE_BINDING_MISSING:execution-flow")
        self.assertIsNot(missing_payload.get("replay"), True)
        self.assertEqual(missing_payload["changed_files"], [])

        mismatched_kind = original_registry.replace(
            "        checkout_kind: nested-member\n",
            "        checkout_kind: managed-worktree\n",
            1,
        )
        registry.write_text(mismatched_kind, encoding="utf-8")
        kind_proposal = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        kind = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            kind_proposal["proposal_id"],
            "--apply",
        )
        self.assertEqual(kind.returncode, 1, kind.stdout + kind.stderr)
        kind_payload = json.loads(kind.stdout)
        self.assertEqual(kind_payload["failure_code"], "WB_CONTROL_PLANE_MEMBER_DEVICE_BINDING_MISMATCH:execution-flow")
        self.assertIsNot(kind_payload.get("replay"), True)

        member_path = str((workspace / "execution-flow").resolve())
        mismatched_path = original_registry.replace(
            f"        project_root: {member_path}\n",
            f"        project_root: {member_path}-stale\n",
            1,
        )
        registry.write_text(mismatched_path, encoding="utf-8")
        path_proposal = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        path = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            path_proposal["proposal_id"],
            "--apply",
        )
        self.assertEqual(path.returncode, 1, path.stdout + path.stderr)
        path_payload = json.loads(path.stdout)
        self.assertEqual(path_payload["failure_code"], "WB_CONTROL_PLANE_MEMBER_DEVICE_BINDING_MISMATCH:execution-flow")
        self.assertIsNot(path_payload.get("replay"), True)
        self.assertEqual((workspace / ".work-bundle/project.yaml").read_bytes(), metadata_before)
        self.assertEqual((workspace / ".git/info/exclude").read_bytes(), exclude_before)
        self.assertEqual(git(workspace / "execution-flow", "rev-parse", "HEAD"), member_head)
        self.assertTrue((workspace / "execution-flow/README.md").is_file())

    def test_add_workspace_member_replay_rejects_missing_exclude(self) -> None:
        config, workspace, _, _ = init_single_v4(self.tmp_path)
        member_remote, _, _ = make_remote(self.tmp_path / "member-fixture", "execution-flow")
        self._apply_first_member(config, workspace, member_remote)
        exclude = workspace / ".git/info/exclude"
        kept = "\n".join(line for line in exclude.read_text(encoding="utf-8").splitlines() if "execution-flow" not in line)
        exclude.write_text(kept + "\n", encoding="utf-8")
        metadata_before = (workspace / ".work-bundle/project.yaml").read_bytes()
        registry_before = (config / "registry/projects.yaml").read_bytes()
        exclude_before = exclude.read_bytes()

        replay_proposal = json.loads(run_wb(config, *add_workspace_member_args(workspace, member_remote), "--dry-run").stdout)
        replayed = run_wb(
            config,
            *add_workspace_member_args(workspace, member_remote),
            "--accepted-proposal-id",
            replay_proposal["proposal_id"],
            "--apply",
        )
        self.assertEqual(replayed.returncode, 1, replayed.stdout + replayed.stderr)
        payload = json.loads(replayed.stdout)
        self.assertEqual(payload["failure_code"], "WB_CONTROL_PLANE_MEMBER_EXCLUDE_MISSING:execution-flow")
        self.assertIsNot(payload.get("replay"), True)
        self.assertEqual(payload["changed_files"], [])
        self.assertEqual((workspace / ".work-bundle/project.yaml").read_bytes(), metadata_before)
        self.assertEqual((config / "registry/projects.yaml").read_bytes(), registry_before)
        self.assertEqual(exclude.read_bytes(), exclude_before)
        self.assertTrue((workspace / "execution-flow/README.md").is_file())
