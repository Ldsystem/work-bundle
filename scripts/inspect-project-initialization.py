from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

REQUIRED_PROJECT_GITIGNORE = ['.work-bundle/', 'AGENTS.md']
WORK_BUNDLE_IGNORES = ['*.secret','*.key','*.pem','.env','.env.*','cache/','tmp/','temp','.DS_Store','*.zip','*.tar','*.gz','*.7z','*.log','.cursor/','.idea/','.vscode/']

def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')

def ensure_lines(path: Path, lines: list[str]) -> bool:
    current = read_text(path).splitlines()
    changed = False
    for line in lines:
        if line not in current:
            current.append(line); changed = True
    if changed or not path.exists():
        write_text(path, '\n'.join(current).rstrip() + '\n')
    return changed

def inspect(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    pgi = read_text(project_root / '.gitignore').splitlines()
    return {
        'project_root': str(project_root),
        'project_git': (project_root / '.git').exists(),
        'project_gitignore': (project_root / '.gitignore').exists(),
        'project_ignores_work_bundle': any(x in pgi for x in ['.work-bundle/','.work-bundle','/.work-bundle']),
        'project_ignores_agents': any(x in pgi for x in ['AGENTS.md','/AGENTS.md']),
        'agents_md': (project_root / 'AGENTS.md').exists(),
        'work_bundle': wb.exists(),
        'work_bundle_git': (wb / '.git').exists(),
        'work_bundle_gitignore': (wb / '.gitignore').exists(),
        'knowledge_root': (wb / 'knowledge').exists(),
        'orchestration_root': (wb / 'orchestration').exists(),
        'bootstrap_root': (wb / 'orchestration' / 'bootstrap').exists(),
        'repository_binding': (wb / 'orchestration' / 'bootstrap' / 'repository-binding.md').exists(),
        'agent_bootstrap': (wb / 'orchestration' / 'bootstrap' / 'agent-bootstrap.md').exists(),
        'domain_profile': (wb / 'orchestration' / 'bootstrap' / 'project-domain-profile.yaml').exists(),
        'rules_root': (project_root / 'references' / 'rules').exists(),
        'rule_contract': (project_root / 'references' / 'rules' / 'contract.yaml').exists(),
        'rule_index': (project_root / 'references' / 'rules' / 'index.yaml').exists(),
    }

def validate(project_root: Path, include_bootstrap: bool = False) -> tuple[bool, dict]:
    data = inspect(project_root)
    required = ['project_gitignore','project_ignores_work_bundle','project_ignores_agents','agents_md','work_bundle','work_bundle_gitignore','knowledge_root','orchestration_root','bootstrap_root','repository_binding','rules_root','rule_contract','rule_index']
    if include_bootstrap:
        required += ['agent_bootstrap','domain_profile']
    failures = [k for k in required if not data.get(k)]
    data['status'] = 'passed' if not failures else 'issues-found'
    data['failures'] = failures
    return not failures, data

def print_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

BOOTSTRAP = '''# Agent Bootstrap

## Project Identity
project: keep-summarizing

## Repository Layout
work_bundle: .work-bundle

## Git Boundary
Project Git and work-bundle Git are separate.

## Project Gitignore
`.gitignore` must ignore `.work-bundle/` and `AGENTS.md`.

## Work Bundle Git Repository
`.work-bundle/.git`

## Knowledge Source of Truth
`.work-bundle/knowledge/`

## Orchestration Artifact Root
`.work-bundle/orchestration/`

## Work Bundle Rules Root
`references/rules/`

## Project Agents Entry
`AGENTS.md`

## Required Loading Order
1. repository-binding.md
2. verify Git boundaries
3. agent-bootstrap.md
4. rules contract and index
5. project.yaml
6. project-domain-profile.yaml
7. role context
8. skill registry
9. task artifact

## Available Role Profiles
`references/roles/`

## Available Skill Registry
`~/.work-bundle/skills/skill-registry.yaml`

## Customized Skill Root
`/Users/shenglong/Documents/Repository/work-bundle/skills`

## Project Skill Override
`.work-bundle/orchestration/skill-registry.override.yaml`

## Enabled Work Bundle Rules
Resolve from `references/rules/index.yaml`.

## Output Rules
Keep runtime artifacts compact and machine-readable.

## Handoff Rules
Use `.work-bundle/orchestration/handoff/`.

## Forbidden Behavior
Do not write durable knowledge from orchestration directives. Do not generate `.mdc` rules.
'''
PROFILE = '''id: project-domain-profile
status: current
version: 1
generated_by: wb-initialize-project
updated_at: 2026-05-24
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
  - path: .work-bundle/orchestration/spec/active/spec-process-v4-project-local-agent-operating-system.md
    role: authority
    reason: v4 implementation specification
warnings: []
'''
def do_apply(pr: Path):
    subprocess.run([sys.executable, '/Users/shenglong/Documents/Repository/work-bundle/scripts/apply-repository-model.py', str(pr)], check=False)
    write_text(pr/'.work-bundle/orchestration/bootstrap/agent-bootstrap.md', BOOTSTRAP)
    prof=pr/'.work-bundle/orchestration/bootstrap/project-domain-profile.yaml'
    if not prof.exists(): write_text(prof, PROFILE)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project_root'); ap.add_argument('--apply', action='store_true')
    args=ap.parse_args(); pr=Path(args.project_root).resolve()
    if args.apply: do_apply(pr)
    ok,data=validate(pr, include_bootstrap=True); print_json(data); return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
