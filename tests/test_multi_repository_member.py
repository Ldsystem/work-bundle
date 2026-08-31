"""Public lifecycle regression tests for adding members to a non-Git v4 root."""
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from test_control_plane_v4 import (
    add_workspace_member_args, config_root, git, make_remote, run_wb,
)


@pytest.fixture
def multi(tmp_path):
    config = config_root(tmp_path)
    remote, _, _ = make_remote(tmp_path, "source")
    workspace = tmp_path / "workspace"
    result = run_wb(config, "init-workspace", str(workspace), "--slug", "multi",
                    "--repository", f"source-main={remote}", "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    result = run_wb(config, "attach-workspace", str(workspace), "--materialize", "missing", "--apply")
    assert result.returncode == 0, result.stdout + result.stderr
    member_remote, _, _ = make_remote(tmp_path, "new-source")
    return config, workspace, member_remote


def propose(config, workspace, remote, **kwargs):
    result = run_wb(config, *add_workspace_member_args(workspace, remote, **kwargs), "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def apply(config, workspace, remote, proposal, **kwargs):
    return run_wb(config, *add_workspace_member_args(workspace, remote, **kwargs),
                  "--accepted-proposal-id", proposal["proposal_id"], "--apply")


@pytest.mark.parametrize("adopt", [False, True])
def test_multi_member_add_preserves_mode_and_replays_without_root_git(multi, adopt):
    config, workspace, remote = multi
    member = workspace / "execution-flow"
    if adopt:
        subprocess.run(["git", "clone", "-q", str(remote), str(member)], check=True)
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    original = metadata.read_text()
    # Extra top-level fields must not capture the appended repository block.
    original = original.replace("prefer_subagent: false\n", "") + "custom_owner_field: retained\n"
    metadata.write_text(original)
    before = metadata.read_bytes(), registry.read_bytes()
    proposal = propose(config, workspace, remote)
    assert proposal["proposal"]["target_mode"] == "multi-repository"
    assert proposal["proposal"]["exclude_patterns"] == []
    assert before == (metadata.read_bytes(), registry.read_bytes())
    result = apply(config, workspace, remote, proposal)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mode: multi-repository" in metadata.read_text()
    assert "custom_owner_field: retained" in metadata.read_text()
    assert not (workspace / ".git").exists()
    assert git(member, "rev-parse", "HEAD") == git(remote, "rev-parse", "HEAD")
    portable = yaml.safe_load(metadata.read_text())
    assert len(portable["source_repositories"]) == 2
    assert portable["source_repositories"][1]["workspace_binding"] == {"type": "member", "name": "execution-flow"}
    binding = yaml.safe_load(registry.read_text())["device_bindings"][portable["workspace"]["id"]]
    assert binding["repositories"]["execution-flow"]["checkout_kind"] == "managed-worktree"
    before = metadata.read_bytes(), registry.read_bytes()
    replay = apply(config, workspace, remote, propose(config, workspace, remote))
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert json.loads(replay.stdout)["replay"] is True
    assert json.loads(replay.stdout)["changed_files"] == []
    assert before == (metadata.read_bytes(), registry.read_bytes())
    for command in ("doctor-workspace", "attach-workspace"):
        extra = ("--materialize", "none", "--apply") if command == "attach-workspace" else ()
        checked = run_wb(config, command, str(workspace), *extra)
        assert checked.returncode == 0, checked.stdout + checked.stderr
    assert not (workspace / ".git").exists()


@pytest.mark.parametrize("adopt", [False, True])
def test_multi_member_failure_preserves_existing_and_removes_only_owned_checkout(multi, adopt):
    config, workspace, remote = multi
    member = workspace / "execution-flow"
    if adopt:
        subprocess.run(["git", "clone", "-q", str(remote), str(member)], check=True)
    proposal = propose(config, workspace, remote)
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    before = metadata.read_bytes(), registry.read_bytes()
    os.chmod(config / "registry", 0o555)
    try:
        result = apply(config, workspace, remote, proposal)
    finally:
        os.chmod(config / "registry", 0o755)
    assert result.returncode == 1
    assert json.loads(result.stdout)["failure_code"] == "WB_CONTROL_PLANE_TRANSACTION_FAILED"
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert member.exists() is adopt
    assert not (workspace / ".git").exists()


def test_multi_member_rejects_stale_proposal_and_name_path_disagreement(multi):
    config, workspace, remote = multi
    proposal = propose(config, workspace, remote)
    metadata = workspace / ".work-bundle/project.yaml"
    metadata.write_text(metadata.read_text() + "custom_field: changed\n")
    result = apply(config, workspace, remote, proposal)
    assert json.loads(result.stdout)["failure_code"] == "WB_CONTROL_PLANE_PROPOSAL_STALE"
    result = run_wb(config, *add_workspace_member_args(workspace, remote, path="different"), "--dry-run")
    assert result.returncode == 1
    assert not (workspace / "execution-flow").exists()


@pytest.mark.parametrize("unsafe", ["symlink", "external-git-store", "wrong-branch", "dirty"])
def test_multi_member_rejects_unsafe_existing_checkout_without_mutation(multi, tmp_path, unsafe):
    config, workspace, remote = multi
    member = workspace / "execution-flow"
    external = tmp_path / "external"
    if unsafe == "symlink":
        subprocess.run(["git", "clone", "-q", str(remote), str(external)], check=True)
        member.symlink_to(external, target_is_directory=True)
    elif unsafe == "external-git-store":
        subprocess.run(["git", "clone", "-q", str(remote), str(external)], check=True)
        git(external, "worktree", "add", "--detach", str(member), "HEAD")
        git(member, "checkout", "-b", "main-local")
    else:
        subprocess.run(["git", "clone", "-q", str(remote), str(member)], check=True)
        if unsafe == "wrong-branch":
            git(member, "checkout", "-b", "other")
        else:
            (member / "user.txt").write_text("preserve me")
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    before = metadata.read_bytes(), registry.read_bytes()
    kwargs = {"default_branch": "main-local"} if unsafe == "external-git-store" else {}
    result = run_wb(config, *add_workspace_member_args(workspace, remote, **kwargs), "--dry-run")
    assert result.returncode == 1
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert member.exists()
    assert not (workspace / ".git").exists()


def test_multi_member_refuses_missing_required_existing_source(multi):
    config, workspace, remote = multi
    (workspace / "source-main").rename(workspace / "source-moved")
    result = run_wb(config, *add_workspace_member_args(workspace, remote), "--dry-run")
    assert result.returncode == 1
    assert "source-main" in result.stdout
    assert not (workspace / "execution-flow").exists()


@pytest.mark.parametrize("name", [".git", "script", "credentials", ".work-bundle", "../escape"])
def test_multi_member_rejects_reserved_or_escaping_paths(multi, name):
    config, workspace, remote = multi
    result = run_wb(config, *add_workspace_member_args(workspace, remote, name=name, path=name), "--dry-run")
    assert result.returncode == 1
    assert "MEMBER_PATH" in result.stdout
    assert not (workspace / ".git").exists()


@pytest.mark.parametrize("damage", ["missing", "kind", "path"])
def test_multi_member_replay_refuses_incomplete_binding(multi, damage):
    config, workspace, remote = multi
    result = apply(config, workspace, remote, propose(config, workspace, remote))
    assert result.returncode == 0, result.stdout + result.stderr
    registry = config / "registry/projects.yaml"
    data = yaml.safe_load(registry.read_text())
    binding = next(iter(data["device_bindings"].values()))["repositories"]
    if damage == "missing":
        del binding["execution-flow"]
    elif damage == "kind":
        binding["execution-flow"]["checkout_kind"] = "nested-member"
    else:
        binding["execution-flow"]["project_root"] = str(workspace / "source-main")
    registry.write_text(yaml.safe_dump(data, sort_keys=False))
    before = registry.read_bytes()
    dry = run_wb(config, *add_workspace_member_args(workspace, remote), "--dry-run")
    if dry.returncode == 0:
        result = apply(config, workspace, remote, json.loads(dry.stdout))
    else:
        result = dry
    assert result.returncode == 1
    assert before == registry.read_bytes()
    assert not (workspace / ".git").exists()


def test_multi_member_add_only_and_collisions(multi, tmp_path):
    config, workspace, remote = multi
    result = apply(config, workspace, remote, propose(config, workspace, remote))
    assert result.returncode == 0, result.stdout + result.stderr
    second, _, _ = make_remote(tmp_path, "second-source")
    args = {"repository_id": "second", "name": "second", "path": "second"}
    result = apply(config, workspace, second, propose(config, workspace, second, **args), **args)
    assert result.returncode == 0, result.stdout + result.stderr
    metadata = workspace / ".work-bundle/project.yaml"
    before = metadata.read_bytes()
    result = run_wb(config, *add_workspace_member_args(workspace, second), "--dry-run")
    assert result.returncode == 1
    assert before == metadata.read_bytes()
    assert len(yaml.safe_load(before)["source_repositories"]) == 3
