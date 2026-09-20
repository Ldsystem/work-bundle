from __future__ import annotations

import json
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "bin" / "install.py"
HOOK_SCRIPT = REPO_ROOT / "bin" / "work-bundle-session-start.py"


def run_install(home: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        cwd=cwd or REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_installer_module():
    name = "work_bundle_installer_test_module"
    spec = importlib.util.spec_from_file_location(name, INSTALLER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def codex_work_bundle_entry() -> dict:
    command = subprocess.list2cmdline([sys.executable, str(HOOK_SCRIPT)]) if os.name == "nt" else shlex.join(
        [sys.executable, str(HOOK_SCRIPT)]
    )
    return {
        "matcher": "startup|resume",
        "hooks": [
            {
                "id": "work-bundle-session-start",
                "type": "command",
                "command": command,
                "statusMessage": "Syncing WorkBundle rules",
            }
        ],
    }


def test_default_install_from_source_archive_uses_only_python_and_is_idempotent(tmp_path: Path) -> None:
    isolated_root = tmp_path / "archive # copy"
    for relative in [
        "bin/install.py",
        "bin/work-bundle-skill",
        "bin/work-bundle-session-start.py",
        "scripts/platform_runtime.py",
        "references/assets/template/bootstrap.yaml",
        "references/assets/template/projects.yaml",
        "references/assets/template/skill-registry.yaml",
    ]:
        source = REPO_ROOT / relative
        destination = isolated_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    skill = isolated_root / "skills" / "sample" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: sample\ndescription: Sample skill.\n---\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)

    first = subprocess.run(
        [sys.executable, str(isolated_root / "bin" / "install.py")],
        cwd=isolated_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [sys.executable, str(isolated_root / "bin" / "install.py")],
        cwd=isolated_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    bootstrap_line = (home / ".work-bundle" / "bootstrap.yaml").read_text(encoding="utf-8").splitlines()[2]
    assert json.loads(bootstrap_line.split(":", 1)[1].strip()) == str(isolated_root)
    assert (home / ".agents" / "skills" / "sample").resolve() == skill.parent.resolve()
    assert "created:" in first.stdout
    assert "skipped:" in second.stdout


def test_codex_register_hook_merges_unrelated_hooks_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hooks_path = home / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [{"type": "command", "command": "echo keep"}],
                        }
                    ],
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": "echo before"}],
                        }
                    ],
                },
                "other": {"preserved": True},
            }
        ),
        encoding="utf-8",
    )

    first = run_install(home, "register-hook", "--agent", "codex", "--scope", "user")
    assert first.returncode == 0, first.stdout + first.stderr
    data = read_json(hooks_path)
    session = data["hooks"]["SessionStart"]
    assert session[0] == {
        "matcher": "startup",
        "hooks": [{"type": "command", "command": "echo keep"}],
    }
    assert session[1] == codex_work_bundle_entry()
    assert data["hooks"]["PreToolUse"] == [
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "echo before"}],
        }
    ]
    assert data["other"] == {"preserved": True}
    assert "/hooks review" in first.stdout

    before = hooks_path.read_text(encoding="utf-8")
    second = run_install(home, "register-hook", "--agent", "codex", "--scope", "user")
    assert second.returncode == 0, second.stdout + second.stderr
    assert hooks_path.read_text(encoding="utf-8") == before
    assert len(read_json(hooks_path)["hooks"]["SessionStart"]) == 2


def test_claude_register_hook_merges_settings_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(echo:*)"]},
                "hooks": {
                    "SessionStart": [{"hooks": [{"type": "command", "command": "echo keep"}]}],
                    "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}],
                },
            }
        ),
        encoding="utf-8",
    )

    first = run_install(home, "register-hook", "--agent", "claude", "--scope", "user")
    assert first.returncode == 0, first.stdout + first.stderr
    data = read_json(settings_path)
    assert data["permissions"] == {"allow": ["Bash(echo:*)"]}
    assert data["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "echo stop"}]}]
    session = data["hooks"]["SessionStart"]
    assert session[0] == {"hooks": [{"type": "command", "command": "echo keep"}]}
    assert session[1] == {
        "hooks": [
            {
                "type": "command",
                "command": codex_work_bundle_entry()["hooks"][0]["command"],
                "name": "work-bundle-session-start",
            }
        ]
    }

    before = settings_path.read_text(encoding="utf-8")
    second = run_install(home, "register-hook", "--agent", "claude", "--scope", "user")
    assert second.returncode == 0, second.stdout + second.stderr
    assert settings_path.read_text(encoding="utf-8") == before


def test_force_refreshes_only_work_bundle_hook_entry(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hooks_path = home / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [{"type": "command", "command": "echo keep"}],
                        },
                        {
                            "id": "work-bundle-session-start",
                            "type": "command",
                            "command": "/old/work-bundle-session-start.py",
                            "extra": "remove",
                        },
                        {
                            "id": "work-bundle-session-start",
                            "type": "command",
                            "command": "/duplicate/work-bundle-session-start.py",
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_install(home, "register-hook", "--agent", "codex", "--scope", "user", "--force")
    assert result.returncode == 0, result.stdout + result.stderr
    session = read_json(hooks_path)["hooks"]["SessionStart"]
    assert session == [
        {
            "matcher": "startup",
            "hooks": [{"type": "command", "command": "echo keep"}],
        },
        codex_work_bundle_entry(),
    ]


def test_command_substring_does_not_claim_unrelated_hook(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hooks_path = home / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    unrelated = {
        "matcher": "startup",
        "hooks": [{"type": "command", "command": "echo work-bundle-session-start"}],
    }
    hooks_path.write_text(json.dumps({"hooks": {"SessionStart": [unrelated]}}), encoding="utf-8")

    result = run_install(home, "register-hook", "--agent", "codex", "--scope", "user")

    assert result.returncode == 0, result.stdout + result.stderr
    session = read_json(hooks_path)["hooks"]["SessionStart"]
    assert session == [unrelated, codex_work_bundle_entry()]


def test_codex_refresh_preserves_unrelated_outer_group_fields(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hooks_path = home / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "old",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/old/work-bundle-session-start.py",
                                }
                            ],
                            "timeout": 30,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_install(home, "register-hook", "--agent", "codex", "--scope", "user", "--force")

    assert result.returncode == 0, result.stdout + result.stderr
    group = read_json(hooks_path)["hooks"]["SessionStart"][0]
    assert group["matcher"] == "startup|resume"
    assert group["timeout"] == 30
    assert group["hooks"] == codex_work_bundle_entry()["hooks"]


def test_dry_run_reports_planned_write_without_changing_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hooks_path = home / ".codex" / "hooks.json"

    result = run_install(home, "register-hook", "--agent", "codex", "--scope", "user", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "would update" in result.stdout
    assert "skipped:" in result.stdout
    assert not hooks_path.exists()

    settings_path = home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"hooks": {"SessionStart": []}, "keep": true}\n', encoding="utf-8")
    before = settings_path.read_text(encoding="utf-8")
    claude = run_install(home, "register-hook", "--agent", "claude", "--scope", "user", "--dry-run")
    assert claude.returncode == 0, claude.stdout + claude.stderr
    assert "would update" in claude.stdout
    assert settings_path.read_text(encoding="utf-8") == before


def test_invalid_hook_json_fails_before_default_install_writes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hooks_path = home / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("not-json\n", encoding="utf-8")

    result = run_install(home, "--hooks", "auto")

    assert result.returncode == 1
    assert "invalid JSON" in result.stderr
    assert not (home / ".work-bundle").exists()
    assert hooks_path.read_text(encoding="utf-8") == "not-json\n"


def test_unknown_argument_returns_two_without_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"

    result = run_install(home, "--unknown")

    assert result.returncode == 2
    assert not home.exists()


def test_skill_collision_fails_before_default_install_writes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    first_skill = sorted(path.name for path in (REPO_ROOT / "skills").iterdir() if (path / "SKILL.md").is_file())[0]
    (home / ".agents" / "skills" / first_skill).mkdir(parents=True)

    result = run_install(home)

    assert result.returncode == 1
    assert "skill activation preflight failed" in result.stderr
    assert not (home / ".work-bundle").exists()


def test_skill_parent_file_fails_before_default_install_writes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".agents").write_text("obstruction\n", encoding="utf-8")

    result = run_install(home)

    assert result.returncode == 1
    assert "non-directory parent" in result.stderr
    assert not (home / ".work-bundle").exists()


def test_late_io_failure_reports_exact_partial_effects(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    installer = load_installer_module()
    directory = tmp_path / "output"
    first = directory / "first.txt"
    blocked = directory / "blocked.txt"
    plan = installer.EffectPlan(
        (
            installer.DirectoryEffect(directory, "created"),
            installer.FileEffect(first, b"first", "created"),
            installer.FileEffect(blocked, b"blocked", "created"),
        )
    )
    real_replace = installer.atomic_replace_bytes

    def fail_second(path: Path, content: bytes) -> None:
        if path == blocked:
            raise OSError(5, "simulated failure", str(path))
        real_replace(path, content)

    monkeypatch.setattr(installer, "build_effect_plan", lambda args: plan)
    monkeypatch.setattr(installer, "atomic_replace_bytes", fail_second)

    assert installer.main([]) == 1
    output = capsys.readouterr()
    assert first.read_bytes() == b"first"
    assert not blocked.exists()
    assert str(first) in output.out
    assert str(blocked) in output.out
    assert "partial effects" in output.err


def test_hook_script_need_not_be_executable_and_command_uses_active_interpreter(tmp_path: Path) -> None:
    home = tmp_path / "home"
    original_mode = HOOK_SCRIPT.stat().st_mode
    try:
        HOOK_SCRIPT.chmod(0o644)
        result = run_install(home, "register-hook", "--agent", "codex", "--scope", "user")
    finally:
        HOOK_SCRIPT.chmod(original_mode)

    assert result.returncode == 0, result.stdout + result.stderr
    command = read_json(home / ".codex" / "hooks.json")["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert command == codex_work_bundle_entry()["hooks"][0]["command"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink fixture")
def test_custom_hook_config_beneath_symlink_parent_is_rejected_lexically(tmp_path: Path) -> None:
    home = tmp_path / "home"
    real_parent = tmp_path / "real-config"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-config"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    result = run_install(
        home,
        "register-hook",
        "--agent",
        "codex",
        "--scope",
        "user",
        "--config",
        str(linked_parent / "hooks.json"),
        "--dry-run",
    )

    assert result.returncode == 1
    assert "link-like" in result.stderr
    assert not (real_parent / "hooks.json").exists()


def test_hook_config_beneath_file_parent_is_rejected_before_default_writes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("file\n", encoding="utf-8")

    result = run_install(
        home,
        "register-hook",
        "--agent",
        "codex",
        "--scope",
        "user",
        "--config",
        str(blocked_parent / "hooks.json"),
    )

    assert result.returncode == 1
    assert "non-directory parent" in result.stderr
    assert blocked_parent.read_text(encoding="utf-8") == "file\n"
    assert not (home / ".work-bundle").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink fixture")
def test_hook_config_rejects_raw_parent_traversal_before_normalization(tmp_path: Path) -> None:
    home = tmp_path / "home"
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    raw_config = linked / ".." / "hooks.json"

    result = run_install(
        home,
        "register-hook",
        "--agent",
        "codex",
        "--scope",
        "user",
        "--config",
        str(raw_config),
        "--dry-run",
    )

    assert result.returncode == 1
    assert "parent traversal" in result.stderr
    assert not (tmp_path / "hooks.json").exists()


def test_projected_link_like_hook_parent_is_rejected(tmp_path: Path, monkeypatch) -> None:
    installer = load_installer_module()
    target = tmp_path / "junction-parent" / "hooks.json"
    monkeypatch.setattr(
        installer,
        "contains_link_like_component",
        lambda path, *, anchor: path == target.parent,
    )

    with pytest.raises(installer.InstallError, match="link-like parent"):
        installer._validate_destination(target, allow_file=True)


def test_projected_windows_hook_path_rejects_raw_parent_traversal(tmp_path: Path) -> None:
    installer = load_installer_module()
    raw_target = tmp_path / "junction" / ".." / "hooks.json"

    with pytest.raises(installer.InstallError, match="parent traversal"):
        installer._validate_destination(raw_target, allow_file=True)


def test_direct_project_mode_accepts_config_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    custom_config = tmp_path / "custom" / "codex-hooks.json"

    result = run_install(
        home,
        "register-hook",
        "--agent",
        "codex",
        "--scope",
        "project",
        "--project-root",
        str(project),
        "--config",
        str(custom_config),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = read_json(custom_config)
    assert data["hooks"]["SessionStart"] == [codex_work_bundle_entry()]
    assert not (project / ".codex" / "hooks.json").exists()


def test_hooks_auto_scans_codex_and_claude_without_gemini(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True)

    result = run_install(home, "--dry-run", "--hooks", "auto")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Codex" in result.stdout
    assert ".claude/settings.json" in result.stdout
    assert "gemini" not in result.stdout.lower()


def test_gemini_is_not_supported_or_advertised(tmp_path: Path) -> None:
    home = tmp_path / "home"
    help_result = run_install(home, "--help")
    assert help_result.returncode == 0
    assert "codex, claude" in help_result.stdout
    assert "gemini" not in help_result.stdout.lower()

    result = run_install(home, "register-hook", "--agent", "gemini", "--scope", "user")
    assert result.returncode == 2
    assert "unsupported hook agent: gemini" in result.stderr
