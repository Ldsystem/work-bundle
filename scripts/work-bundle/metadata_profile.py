from core import *

def cmd_domain_profile(args: list[str], merge: bool = False, validate: bool = False) -> int:
    if validate:
        parser = argparse.ArgumentParser(prog='wb.py validate-domain-profile')
        parser.add_argument('profile')
        parsed = parser.parse_args(args)
        text = read(Path(parsed.profile))
        failures = [token for token in ['id:', 'status:', 'industry:', 'business_context:', 'source_knowledge:', 'role_positioning:', 'warnings:'] if token not in text]
        if len(text.splitlines()) > 120:
            failures.append('prose_heavy')
        out({'path': parsed.profile, 'status': 'passed' if not failures else 'issues-found', 'failures': failures, 'line_count': len(text.splitlines())})
        return 0 if not failures else 1
    parser = argparse.ArgumentParser(prog='wb.py merge-domain-profile' if merge else 'wb.py generate-domain-profile')
    if merge:
        parser.add_argument('--current')
        parser.add_argument('--incoming', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(args)
        write(Path(parsed.output), read(Path(parsed.incoming)))
    else:
        parser.add_argument('--input', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(args)
        write(Path(parsed.output), PROFILE.replace('explicit-source', parsed.input))
    out({'status': 'passed', 'output': parsed.output})
    return 0

