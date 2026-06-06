from core import *

def rule_text(name: str) -> str:
    return f'''id: rule-work-bundle-{name}
status: current
scope: work-bundle
applies_to: {{paths: [.work-bundle/**], skills: [], artifacts: []}}
enable_when: [v4 work-bundle operation requires {name}]
severity: must
rule: {name} rule applies to v4 work-bundle operations.
required_behavior: [follow source authority, keep runtime files compact]
prohibited_behavior: [do not generate .mdc files, do not include raw logs or secrets]
validation: [required fields exist, scope is work-bundle]
source_authority: [.work-bundle/orchestration/spec/active/spec-process-v4-project-local-agent-operating-system.md]
deprecated_sources: []
'''


def cmd_create_rules(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py create-rules')
    parser.add_argument('rules_root')
    parsed = parser.parse_args(args)
    root = Path(parsed.rules_root)
    root.mkdir(parents=True, exist_ok=True)
    for rule in RULES:
        write(root / f'{rule}.yaml', rule_text(rule))
    write(root / 'index.yaml', 'id: work-bundle-rule-index\nstatus: current\nrules:\n' + ''.join(f'  - {rule}.yaml\n' for rule in RULES))
    out({'status': 'passed', 'rules': RULES})
    return 0


def cmd_validate_rules(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py validate-rules')
    parser.add_argument('rules_root')
    parsed = parser.parse_args(args)
    root = Path(parsed.rules_root)
    failures: list[str] = []
    if list(root.glob('*.mdc')):
        failures.append('generated_mdc_present')
    for path in root.glob('*.yaml'):
        if path.name in {'index.yaml', 'contract.yaml'}:
            continue
        text = read(path)
        for token in ['id:', 'status:', 'scope: work-bundle', 'enable_when:', 'severity:', 'required_behavior:', 'prohibited_behavior:', 'validation:', 'source_authority:']:
            if token not in text:
                failures.append(f'{path.name}:{token}')
        if len(text.splitlines()) > 80:
            failures.append(f'{path.name}:prose_heavy')
    out({'status': 'passed' if not failures else 'issues-found', 'failures': failures})
    return 0 if not failures else 1
