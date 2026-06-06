from core import *

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
    data['canonical_metadata_authority'] = '.work-bundle/project.yaml'
    data['migration_guidance'] = {
        'owner': '/wb-initialize-project',
        'doctor': '/wb-initialize-project doctor',
        'migrate': '/wb-initialize-project migrate',
    }
    data['status'] = 'passed' if not failures else 'issues-found'
    data['failures'] = failures
    if parsed.dry_run:
        data['dry_run'] = True
    if apply and not parsed.dry_run:
        data['changed_files'] = changed
    out(data)
    return 0 if not failures else 1


