from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


SCRIPT_INDEX_TEMPLATE = '''version: 1
entry_contract:
  required:
    - id
    - path
    - description
    - functionality
    - use_cases
    - runtime
    - invocation
    - dependencies
    - applicable_repositories
    - operation
    - credentials
    - inputs
    - outputs
    - safety_notes
  path:
    relative_to: workspace_root
    required_prefix: script/
    path_escape: forbidden
  operation:
    allowed: [read-only, read-write]
  duplicate_ids: forbidden
  stale_paths: forbidden
  undeclared_credential_use: forbidden
  discovery_authorizes_execution: false
scripts: []
'''
CREDENTIAL_TEMPLATE = 'version: 1\ncredentials: []\n'


def ensure_workspace_resources(workspace_root: Path, *, create_script_index: bool = True) -> list[str]:
    changed: list[str] = []
    script_index = workspace_root / 'script' / 'index.yaml'
    credential_file = workspace_root / 'credentials' / 'credentials.yaml'
    if create_script_index and not script_index.exists():
        script_index.parent.mkdir(parents=True, exist_ok=True)
        script_index.write_text(SCRIPT_INDEX_TEMPLATE, encoding='utf-8')
        changed.append(str(script_index))
    credential_file.parent.mkdir(parents=True, exist_ok=True)
    credential_file.parent.chmod(0o700)
    if not credential_file.exists():
        credential_file.write_text(CREDENTIAL_TEMPLATE, encoding='utf-8')
        changed.append(str(credential_file))
    credential_file.chmod(0o600)
    return changed


REQUIRED_SCRIPT_FIELDS = frozenset({
    'id', 'path', 'description', 'functionality', 'use_cases', 'runtime',
    'invocation', 'dependencies', 'applicable_repositories', 'operation',
    'credentials', 'inputs', 'outputs', 'safety_notes',
})
LIST_FIELDS = frozenset({'use_cases', 'dependencies', 'applicable_repositories', 'credentials', 'inputs', 'outputs', 'safety_notes'})
SCRIPT_ENTRY_FIELDS = REQUIRED_SCRIPT_FIELDS
SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
EXPECTED_ENTRY_CONTRACT = {
    'required': sorted(REQUIRED_SCRIPT_FIELDS),
    'path': {
        'relative_to': 'workspace_root',
        'required_prefix': 'script/',
        'path_escape': 'forbidden',
    },
    'operation': {'allowed': ['read-only', 'read-write']},
    'duplicate_ids': 'forbidden',
    'stale_paths': 'forbidden',
    'undeclared_credential_use': 'forbidden',
    'discovery_authorizes_execution': False,
}


def _load_yaml(text: str) -> object:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[object, object]:
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValueError('duplicate mapping key')
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping,
    )
    return yaml.load(text, Loader=UniqueKeyLoader)


def validate_script_index(workspace_root: Path) -> list[str]:
    path = workspace_root / 'script' / 'index.yaml'
    if not path.is_file() or path.is_symlink():
        return ['WB_SCRIPT_INDEX_MISSING']
    try:
        document = _load_yaml(path.read_text(encoding='utf-8'))
    except (ValueError, TypeError, SyntaxError, yaml.YAMLError):
        return ['WB_SCRIPT_INDEX_YAML_INVALID']
    if not isinstance(document, dict) or set(document) != {'version', 'entry_contract', 'scripts'}:
        return ['WB_SCRIPT_INDEX_INVALID']
    if document.get('version') != 1:
        return ['WB_SCRIPT_INDEX_INVALID']
    entry_contract = document.get('entry_contract')
    if not isinstance(entry_contract, dict):
        return ['WB_SCRIPT_INDEX_CONTRACT_INVALID']
    normalized_contract = dict(entry_contract)
    required = normalized_contract.get('required')
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        return ['WB_SCRIPT_INDEX_CONTRACT_INVALID']
    normalized_contract['required'] = sorted(required)
    if normalized_contract != EXPECTED_ENTRY_CONTRACT:
        return ['WB_SCRIPT_INDEX_CONTRACT_INVALID']
    entries = document.get('scripts')
    if not isinstance(entries, list):
        return ['WB_SCRIPT_INDEX_INVALID']
    failures: list[str] = []
    ids: set[str] = set()
    indexed_paths: set[Path] = set()
    script_root = (workspace_root / 'script').resolve()
    for index, entry in enumerate(entries):
        prefix = f'WB_SCRIPT_INDEX_ENTRY_{index}'
        if not isinstance(entry, dict):
            failures.append(f'{prefix}_INVALID')
            continue
        unknown = sorted(set(entry) - SCRIPT_ENTRY_FIELDS)
        if unknown:
            failures.append(f'{prefix}_FIELDS_UNKNOWN:{",".join(unknown)}')
        missing = sorted(REQUIRED_SCRIPT_FIELDS - set(entry))
        if missing:
            failures.append(f'{prefix}_FIELDS_MISSING:{",".join(missing)}')
        script_id = str(entry.get('id') or '')
        if not SAFE_ID.fullmatch(script_id) or script_id in ids:
            failures.append('WB_SCRIPT_INDEX_DUPLICATE_ID' if script_id in ids else f'{prefix}_ID_MISSING')
        ids.add(script_id)
        raw_path = str(entry.get('path') or '')
        declared = workspace_root / raw_path
        candidate = declared.resolve(strict=False)
        if not raw_path.startswith('script/') or candidate == script_root or script_root not in candidate.parents:
            failures.append('WB_SCRIPT_INDEX_PATH_ESCAPE')
        elif declared.is_symlink():
            failures.append('WB_SCRIPT_INDEX_SYMLINK_FORBIDDEN')
        elif not candidate.is_file():
            failures.append('WB_SCRIPT_INDEX_STALE_PATH')
        else:
            indexed_paths.add(candidate)
        if entry.get('operation') not in {'read-only', 'read-write'}:
            failures.append(f'{prefix}_OPERATION_INVALID')
        for field in LIST_FIELDS:
            if field in entry and not isinstance(entry[field], list):
                failures.append(f'{prefix}_{field.upper()}_INVALID')
            elif field in entry and any(not isinstance(item, str) or not item.strip() for item in entry[field]):
                failures.append(f'{prefix}_{field.upper()}_INVALID')
        credentials = entry.get('credentials')
        if isinstance(credentials, list) and any(not SAFE_ID.fullmatch(item) for item in credentials if isinstance(item, str)):
            failures.append(f'{prefix}_CREDENTIALS_INVALID')
        invocation = entry.get('invocation')
        if not isinstance(invocation, str) or not invocation.strip() or any(character in invocation for character in ('\0', '\n', '\r')):
            failures.append(f'{prefix}_INVOCATION_INVALID')
        for field in ('description', 'functionality', 'runtime'):
            if not isinstance(entry.get(field), str) or not str(entry.get(field)).strip():
                failures.append(f'{prefix}_{field.upper()}_INVALID')
    for utility in sorted((workspace_root / 'script').iterdir() if (workspace_root / 'script').is_dir() else []):
        if utility.name == 'index.yaml' or utility.name.startswith('.'):
            continue
        if utility.is_symlink():
            if utility.resolve(strict=False) not in indexed_paths:
                failures.append(f'WB_SCRIPT_INDEX_ORPHAN:{utility.name}')
            continue
        if not utility.is_file():
            continue
        if utility.resolve() not in indexed_paths:
            failures.append(f'WB_SCRIPT_INDEX_ORPHAN:{utility.name}')
    return sorted(set(failures))
