from core import *

def cmd_merge_skill_hints(args: list[str]) -> int:
    out({'status': 'passed', 'suggested_skills': []})
    return 0


def cmd_integrity_report(args: list[str]) -> int:
    script = Path(__file__).resolve().parents[1] / 'integrity_check_report.py'
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

