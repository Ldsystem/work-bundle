from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core import (
    out,
    read,
    resolve_project_registry_path,
    resolve_work_bundle_root,
    utc_now_rfc3339,
    work_bundle_config_root,
    write,
)
from workspace_resources import _load_yaml


CATALOG_REFERENCE = Path('references/wb-registry-layout-migration.yaml')
CREDENTIAL_DIR_NAME = 'credentials'


class RegistryLayoutError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        slug: str = '',
        from_version: str = '',
        to_version: str = '',
        failed_step: str = '',
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.slug = slug
        self.from_version = from_version
        self.to_version = to_version
        self.failed_step = failed_step
        self.details = details or {}


@dataclass(frozen=True)
class LayoutMigrationStep:
    step_id: str
    from_version: str
    to_version: str
    owner: str


@dataclass(frozen=True)
class MigrationCatalog:
    registry_schema_current: str
    registry_schema_supported: tuple[str, ...]
    registry_schema_implicit: str
    layout_current: str
    layout_supported: tuple[str, ...]
    steps: tuple[LayoutMigrationStep, ...]


def load_migration_catalog(toolkit_root: Path | None = None) -> MigrationCatalog:
    root = toolkit_root or resolve_work_bundle_root()
    if root is None:
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_UNRESOLVED')
    path = root / CATALOG_REFERENCE
    if not path.is_file():
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_MISSING', details={'path': str(path)})
    document = _load_yaml(read(path))
    if not isinstance(document, dict):
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_INVALID')
    registry_schema = document.get('registry_schema')
    layout = document.get('layout')
    if not isinstance(registry_schema, dict) or not isinstance(layout, dict):
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_INVALID')
    raw_steps = layout.get('steps')
    if not isinstance(raw_steps, list):
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_INVALID')
    steps: list[LayoutMigrationStep] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_INVALID')
        steps.append(
            LayoutMigrationStep(
                step_id=str(item.get('id') or ''),
                from_version=_normalize_version(item.get('from')),
                to_version=_normalize_version(item.get('to')),
                owner=str(item.get('owner') or ''),
            )
        )
    if not steps or any(not step.step_id or not step.from_version or not step.to_version for step in steps):
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_CATALOG_INVALID')
    supported = tuple(_normalize_version(item) for item in layout.get('supported') or [])
    schema_supported = tuple(str(item) for item in registry_schema.get('supported') or [])
    return MigrationCatalog(
        registry_schema_current=str(registry_schema.get('current') or ''),
        registry_schema_supported=schema_supported,
        registry_schema_implicit=str(registry_schema.get('implicit_when_missing') or '1'),
        layout_current=_normalize_version(layout.get('current')),
        layout_supported=supported,
        steps=tuple(steps),
    )


def _normalize_version(value: object) -> str:
    text = str(value or '').strip().lower()
    if text.startswith('v'):
        text = text[1:]
    return text


def detect_registry_schema_version(text: str, catalog: MigrationCatalog) -> str:
    for line in text.splitlines():
        if line.startswith('registry_schema_version:'):
            return str(line.split(':', 1)[1].strip().strip('"').strip("'"))
    return catalog.registry_schema_implicit


def detect_layout_version(metadata_text: str) -> str:
    from project import _yaml_scalar
    return _normalize_version(_yaml_scalar(metadata_text, 'metadata_version'))


def migration_path(
    source_version: str,
    catalog: MigrationCatalog,
    *,
    target_version: str | None = None,
) -> list[LayoutMigrationStep] | None:
    target = target_version or catalog.layout_current
    source = _normalize_version(source_version)
    target = _normalize_version(target)
    if source == target:
        return []
    by_from = {step.from_version: step for step in catalog.steps}
    path: list[LayoutMigrationStep] = []
    current = source
    seen: set[str] = set()
    while current != target:
        if current in seen or current not in by_from:
            return None
        seen.add(current)
        step = by_from[current]
        path.append(step)
        current = step.to_version
    return path


def _workspace_root_from_entry(entry: dict[str, object]) -> Path | None:
    workspace_root = str(entry.get('workspace_root') or '').strip()
    if workspace_root:
        return Path(workspace_root).expanduser()
    work_bundle_root = str(entry.get('work_bundle_root') or '').strip()
    if work_bundle_root:
        root = Path(work_bundle_root).expanduser()
        return root.parent if root.name == '.work-bundle' else root
    sources = entry.get('source_repositories')
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict) and source.get('path'):
                return Path(str(source['path'])).expanduser()
    return None


def _metadata_digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _ignore_credentials(directory: str, names: list[str]) -> list[str]:
    ignored: list[str] = []
    if Path(directory).name == CREDENTIAL_DIR_NAME or CREDENTIAL_DIR_NAME in names:
        ignored.append(CREDENTIAL_DIR_NAME)
    return ignored


def _credential_store_exists(workspace_root: Path) -> bool:
    return (workspace_root / CREDENTIAL_DIR_NAME / 'credentials.yaml').is_file()


def _remove_created_credential_store(workspace_root: Path) -> None:
    credential_file = workspace_root / CREDENTIAL_DIR_NAME / 'credentials.yaml'
    credential_dir = workspace_root / CREDENTIAL_DIR_NAME
    if credential_file.is_file():
        credential_file.unlink()
    if credential_dir.is_dir():
        try:
            credential_dir.rmdir()
        except OSError:
            pass


def snapshot_workspace(workspace_root: Path, destination: Path) -> dict[str, object]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(workspace_root, destination, ignore=_ignore_credentials, symlinks=False)
    return {
        'workspace_root': str(workspace_root),
        'snapshot_root': str(destination),
        'credential_store_existed': _credential_store_exists(workspace_root),
    }


def restore_workspace(snapshot: dict[str, object]) -> None:
    workspace_root = Path(str(snapshot['workspace_root']))
    snapshot_root = Path(str(snapshot['snapshot_root']))
    credential_existed = bool(snapshot.get('credential_store_existed'))
    credential_dir = workspace_root / CREDENTIAL_DIR_NAME
    parked: Path | None = None
    if credential_dir.exists():
        parked = workspace_root.parent / f'.{workspace_root.name}.credentials-restore'
        if parked.exists():
            shutil.rmtree(parked)
        shutil.move(str(credential_dir), str(parked))
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    shutil.copytree(snapshot_root, workspace_root, symlinks=False)
    if parked is not None and credential_existed:
        target = workspace_root / CREDENTIAL_DIR_NAME
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(parked), str(target))
    else:
        if parked is not None and parked.exists():
            shutil.rmtree(parked)
        if not credential_existed:
            _remove_created_credential_store(workspace_root)


def _project_block_bounds(lines: list[str], slug: str) -> tuple[int, int] | None:
    start: int | None = None
    for index, line in enumerate(lines):
        if not line.startswith('  - slug:'):
            continue
        value = line.split(':', 1)[1].strip().strip('"').strip("'")
        if value == slug:
            start = index
            break
    if start is None:
        return None
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.startswith('  - '):
            break
        if line and not line.startswith((' ', '#')):
            break
        end += 1
    return start, end


def set_entry_layout_version(text: str, slug: str, version: str) -> str:
    lines = text.splitlines()
    bounds = _project_block_bounds(lines, slug)
    if bounds is None:
        raise RegistryLayoutError(
            'WB_REGISTRY_LAYOUT_ENTRY_MISSING',
            slug=slug,
            to_version=version,
            failed_step='registry-publication',
        )
    start, end = bounds
    field = f'    layout_version: {version}'
    replaced = False
    for index in range(start, end):
        if lines[index].startswith('    layout_version:'):
            lines[index] = field
            replaced = True
            break
    if not replaced:
        insert_at = start + 1
        for index in range(start, end):
            if lines[index].startswith('    status:'):
                insert_at = index
                break
        lines.insert(insert_at, field)
    return '\n'.join(lines).rstrip() + '\n'


def ensure_registry_schema_version(text: str, version: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith('registry_schema_version:'):
            lines[index] = f'registry_schema_version: {version}'
            return '\n'.join(lines).rstrip() + '\n'
    insert = [f'registry_schema_version: {version}']
    if lines and lines[0].strip():
        return '\n'.join(insert + lines).rstrip() + '\n'
    return '\n'.join(insert + lines).rstrip() + '\n'


def classify_registered_project(
    entry: dict[str, object],
    catalog: MigrationCatalog,
    *,
    registry_schema_version: str,
) -> dict[str, object]:
    slug = str(entry.get('slug') or '')
    declared_layout = _normalize_version(entry.get('layout_version'))
    workspace_root = _workspace_root_from_entry(entry)
    result: dict[str, object] = {
        'slug': slug,
        'name': str(entry.get('name') or slug),
        'workspace_root': str(workspace_root) if workspace_root is not None else '',
        'registry_schema_version': registry_schema_version,
        'declared_layout_version': declared_layout,
        'layout_version': '',
        'target_version': catalog.layout_current,
        'classification': 'missing',
        'steps': [],
        'blockers': [],
        'failure_code': '',
        'metadata_digest': '',
    }
    if workspace_root is None:
        result['failure_code'] = 'WB_REGISTRY_LAYOUT_MISSING_WORKSPACE'
        return result
    workspace_root = workspace_root.expanduser()
    if not workspace_root.exists():
        result['failure_code'] = 'WB_REGISTRY_LAYOUT_MISSING_WORKSPACE'
        return result
    metadata_path = workspace_root / '.work-bundle' / 'project.yaml'
    if not metadata_path.is_file():
        result['failure_code'] = 'WB_REGISTRY_LAYOUT_MISSING_WORKSPACE'
        return result
    metadata_text = read(metadata_path)
    layout_version = detect_layout_version(metadata_text)
    result['layout_version'] = layout_version
    result['workspace_root'] = str(workspace_root.resolve()) if workspace_root.exists() else str(workspace_root)
    result['metadata_digest'] = _metadata_digest(metadata_text)
    if layout_version not in catalog.layout_supported:
        result['classification'] = 'unsupported'
        result['failure_code'] = 'WB_REGISTRY_LAYOUT_UNSUPPORTED_VERSION'
        return result
    path = migration_path(layout_version, catalog)
    if path is None:
        result['classification'] = 'unsupported'
        result['failure_code'] = 'WB_REGISTRY_LAYOUT_UNSUPPORTED_VERSION'
        return result
    steps = [
        {
            'id': step.step_id,
            'from_version': step.from_version,
            'to_version': step.to_version,
            'owner': step.owner,
        }
        for step in path
    ]
    result['steps'] = steps
    blockers = _classify_blockers(workspace_root, metadata_text, entry, path[:1])
    if blockers:
        result['classification'] = 'blocked'
        result['blockers'] = blockers
        result['failure_code'] = str(blockers[0]['code'])
        return result
    if not steps:
        result['classification'] = 'current'
        return result
    result['classification'] = 'migratable'
    return result


def _classify_blockers(
    workspace_root: Path,
    metadata_text: str,
    entry: dict[str, object],
    path: list[LayoutMigrationStep],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    from project import assess_legacy_topology
    from control_plane import (
        ControlPlaneError,
        _proposal,
        _protected_tracked_paths,
        _source_tracks_control_plane,
    )
    for step in path:
        if step.step_id == 'layout-v2-to-v3':
            topology = assess_legacy_topology(workspace_root, metadata_text, entry)
            failure = str(topology.get('failure_code') or '')
            if failure:
                blockers.append({
                    'code': failure,
                    'step': step.step_id,
                    'required_command': str(topology.get('required_command') or ''),
                })
        elif step.step_id == 'layout-v3-to-v4':
            protected = _protected_tracked_paths(workspace_root)
            if protected:
                blockers.append({
                    'code': 'WB_CONTROL_PLANE_PROTECTED_PATH_TRACKED',
                    'step': step.step_id,
                    'required_command': 'migrate-control-plane',
                })
            if _source_tracks_control_plane(workspace_root):
                blockers.append({
                    'code': 'WB_CONTROL_PLANE_SOURCE_TRACKS_CONTROL_PLANE',
                    'step': step.step_id,
                    'required_command': 'migrate-control-plane',
                })
            try:
                _proposal(workspace_root, metadata_text)
            except ControlPlaneError as exc:
                blockers.append({
                    'code': exc.code,
                    'step': step.step_id,
                    'required_command': 'migrate-control-plane',
                })
    return blockers


def inspect_registered_projects(
    *,
    slug: str | None = None,
    catalog: MigrationCatalog | None = None,
) -> dict[str, object]:
    catalog = catalog or load_migration_catalog()
    registry_path = resolve_project_registry_path()
    if not registry_path.is_file():
        raise RegistryLayoutError('WB_REGISTRY_LAYOUT_REGISTRY_MISSING', details={'path': str(registry_path)})
    registry_text = read(registry_path)
    registry_schema_version = detect_registry_schema_version(registry_text, catalog)
    if registry_schema_version not in catalog.registry_schema_supported:
        raise RegistryLayoutError(
            'WB_REGISTRY_SCHEMA_UNSUPPORTED',
            details={'registry_schema_version': registry_schema_version},
        )
    from project import _project_blocks
    entries = _project_blocks(registry_path)
    projects = [
        classify_registered_project(entry, catalog, registry_schema_version=registry_schema_version)
        for entry in sorted(entries, key=lambda item: str(item.get('slug') or ''))
        if slug is None or str(entry.get('slug') or '') == slug
    ]
    plan = {
        'registry_path': str(registry_path),
        'registry_schema_version': registry_schema_version,
        'target_layout_version': catalog.layout_current,
        'projects': projects,
    }
    plan['plan_id'] = _plan_id(plan)
    return plan


def _plan_id(plan: dict[str, object]) -> str:
    projects = []
    for project in plan.get('projects') or []:
        if not isinstance(project, dict):
            continue
        projects.append({
            'slug': project.get('slug'),
            'classification': project.get('classification'),
            'layout_version': project.get('layout_version'),
            'declared_layout_version': project.get('declared_layout_version'),
            'metadata_digest': project.get('metadata_digest'),
            'steps': project.get('steps'),
            'failure_code': project.get('failure_code'),
            'blockers': project.get('blockers'),
        })
    payload = {
        'registry_schema_version': plan.get('registry_schema_version'),
        'target_layout_version': plan.get('target_layout_version'),
        'projects': projects,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return 'rl-' + hashlib.sha256(encoded).hexdigest()[:24]


def apply_layout_step(
    step: LayoutMigrationStep,
    workspace_root: Path,
    entry: dict[str, object],
) -> dict[str, object]:
    if step.step_id == 'layout-v2-to-v3':
        from project import apply_layout_v2_to_v3
        return apply_layout_v2_to_v3(
            workspace_root,
            name=str(entry.get('name') or entry.get('slug') or ''),
            registry_entry_data=entry,
        )
    if step.step_id == 'layout-v3-to-v4':
        from control_plane import apply_layout_v3_to_v4
        return apply_layout_v3_to_v4(workspace_root)
    raise RegistryLayoutError(
        'WB_REGISTRY_LAYOUT_STEP_UNKNOWN',
        slug=str(entry.get('slug') or ''),
        from_version=step.from_version,
        to_version=step.to_version,
        failed_step=step.step_id,
    )


def validate_layout_version(workspace_root: Path, expected_version: str) -> list[str]:
    metadata_path = workspace_root / '.work-bundle' / 'project.yaml'
    metadata_text = read(metadata_path)
    actual = detect_layout_version(metadata_text)
    if actual != _normalize_version(expected_version):
        return [f'WB_REGISTRY_LAYOUT_VERSION_MISMATCH:{actual}']
    if actual == '3':
        from project import inspect_project, project_failures
        return project_failures(inspect_project(workspace_root), strict=False, include_roles=False)
    if actual == '4':
        from control_plane import _portable_failures
        return _portable_failures(metadata_text)
    if actual == '2':
        return ['WB_REGISTRY_LAYOUT_VERSION_NOT_TARGET']
    return ['WB_REGISTRY_LAYOUT_UNSUPPORTED_VERSION']


def _diagnostic(
    *,
    slug: str,
    from_version: str,
    to_version: str,
    failed_step: str,
    code: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        'slug': slug,
        'from_version': from_version,
        'to_version': to_version,
        'failed_step': failed_step,
        'failure_code': code,
    }
    if details:
        payload['details'] = details
    return payload


def apply_registered_project(
    entry: dict[str, object],
    inspection: dict[str, object],
    catalog: MigrationCatalog,
    *,
    apply_step: Callable[[LayoutMigrationStep, Path, dict[str, object]], dict[str, object]] = apply_layout_step,
    validate: Callable[[Path, str], list[str]] = validate_layout_version,
) -> dict[str, object]:
    slug = str(inspection.get('slug') or entry.get('slug') or '')
    source_version = str(inspection.get('layout_version') or '')
    target_version = catalog.layout_current
    workspace_root = Path(str(inspection.get('workspace_root') or ''))
    classification = str(inspection.get('classification') or '')
    if classification == 'current':
        return {
            'slug': slug,
            'status': 'noop',
            'classification': 'current',
            'from_version': source_version,
            'to_version': target_version,
            'steps': [],
            'changed_files': [],
            'registry_published': False,
        }
    if classification != 'migratable':
        return {
            'slug': slug,
            'status': classification,
            'classification': classification,
            'from_version': source_version,
            'to_version': target_version,
            'steps': inspection.get('steps') or [],
            'changed_files': [],
            'registry_published': False,
            'diagnostic': _diagnostic(
                slug=slug,
                from_version=source_version,
                to_version=target_version,
                failed_step='',
                code=str(inspection.get('failure_code') or 'WB_REGISTRY_LAYOUT_BLOCKED'),
                details={'blockers': inspection.get('blockers') or []},
            ),
        }
    path = migration_path(source_version, catalog) or []
    registry_path = resolve_project_registry_path()
    registry_before = registry_path.read_bytes() if registry_path.is_file() else None
    transaction_id = f"{slug}-{utc_now_rfc3339().replace(':', '')}"
    recovery_root = work_bundle_config_root() / 'runtime' / 'registry-layout-migrations' / transaction_id
    snapshot = snapshot_workspace(workspace_root, recovery_root / 'workspace')
    applied_steps: list[dict[str, object]] = []
    changed_files: list[str] = []
    try:
        current_version = source_version
        for step in path:
            try:
                result = apply_step(step, workspace_root, entry)
            except Exception as exc:
                code = getattr(exc, 'code', None) or 'WB_REGISTRY_LAYOUT_STEP_FAILED'
                raise RegistryLayoutError(
                    str(code),
                    slug=slug,
                    from_version=source_version,
                    to_version=target_version,
                    failed_step=step.step_id,
                    details={'exception': type(exc).__name__},
                ) from exc
            failures = list(result.get('failures') or []) if isinstance(result, dict) else []
            if isinstance(result, dict) and result.get('status') not in {None, 'passed'}:
                failures = failures or [str(result.get('failure_code') or 'WB_REGISTRY_LAYOUT_STEP_FAILED')]
            if failures:
                raise RegistryLayoutError(
                    str(failures[0]),
                    slug=slug,
                    from_version=source_version,
                    to_version=target_version,
                    failed_step=step.step_id,
                    details={'failures': failures},
                )
            if isinstance(result, dict):
                changed_files.extend(str(item) for item in result.get('changed_files') or [])
            step_failures = validate(workspace_root, step.to_version)
            if step_failures:
                raise RegistryLayoutError(
                    'WB_REGISTRY_LAYOUT_VALIDATION_FAILED',
                    slug=slug,
                    from_version=source_version,
                    to_version=target_version,
                    failed_step=step.step_id,
                    details={'failures': step_failures},
                )
            current_version = step.to_version
            applied_steps.append({
                'id': step.step_id,
                'from_version': step.from_version,
                'to_version': step.to_version,
                'status': 'passed',
            })
        target_failures = validate(workspace_root, target_version)
        if target_failures or current_version != target_version:
            raise RegistryLayoutError(
                'WB_REGISTRY_LAYOUT_VALIDATION_FAILED',
                slug=slug,
                from_version=source_version,
                to_version=target_version,
                failed_step='target-validation',
                details={'failures': target_failures},
            )
        registry_text = read(registry_path)
        registry_text = set_entry_layout_version(registry_text, slug, target_version)
        registry_text = ensure_registry_schema_version(
            registry_text,
            catalog.registry_schema_current,
        )
        if write(registry_path, registry_text):
            changed_files.append(str(registry_path))
        return {
            'slug': slug,
            'status': 'passed',
            'classification': 'current',
            'from_version': source_version,
            'to_version': target_version,
            'steps': applied_steps,
            'changed_files': sorted(set(changed_files)),
            'registry_published': True,
            'transaction_id': transaction_id,
        }
    except RegistryLayoutError as exc:
        restore_workspace(snapshot)
        if registry_before is None:
            registry_path.unlink(missing_ok=True)
        else:
            registry_path.write_bytes(registry_before)
        record = {
            'transaction_id': transaction_id,
            'slug': slug,
            'from_version': source_version,
            'to_version': target_version,
            'failed_step': exc.failed_step,
            'failure_code': exc.code,
            'registry_status': 'unchanged',
            'workspace_status': 'restored',
        }
        write(recovery_root / 'record.json', json.dumps(record, indent=2, sort_keys=True) + '\n')
        return {
            'slug': slug,
            'status': 'failed',
            'classification': 'migratable',
            'from_version': source_version,
            'to_version': target_version,
            'steps': applied_steps,
            'changed_files': [],
            'registry_published': False,
            'transaction_id': transaction_id,
            'transaction_record': str(recovery_root / 'record.json'),
            'diagnostic': _diagnostic(
                slug=slug,
                from_version=source_version,
                to_version=target_version,
                failed_step=exc.failed_step,
                code=exc.code,
                details=exc.details,
            ),
        }


def migrate_registered_projects(
    *,
    dry_run: bool,
    apply: bool,
    accepted_plan_id: str | None = None,
    slug: str | None = None,
    apply_step: Callable[[LayoutMigrationStep, Path, dict[str, object]], dict[str, object]] = apply_layout_step,
    validate: Callable[[Path, str], list[str]] = validate_layout_version,
) -> dict[str, object]:
    catalog = load_migration_catalog()
    from project import _project_blocks
    plan = inspect_registered_projects(slug=slug, catalog=catalog)
    payload: dict[str, object] = {
        'command': 'migrate-registered-projects',
        'dry_run': dry_run,
        'registry_path': plan['registry_path'],
        'registry_schema_version': plan['registry_schema_version'],
        'target_layout_version': plan['target_layout_version'],
        'plan_id': plan['plan_id'],
        'projects': plan['projects'],
        'changed_files': [],
    }
    if dry_run:
        payload['status'] = 'passed'
        return payload
    if not apply:
        payload['status'] = 'issues-found'
        payload['failure_code'] = 'WB_REGISTRY_LAYOUT_EXPLICIT_ACTION_REQUIRED'
        return payload
    if accepted_plan_id != plan['plan_id']:
        payload['status'] = 'issues-found'
        payload['failure_code'] = 'WB_REGISTRY_LAYOUT_PLAN_STALE'
        return payload
    registry_path = resolve_project_registry_path()
    entries = {
        str(entry.get('slug') or ''): entry
        for entry in _project_blocks(registry_path)
    }
    results: list[dict[str, object]] = []
    changed: list[str] = []
    for inspection in plan['projects']:
        if not isinstance(inspection, dict):
            continue
        entry = entries.get(str(inspection.get('slug') or ''), {})
        result = apply_registered_project(
            entry,
            inspection,
            catalog,
            apply_step=apply_step,
            validate=validate,
        )
        results.append(result)
        changed.extend(str(item) for item in result.get('changed_files') or [])
    failed = [item for item in results if item.get('status') == 'failed']
    payload['results'] = results
    payload['changed_files'] = sorted(set(changed))
    payload['status'] = 'issues-found' if failed else 'passed'
    if failed:
        payload['failure_code'] = str((failed[0].get('diagnostic') or {}).get('failure_code') or 'WB_REGISTRY_LAYOUT_STEP_FAILED')
        payload['diagnostics'] = [item.get('diagnostic') for item in failed if item.get('diagnostic')]
    return payload


def cmd_migrate_registered_projects(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py migrate-registered-projects')
    parser.add_argument('--slug')
    parser.add_argument('--accepted-plan-id')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true')
    action.add_argument('--apply', action='store_true')
    parsed = parser.parse_args(args)
    try:
        result = migrate_registered_projects(
            dry_run=parsed.dry_run,
            apply=parsed.apply,
            accepted_plan_id=parsed.accepted_plan_id,
            slug=parsed.slug,
        )
    except RegistryLayoutError as exc:
        out({
            'command': 'migrate-registered-projects',
            'status': 'issues-found',
            'failure_code': exc.code,
            'slug': exc.slug,
            'from_version': exc.from_version,
            'to_version': exc.to_version,
            'failed_step': exc.failed_step,
            'details': exc.details,
            'changed_files': [],
        })
        return 1
    out(result)
    status = str(result.get('status') or '')
    return 0 if status == 'passed' else 1
