from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
STAGE_MAP = {
 'tender': ('domain-analyst', ['project-manager']), 'investigation': ('domain-analyst', ['solution-architect', 'project-manager']), 'customer-design': ('domain-analyst', ['ui-designer', 'project-manager', 'solution-architect']), 'bidding': ('project-manager', ['domain-analyst', 'solution-architect']), 'development-design': ('solution-architect', ['backend-developer', 'frontend-developer', 'database-engineer', 'qa-reviewer', 'ui-designer']), 'implementation': ('backend-developer', ['frontend-developer', 'database-engineer', 'qa-reviewer', 'solution-architect']), 'deployment': ('devops-engineer', ['database-engineer', 'qa-reviewer']), 'go-live-delivery': ('project-manager', ['qa-reviewer', 'devops-engineer', 'domain-analyst']), 'operation': ('devops-engineer', ['database-engineer', 'qa-reviewer', 'solution-architect']), 'repository-management': ('devops-engineer', ['solution-architect'])}
LEAF_MAP = {'development-design/data/schema': ('solution-architect', ['database-engineer']), 'development-design/implementation/backend': ('solution-architect', ['backend-developer', 'qa-reviewer']), 'development-design/implementation/frontend': ('solution-architect', ['frontend-developer', 'ui-designer', 'qa-reviewer']), 'customer-design/ui-prototype': ('domain-analyst', ['ui-designer']), 'implementation/tests': ('backend-developer', ['qa-reviewer']), 'repository-management/gitignore-repair': ('devops-engineer', ['solution-architect'])}
DIRECTIVE_ALLOWED_SKILLS = {'create-specification': ['create-specification', 'wb-generate-domain-profile', 'wb-select-role-context'], 'create-implementation-plan': ['orchestrator', 'wb-select-role-context'], 'execute-plan': [], 'create-handoff': ['orchestrator', 'wb-select-role-context'], 'review-plan': ['orchestrator', 'wb-doctor'], 'create-document': ['orchestrator', 'wb-select-role-context'], 'wb-doctor': ['wb-doctor']}
def read(path: Path) -> str: return path.read_text(encoding='utf-8') if path.exists() else ''
def first_match(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE); return m.group(1).strip() if m else None
def profile_stage(project_root: Path) -> str | None: return first_match(r'^current_lifecycle_stage:\s*([^\n]+)', read(project_root/'.work-bundle/orchestration/bootstrap/project-domain-profile.yaml'))
def source_stage(source: Path | None) -> str | None:
    if not source or not source.exists(): return None
    text = read(source); return first_match(r'(?i)^lifecycle_stage:\s*([^\n]+)', text) or first_match(r'(?i)^stage:\s*([^\n]+)', text)
def skill_hints(project_root: Path, directive: str) -> list[str]:
    registry_text = read(Path.home()/'.work-bundle/skills/skill-registry.yaml')
    hints = []
    for skill in DIRECTIVE_ALLOWED_SKILLS.get(directive, []):
        if skill in registry_text or skill in ['wb-select-role-context', 'wb-doctor', 'orchestrator']:
            hints.append(skill)
    return hints
def make_context(args) -> dict:
    project_root = Path(args.project_root).resolve(); source = Path(args.source_artifact).resolve() if args.source_artifact else None
    stage = args.stage or source_stage(source) or profile_stage(project_root) or 'unknown'; perspective = args.perspective or (stage if stage != 'unknown' else 'unknown')
    blocked = False; blocker = None; warnings = []
    if args.directive == 'execute-plan' and not source: blocked = True; blocker = 'execute-plan requires carried source artifact role context'
    if stage == 'unknown': warnings.append('lifecycle stage unresolved')
    primary, supporting = LEAF_MAP.get(perspective, STAGE_MAP.get(stage, ('solution-architect', ['qa-reviewer'])))
    role_paths = [f'references/roles/{r}.yaml' for r in [primary] + supporting]
    missing_roles = [p for p in role_paths if not (project_root / p).exists()]
    if missing_roles: blocked = True; blocker = 'missing role profiles: ' + ', '.join(missing_roles)
    override = project_root/'.work-bundle/orchestration/skill-registry.override.yaml'
    return {'role_context': {'source': 'wb-select-role-context', 'version': 1, 'target_directive': args.directive, 'source_artifact': str(source) if source else None, 'lifecycle_stage': stage, 'perspective': perspective, 'authority_stage': stage, 'primary_role': primary, 'supporting_roles': supporting, 'domain_profile': '.work-bundle/orchestration/bootstrap/project-domain-profile.yaml', 'role_profiles': role_paths, 'skill_registry': '~/.work-bundle/skills/skill-registry.yaml', 'project_skill_override': '.work-bundle/orchestration/skill-registry.override.yaml' if override.exists() else None, 'suggested_skills': skill_hints(project_root, args.directive), 'source_basis': [x for x in ['.work-bundle/orchestration/bootstrap/repository-binding.md', '.work-bundle/orchestration/bootstrap/agent-bootstrap.md', str(source) if source else None] if x], 'warnings': warnings, 'blocked': blocked, 'blocker': blocker}}
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--project-root', default='.'); ap.add_argument('--directive', '--target-directive', dest='directive', default='create-implementation-plan'); ap.add_argument('--source-artifact'); ap.add_argument('--stage'); ap.add_argument('--perspective'); ap.add_argument('--allow-repository-inspection', action='store_true'); ap.add_argument('--output')
    args = ap.parse_args(); data = make_context(args); text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output: Path(args.output).parent.mkdir(parents=True, exist_ok=True); Path(args.output).write_text(text + '\n', encoding='utf-8')
    print(text); return 0 if not data['role_context']['blocked'] else 1
if __name__ == '__main__': raise SystemExit(main())
