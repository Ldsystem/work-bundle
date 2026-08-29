from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from core import out, read, work_bundle_config_root, write


REFERENCE_PATH = Path(__file__).resolve().parents[2] / 'references' / 'wb-violation-evidence.yaml'


class ViolationError(Exception):
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
        raise ViolationError(f'missing reference catalog: {REFERENCE_PATH}')
    catalog = {
        'statuses': _plain_yaml_list(text, 'statuses'),
        'actions': _plain_yaml_list(text, 'actions'),
        'severities': _plain_yaml_list(text, 'severities'),
        'filename': _plain_yaml_map(text, 'filename'),
    }
    if not all(catalog.values()):
        raise ViolationError(f'invalid reference catalog: {REFERENCE_PATH}')
    return catalog


def _store_root() -> Path:
    return work_bundle_config_root() / 'violation'


def _ensure_store() -> dict[str, object]:
    root = _store_root()
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
        raise ViolationError(f'invalid short-description slug: {slug}')


def _validate_date(date_value: str) -> None:
    if not re.fullmatch(r'\d{8}', date_value):
        raise ViolationError(f'invalid evidence date: {date_value}')


def _validate_evidence_id(evidence_id: str, catalog: dict[str, object]) -> None:
    filename = catalog['filename']
    assert isinstance(filename, dict)
    prefix = filename.get('prefix', 'evidence')
    parts = evidence_id.split('-', 2)
    if len(parts) != 3 or parts[0] != prefix:
        raise ViolationError(f'invalid evidence filename: {evidence_id}')
    _validate_date(parts[1])
    _validate_slug(parts[2], catalog)


def _validate_status_action(status: str, action: str | None, catalog: dict[str, object]) -> None:
    statuses = catalog['statuses']
    actions = catalog['actions']
    assert isinstance(statuses, list)
    assert isinstance(actions, list)
    if status not in statuses:
        raise ViolationError(f'invalid status: {status}')
    if action is not None and action not in actions:
        raise ViolationError(f'invalid action: {action}')
    if status == 'archived' and action is None:
        raise ViolationError('archived evidence requires --action')
    if status == 'active' and action is not None:
        raise ViolationError('active evidence must not include final --action')


def _validate_severity(severity: str, catalog: dict[str, object]) -> None:
    severities = catalog['severities']
    assert isinstance(severities, list)
    if severity not in severities:
        raise ViolationError(f'invalid severity: {severity}')


def _evidence_id(slug: str, date_value: str, catalog: dict[str, object]) -> str:
    filename = catalog['filename']
    assert isinstance(filename, dict)
    prefix = filename.get('prefix', 'evidence')
    return f'{prefix}-{date_value}-{slug}'


def _evidence_path(status: str, evidence_id: str) -> Path:
    return _store_root() / status / f'{evidence_id}.yaml'


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
            raise ViolationError(f'invalid yaml line in {path}: {raw}')
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
    except ViolationError as exc:
        errors.append(f'{path}: {exc}')
    try:
        _validate_severity(severity, catalog)
    except ViolationError as exc:
        errors.append(f'{path}: {exc}')
    if status and status != status_dir:
        errors.append(f'{path}: status {status} does not match directory {status_dir}')
    evidence = record.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        errors.append(f'{path}: evidence must be a non-empty list')
    return errors


def _load_records(catalog: dict[str, object]) -> tuple[dict[str, dict[str, object]], list[str]]:
    _ensure_store()
    records: dict[str, dict[str, object]] = {'active': {}, 'archived': {}}
    errors: list[str] = []
    for status in ['active', 'archived']:
        for path in sorted((_store_root() / status).glob('*.yaml')):
            try:
                _validate_evidence_id(path.stem, catalog)
            except ViolationError as exc:
                errors.append(f'{path}: {exc}')
            try:
                record = _parse_evidence(read(path), path)
            except ViolationError as exc:
                errors.append(str(exc))
                continue
            errors.extend(_validate_record(record, path, status, catalog))
            records[status][path.stem] = record
    return records, errors


def _build_index_data() -> dict[str, dict[str, dict[str, str]]]:
    catalog = _catalog()
    records, errors = _load_records(catalog)
    if errors:
        raise ViolationError('; '.join(errors))
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


def _write_or_collide(path: Path, content: str) -> bool:
    existing = read(path)
    if existing:
        if existing == content:
            return False
        raise ViolationError(f'evidence file collision: {path}')
    return write(path, content)


def _run(handler) -> int:
    try:
        return handler()
    except ViolationError as exc:
        out({'status': 'error', 'error': str(exc)})
        return 1


def cmd_violation_ensure_store(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py violation-ensure-store')
    parser.parse_args(argv)
    return _run(lambda: (out(_ensure_store()) or 0))


def cmd_violation_create_evidence(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py violation-create-evidence')
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


def cmd_violation_build_index(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py violation-build-index')
    parser.parse_args(argv)
    try:
        sys.stdout.write(_render_index(_build_index_data()))
        return 0
    except ViolationError as exc:
        out({'status': 'error', 'error': str(exc)})
        return 1


def cmd_violation_write_index(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py violation-write-index')
    parser.parse_args(argv)

    def handler() -> int:
        index = _build_index_data()
        content = _render_index(index)
        path = _store_root() / 'index.yaml'
        changed = write(path, content)
        out({'status': 'ok', 'path': str(path), 'changed': changed, 'active': len(index['active']), 'archived': len(index['archived'])})
        return 0

    return _run(handler)


def cmd_violation_archive_evidence(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py violation-archive-evidence')
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
            raise ViolationError(f'archived evidence collision: {archived_path}')
        if not active_path.exists():
            raise ViolationError(f'active evidence not found: {parsed.evidence}')
        record = _parse_evidence(read(active_path), active_path)
        errors = _validate_record(record, active_path, 'active', catalog)
        if errors:
            raise ViolationError('; '.join(errors))
        record['status'] = 'archived'
        record['action'] = parsed.action
        content = _render_evidence(record)
        if archived_path.exists() and read(archived_path) != content:
            raise ViolationError(f'archived evidence collision: {archived_path}')
        changed = write(archived_path, content)
        active_path.unlink()
        out({'status': 'ok', 'source_path': str(active_path), 'archived_path': str(archived_path), 'action': parsed.action, 'changed': changed})
        return 0

    return _run(handler)
