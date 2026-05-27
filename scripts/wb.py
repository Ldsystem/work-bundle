from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


CUSTOMIZED_SKILL_ROOT = Path('/Users/shenglong/Documents/Repository/work-bundle/skills')
GLOBAL_SKILL_REGISTRY = '~/.work-bundle/skills/skill-registry.yaml'
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
    'create-specification': ['create-specification', 'wb-generate-domain-profile', 'wb-select-role-context'],
    'create-implementation-plan': ['orchestrator', 'wb-select-role-context'],
    'execute-plan': [],
    'create-handoff': ['orchestrator', 'wb-select-role-context'],
    'review-plan': ['orchestrator', 'wb-doctor'],
    'create-document': ['orchestrator', 'wb-select-role-context'],
    'wb-doctor': ['wb-doctor'],
}

AGENTS = '# Agent Entry\n\nThis project uses a local work bundle for agent knowledge and orchestration.\n\nRead:\n\n```text\nreferences/bootstrap/agent-bootstrap.md\nreferences/bootstrap/repository-binding.md\n```\n\nDo not commit this file to the project repository by default.\n'
BOOTSTRAP = '''# Agent Bootstrap

## Project Identity
project: keep-summarizing

## Repository Layout
work_bundle: .work-bundle
source_code_root: .

## Git Boundary
Project Git and work-bundle Git are separate. Do not mix commit scopes by default.

## Project Gitignore
.gitignore must ignore .work-bundle/ and AGENTS.md.

## Work Bundle Git Repository
.work-bundle/.git

## Knowledge Source of Truth
.work-bundle/knowledge/

## Orchestration Artifact Root
.work-bundle/orchestration/

## Work Bundle Rules Root
references/rules/

## Project Agents Entry
AGENTS.md

## Required Loading Order
1. repository-binding.md
2. verify project Git boundary
3. verify work-bundle Git boundary
4. agent-bootstrap.md
5. load work-bundle rules contract and rule index
6. resolve enabled work-bundle rules for current task
7. project.yaml
8. project-domain-profile.yaml
9. identify current lifecycle stage
10. load relevant stage-first notes only through allowed gateway/directive rules
11. classify retrieved notes by status and retrieval role
12. load relevant open-question records when allowed
13. select primary role profile by lifecycle stage
14. select supporting role profiles by leaf perspective
15. locate customized skill root
16. load global skill registry
17. load optional project skill registry override if present
18. load task-specific spec or plan

## Available Role Profiles
references/roles/

## Available Skill Registry
~/.work-bundle/skills/skill-registry.yaml

## Customized Skill Root
/Users/shenglong/Documents/Repository/work-bundle/skills

## Project Skill Override
optional: .work-bundle/orchestration/skill-registry.override.yaml

## Project Registry
The optional global project registry lives at `~/.work-bundle/registry/projects.yaml` unless `KS_PROJECT_REGISTRY` or `--registry-file` overrides it.

Use it only as local runtime state for project discovery. Do not copy it into skill resources, durable project knowledge, orchestration artifacts, or reusable templates.

Resolution priority:

1. explicit `--knowledge-root`
2. explicit `--project-root`
3. walk upward from `--cwd` or current directory to find `.work-bundle/knowledge`
4. global project registry by slug, alias, work-bundle root, or source repository path
5. explicit external legacy root for migration/read-only intake

## Enabled Work Bundle Rules
Resolve from references/rules/index.yaml before directive-specific behavior.

## Output Rules
Keep runtime artifacts compact and machine-readable. Prefer compact YAML for runtime rules, role profiles, domain profile, and role context.

## Handoff Rules
Use .work-bundle/orchestration/handoff/. Executor handoffs carry role_context_used when available.

## Forbidden Behavior
Do not write durable knowledge from orchestration directives. Do not generate .mdc rules. Do not treat deprecated .mdc files as current authority.
'''
PROFILE = '''id: project-domain-profile
status: current
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


def role_duty_profile(project_root: Path, role: str) -> dict:
    path = project_root / 'references' / 'roles' / f'{role}.yaml'
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
    return f"""# Repository Binding

```yaml
project_root: {project_root}
project_git:
  exists: {str((project_root / '.git').exists()).lower()}
  gitignore: {project_root / '.gitignore'}
  ignores_work_bundle: {str(has_ignore(pgi, '.work-bundle/')).lower()}
  ignores_agent_entry: {str(has_ignore(pgi, 'AGENTS.md')).lower()}
source_code_root: {project_root}
skills_root: {project_root / 'skills'}
scripts_root: {project_root / 'scripts'}
references_root: {project_root / 'references'}
roles_root: {project_root / 'references/roles'}
rules_root: {project_root / 'references/rules'}
rule_contract: {project_root / 'references/rules/contract.yaml'}
rule_index: {project_root / 'references/rules/index.yaml'}
knowledge_root: {wb / 'knowledge'}
orchestration_root: {wb / 'orchestration'}
work_bundle:
  root: {wb}
  git_repo: {str((wb / '.git').exists()).lower()}
  gitignore: {wb / '.gitignore'}
agent_entry:
  path: {project_root / 'AGENTS.md'}
  ignored_by_project_git: {str(has_ignore(pgi, 'AGENTS.md')).lower()}
customized_skill_root: {CUSTOMIZED_SKILL_ROOT}
global_skill_registry: {GLOBAL_SKILL_REGISTRY}
project_skill_override: {override if override.exists() else 'not configured'}
optional_git_remote: not configured
branch_defaults:
  project: current
  work_bundle: current
private_repository_notes: no secrets or credentials are recorded here
deprecated_rule_format: mdc
```
"""


def inspect_project(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    rules = project_root / 'references/rules'
    roles = project_root / 'references/roles'
    pgi = read(project_root / '.gitignore').splitlines()
    wbi = read(wb / '.gitignore').splitlines()
    rb = read(project_root / 'references/bootstrap/repository-binding.md')
    ab = read(project_root / 'references/bootstrap/agent-bootstrap.md')
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
        'repository_binding_records_state': all(k in rb for k in ['project_git:', 'ignores_work_bundle:', 'ignores_agent_entry:', 'work_bundle:', 'git_repo:', 'agent_entry:']),
        'agent_bootstrap': (project_root / 'references/bootstrap/agent-bootstrap.md').exists(),
        'agent_bootstrap_loading_order': all(s in ab for s in ['verify project Git boundary', 'verify work-bundle Git boundary', 'load global skill registry', 'load optional project skill registry override']),
        'project_domain_profile': (project_root / 'references/bootstrap/project-domain-profile.yaml').exists(),
        'domain_profile': (project_root / 'references/bootstrap/project-domain-profile.yaml').exists(),
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
    }


def project_failures(data: dict, strict: bool = True, include_roles: bool = False) -> list[str]:
    required = ['project_gitignore', 'project_ignores_work_bundle', 'project_ignores_agents', 'agents_md', 'work_bundle', 'work_bundle_gitignore', 'knowledge_root', 'orchestration_root', 'bootstrap_root', 'repository_binding', 'agent_bootstrap', 'project_domain_profile', 'rules_root']
    if strict:
        required.extend(['work_bundle_gitignore_required_entries', 'orchestration_tree', 'repository_binding_records_state', 'rule_contract', 'rule_contract_requires_enable_when', 'rule_index', 'roles_root', 'role_profiles'])
    failures = [k for k in required if not data.get(k)]
    if include_roles:
        failures.extend(data.get('role_duty_failures') or [])
    if data.get('mdc_rules'):
        failures.append('mdc_rules_present')
    if data.get('global_registry_copied'):
        failures.append('global_registry_not_copied')
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
    for directory in ['references/bootstrap', 'references/roles', 'references/rules']:
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
    if write(project_root / 'references/rules/contract.yaml', RULE_CONTRACT, overwrite=False):
        changed.append(str(project_root / 'references/rules/contract.yaml'))
    if write(project_root / 'references/rules/index.yaml', 'rules_root: references/rules\ngenerated_by: wb-initialize-project\nstatus: initialized\nrule_files: []\n', overwrite=False):
        changed.append(str(project_root / 'references/rules/index.yaml'))
    if create_override:
        path = wb / 'orchestration/skill-registry.override.yaml'
        if write(path, 'id: project-skill-registry-override\nstatus: current\noverrides: {}\n', overwrite=False):
            changed.append(str(path))
    return sorted(set(changed))


def rule_text(name: str) -> str:
    return f'''id: rule-work-bundle-{name}
status: current
scope: work-bundle
applies_to: {{paths: [.work-bundle/**], skills: [], artifacts: []}}
enable_when: [v4 work-bundle operation requires {name}]
severity: must
rule: {name} rule applies to v4 work-bundle operations.
required_behavior: [follow source authority, keep runtime files compact]
prohibited_behavior: [do not generate .mdc files, do not include raw logs or secrets]
validation: [required fields exist, scope is work-bundle]
source_authority: [.work-bundle/orchestration/spec/active/spec-process-v4-project-local-agent-operating-system.md]
deprecated_sources: []
'''


def cmd_create_rules(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py create-rules')
    parser.add_argument('rules_root')
    parsed = parser.parse_args(args)
    root = Path(parsed.rules_root)
    root.mkdir(parents=True, exist_ok=True)
    for rule in RULES:
        write(root / f'{rule}.yaml', rule_text(rule))
    write(root / 'index.yaml', 'id: work-bundle-rule-index\nstatus: current\nrules:\n' + ''.join(f'  - {rule}.yaml\n' for rule in RULES))
    out({'status': 'passed', 'rules': RULES})
    return 0


def cmd_validate_rules(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py validate-rules')
    parser.add_argument('rules_root')
    parsed = parser.parse_args(args)
    root = Path(parsed.rules_root)
    failures: list[str] = []
    if list(root.glob('*.mdc')):
        failures.append('generated_mdc_present')
    for path in root.glob('*.yaml'):
        if path.name in {'index.yaml', 'contract.yaml'}:
            continue
        text = read(path)
        for token in ['id:', 'status:', 'scope: work-bundle', 'enable_when:', 'severity:', 'required_behavior:', 'prohibited_behavior:', 'validation:', 'source_authority:']:
            if token not in text:
                failures.append(f'{path.name}:{token}')
        if len(text.splitlines()) > 80:
            failures.append(f'{path.name}:prose_heavy')
    out({'status': 'passed' if not failures else 'issues-found', 'failures': failures})
    return 0 if not failures else 1


def cmd_project(args: list[str], apply: bool = False, inspect_only: bool = False, repo_model: bool = False) -> int:
    parser = argparse.ArgumentParser(prog='wb.py initialize-project' if apply else 'wb.py validate-project')
    parser.add_argument('project_root')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--disable-work-bundle-git', action='store_true')
    parser.add_argument('--create-project-skill-override', action='store_true')
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).resolve()
    changed: list[str] | str = 'none'
    if apply and not parsed.dry_run:
        changed = apply_project(project_root, init_git=not parsed.disable_work_bundle_git, create_override=parsed.create_project_skill_override)
    data = inspect_project(project_root)
    failures = project_failures(data, strict=not inspect_only, include_roles=False)
    data['status'] = 'passed' if not failures else 'issues-found'
    data['failures'] = failures
    if parsed.dry_run:
        data['dry_run'] = True
    if apply and not parsed.dry_run:
        data['changed_files'] = changed
    out(data)
    return 0 if not failures else 1


def cmd_doctor(args: list[str], report: bool = False, workflow: bool = False) -> int:
    parser = argparse.ArgumentParser(prog='wb.py doctor')
    parser.add_argument('project_root')
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).resolve()
    if workflow:
        required = ['success', 'blocked', 'invalid', 'missing-context', 'repair-needed', 'no-op-idempotent', 'read-only-diagnosis']
        evidence = project_root / '.work-bundle/orchestration/reviews/branch-validation/evidence.json'
        if not evidence.exists():
            out({'status': 'issues-found', 'failures': ['missing_branch_evidence'], 'required_branches': required})
            return 1
        data = json.loads(read(evidence))
        seen = {item.get('branch') for item in data.get('evidence', [])}
        missing = [branch for branch in required if branch not in seen]
        out({'status': 'passed' if not missing else 'issues-found', 'missing': missing, 'evidence': str(evidence)})
        return 0 if not missing else 1
    data = inspect_project(project_root)
    failures = project_failures(data, strict=False, include_roles=True)
    if report:
        print('# Doctor Report\n')
        print('## Status\n')
        print('passed' if not failures else 'issues-found')
        print('\n## Target\n')
        print(project_root)
        print('\n## Errors\n')
        print('none' if not failures else '\n'.join(f'- {failure}' for failure in failures))
        print('\n## Files Changed\nnone')
    else:
        out({'status': 'passed' if not failures else 'issues-found', 'failures': failures, 'files_changed': 'none', 'data': data})
    return 0 if not failures else 1


def cmd_domain_profile(args: list[str], merge: bool = False, validate: bool = False) -> int:
    if validate:
        parser = argparse.ArgumentParser(prog='wb.py validate-domain-profile')
        parser.add_argument('profile')
        parsed = parser.parse_args(args)
        text = read(Path(parsed.profile))
        failures = [token for token in ['id:', 'status:', 'industry:', 'business_context:', 'source_knowledge:', 'role_positioning:', 'warnings:'] if token not in text]
        if len(text.splitlines()) > 120:
            failures.append('prose_heavy')
        out({'path': parsed.profile, 'status': 'passed' if not failures else 'issues-found', 'failures': failures, 'line_count': len(text.splitlines())})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py merge-domain-profile' if merge else 'wb.py generate-domain-profile')
    if merge:
        parser.add_argument('--current')
        parser.add_argument('--incoming', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(args)
        write(Path(parsed.output), read(Path(parsed.incoming)))
    else:
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(args)
        write(Path(parsed.output), PROFILE.replace('explicit-source', parsed.input))
    out({'status': 'passed', 'output': parsed.output})
    return 0


def norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'unknown-skill'


def cmd_registry(args: list[str], inspect: bool = False, validate: bool = False) -> int:
    if inspect:
        parser = argparse.ArgumentParser(prog='wb.py inspect-skill')
        parser.add_argument('skill_file')
        parsed = parser.parse_args(args)
        path = Path(parsed.skill_file)
        text = read(path)
        match = re.search(r'^name:\s*(.+)$', text, re.M)
        name = match.group(1).strip() if match else path.parent.name
        out({'skill_id': norm(name), 'source': str(path), 'capability_summary': ' '.join(text.split())[:240], 'warnings': []})
        return 0
    if validate:
        parser = argparse.ArgumentParser(prog='wb.py validate-registry-entry')
        parser.add_argument('entry')
        parsed = parser.parse_args(args)
        text = read(Path(parsed.entry))
        failures = [token for token in ['source:', 'mode:', 'priority:', 'used_by:', 'stages:', 'allowed_outputs:', 'validation:', 'fallback:'] if token not in text]
        out({'status': 'passed' if not failures else 'issues-found', 'failures': failures})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py register-skill')
    parser.add_argument('--registry', required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--confirmed', action='store_true')
    parsed = parser.parse_args(args)
    if not parsed.confirmed:
        out({'status': 'blocked', 'blocker': 'confirmation-required'})
        return 2
    registry = Path(parsed.registry).expanduser()
    write(registry, (read(registry).rstrip() + '\n' + read(Path(parsed.entry))).lstrip())
    out({'status': 'passed', 'registry': str(registry)})
    return 0


def skill_hints(project_root: Path, directive: str) -> list[str]:
    registry_text = read(Path.home() / '.work-bundle/skills/skill-registry.yaml')
    return [skill for skill in DIRECTIVE_ALLOWED_SKILLS.get(directive, []) if skill in registry_text or skill in ['wb-select-role-context', 'wb-doctor', 'orchestrator']]


def cmd_role_context(args: list[str], validate: bool = False) -> int:
    if validate:
        parser = argparse.ArgumentParser(prog='wb.py validate-role-context')
        parser.add_argument('role_context')
        parser.add_argument('--project-root', default='.')
        parsed = parser.parse_args(args)
        project = Path(parsed.project_root).resolve()
        text = read(Path(parsed.role_context))
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {'role_context': {}}
        context = data.get('role_context', data)
        failures = [key for key in ['source', 'target_directive', 'lifecycle_stage', 'primary_role', 'supporting_roles', 'domain_profile', 'role_profiles', 'blocked'] if key not in context]
        if context.get('primary_role') not in set(ROLE_NAMES):
            failures.append('invalid:primary_role')
        if not (project / context.get('domain_profile', '')).exists():
            failures.append('missing:domain_profile_file')
        out({'status': 'passed' if not failures else 'issues-found', 'failures': failures, 'warnings': []})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py select-role-context')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--directive', '--target-directive', dest='directive', default='create-implementation-plan')
    parser.add_argument('--source-artifact')
    parser.add_argument('--stage')
    parser.add_argument('--perspective')
    parser.add_argument('--allow-repository-inspection', action='store_true')
    parser.add_argument('--output')
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).resolve()
    source = Path(parsed.source_artifact).resolve() if parsed.source_artifact else None
    source_text = read(source) if source else ''
    stage = parsed.stage or first_match(r'(?i)^lifecycle_stage:\s*([^\n]+)', source_text) or first_match(r'(?i)^stage:\s*([^\n]+)', source_text) or first_match(r'^current_lifecycle_stage:\s*([^\n]+)', read(project_root / 'references/bootstrap/project-domain-profile.yaml')) or 'unknown'
    perspective = parsed.perspective or (stage if stage != 'unknown' else 'unknown')
    blocked = parsed.directive == 'execute-plan' and source is None
    blocker = 'execute-plan requires carried source artifact role context' if blocked else None
    matched_perspective = perspective in LEAF_MAP
    matched_stage = stage in STAGE_MAP
    primary, supporting = LEAF_MAP.get(perspective, STAGE_MAP.get(stage, ('solution-architect', ['qa-reviewer'])))
    resolution = 'perspective-match' if matched_perspective else ('stage-match' if matched_stage else 'fallback-draft-role')
    draft_role: dict | None = None
    if resolution == 'fallback-draft-role':
        primary = suggest_draft_role(stage, perspective)
        supporting = []
        draft_role = role_duty_profile(project_root, primary)
    role_paths = [f'references/roles/{role}.yaml' for role in [primary] + supporting]
    missing_roles = [path for path in role_paths if not (project_root / path).exists()]
    if missing_roles:
        blocked = True
        blocker = 'missing role profiles: ' + ', '.join(missing_roles)
    warnings = [] if stage != 'unknown' else ['lifecycle stage unresolved']
    if resolution == 'fallback-draft-role':
        warnings.append('role resolution used one draft role')
    data = {'role_context': {'source': 'wb-select-role-context', 'version': 1, 'target_directive': parsed.directive, 'source_artifact': str(source) if source else None, 'lifecycle_stage': stage, 'perspective': perspective, 'authority_stage': stage, 'primary_role': primary, 'supporting_roles': supporting, 'resolution': resolution, 'draft_role': draft_role, 'domain_profile': 'references/bootstrap/project-domain-profile.yaml', 'role_profiles': role_paths, 'skill_registry': GLOBAL_SKILL_REGISTRY, 'project_skill_override': '.work-bundle/orchestration/skill-registry.override.yaml' if (project_root / '.work-bundle/orchestration/skill-registry.override.yaml').exists() else None, 'suggested_skills': skill_hints(project_root, parsed.directive), 'source_basis': [item for item in ['references/bootstrap/repository-binding.md', 'references/bootstrap/agent-bootstrap.md', str(source) if source else None] if item], 'warnings': warnings, 'blocked': blocked, 'blocker': blocker}}
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if parsed.output:
        write(Path(parsed.output), text + '\n')
    print(text)
    return 0 if not blocked else 1


def cmd_merge_skill_hints(args: list[str]) -> int:
    out({'status': 'passed', 'suggested_skills': []})
    return 0


def cmd_integrity_report(args: list[str]) -> int:
    script = Path(__file__).with_name('integrity_check_report.py')
    if not script.exists():
        out({'status': 'issues-found', 'failures': ['missing_integrity_report_cli'], 'expected': str(script)})
        return 1
    spec = importlib.util.spec_from_file_location('integrity_check_report', script)
    if spec is None or spec.loader is None:
        out({'status': 'issues-found', 'failures': ['load_integrity_report_cli_failed'], 'expected': str(script)})
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(args))


def main() -> int:
    parser = argparse.ArgumentParser(prog='wb.py', description='Canonical work-bundle helper CLI.')
    parser.add_argument('command')
    parser.add_argument('args', nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    command = parsed.command
    aliases = {
        'apply-project-initialization': 'initialize-project',
        'apply-repository-model': 'repository-model',
        'extract-domain-profile': 'generate-domain-profile',
        'merge-registry-entry': 'register-skill',
        'validate-project-initialization': 'validate-project',
        'validate-runtime-artifacts': 'doctor',
        'validate-repository-health': 'repository-health',
        'validate-workflow-branches': 'workflow-branches',
        'integrity-report': 'integrity-check-report',
    }
    command = aliases.get(command, command)
    if command in {'initialize-project', 'repository-model'}:
        return cmd_project(parsed.args, apply=True, repo_model=command == 'repository-model')
    if command in {'inspect-project-initialization', 'inspect-repository-model'}:
        return cmd_project(parsed.args, inspect_only=True, repo_model=command == 'inspect-repository-model')
    if command in {'validate-project', 'validate-repository-model'}:
        return cmd_project(parsed.args, apply=False, repo_model=command == 'validate-repository-model')
    if command == 'create-rules':
        return cmd_create_rules(parsed.args)
    if command == 'validate-rules':
        return cmd_validate_rules(parsed.args)
    if command in {'doctor', 'repository-health', 'validate-directive-wiring', 'validate-skill-registry', 'validate-work-bundle-rules'}:
        return cmd_doctor(parsed.args)
    if command == 'render-doctor-report':
        return cmd_doctor(parsed.args, report=True)
    if command == 'workflow-branches':
        return cmd_doctor(parsed.args, workflow=True)
    if command == 'generate-domain-profile':
        return cmd_domain_profile(parsed.args)
    if command == 'merge-domain-profile':
        return cmd_domain_profile(parsed.args, merge=True)
    if command == 'validate-domain-profile':
        return cmd_domain_profile(parsed.args, validate=True)
    if command == 'inspect-skill':
        return cmd_registry(parsed.args, inspect=True)
    if command == 'validate-registry-entry':
        return cmd_registry(parsed.args, validate=True)
    if command == 'register-skill':
        return cmd_registry(parsed.args)
    if command == 'select-role-context':
        return cmd_role_context(parsed.args)
    if command == 'validate-role-context':
        return cmd_role_context(parsed.args, validate=True)
    if command == 'merge-skill-hints':
        return cmd_merge_skill_hints(parsed.args)
    if command == 'integrity-check-report':
        return cmd_integrity_report(parsed.args)
    parser.error(f'unknown command: {parsed.command}')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
