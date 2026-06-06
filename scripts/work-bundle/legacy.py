from core import *

def cmd_legacy_command_removed(command: str, replacement: str) -> int:
    out({
        'status': 'issues-found',
        'diagnostic': DIAG_LEGACY_COMMAND_REMOVED,
        'legacy_command': command,
        'replacement_command': replacement,
        'migration_owner': '/wb-initialize-project',
        'guidance': [
            f'Use `python3 scripts/wb.py {replacement}` instead.',
            'Use `/wb-initialize-project doctor` for legacy structure diagnostics.',
            'Use `/wb-initialize-project migrate` to converge stale metadata and command usage.',
        ],
    })
    return 2
