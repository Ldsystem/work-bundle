from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROLE_NAMES = ['project-manager','solution-architect','domain-analyst','ui-designer','frontend-developer','backend-developer','database-engineer','qa-reviewer','devops-engineer']
STACK_TERMS = ['Spring','React','Vue','Angular','Svelte','MySQL','PostgreSQL','AWS','Azure','GCP']

def out(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

def read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''

def role_duty_failures(roles_root: Path) -> list[str]:
    failures: list[str] = []
    for role in ROLE_NAMES:
        path = roles_root / f'{role}.yaml'
        text = read(path)
        if not path.exists():
            failures.append(f'role_missing:{role}')
            continue
        checks = {
            'duty_profile': 'duty_profile:',
            'stance': '  stance:',
            'skilled_at': '  skilled_at:',
            'quality_focus': '  quality_focus:',
            'must_resolve_from_context': '  must_resolve_from_context:',
        }
        for key, token in checks.items():
            if token not in text:
                failures.append(f'role_duty_missing:{role}:{key}')
        if role in {'frontend-developer','backend-developer','database-engineer','devops-engineer'}:
            for term in STACK_TERMS:
                if term in text:
                    failures.append(f'role_duty_assumes_stack:{role}:{term}')
        if 'project-domain-profile' not in text:
            failures.append(f'role_missing_domain_profile_reference:{role}')
    return failures

def inspect(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    rules = project_root / 'references/rules'
    roles = project_root / 'references/roles'
    duty_failures = role_duty_failures(roles)
    return {
      'project_root': str(project_root),
      'project_gitignore': (project_root/'.gitignore').exists(),
      'agents_md': (project_root/'AGENTS.md').exists(),
      'work_bundle': wb.exists(),
      'work_bundle_gitignore': (wb/'.gitignore').exists(),
      'repository_binding': (wb/'orchestration/bootstrap/repository-binding.md').exists(),
      'agent_bootstrap': (wb/'orchestration/bootstrap/agent-bootstrap.md').exists(),
      'project_domain_profile': (wb/'orchestration/bootstrap/project-domain-profile.yaml').exists(),
      'roles_root': roles.exists(),
      'role_files': len(list(roles.glob('*.yaml'))) if roles.exists() else 0,
      'role_duty_failures': duty_failures,
      'rules_root': rules.exists(),
      'rule_files': len(list(rules.glob('*.yaml'))) if rules.exists() else 0,
      'mdc_rules': [str(p) for p in rules.glob('*.mdc')] if rules.exists() else [],
    }

def status(data: dict) -> list[str]:
    req = ['project_gitignore','agents_md','work_bundle','work_bundle_gitignore','repository_binding','agent_bootstrap','project_domain_profile','roles_root','rules_root']
    failures = [k for k in req if not data.get(k)]
    failures.extend(data.get('role_duty_failures') or [])
    if data.get('mdc_rules'):
        failures.append('mdc_rules_present')
    return failures

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project_root')
    args = ap.parse_args()
    pr = Path(args.project_root).resolve()
    data = inspect(pr)
    failures = status(data)
    print('# Doctor Report\n')
    print('## Status\n')
    print('passed' if not failures else 'issues-found')
    print('\n## Target\n')
    print(pr)
    print('\n## Summary\n')
    print('Read-only v4 audit completed.')
    print('\n## Errors\n')
    print('none' if not failures else '\n'.join(f'- {f}' for f in failures))
    print('\n## Warnings\nnone')
    print('\n## Recommended Fixes\n')
    print('Run responsible repair skills for listed errors.' if failures else 'none')
    print('\n## Suggested Repair Skills\nmanage-repository-model, wb-initialize-project, wb-create-rules')
    print('\n## Files Checked\n')
    print('\n'.join(f'- {k}: {v}' for k, v in data.items()))
    print('\n## Files Changed\nnone')
    return 0 if not failures else 1
if __name__ == '__main__':
    raise SystemExit(main())
