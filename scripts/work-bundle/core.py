from __future__ import annotations

import argparse
import os
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


CUSTOMIZED_SKILL_ROOT = Path(__file__).resolve().parents[2] / 'skills'
GLOBAL_SKILL_REGISTRY = '~/.work-bundle/skills/skill-registry.yaml'
WORK_BUNDLE_CONFIG_ROOT_ENV = 'WB_CONFIG_ROOT'
WORK_BUNDLE_ROOT_ENV = 'WB_WORK_BUNDLE_ROOT'
GLOBAL_BOOTSTRAP_FILE_NAME = 'bootstrap.yaml'
LEGACY_ROOT_POINTER_FILE_NAME = 'work-bundle-root.yaml'
DIAG_PROJECT_METADATA_MISSING = 'WB_PROJECT_METADATA_MISSING'
DIAG_PROJECT_METADATA_INVALID = 'WB_PROJECT_METADATA_INVALID'
DIAG_LEGACY_COMMAND_REMOVED = 'WB_LEGACY_COMMAND_REMOVED'
DIAG_WORKSPACE_MODE_INVALID = 'WB_WORKSPACE_MODE_INVALID'
DIAG_GIT_CONTROL_SCOPE_EXTERNAL = 'WB_GIT_CONTROL_SCOPE_EXTERNAL'
LEGACY_COMMAND_MIGRATIONS = {
    'inspect-repository-model': 'inspect-project-initialization',
    'repository-model': 'initialize-project',
    'validate-repository-model': 'validate-project',
    'generate-domain-profile': 'generate-project-metadata-profile',
    'merge-domain-profile': 'merge-project-metadata-profile',
    'validate-domain-profile': 'validate-project-metadata-profile',
}
ROLE_NAMES = ['project-manager', 'solution-architect', 'domain-analyst', 'ui-designer', 'frontend-developer', 'backend-developer', 'database-engineer', 'qa-reviewer', 'devops-engineer']
# Retired v4 root stubs merged into rules/orchestration/: orchestration-boundary -> orch-orchestration-boundary; knowledge-boundary, retrieval-gateway -> orch-knowledge-gateway; execution-boundary -> orch-execute-plan skill-owned constraints; handoff-boundary -> orch-handoff-required; review-archive-boundary -> orch-review-completion
RULES = ['repository-boundary', 'lifecycle-authority', 'skill-registry', 'domain-profile', 'doctor-readonly', 'runtime-artifact-format', 'security-exclusion']

CLI_HELP_EPILOG = '''Canonical consolidated command surface:
  init-project <project-root> --mode <single-repository|multi-repository>
  show-project [--workspace-root <workspace-root> | --project-root <project-root>]
  validate-project <project-root> --dry-run
  doctor-project <project-root> [--repair] [--force]
  migrate-project <project-root> --dry-run
  migrate-control-plane <workspace-root> (--dry-run|--apply --accepted-proposal-id <id>)
  init-workspace <workspace-root> --slug <slug> --repository <id=remote> (--dry-run|--apply)
  publish-control-plane <workspace-root> --remote <git-remote> (--dry-run|--apply)
  attach-workspace <workspace-root> [--materialize none|missing|all] (--dry-run|--apply)
  doctor-workspace <workspace-root> [--repair]
  detach-workspace <workspace-root> --apply
  migrate-to-multi-repository <source-project-root> --target-workspace-root <target> [--origin <git-origin>] ...
  provision-member --workspace-root <workspace-root> --origin <git-origin> ... (--dry-run|--apply)
  cleanup-member --workspace-root <workspace-root> --repository-id <id> (--dry-run|--apply)
  execution-workspace-prepare --workspace-root <workspace-root> --source-repository <repo> ...
  execution-workspace-status --runtime-root <runtime-root> --workspace-id <id> ...
  execution-workspace-mark-terminal --runtime-root <runtime-root> --workspace-id <id> --status <integrated|discarded|retired> --evidence <reference>
  execution-workspace-cleanup-owned --runtime-root <runtime-root> --workspace-id <id> ...
  execution-workspace-doctor-stale [--runtime-root <runtime-root>] [--cleanup]
  instruction-audit --root <toolkit-root> [--soft-threshold-words <count>]
  set-prefer-subagent <true|false|enable|disable|on|off> --scope <global|project> [--project-root <project-root>]
  generate-project-metadata-profile --input <authority-context> --output <output-path>
  merge-project-metadata-profile --current <current-profile> --incoming <incoming-profile> --output <output-path>
  validate-project-metadata-profile <profile-path>

Legacy commands are hard-removed and return WB_LEGACY_COMMAND_REMOVED:
  inspect-repository-model            => inspect-project-initialization
  repository-model                    => initialize-project
  validate-repository-model           => validate-project
  generate-domain-profile             => generate-project-metadata-profile
  merge-domain-profile                => merge-project-metadata-profile
  validate-domain-profile             => validate-project-metadata-profile
'''


def out(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def write(path: Path, data: str, overwrite: bool = True) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    if read(path) == data:
        return False
    path.write_text(data, encoding='utf-8')
    return True


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else None


def duty_items(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    header = f'  {key}:'
    collecting = False
    values: list[str] = []
    for line in lines:
        if not collecting and line == header:
            collecting = True
            continue
        if collecting:
            if line.startswith('  ') and not line.startswith('    '):
                break
            if line.startswith('    - '):
                values.append(line[6:].strip())
    return values


def work_bundle_config_root() -> Path:
    override = os.environ.get(WORK_BUNDLE_CONFIG_ROOT_ENV, '').strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / '.work-bundle'


def resolve_project_registry_path() -> Path:
    config_root = work_bundle_config_root()
    bootstrap_path = config_root / GLOBAL_BOOTSTRAP_FILE_NAME
    bootstrap = compact_yaml_map(read(bootstrap_path)) if bootstrap_path.is_file() else {}
    value = bootstrap.get('project_registry', '$work_bundle_config_root/registry/projects.yaml')
    value = value.replace('$work_bundle_config_root', str(config_root))
    return Path(value).expanduser().resolve()


def compact_yaml_map(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, value = line.split(':', 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def yaml_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {'true', 'yes', 'on', '1'}:
        return True
    if normalized in {'false', 'no', 'off', '0', ''}:
        return False
    return default


def utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def resolve_work_bundle_root() -> Path | None:
    env_root = os.environ.get(WORK_BUNDLE_ROOT_ENV, '').strip()
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.exists():
            return candidate.resolve()

    config_root = work_bundle_config_root()
    bootstrap_path = config_root / GLOBAL_BOOTSTRAP_FILE_NAME
    bootstrap = compact_yaml_map(read(bootstrap_path)) if bootstrap_path.is_file() else {}
    bootstrap_root_raw = bootstrap.get('work_bundle_root', '').strip()
    if bootstrap_root_raw:
        candidate = Path(bootstrap_root_raw).expanduser()
        if candidate.exists():
            return candidate.resolve()

    return None


def resolve_bootstrap_runtime() -> dict[str, object]:
    config_root = work_bundle_config_root()
    bootstrap_path = config_root / GLOBAL_BOOTSTRAP_FILE_NAME
    resolved = resolve_work_bundle_root()
    bootstrap = compact_yaml_map(read(bootstrap_path)) if bootstrap_path.is_file() else {}
    global_prefer_subagent = yaml_bool(bootstrap.get('prefer_subagent'), False)
    return {
        'work_bundle_config_root': str(config_root),
        'global_bootstrap_path': str(bootstrap_path),
        'global_bootstrap_exists': bootstrap_path.is_file(),
        'resolved_work_bundle_root': str(resolved) if resolved else None,
        'prefer_subagent': global_prefer_subagent,
    }


def project_metadata_path(project_root: Path) -> Path:
    return project_root.expanduser().resolve() / '.work-bundle' / 'project.yaml'


def resolve_effective_prefer_subagent(project_root: Path | None = None) -> dict[str, object]:
    config_root = work_bundle_config_root()
    bootstrap_path = config_root / GLOBAL_BOOTSTRAP_FILE_NAME
    bootstrap = compact_yaml_map(read(bootstrap_path)) if bootstrap_path.is_file() else {}
    global_prefer_subagent = yaml_bool(bootstrap.get('prefer_subagent'), False)

    project_path = project_metadata_path(project_root) if project_root is not None else None
    project_metadata = compact_yaml_map(read(project_path)) if project_path and project_path.is_file() else {}
    has_project_override = 'prefer_subagent' in project_metadata
    effective = yaml_bool(project_metadata.get('prefer_subagent'), global_prefer_subagent) if has_project_override else global_prefer_subagent
    source = 'project' if has_project_override else ('global' if 'prefer_subagent' in bootstrap else 'default')
    return {
        'prefer_subagent': effective,
        'source': source,
        'project_prefer_subagent': yaml_bool(project_metadata.get('prefer_subagent'), False) if has_project_override else None,
        'global_prefer_subagent': global_prefer_subagent,
        'global_bootstrap_path': str(bootstrap_path),
        'project_metadata_path': str(project_path) if project_path else None,
    }
