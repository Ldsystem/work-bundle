from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "bin" / "install.sh"
HOOK_SCRIPT = REPO_ROOT / "bin" / "work-bundle-session-start.py"


def run_install(home: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        cwd=cwd or REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def codex_work_bundle_entry() -> dict:
    return {
        "matcher": "startup|resume",
        "hooks": [
            {
                "id": "work-bundle-session-start",
                "type": "command",
                "command": str(HOOK_SCRIPT),
                "statusMessage": "Syncing WorkBundle rules",
            }
        ],
    }


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
                "command": str(HOOK_SCRIPT),
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
