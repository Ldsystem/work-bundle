from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/work-bundle'))

import credential as credential_module
from credential import CredentialError, inject_secret, list_metadata, parse_credential_yaml
from platform_runtime import PathKind


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
        'stdin-json': 'import json,sys; value=json.load(sys.stdin); assert set(value)=={"username","password"}; print("hidden")',
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
        ('username_password', 'stdin-json'),
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


def test_windows_subprocess_seam_sends_one_exact_utf8_json_object_without_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    username = 'synthetic-用户'
    password = _canary()
    _store(tmp_path, _yaml_entry('username_password', {'username': username, 'password': password}))
    monkeypatch.setenv(f'WB_{password}_KEY', 'ordinary')
    monkeypatch.setenv('WB_SYNTHETIC_PASSWORD_VALUE', f'prefix-{password}-suffix')
    monkeypatch.setenv('WB_SYNTHETIC_USERNAME_VALUE', f'prefix-{username}-suffix')
    parent_before = dict(os.environ)
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed['command'] = command
        observed.update(kwargs)
        return type('Completed', (), {'returncode': 0})()

    monkeypatch.setattr(credential_module.subprocess, 'run', fake_run)
    command = ['synthetic-consumer', '--bounded']

    result = inject_secret(
        tmp_path, 'synthetic', 'local', 'read-only', True, command,
        mechanism='stdin-json', purpose='synthetic adapter test',
    )

    expected = json.dumps(
        {'username': username, 'password': password},
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')
    assert observed['input'] == expected
    assert observed['command'] == command
    assert observed['stdout'] is subprocess.DEVNULL
    assert observed['stderr'] is subprocess.DEVNULL
    assert 'pass_fds' not in observed
    assert 'text' not in observed
    assert password not in json.dumps(observed['command'])
    assert password not in json.dumps(observed['env'])
    assert username not in json.dumps(observed['env'], ensure_ascii=False)
    assert password not in json.dumps(result)
    assert dict(os.environ) == parent_before


@pytest.mark.parametrize(
    ('command', 'mechanism', 'code'),
    [
        ([], 'stdin-json', 'CONSUMER_INVALID'),
        (['synthetic-consumer'], 'protected-fd', 'ADAPTER_UNSUPPORTED'),
    ],
)
def test_command_and_mechanism_fail_before_credential_store_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    mechanism: str,
    code: str,
) -> None:
    store_read = False

    def forbidden_read(workspace_root: Path) -> list[dict[str, object]]:
        nonlocal store_read
        store_read = True
        raise AssertionError(f'unexpected credential read from {workspace_root}')

    monkeypatch.setattr(credential_module, '_entries', forbidden_read)

    with pytest.raises(CredentialError, match=code):
        inject_secret(
            tmp_path, 'synthetic', 'local', 'read-only', True, command,
            mechanism=mechanism, purpose='synthetic validation test',
        )
    assert not store_read


def test_supported_form_mismatch_fails_before_secret_value_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MetadataOnlyCredential(dict[str, object]):
        def __getitem__(self, key: str) -> object:
            if key in {'username', 'password'}:
                raise AssertionError(f'secret field accessed: {key}')
            return super().__getitem__(key)

        def get(self, key: str, default: object = None) -> object:
            if key in {'username', 'password'}:
                raise AssertionError(f'secret field accessed: {key}')
            return super().get(key, default)

    credential = MetadataOnlyCredential(
        kind='username_password', username='synthetic-user', password=_canary(),
    )
    _store(tmp_path, 'version: 1\ncredentials: []\n')
    monkeypatch.setattr(
        credential_module,
        'parse_credential_yaml',
        lambda text: {'version': 1, 'credentials': [{
            'id': 'synthetic',
            'description': 'synthetic test only',
            'severity': 'high',
            'operation': 'read-only',
            'targets': ['local'],
            'credential': credential,
        }]},
    )

    with pytest.raises(CredentialError, match='WB_CREDENTIAL_ADAPTER_UNSUPPORTED'):
        inject_secret(
            tmp_path, 'synthetic', 'local', 'read-only', True,
            ['synthetic-consumer'], mechanism='stdin', purpose='synthetic mismatch test',
        )


def test_non_secret_adapter_fields_remain_permitted_in_command_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    referenced_file = tmp_path / 'synthetic-reference'
    referenced_file.write_text('synthetic', encoding='utf-8')
    referenced_file.chmod(0o600)
    monkeypatch.setenv('WB_SYNTHETIC_REFERENCE', 'synthetic-environment-value')
    monkeypatch.setattr(
        credential_module.subprocess,
        'run',
        lambda *args, **kwargs: type('Completed', (), {'returncode': 0})(),
    )
    cases = [
        ('password_file', {'path': str(referenced_file)}, 'path-reference', str(referenced_file)),
        ('environment_reference', {'variable': 'WB_SYNTHETIC_REFERENCE'}, 'child-environment', 'WB_SYNTHETIC_REFERENCE'),
        ('external_secret_reference', {'provider': 'keychain', 'reference': 'synthetic-reference'}, 'keychain', 'synthetic-reference'),
    ]

    for kind, fields, mechanism, argument in cases:
        root = tmp_path / kind
        _store(root, _yaml_entry(kind, fields))
        result = inject_secret(
            root, 'synthetic', 'local', 'read-only', True,
            ['synthetic-consumer', argument], mechanism=mechanism, purpose='synthetic compatibility test',
        )
        assert result['result'] == 'passed'


def test_secret_command_argument_and_non_utf8_username_password_fail_redacted_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spawned = False

    def forbidden_spawn(*args: object, **kwargs: object) -> object:
        nonlocal spawned
        spawned = True
        raise AssertionError('consumer must not spawn')

    monkeypatch.setattr(credential_module.subprocess, 'run', forbidden_spawn)
    marker = _canary()
    passphrase_root = tmp_path / 'passphrase'
    _store(passphrase_root, _yaml_entry('passphrase', {'passphrase': marker}))
    with pytest.raises(CredentialError, match='WB_CREDENTIAL_CONSUMER_INVALID') as argument_error:
        inject_secret(
            passphrase_root, 'synthetic', 'local', 'read-only', True,
            ['synthetic-consumer', f'prefix-{marker}-suffix'], mechanism='stdin',
            purpose='synthetic containment test',
        )
    assert marker not in str(argument_error.value)

    surrogate = '\ud800'
    credential = {'kind': 'username_password', 'username': surrogate, 'password': marker}
    monkeypatch.setattr(
        credential_module,
        '_entries',
        lambda workspace_root, **kwargs: [{
            'id': 'synthetic',
            'description': 'synthetic test only',
            'severity': 'high',
            'operation': 'read-only',
            'targets': ['local'],
            'credential': credential,
        }],
    )
    with pytest.raises(CredentialError, match='WB_CREDENTIAL_VALUE_ENCODING') as encoding_error:
        inject_secret(
            tmp_path, 'synthetic', 'local', 'read-only', True,
            ['synthetic-consumer'], mechanism='stdin-json', purpose='synthetic encoding test',
        )
    captured = capsys.readouterr()
    visible = str(encoding_error.value) + captured.out + captured.err
    assert marker not in visible
    assert surrogate not in visible
    assert not spawned


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


@pytest.mark.parametrize('kind', [PathKind.SYMLINK, PathKind.JUNCTION, PathKind.REPARSE])
def test_credential_store_rejects_every_link_like_boundary_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: PathKind
) -> None:
    store = _store(tmp_path, 'version: 1\ncredentials: []\n')
    original_classifier = credential_module.classify_path
    monkeypatch.setattr(
        credential_module,
        'classify_path',
        lambda path: kind if Path(path) == store else original_classifier(path),
    )

    with pytest.raises(CredentialError, match='WB_CREDENTIAL_LINK_LIKE'):
        list_metadata(tmp_path)


@pytest.mark.parametrize('kind', [PathKind.SYMLINK, PathKind.JUNCTION, PathKind.REPARSE])
def test_path_reference_rejects_every_link_like_kind_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: PathKind
) -> None:
    marker = _canary()
    referenced_file = tmp_path / 'synthetic-reference'
    referenced_file.write_text(marker, encoding='utf-8')
    _store(tmp_path, _yaml_entry('password_file', {'path': str(referenced_file)}))
    original_classifier = credential_module.classify_path
    monkeypatch.setattr(
        credential_module,
        'classify_path',
        lambda path: kind if Path(path) == referenced_file else original_classifier(path),
    )
    spawned = False

    def forbidden_spawn(*args: object, **kwargs: object) -> object:
        nonlocal spawned
        spawned = True
        raise AssertionError('consumer must not spawn')

    monkeypatch.setattr(credential_module.subprocess, 'run', forbidden_spawn)

    with pytest.raises(CredentialError, match='WB_CREDENTIAL_REFERENCE_INVALID') as captured:
        inject_secret(
            tmp_path, 'synthetic', 'local', 'read-only', True,
            ['synthetic-consumer'], mechanism='path-reference', purpose='synthetic path test',
        )
    assert marker not in str(captured.value)
    assert not spawned


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
