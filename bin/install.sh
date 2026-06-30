#!/usr/bin/env bash
set -euo pipefail

force=0
dry_run=0
hooks_mode=""

bin_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work_bundle_root="$(cd "$bin_dir/.." && pwd)"
work_bundle_config_root="${HOME}/.work-bundle"
registry_root="${work_bundle_config_root}/registry"
template_root="${work_bundle_root}/references/assets/template"
hook_script="${work_bundle_root}/bin/work-bundle-session-start.py"
hook_command="${hook_script}"

created=()
updated=()
skipped=()
failed=()

record() {
  local bucket="$1"
  local path="$2"
  case "$bucket" in
    created) created+=("$path") ;;
    updated) updated+=("$path") ;;
    skipped) skipped+=("$path") ;;
    failed) failed+=("$path") ;;
  esac
}

usage() {
  cat <<'EOF'
usage:
  bin/install.sh [--force] [--dry-run] [--hooks auto|select]
  bin/install.sh register-hook --agent codex|claude --scope user|project [--project-root <path>] [--config <path>] [--force] [--dry-run]

Supported hook adapters: codex, claude
EOF
}

ensure_dir() {
  local path="$1"
  if [[ -d "$path" ]]; then
    record skipped "$path"
    return
  fi
  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$path"
  fi
  record created "$path"
}

copy_if_missing() {
  local src="$1"
  local dest="$2"
  if [[ ! -f "$src" ]]; then
    record failed "$src"
    echo "missing template: $src" >&2
    return 1
  fi
  if [[ -e "$dest" && "$force" -eq 0 ]]; then
    record skipped "$dest"
    return
  fi
  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
  fi
  if [[ -e "$dest" && "$force" -eq 1 ]]; then
    record updated "$dest"
  else
    record created "$dest"
  fi
}

install_bootstrap() {
  local src="${template_root}/bootstrap.yaml"
  local dest="${work_bundle_config_root}/bootstrap.yaml"
  if [[ ! -f "$src" ]]; then
    record failed "$src"
    echo "missing template: $src" >&2
    return 1
  fi
  if [[ -e "$dest" && "$force" -eq 0 ]]; then
    record skipped "$dest"
    return
  fi
  if [[ "$dry_run" -eq 0 ]]; then
    mkdir -p "$(dirname "$dest")"
    sed "s|__WORK_BUNDLE_ROOT__|${work_bundle_root}|g; s|\\\${PLACEHOLDER} --> replace by install script|${work_bundle_root}|g" "$src" > "$dest"
  fi
  if [[ -e "$dest" && "$force" -eq 1 ]]; then
    record updated "$dest"
  else
    record created "$dest"
  fi
}

config_path_for() {
  local agent="$1"
  local scope="$2"
  local project_root="$3"
  case "${agent}:${scope}" in
    codex:user) printf '%s/.codex/hooks.json' "$HOME" ;;
    codex:project) printf '%s/.codex/hooks.json' "$project_root" ;;
    claude:user) printf '%s/.claude/settings.json' "$HOME" ;;
    claude:project) printf '%s/.claude/settings.json' "$project_root" ;;
    *)
      echo "unsupported agent/scope: ${agent}/${scope}" >&2
      return 2
      ;;
  esac
}

merge_hook_json() {
  local agent="$1"
  local config="$2"
  local dry="$3"
  local force_refresh="$4"
  local command="$5"
  AGENT="$agent" CONFIG_PATH="$config" DRY_RUN="$dry" FORCE_REFRESH="$force_refresh" HOOK_COMMAND="$command" python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

agent = os.environ["AGENT"]
config_path = Path(os.environ["CONFIG_PATH"])
dry_run = os.environ["DRY_RUN"] == "1"
force_refresh = os.environ["FORCE_REFRESH"] == "1"
command = os.environ["HOOK_COMMAND"]
marker = "work-bundle-session-start"


def load_config() -> dict:
    if not config_path.exists():
        return {}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {config_path}: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object in {config_path}")
    return value


def is_owned(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("id") == marker or value.get("name") == marker or marker in str(value.get("command", ""))


def codex_hook() -> dict:
    return {
        "id": marker,
        "type": "command",
        "command": command,
        "statusMessage": "Syncing WorkBundle rules",
    }


def codex_entry() -> dict:
    return {
        "matcher": "startup|resume",
        "hooks": [codex_hook()],
    }


def claude_entry() -> dict:
    return {
        "type": "command",
        "command": command,
        "name": marker,
    }


def merge_codex(data: dict) -> tuple[dict, bool]:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"expected object at hooks in {config_path}")
    session_hooks = hooks.setdefault("SessionStart", [])
    if not isinstance(session_hooks, list):
        raise SystemExit(f"expected array at hooks.SessionStart in {config_path}")
    entry = codex_entry()
    hook_entry = codex_hook()
    owned_indexes: list[tuple[int, int | None]] = []
    for matcher_index, matcher_entry in enumerate(session_hooks):
        if is_owned(matcher_entry):
            owned_indexes.append((matcher_index, None))
            continue
        if isinstance(matcher_entry, dict) and isinstance(matcher_entry.get("hooks"), list):
            for hook_index, hook in enumerate(matcher_entry["hooks"]):
                if is_owned(hook):
                    owned_indexes.append((matcher_index, hook_index))
    changed = False
    if owned_indexes:
        matcher_index, hook_index = owned_indexes[0]
        if hook_index is None:
            if session_hooks[matcher_index] != entry or force_refresh:
                session_hooks[matcher_index] = entry
                changed = True
        else:
            matcher_entry = session_hooks[matcher_index]
            hooks_list = matcher_entry["hooks"]
            if len(hooks_list) == 1:
                if matcher_entry != entry or force_refresh:
                    session_hooks[matcher_index] = entry
                    changed = True
            elif hooks_list[hook_index] != hook_entry or force_refresh:
                hooks_list[hook_index] = hook_entry
                changed = True
        for matcher_index, hook_index in reversed(owned_indexes[1:]):
            if hook_index is None:
                del session_hooks[matcher_index]
            else:
                hooks_list = session_hooks[matcher_index]["hooks"]
                del hooks_list[hook_index]
            changed = True
    else:
        session_hooks.append(entry)
        changed = True
    return data, changed


def merge_claude(data: dict) -> tuple[dict, bool]:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"expected object at hooks in {config_path}")
    session_hooks = hooks.setdefault("SessionStart", [])
    if not isinstance(session_hooks, list):
        raise SystemExit(f"expected array at hooks.SessionStart in {config_path}")
    entry = claude_entry()
    owned_indexes: list[tuple[int, int | None]] = []
    for matcher_index, matcher in enumerate(session_hooks):
        if is_owned(matcher):
            owned_indexes.append((matcher_index, None))
            continue
        if isinstance(matcher, dict) and isinstance(matcher.get("hooks"), list):
            for hook_index, hook in enumerate(matcher["hooks"]):
                if is_owned(hook):
                    owned_indexes.append((matcher_index, hook_index))
    changed = False
    if owned_indexes:
        matcher_index, hook_index = owned_indexes[0]
        if hook_index is None:
            replacement = {"hooks": [entry]}
            if session_hooks[matcher_index] != replacement or force_refresh:
                session_hooks[matcher_index] = replacement
                changed = True
        else:
            matcher = session_hooks[matcher_index]
            hooks_list = matcher["hooks"]
            if hooks_list[hook_index] != entry or force_refresh:
                hooks_list[hook_index] = entry
                changed = True
        for matcher_index, hook_index in reversed(owned_indexes[1:]):
            if hook_index is None:
                del session_hooks[matcher_index]
                changed = True
            else:
                hooks_list = session_hooks[matcher_index]["hooks"]
                del hooks_list[hook_index]
                changed = True
    else:
        session_hooks.append({"hooks": [entry]})
        changed = True
    return data, changed


data = load_config()
if agent == "codex":
    data, changed = merge_codex(data)
elif agent == "claude":
    data, changed = merge_claude(data)
else:
    raise SystemExit(f"unsupported agent: {agent}")

if not changed:
    print(f"unchanged {config_path}")
    raise SystemExit(0)

print(f"would update {config_path}" if dry_run else f"updated {config_path}")
if not dry_run:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

register_hook() {
  local agent=""
  local scope=""
  local project_root="${PWD}"
  local config=""

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --agent)
        agent="${2:-}"
        shift 2
        ;;
      --scope)
        scope="${2:-}"
        shift 2
        ;;
      --project-root)
        project_root="${2:-}"
        shift 2
        ;;
      --config)
        config="${2:-}"
        shift 2
        ;;
      --force)
        force=1
        shift
        ;;
      --dry-run)
        dry_run=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "unknown register-hook argument: $1" >&2
        usage >&2
        return 2
        ;;
    esac
  done

  case "$agent" in
    codex|claude) ;;
    "")
      echo "register-hook requires --agent codex|claude" >&2
      return 2
      ;;
    *)
      echo "unsupported hook agent: $agent" >&2
      return 2
      ;;
  esac

  case "$scope" in
    user|project) ;;
    "")
      echo "register-hook requires --scope user|project" >&2
      return 2
      ;;
    *)
      echo "unsupported hook scope: $scope" >&2
      return 2
      ;;
  esac

  project_root="$(cd "$project_root" && pwd)"
  if [[ -z "$config" ]]; then
    config="$(config_path_for "$agent" "$scope" "$project_root")"
  fi

  if [[ ! -x "$hook_script" ]]; then
    record failed "$hook_script"
    echo "missing executable hook script: $hook_script" >&2
    return 1
  fi

  local before_hash="missing"
  if [[ -f "$config" ]]; then
    before_hash="$(python3 - "$config" <<'PY'
from pathlib import Path
import hashlib
import sys
path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"
  fi

  merge_hook_json "$agent" "$config" "$dry_run" "$force" "$hook_command"

  local after_hash="$before_hash"
  if [[ -f "$config" ]]; then
    after_hash="$(python3 - "$config" <<'PY'
from pathlib import Path
import hashlib
import sys
path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"
  fi

  if [[ "$dry_run" -eq 1 ]]; then
    record skipped "$config"
  elif [[ "$before_hash" == "missing" ]]; then
    record created "$config"
  elif [[ "$before_hash" != "$after_hash" ]]; then
    record updated "$config"
  else
    record skipped "$config"
  fi

  if [[ "$agent" == "codex" ]]; then
    echo "Codex may require /hooks review or trust before command hooks run."
  fi
}

run_hooks_auto() {
  local project_root="${PWD}"
  local matched=0
  if [[ -d "${HOME}/.codex" || -f "${HOME}/.codex/hooks.json" ]]; then
    register_hook --agent codex --scope user --project-root "$project_root"
    matched=1
  fi
  if [[ -d "${project_root}/.codex" || -f "${project_root}/.codex/hooks.json" ]]; then
    register_hook --agent codex --scope project --project-root "$project_root"
    matched=1
  fi
  if [[ -d "${HOME}/.claude" || -f "${HOME}/.claude/settings.json" ]]; then
    register_hook --agent claude --scope user --project-root "$project_root"
    matched=1
  fi
  if [[ -d "${project_root}/.claude" || -f "${project_root}/.claude/settings.json" ]]; then
    register_hook --agent claude --scope project --project-root "$project_root"
    matched=1
  fi
  if [[ "$matched" -eq 0 ]]; then
    record skipped "hooks:auto:no-supported-config-roots"
    echo "no Codex or Claude config roots found for hook auto mode"
  fi
}

run_hooks_select() {
  local project_root="${PWD}"
  local agent=""
  local scope=""
  while true; do
    printf 'Select hook adapter: [1] codex [2] claude [q] quit: '
    read -r agent
    case "$agent" in
      1|codex) agent="codex" ;;
      2|claude) agent="claude" ;;
      q|Q|quit|exit) break ;;
      *) echo "invalid adapter"; continue ;;
    esac
    printf 'Select config scope: [1] user [2] project [q] cancel: '
    read -r scope
    case "$scope" in
      1|user) scope="user" ;;
      2|project) scope="project" ;;
      q|Q|quit|exit) continue ;;
      *) echo "invalid scope"; continue ;;
    esac
    register_hook --agent "$agent" --scope "$scope" --project-root "$project_root"
  done
}

install_default() {
  ensure_dir "$work_bundle_config_root"
  ensure_dir "$registry_root"
  install_bootstrap
  copy_if_missing "${template_root}/projects.yaml" "${registry_root}/projects.yaml"
  copy_if_missing "${template_root}/skill-registry.yaml" "${registry_root}/skill-registry.yaml"

  installer="${bin_dir}/install-work-bundle-skills"
  if [[ ! -x "$installer" ]]; then
    record failed "$installer"
    echo "missing executable skill installer: $installer" >&2
  else
    installer_args=()
    if [[ "$force" -eq 1 ]]; then
      installer_args+=(--force)
    fi
    if [[ "$dry_run" -eq 1 ]]; then
      installer_args+=(--dry-run)
    fi
    if installer_output="$("$installer" "${installer_args[@]}")"; then
      printf '%s\n' "$installer_output"
      record updated "$installer"
    else
      record failed "$installer"
    fi
  fi

  case "$hooks_mode" in
    "") ;;
    auto) run_hooks_auto ;;
    select) run_hooks_select ;;
  esac
}

print_summary() {
  printf 'created:\n'
  printf '  %s\n' "${created[@]:-none}"
  printf 'updated:\n'
  printf '  %s\n' "${updated[@]:-none}"
  printf 'skipped:\n'
  printf '  %s\n' "${skipped[@]:-none}"
  printf 'failed:\n'
  printf '  %s\n' "${failed[@]:-none}"
}

main() {
  if [[ "${1:-}" == "register-hook" ]]; then
    shift
    register_hook "$@"
    print_summary
    if [[ "${#failed[@]}" -gt 0 ]]; then
      exit 1
    fi
    return
  fi

  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --force)
        force=1
        shift
        ;;
      --dry-run)
        dry_run=1
        shift
        ;;
      --hooks)
        hooks_mode="${2:-}"
        case "$hooks_mode" in
          auto|select) ;;
          *)
            echo "--hooks requires auto or select" >&2
            usage >&2
            exit 2
            ;;
        esac
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "unknown argument: $1" >&2
        usage >&2
        exit 2
        ;;
    esac
  done

  install_default
  print_summary
  if [[ "${#failed[@]}" -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
