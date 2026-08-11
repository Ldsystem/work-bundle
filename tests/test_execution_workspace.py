from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "work-bundle"))

from execution_workspace import (  # noqa: E402
    ExecutionWorkspaceError,
    cleanup_owned,
    doctor_stale,
    hydrate_workspace,
    register_existing,
    prepare_worktree,
    state_path,
    workspace_status,
)
from instruction_audit import audit_instructions  # noqa: E402


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def seed_repository(root: Path) -> None:
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "seed"], check=True)


def prepare_fixture(tmp_path: Path, *, execution_id: str = "exec-1") -> tuple[Path, Path, dict[str, object]]:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    seed_repository(source)
    result = prepare_worktree(
        source,
        workspace_id="workspace-1",
        execution_id=execution_id,
        repository_id="repo-1",
        branch=f"codex/{execution_id}",
        created_for="task-1",
        runtime_root=runtime,
    )
    return source, runtime, result


def test_project_template_declares_hydration_profiles_and_runtime_ignore() -> None:
    project_template = (REPO_ROOT / "references/assets/template/project.yaml").read_text(encoding="utf-8")
    ignore_template = (REPO_ROOT / "references/assets/template/.gitignore.template").read_text(encoding="utf-8")
    assert "execution_workspace_profiles:" in project_template
    assert "strategy: regenerate" in project_template
    assert "strategy: credential-inject" in project_template
    assert "strategy: copy" in project_template
    assert "sensitivity: non-secret" in project_template
    assert ".work-bundle/" in ignore_template


def test_hydration_classifies_regenerate_copy_and_credential_without_reading_secret(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    (source / "config").mkdir(parents=True)
    target.mkdir()
    (source / "config/local.yaml").write_text("local: true\n", encoding="utf-8")
    secret = source / ".env.local"
    secret.write_text("SYNTHETIC_PRIVATE_VALUE\n", encoding="utf-8")
    profile = {
        "hydrate": [
            {"path": ".codegraph", "strategy": "regenerate"},
            {"path": "config/local.yaml", "strategy": "copy", "sensitivity": "non-secret"},
            {"path": ".env.local", "strategy": "credential-inject"},
        ]
    }

    report = hydrate_workspace(source, target, profile)

    assert [item["classification"] for item in report] == [
        "regenerate-required", "copied-non-secret", "credential-boundary-required"
    ]
    assert (target / "config/local.yaml").read_text(encoding="utf-8") == "local: true\n"
    assert not (target / ".env.local").exists()
    assert "SYNTHETIC_PRIVATE_VALUE" not in json.dumps(report)


@pytest.mark.parametrize(
    ("path", "sensitivity"),
    [(".env.local", "non-secret"), ("credentials/credentials.yaml", "non-secret"), ("config/local.yaml", "secret")],
)
def test_hydration_copy_fails_closed_for_secret_or_credential_paths(
    tmp_path: Path, path: str, sensitivity: str
) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    candidate = source / path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("SYNTHETIC_PRIVATE_VALUE\n", encoding="utf-8")
    target.mkdir()
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_HYDRATION_SECRET_COPY_FORBIDDEN"):
        hydrate_workspace(
            source,
            target,
            {"hydrate": [{"path": path, "strategy": "copy", "sensitivity": sensitivity}]},
        )
    assert "SYNTHETIC_PRIVATE_VALUE" not in repr(sys.exc_info())


def test_symlink_readonly_requires_nonwritable_source_and_refuses_write_through(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    shared = source / "shared.idx"
    shared.write_text("index\n", encoding="utf-8")
    profile = {
        "hydrate": [
            {
                "path": "shared.idx",
                "strategy": "symlink-readonly",
                "sensitivity": "non-secret",
                "concurrent_safe": True,
            }
        ]
    }

    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_SYMLINK_SOURCE_WRITABLE"):
        hydrate_workspace(source, target, profile)

    shared.chmod(0o444)
    report = hydrate_workspace(source, target, profile)
    linked = target / "shared.idx"
    assert report[0]["classification"] == "symlinked-readonly"
    assert linked.is_symlink()
    with pytest.raises(PermissionError):
        linked.write_text("mutation\n", encoding="utf-8")


def test_prepare_records_provenance_status_and_cleanup_owned(tmp_path: Path) -> None:
    source, runtime, prepared = prepare_fixture(tmp_path)
    workspace = Path(str(prepared["execution_workspace_state"]["path"]))
    state = prepared["execution_workspace_state"]
    assert state["kind"] == "worktree"
    assert state["owner"] == "work-bundle"
    assert state["cleanup_policy"] == "after_integration"
    assert git(workspace, "branch", "--show-current") == "codex/exec-1"

    status = workspace_status(runtime, "workspace-1", "exec-1", "repo-1")
    assert status["status"] == "active"
    assert status["git_identity"] == "matched"

    cleaned = cleanup_owned(runtime, "workspace-1", "exec-1", "repo-1")
    assert cleaned["status"] == "cleaned"
    assert not workspace.exists()
    assert not state_path(runtime, "workspace-1", "exec-1", "repo-1").exists()
    assert str(workspace) not in git(source, "worktree", "list", "--porcelain")


def test_prepare_rejects_target_collision_without_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    seed_repository(source)
    target = runtime / "workspace-1/exec-1/repo-1"
    target.mkdir(parents=True)
    (target / "user.txt").write_text("preserve\n", encoding="utf-8")
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_WORKSPACE_COLLISION"):
        prepare_worktree(
            source,
            workspace_id="workspace-1",
            execution_id="exec-1",
            repository_id="repo-1",
            branch="codex/exec-1",
            created_for="task-1",
            runtime_root=runtime,
        )
    assert (target / "user.txt").read_text(encoding="utf-8") == "preserve\n"


def test_failed_hydration_rolls_back_worktree_and_owned_branch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    seed_repository(source)
    (source / ".env.local").write_text("SYNTHETIC_PRIVATE_VALUE\n", encoding="utf-8")
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_HYDRATION_SECRET_COPY_FORBIDDEN"):
        prepare_worktree(
            source,
            workspace_id="workspace-1",
            execution_id="exec-1",
            repository_id="repo-1",
            branch="codex/exec-1",
            created_for="task-1",
            runtime_root=runtime,
            profile={
                "hydrate": [
                    {"path": ".env.local", "strategy": "copy", "sensitivity": "non-secret"}
                ]
            },
        )
    assert not (runtime / "workspace-1/exec-1/repo-1").exists()
    branches = git(source, "branch", "--format=%(refname:short)").splitlines()
    assert "codex/exec-1" not in branches


def test_cleanup_owned_removes_explicit_non_secret_hydration(tmp_path: Path) -> None:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    seed_repository(source)
    (source / "local.cfg").write_text("local=true\n", encoding="utf-8")
    prepared = prepare_worktree(
        source,
        workspace_id="workspace-1",
        execution_id="exec-1",
        repository_id="repo-1",
        branch="codex/exec-1",
        created_for="task-1",
        runtime_root=runtime,
        profile={
            "hydrate": [
                {"path": "local.cfg", "strategy": "copy", "sensitivity": "non-secret"}
            ]
        },
    )
    workspace = Path(str(prepared["execution_workspace_state"]["path"]))
    assert (workspace / "local.cfg").is_file()
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_WORKSPACE_DIRTY"):
        cleanup_owned(runtime, "workspace-1", "exec-1", "repo-1")
    (workspace / "local.cfg").unlink()
    assert cleanup_owned(runtime, "workspace-1", "exec-1", "repo-1")["status"] == "cleaned"
    assert not workspace.exists()


def test_cleanup_refuses_user_owned_and_identity_mismatch(tmp_path: Path) -> None:
    _, runtime, prepared = prepare_fixture(tmp_path)
    workspace = Path(str(prepared["execution_workspace_state"]["path"]))
    record = state_path(runtime, "workspace-1", "exec-1", "repo-1")
    data = json.loads(record.read_text(encoding="utf-8"))
    data["execution_workspace_state"]["owner"] = "user"
    record.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_WORKSPACE_NOT_OWNED"):
        cleanup_owned(runtime, "workspace-1", "exec-1", "repo-1")
    assert workspace.is_dir()

    data["execution_workspace_state"]["owner"] = "work-bundle"
    data["git_identity"]["git_common_dir"] = str(tmp_path / "wrong.git")
    record.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_GIT_IDENTITY_MISMATCH"):
        cleanup_owned(runtime, "workspace-1", "exec-1", "repo-1")
    assert workspace.is_dir()


def test_existing_workspace_provenance_is_statusable_but_never_cleanup_owned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    seed_repository(source)
    registered = register_existing(
        source,
        workspace_id="workspace-1",
        execution_id="exec-existing",
        repository_id="repo-1",
        created_for="task-1",
        owner="user",
        runtime_root=runtime,
    )
    assert registered["execution_workspace_state"]["kind"] == "existing"
    assert workspace_status(runtime, "workspace-1", "exec-existing", "repo-1")["status"] == "active"
    with pytest.raises(ExecutionWorkspaceError, match="WB_EXECUTION_WORKSPACE_NOT_OWNED"):
        cleanup_owned(runtime, "workspace-1", "exec-existing", "repo-1")
    assert source.is_dir()


def test_doctor_stale_reports_and_cleans_only_with_explicit_permission(tmp_path: Path) -> None:
    _, runtime, prepared = prepare_fixture(tmp_path)
    workspace = Path(str(prepared["execution_workspace_state"]["path"]))
    record = state_path(runtime, "workspace-1", "exec-1", "repo-1")
    data = json.loads(record.read_text(encoding="utf-8"))
    data["execution_workspace_state"]["created_at"] = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record.write_text(json.dumps(data), encoding="utf-8")

    report = doctor_stale(runtime, max_age_hours=24, cleanup=False)
    assert report["stale_count"] == 1
    assert report["cleaned_count"] == 0
    assert workspace.is_dir()

    cleaned = doctor_stale(runtime, max_age_hours=24, cleanup=True)
    assert cleaned["cleaned_count"] == 1
    assert not workspace.exists()


def test_doctor_stale_never_force_cleans_dirty_owned_workspace(tmp_path: Path) -> None:
    _, runtime, prepared = prepare_fixture(tmp_path)
    workspace = Path(str(prepared["execution_workspace_state"]["path"]))
    (workspace / "README.md").write_text("uncommitted task work\n", encoding="utf-8")
    record = state_path(runtime, "workspace-1", "exec-1", "repo-1")
    data = json.loads(record.read_text(encoding="utf-8"))
    data["execution_workspace_state"]["created_at"] = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record.write_text(json.dumps(data), encoding="utf-8")

    report = doctor_stale(runtime, max_age_hours=24, cleanup=True)

    assert report["cleaned_count"] == 0
    assert report["stale"][0]["cleanup_failure_code"] == "WB_EXECUTION_WORKSPACE_DIRTY"
    assert workspace.is_dir()
    assert (workspace / "README.md").read_text(encoding="utf-8") == "uncommitted task work\n"


def test_instruction_audit_reports_only_deterministic_metrics(tmp_path: Path) -> None:
    (tmp_path / "skills/one").mkdir(parents=True)
    (tmp_path / "skills/two").mkdir(parents=True)
    (tmp_path / "rules").mkdir()
    block = "## Rule Loading (mandatory)\n\nLoad the central index first.\n"
    skill = "---\nname: one\ndescription: Short description here.\n---\n\n# One\n\n" + block
    (tmp_path / "skills/one/SKILL.md").write_text(skill, encoding="utf-8")
    (tmp_path / "skills/two/SKILL.md").write_text(skill.replace("name: one", "name: two"), encoding="utf-8")
    (tmp_path / "rules/always.md").write_text(
        "---\nid: always\nload: always\n---\n\n# Always\n\nthree word body\n", encoding="utf-8"
    )
    (tmp_path / "rules/conditional.md").write_text(
        "---\nid: conditional\nload: conditional\n---\n\n# Conditional\n", encoding="utf-8"
    )

    report = audit_instructions(tmp_path, soft_threshold_words=8)

    assert report["status"] == "reported"
    assert report["always_loaded_rules"]["files"] == ["rules/always.md"]
    assert report["always_loaded_rules"]["total_words"] > 0
    assert report["repeated_rule_loading_blocks"][0]["occurrences"] == 2
    assert report["soft_threshold_files"]
    first_skill = next(item for item in report["files"] if item["path"] == "skills/one/SKILL.md")
    assert first_skill["description_length"] == {"characters": 23, "words": 3}
    assert "semantic" not in json.dumps(report).lower()


def test_dispatcher_exposes_instruction_audit(tmp_path: Path) -> None:
    (tmp_path / "skills/example").mkdir(parents=True)
    (tmp_path / "rules").mkdir()
    (tmp_path / "skills/example/SKILL.md").write_text("---\nname: example\ndescription: Example.\n---\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/wb.py"),
            "instruction-audit",
            "--root",
            str(tmp_path),
            "--soft-threshold-words",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["soft_threshold_words"] == 5


def test_dispatcher_exposes_execution_workspace_doctor(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/wb.py"),
            "execution-workspace-doctor-stale",
            "--runtime-root",
            str(tmp_path / "runtime"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["command"] == "execution-workspace-doctor-stale"
    assert report["stale_count"] == 0
    assert report["cleanup_permitted"] is False
