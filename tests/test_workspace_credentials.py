from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/work-bundle'))

from credential import CredentialError, inject_secret, list_metadata, parse_credential_yaml


ROOT = Path(__file__).resolve().parents[1]


def _canary() -> str:
    return f"wb-test-{uuid.uuid4().hex}"


def _yaml_entry(kind: str, fields: dict[str, str], *, operation: str = 'read-only') -> str:
    credential = '\n'.join(f"      {key}: {json.dumps(value)}" for key, value in fields.items())
    return (
        "version: 1\n"
        "credentials:\n"
        "  - id: synthetic\n"
        "    description: synthetic test only\n"
        "    severity: high\n"
        f"    operation: {operation}\n"
        "    targets: [local]\n"
        "    scopes: [test]\n"
        "    credential:\n"
        f"      kind: {kind}\n"
        f"{credential}\n"
    )


def _store(root: Path, yaml_text: str) -> Path:
    directory = root / 'credentials'
    directory.mkdir(parents=True)
    directory.chmod(0o700)
    path = directory / 'credentials.yaml'
    path.write_text(yaml_text, encoding='utf-8')
    path.chmod(0o600)
    return path


def _consumer_for(mechanism: str) -> list[str]:
    snippets = {
        'path-reference': 'import os,pathlib; pathlib.Path(os.environ["WB_CREDENTIAL_PATH"]).exists(); print("hidden")',
        'protected-fd': 'import json,os; json.load(os.fdopen(int(os.environ["WB_CREDENTIAL_FD"]))); print("hidden")',
        'stdin': 'import sys; sys.stdin.read(); print("hidden")',
        'child-environment': 'import os; os.environ["WB_CREDENTIAL_VALUE"]; print("hidden")',
        'keychain': 'import os; os.environ["WB_CREDENTIAL_REFERENCE"]; print("hidden")',
        'ssh-agent': 'import os; os.environ["SSH_AUTH_SOCK"]; os.environ["WB_CREDENTIAL_REFERENCE"]; print("hidden")',
    }
    return [sys.executable, '-c', snippets[mechanism]]


@pytest.mark.parametrize(
    ('kind', 'mechanism'),
    [
        ('password_file', 'path-reference'),
        ('username_password', 'protected-fd'),
        ('ssh_private_key', 'path-reference'),
        ('passphrase', 'stdin'),
        ('environment_reference', 'child-environment'),
        ('external_secret_reference', 'keychain'),
        ('external_secret_reference', 'ssh-agent'),
    ],
)
def test_canonical_yaml_six_form_adapter_matrix_has_zero_visible_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, mechanism: str
) -> None:
    marker = _canary()
    referenced_file = tmp_path / 'protected-input'
    referenced_file.write_text(marker, encoding='utf-8')
    referenced_file.chmod(0o600)
    fields = {
        'password_file': {'path': str(referenced_file)},
        'username_password': {'username': 'synthetic-user', 'password': marker},
        'ssh_private_key': {'private_key_path': str(referenced_file)},
        'passphrase': {'passphrase': marker},
        'environment_reference': {'variable': 'WB_SYNTHETIC_CREDENTIAL'},
        'external_secret_reference': {'provider': mechanism, 'reference': marker},
    }[kind]
    if kind == 'environment_reference':
        monkeypatch.setenv('WB_SYNTHETIC_CREDENTIAL', marker)
    if mechanism == 'ssh-agent':
        monkeypatch.setenv('SSH_AUTH_SOCK', str(tmp_path / 'synthetic-agent.sock'))
    _store(tmp_path, _yaml_entry(kind, fields))
    parent_before = dict(os.environ)

    metadata = list_metadata(tmp_path)
    result = inject_secret(
        tmp_path, 'synthetic', 'local', 'read-only', True,
        _consumer_for(mechanism), mechanism=mechanism, purpose='synthetic adapter test',
    )

    assert result == {
        'credential_id': 'synthetic',
        'target': 'local',
        'requested_operation': 'read-only',
        'effective_operation': 'read-only',
        'injection_mechanism': mechanism,
        'result': 'passed',
        'redacted_failure_code': None,
    }
    assert metadata[0].kind == kind
    assert dict(os.environ) == parent_before
    audit = (tmp_path / '.work-bundle/orchestration/execution-state/credential-use.jsonl').read_text(encoding='utf-8')
    handoff_fixture = json.dumps({'credential_id': result['credential_id'], 'result': result['result']})
    index_fixture = json.dumps([item.__dict__ for item in metadata])
    git_surface = subprocess.check_output(['git', 'diff', '--', *TASK_TARGETS], cwd=ROOT, text=True)
    visible = json.dumps(result) + repr(metadata) + audit + handoff_fixture + index_fixture + git_surface
    assert marker not in visible


TASK_TARGETS = [
    'references/assets/template/credentials.yaml',
    'references/wb-credential-use-contract.yaml',
    'scripts/work-bundle/credential.py',
    'scripts/work-bundle/dispatcher.py',
    'skills/wb-credential-use/SKILL.md',
    'skills/wb-credential-use/agents/openai.yaml',
    'rules/security-exclusion.md',
    'rules/work-bundle/wb-credential-use.md',
    'tests/test_workspace_credentials.py',
    'tests/test_rule_contracts.py',
]


@pytest.mark.parametrize(
    ('yaml_text', 'code'),
    [
        ('version: 1\ncredentials:\n  - not-a-mapping\n', 'ENTRY_INVALID'),
        ('version: 1\ncredentials: []\nunknown: field\n', 'SCHEMA_INVALID'),
        (
            'version: 1\ncredentials:\n'
            '  - id: repeated\n    description: one\n    severity: low\n    operation: read-only\n    credential:\n      kind: passphrase\n      passphrase: one\n'
            '  - id: repeated\n    description: two\n    severity: low\n    operation: read-only\n    credential:\n      kind: passphrase\n      passphrase: two\n',
            'DUPLICATE_ID',
        ),
        (
            'version: 1\ncredentials:\n  - id: one\n    description: test\n    severity: low\n    operation: read-only\n    unknown: field\n    credential:\n      kind: passphrase\n      passphrase: value\n',
            'ENTRY_FIELDS',
        ),
        (
            'version: 1\ncredentials:\n  - id: one\n    description: test\n    severity: low\n    operation: read-only\n    credential:\n      kind: username_password\n      username: user\n',
            'VARIANT_INCOMPLETE',
        ),
        (
            'version: 1\ncredentials:\n  - id: one\n    description: test\n    severity: low\n    operation: read-only\n    credential:\n      kind: passphrase\n      passphrase: ""\n',
            'REFERENCE_EMPTY',
        ),
    ],
)
def test_malformed_yaml_and_closed_schema_fail_with_non_secret_codes(tmp_path: Path, yaml_text: str, code: str) -> None:
    _store(tmp_path, yaml_text)
    with pytest.raises(CredentialError) as captured:
        list_metadata(tmp_path)
    assert code in str(captured.value)
    assert yaml_text not in str(captured.value)


def test_duplicate_yaml_mapping_key_is_rejected_without_value_diagnostic() -> None:
    with pytest.raises(CredentialError, match='WB_CREDENTIAL_YAML_INVALID'):
        parse_credential_yaml('version: 1\nversion: 2\ncredentials: []\n')


def test_authority_operation_and_adapter_gates_block_before_consumer(tmp_path: Path) -> None:
    marker = _canary()
    _store(tmp_path, _yaml_entry('passphrase', {'passphrase': marker}))
    invoked = tmp_path / 'invoked'
    command = [sys.executable, '-c', f'import pathlib; pathlib.Path({str(invoked)!r}).write_text("x")']
    attempts = [
        ('other', 'read-only', True, 'stdin', 'TARGET_MISMATCH'),
        ('local', 'read-write', True, 'stdin', 'OPERATION_MISMATCH'),
        ('local', 'read-only', False, 'stdin', 'AUTHORITY_REQUIRED'),
        ('local', 'read-only', True, 'child-environment', 'ADAPTER_UNSUPPORTED'),
        ('local', 'read-only', True, 'command-line', 'ADAPTER_UNSUPPORTED'),
    ]
    for target, operation, authority, mechanism, code in attempts:
        with pytest.raises(CredentialError, match=code) as captured:
            inject_secret(tmp_path, 'synthetic', target, operation, authority, command, mechanism=mechanism)
        assert marker not in str(captured.value)
        assert not invoked.exists()


def test_passphrase_protected_ssh_key_and_unsafe_external_provider_block(tmp_path: Path) -> None:
    marker = _canary()
    key = tmp_path / 'synthetic-key'
    key.write_text(marker, encoding='utf-8')
    key.chmod(0o600)
    cases = [
        _yaml_entry('ssh_private_key', {'private_key_path': str(key), 'passphrase': marker}),
        _yaml_entry('external_secret_reference', {'provider': 'unsupported-provider', 'reference': marker}),
    ]
    for yaml_text in cases:
        root = tmp_path / uuid.uuid4().hex
        _store(root, yaml_text)
        with pytest.raises(CredentialError, match='ADAPTER_UNSUPPORTED') as captured:
            inject_secret(root, 'synthetic', 'local', 'read-only', True, [sys.executable, '-c', 'raise SystemExit(99)'])
        assert marker not in str(captured.value)
        assert not (root / '.work-bundle').exists()


def test_permissions_extra_files_and_symlink_fail_closed(tmp_path: Path) -> None:
    _store(tmp_path, 'version: 1\ncredentials: []\n')
    (tmp_path / 'credentials/extra').write_text('x', encoding='utf-8')
    with pytest.raises(CredentialError, match='EXTRA_FILE'):
        list_metadata(tmp_path)


def test_dispatcher_lists_metadata_only_from_canonical_yaml(tmp_path: Path) -> None:
    marker = _canary()
    _store(tmp_path, _yaml_entry('passphrase', {'passphrase': marker}))
    result = subprocess.run(
        [sys.executable, 'scripts/wb.py', 'credential-list', '--workspace-root', str(tmp_path)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0
    assert marker not in result.stdout + result.stderr
    assert 'synthetic' in result.stdout and 'passphrase' in result.stdout
