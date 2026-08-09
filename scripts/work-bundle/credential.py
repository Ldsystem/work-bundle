from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CredentialError(Exception):
    """A stable, non-secret credential workflow failure."""


@dataclass(frozen=True)
class CredentialMetadata:
    id: str
    description: str
    severity: str
    operation: str
    kind: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class ConsumerAdapter:
    mechanism: str
    value_fields: tuple[str, ...]


_KINDS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    'password_file': (frozenset({'path'}), frozenset()),
    'username_password': (frozenset({'username', 'password'}), frozenset()),
    'ssh_private_key': (frozenset({'private_key_path'}), frozenset({'passphrase'})),
    'passphrase': (frozenset({'passphrase'}), frozenset()),
    'environment_reference': (frozenset({'variable'}), frozenset()),
    'external_secret_reference': (frozenset({'provider', 'reference'}), frozenset()),
}
_ENTRY_REQUIRED = frozenset({'id', 'description', 'severity', 'operation', 'credential'})
_ENTRY_OPTIONAL = frozenset({'targets', 'scopes'})
_SEVERITIES = frozenset({'low', 'medium', 'high', 'critical'})
_OPERATIONS = frozenset({'read-only', 'read-write'})
_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')


def _fail(code: str) -> None:
    raise CredentialError(code)


def validate_store(workspace_root: Path) -> Path:
    directory = workspace_root / 'credentials'
    store = directory / 'credentials.yaml'
    if directory.is_symlink() or store.is_symlink():
        _fail('WB_CREDENTIAL_SYMLINK')
    if not directory.is_dir() or not store.is_file():
        _fail('WB_CREDENTIAL_STORE_MISSING')
    if sorted(path.name for path in directory.iterdir()) != ['credentials.yaml']:
        _fail('WB_CREDENTIAL_EXTRA_FILE')
    if os.name == 'posix' and directory.stat().st_mode & 0o777 != 0o700:
        _fail('WB_CREDENTIAL_DIRECTORY_MODE')
    if os.name == 'posix' and store.stat().st_mode & 0o777 != 0o600:
        _fail('WB_CREDENTIAL_FILE_MODE')
    return store


class _YamlParser:
    """Parse the bounded YAML subset used by the credential-store contract."""

    def __init__(self, text: str) -> None:
        self.lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            if not raw.strip() or raw.lstrip().startswith('#'):
                continue
            if '\t' in raw:
                raise ValueError
            indent = len(raw) - len(raw.lstrip(' '))
            if indent % 2:
                raise ValueError
            self.lines.append((indent, raw.strip()))

    def parse(self) -> object:
        if not self.lines or self.lines[0][0] != 0:
            raise ValueError
        value, cursor = self._block(0, 0)
        if cursor != len(self.lines):
            raise ValueError
        return value

    def _block(self, cursor: int, indent: int) -> tuple[object, int]:
        if cursor >= len(self.lines) or self.lines[cursor][0] != indent:
            raise ValueError
        if self.lines[cursor][1] == '-' or self.lines[cursor][1].startswith('- '):
            return self._list(cursor, indent)
        return self._mapping(cursor, indent)

    def _mapping(self, cursor: int, indent: int) -> tuple[dict[str, object], int]:
        result: dict[str, object] = {}
        while cursor < len(self.lines) and self.lines[cursor][0] == indent:
            text = self.lines[cursor][1]
            if text == '-' or text.startswith('- '):
                break
            key, raw_value = self._pair(text)
            if key in result:
                raise ValueError
            cursor += 1
            if raw_value:
                result[key] = self._scalar(raw_value)
            else:
                if cursor >= len(self.lines) or self.lines[cursor][0] <= indent:
                    result[key] = None
                elif self.lines[cursor][0] != indent + 2:
                    raise ValueError
                else:
                    result[key], cursor = self._block(cursor, indent + 2)
        return result, cursor

    def _list(self, cursor: int, indent: int) -> tuple[list[object], int]:
        result: list[object] = []
        while cursor < len(self.lines) and self.lines[cursor][0] == indent:
            text = self.lines[cursor][1]
            if text != '-' and not text.startswith('- '):
                break
            item = text[1:].strip()
            cursor += 1
            if not item:
                if cursor >= len(self.lines) or self.lines[cursor][0] != indent + 2:
                    raise ValueError
                value, cursor = self._block(cursor, indent + 2)
                result.append(value)
                continue
            if ':' not in item:
                result.append(self._scalar(item))
                continue
            key, raw_value = self._pair(item)
            mapping: dict[str, object] = {}
            mapping[key] = self._scalar(raw_value) if raw_value else None
            if cursor < len(self.lines) and self.lines[cursor][0] > indent:
                if self.lines[cursor][0] != indent + 2:
                    raise ValueError
                tail, cursor = self._mapping(cursor, indent + 2)
                if key in tail:
                    raise ValueError
                if mapping[key] is None and key in tail:
                    mapping[key] = tail.pop(key)
                mapping.update(tail)
            result.append(mapping)
        return result, cursor

    @staticmethod
    def _pair(text: str) -> tuple[str, str]:
        key, separator, value = text.partition(':')
        key = key.strip()
        if not separator or not _KEY.fullmatch(key):
            raise ValueError
        return key, value.strip()

    @staticmethod
    def _scalar(value: str) -> object:
        if value in {'[]', '{}'}:
            return [] if value == '[]' else {}
        if value.startswith('[') and value.endswith(']'):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            body = value[1:-1].strip()
            if not body:
                return []
            if any(token in body for token in ('[', ']', '{', '}')):
                raise ValueError
            return [_YamlParser._scalar(item.strip()) for item in body.split(',')]
        if value in {'null', 'Null', 'NULL', '~'}:
            return None
        if value in {'true', 'True', 'TRUE'}:
            return True
        if value in {'false', 'False', 'FALSE'}:
            return False
        if re.fullmatch(r'-?(0|[1-9][0-9]*)', value):
            return int(value)
        if value.startswith(('{', '"')):
            return json.loads(value)
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1].replace("''", "'")
        if any(token in value for token in (' #', '\r', '\n')):
            raise ValueError
        return value


def parse_credential_yaml(text: str) -> dict[str, object]:
    try:
        parsed = _YamlParser(text).parse()
    except Exception:
        _fail('WB_CREDENTIAL_YAML_INVALID')
    if not isinstance(parsed, dict):
        _fail('WB_CREDENTIAL_SCHEMA_INVALID')
    return parsed


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        _fail('WB_CREDENTIAL_SCHEMA_INVALID')
    if any(not _nonempty(item) for item in value):
        _fail('WB_CREDENTIAL_SCHEMA_INVALID')
    return tuple(str(item) for item in value)


def validate_credential_variant(credential: object) -> dict[str, object]:
    if not isinstance(credential, dict):
        _fail('WB_CREDENTIAL_VARIANT_INVALID')
    kind = credential.get('kind')
    if kind not in _KINDS:
        _fail('WB_CREDENTIAL_KIND_UNSUPPORTED')
    required, optional = _KINDS[str(kind)]
    allowed = required | optional | {'kind'}
    if not required.issubset(credential):
        _fail('WB_CREDENTIAL_VARIANT_INCOMPLETE')
    if not set(credential).issubset(allowed):
        _fail('WB_CREDENTIAL_VARIANT_FIELDS')
    for field in required | (set(credential) & optional):
        if not _nonempty(credential[field]):
            _fail('WB_CREDENTIAL_REFERENCE_EMPTY')
    return credential


def _entries(workspace_root: Path) -> list[dict[str, object]]:
    try:
        data = parse_credential_yaml(validate_store(workspace_root).read_text(encoding='utf-8'))
    except CredentialError:
        raise
    except Exception:
        _fail('WB_CREDENTIAL_STORE_READ_FAILED')
    if set(data) != {'version', 'credentials'} or data.get('version') != 1:
        _fail('WB_CREDENTIAL_SCHEMA_INVALID')
    raw_entries = data.get('credentials')
    if not isinstance(raw_entries, list):
        _fail('WB_CREDENTIAL_SCHEMA_INVALID')
    entries: list[dict[str, object]] = []
    identifiers: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            _fail('WB_CREDENTIAL_ENTRY_INVALID')
        if not _ENTRY_REQUIRED.issubset(raw) or not set(raw).issubset(_ENTRY_REQUIRED | _ENTRY_OPTIONAL):
            _fail('WB_CREDENTIAL_ENTRY_FIELDS')
        if not _nonempty(raw.get('id')) or not _nonempty(raw.get('description')):
            _fail('WB_CREDENTIAL_ENTRY_INVALID')
        identifier = str(raw['id'])
        if identifier in identifiers:
            _fail('WB_CREDENTIAL_DUPLICATE_ID')
        identifiers.add(identifier)
        if raw.get('severity') not in _SEVERITIES or raw.get('operation') not in _OPERATIONS:
            _fail('WB_CREDENTIAL_ENTRY_INVALID')
        raw['targets'] = list(_string_list(raw.get('targets', [])))
        if 'scopes' in raw:
            raw['scopes'] = list(_string_list(raw['scopes']))
        validate_credential_variant(raw['credential'])
        entries.append(raw)
    return entries


def list_metadata(workspace_root: Path) -> list[CredentialMetadata]:
    return [
        CredentialMetadata(
            id=str(entry['id']),
            description=str(entry['description']),
            severity=str(entry['severity']),
            operation=str(entry['operation']),
            kind=str(entry['credential']['kind']),  # type: ignore[index]
            targets=tuple(str(item) for item in entry['targets']),
        )
        for entry in _entries(workspace_root)
    ]


def authorize_operation(metadata: CredentialMetadata, target: str, requested: str, authorized: bool) -> None:
    if requested not in _OPERATIONS:
        _fail('WB_CREDENTIAL_OPERATION_INVALID')
    if not target or target not in metadata.targets:
        _fail('WB_CREDENTIAL_TARGET_MISMATCH')
    if requested == 'read-write' and metadata.operation != 'read-write':
        _fail('WB_CREDENTIAL_OPERATION_MISMATCH')
    if (metadata.severity in {'high', 'critical'} or requested == 'read-write') and not authorized:
        _fail('WB_CREDENTIAL_AUTHORITY_REQUIRED')


def select_consumer_adapter(credential: dict[str, object], requested_mechanism: str | None = None) -> ConsumerAdapter:
    kind = str(credential['kind'])
    adapters = {
        'password_file': ConsumerAdapter('path-reference', ('path',)),
        'username_password': ConsumerAdapter('protected-fd', ('username', 'password')),
        'ssh_private_key': ConsumerAdapter('path-reference', ('private_key_path',)),
        'passphrase': ConsumerAdapter('stdin', ('passphrase',)),
        'environment_reference': ConsumerAdapter('child-environment', ('variable',)),
        'external_secret_reference': ConsumerAdapter('keychain', ('provider', 'reference')),
    }
    adapter = adapters[kind]
    if kind == 'ssh_private_key' and 'passphrase' in credential:
        _fail('WB_CREDENTIAL_ADAPTER_UNSUPPORTED')
    if kind == 'external_secret_reference':
        provider = credential.get('provider')
        if provider not in {'keychain', 'ssh-agent'}:
            _fail('WB_CREDENTIAL_ADAPTER_UNSUPPORTED')
        adapter = ConsumerAdapter(str(provider), ('provider', 'reference'))
    if requested_mechanism is not None and requested_mechanism != adapter.mechanism:
        _fail('WB_CREDENTIAL_ADAPTER_UNSUPPORTED')
    return adapter


def _run_consumer(command: list[str], credential: dict[str, object], adapter: ConsumerAdapter) -> int:
    if not command or any(not isinstance(part, str) or not part for part in command):
        _fail('WB_CREDENTIAL_CONSUMER_INVALID')
    kind = str(credential['kind'])
    child_environment = os.environ.copy()
    if adapter.mechanism == 'path-reference':
        field = 'path' if kind == 'password_file' else 'private_key_path'
        path = Path(str(credential[field])).expanduser()
        if not path.is_file() or path.is_symlink():
            _fail('WB_CREDENTIAL_REFERENCE_INVALID')
        child_environment['WB_CREDENTIAL_PATH'] = str(path)
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_environment, check=False)
        return process.returncode
    if adapter.mechanism == 'protected-fd':
        with tempfile.TemporaryFile() as protected:
            protected.write(json.dumps({'username': credential['username'], 'password': credential['password']}).encode('utf-8'))
            protected.seek(0)
            child_environment['WB_CREDENTIAL_FD'] = str(protected.fileno())
            process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_environment, pass_fds=(protected.fileno(),), check=False)
            return process.returncode
    if adapter.mechanism == 'stdin':
        process = subprocess.run(command, input=str(credential['passphrase']), text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_environment, check=False)
        return process.returncode
    if adapter.mechanism == 'child-environment':
        variable = str(credential['variable'])
        if variable not in os.environ or not os.environ[variable]:
            _fail('WB_CREDENTIAL_REFERENCE_INVALID')
        child_environment['WB_CREDENTIAL_VALUE'] = os.environ[variable]
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_environment, check=False)
        return process.returncode
    if adapter.mechanism == 'keychain':
        child_environment['WB_CREDENTIAL_PROVIDER'] = str(credential['provider'])
        child_environment['WB_CREDENTIAL_REFERENCE'] = str(credential['reference'])
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_environment, check=False)
        return process.returncode
    if adapter.mechanism == 'ssh-agent':
        if not child_environment.get('SSH_AUTH_SOCK'):
            _fail('WB_CREDENTIAL_REFERENCE_INVALID')
        child_environment['WB_CREDENTIAL_REFERENCE'] = str(credential['reference'])
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_environment, check=False)
        return process.returncode
    _fail('WB_CREDENTIAL_ADAPTER_UNSUPPORTED')
    return 1


def inject_secret(
    workspace_root: Path,
    credential_id: str,
    target: str,
    requested: str,
    authorized: bool,
    command: list[str],
    *,
    mechanism: str | None = None,
    purpose: str = 'current-task',
    authorization_source: str = 'current-task',
) -> dict[str, object]:
    entries = _entries(workspace_root)
    entry = next((candidate for candidate in entries if candidate['id'] == credential_id), None)
    if entry is None:
        _fail('WB_CREDENTIAL_NOT_FOUND')
    credential = entry['credential']
    assert isinstance(credential, dict)
    metadata = CredentialMetadata(
        id=str(entry['id']), description=str(entry['description']), severity=str(entry['severity']),
        operation=str(entry['operation']), kind=str(credential['kind']), targets=tuple(entry['targets']),
    )
    if not _nonempty(purpose) or not _nonempty(authorization_source):
        _fail('WB_CREDENTIAL_AUTHORITY_REQUIRED')
    authorize_operation(metadata, target, requested, authorized)
    adapter = select_consumer_adapter(credential, mechanism)
    returncode = _run_consumer(command, credential, adapter)
    result_state = 'passed' if returncode == 0 else 'failed'
    result = {
        'credential_id': credential_id,
        'target': target,
        'requested_operation': requested,
        'effective_operation': requested,
        'injection_mechanism': adapter.mechanism,
        'result': result_state,
        'redacted_failure_code': None if returncode == 0 else 'WB_CREDENTIAL_CONSUMER_FAILED',
    }
    write_audit_evidence(workspace_root, credential_id, target, requested, result_state, authorization_source, result['redacted_failure_code'])
    return result


def write_audit_evidence(
    workspace_root: Path,
    credential_id: str,
    target: str,
    operation: str,
    result: str,
    authorization_source: str = 'current-task',
    failure_code: object = None,
) -> None:
    path = workspace_root / '.work-bundle/orchestration/execution-state/credential-use.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'credential_id': credential_id,
        'target': target,
        'requested_operation': operation,
        'effective_operation': operation,
        'invoking_skill_or_script_id': 'wb-credential-use',
        'authorization_source': authorization_source,
        'result': result,
        'redacted_failure_code': failure_code,
    }
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, sort_keys=True) + '\n')
