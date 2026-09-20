#!/usr/bin/env python3
"""Install WorkBundle from its readable source tree."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path, PureWindowsPath
import shlex
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.platform_runtime import (  # noqa: E402
    PathKind,
    atomic_replace_bytes,
    classify_path,
    contains_link_like_component,
)


MARKER = "work-bundle-session-start"
HOOK_SCRIPT_NAME = "work-bundle-session-start.py"


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class DirectoryEffect:
    path: Path
    action: str


@dataclass(frozen=True)
class FileEffect:
    path: Path
    content: bytes
    action: str


@dataclass(frozen=True)
class SkillEffect:
    command: tuple[str, ...]
    preview: tuple[dict[str, Any], ...]


Effect = DirectoryEffect | FileEffect | SkillEffect


@dataclass(frozen=True)
class EffectPlan:
    effects: tuple[Effect, ...]
    notices: tuple[str, ...] = ()


class Summary:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.updated: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    def record(self, action: str, path: str | Path) -> None:
        getattr(self, action).append(str(path))

    def print(self) -> None:
        for name in ("created", "updated", "skipped", "failed"):
            values = getattr(self, name)
            print(f"{name}:")
            if values:
                for value in values:
                    print(f"  {value}")
            else:
                print("  none")


def _require_python() -> None:
    if sys.version_info < (3, 13):
        raise InstallError("WorkBundle installation requires Python 3.13 or newer")


def _require_readable_file(path: Path, label: str) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise InstallError(f"missing or unreadable {label}: {path}: {error}") from error
    if classify_path(path) is not PathKind.ORDINARY:
        raise InstallError(f"unsafe {label}: expected an ordinary file: {path}")
    return content


def _lexical_absolute(path: Path) -> Path:
    if ".." in path.parts:
        raise InstallError(f"refusing destination with unresolved parent traversal: {path}")
    return Path(os.path.abspath(path))


def _validate_destination(path: Path, *, allow_file: bool) -> tuple[Path, PathKind]:
    lexical = _lexical_absolute(path)
    anchor = Path(lexical.anchor)
    if contains_link_like_component(lexical.parent, anchor=anchor):
        raise InstallError(f"refusing destination beneath link-like parent: {path}")
    current = anchor
    for component in lexical.parent.relative_to(anchor).parts:
        current /= component
        if classify_path(current) is PathKind.ORDINARY and not current.is_dir():
            raise InstallError(f"refusing destination beneath non-directory parent: {current}")

    kind = classify_path(lexical)
    if kind in {PathKind.SYMLINK, PathKind.JUNCTION, PathKind.REPARSE}:
        raise InstallError(f"refusing link-like destination: {path}")
    if kind is PathKind.ORDINARY:
        if allow_file and lexical.is_file():
            return lexical, kind
        if not allow_file and lexical.is_dir():
            return lexical, kind
        expected = "file" if allow_file else "directory"
        raise InstallError(f"refusing destination that is not an ordinary {expected}: {path}")

    return lexical, kind


def _directory_effect(path: Path) -> DirectoryEffect:
    lexical, kind = _validate_destination(path, allow_file=False)
    return DirectoryEffect(path=lexical, action="skipped" if kind is PathKind.ORDINARY else "created")


def _file_effect(path: Path, content: bytes, *, force: bool) -> FileEffect:
    lexical, kind = _validate_destination(path, allow_file=True)
    if kind is PathKind.MISSING:
        action = "created"
    elif force:
        action = "updated"
    else:
        action = "skipped"
    return FileEffect(path=lexical, content=content, action=action)


def _hook_command(hook_script: Path) -> str:
    arguments = [sys.executable, str(hook_script)]
    return subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)


def _command_token_name(token: str) -> str:
    stripped = token.strip('"\'')
    return PureWindowsPath(stripped).name if "\\" in stripped else Path(stripped).name


def _is_legacy_hook_command(command: object) -> bool:
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return False
    if len(tokens) == 1:
        return _command_token_name(tokens[0]) == HOOK_SCRIPT_NAME
    if len(tokens) != 2 or _command_token_name(tokens[1]) != HOOK_SCRIPT_NAME:
        return False
    interpreter = _command_token_name(tokens[0]).lower()
    return bool(re.fullmatch(r"(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?", interpreter))


def _is_owned(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("id") == MARKER
        or value.get("name") == MARKER
        or _is_legacy_hook_command(value.get("command"))
    )


def _owned_locations(session_hooks: list[Any]) -> list[tuple[int, int | None]]:
    locations: list[tuple[int, int | None]] = []
    for outer_index, outer in enumerate(session_hooks):
        if _is_owned(outer):
            locations.append((outer_index, None))
        elif isinstance(outer, dict) and isinstance(outer.get("hooks"), list):
            for inner_index, hook in enumerate(outer["hooks"]):
                if _is_owned(hook):
                    locations.append((outer_index, inner_index))
    return locations


def _deduplicate_owned(session_hooks: list[Any], keep: tuple[int, int | None]) -> None:
    for outer_index in range(len(session_hooks) - 1, -1, -1):
        outer = session_hooks[outer_index]
        if _is_owned(outer):
            if (outer_index, None) != keep:
                del session_hooks[outer_index]
            continue
        if not isinstance(outer, dict) or not isinstance(outer.get("hooks"), list):
            continue
        hooks = outer["hooks"]
        for inner_index in range(len(hooks) - 1, -1, -1):
            if _is_owned(hooks[inner_index]) and (outer_index, inner_index) != keep:
                del hooks[inner_index]


def _merge_hook(data: dict[str, Any], *, agent: str, command: str) -> dict[str, Any]:
    merged = deepcopy(data)
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InstallError("expected object at hooks")
    session_hooks = hooks.setdefault("SessionStart", [])
    if not isinstance(session_hooks, list):
        raise InstallError("expected array at hooks.SessionStart")

    codex_hook = {
        "id": MARKER,
        "type": "command",
        "command": command,
        "statusMessage": "Syncing WorkBundle rules",
    }
    codex_entry = {"matcher": "startup|resume", "hooks": [codex_hook]}
    claude_hook = {"type": "command", "command": command, "name": MARKER}
    locations = _owned_locations(session_hooks)
    if not locations:
        session_hooks.append(codex_entry if agent == "codex" else {"hooks": [claude_hook]})
        return merged

    outer_index, inner_index = locations[0]
    if agent == "codex":
        if inner_index is None:
            session_hooks[outer_index] = codex_entry
            keep = (outer_index, 0)
        else:
            matcher_entry = session_hooks[outer_index]
            matcher_entry["matcher"] = "startup|resume"
            matcher_entry["hooks"][inner_index] = codex_hook
            keep = (outer_index, inner_index)
    else:
        if inner_index is None:
            session_hooks[outer_index] = {"hooks": [claude_hook]}
            keep = (outer_index, 0)
        else:
            session_hooks[outer_index]["hooks"][inner_index] = claude_hook
            keep = (outer_index, inner_index)
    _deduplicate_owned(session_hooks, keep)
    return merged


def _load_json_object(path: Path) -> tuple[Path, dict[str, Any]]:
    lexical, kind = _validate_destination(path, allow_file=True)
    if kind is PathKind.MISSING:
        return lexical, {}
    try:
        value = json.loads(lexical.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise InstallError(f"invalid JSON in {lexical}: {error}") from error
    except OSError as error:
        raise InstallError(f"cannot read hook configuration {lexical}: {error}") from error
    if not isinstance(value, dict):
        raise InstallError(f"expected JSON object in {lexical}")
    return lexical, value


def _hook_effect(path: Path, *, agent: str, command: str, force: bool) -> FileEffect:
    lexical, current = _load_json_object(path)
    merged = _merge_hook(current, agent=agent, command=command)
    content = (json.dumps(merged, indent=2, sort_keys=True) + "\n").encode("utf-8")
    effect = _file_effect(lexical, content, force=True)
    if current == merged and not force:
        return FileEffect(path=lexical, content=content, action="skipped")
    return effect


def _config_path(agent: str, scope: str, *, home: Path, project_root: Path) -> Path:
    if agent == "codex":
        return (home if scope == "user" else project_root) / ".codex" / "hooks.json"
    if agent == "claude":
        return (home if scope == "user" else project_root) / ".claude" / "settings.json"
    raise InstallError(f"unsupported hook agent: {agent}")


def _plan_hook(
    *,
    agent: str,
    scope: str,
    home: Path,
    project_root: Path,
    config: Path | None,
    force: bool,
) -> tuple[FileEffect, str | None]:
    hook_script = ROOT / "bin" / "work-bundle-session-start.py"
    _require_readable_file(hook_script, "hook script")
    path = config or _config_path(agent, scope, home=home, project_root=project_root)
    effect = _hook_effect(path, agent=agent, command=_hook_command(hook_script), force=force)
    notice = "Codex may require /hooks review or trust before command hooks run." if agent == "codex" else None
    return effect, notice


def _run_skill_preview(home: Path, *, force: bool) -> SkillEffect:
    skill_script = ROOT / "bin" / "work-bundle-skill"
    _require_readable_file(skill_script, "skill installer")
    command = [sys.executable, str(skill_script), "--home", str(home), "enable-all"]
    if force:
        command.append("--force")
    preview_command = [*command, "--dry-run"]
    result = subprocess.run(preview_command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown skill preflight failure"
        raise InstallError(f"skill activation preflight failed: {detail}")
    try:
        payload = json.loads(result.stdout)
        actions = payload["actions"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise InstallError("skill activation preflight returned invalid output") from error
    if not isinstance(actions, list) or not all(isinstance(item, dict) for item in actions):
        raise InstallError("skill activation preflight returned invalid actions")
    return SkillEffect(command=tuple(command), preview=tuple(actions))


def _bootstrap_content(template: bytes) -> bytes:
    root = json.dumps(str(ROOT), ensure_ascii=False).encode("utf-8")
    return template.replace(b"__WORK_BUNDLE_ROOT__", root).replace(
        b"${PLACEHOLDER} --> replace by install script", root
    )


def _selected_hooks() -> list[tuple[str, str]]:
    selections: list[tuple[str, str]] = []
    while True:
        agent = input("Select hook adapter: [1] codex [2] claude [q] quit: ").strip().lower()
        if agent in {"q", "quit", "exit"}:
            return selections
        if agent in {"1", "codex"}:
            agent = "codex"
        elif agent in {"2", "claude"}:
            agent = "claude"
        else:
            print("invalid adapter")
            continue
        scope = input("Select config scope: [1] user [2] project [q] cancel: ").strip().lower()
        if scope in {"q", "quit", "exit"}:
            continue
        if scope in {"1", "user"}:
            scope = "user"
        elif scope in {"2", "project"}:
            scope = "project"
        else:
            print("invalid scope")
            continue
        selections.append((agent, scope))


def build_effect_plan(args: argparse.Namespace) -> EffectPlan:
    _require_python()
    home = Path.home()
    project_root = _lexical_absolute(Path(getattr(args, "project_root", None) or Path.cwd()).expanduser())
    effects: list[Effect] = []
    notices: list[str] = []

    if args.command == "register-hook":
        effect, notice = _plan_hook(
            agent=args.agent,
            scope=args.scope,
            home=home,
            project_root=project_root,
            config=Path(args.config).expanduser() if args.config else None,
            force=args.force,
        )
        effects.append(effect)
        if notice:
            notices.append(notice)
        return EffectPlan(tuple(effects), tuple(notices))

    config_root = home / ".work-bundle"
    registry_root = config_root / "registry"
    template_root = ROOT / "references" / "assets" / "template"
    bootstrap = _bootstrap_content(_require_readable_file(template_root / "bootstrap.yaml", "bootstrap template"))
    projects = _require_readable_file(template_root / "projects.yaml", "project registry template")
    skills = _require_readable_file(template_root / "skill-registry.yaml", "skill registry template")

    effects.extend((_directory_effect(config_root), _directory_effect(registry_root)))
    effects.extend(
        (
            _file_effect(config_root / "bootstrap.yaml", bootstrap, force=args.force),
            _file_effect(registry_root / "projects.yaml", projects, force=args.force),
            _file_effect(registry_root / "skill-registry.yaml", skills, force=args.force),
        )
    )
    effects.append(_run_skill_preview(home, force=args.force))

    hook_targets: list[tuple[str, str]] = []
    if args.hooks == "select":
        hook_targets = _selected_hooks()
    elif args.hooks == "auto":
        candidates = [
            ("codex", "user", home / ".codex"),
            ("codex", "project", project_root / ".codex"),
            ("claude", "user", home / ".claude"),
            ("claude", "project", project_root / ".claude"),
        ]
        hook_targets = [(agent, scope) for agent, scope, root in candidates if root.is_dir()]
        if not hook_targets:
            notices.append("no Codex or Claude config roots found for hook auto mode")

    for agent, scope in hook_targets:
        effect, notice = _plan_hook(
            agent=agent,
            scope=scope,
            home=home,
            project_root=project_root,
            config=None,
            force=args.force,
        )
        effects.append(effect)
        if notice:
            notices.append(notice)
    return EffectPlan(tuple(effects), tuple(notices))


def _record_skill_actions(summary: Summary, actions: tuple[dict[str, Any], ...]) -> None:
    for item in actions:
        action = str(item.get("action", ""))
        path = str(item.get("link", item.get("name", "skill")))
        if action.startswith("create "):
            summary.record("created", path)
        elif action.startswith("replace "):
            summary.record("updated", path)
        else:
            summary.record("skipped", path)


def apply_effect_plan(plan: EffectPlan, *, dry_run: bool, summary: Summary) -> None:
    for effect in plan.effects:
        if isinstance(effect, DirectoryEffect):
            if effect.action == "created" and not dry_run:
                effect.path.mkdir(parents=True, exist_ok=False)
            summary.record(effect.action, effect.path)
        elif isinstance(effect, FileEffect):
            if effect.action != "skipped" and not dry_run:
                atomic_replace_bytes(effect.path, effect.content)
            summary.record(effect.action, effect.path)
            if dry_run and effect.action != "skipped":
                print(f"would update {effect.path}")
        else:
            if not dry_run:
                result = subprocess.run(effect.command, check=False, capture_output=True, text=True)
                if result.returncode != 0:
                    summary.record("failed", effect.command[1])
                    detail = result.stderr.strip() or result.stdout.strip() or "unknown skill activation failure"
                    raise InstallError(f"skill activation failed after prior effects: {detail}")
            _record_skill_actions(summary, effect.preview)
    for notice in plan.notices:
        print(notice)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Install WorkBundle. Supported hook adapters: codex, claude",
    )
    parser.set_defaults(command="install")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hooks", choices=("auto", "select"))
    subparsers = parser.add_subparsers(dest="command")
    register = subparsers.add_parser("register-hook")
    register.add_argument("--agent", required=True)
    register.add_argument("--scope", required=True)
    register.add_argument("--project-root")
    register.add_argument("--config")
    register.add_argument("--force", action="store_true")
    register.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "register-hook" and args.agent not in {"codex", "claude"}:
        print(f"unsupported hook agent: {args.agent}", file=sys.stderr)
        return 2
    if args.command == "register-hook" and args.scope not in {"user", "project"}:
        print(f"unsupported hook scope: {args.scope}", file=sys.stderr)
        return 2
    summary = Summary()
    try:
        plan = build_effect_plan(args)
        apply_effect_plan(plan, dry_run=args.dry_run, summary=summary)
    except InstallError as error:
        print(str(error), file=sys.stderr)
        if summary.created or summary.updated or summary.skipped or summary.failed:
            summary.print()
        return 1
    except OSError as error:
        summary.record("failed", getattr(error, "filename", None) or "install")
        print(f"installation failed after partial effects: {error}", file=sys.stderr)
        summary.print()
        return 1
    summary.print()
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
