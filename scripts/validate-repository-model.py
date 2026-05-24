from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

CUSTOMIZED_SKILL_ROOT = Path('/Users/shenglong/Documents/Repository/work-bundle/skills')
GLOBAL_SKILL_REGISTRY = '~/.work-bundle/skills/skill-registry.yaml'
REQUIRED_PROJECT_GITIGNORE = ['.work-bundle/', 'AGENTS.md']
WORK_BUNDLE_IGNORES = ['*.secret','*.key','*.pem','.env','.env.*','cache/','tmp/','temp','.DS_Store','*.zip','*.tar','*.gz','*.7z','*.log','.cursor/','.idea/','.vscode/']
STAGE_FIRST_DIRS = ['knowledge/notes/tender/background', 'knowledge/notes/tender/requirements', 'knowledge/notes/tender/constraints', 'knowledge/notes/tender/deliverables', 'knowledge/notes/tender/glossary', 'knowledge/notes/investigation/scope-of-work', 'knowledge/notes/investigation/user-portrait', 'knowledge/notes/investigation/business-boundary', 'knowledge/notes/investigation/process-flow', 'knowledge/notes/investigation/performance-requirement', 'knowledge/notes/investigation/integration-landscape', 'knowledge/notes/investigation/risks', 'knowledge/notes/investigation/constraints', 'knowledge/notes/customer-design/business-boundary', 'knowledge/notes/customer-design/process-flow', 'knowledge/notes/customer-design/functional-modules', 'knowledge/notes/customer-design/user-flow', 'knowledge/notes/customer-design/ui-prototype', 'knowledge/notes/customer-design/acceptance-criteria', 'knowledge/notes/customer-design/non-goals', 'knowledge/notes/bidding/committed-scope', 'knowledge/notes/bidding/exclusions', 'knowledge/notes/bidding/deliverables', 'knowledge/notes/bidding/milestones', 'knowledge/notes/bidding/assumptions', 'knowledge/notes/bidding/risks', 'knowledge/notes/development-design/architecture/system-boundary', 'knowledge/notes/development-design/architecture/component-boundary', 'knowledge/notes/development-design/architecture/dependency-direction', 'knowledge/notes/development-design/architecture/source-of-truth', 'knowledge/notes/development-design/architecture/decisions', 'knowledge/notes/development-design/architecture/patterns', 'knowledge/notes/development-design/workflow/process-flow', 'knowledge/notes/development-design/workflow/data-flow', 'knowledge/notes/development-design/workflow/state-lifecycle', 'knowledge/notes/development-design/workflow/control-flow', 'knowledge/notes/development-design/data/data-model', 'knowledge/notes/development-design/data/schema', 'knowledge/notes/development-design/data/identifiers', 'knowledge/notes/development-design/data/relationships', 'knowledge/notes/development-design/data/lineage', 'knowledge/notes/development-design/data/migration', 'knowledge/notes/development-design/interfaces/api-contract', 'knowledge/notes/development-design/interfaces/event-contract', 'knowledge/notes/development-design/interfaces/file-contract', 'knowledge/notes/development-design/interfaces/error-contract', 'knowledge/notes/development-design/interfaces/compatibility', 'knowledge/notes/development-design/implementation/backend', 'knowledge/notes/development-design/implementation/frontend', 'knowledge/notes/development-design/implementation/database', 'knowledge/notes/development-design/implementation/cache', 'knowledge/notes/development-design/implementation/async-messaging', 'knowledge/notes/development-design/quality/requirements', 'knowledge/notes/development-design/quality/validation', 'knowledge/notes/development-design/quality/testing-strategy', 'knowledge/notes/development-design/quality/edge-cases', 'knowledge/notes/development-design/quality/performance', 'knowledge/notes/development-design/quality/observability', 'knowledge/notes/implementation/implemented-features', 'knowledge/notes/implementation/reusable-functions', 'knowledge/notes/implementation/module-structure', 'knowledge/notes/implementation/code-structure', 'knowledge/notes/implementation/coding-rules', 'knowledge/notes/implementation/tests', 'knowledge/notes/implementation/known-limitations', 'knowledge/notes/implementation/implementation-decisions', 'knowledge/notes/deployment/topology', 'knowledge/notes/deployment/configuration', 'knowledge/notes/deployment/packaging', 'knowledge/notes/deployment/migration', 'knowledge/notes/deployment/backup-restore', 'knowledge/notes/deployment/resource-limits', 'knowledge/notes/deployment/rollout-rollback', 'knowledge/notes/deployment/startup-shutdown', 'knowledge/notes/deployment/security-permission', 'knowledge/notes/go-live-delivery/acceptance-result', 'knowledge/notes/go-live-delivery/delivery-scope', 'knowledge/notes/go-live-delivery/handover', 'knowledge/notes/go-live-delivery/training', 'knowledge/notes/go-live-delivery/final-exclusions', 'knowledge/notes/go-live-delivery/support-boundary', 'knowledge/notes/go-live-delivery/production-cutover', 'knowledge/notes/operation/runtime-observation', 'knowledge/notes/operation/troubleshooting', 'knowledge/notes/operation/incidents', 'knowledge/notes/operation/performance', 'knowledge/notes/operation/maintenance', 'knowledge/notes/operation/optimization', 'knowledge/notes/operation/security-audit']
ORCHESTRATION_DIRS = ['orchestration/bootstrap', 'orchestration/principles', 'orchestration/templates', 'orchestration/spec/active', 'orchestration/spec/archived', 'orchestration/plan/active', 'orchestration/plan/archived', 'orchestration/handoff/executor/active', 'orchestration/handoff/orchestration/active', 'orchestration/docs', 'orchestration/reviews', 'orchestration/execution-state']
ROLE_NAMES = ['project-manager', 'solution-architect', 'domain-analyst', 'ui-designer', 'frontend-developer', 'backend-developer', 'database-engineer', 'qa-reviewer', 'devops-engineer']
REQUIRED_RULES = ['repository-boundary', 'knowledge-boundary', 'orchestration-boundary', 'lifecycle-authority', 'retrieval-gateway', 'role-context', 'skill-registry', 'domain-profile', 'execution-boundary', 'handoff-boundary', 'review-archive-boundary', 'doctor-readonly', 'runtime-artifact-format', 'security-exclusion']
AGENTS = '# Agent Entry\n\nThis project uses a local work bundle for agent knowledge and orchestration.\n\nRead:\n\n```text\n.work-bundle/orchestration/bootstrap/agent-bootstrap.md\n.work-bundle/orchestration/bootstrap/repository-binding.md\n```\n\nDo not commit this file to the project repository by default.\n'
BOOTSTRAP = '# Agent Bootstrap\n\n## Project Identity\nproject: keep-summarizing\n\n## Repository Layout\nwork_bundle: .work-bundle\nsource_code_root: .\n\n## Git Boundary\nProject Git and work-bundle Git are separate. Do not mix commit scopes by default.\n\n## Project Gitignore\n.gitignore must ignore .work-bundle/ and AGENTS.md.\n\n## Work Bundle Git Repository\n.work-bundle/.git\n\n## Knowledge Source of Truth\n.work-bundle/knowledge/\n\n## Orchestration Artifact Root\n.work-bundle/orchestration/\n\n## Work Bundle Rules Root\nreferences/rules/\n\n## Project Agents Entry\nAGENTS.md\n\n## Required Loading Order\n1. repository-binding.md\n2. verify project Git boundary\n3. verify work-bundle Git boundary\n4. agent-bootstrap.md\n5. load work-bundle rules contract and rule index\n6. resolve enabled work-bundle rules for current task\n7. project.yaml\n8. project-domain-profile.yaml\n9. identify current lifecycle stage\n10. load relevant stage-first notes only through allowed gateway/directive rules\n11. classify retrieved notes by status and retrieval role\n12. load relevant open-question records when allowed\n13. select primary role profile by lifecycle stage\n14. select supporting role profiles by leaf perspective\n15. locate customized skill root\n16. load global skill registry\n17. load optional project skill registry override if present\n18. load task-specific spec or plan\n\n## Available Role Profiles\nreferences/roles/\n\n## Available Skill Registry\n~/.work-bundle/skills/skill-registry.yaml\n\n## Customized Skill Root\n/Users/shenglong/Documents/Repository/work-bundle/skills\n\n## Project Skill Override\noptional: .work-bundle/orchestration/skill-registry.override.yaml\n\n## Enabled Work Bundle Rules\nResolve from references/rules/index.yaml before directive-specific behavior.\n\n## Output Rules\nKeep runtime artifacts compact and machine-readable. Prefer compact YAML for runtime rules, role profiles, domain profile, and role context.\n\n## Handoff Rules\nUse .work-bundle/orchestration/handoff/. Executor handoffs carry role_context_used when available.\n\n## Forbidden Behavior\nDo not write durable knowledge from orchestration directives. Do not generate .mdc rules. Do not treat deprecated .mdc files as current authority.\n'
PROFILE = 'id: project-domain-profile\nstatus: current\nversion: 1\ngenerated_by: wb-initialize-project\nupdated_at: 2026-05-24\nindustry: agent-workflow-tooling\nbusiness_context: Local-first agent knowledge and orchestration workflow tooling.\ncore_domain_objects: [work-bundle, durable-knowledge, orchestration-artifact, skill, runtime-rule, role-context]\ncore_lifecycles: [spec -> plan -> phase -> task -> execute -> handoff -> review]\ndomain_constraints: [keep durable knowledge separate from orchestration artifacts, compact runtime files first]\ncommon_misunderstandings: [do not treat open questions as facts, do not let execute-plan retrieve knowledge]\ncurrent_lifecycle_stage: development-design\nstage_specific_authority:\n  tender: weak input unless confirmed later\n  investigation: discovery findings; useful for scope and clarification\n  customer-design: customer-visible intent, not engineering authority by default\n  bidding: commercial commitment; not implementation design by default\n  development-design: primary authority for specs and plans\n  implementation: verified behavior from code, handoff, review, or tests\n  deployment: runtime and rollout authority\n  go-live-delivery: delivery and acceptance authority\n  operation: production/runtime authority\nrole_positioning:\n  default: selected role profiles must apply this domain profile before producing domain-sensitive output\nsource_knowledge:\n  - path: .work-bundle/orchestration/spec/active/spec-process-v4-project-local-agent-operating-system.md\n    role: authority\n    reason: v4 implementation specification\nwarnings: []\n'
RULE_CONTRACT = 'id: work-bundle-rule-contract\nstatus: current\nrule_format: yaml\nscope: work-bundle\nrequired_fields: [id, status, scope, applies_to, enable_when, severity, rule, required_behavior, prohibited_behavior, validation, source_authority]\ndeprecated_formats: [mdc]\ndeprecated_sources_policy: deprecated_mdc_reference_only\n'
RULE_INDEX = 'rules_root: references/rules\ngenerated_by: wb-initialize-project\nstatus: initialized\nrequired_rules_source: cursor_knowledge_orchestrator_files/docs/v4/create-rules-instruction.md\nrule_files: []\nnotes: [full work-bundle rules are created by wb-create-rules, not wb-initialize-project]\n'

def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''

def write_text(path: Path, text: str, overwrite: bool = True) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    old = read_text(path)
    if old == text:
        return False
    path.write_text(text, encoding='utf-8')
    return True

def ensure_lines(path: Path, lines: list[str]) -> bool:
    current = read_text(path).splitlines()
    changed = False
    for line in lines:
        if line not in current:
            current.append(line); changed = True
    if changed or not path.exists():
        write_text(path, '\n'.join(current).rstrip() + '\n')
    return changed

def has_ignore(lines: list[str], wanted: str) -> bool:
    variants = {wanted, wanted.rstrip('/'), '/' + wanted.rstrip('/')}
    return any(line.strip() in variants for line in lines)

def inspect(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    pgi = read_text(project_root / '.gitignore').splitlines()
    wbi = read_text(wb / '.gitignore').splitlines()
    rb = read_text(wb / 'orchestration/bootstrap/repository-binding.md')
    ab = read_text(wb / 'orchestration/bootstrap/agent-bootstrap.md')
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
        'stage_first_tree': all((wb / d).exists() for d in STAGE_FIRST_DIRS),
        'orchestration_root': (wb / 'orchestration').exists(),
        'orchestration_tree': all((wb / d).exists() for d in ORCHESTRATION_DIRS),
        'bootstrap_root': (wb / 'orchestration' / 'bootstrap').exists(),
        'repository_binding': (wb / 'orchestration' / 'bootstrap' / 'repository-binding.md').exists(),
        'repository_binding_records_state': all(k in rb for k in ['project_git:', 'ignores_work_bundle:', 'ignores_agent_entry:', 'work_bundle:', 'git_repo:', 'agent_entry:']),
        'agent_bootstrap': (wb / 'orchestration' / 'bootstrap' / 'agent-bootstrap.md').exists(),
        'agent_bootstrap_loading_order': all(s in ab for s in ['verify project Git boundary', 'verify work-bundle Git boundary', 'load global skill registry', 'load optional project skill registry override']),
        'domain_profile': (wb / 'orchestration' / 'bootstrap' / 'project-domain-profile.yaml').exists(),
        'roles_root': (project_root / 'references' / 'roles').exists(),
        'role_profiles': all((project_root / 'references' / 'roles' / f'{r}.yaml').exists() for r in ROLE_NAMES),
        'rules_root': (project_root / 'references' / 'rules').exists(),
        'rule_contract': (project_root / 'references' / 'rules' / 'contract.yaml').exists(),
        'rule_contract_requires_enable_when': 'enable_when' in read_text(project_root / 'references' / 'rules' / 'contract.yaml'),
        'rule_index': (project_root / 'references' / 'rules' / 'index.yaml').exists(),
        'mdc_rules': [str(p) for p in (project_root / 'references' / 'rules').glob('**/*.mdc')],
        'global_registry_copied': (wb / 'skills' / 'skill-registry.yaml').exists(),
        'project_skill_override': (wb / 'orchestration/skill-registry.override.yaml').exists(),
    }

def validate(project_root: Path, include_bootstrap: bool = True) -> tuple[bool, dict]:
    data = inspect(project_root)
    required = ['project_gitignore','project_ignores_work_bundle','project_ignores_agents','agents_md','work_bundle','work_bundle_gitignore','work_bundle_gitignore_required_entries','knowledge_root','stage_first_tree','orchestration_root','orchestration_tree','bootstrap_root','repository_binding','repository_binding_records_state','rules_root','rule_contract','rule_contract_requires_enable_when','rule_index','roles_root','role_profiles']
    if include_bootstrap:
        required += ['agent_bootstrap','agent_bootstrap_loading_order','domain_profile']
    failures = [k for k in required if not data.get(k)]
    if data.get('mdc_rules'):
        failures.append('mdc_rules_absent')
    if data.get('global_registry_copied'):
        failures.append('global_registry_not_copied')
    data['status'] = 'passed' if not failures else 'issues-found'
    data['failures'] = failures
    return not failures, data

def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

def binding(project_root: Path) -> str:
    pgi = read_text(project_root / '.gitignore').splitlines()
    wb = project_root / '.work-bundle'
    override = wb / 'orchestration' / 'skill-registry.override.yaml'
    return f"""# Repository Binding

```yaml
project_root: {project_root}
project_git:
  exists: {str((project_root/'.git').exists()).lower()}
  gitignore: {project_root/'.gitignore'}
  ignores_work_bundle: {str(has_ignore(pgi, '.work-bundle/')).lower()}
  ignores_agent_entry: {str(has_ignore(pgi, 'AGENTS.md')).lower()}
source_code_root: {project_root}
knowledge_root: {wb/'knowledge'}
orchestration_root: {wb/'orchestration'}
rules_root: {project_root/'references/rules'}
rule_contract: {project_root/'references/rules/contract.yaml'}
rule_index: {project_root/'references/rules/index.yaml'}
work_bundle:
  root: {wb}
  git_repo: {str((wb/'.git').exists()).lower()}
  gitignore: {wb/'.gitignore'}
agent_entry:
  path: {project_root/'AGENTS.md'}
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

def apply_model(project_root: Path, init_git: bool = True, create_override: bool = False) -> list[str]:
    wb = project_root / '.work-bundle'
    changed: list[str] = []
    if ensure_lines(project_root / '.gitignore', REQUIRED_PROJECT_GITIGNORE): changed.append(str(project_root/'.gitignore'))
    if write_text(project_root / 'AGENTS.md', AGENTS, overwrite=False): changed.append(str(project_root/'AGENTS.md'))
    for d in STAGE_FIRST_DIRS + ORCHESTRATION_DIRS + ['knowledge/open-questions','knowledge/context-packs','knowledge/indexes']:
        p = wb / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True); changed.append(str(p))
    for ref_dir in ['references/roles', 'references/rules']:
        p = project_root / ref_dir
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True); changed.append(str(p))
    if write_text(wb / 'knowledge/project.yaml', 'id: project\nstatus: current\n', overwrite=False): changed.append(str(wb/'knowledge/project.yaml'))
    if ensure_lines(wb / '.gitignore', WORK_BUNDLE_IGNORES): changed.append(str(wb/'.gitignore'))
    if init_git and not (wb / '.git').exists():
        subprocess.run(['git','init',str(wb)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        changed.append(str(wb/'.git'))
    if write_text(wb/'orchestration/bootstrap/repository-binding.md', binding(project_root)): changed.append(str(wb/'orchestration/bootstrap/repository-binding.md'))
    if write_text(wb/'orchestration/bootstrap/agent-bootstrap.md', BOOTSTRAP): changed.append(str(wb/'orchestration/bootstrap/agent-bootstrap.md'))
    if write_text(wb/'orchestration/bootstrap/project-domain-profile.yaml', PROFILE, overwrite=False): changed.append(str(wb/'orchestration/bootstrap/project-domain-profile.yaml'))
    if write_text(project_root/'references/rules/contract.yaml', RULE_CONTRACT, overwrite=False): changed.append(str(project_root/'references/rules/contract.yaml'))
    if write_text(project_root/'references/rules/index.yaml', RULE_INDEX, overwrite=False): changed.append(str(project_root/'references/rules/index.yaml'))
    for role in ROLE_NAMES:
        role_path = project_root/'references/roles'/f'{role}.yaml'
        if write_text(role_path, f'id: {role}\nstatus: draft\n', overwrite=False): changed.append(str(role_path))
    if create_override:
        if write_text(wb/'orchestration/skill-registry.override.yaml', 'id: project-skill-registry-override\nstatus: current\noverrides: {}\n', overwrite=False): changed.append(str(wb/'orchestration/skill-registry.override.yaml'))
    return sorted(set(changed))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project_root')
    args = ap.parse_args()
    ok, data = validate(Path(args.project_root).resolve())
    print_json(data)
    return 0 if ok else 1
if __name__ == '__main__':
    raise SystemExit(main())
