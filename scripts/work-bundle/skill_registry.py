from core import *


def cmd_merge_skill_hints(args: list[str]) -> int:
    out({'status': 'passed', 'suggested_skills': []})
    return 0

def norm(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'unknown-skill'


def registry_entry_failures(text: str) -> list[str]:
    failures = [token for token in ['source:', 'mode:', 'priority:', 'used_by:', 'stages:', 'allowed_outputs:', 'validation:', 'fallback:'] if token not in text]
    type_match = re.search(r'^\s*type:\s*([^#\n]+)', text, re.M)
    if not type_match or type_match.group(1).strip() != 'external':
        failures.append('external-type-required')

    source_match = re.search(r'^\s*source:\s*([^#\n]+)', text, re.M)
    toolkit_root = resolve_work_bundle_root()
    if source_match:
        source = Path(source_match.group(1).strip().strip('"\'')).expanduser().resolve(strict=False)
        built_in_roots = {CUSTOMIZED_SKILL_ROOT.resolve()}
        if toolkit_root:
            built_in_roots.add((toolkit_root / 'skills').resolve())
        if any(source.is_relative_to(root) for root in built_in_roots):
            failures.append('built-in-work-bundle-skill-forbidden')
    return failures


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
        failures = registry_entry_failures(text)
        out({'status': 'passed' if not failures else 'issues-found', 'failures': failures})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py register-skill')
    parser.add_argument('--registry', required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--confirmed', action='store_true')
    parsed = parser.parse_args(args)
    entry_text = read(Path(parsed.entry))
    failures = registry_entry_failures(entry_text)
    if failures:
        out({'status': 'blocked', 'blocker': 'external-registry-entry-invalid', 'failures': failures})
        return 2
    if not parsed.confirmed:
        out({'status': 'blocked', 'blocker': 'confirmation-required'})
        return 2
    registry = Path(parsed.registry).expanduser()
    write(registry, (read(registry).rstrip() + '\n' + entry_text).lstrip())
    out({'status': 'passed', 'registry': str(registry)})
    return 0
