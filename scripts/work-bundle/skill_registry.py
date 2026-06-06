from core import *

def norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'unknown-skill'


def cmd_registry(args: list[str], inspect: bool = False, validate: bool = False) -> int:
    if inspect:
        parser = argparse.ArgumentParser(prog='wb.py inspect-skill')
        parser.add_argument('skill_file')
        parsed = parser.parse_args(args)
        path = Path(parsed.skill_file)
        text = read(path)
        match = re.search(r'^name:\s*(.+)$', text, re.M)
        name = match.group(1).strip() if match else path.parent.name
        out({'skill_id': norm(name), 'source': str(path), 'capability_summary': ' '.join(text.split())[:240], 'warnings': []})
        return 0
    if validate:
        parser = argparse.ArgumentParser(prog='wb.py validate-registry-entry')
        parser.add_argument('entry')
        parsed = parser.parse_args(args)
        text = read(Path(parsed.entry))
        failures = [token for token in ['source:', 'mode:', 'priority:', 'used_by:', 'stages:', 'allowed_outputs:', 'validation:', 'fallback:'] if token not in text]
        out({'status': 'passed' if not failures else 'issues-found', 'failures': failures})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py register-skill')
    parser.add_argument('--registry', required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--confirmed', action='store_true')
    parsed = parser.parse_args(args)
    if not parsed.confirmed:
        out({'status': 'blocked', 'blocker': 'confirmation-required'})
        return 2
    registry = Path(parsed.registry).expanduser()
    write(registry, (read(registry).rstrip() + '\n' + read(Path(parsed.entry))).lstrip())
    out({'status': 'passed', 'registry': str(registry)})
    return 0

