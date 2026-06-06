from core import *

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
    role_paths = [f'roles/{role}.yaml' for role in [primary] + supporting]
    missing_roles = [path for path in role_paths if not (project_root / path).exists()]
    if missing_roles:
        blocked = True
        blocker = 'missing role profiles: ' + ', '.join(missing_roles)
    warnings = [] if stage != 'unknown' else ['lifecycle stage unresolved']
    if resolution == 'fallback-draft-role':
        warnings.append('role resolution used one draft role')
    data = {'role_context': {'source': 'wb-select-role-context', 'version': 1, 'target_directive': parsed.directive, 'source_artifact': str(source) if source else None, 'lifecycle_stage': stage, 'perspective': perspective, 'authority_stage': stage, 'primary_role': primary, 'supporting_roles': supporting, 'resolution': resolution, 'draft_role': draft_role, 'domain_profile': 'references/bootstrap/project-domain-profile.yaml', 'role_profiles': role_paths, 'skill_registry': GLOBAL_SKILL_REGISTRY, 'project_skill_override': '.work-bundle/orchestration/skill-registry.override.yaml' if (project_root / '.work-bundle/orchestration/skill-registry.override.yaml').exists() else None, 'suggested_skills': skill_hints(project_root, parsed.directive), 'source_basis': [item for item in ['.work-bundle/project.yaml', 'references/bootstrap/agent-bootstrap.md', str(source) if source else None] if item], 'warnings': warnings, 'blocked': blocked, 'blocker': blocker}}
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if parsed.output:
        write(Path(parsed.output), text + '\n')
    print(text)
    return 0 if not blocked else 1

