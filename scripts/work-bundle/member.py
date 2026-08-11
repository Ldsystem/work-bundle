from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from migration import _atomic_write, _member_preflight, _session_start_workspace_root
from worktree import (
    ProvisionMemberError,
    _remove_created_member,
    provision_member,
    verify_git_control_scope,
)


class MemberLifecycleError(RuntimeError):
    def __init__(self, code: str, result: dict[str, object] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.result = result or {}


def _transaction_id(
    workspace_root: Path,
    origin: Path,
    repository_id: str,
    branch: str,
    base_ref: str,
) -> str:
    value = f'{workspace_root.resolve()}:{origin.resolve()}:{repository_id}:{branch}:{base_ref}'
    return f"provision-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _record_path(workspace_root: Path, repository_id: str) -> Path:
    return workspace_root / '.work-bundle' / 'transactions' / f'provision-{repository_id}.json'


def _read_record(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemberLifecycleError('WB_MEMBER_RECOVERY_INVALID') from exc
    if not isinstance(value, dict):
        raise MemberLifecycleError('WB_MEMBER_RECOVERY_INVALID')
    return value


def _write_record(path: Path, payload: dict[str, object]) -> None:
    _atomic_write(path, (json.dumps(payload, sort_keys=True) + '\n').encode('utf-8'))


def _context_matches(record: dict[str, object], context: dict[str, object]) -> bool:
    return record.get('id') == context['transaction_id'] and record.get('context') == context


def _registry_project(
    registry_path: Path,
    workspace_root: Path,
    workspace_slug: str | None,
) -> tuple[str, dict[str, object]]:
    from project import _project_blocks

    matches: list[dict[str, object]] = []
    for project in _project_blocks(registry_path):
        slug = str(project.get('slug') or '')
        work_bundle_root = str(project.get('work_bundle_root') or '')
        registered_root = Path(work_bundle_root).expanduser().resolve().parent if work_bundle_root else None
        if workspace_slug and slug == workspace_slug:
            matches.append(project)
        elif not workspace_slug and registered_root == workspace_root.resolve():
            matches.append(project)
    if len(matches) != 1:
        raise MemberLifecycleError(
            'WB_MEMBER_WORKSPACE_REGISTRY_NOT_FOUND' if not matches else 'WB_MEMBER_WORKSPACE_REGISTRY_AMBIGUOUS'
        )
    project = matches[0]
    slug = str(project.get('slug') or '')
    if not slug:
        raise MemberLifecycleError('WB_MEMBER_WORKSPACE_SLUG_MISSING')
    work_bundle_root = str(project.get('work_bundle_root') or '')
    if work_bundle_root and Path(work_bundle_root).expanduser().resolve() != workspace_root / '.work-bundle':
        raise MemberLifecycleError('WB_MEMBER_WORKSPACE_REGISTRY_MISMATCH')
    return slug, project


def _list_bounds(lines: list[str], key: str, start: int, end: int, indent: str) -> tuple[int, int] | None:
    prefix = f'{indent}{key}:'
    for index in range(start, end):
        if lines[index].startswith(prefix):
            cursor = index + 1
            while cursor < end:
                line = lines[cursor]
                if line and not line.startswith(indent + '  '):
                    break
                cursor += 1
            return index, cursor
    return None


def _project_bounds(lines: list[str], slug: str) -> tuple[int, int]:
    starts = [index for index, line in enumerate(lines) if line.startswith('  - slug:')]
    for position, start in enumerate(starts):
        value = lines[start].split(':', 1)[1].strip().strip('"\'')
        if value == slug:
            return start, starts[position + 1] if position + 1 < len(starts) else len(lines)
    raise MemberLifecycleError('WB_MEMBER_WORKSPACE_REGISTRY_NOT_FOUND')


def _items(lines: list[str], bounds: tuple[int, int] | None) -> list[dict[str, str]]:
    if bounds is None:
        return []
    start, end = bounds
    result: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines[start + 1:end]:
        if line.startswith('      - '):
            if current is not None:
                result.append(current)
            current = {}
            item = line.strip()[2:]
            if ':' in item:
                key, value = item.split(':', 1)
                current[key.strip()] = value.strip().strip('"\'')
        elif current is not None and line.startswith('        ') and ':' in line:
            key, value = line.strip().split(':', 1)
            current[key.strip()] = value.strip().strip('"\'')
    if current is not None:
        result.append(current)
    return result


def _append_registry_item(
    lines: list[str],
    slug: str,
    key: str,
    item_lines: list[str],
) -> list[str]:
    project_start, project_end = _project_bounds(lines, slug)
    bounds = _list_bounds(lines, key, project_start, project_end, '    ')
    if bounds is None:
        insertion = next(
            (index for index in range(project_start + 1, project_end) if lines[index].startswith('    status:')),
            project_end,
        )
        return lines[:insertion] + [f'    {key}:', *item_lines] + lines[insertion:]
    start, end = bounds
    if lines[start].strip().endswith('[]'):
        replacement = [f'    {key}:', *item_lines]
        return lines[:start] + replacement + lines[start + 1:]
    return lines[:end] + item_lines + lines[end:]


def _registry_candidate(
    current: str,
    slug: str,
    origin: Path,
    repository_id: str,
) -> str:
    from project import _git_remote, _yaml_string

    lines = current.splitlines()
    project_start, project_end = _project_bounds(lines, slug)
    origins_bounds = _list_bounds(lines, 'repository_origins', project_start, project_end, '    ')
    sources_bounds = _list_bounds(lines, 'source_repositories', project_start, project_end, '    ')
    origin_items = _items(lines, origins_bounds)
    source_items = _items(lines, sources_bounds)
    expected = str(origin.resolve())
    for item in [*origin_items, *source_items]:
        if item.get('id') != repository_id:
            continue
        existing = item.get('origin_path') or item.get('path') or ''
        if existing and str(Path(existing).expanduser().resolve()) != expected:
            raise MemberLifecycleError('WB_MEMBER_REPOSITORY_ID_CONFLICT')

    if not any(item.get('id') == repository_id for item in origin_items):
        lines = _append_registry_item(lines, slug, 'repository_origins', [
            f'      - id: {_yaml_string(repository_id)}',
            f'        origin_path: {_yaml_string(origin.resolve())}',
            f'        remote: {_yaml_string(_git_remote(origin))}',
            '        git_repository: true',
        ])
    project_start, project_end = _project_bounds(lines, slug)
    sources_bounds = _list_bounds(lines, 'source_repositories', project_start, project_end, '    ')
    source_items = _items(lines, sources_bounds)
    if not any(item.get('id') == repository_id for item in source_items):
        lines = _append_registry_item(lines, slug, 'source_repositories', [
            f'      - id: {_yaml_string(repository_id)}',
            f'        path: {_yaml_string(origin.resolve())}',
            '        checkout_role: development',
            '        work_dir: false',
            f'        remote: {_yaml_string(_git_remote(origin))}',
            '        git_repository: true',
        ])
    return '\n'.join(lines).rstrip() + '\n'


def _metadata_candidate(
    current: str,
    workspace_root: Path,
    member: dict[str, object],
    repository_id: str,
    branch: str,
    base_ref: str,
    transaction_id: str,
) -> str:
    from project import (
        _git_head,
        _metadata_source_repositories,
        _replace_top_level_block,
        _yaml_block_bounds,
        _yaml_string,
        utc_now_rfc3339,
    )

    member_root = Path(str(member['project_root'])).resolve()
    control_root = Path(str(member['git_control_root'])).resolve()
    repositories = _metadata_source_repositories(current)
    for repository in repositories:
        if str(repository.get('id') or '') != repository_id:
            continue
        existing_root = Path(str(repository.get('project_root') or repository.get('path') or '')).expanduser().resolve()
        if existing_root != member_root:
            raise MemberLifecycleError('WB_MEMBER_REPOSITORY_ID_CONFLICT')
        return current

    codegraph_present = (member_root / '.codegraph').is_dir()
    entry = [
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
        f'    observed_head: {_yaml_string(_git_head(member_root))}',
        f'    observation_time: {_yaml_string(utc_now_rfc3339())}',
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
    ]
    lines = current.splitlines()
    bounds = _yaml_block_bounds(lines, 'source_repositories')
    if not bounds:
        raise MemberLifecycleError('WB_MEMBER_METADATA_SOURCES_MISSING')
    _, end = bounds
    lines = lines[:end] + entry + lines[end:]
    transaction_block = '\n'.join([
        'lifecycle_transaction:',
        f'  id: {_yaml_string(transaction_id)}',
        '  state: published',
        '  registry_status: published',
        '  metadata_status: published',
    ])
    lines, _ = _replace_top_level_block(lines, transaction_block, 'lifecycle_transaction')
    return '\n'.join(lines).rstrip() + '\n'


def _member_result(member: dict[str, object], transaction_id: str) -> dict[str, object]:
    return {
        'repository_id': member['repository_id'],
        'project_root': member['project_root'],
        'git_control_root': member['git_control_root'],
        'branch': member['branch'],
        'base_ref': member['base_ref'],
        'verification': member['verification'],
        'transaction_id': transaction_id,
    }


def _matching_checkout(
    workspace_root: Path,
    origin: Path,
    repository_id: str,
    branch: str,
    base_ref: str,
    *,
    require_base: bool,
) -> dict[str, object] | None:
    from project import _git_branch, _git_value

    target = workspace_root / repository_id
    control = workspace_root / '.work-bundle' / 'git' / f'{repository_id}.git'
    if not target.is_dir() or not control.is_dir():
        return None
    try:
        verification = verify_git_control_scope(workspace_root, target)
    except (OSError, RuntimeError):
        return None
    if not verification['valid'] or _git_branch(target) != branch:
        return None
    remote = _git_value(target, 'remote', 'get-url', 'origin')
    if remote:
        remote_path = Path(remote).expanduser()
        if remote_path.exists() and remote_path.resolve() != origin.resolve():
            return None
    if require_base:
        expected_head = _git_value(origin, 'rev-parse', base_ref)
        actual_head = _git_value(target, 'rev-parse', 'HEAD')
        if not expected_head or expected_head != actual_head:
            return None
    return {
        'repository_id': repository_id,
        'project_root': str(target),
        'git_control_root': str(control),
        'branch': branch,
        'base_ref': base_ref,
        'verification': verification,
        'git_actions': [],
    }


def provision_member_lifecycle(
    workspace_root: Path,
    origin: Path,
    repository_id: str,
    branch: str,
    base_ref: str = 'HEAD',
    *,
    workspace_slug: str | None = None,
    dry_run: bool = False,
    fail_stage: str | None = None,
) -> dict[str, object]:
    from project import (
        _metadata_failures,
        _metadata_source_repositories,
        _workspace_metadata_failures,
        _yaml_scalar,
        project_registry_path,
    )

    workspace_root = workspace_root.expanduser().resolve()
    origin = origin.expanduser().resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', repository_id):
        raise MemberLifecycleError('WB_REPOSITORY_ID_INVALID')
    metadata_path = workspace_root / '.work-bundle/project.yaml'
    registry_path = project_registry_path()
    if not metadata_path.is_file():
        raise MemberLifecycleError('WB_MEMBER_METADATA_MISSING')
    metadata_before = metadata_path.read_bytes()
    metadata_text = metadata_before.decode('utf-8')
    if _yaml_scalar(metadata_text, 'metadata_version') != '3':
        raise MemberLifecycleError('WB_MEMBER_METADATA_V3_REQUIRED')
    if _yaml_scalar(metadata_text, 'workspace_mode') != 'multi-repository':
        raise MemberLifecycleError('WB_MEMBER_MULTI_REPOSITORY_REQUIRED')
    declared_root = _yaml_scalar(metadata_text, 'workspace_root')
    if not declared_root or Path(declared_root).expanduser().resolve() != workspace_root:
        raise MemberLifecycleError('WB_MEMBER_WORKSPACE_ROOT_MISMATCH')
    if not origin.is_dir() or not (origin / '.git').exists():
        raise MemberLifecycleError('WB_MEMBER_ORIGIN_INVALID')
    slug, registry_entry = _registry_project(registry_path, workspace_root, workspace_slug)
    registry_before = registry_path.read_bytes()
    transaction_id = _transaction_id(workspace_root, origin, repository_id, branch, base_ref)
    context = {
        'transaction_id': transaction_id,
        'workspace_root': str(workspace_root),
        'workspace_slug': slug,
        'origin': str(origin),
        'repository_id': repository_id,
        'branch': branch,
        'base_ref': base_ref,
    }
    record_path = _record_path(workspace_root, repository_id)
    record = _read_record(record_path)
    target = workspace_root / repository_id
    control = workspace_root / '.work-bundle' / 'git' / f'{repository_id}.git'
    proposal = {
        'workspace_root': str(workspace_root),
        'workspace_slug': slug,
        'origin': str(origin),
        'repository_id': repository_id,
        'working_branch': branch,
        'base_ref': base_ref,
        'metadata_before_sha256': hashlib.sha256(metadata_before).hexdigest(),
        'registry_before_sha256': hashlib.sha256(registry_before).hexdigest(),
    }
    metadata_repositories = _metadata_source_repositories(metadata_text)
    for repository in metadata_repositories:
        if str(repository.get('id') or '') != repository_id:
            continue
        existing_root = Path(
            str(repository.get('project_root') or repository.get('path') or '')
        ).expanduser().resolve()
        if existing_root != target:
            raise MemberLifecycleError('WB_MEMBER_REPOSITORY_ID_CONFLICT', {'proposal': proposal})
    _registry_candidate(registry_before.decode('utf-8'), slug, origin, repository_id)
    matching_orphan = None
    if not record and target.exists() and any(target.iterdir()):
        matching_orphan = _matching_checkout(
            workspace_root, origin, repository_id, branch, base_ref, require_base=True
        )
    metadata_ids = {str(item.get('id') or '') for item in metadata_repositories}
    registry_ids = {
        str(item.get('id') or '')
        for item in registry_entry.get('source_repositories', [])
        if isinstance(item, dict)
    }
    if (
        not record
        and matching_orphan
        and repository_id in metadata_ids
        and repository_id in registry_ids
    ):
        public_member = _member_result(matching_orphan, transaction_id)
        return {
            'status': 'passed',
            'mode': 'multi-repository',
            'dry_run': dry_run,
            'idempotent': True,
            'result': {
                **public_member,
                'metadata_status': 'published',
                'registry_status': 'published',
            },
            'changed_files': [],
            'git_actions': [],
            'transaction': {
                'id': transaction_id,
                'state': 'published',
                'owned_paths': [],
                'registry_status': 'published',
                'metadata_status': 'published',
                'resume_source': 'converged-authorities',
            },
            'validation_results': {'metadata_and_registry_converged': True},
            'failures': [],
        }
    if dry_run:
        if target.exists() and any(target.iterdir()) and not (
            (record and _context_matches(record, context)) or matching_orphan
        ):
            raise MemberLifecycleError('WB_WORKTREE_TARGET_COLLISION', {'proposal': proposal})
        return {
            'status': 'proposed',
            'mode': 'multi-repository',
            'dry_run': True,
            'proposal': proposal,
            'changed_files': [],
            'git_actions': [],
            'transaction': {
                'id': transaction_id,
                'state': 'verified' if matching_orphan else 'proposed',
                'resume_source': 'verified-orphan' if matching_orphan else 'new-checkout',
                'owned_paths': [],
                'registry_status': 'pending',
                'metadata_status': 'pending',
            },
            'failures': [],
        }

    if record and record.get('state') == 'published' and _context_matches(record, context):
        member = _matching_checkout(
            workspace_root, origin, repository_id, branch, base_ref, require_base=False
        )
        published_result = record.get('published_result')
        if member is None or not isinstance(published_result, dict):
            raise MemberLifecycleError('WB_MEMBER_PUBLISHED_RECOVERY_INVALID')
        metadata_ids = {str(item.get('id') or '') for item in _metadata_source_repositories(metadata_text)}
        registry_ids = {
            str(item.get('id') or '')
            for item in registry_entry.get('source_repositories', [])
            if isinstance(item, dict)
        }
        if repository_id not in metadata_ids or repository_id not in registry_ids:
            raise MemberLifecycleError('WB_MEMBER_PUBLISHED_STATE_DIVERGED')
        replay = json.loads(json.dumps(published_result))
        replay['idempotent'] = True
        replay['changed_files'] = []
        return replay

    member = None
    checkout_owned = False
    if record and record.get('state') == 'verified' and _context_matches(record, context):
        member = _matching_checkout(
            workspace_root, origin, repository_id, branch, base_ref, require_base=True
        )
        if member is None:
            raise MemberLifecycleError('WB_MEMBER_VERIFIED_STATE_DIVERGED')
        checkout_owned = bool(record.get('checkout_owned', True))
    elif target.exists() and any(target.iterdir()):
        member = matching_orphan or _matching_checkout(
            workspace_root, origin, repository_id, branch, base_ref, require_base=True
        )
        if member is None:
            raise MemberLifecycleError('WB_WORKTREE_TARGET_COLLISION', {'proposal': proposal})
        # A checkout without a recovery record is safe to resume only after exact
        # origin/branch/base/control verification. Its paths are not claimed for
        # rollback because prior transaction ownership cannot be proven.
        checkout_owned = False

    try:
        if member is None:
            try:
                member = provision_member(workspace_root, origin, repository_id, branch, base_ref)
            except ProvisionMemberError as exc:
                raise MemberLifecycleError(exc.code, exc.result) from exc
            checkout_owned = True
        verified_record = {
            'id': transaction_id,
            'state': 'verified',
            'context': context,
            'checkout_owned': checkout_owned,
            'registry_status': 'unchanged',
            'metadata_status': 'unchanged',
            'member': _member_result(member, transaction_id),
        }
        _write_record(record_path, verified_record)
        if fail_stage == 'verified':
            raise MemberLifecycleError('WB_MEMBER_INJECTED_VERIFIED_FAILURE')

        metadata_candidate = _metadata_candidate(
            metadata_text, workspace_root, member, repository_id, branch, base_ref, transaction_id
        )
        registry_candidate = _registry_candidate(
            registry_before.decode('utf-8'), slug, origin, repository_id
        )
        member_preflight = _member_preflight(workspace_root, member, branch)
        discovery_root = _session_start_workspace_root(Path(str(member['project_root'])))
        if not member_preflight['passed'] or discovery_root != workspace_root:
            raise MemberLifecycleError('WB_MEMBER_FINAL_VERIFICATION_FAILED')
        candidate_entry = dict(registry_entry)
        candidate_sources = list(candidate_entry.get('source_repositories', []))
        if not any(
            isinstance(item, dict) and str(item.get('id') or '') == repository_id
            for item in candidate_sources
        ):
            candidate_sources.append({
                'id': repository_id,
                'path': str(origin),
                'checkout_role': 'development',
                'work_dir': False,
                'remote': '',
                'git_repository': True,
            })
        candidate_entry['source_repositories'] = candidate_sources
        candidate_failures = [
            *_metadata_failures(workspace_root, metadata_candidate, candidate_entry),
            *_workspace_metadata_failures(workspace_root, metadata_candidate),
        ]
        if candidate_failures:
            raise MemberLifecycleError('WB_MEMBER_CANDIDATE_INVALID', {'failures': candidate_failures})

        if metadata_path.read_bytes() != metadata_before or registry_path.read_bytes() != registry_before:
            raise MemberLifecycleError('WB_MEMBER_PUBLICATION_BASELINE_CHANGED')

        if fail_stage == 'metadata-publication':
            raise MemberLifecycleError('WB_MEMBER_INJECTED_METADATA_PUBLICATION_FAILURE')
        _atomic_write(metadata_path, metadata_candidate.encode('utf-8'))
        if fail_stage == 'registry-publication':
            raise MemberLifecycleError('WB_MEMBER_INJECTED_REGISTRY_PUBLICATION_FAILURE')
        _atomic_write(registry_path, registry_candidate.encode('utf-8'))
        if metadata_path.read_text(encoding='utf-8') != metadata_candidate or registry_path.read_text(encoding='utf-8') != registry_candidate:
            raise MemberLifecycleError('WB_MEMBER_PUBLICATION_VERIFY_FAILED')

        public_member = _member_result(member, transaction_id)
        result = {
            'status': 'passed',
            'mode': 'multi-repository',
            'dry_run': False,
            'result': {
                **public_member,
                'metadata_status': 'published',
                'registry_status': 'published',
            },
            'changed_files': [str(control), str(target), str(metadata_path), str(registry_path), str(record_path)],
            'git_actions': [],
            'transaction': {
                'id': transaction_id,
                'state': 'published',
                'owned_paths': [str(control), str(target), str(metadata_path), str(registry_path), str(record_path)],
                'registry_status': 'published',
                'metadata_status': 'published',
                'publication': {
                    'metadata_before': hashlib.sha256(metadata_before).hexdigest(),
                    'metadata_after': hashlib.sha256(metadata_candidate.encode('utf-8')).hexdigest(),
                    'registry_before': hashlib.sha256(registry_before).hexdigest(),
                    'registry_after': hashlib.sha256(registry_candidate.encode('utf-8')).hexdigest(),
                },
            },
            'validation_results': {
                'member_preflight': member_preflight,
                'session_start_discovery': {'passed': True, 'workspace_root': str(discovery_root)},
                'metadata_and_registry_converged': True,
            },
            'failures': [],
        }
        _write_record(record_path, {
            'id': transaction_id,
            'state': 'published',
            'context': context,
            'checkout_owned': checkout_owned,
            'registry_status': 'published',
            'metadata_status': 'published',
            'published_result': result,
        })
        return result
    except Exception as exc:
        code = exc.code if isinstance(exc, MemberLifecycleError) else 'WB_MEMBER_PUBLICATION_FAILED'
        if metadata_path.read_bytes() != metadata_before:
            _atomic_write(metadata_path, metadata_before)
        if registry_path.read_bytes() != registry_before:
            _atomic_write(registry_path, registry_before)
        rollback: dict[str, object] = {'state': 'not-required'}
        if checkout_owned and (target.exists() or control.exists()):
            rollback = _remove_created_member(
                control, target, branch,
                keep_control=False, keep_target=False, delete_branch=True,
            )
        failure_record = {
            'id': transaction_id,
            'state': 'failed',
            'context': context,
            'failure_code': code,
            'checkout_owned': checkout_owned,
            'registry_status': 'unchanged',
            'metadata_status': 'unchanged',
            'rollback': rollback,
        }
        _write_record(record_path, failure_record)
        detail = exc.result if isinstance(exc, MemberLifecycleError) else {}
        raise MemberLifecycleError(code, {**detail, 'transaction': failure_record, 'recovery_record': str(record_path)}) from exc


def cleanup_member_lifecycle(
    workspace_root: Path,
    repository_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    """Remove only a recorded, unpublished, transaction-owned checkout."""
    from project import _metadata_source_repositories

    workspace_root = workspace_root.expanduser().resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', repository_id):
        raise MemberLifecycleError('WB_REPOSITORY_ID_INVALID')
    metadata_path = workspace_root / '.work-bundle/project.yaml'
    if not metadata_path.is_file():
        raise MemberLifecycleError('WB_MEMBER_METADATA_MISSING')
    published_ids = {
        str(item.get('id') or '')
        for item in _metadata_source_repositories(metadata_path.read_text(encoding='utf-8'))
    }
    if repository_id in published_ids:
        raise MemberLifecycleError('WB_MEMBER_CLEANUP_PUBLISHED')
    record_path = _record_path(workspace_root, repository_id)
    record = _read_record(record_path)
    if not record:
        raise MemberLifecycleError('WB_MEMBER_CLEANUP_RECOVERY_MISSING')
    context = record.get('context')
    if (
        not isinstance(context, dict)
        or context.get('workspace_root') != str(workspace_root)
        or context.get('repository_id') != repository_id
        or record.get('state') not in {'verified', 'failed'}
        or record.get('checkout_owned') is not True
    ):
        raise MemberLifecycleError('WB_MEMBER_CLEANUP_NOT_OWNED')
    target = workspace_root / repository_id
    control = workspace_root / '.work-bundle' / 'git' / f'{repository_id}.git'
    branch = str(context.get('branch') or '')
    result = {
        'status': 'proposed' if dry_run else 'passed',
        'dry_run': dry_run,
        'repository_id': repository_id,
        'changed_files': [] if dry_run else [str(path) for path in (target, control) if path.exists()],
        'git_actions': [],
        'transaction': {
            'id': record.get('id'),
            'state': 'cleanup-proposed' if dry_run else 'cleaned',
            'owned_paths': [str(target), str(control)],
            'registry_status': 'unchanged',
            'metadata_status': 'unchanged',
        },
        'failures': [],
    }
    if dry_run:
        return result
    _remove_created_member(
        control, target, branch,
        keep_control=False, keep_target=False, delete_branch=True,
    )
    record['state'] = 'cleaned'
    record['cleanup'] = {'state': 'completed', 'metadata_status': 'unchanged', 'registry_status': 'unchanged'}
    _write_record(record_path, record)
    return result
