from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
ROLES = {'project-manager','solution-architect','domain-analyst','ui-designer','frontend-developer','backend-developer','database-engineer','qa-reviewer','devops-engineer'}
STAGES = {'tender','investigation','customer-design','bidding','development-design','implementation','deployment','go-live-delivery','operation','repository-management','unknown'}
def load(path: Path) -> dict:
    text = path.read_text(encoding='utf-8')
    try: return json.loads(text)
    except json.JSONDecodeError:
        ctx = {}
        for key in ['lifecycle_stage','primary_role','domain_profile','blocked','blocker']:
            m = re.search(rf'^\s*{key}:\s*(.+)$', text, re.MULTILINE)
            if m: ctx[key] = m.group(1).strip()
        roles = re.search(r'^\s*supporting_roles:\s*\[(.*)\]', text, re.MULTILINE)
        ctx['supporting_roles'] = [x.strip() for x in roles.group(1).split(',')] if roles else []
        return {'role_context': ctx}
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('role_context'); ap.add_argument('--project-root', default='.')
    args = ap.parse_args(); project = Path(args.project_root).resolve(); data = load(Path(args.role_context)); ctx = data.get('role_context', data); failures = []
    for k in ['source','target_directive','lifecycle_stage','primary_role','supporting_roles','domain_profile','role_profiles','blocked']:
        if k not in ctx: failures.append(f'missing:{k}')
    if ctx.get('lifecycle_stage') not in STAGES: failures.append('invalid:lifecycle_stage')
    if ctx.get('primary_role') not in ROLES: failures.append('invalid:primary_role')
    for r in ctx.get('supporting_roles', []):
        if r not in ROLES: failures.append(f'invalid:supporting_role:{r}')
    if not (project / ctx.get('domain_profile', '')).exists(): failures.append('missing:domain_profile_file')
    warnings = [] if (Path.home()/'.work-bundle/skills/skill-registry.yaml').exists() else ['global skill registry missing']
    result = {'status': 'passed' if not failures else 'issues-found', 'failures': failures, 'warnings': warnings}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)); return 0 if not failures else 1
if __name__ == '__main__': raise SystemExit(main())
