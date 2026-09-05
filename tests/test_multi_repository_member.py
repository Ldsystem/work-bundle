"""Public lifecycle regression tests for adding members to a non-Git v4 root."""
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from test_control_plane_v4 import (
    add_workspace_member_args, config_root, git, init_single_v4, make_remote, run_wb,
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


def deferred_args(workspace, *, replay_key="replay-c02", default_branch="main"):
    return [
        "defer-workspace-member", str(workspace),
        "--repository-id", "execution-flow",
        "--name", "execution-flow",
        "--path", "execution-flow",
        "--default-branch", default_branch,
        "--replay-key", replay_key,
    ]


def attach_deferred_args(workspace, remote):
    return [
        "attach-deferred-remote", str(workspace),
        "--repository-id", "execution-flow",
        "--remote", str(remote),
    ]


def test_deferred_remote_apply_replay_and_attach_are_portable_and_idempotent(multi):
    config, workspace, remote = multi
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    member_path = workspace / "execution-flow"

    dry = run_wb(config, *deferred_args(workspace), "--dry-run")
    assert dry.returncode == 0, dry.stdout + dry.stderr
    proposal = json.loads(dry.stdout)
    assert proposal["member"]["remote"] is None
    assert proposal["member"]["materialization"] == "deferred"
    assert proposal["member"]["device_binding"] is None
    assert not member_path.exists()

    applied = run_wb(
        config, *deferred_args(workspace), "--accepted-proposal-id", proposal["proposal_id"], "--apply"
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert not member_path.exists()
    portable = yaml.safe_load(metadata.read_text())
    deferred = portable["source_repositories"][-1]
    assert deferred["remote"]["canonical"] is None
    assert deferred["materialization"] == {"required": True, "state": "deferred"}
    assert deferred["deferred_remote"]["replay_key"] == "replay-c02"
    bindings = yaml.safe_load(registry.read_text())["device_bindings"]
    assert "execution-flow" not in next(iter(bindings.values()))["repositories"]
    doctor = run_wb(config, "doctor-workspace", str(workspace))
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    generic_attach = run_wb(config, "attach-workspace", str(workspace), "--materialize", "missing", "--apply")
    assert generic_attach.returncode == 0, generic_attach.stdout + generic_attach.stderr
    assert not member_path.exists()

    before = metadata.read_bytes(), registry.read_bytes()
    replay = run_wb(
        config, *deferred_args(workspace), "--accepted-proposal-id", proposal["proposal_id"], "--apply"
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert json.loads(replay.stdout)["replay"] is True
    assert json.loads(replay.stdout)["changed_files"] == []
    assert before == (metadata.read_bytes(), registry.read_bytes())

    attach_dry = run_wb(config, *attach_deferred_args(workspace, remote), "--dry-run")
    assert attach_dry.returncode == 0, attach_dry.stdout + attach_dry.stderr
    attached = run_wb(
        config,
        *attach_deferred_args(workspace, remote),
        "--accepted-proposal-id", json.loads(attach_dry.stdout)["proposal_id"],
        "--apply",
    )
    assert attached.returncode == 0, attached.stdout + attached.stderr
    record = json.loads(attached.stdout)["member"]
    assert record["materialization"] == "attached"
    assert set(record["device_binding"]) == {
        "device_id", "checkout_path_token", "remote_fingerprint", "observed_revision", "observed_tree"
    }
    assert git(member_path, "branch", "--show-current") == "main"
    assert yaml.safe_load(metadata.read_text())["source_repositories"][-1]["materialization"]["state"] == "attached"


def test_deferred_remote_attach_rejects_stale_and_collision_without_mutation(multi):
    config, workspace, remote = multi
    proposal = json.loads(run_wb(config, *deferred_args(workspace), "--dry-run").stdout)
    applied = run_wb(
        config, *deferred_args(workspace), "--accepted-proposal-id", proposal["proposal_id"], "--apply"
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    attach = json.loads(run_wb(config, *attach_deferred_args(workspace, remote), "--dry-run").stdout)
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    metadata.write_text(metadata.read_text() + "owner_field: changed\n")
    before = metadata.read_bytes(), registry.read_bytes()
    stale = run_wb(
        config,
        *attach_deferred_args(workspace, remote),
        "--accepted-proposal-id", attach["proposal_id"],
        "--apply",
    )
    assert stale.returncode == 1
    assert json.loads(stale.stdout)["failure_code"] == "WB_CONTROL_PLANE_PROPOSAL_STALE"
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert not (workspace / "execution-flow").exists()

    fresh = json.loads(run_wb(config, *attach_deferred_args(workspace, remote), "--dry-run").stdout)
    (workspace / "execution-flow").mkdir()
    before = metadata.read_bytes(), registry.read_bytes()
    collision = run_wb(
        config,
        *attach_deferred_args(workspace, remote),
        "--accepted-proposal-id", fresh["proposal_id"],
        "--apply",
    )
    assert collision.returncode == 1
    assert json.loads(collision.stdout)["failure_code"] == "WB_CONTROL_PLANE_MEMBER_COLLISION"
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert (workspace / "execution-flow").is_dir()


def test_deferred_remote_attach_interruption_rolls_back_and_retry_converges(multi, monkeypatch, capsys):
    import control_plane

    config, workspace, remote = multi
    proposal = json.loads(run_wb(config, *deferred_args(workspace), "--dry-run").stdout)
    applied = run_wb(
        config, *deferred_args(workspace), "--accepted-proposal-id", proposal["proposal_id"], "--apply"
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr
    attach = json.loads(run_wb(config, *attach_deferred_args(workspace, remote), "--dry-run").stdout)
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    before = metadata.read_bytes(), registry.read_bytes()
    original_publish = control_plane._atomic_publish
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config))
    monkeypatch.setattr(control_plane, "_atomic_publish", lambda payloads: (_ for _ in ()).throw(OSError("injected")))

    result = control_plane.cmd_attach_deferred_remote(
        attach_deferred_args(workspace, remote)[1:]
        + ["--accepted-proposal-id", attach["proposal_id"], "--apply"]
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out)["failure_code"] == "WB_CONTROL_PLANE_TRANSACTION_FAILED"
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert not (workspace / "execution-flow").exists()

    monkeypatch.setattr(control_plane, "_atomic_publish", original_publish)
    retried = run_wb(
        config,
        *attach_deferred_args(workspace, remote),
        "--accepted-proposal-id", attach["proposal_id"],
        "--apply",
    )
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert json.loads(retried.stdout)["member"]["materialization"] == "attached"


def test_deferred_remote_composite_attach_rejects_external_git_common_dir(tmp_path):
    config, workspace, remote, _ = init_single_v4(tmp_path / "workspace")
    proposal = json.loads(
        run_wb(config, *deferred_args(workspace, default_branch="main-local"), "--dry-run").stdout
    )
    applied = run_wb(
        config,
        *deferred_args(workspace, default_branch="main-local"),
        "--accepted-proposal-id", proposal["proposal_id"],
        "--apply",
    )
    assert applied.returncode == 0, applied.stdout + applied.stderr

    external = tmp_path / "external-owner"
    subprocess.run(["git", "clone", "-q", str(remote), str(external)], check=True)
    git(external, "branch", "main-local")
    member = workspace / "execution-flow"
    git(external, "worktree", "add", "-q", str(member), "main-local")
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    before = metadata.read_bytes(), registry.read_bytes()

    attach = run_wb(config, *attach_deferred_args(workspace, remote), "--dry-run")

    assert attach.returncode == 1
    assert json.loads(attach.stdout)["failure_code"] == "WB_CONTROL_PLANE_BOUND_GIT_INVALID:execution-flow"
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert Path(git(member, "rev-parse", "--path-format=absolute", "--git-common-dir")).is_relative_to(external)


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


@pytest.mark.parametrize("mode", ["single", "multi"])
@pytest.mark.parametrize("shape", ["commented-header", "anchored-header", "quoted-key", "quoted-nested", "commented-control", "owner-flow", "owner-comment"])
@pytest.mark.parametrize("dependency_free", [False, True])
def test_member_add_preserves_yaml_section_boundaries(multi, tmp_path, monkeypatch, mode, shape, dependency_free):
    config, workspace, remote = multi
    if mode == "single":
        config, workspace, _, _ = init_single_v4(tmp_path / "single")
    metadata = workspace / ".work-bundle/project.yaml"
    text = metadata.read_text()
    if shape == "commented-header":
        text = text.replace("source_repositories:", "source_repositories: # managed members")
    elif shape == "anchored-header":
        text = text.replace("source_repositories:", "source_repositories: &sources")
    elif shape == "quoted-key":
        text = text.replace("prefer_subagent:", "'custom_owner_field': retained\nprefer_subagent:")
    elif shape == "quoted-nested":
        text = text.replace("prefer_subagent:", "'owner_settings':\n  contact:\n    team: engineering\nprefer_subagent:")
    elif shape == "commented-control":
        text = text.replace("control_plane:", "control_plane: # portable settings")
    elif shape == "owner-flow":
        text += "owner_settings: {}\n"
    else:
        text += "owner_settings: # retained\n  team: engineering\n"
    metadata.write_text(text)
    original = yaml.safe_load(text)
    if dependency_free:
        # Exercise the actual CLI without its optional YAML dependency, while
        # retaining PyYAML in the test process as an independent output oracle.
        no_yaml = tmp_path / "no-yaml"
        no_yaml.mkdir()
        (no_yaml / "yaml.py").write_text("raise ImportError('dependency-free regression')\n")
        monkeypatch.setenv("PYTHONPATH", str(no_yaml))
    proposal = propose(config, workspace, remote)
    assert metadata.read_text() == text
    result = apply(config, workspace, remote, proposal)
    assert result.returncode == 0, result.stdout + result.stderr
    document = yaml.safe_load(metadata.read_text())
    assert len(document["source_repositories"]) == 2
    assert document["source_repositories"][0] == original["source_repositories"][0]
    for key, value in original.items():
        if key not in {"source_repositories", "workspace"}:
            assert document[key] == value
    if shape == "quoted-key":
        assert document["custom_owner_field"] == "retained"
    elif shape == "commented-header":
        assert "source_repositories: # managed members" in metadata.read_text()
    elif shape == "anchored-header":
        assert "source_repositories: &sources" in metadata.read_text()
    elif shape == "commented-control":
        assert "control_plane: # portable settings" in metadata.read_text()
    elif shape == "owner-comment":
        assert "owner_settings: # retained\n  team: engineering\n" in metadata.read_text()
    replay = apply(config, workspace, remote, propose(config, workspace, remote))
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert json.loads(replay.stdout)["changed_files"] == []


def test_member_add_rejects_misplaced_rendered_block_without_mutation(multi, monkeypatch, capsys):
    import control_plane

    config, workspace, remote = multi
    monkeypatch.setenv("WB_CONFIG_ROOT", str(config))
    # Inject the publication defect reported in review: the generated member
    # appears after a root scalar instead of inside source_repositories.
    monkeypatch.setattr(control_plane, "_append_member_metadata", lambda text, member:
                        text + control_plane._render_member_metadata_block(member, multi=True))
    metadata = workspace / ".work-bundle/project.yaml"
    registry = config / "registry/projects.yaml"
    before = metadata.read_bytes(), registry.read_bytes()
    result = control_plane.cmd_add_workspace_member(add_workspace_member_args(workspace, remote)[1:] + ["--dry-run"])
    assert result == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["failure_code"] == "WB_CONTROL_PLANE_METADATA_INVALID"
    assert "Traceback" not in output.err
    assert before == (metadata.read_bytes(), registry.read_bytes())
    assert not (workspace / "execution-flow").exists()
