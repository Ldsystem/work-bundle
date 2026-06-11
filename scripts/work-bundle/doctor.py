from core import *
from project import inspect_project, project_failures

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

