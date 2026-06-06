from __future__ import annotations

import argparse
import os
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CUSTOMIZED_SKILL_ROOT = Path('/Users/shenglong/Documents/Repository/work-bundle/skills')
GLOBAL_SKILL_REGISTRY = '~/.work-bundle/skills/skill-registry.yaml'
WORK_BUNDLE_CONFIG_ROOT_ENV = 'WB_CONFIG_ROOT'
GLOBAL_BOOTSTRAP_FILE_NAME = 'bootstrap.yaml'
WORK_BUNDLE_ROOT_POINTER_FILE_NAME = 'work-bundle-root.yaml'
WORK_BUNDLE_ROOT_POINTER_VERSION = 1
DIAG_POINTER_MISSING = 'WB_POINTER_MISSING'
DIAG_POINTER_STALE = 'WB_POINTER_STALE'
DIAG_PROJECT_METADATA_MISSING = 'WB_PROJECT_METADATA_MISSING'
DIAG_PROJECT_METADATA_INVALID = 'WB_PROJECT_METADATA_INVALID'
DIAG_LEGACY_METADATA_STALE = 'WB_PROJECT_METADATA_LEGACY_STALE'
DIAG_LEGACY_COMMAND_REMOVED = 'WB_LEGACY_COMMAND_REMOVED'
LEGACY_COMMAND_MIGRATIONS = {
    'inspect-repository-model': 'inspect-project-initialization',
    'repository-model': 'initialize-project',
    'validate-repository-model': 'validate-project',
    'generate-domain-profile': 'generate-project-metadata-profile',
    'merge-domain-profile': 'merge-project-metadata-profile',
    'validate-domain-profile': 'validate-project-metadata-profile',
}
PROJECT_METADATA_REQUIRED_FIELDS = [
    'project_root',
    'work_bundle_config_root',
    'work_bundle_root',
    'project_git',
    'work_bundle_git',
    'rules_root',
    'skills_root',
    'scripts_root',
    'metadata_version',
]
REQUIRED_PROJECT_GITIGNORE = ['.work-bundle/', 'AGENTS.md']
WORK_BUNDLE_IGNORES = ['*.secret', '*.key', '*.pem', '.env', '.env.*', 'cache/', 'tmp/', 'temp', '.DS_Store', '*.zip', '*.tar', '*.gz', '*.7z', '*.log', '.cursor/', '.idea/', '.vscode/']
ORCHESTRATION_DIRS = ['orchestration/principles', 'orchestration/templates', 'orchestration/spec/active', 'orchestration/spec/archived', 'orchestration/plan/active', 'orchestration/plan/archived', 'orchestration/handoff/executor/active', 'orchestration/handoff/orchestration/active', 'orchestration/docs', 'orchestration/reviews', 'orchestration/execution-state']
KNOWLEDGE_DIRS = ['knowledge/notes', 'knowledge/open-questions', 'knowledge/context-packs', 'knowledge/indexes']
ROLE_NAMES = ['project-manager', 'solution-architect', 'domain-analyst', 'ui-designer', 'frontend-developer', 'backend-developer', 'database-engineer', 'qa-reviewer', 'devops-engineer']
STACK_TERMS = ['Spring', 'React', 'Vue', 'Angular', 'Svelte', 'MySQL', 'PostgreSQL', 'AWS', 'Azure', 'GCP']
ROLE_KEYWORDS = {
    'project-manager': ['project', 'plan', 'timeline', 'delivery', 'coordination', 'stakeholder', 'scope'],
    'solution-architect': ['architecture', 'design', 'boundary', 'tradeoff', 'integration', 'system'],
    'domain-analyst': ['domain', 'business', 'customer', 'intent', 'process', 'requirement', 'semantics'],
    'ui-designer': ['ui', 'ux', 'prototype', 'wireframe', 'visual', 'interaction', 'figma', 'journey'],
    'frontend-developer': ['frontend', 'front-end', 'web', 'component', 'view', 'css', 'vue', 'react'],
    'backend-developer': ['backend', 'back-end', 'api', 'service', 'server', 'endpoint', 'java', 'python'],
    'database-engineer': ['data', 'database', 'schema', 'sql', 'etl', 'warehouse', 'migration'],
    'qa-reviewer': ['qa', 'test', 'testing', 'quality', 'verification', 'validation', 'acceptance'],
    'devops-engineer': ['devops', 'deployment', 'release', 'pipeline', 'ci', 'cd', 'operation', 'infra'],
}
RULES = ['repository-boundary', 'knowledge-boundary', 'orchestration-boundary', 'lifecycle-authority', 'retrieval-gateway', 'role-context', 'skill-registry', 'domain-profile', 'execution-boundary', 'handoff-boundary', 'review-archive-boundary', 'doctor-readonly', 'runtime-artifact-format', 'security-exclusion']
STAGE_MAP = {
    'tender': ('domain-analyst', ['project-manager']),
    'investigation': ('domain-analyst', ['solution-architect', 'project-manager']),
    'customer-design': ('domain-analyst', ['ui-designer', 'project-manager', 'solution-architect']),
    'bidding': ('project-manager', ['domain-analyst', 'solution-architect']),
    'development-design': ('solution-architect', ['backend-developer', 'frontend-developer', 'database-engineer', 'qa-reviewer', 'ui-designer']),
    'implementation': ('backend-developer', ['frontend-developer', 'database-engineer', 'qa-reviewer', 'solution-architect']),
    'deployment': ('devops-engineer', ['database-engineer', 'qa-reviewer']),
    'go-live-delivery': ('project-manager', ['qa-reviewer', 'devops-engineer', 'domain-analyst']),
    'operation': ('devops-engineer', ['database-engineer', 'qa-reviewer', 'solution-architect']),
    'repository-management': ('devops-engineer', ['solution-architect']),
}
LEAF_MAP = {
    'development-design/data/schema': ('solution-architect', ['database-engineer']),
    'development-design/implementation/backend': ('solution-architect', ['backend-developer', 'qa-reviewer']),
    'development-design/implementation/frontend': ('solution-architect', ['frontend-developer', 'ui-designer', 'qa-reviewer']),
    'customer-design/ui-prototype': ('domain-analyst', ['ui-designer']),
    'implementation/tests': ('backend-developer', ['qa-reviewer']),
    'repository-management/gitignore-repair': ('devops-engineer', ['solution-architect']),
}
DIRECTIVE_ALLOWED_SKILLS = {
    'create-specification': ['create-specification', 'wb-initialize-project', 'wb-select-role-context'],
    'create-implementation-plan': ['orchestrator', 'wb-select-role-context'],
    'execute-plan': [],
    'create-handoff': ['orchestrator', 'wb-select-role-context'],
    'review-plan': ['orchestrator', 'wb-doctor'],
    'create-document': ['orchestrator', 'wb-select-role-context'],
    'wb-doctor': ['wb-doctor'],
}

AGENTS = '# Agent Entry\n\nThis project uses a local work bundle for agent knowledge and orchestration.\n\nRead:\n\n```text\nreferences/bootstrap/agent-bootstrap.md\n.work-bundle/project.yaml\n```\n\nDo not commit this file to the project repository by default.\n'
BOOTSTRAP = '''# Agent Bootstrap (Compatibility Bridge)

## Authority
Canonical bootstrap authority is global: `~/.work-bundle/bootstrap.yaml`.
This repository file is compatibility guidance, not the primary bootstrap authority.

## Canonical Root Model
- `work-bundle-root`: installed work-bundle source root resolved from `~/.work-bundle/work-bundle-root.yaml`.
- `project-root`: current workspace root.
- `work-bundle-config-root`: `~/.work-bundle/`.

## Root Pointer Contract
Pointer file: `~/.work-bundle/work-bundle-root.yaml`
Required fields:
- `pointer_version` (integer, current `1`)
- `work_bundle_root` (string path)
- `updated_at` (RFC3339 UTC timestamp)

Deterministic diagnostics:
- missing pointer: `WB_POINTER_MISSING`
- stale pointer: `WB_POINTER_STALE`

## Required Loading Order
1. load global bootstrap from `~/.work-bundle/bootstrap.yaml`
2. resolve `work-bundle-root` via `~/.work-bundle/work-bundle-root.yaml`
3. load canonical project metadata from `<project-root>/.work-bundle/project.yaml`
4. verify project Git boundary
5. verify work-bundle Git boundary
6. resolve enabled work-bundle rules for current task
7. load task-specific spec or plan

## Transition Notes
- Do not treat project-local bootstrap markdown as authority.
- Do not encode project identity in global bootstrap authority.
- Do not use split metadata files as runtime authority.
- Keep runtime artifacts compact and machine-readable.
'''
PROFILE = '''id: project-domain-profile
status: deprecated
authority: compatibility-reference
canonical_metadata: .work-bundle/project.yaml
migration_owner: /wb-initialize-project
doctor_flow: /wb-initialize-project doctor
migrate_flow: /wb-initialize-project migrate
version: 1
generated_by: wb-initialize-project
updated_at: 2026-05-25
industry: agent-workflow-tooling
business_context: Local-first agent knowledge and orchestration workflow tooling.
core_domain_objects: [work-bundle, durable-knowledge, orchestration-artifact, skill, runtime-rule, role-context]
core_lifecycles: [spec -> plan -> phase -> task -> execute -> handoff -> review]
domain_constraints: [keep durable knowledge separate from orchestration artifacts, compact runtime files first]
common_misunderstandings: [do not treat open questions as facts, do not let execute-plan retrieve knowledge]
current_lifecycle_stage: development-design
stage_specific_authority:
  tender: weak input unless confirmed later
  investigation: discovery findings; useful for scope and clarification
  customer-design: customer-visible intent, not engineering authority by default
  bidding: commercial commitment; not implementation design by default
  development-design: primary authority for specs and plans
  implementation: verified behavior from code, handoff, review, or tests
  deployment: runtime and rollout authority
  go-live-delivery: delivery and acceptance authority
  operation: production/runtime authority
role_positioning:
  default: selected role profiles must apply this domain profile before producing domain-sensitive output
source_knowledge:
  - path: explicit-source
    role: authority
    reason: input context
warnings: []
'''
RULE_CONTRACT = 'id: work-bundle-rule-contract\nstatus: current\nrule_format: yaml\nscope: work-bundle\nrequired_fields: [id, status, scope, applies_to, enable_when, severity, rule, required_behavior, prohibited_behavior, validation, source_authority]\ndeprecated_formats: [mdc]\ndeprecated_sources_policy: deprecated_mdc_reference_only\n'
CLI_HELP_EPILOG = '''Canonical consolidated command surface:
  inspect-project-initialization <project-root>
  initialize-project <project-root>
  validate-project <project-root> --dry-run
  generate-project-metadata-profile --input <authority-context> --output references/bootstrap/project-domain-profile.yaml
  merge-project-metadata-profile --current references/bootstrap/project-domain-profile.yaml --incoming <incoming-profile> --output references/bootstrap/project-domain-profile.yaml
  validate-project-metadata-profile references/bootstrap/project-domain-profile.yaml

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


def ensure_lines(path: Path, lines: list[str]) -> bool:
    current = read(path).splitlines()
    changed = False
    for line in lines:
        if line not in current:
            current.append(line)
            changed = True
    if changed or not path.exists():
        write(path, '\n'.join(current).rstrip() + '\n')
    return changed


def has_ignore(lines: list[str], wanted: str) -> bool:
    variants = {wanted, wanted.rstrip('/'), '/' + wanted.rstrip('/')}
    return any(line.strip() in variants for line in lines)


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


def compact_yaml_map(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, value = line.split(':', 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def resolve_bootstrap_runtime() -> dict[str, object]:
    config_root = work_bundle_config_root()
    bootstrap_path = config_root / GLOBAL_BOOTSTRAP_FILE_NAME
    pointer_path = config_root / WORK_BUNDLE_ROOT_POINTER_FILE_NAME
    result: dict[str, object] = {
        'work_bundle_config_root': str(config_root),
        'global_bootstrap_path': str(bootstrap_path),
        'global_bootstrap_exists': bootstrap_path.exists(),
        'work_bundle_root_pointer_path': str(pointer_path),
        'work_bundle_root_pointer_exists': pointer_path.exists(),
        'work_bundle_root_pointer_state': 'missing',
        'work_bundle_root_pointer_diagnostic': DIAG_POINTER_MISSING,
        'work_bundle_root_pointer_reason': 'pointer file not found',
        'resolved_work_bundle_root': None,
    }
    if not pointer_path.exists():
        return result
    pointer = compact_yaml_map(read(pointer_path))
    reasons: list[str] = []
    version_raw = pointer.get('pointer_version')
    try:
        version = int(version_raw) if version_raw is not None else None
    except ValueError:
        version = None
    if version != WORK_BUNDLE_ROOT_POINTER_VERSION:
        reasons.append('unsupported pointer_version')
    root_raw = pointer.get('work_bundle_root', '').strip()
    resolved_root: Path | None = None
    if not root_raw:
        reasons.append('missing work_bundle_root')
    else:
        resolved_root = Path(root_raw).expanduser()
        if not resolved_root.exists():
            reasons.append('work_bundle_root path does not exist')
    updated_at = pointer.get('updated_at', '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', updated_at):
        reasons.append('invalid updated_at')
    if reasons:
        result['work_bundle_root_pointer_state'] = 'stale'
        result['work_bundle_root_pointer_diagnostic'] = DIAG_POINTER_STALE
        result['work_bundle_root_pointer_reason'] = '; '.join(reasons)
        return result
    result['work_bundle_root_pointer_state'] = 'present'
    result['work_bundle_root_pointer_diagnostic'] = None
    result['work_bundle_root_pointer_reason'] = None
    result['resolved_work_bundle_root'] = str(resolved_root) if resolved_root else None
    return result


def ensure_work_bundle_root_pointer(work_bundle_root: Path) -> str | None:
    config_root = work_bundle_config_root()
    pointer_path = config_root / WORK_BUNDLE_ROOT_POINTER_FILE_NAME
    text = '\n'.join([
        f'pointer_version: {WORK_BUNDLE_ROOT_POINTER_VERSION}',
        f'work_bundle_root: {work_bundle_root.resolve()}',
        f'updated_at: {utc_now_rfc3339()}',
    ]) + '\n'
    changed = write(pointer_path, text)
    return str(pointer_path) if changed else None


def role_duty_profile(project_root: Path, role: str) -> dict:
    path = project_root / 'roles' / f'{role}.yaml'
    text = read(path)
    if not text:
        return {'role': role, 'profile_found': False, 'profile_path': str(path), 'stance': None, 'capabilities': [], 'duties': [], 'must_resolve_from_context': []}
    return {
        'role': role,
        'profile_found': True,
        'profile_path': str(path),
        'stance': first_match(r'^\s{2}stance:\s*(.+)$', text),
        'capabilities': duty_items(text, 'skilled_at'),
        'duties': duty_items(text, 'quality_focus'),
        'must_resolve_from_context': duty_items(text, 'must_resolve_from_context'),
    }


def suggest_draft_role(stage: str, perspective: str) -> str:
    scores = {role: 0 for role in ROLE_NAMES}
    signals = f'{stage} {perspective}'.lower()
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in signals:
                scores[role] += 1
    if stage in STAGE_MAP:
        primary, supporting = STAGE_MAP[stage]
        scores[primary] += 2
        for role in supporting:
            scores[role] += 1
    if perspective in LEAF_MAP:
        primary, supporting = LEAF_MAP[perspective]
        scores[primary] += 3
        for role in supporting:
            scores[role] += 2
    ranked = sorted(scores.items(), key=lambda item: (-item[1], ROLE_NAMES.index(item[0])))
    for role, score in ranked:
        if score > 0:
            return role
    return 'solution-architect'


def role_duty_failures(roles_root: Path) -> list[str]:
    failures: list[str] = []
    for role in ROLE_NAMES:
        path = roles_root / f'{role}.yaml'
        text = read(path)
        if not path.exists():
            failures.append(f'role_missing:{role}')
            continue
        for key, token in {
            'duty_profile': 'duty_profile:',
            'stance': '  stance:',
            'skilled_at': '  skilled_at:',
            'quality_focus': '  quality_focus:',
            'must_resolve_from_context': '  must_resolve_from_context:',
        }.items():
            if token not in text:
                failures.append(f'role_duty_missing:{role}:{key}')
        if role in {'frontend-developer', 'backend-developer', 'database-engineer', 'devops-engineer'}:
            for term in STACK_TERMS:
                if term in text:
                    failures.append(f'role_duty_assumes_stack:{role}:{term}')
        if 'project-domain-profile' not in text:
            failures.append(f'role_missing_domain_profile_reference:{role}')
    return failures


def binding(project_root: Path) -> str:
    pgi = read(project_root / '.gitignore').splitlines()
    wb = project_root / '.work-bundle'
    override = wb / 'orchestration' / 'skill-registry.override.yaml'
    return f"""# Repository Binding (Deprecated Authority)

This file is retained only as a compatibility reference.
Canonical project metadata authority is `<project-root>/.work-bundle/project.yaml`.

## Migration owner
- `/wb-initialize-project`

## Deterministic migration guidance
- Doctor legacy structure: `/wb-initialize-project doctor`
- Migrate to canonical metadata: `/wb-initialize-project migrate`

## Last observed repository state (non-authoritative)
```yaml
project_root: {project_root}
project_git_exists: {str((project_root / '.git').exists()).lower()}
project_gitignore: {project_root / '.gitignore'}
project_ignores_work_bundle: {str(has_ignore(pgi, '.work-bundle/')).lower()}
project_ignores_agent_entry: {str(has_ignore(pgi, 'AGENTS.md')).lower()}
work_bundle_root: {wb}
work_bundle_git_repo: {str((wb / '.git').exists()).lower()}
work_bundle_gitignore: {wb / '.gitignore'}
agent_entry_path: {project_root / 'AGENTS.md'}
project_skill_override: {override if override.exists() else 'not configured'}
global_skill_registry: {GLOBAL_SKILL_REGISTRY}
customized_skill_root: {CUSTOMIZED_SKILL_ROOT}
```
"""


def inspect_project(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    rules = project_root / 'rules'
    roles = project_root / 'roles'
    pgi = read(project_root / '.gitignore').splitlines()
    wbi = read(wb / '.gitignore').splitlines()
    rb = read(project_root / 'references/bootstrap/repository-binding.md')
    pdp = read(project_root / 'references/bootstrap/project-domain-profile.yaml')
    ab = read(project_root / 'references/bootstrap/agent-bootstrap.md')
    pm = read(project_root / '.work-bundle/project.yaml')
    runtime = resolve_bootstrap_runtime()
    project_metadata_path = project_root / '.work-bundle/project.yaml'
    project_metadata_missing = [field for field in PROJECT_METADATA_REQUIRED_FIELDS if f'{field}:' not in pm]
    legacy_reference_paths = [
        'references/bootstrap/repository-binding.md',
        'references/bootstrap/project-domain-profile.yaml',
    ]
    legacy_guidance_tokens = ['/wb-initialize-project doctor', '/wb-initialize-project migrate', '.work-bundle/project.yaml']
    legacy_guidance_missing = []
    for rel in legacy_reference_paths:
        text = read(project_root / rel)
        if text and not all(token in text for token in legacy_guidance_tokens):
            legacy_guidance_missing.append(rel)
    return {
        'project_root': str(project_root),
        'project_git': (project_root / '.git').exists(),
        'project_gitignore': (project_root / '.gitignore').exists(),
        'project_ignores_work_bundle': has_ignore(pgi, '.work-bundle/'),
        'project_ignores_agents': has_ignore(pgi, 'AGENTS.md'),
        'agents_md': (project_root / 'AGENTS.md').exists(),
        'work_bundle': wb.exists(),
        'work_bundle_git': (wb / '.git').exists(),
        'work_bundle_gitignore': (wb / '.gitignore').exists(),
        'work_bundle_gitignore_required_entries': all(x in wbi for x in WORK_BUNDLE_IGNORES),
        'knowledge_root': (wb / 'knowledge').exists(),
        'orchestration_root': (wb / 'orchestration').exists(),
        'orchestration_tree': all((wb / d).exists() for d in ORCHESTRATION_DIRS),
        'bootstrap_root': (project_root / 'references/bootstrap').exists(),
        'repository_binding': (project_root / 'references/bootstrap/repository-binding.md').exists(),
        'repository_binding_migration_guidance': all(token in rb for token in legacy_guidance_tokens),
        'agent_bootstrap': (project_root / 'references/bootstrap/agent-bootstrap.md').exists(),
        'agent_bootstrap_loading_order': all(s in ab for s in ['load global bootstrap', 'resolve `work-bundle-root`', 'load canonical project metadata', 'verify project Git boundary', 'verify work-bundle Git boundary']),
        'agent_bootstrap_migration_guidance': '/wb-initialize-project' in ab,
        'project_domain_profile': (project_root / 'references/bootstrap/project-domain-profile.yaml').exists(),
        'domain_profile': (project_root / 'references/bootstrap/project-domain-profile.yaml').exists(),
        'project_domain_profile_migration_guidance': all(token in pdp for token in legacy_guidance_tokens),
        'project_metadata_path': str(project_metadata_path),
        'project_metadata_exists': project_metadata_path.exists(),
        'project_metadata_required_fields_missing': project_metadata_missing,
        'project_metadata_valid': not project_metadata_missing,
        'project_metadata_authority': '.work-bundle/project.yaml',
        'legacy_metadata_references_with_missing_guidance': legacy_guidance_missing,
        'rules_root': rules.exists(),
        'rule_files': len(list(rules.glob('*.yaml'))) if rules.exists() else 0,
        'rule_contract': (rules / 'contract.yaml').exists(),
        'rule_contract_requires_enable_when': 'enable_when' in read(rules / 'contract.yaml'),
        'rule_index': (rules / 'index.yaml').exists(),
        'roles_root': roles.exists(),
        'role_files': len(list(roles.glob('*.yaml'))) if roles.exists() else 0,
        'role_profiles': all((roles / f'{r}.yaml').exists() for r in ROLE_NAMES),
        'role_duty_failures': role_duty_failures(roles),
        'mdc_rules': [str(p) for p in rules.glob('**/*.mdc')] if rules.exists() else [],
        'global_registry_copied': (wb / 'skills/skill-registry.yaml').exists(),
        'project_skill_override': (wb / 'orchestration/skill-registry.override.yaml').exists(),
        'path_model': {
            'project_root': str(project_root),
            'work_bundle_root': runtime.get('resolved_work_bundle_root'),
            'work_bundle_config_root': runtime.get('work_bundle_config_root'),
        },
        'global_bootstrap_path': runtime.get('global_bootstrap_path'),
        'global_bootstrap_exists': runtime.get('global_bootstrap_exists'),
        'work_bundle_root_pointer_path': runtime.get('work_bundle_root_pointer_path'),
        'work_bundle_root_pointer_exists': runtime.get('work_bundle_root_pointer_exists'),
        'work_bundle_root_pointer_state': runtime.get('work_bundle_root_pointer_state'),
        'work_bundle_root_pointer_diagnostic': runtime.get('work_bundle_root_pointer_diagnostic'),
        'work_bundle_root_pointer_reason': runtime.get('work_bundle_root_pointer_reason'),
        'resolved_work_bundle_root': runtime.get('resolved_work_bundle_root'),
    }


def project_failures(data: dict, strict: bool = True, include_roles: bool = False) -> list[str]:
    required = ['project_gitignore', 'project_ignores_work_bundle', 'project_ignores_agents', 'agents_md', 'work_bundle', 'work_bundle_gitignore', 'knowledge_root', 'orchestration_root', 'bootstrap_root', 'repository_binding', 'agent_bootstrap', 'project_domain_profile', 'rules_root', 'project_metadata_exists']
    if strict:
        required.extend(['work_bundle_gitignore_required_entries', 'orchestration_tree', 'repository_binding_migration_guidance', 'project_domain_profile_migration_guidance', 'agent_bootstrap_loading_order', 'agent_bootstrap_migration_guidance', 'rule_contract', 'rule_contract_requires_enable_when', 'rule_index', 'roles_root', 'role_profiles'])
    failures = [k for k in required if not data.get(k)]
    if not data.get('project_metadata_exists'):
        failures.append(DIAG_PROJECT_METADATA_MISSING)
    if data.get('project_metadata_exists') and data.get('project_metadata_required_fields_missing'):
        failures.append(DIAG_PROJECT_METADATA_INVALID)
    if data.get('legacy_metadata_references_with_missing_guidance'):
        failures.append(DIAG_LEGACY_METADATA_STALE)
    if include_roles:
        failures.extend(data.get('role_duty_failures') or [])
    if data.get('mdc_rules'):
        failures.append('mdc_rules_present')
    if data.get('global_registry_copied'):
        failures.append('global_registry_not_copied')
    pointer_diagnostic = data.get('work_bundle_root_pointer_diagnostic')
    if pointer_diagnostic:
        failures.append(pointer_diagnostic)
    return failures


def apply_project(project_root: Path, init_git: bool = True, create_override: bool = False) -> list[str]:
    wb = project_root / '.work-bundle'
    changed: list[str] = []
    if ensure_lines(project_root / '.gitignore', REQUIRED_PROJECT_GITIGNORE):
        changed.append(str(project_root / '.gitignore'))
    if write(project_root / 'AGENTS.md', AGENTS, overwrite=False):
        changed.append(str(project_root / 'AGENTS.md'))
    for directory in KNOWLEDGE_DIRS + ORCHESTRATION_DIRS:
        path = wb / directory
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            changed.append(str(path))
    for directory in ['references/bootstrap', 'roles', 'rules']:
        path = project_root / directory
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            changed.append(str(path))
    if write(wb / 'knowledge/project.yaml', 'id: project\nstatus: current\n', overwrite=False):
        changed.append(str(wb / 'knowledge/project.yaml'))
    if ensure_lines(wb / '.gitignore', WORK_BUNDLE_IGNORES):
        changed.append(str(wb / '.gitignore'))
    if init_git and not (wb / '.git').exists():
        subprocess.run(['git', 'init', str(wb)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        changed.append(str(wb / '.git'))
    if write(project_root / 'references/bootstrap/repository-binding.md', binding(project_root)):
        changed.append(str(project_root / 'references/bootstrap/repository-binding.md'))
    if write(project_root / 'references/bootstrap/agent-bootstrap.md', BOOTSTRAP):
        changed.append(str(project_root / 'references/bootstrap/agent-bootstrap.md'))
    if write(project_root / 'references/bootstrap/project-domain-profile.yaml', PROFILE, overwrite=False):
        changed.append(str(project_root / 'references/bootstrap/project-domain-profile.yaml'))
    if write(project_root / 'rules/contract.yaml', RULE_CONTRACT, overwrite=False):
        changed.append(str(project_root / 'rules/contract.yaml'))
    if write(project_root / 'rules/index.yaml', 'rules_root: rules\ngenerated_by: wb-initialize-project\nstatus: initialized\nrule_files: []\n', overwrite=False):
        changed.append(str(project_root / 'rules/index.yaml'))
    if write(project_root / '.work-bundle/project.yaml', '\n'.join([
        'metadata_version: 1',
        'authority: canonical',
        f'project_root: {project_root}',
        'work_bundle_config_root: ~/.work-bundle',
        f'work_bundle_root: {project_root / ".work-bundle"}',
        'project_git:',
        f'  exists: {str((project_root / ".git").exists()).lower()}',
        f'  gitignore: {project_root / ".gitignore"}',
        f'  ignores_work_bundle: {str(has_ignore(read(project_root / ".gitignore").splitlines(), ".work-bundle/")).lower()}',
        f'  ignores_agent_entry: {str(has_ignore(read(project_root / ".gitignore").splitlines(), "AGENTS.md")).lower()}',
        'work_bundle_git:',
        f'  exists: {str((project_root / ".work-bundle/.git").exists()).lower()}',
        f'  gitignore: {project_root / ".work-bundle/.gitignore"}',
        f'rules_root: {project_root / "rules"}',
        f'skills_root: {project_root / "skills"}',
        f'scripts_root: {project_root / "scripts"}',
        'migration:',
        '  authority_owner: /wb-initialize-project',
        '  compatibility_window: none',
        '  doctor_flow: "Use /wb-initialize-project doctor for stale legacy project metadata structures."',
        '  migrate_flow: "Use /wb-initialize-project migrate to converge old metadata paths to .work-bundle/project.yaml."',
        '',
    ]), overwrite=False):
        changed.append(str(project_root / '.work-bundle/project.yaml'))
    if create_override:
        path = wb / 'orchestration/skill-registry.override.yaml'
        if write(path, 'id: project-skill-registry-override\nstatus: current\noverrides: {}\n', overwrite=False):
            changed.append(str(path))
    pointer_path = ensure_work_bundle_root_pointer(project_root)
    if pointer_path:
        changed.append(pointer_path)
    return sorted(set(changed))


