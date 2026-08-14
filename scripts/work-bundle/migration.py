from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from workspace_resources import ensure_workspace_resources, validate_script_index
from worktree import provision_member


TRANSIENT_NAMES = frozenset({'.cache', '.tmp', '__pycache__', '.pytest_cache'})
RECOVERY_DIRECTORY = '.work-bundle-migration-transactions'
TRANSACTION_STAGES = (
    'copy-authority',
    'workspace-resources',
    'member-provision',
    'final-verification',
    'metadata-publication',
    'registry-publication',
)


class MigrationError(Exception):
    def __init__(self, code: str, transaction_record: Path | None = None) -> None:
        self.code = code
        self.transaction_record = transaction_record
        super().__init__(code)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            value.update(chunk)
    return value.hexdigest()


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', '-C', str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def source_git_state(root: Path) -> dict[str, object]:
    """Return bounded Git facts without modifying the repository."""
    resolved = root.resolve()
    inside = _run_git(resolved, 'rev-parse', '--is-inside-work-tree')
    if inside.returncode or inside.stdout.strip() != 'true':
        return {
            'root': str(resolved),
            'git_repository': False,
            'branch': '',
            'head': '',
            'dirty': False,
            'status_entries': [],
        }
    branch = _run_git(resolved, 'branch', '--show-current')
    head = _run_git(resolved, 'rev-parse', 'HEAD')
    status_result = _run_git(resolved, 'status', '--porcelain=v1', '--untracked-files=all')
    if status_result.returncode:
        raise MigrationError('WB_MIGRATION_GIT_STATE_UNRESOLVED')
    entries = [line for line in status_result.stdout.splitlines() if line]
    return {
        'root': str(resolved),
        'git_repository': True,
        'branch': branch.stdout.strip() if branch.returncode == 0 else '',
        'head': head.stdout.strip() if head.returncode == 0 else '',
        'dirty': bool(entries),
        'status_entries': entries,
    }


def work_bundle_git_state(source: Path) -> dict[str, object]:
    root = source.resolve() / '.work-bundle'
    if not root.is_dir():
        return {
            'root': str(root),
            'git_repository': False,
            'branch': '',
            'head': '',
            'dirty': False,
            'status_entries': [],
        }
    return source_git_state(root)


def _entry(path: Path, root: Path) -> dict[str, object]:
    relative = str(path.relative_to(root))
    mode = stat.S_IMODE(path.lstat().st_mode)
    if path.is_symlink():
        raise MigrationError('WB_MIGRATION_UNSAFE_SYMLINK')
    if path.is_dir():
        return {'path': relative, 'type': 'directory', 'mode': mode, 'mtime_ns': path.stat().st_mtime_ns}
    if path.is_file():
        return {
            'path': relative,
            'type': 'file',
            'mode': mode,
            'mtime_ns': path.stat().st_mtime_ns,
            'digest': _digest(path),
        }
    raise MigrationError('WB_MIGRATION_UNSUPPORTED_FILE_TYPE')


def _is_transient(path: Path, root: Path) -> bool:
    return any(part in TRANSIENT_NAMES for part in path.relative_to(root).parts)


def _inventory(root: Path, *, exclude_transient: bool = True) -> list[dict[str, object]]:
    if not root.exists():
        return []
    result: list[dict[str, object]] = []
    for path in sorted(root.rglob('*')):
        if exclude_transient and _is_transient(path, root):
            continue
        result.append(_entry(path, root))
    return result


def _inventory_digest(inventory: Iterable[dict[str, object]]) -> str:
    encoded = json.dumps(list(inventory), sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _preservation_inventory(root: Path) -> list[dict[str, object]]:
    """Ignore incidental Git-index timestamps while preserving all bytes and modes."""
    inventory = _inventory(root)
    for item in inventory:
        if '.git' in Path(str(item['path'])).parts:
            item.pop('mtime_ns', None)
    return inventory


def _baseline_evidence(
    source_state: dict[str, object],
    nested_state: dict[str, object],
    member_origin_state: dict[str, object] | None = None,
) -> dict[str, object]:
    origin_state = member_origin_state or source_state
    facts = {
        'source_repository_dirty': bool(source_state['dirty']),
        'work_bundle_git_dirty': bool(nested_state['dirty']),
        'member_origin_dirty': bool(origin_state['dirty']),
        'source_head': source_state['head'],
        'work_bundle_head': nested_state['head'],
        'member_origin_head': origin_state['head'],
        'source_status_entries': source_state['status_entries'],
        'work_bundle_status_entries': nested_state['status_entries'],
        'member_origin_status_entries': origin_state['status_entries'],
    }
    token = hashlib.sha256(json.dumps(facts, sort_keys=True).encode('utf-8')).hexdigest()
    return {**facts, 'id': token}


def inspect_migration(source: Path, target: Path, origin: Path | None = None) -> dict[str, object]:
    source, target = source.resolve(), target.resolve()
    origin = (origin or source).resolve()
    source_state = source_git_state(source)
    nested_state = work_bundle_git_state(source)
    origin_state = source_git_state(origin)
    return {
        'source_root': str(source),
        'target_root': str(target),
        'member_origin_root': str(origin),
        'source_exists': source.is_dir(),
        'target_exists': target.exists(),
        'work_bundle_exists': (source / '.work-bundle').is_dir(),
        'credential_store_present': (source / 'credentials/credentials.yaml').is_file(),
        'source_repository_git': source_state,
        'work_bundle_git': nested_state,
        'member_origin_git': origin_state,
        'accepted_baseline_evidence': _baseline_evidence(source_state, nested_state, origin_state),
    }


def propose_migration(
    source: Path,
    target: Path,
    repository_id: str,
    branch: str,
    base_ref: str,
    *,
    origin: Path | None = None,
    workspace_slug: str | None = None,
    repository_name: str | None = None,
    additional_repository_origins: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    inspection = inspect_migration(source, target, origin)
    slug = workspace_slug or target.name
    name = repository_name or repository_id
    return {
        **inspection,
        'workspace_slug': slug,
        'repository_id': repository_id,
        'repository_name': name,
        'working_branch': branch,
        'base_ref': base_ref,
        'additional_repository_origins': list(additional_repository_origins or []),
        'dry_run': True,
        'changed_files': [],
        'git_actions': [],
        'credential_action': 'create-empty-protected-store',
        'apply_requires_accepted_baseline': bool(
            inspection['source_repository_git']['dirty']
            or inspection['work_bundle_git']['dirty']
            or inspection['member_origin_git']['dirty']
        ),
    }


def verify_copy(source: Path, target: Path) -> bool:
    return _inventory(source / '.work-bundle') == _inventory(target / '.work-bundle')


@dataclass
class MigrationTransaction:
    target_root: Path
    transaction_id: str
    owned_paths: list[Path] = field(default_factory=list)
    state: str = 'proposed'
    failure_code: str | None = None
    context: dict[str, object] = field(default_factory=dict)
    target_root_created: bool = False

    @property
    def recovery_path(self) -> Path:
        return self.target_root.parent / RECOVERY_DIRECTORY / f'{self.transaction_id}.json'

    def own(self, path: Path) -> None:
        resolved = path.resolve(strict=False)
        root = self.target_root.resolve(strict=False)
        if resolved != root and root not in resolved.parents:
            raise MigrationError('WB_MIGRATION_PATH_ESCAPE')
        if resolved not in self.owned_paths:
            self.owned_paths.append(resolved)

    def evidence(self, **extra: object) -> dict[str, object]:
        result: dict[str, object] = {
            'id': self.transaction_id,
            'state': self.state,
            'failure_code': self.failure_code,
            'owned_paths': [str(path) for path in sorted(self.owned_paths)],
            'metadata_status': extra.pop('metadata_status', 'pending'),
            'registry_status': extra.pop('registry_status', 'pending'),
            'updated_at': _utc_now(),
        }
        result.update(extra)
        if self.context:
            result['context'] = self.context
        return result

    def persist(self, **extra: object) -> Path:
        path = self.recovery_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.evidence(**extra)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(temporary, path)
        return path


def rollback_owned_paths(transaction: MigrationTransaction) -> dict[str, object]:
    for path in sorted(transaction.owned_paths, key=lambda value: len(value.parts), reverse=True):
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)
    root = transaction.target_root.resolve(strict=False)
    if transaction.target_root_created and root.is_dir() and not any(root.iterdir()):
        root.rmdir()
    transaction.state = 'rolled-back'
    transaction.persist(metadata_status='rolled-back', registry_status='unchanged')
    return transaction.evidence(metadata_status='rolled-back', registry_status='unchanged')


def _copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    _inventory(source)
    shutil.copytree(
        source,
        target,
        copy_function=shutil.copy2,
        symlinks=False,
        ignore=lambda _root, names: [name for name in names if name in TRANSIENT_NAMES],
        dirs_exist_ok=False,
    )


def _yaml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def _git_remote(source: Path) -> str:
    result = _run_git(source, 'remote', 'get-url', 'origin')
    return result.stdout.strip() if result.returncode == 0 else ''


def _top_level_unknown_blocks(text: str, known: set[str]) -> list[str]:
    lines = text.splitlines()
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith((' ', '#')) or ':' not in line:
            index += 1
            continue
        key = line.split(':', 1)[0]
        end = index + 1
        while end < len(lines) and (not lines[end] or lines[end].startswith((' ', '\t'))):
            end += 1
        if key not in known:
            result.append('\n'.join(lines[index:end]).rstrip())
        index = end
    return result


def _metadata_text(
    current: str,
    target: Path,
    member: dict[str, object],
    repository_id: str,
    branch: str,
    base_ref: str,
    transaction_id: str,
) -> str:
    member_root = Path(str(member['project_root'])).resolve()
    control_root = Path(str(member['git_control_root'])).resolve()
    head = _run_git(member_root, 'rev-parse', 'HEAD')
    observed_head = head.stdout.strip() if head.returncode == 0 else ''
    codegraph_present = (member_root / '.codegraph').is_dir()
    known = {
        'metadata_version', 'authority', 'workspace_root', 'workspace_mode', 'project_root',
        'industry', 'prefer_subagent', 'metadata_compatibility', 'workspace_resources',
        'language', 'operation_policy', 'source_repository_roles',
        'source_repositories', 'lifecycle_transaction', 'migration',
    }
    lines = [
        'metadata_version: 3',
        'authority: workspace-working-state',
        f'workspace_root: {_yaml_string(target.resolve())}',
        'workspace_mode: multi-repository',
        f'project_root: {_yaml_string(member_root)}',
        f'industry: {_yaml_string(repository_id)}',
        'prefer_subagent: false',
        'metadata_compatibility:',
        '  readable_versions: [2, 3]',
        '  migration_requires_explicit_apply: true',
        '  preserves_unknown_fields: true',
        'workspace_resources:',
        '  script_index:',
        '    path: script/index.yaml',
        '    status: current',
        '  credential_store:',
        '    path: credentials/credentials.yaml',
        '    status: protected',
        'operation_policy:',
        '  project_files:',
        '    allow: [read, create, update]',
        '    forbid: [delete_unknown_files, overwrite_non_empty_without_force]',
        '  git:',
        '    allow_operations: [status, diff, log, branch --show-current, rev-parse HEAD]',
        '    permissive_operations: [stage, commit, pull]',
        '    forbid_operations: [reset --hard, clean -fd, push --force]',
        'source_repository_roles:',
        '  registry: "Locator only: workspace slug/root and stable repository origin identity and locators."',
        '  project_metadata: "Working-state authority: member path, branch/HEAD observation, lifecycle transaction, operation policy, and CodeGraph state."',
        'source_repositories:',
        f'  - id: {_yaml_string(repository_id)}',
        f'    project_root: {_yaml_string(member_root)}',
        f'    origin_id: {_yaml_string(repository_id)}',
        '    checkout_kind: managed-worktree',
        f'    git_control_root: {_yaml_string(control_root)}',
        '    git_control_scope: workspace',
        f'    worktree_name: {_yaml_string(repository_id)}',
        '    git_repository: true',
        f'    expected_branch: {_yaml_string(branch)}',
        f'    base_ref: {_yaml_string(base_ref)}',
        f'    observed_head: {_yaml_string(observed_head)}',
        f'    observation_time: {_yaml_string(_utc_now())}',
        '    baseline_status: current',
        '    lifecycle_status: active',
        '    operation_policy: inherit',
        '    codegraph:',
        f'      supported: {str(codegraph_present).lower()}',
        f'      index_present: {str(codegraph_present).lower()}',
        f'      root: {_yaml_string(member_root)}',
        f"      status: {'current' if codegraph_present else 'not-indexed'}",
        '      synced_commit_id: ""',
        '      last_synced_at: ""',
        f"      reason: {'\"\"' if codegraph_present else 'no-index'}",
        'lifecycle_transaction:',
        f'  id: {_yaml_string(transaction_id)}',
        '  state: published',
        '  registry_status: published',
        '  metadata_status: published',
        'migration:',
        '  authority_owner: /wb-initialize-project',
        '  compatibility_window: metadata-v2-readable-until-explicit-v3-apply',
        '  doctor_flow: "Use /wb-initialize-project doctor for deterministic file-only repair."',
        '  migrate_flow: "Inspect/dry-run single-to-multi migration, then explicitly apply."',
    ]
    unknown = _top_level_unknown_blocks(current, known)
    if unknown:
        lines.extend([''] + unknown)
    return '\n'.join(lines).rstrip() + '\n'


def _registry_entry_lines(
    workspace_root: Path,
    workspace_slug: str,
    repository_id: str,
    repository_name: str,
    source: Path,
    additional_origins: list[dict[str, object]],
) -> list[str]:
    origins = [{
        'id': repository_id,
        'origin_path': str(source.resolve()),
        'remote': _git_remote(source),
        'git_repository': True,
    }, *additional_origins]
    lines = [
        f'  - slug: {workspace_slug}',
        f'    name: {_yaml_string(repository_name)}',
        f'    workspace_root: {_yaml_string(workspace_root.resolve())}',
        f'    work_bundle_root: {_yaml_string(workspace_root.resolve() / ".work-bundle")}',
        f'    knowledge_root: {_yaml_string(workspace_root.resolve() / ".work-bundle/knowledge")}',
        '    aliases: []',
        '    repository_origins:',
    ]
    for origin in origins:
        lines.extend([
            f"      - id: {_yaml_string(origin.get('id', ''))}",
            f"        origin_path: {_yaml_string(origin.get('origin_path', ''))}",
            f"        remote: {_yaml_string(origin.get('remote', ''))}",
            f"        git_repository: {str(bool(origin.get('git_repository', True))).lower()}",
        ])
    lines.extend([
        '    source_repositories:',
        f'      - id: {_yaml_string(repository_id)}',
        f'        path: {_yaml_string(source.resolve())}',
        '        checkout_role: truth',
        '        work_dir: false',
        f'        remote: {_yaml_string(_git_remote(source))}',
        '        git_repository: true',
        '    compatibility:',
        '      readable_project_metadata_versions: [2, 3]',
        '      source_repositories_role: locator-only',
        '    status: active',
        f'    updated_at: {_utc_now()[:10]}',
    ])
    return lines


def _registry_text(
    current: str,
    workspace_root: Path,
    workspace_slug: str,
    repository_id: str,
    repository_name: str,
    source: Path,
    additional_origins: list[dict[str, object]],
) -> str:
    lines = current.splitlines() if current.strip() else ['projects:']
    if not any(line.strip() == 'projects:' for line in lines):
        lines.extend(['', 'projects:'])
    replacement = _registry_entry_lines(
        workspace_root, workspace_slug, repository_id, repository_name, source, additional_origins
    )
    starts = [index for index, line in enumerate(lines) if line.startswith('  - slug:')]
    for position, start in enumerate(starts):
        value = lines[start].split(':', 1)[1].strip().strip('"\'')
        if value != workspace_slug:
            continue
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        return '\n'.join(lines[:start] + replacement + lines[end:]).rstrip() + '\n'
    if lines and lines[-1] != '':
        lines.append('')
    return '\n'.join(lines + replacement).rstrip() + '\n'


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish_transaction(
    transaction: MigrationTransaction,
    metadata_path: Path,
    metadata_text: str,
    registry_path: Path,
    registry_text: str,
    *,
    fail_stage: str | None = None,
) -> dict[str, object]:
    before = {
        metadata_path: metadata_path.read_bytes() if metadata_path.is_file() else None,
        registry_path: registry_path.read_bytes() if registry_path.is_file() else None,
    }
    transaction.context['publication'] = {
        'metadata_before': hashlib.sha256(before[metadata_path] or b'').hexdigest(),
        'metadata_after': hashlib.sha256(metadata_text.encode('utf-8')).hexdigest(),
        'registry_before': hashlib.sha256(before[registry_path] or b'').hexdigest(),
        'registry_after': hashlib.sha256(registry_text.encode('utf-8')).hexdigest(),
    }
    transaction.state = 'applying'
    try:
        if fail_stage == 'metadata-publication':
            raise MigrationError('WB_MIGRATION_INJECTED_METADATA_PUBLICATION_FAILURE')
        _atomic_write(metadata_path, metadata_text.encode('utf-8'))
        if fail_stage == 'registry-publication':
            raise MigrationError('WB_MIGRATION_INJECTED_REGISTRY_PUBLICATION_FAILURE')
        _atomic_write(registry_path, registry_text.encode('utf-8'))
        if metadata_path.read_text(encoding='utf-8') != metadata_text or registry_path.read_text(encoding='utf-8') != registry_text:
            raise MigrationError('WB_MIGRATION_PUBLICATION_VERIFY_FAILED')
    except Exception as exc:
        for path, payload in before.items():
            if payload is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, payload)
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError('WB_MIGRATION_PUBLICATION_FAILED') from exc
    transaction.state = 'published'
    return transaction.evidence(
        metadata_status='published',
        registry_status='published',
        publication=transaction.context['publication'],
    )


def _failure(fail_stage: str | None, current: str) -> None:
    if fail_stage == current:
        raise MigrationError(f'WB_MIGRATION_INJECTED_{current.upper().replace("-", "_")}_FAILURE')


def _published_state_valid(target: Path, registry_path: Path, workspace_slug: str) -> bool:
    metadata = target / '.work-bundle/project.yaml'
    if not metadata.is_file() or not registry_path.is_file():
        return False
    return (
        'metadata_version: 3' in metadata.read_text(encoding='utf-8')
        and 'workspace_mode: multi-repository' in metadata.read_text(encoding='utf-8')
        and f'  - slug: {workspace_slug}' in registry_path.read_text(encoding='utf-8')
    )


def _persisted_published_result(transaction: MigrationTransaction) -> dict[str, object]:
    path = transaction.recovery_path
    if not path.is_file():
        raise MigrationError('WB_MIGRATION_PUBLISHED_RECOVERY_MISSING')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError('WB_MIGRATION_PUBLISHED_RECOVERY_INVALID') from exc
    result = record.get('published_result') if isinstance(record, dict) else None
    context = record.get('context') if isinstance(record, dict) else None
    if (
        record.get('id') != transaction.transaction_id
        or record.get('state') != 'published'
        or not isinstance(context, dict)
        or not isinstance(result, dict)
        or not isinstance(result.get('transaction'), dict)
        or result['transaction'].get('id') != transaction.transaction_id
        or result['transaction'].get('context') != context
    ):
        raise MigrationError('WB_MIGRATION_PUBLISHED_RECOVERY_INCOMPLETE')
    replay = json.loads(json.dumps(result))
    replay['idempotent'] = True
    return replay


def _session_start_workspace_root(member_root: Path) -> Path:
    """Use the SessionStart resolver without invoking registry or hook IO."""
    module_path = Path(__file__).resolve().parents[2] / 'bin' / 'work-bundle-session-start.py'
    specification = importlib.util.spec_from_file_location('work_bundle_session_start_migration_check', module_path)
    if specification is None or specification.loader is None:
        raise MigrationError('WB_MIGRATION_SESSION_START_UNAVAILABLE')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return Path(module.resolve_workspace_root(member_root)).resolve()


def _member_preflight(target: Path, member: dict[str, object], branch: str) -> dict[str, object]:
    member_root = Path(str(member['project_root'])).resolve()
    branch_result = _run_git(member_root, 'branch', '--show-current')
    head_result = _run_git(member_root, 'rev-parse', 'HEAD')
    common_result = _run_git(member_root, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    actual_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ''
    observed_head = head_result.stdout.strip() if head_result.returncode == 0 else ''
    common = Path(common_result.stdout.strip()).resolve() if common_result.returncode == 0 else Path('/')
    scope_valid = (
        member_root != target.resolve()
        and target.resolve() in member_root.parents
        and common != target.resolve()
        and target.resolve() in common.parents
    )
    result = {
        'repository_id': member.get('repository_id'),
        'lifecycle_state': 'verified' if scope_valid and actual_branch == branch and observed_head else 'failed',
        'expected_branch': branch,
        'actual_branch': actual_branch,
        'branch_status': 'matched' if actual_branch == branch else 'mismatch',
        'observed_head': observed_head,
        'git_common_dir': str(common),
        'git_control_scope_valid': scope_valid,
    }
    result['passed'] = result['lifecycle_state'] == 'verified'
    return result


def verify_target_before_publish(
    target: Path,
    member: dict[str, object],
    metadata_text: str,
    registry_text: str,
    workspace_slug: str,
    repository_id: str,
    branch: str,
) -> dict[str, object]:
    member_root = Path(str(member['project_root'])).resolve()
    discovered = _session_start_workspace_root(member_root)
    preflight = _member_preflight(target, member, branch)
    credential_file = target / 'credentials' / 'credentials.yaml'
    validations = {
        'script_index': {'passed': not validate_script_index(target)},
        'credential_store': {
            'passed': (
                credential_file.is_file()
                and stat.S_IMODE(credential_file.parent.stat().st_mode) == 0o700
                and stat.S_IMODE(credential_file.stat().st_mode) == 0o600
            ),
        },
        'session_start_discovery': {
            'passed': discovered == target.resolve(),
            'workspace_root': str(discovered),
            'member_root': str(member_root),
        },
        'member_preflight': preflight,
        'metadata_candidate': {
            'passed': all(token in metadata_text for token in (
                'metadata_version: 3',
                'workspace_mode: multi-repository',
                f'  - id: {_yaml_string(repository_id)}',
                '    lifecycle_status: active',
            )),
        },
        'registry_candidate': {'passed': f'  - slug: {workspace_slug}' in registry_text},
    }
    validations['passed'] = all(
        bool(value.get('passed')) for key, value in validations.items()
        if key != 'passed' and isinstance(value, dict)
    )
    return validations


def apply_migration(
    source: Path,
    target: Path,
    repository_id: str,
    branch: str,
    base_ref: str = 'HEAD',
    *,
    origin: Path | None = None,
    workspace_slug: str | None = None,
    repository_name: str | None = None,
    additional_repository_origins: list[dict[str, object]] | None = None,
    accepted_baseline_id: str | None = None,
    registry_path: Path | None = None,
    fail_stage: str | None = None,
    retry: bool = False,
) -> dict[str, object]:
    source, target = source.resolve(), target.resolve()
    origin = (origin or source).resolve()
    slug = workspace_slug or target.name
    name = repository_name or repository_id
    if registry_path is None:
        from project import project_registry_path
        registry_path = project_registry_path()
    registry_path = registry_path.resolve()
    proposal = propose_migration(
        source,
        target,
        repository_id,
        branch,
        base_ref,
        origin=origin,
        workspace_slug=slug,
        repository_name=name,
        additional_repository_origins=additional_repository_origins,
    )
    baseline = proposal['accepted_baseline_evidence']
    if proposal['apply_requires_accepted_baseline'] and accepted_baseline_id != baseline['id']:
        raise MigrationError('WB_MIGRATION_ACCEPTED_BASELINE_REQUIRED')
    transaction_identity = (
        f'{source}:{target}:{slug}:{repository_id}'
        if origin == source
        else f'{source}:{origin}:{target}:{slug}:{repository_id}'
    )
    transaction_id = hashlib.sha256(transaction_identity.encode('utf-8')).hexdigest()[:20]
    target_preexisted = target.exists()
    transaction = MigrationTransaction(target, transaction_id, target_root_created=not target_preexisted)
    transaction.context.update({
        'source_root': str(source),
        'member_origin_root': str(origin),
        'target_root': str(target),
        'workspace_slug': slug,
        'repository_id': repository_id,
        'working_branch': branch,
        'base_ref': base_ref,
        'baseline_id': baseline['id'],
        'source_repository_dirty': baseline['source_repository_dirty'],
        'work_bundle_git_dirty': baseline['work_bundle_git_dirty'],
        'member_origin_dirty': baseline['member_origin_dirty'],
        'target_root_preexisting': target_preexisted,
        'member': {
            'lifecycle_state': 'not-started',
            'expected_branch': branch,
            'base_ref': base_ref,
            'observed_git': None,
            'verification': None,
        },
        'metadata_identity': {
            'old': None,
            'new': {'version': 3, 'workspace_root': str(target), 'workspace_mode': 'multi-repository'},
        },
        'registry_identity': {
            'old': {'workspace_slug': slug, 'published': False},
            'new': {'workspace_slug': slug, 'workspace_root': str(target), 'status': 'active'},
        },
    })
    if retry and _published_state_valid(target, registry_path, slug):
        return _persisted_published_result(transaction)
    if target.exists() and any(target.iterdir()):
        raise MigrationError('WB_MIGRATION_TARGET_NOT_EMPTY')
    source_snapshot = {
        'repository_git': source_git_state(source),
        'work_bundle_git': work_bundle_git_state(source),
        'member_origin_git': source_git_state(origin),
        'work_bundle_inventory': _preservation_inventory(source / '.work-bundle'),
        'script_inventory': _inventory(source / 'script'),
        'agents_digest': _digest(source / 'AGENTS.md') if (source / 'AGENTS.md').is_file() else None,
    }
    registry_before = registry_path.read_bytes() if registry_path.is_file() else None
    publication_complete = False
    try:
        target.mkdir(parents=True, exist_ok=True)
        work_bundle_target = target / '.work-bundle'
        transaction.own(work_bundle_target)
        _copy_tree(source / '.work-bundle', work_bundle_target)
        _failure(fail_stage, 'copy-authority')
        if not verify_copy(source, target):
            raise MigrationError('WB_MIGRATION_COPY_MISMATCH')
        if (source / 'AGENTS.md').is_file():
            agents_target = target / 'AGENTS.md'
            transaction.own(agents_target)
            shutil.copy2(source / 'AGENTS.md', agents_target)
        credentials_target = target / 'credentials'
        transaction.own(credentials_target)
        transaction.own(target / 'script')
        transaction.own(target / 'roles')
        transaction.own(target / '.gitignore')
        ensure_workspace_resources(target)
        from project import ensure_project_layout, sync_agents_managed_section
        ensure_project_layout(target)
        sync_agents_managed_section(target)
        _failure(fail_stage, 'workspace-resources')
        script_failures = validate_script_index(target)
        if script_failures:
            raise MigrationError('WB_MIGRATION_SCRIPT_INDEX_INVALID')
        control_target = target / '.work-bundle/git' / f'{repository_id}.git'
        member_target = target / repository_id
        transaction.own(control_target)
        transaction.own(member_target)
        transaction.context['member']['lifecycle_state'] = 'provisioning'
        member = provision_member(target, origin, repository_id, branch, base_ref)
        member_preflight = _member_preflight(target, member, branch)
        transaction.context['member'] = {
            'lifecycle_state': 'verified' if member_preflight['passed'] else 'failed',
            'expected_branch': branch,
            'base_ref': base_ref,
            'observed_git': {
                'branch': member_preflight['actual_branch'],
                'head': member_preflight['observed_head'],
                'git_common_dir': member_preflight['git_common_dir'],
            },
            'verification': {
                'passed': member_preflight['passed'],
                'git_control_scope_valid': member_preflight['git_control_scope_valid'],
            },
        }
        _failure(fail_stage, 'member-provision')
        current_metadata = (target / '.work-bundle/project.yaml').read_text(encoding='utf-8')
        transaction.context['metadata_identity']['old'] = {
            'version': next((line.split(':', 1)[1].strip() for line in current_metadata.splitlines() if line.startswith('metadata_version:')), ''),
            'digest': hashlib.sha256(current_metadata.encode('utf-8')).hexdigest(),
        }
        metadata_text = _metadata_text(
            current_metadata, target, member, repository_id, branch, base_ref, transaction_id
        )
        current_registry = registry_path.read_text(encoding='utf-8') if registry_path.is_file() else 'projects:\n'
        transaction.context['registry_identity']['old'] = {
            'workspace_slug': slug,
            'published': f'  - slug: {slug}' in current_registry,
            'digest': hashlib.sha256(current_registry.encode('utf-8')).hexdigest(),
        }
        registry_text = _registry_text(
            current_registry,
            target,
            slug,
            repository_id,
            name,
            origin,
            list(additional_repository_origins or []),
        )
        _failure(fail_stage, 'final-verification')
        validation_results = verify_target_before_publish(
            target, member, metadata_text, registry_text, slug, repository_id, branch
        )
        source_before_publication = {
            'repository_git': source_git_state(source),
            'work_bundle_git': work_bundle_git_state(source),
            'member_origin_git': source_git_state(origin),
            'work_bundle_inventory': _preservation_inventory(source / '.work-bundle'),
            'script_inventory': _inventory(source / 'script'),
            'agents_digest': _digest(source / 'AGENTS.md') if (source / 'AGENTS.md').is_file() else None,
        }
        validation_results['source_preservation'] = {'passed': source_before_publication == source_snapshot}
        validation_results['passed'] = bool(validation_results['passed'] and validation_results['source_preservation']['passed'])
        transaction.context['member']['verification']['target_validation_passed'] = validation_results['passed']
        if not validation_results['passed']:
            raise MigrationError('WB_MIGRATION_FINAL_VERIFICATION_FAILED')
        publication = publish_transaction(
            transaction,
            target / '.work-bundle/project.yaml',
            metadata_text,
            registry_path,
            registry_text,
            fail_stage=fail_stage,
        )
        publication_complete = True
        source_after = {
            'repository_git': source_git_state(source),
            'work_bundle_git': work_bundle_git_state(source),
            'member_origin_git': source_git_state(origin),
            'work_bundle_inventory': _preservation_inventory(source / '.work-bundle'),
            'script_inventory': _inventory(source / 'script'),
            'agents_digest': _digest(source / 'AGENTS.md') if (source / 'AGENTS.md').is_file() else None,
        }
        if source_after != source_snapshot:
            raise MigrationError('WB_MIGRATION_SOURCE_CHANGED')
        result = {
            'status': 'published',
            'source_root': str(source),
            'target_root': str(target),
            'workspace_slug': slug,
            'member': member,
            'copied_inventory_and_digests': {
                'work_bundle': _inventory_digest(source_snapshot['work_bundle_inventory']),
            },
            'skipped_sensitive_and_transient_paths': ['credentials/credentials.yaml', 'script', *sorted(TRANSIENT_NAMES)],
            'script_index_validation': 'passed',
            'agents_merge_status': (
                'managed-section-synchronized'
                if source_snapshot['agents_digest']
                else 'managed-section-created'
            ),
            'metadata_and_registry_status': {'metadata': 'published', 'registry': 'published'},
            'source_preservation_checks': {
                'repository_git': True,
                'work_bundle_git': True,
                'member_origin_git': True,
                'authority_inventory': True,
                'script_inventory': True,
                'agents': True,
            },
            'transaction': publication,
            'transaction_record': str(transaction.recovery_path),
            'validation_results': validation_results,
            'retry_or_rollback_instructions': {
                'retry': 'retry with the same accepted_baseline_id',
                'rollback': 'remove transaction-owned target paths only; preserve the recovery record',
            },
            'source_repository_git': proposal['source_repository_git'],
            'work_bundle_git': proposal['work_bundle_git'],
            'member_origin_git': proposal['member_origin_git'],
            'accepted_baseline_id': baseline['id'],
            'git_actions': [],
        }
        transaction.persist(
            metadata_status='published',
            registry_status='published',
            source_preserved=True,
            baseline_id=baseline['id'],
            published_result=result,
        )
        return result
    except Exception as exc:
        code = exc.code if isinstance(exc, MigrationError) else 'WB_MIGRATION_FAILED'
        if publication_complete:
            if registry_before is None:
                registry_path.unlink(missing_ok=True)
            else:
                _atomic_write(registry_path, registry_before)
        transaction.state = 'failed'
        transaction.failure_code = code
        rollback_owned_paths(transaction)
        transaction.state = 'failed'
        record = transaction.persist(
            metadata_status='rolled-back',
            registry_status='unchanged',
            source_preserved=(
                source_git_state(source) == source_snapshot['repository_git']
                and work_bundle_git_state(source) == source_snapshot['work_bundle_git']
                and source_git_state(origin) == source_snapshot['member_origin_git']
            ),
            baseline_id=baseline['id'],
        )
        raise MigrationError(code, record) from exc


def retry_transaction(*args: object, **kwargs: object) -> dict[str, object]:
    kwargs['retry'] = True
    return apply_migration(*args, **kwargs)
