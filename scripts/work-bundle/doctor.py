from core import *
from project import inspect_project, project_failures

def cmd_doctor(args: list[str], report: bool = False) -> int:
    parser = argparse.ArgumentParser(prog='wb.py doctor')
    parser.add_argument('project_root')
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).resolve()
    data = inspect_project(project_root)
    failures = project_failures(data, strict=False)
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
