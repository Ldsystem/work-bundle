from __future__ import annotations

import argparse
import os
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from infrastructure import (
    atomic_write_text,
    load_bootstrap,
    parse_yaml_mapping,
    resolve_config_root,
    resolve_project_registry_path as infrastructure_registry_path,
)


CUSTOMIZED_SKILL_ROOT = Path(__file__).resolve().parents[2] / 'skills'
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

CLI_HELP_EPILOG = '''Canonical consolidated command surface:
  init-workspace <workspace-root> --slug <slug> --repository <id=remote> --mode <single-repository|multi-repository> (--dry-run|--apply)
  show-project [--workspace-root <workspace-root> | --project-root <project-root>]
  validate-project <project-root> --dry-run
  doctor-project <project-root> [--repair] [--force]
  migrate-control-plane <workspace-root> (--dry-run|--apply --accepted-proposal-id <id>)
  migrate-registered-projects (--dry-run|--apply --accepted-plan-id <id>) [--slug <slug>]
  publish-control-plane <workspace-root> --remote <git-remote> (--dry-run|--apply)
  attach-workspace <workspace-root> [--materialize none|missing|all] (--dry-run|--apply)
  doctor-workspace <workspace-root> [--repair]
  add-workspace-member <workspace-root> --repository-id <id> --remote <observed-url> --name <binding-name> --path <relative-path> --default-branch <branch> (--dry-run|--accepted-proposal-id <id> --apply)
  detach-workspace <workspace-root> --apply
  execution-workspace-prepare --workspace-root <workspace-root> --source-repository <repo> ...
  execution-workspace-status --runtime-root <runtime-root> --workspace-id <id> ...
  execution-workspace-mark-terminal --runtime-root <runtime-root> --workspace-id <id> --status <integrated|discarded|retired> --evidence <reference>
  execution-workspace-cleanup-owned --runtime-root <runtime-root> --workspace-id <id> ...
  execution-workspace-doctor-stale [--runtime-root <runtime-root>] [--cleanup]
  instruction-audit --root <toolkit-root> [--soft-threshold-words <count>]
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

Retired metadata commands return typed migration guidance:
  init-project, initialize-project => init-workspace
  migrate-project                  => migrate-control-plane or migrate-registered-projects
  migrate-to-multi-repository      => init-workspace or migrate-control-plane
  provision-member, cleanup-member => add-workspace-member or doctor-workspace
'''


def out(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def compact_yaml_map(text: str) -> dict[str, str]:
    """Compatibility view over the maintained YAML parser for scalar config fields."""
    document = parse_yaml_mapping(text, source='configuration')
    return {
        str(key): '' if value is None else str(value)
        for key, value in document.items()
        if not isinstance(value, (dict, list))
    }


def write(path: Path, data: str, overwrite: bool = True) -> bool:
    if path.exists() and not overwrite:
        return False
    if read(path) == data:
        return False
    atomic_write_text(path, data)
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
    return resolve_config_root()


def resolve_project_registry_path() -> Path:
    return infrastructure_registry_path()


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
    bootstrap = load_bootstrap() if bootstrap_path.is_file() else {}
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
    return {
        'work_bundle_config_root': str(config_root),
        'global_bootstrap_path': str(bootstrap_path),
        'global_bootstrap_exists': bootstrap_path.is_file(),
        'resolved_work_bundle_root': str(resolved) if resolved else None,
    }


def project_metadata_path(project_root: Path) -> Path:
    return project_root.expanduser().resolve() / '.work-bundle' / 'project.yaml'
