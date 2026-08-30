from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from core import out, read, work_bundle_config_root, write


REFERENCE_PATH = Path(__file__).resolve().parents[2] / 'references' / 'wb-defect-evidence.yaml'
STAGING_DIRECTORY = '.defect-migration-staging'
STAGING_OWNER_FILE = '.staging-owner'
STAGING_OWNER_CONTENT = 'work-bundle:defect-migrate-store:v1\n'
MIGRATION_MARKER_FILE = '.migration-marker.json'


class DefectError(Exception):
    pass


def _plain_yaml_list(text: str, key: str) -> list[str]:
    values: list[str] = []
    lines = text.splitlines()
    collecting = False
    for line in lines:
        if line == f'{key}:':
            collecting = True
            continue
        if collecting:
            if line and not line.startswith('  '):
                break
            stripped = line.strip()
            if stripped.startswith('- '):
                values.append(stripped[2:].strip().strip('"').strip("'"))
    return values


def _plain_yaml_map(text: str, key: str) -> dict[str, str]:
    values: dict[str, str] = {}
    lines = text.splitlines()
    collecting = False
    for line in lines:
        if line == f'{key}:':
            collecting = True
            continue
        if collecting:
            if line and not line.startswith('  '):
                break
            stripped = line.strip()
            if ':' in stripped:
                name, value = stripped.split(':', 1)
                values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def _catalog() -> dict[str, object]:
    text = read(REFERENCE_PATH)
    if not text:
        raise DefectError(f'missing reference catalog: {REFERENCE_PATH}')
    catalog = {
        'statuses': _plain_yaml_list(text, 'statuses'),
        'actions': _plain_yaml_list(text, 'actions'),
        'severities': _plain_yaml_list(text, 'severities'),
        'filename': _plain_yaml_map(text, 'filename'),
    }
    if not all(catalog.values()):
        raise DefectError(f'invalid reference catalog: {REFERENCE_PATH}')
    return catalog


def _store_root() -> Path:
    return work_bundle_config_root() / 'defect'


def _legacy_store_root() -> Path:
    return work_bundle_config_root() / 'violation'


def _staging_root() -> Path:
    return work_bundle_config_root() / STAGING_DIRECTORY


def _migration_marker(root: Path | None = None) -> Path:
    return (root or _store_root()) / MIGRATION_MARKER_FILE


def _guard_ready_store() -> None:
    legacy = _legacy_store_root()
    destination = _store_root()
    staging = _staging_root()
    if legacy.exists():
        detail = 'legacy and defect stores conflict' if destination.exists() else 'legacy violation store requires migration'
        raise DefectError(f'{detail}; run defect-migrate-store')
    if staging.exists() or _migration_marker().exists():
        raise DefectError('incomplete defect store migration; run defect-migrate-store')


def _ensure_store_at(root: Path) -> dict[str, object]:
    active = root / 'active'
    archived = root / 'archived'
    active.mkdir(parents=True, exist_ok=True)
    archived.mkdir(parents=True, exist_ok=True)
    return {
        'status': 'ok',
        'root': str(root),
        'active': str(active),
        'archived': str(archived),
    }


def _ensure_store() -> dict[str, object]:
    _guard_ready_store()
    return _ensure_store_at(_store_root())


def _quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _unquote(value: str) -> str | None:
    value = value.strip()
    if value == 'null':
        return None
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return value


def _validate_slug(slug: str, catalog: dict[str, object]) -> None:
    filename = catalog['filename']
    assert isinstance(filename, dict)
    pattern = filename.get('slug_pattern', '')
    if not re.fullmatch(pattern, slug):
        raise DefectError(f'invalid short-description slug: {slug}')


def _validate_date(date_value: str) -> None:
    if not re.fullmatch(r'\d{8}', date_value):
        raise DefectError(f'invalid evidence date: {date_value}')


def _validate_evidence_id(evidence_id: str, catalog: dict[str, object]) -> None:
    filename = catalog['filename']
    assert isinstance(filename, dict)
    prefix = filename.get('prefix', 'evidence')
    parts = evidence_id.split('-', 2)
    if len(parts) != 3 or parts[0] != prefix:
        raise DefectError(f'invalid evidence filename: {evidence_id}')
    _validate_date(parts[1])
    _validate_slug(parts[2], catalog)


def _validate_status_action(status: str, action: str | None, catalog: dict[str, object]) -> None:
    statuses = catalog['statuses']
    actions = catalog['actions']
    assert isinstance(statuses, list)
    assert isinstance(actions, list)
    if status not in statuses:
        raise DefectError(f'invalid status: {status}')
    if action is not None and action not in actions:
        raise DefectError(f'invalid action: {action}')
    if status == 'archived' and action is None:
        raise DefectError('archived evidence requires --action')
    if status == 'active' and action is not None:
        raise DefectError('active evidence must not include final --action')


def _validate_severity(severity: str, catalog: dict[str, object]) -> None:
    severities = catalog['severities']
    assert isinstance(severities, list)
    if severity not in severities:
        raise DefectError(f'invalid severity: {severity}')


def _evidence_id(slug: str, date_value: str, catalog: dict[str, object]) -> str:
    filename = catalog['filename']
    assert isinstance(filename, dict)
    prefix = filename.get('prefix', 'evidence')
    return f'{prefix}-{date_value}-{slug}'


def _evidence_path(status: str, evidence_id: str, root: Path | None = None) -> Path:
    return (root or _store_root()) / status / f'{evidence_id}.yaml'


def _evidence_item(value: str) -> dict[str, str]:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        resolved = candidate.resolve()
        try:
            rel = resolved.relative_to(Path.cwd().resolve())
            return {'path': rel.as_posix(), 'role': 'first-evidence'}
        except ValueError:
            return {'path': str(resolved), 'role': 'first-evidence'}
    return {'surface': value, 'role': 'first-evidence'}


def _render_evidence(record: dict[str, object]) -> str:
    evidence = record['evidence']
    assert isinstance(evidence, list)
    lines = [
        f'deviation: {_quote(str(record["deviation"]))}',
        f'occurrence: {_quote(str(record["occurrence"]))}',
        'evidence:',
    ]
    for item in evidence:
        assert isinstance(item, dict)
        key = 'path' if 'path' in item else 'surface'
        lines.append(f'  - {key}: {_quote(str(item[key]))}')
        lines.append(f'    role: {_quote(str(item["role"]))}')
    lines.extend([
        f'status: {record["status"]}',
        f'action: {record["action"] if record["action"] is not None else "null"}',
        f'severity: {record["severity"]}',
        '',
    ])
    return '\n'.join(lines)


def _parse_evidence(text: str, path: Path) -> dict[str, object]:
    data: dict[str, object] = {'evidence': []}
    current_item: dict[str, str] | None = None
    in_evidence = False
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if raw == 'evidence:':
            in_evidence = True
            continue
        if in_evidence and raw.startswith('  - '):
            current_item = {}
            data['evidence'].append(current_item)  # type: ignore[union-attr]
            key, value = raw[4:].split(':', 1)
            current_item[key.strip()] = str(_unquote(value))
            continue
        if in_evidence and raw.startswith('    ') and current_item is not None:
            key, value = raw.strip().split(':', 1)
            current_item[key.strip()] = str(_unquote(value))
            continue
        in_evidence = False
        if ':' not in raw:
            raise DefectError(f'invalid yaml line in {path}: {raw}')
        key, value = raw.split(':', 1)
        data[key.strip()] = _unquote(value)
    return data


def _validate_record(record: dict[str, object], path: Path, status_dir: str, catalog: dict[str, object]) -> list[str]:
    errors: list[str] = []
    required = ['deviation', 'occurrence', 'evidence', 'status', 'action', 'severity']
    for key in required:
        if key not in record:
            errors.append(f'{path}: missing {key}')
    status = str(record.get('status', ''))
    action = record.get('action')
    severity = str(record.get('severity', ''))
    try:
        _validate_status_action(status, str(action) if action is not None else None, catalog)
    except DefectError as exc:
        errors.append(f'{path}: {exc}')
    try:
        _validate_severity(severity, catalog)
    except DefectError as exc:
        errors.append(f'{path}: {exc}')
    if status and status != status_dir:
        errors.append(f'{path}: status {status} does not match directory {status_dir}')
    evidence = record.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        errors.append(f'{path}: evidence must be a non-empty list')
    return errors


def _load_records(
    catalog: dict[str, object],
    root: Path | None = None,
    *,
    create: bool = True,
) -> tuple[dict[str, dict[str, object]], list[str]]:
    target = root or _store_root()
    if create:
        if root is None:
            _ensure_store()
        else:
            _ensure_store_at(target)
    elif not target.is_dir() or not (target / 'active').is_dir() or not (target / 'archived').is_dir():
        return {'active': {}, 'archived': {}}, [f'{target}: invalid evidence store layout']
    records: dict[str, dict[str, object]] = {'active': {}, 'archived': {}}
    errors: list[str] = []
    for status in ['active', 'archived']:
        for path in sorted((target / status).glob('*.yaml')):
            try:
                _validate_evidence_id(path.stem, catalog)
            except DefectError as exc:
                errors.append(f'{path}: {exc}')
            try:
                record = _parse_evidence(read(path), path)
            except DefectError as exc:
                errors.append(str(exc))
                continue
            errors.extend(_validate_record(record, path, status, catalog))
            records[status][path.stem] = record
    return records, errors


def _build_index_data(root: Path | None = None, *, create: bool = True) -> dict[str, dict[str, dict[str, str]]]:
    catalog = _catalog()
    records, errors = _load_records(catalog, root, create=create)
    if errors:
        raise DefectError('; '.join(errors))
    index: dict[str, dict[str, dict[str, str]]] = {'active': {}, 'archived': {}}
    for evidence_id, record in records['active'].items():
        index['active'][evidence_id] = {
            'severity': str(record['severity']),
            'deviation': str(record['deviation']),
        }
    for evidence_id, record in records['archived'].items():
        index['archived'][evidence_id] = {
            'severity': str(record['severity']),
            'deviation': str(record['deviation']),
            'action': str(record['action']),
        }
    return index


def _render_index(index: dict[str, dict[str, dict[str, str]]]) -> str:
    lines: list[str] = []
    for status in ['active', 'archived']:
        lines.append(f'{status}:')
        entries = index[status]
        if not entries:
            lines.append('  {}')
            continue
        for evidence_id in sorted(entries):
            lines.append(f'  {evidence_id}:')
            entry = entries[evidence_id]
            lines.append(f'    severity: {entry["severity"]}')
            lines.append(f'    deviation: {_quote(entry["deviation"])}')
            if status == 'archived':
                lines.append(f'    action: {entry["action"]}')
    lines.append('')
    return '\n'.join(lines)


def _validate_store(root: Path) -> None:
    _build_index_data(root, create=False)


def _record_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for status in ('active', 'archived'):
        directory = root / status
        if not directory.is_dir():
            raise DefectError(f'{root}: invalid evidence store layout')
        for path in sorted(directory.glob('*.yaml')):
            digest.update(f'{status}/{path.name}'.encode('utf-8'))
            digest.update(b'\0')
            digest.update(path.read_bytes())
            digest.update(b'\n')
    return digest.hexdigest()


def _marker_content(source_fingerprint: str, destination_fingerprint: str) -> str:
    return json.dumps(
        {
            'schema_version': 1,
            'source_fingerprint': source_fingerprint,
            'destination_fingerprint': destination_fingerprint,
        },
        sort_keys=True,
        indent=2,
    ) + '\n'


def _read_marker(root: Path) -> dict[str, object]:
    marker = _migration_marker(root)
    if not marker.is_file():
        raise DefectError(f'defect store migration conflict: missing {MIGRATION_MARKER_FILE}')
    try:
        payload = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DefectError(f'invalid defect migration marker: {marker}') from exc
    source_fingerprint = payload.get('source_fingerprint') if isinstance(payload, dict) else None
    destination_fingerprint = payload.get('destination_fingerprint') if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get('schema_version') != 1
        or not isinstance(source_fingerprint, str)
        or not isinstance(destination_fingerprint, str)
        or not re.fullmatch(r'[0-9a-f]{64}', source_fingerprint)
        or not re.fullmatch(r'[0-9a-f]{64}', destination_fingerprint)
        or source_fingerprint != destination_fingerprint
    ):
        raise DefectError(f'invalid defect migration marker: {marker}')
    return payload


def _staging_is_owned(staging: Path) -> bool:
    owner = staging / STAGING_OWNER_FILE
    return owner.is_file() and owner.read_text(encoding='utf-8') == STAGING_OWNER_CONTENT


def _prepare_staging(legacy: Path, staging: Path) -> tuple[str, str]:
    if staging.exists():
        if not _staging_is_owned(staging):
            raise DefectError(f'unowned defect migration staging path: {staging}')
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    (staging / STAGING_OWNER_FILE).write_text(STAGING_OWNER_CONTENT, encoding='utf-8')
    for status in ('active', 'archived'):
        shutil.copytree(legacy / status, staging / status)
    source_fingerprint = _record_fingerprint(legacy)
    destination_fingerprint = _record_fingerprint(staging)
    if source_fingerprint != destination_fingerprint:
        raise DefectError('defect migration staging fingerprint mismatch')
    index = _build_index_data(staging, create=False)
    (staging / 'index.yaml').write_text(_render_index(index), encoding='utf-8')
    _validate_store(staging)
    _migration_marker(staging).write_text(
        _marker_content(source_fingerprint, destination_fingerprint),
        encoding='utf-8',
    )
    return source_fingerprint, destination_fingerprint


def _finalize_published_migration(legacy: Path, destination: Path) -> str:
    payload = _read_marker(destination)
    _validate_store(destination)
    destination_fingerprint = _record_fingerprint(destination)
    if destination_fingerprint != payload['destination_fingerprint']:
        raise DefectError('defect migration marker does not match destination records')
    if legacy.exists():
        _validate_store(legacy)
        source_fingerprint = _record_fingerprint(legacy)
        if source_fingerprint != payload['source_fingerprint'] or source_fingerprint != destination_fingerprint:
            raise DefectError('defect migration marker does not match legacy records')
        shutil.rmtree(legacy)
    _migration_marker(destination).unlink()
    owner = destination / STAGING_OWNER_FILE
    if owner.exists():
        owner.unlink()
    return destination_fingerprint


def _write_or_collide(path: Path, content: str) -> bool:
    existing = read(path)
    if existing:
        if existing == content:
            return False
        raise DefectError(f'evidence file collision: {path}')
    return write(path, content)


def _run(handler) -> int:
    try:
        return handler()
    except DefectError as exc:
        out({'status': 'error', 'error': str(exc)})
        return 1


def cmd_defect_migrate_store(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py defect-migrate-store')
    parser.parse_args(argv)

    def handler() -> int:
        legacy = _legacy_store_root()
        destination = _store_root()
        staging = _staging_root()
        marker = _migration_marker(destination)

        if destination.exists():
            if staging.exists():
                raise DefectError('defect store migration conflict: destination and staging both exist')
            if marker.exists():
                fingerprint = _finalize_published_migration(legacy, destination)
                out({
                    'status': 'ok',
                    'migration_status': 'migrated',
                    'root': str(destination),
                    'fingerprint': fingerprint,
                    'resumed': True,
                })
                return 0
            if legacy.exists():
                raise DefectError('defect store migration conflict: legacy and destination stores both exist')
            _validate_store(destination)
            out({'status': 'ok', 'migration_status': 'already-migrated', 'root': str(destination), 'changed': False})
            return 0

        if legacy.exists():
            _validate_store(legacy)
            _prepare_staging(legacy, staging)
            staging.rename(destination)
            fingerprint = _finalize_published_migration(legacy, destination)
            out({
                'status': 'ok',
                'migration_status': 'migrated',
                'root': str(destination),
                'fingerprint': fingerprint,
                'resumed': False,
            })
            return 0

        if staging.exists():
            raise DefectError(f'defect store migration is incomplete without legacy authority: {staging}')
        out({'status': 'ok', 'migration_status': 'no-store', 'root': str(destination), 'changed': False})
        return 0

    return _run(handler)


def cmd_defect_ensure_store(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py defect-ensure-store')
    parser.parse_args(argv)
    return _run(lambda: (out(_ensure_store()) or 0))


def cmd_defect_create_evidence(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py defect-create-evidence')
    parser.add_argument('--status', required=True)
    parser.add_argument('--short-description', required=True)
    parser.add_argument('--deviation', required=True)
    parser.add_argument('--occurrence', required=True)
    parser.add_argument('--evidence', action='append', required=True)
    parser.add_argument('--severity', required=True)
    parser.add_argument('--action')
    parsed = parser.parse_args(argv)

    def handler() -> int:
        catalog = _catalog()
        _validate_slug(parsed.short_description, catalog)
        _validate_status_action(parsed.status, parsed.action, catalog)
        _validate_severity(parsed.severity, catalog)
        _ensure_store()
        date_value = datetime.now().strftime('%Y%m%d')
        evidence_id = _evidence_id(parsed.short_description, date_value, catalog)
        path = _evidence_path(parsed.status, evidence_id)
        record = {
            'deviation': parsed.deviation,
            'occurrence': parsed.occurrence,
            'evidence': [_evidence_item(value) for value in parsed.evidence],
            'status': parsed.status,
            'action': parsed.action,
            'severity': parsed.severity,
        }
        content = _render_evidence(record)
        changed = _write_or_collide(path, content)
        out({'status': 'ok', 'path': str(path), 'id': evidence_id, 'evidence_status': parsed.status, 'changed': changed})
        return 0

    return _run(handler)


def cmd_defect_build_index(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py defect-build-index')
    parser.parse_args(argv)
    try:
        sys.stdout.write(_render_index(_build_index_data()))
        return 0
    except DefectError as exc:
        out({'status': 'error', 'error': str(exc)})
        return 1


def cmd_defect_write_index(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py defect-write-index')
    parser.parse_args(argv)

    def handler() -> int:
        index = _build_index_data()
        content = _render_index(index)
        path = _store_root() / 'index.yaml'
        changed = write(path, content)
        out({'status': 'ok', 'path': str(path), 'changed': changed, 'active': len(index['active']), 'archived': len(index['archived'])})
        return 0

    return _run(handler)


def cmd_defect_archive_evidence(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py defect-archive-evidence')
    parser.add_argument('evidence')
    parser.add_argument('--action', required=True)
    parsed = parser.parse_args(argv)

    def handler() -> int:
        catalog = _catalog()
        _validate_status_action('archived', parsed.action, catalog)
        _ensure_store()
        supplied = Path(parsed.evidence)
        evidence_id = supplied.stem if supplied.suffix == '.yaml' else parsed.evidence
        active_path = supplied if supplied.is_file() else _store_root() / 'active' / f'{evidence_id}.yaml'
        archived_path = _store_root() / 'archived' / f'{evidence_id}.yaml'
        if archived_path.exists() and not active_path.exists():
            record = _parse_evidence(read(archived_path), archived_path)
            expected = dict(record)
            expected['status'] = 'archived'
            expected['action'] = parsed.action
            content = _render_evidence(expected)
            if read(archived_path) == content:
                out({'status': 'ok', 'source_path': None, 'archived_path': str(archived_path), 'action': parsed.action, 'changed': False})
                return 0
            raise DefectError(f'archived evidence collision: {archived_path}')
        if not active_path.exists():
            raise DefectError(f'active evidence not found: {parsed.evidence}')
        record = _parse_evidence(read(active_path), active_path)
        errors = _validate_record(record, active_path, 'active', catalog)
        if errors:
            raise DefectError('; '.join(errors))
        record['status'] = 'archived'
        record['action'] = parsed.action
        content = _render_evidence(record)
        if archived_path.exists() and read(archived_path) != content:
            raise DefectError(f'archived evidence collision: {archived_path}')
        changed = write(archived_path, content)
        active_path.unlink()
        out({'status': 'ok', 'source_path': str(active_path), 'archived_path': str(archived_path), 'action': parsed.action, 'changed': changed})
        return 0

    return _run(handler)
