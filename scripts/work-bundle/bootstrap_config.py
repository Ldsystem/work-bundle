from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from core import (
    GLOBAL_BOOTSTRAP_FILE_NAME,
    LEGACY_ROOT_POINTER_FILE_NAME,
    compact_yaml_map,
    out,
    read,
    utc_now_rfc3339,
    work_bundle_config_root,
    write,
)

CANONICAL_BOOTSTRAP_VERSION = 'v1'
LEGACY_SKILL_REGISTRY = 'skills/skill-registry.yaml'
CANONICAL_SKILL_REGISTRY = 'registry/skill-registry.yaml'
BOOTSTRAP_TEMPLATE_REL = 'references/assets/template/bootstrap.yaml'


def default_toolkit_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _bootstrap_template_path(toolkit_root: Path) -> Path:
    return toolkit_root / BOOTSTRAP_TEMPLATE_REL


def _is_legacy_bootstrap(bootstrap: dict[str, str]) -> bool:
    version = bootstrap.get('bootstrap_version', '').strip()
    if version and version != CANONICAL_BOOTSTRAP_VERSION:
        return True
    if bootstrap.get('root_pointer', '').strip():
        return True
    if bootstrap.get('loading_order', '').strip():
        return True
    skill_registry = bootstrap.get('skill_registry', '')
    if '/skills/' in skill_registry.replace('\\', '/'):
        return True
    work_bundle_root = bootstrap.get('work_bundle_root', '').strip()
    return not work_bundle_root


def _resolve_legacy_root_pointer(bootstrap: dict[str, str], config_root: Path) -> Path | None:
    pointer_path_raw = bootstrap.get('root_pointer', '').strip()
    if not pointer_path_raw:
        return None
    pointer_path = Path(pointer_path_raw.replace('$work_bundle_config_root', str(config_root))).expanduser()
    if not pointer_path.is_file():
        pointer_path = config_root / LEGACY_ROOT_POINTER_FILE_NAME
    if not pointer_path.is_file():
        return None
    pointer_root = compact_yaml_map(read(pointer_path)).get('work_bundle_root', '').strip()
    if not pointer_root:
        return None
    candidate = Path(pointer_root).expanduser().resolve()
    return candidate if candidate.exists() else None


def _resolve_toolkit_root(bootstrap: dict[str, str], config_root: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    bootstrap_root = bootstrap.get('work_bundle_root', '').strip()
    if bootstrap_root:
        candidate = Path(bootstrap_root).expanduser().resolve()
        if candidate.exists():
            return candidate
    legacy = _resolve_legacy_root_pointer(bootstrap, config_root)
    if legacy is not None:
        return legacy
    return default_toolkit_root()


def _retire_legacy_root_pointer(config_root: Path) -> tuple[list[str], str | None]:
    pointer_path = config_root / LEGACY_ROOT_POINTER_FILE_NAME
    if not pointer_path.is_file():
        return [], None
    changed: list[str] = []
    archive_dir = config_root / 'archive'
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f'work-bundle-root-legacy-{utc_now_rfc3339()[:10]}.yaml'
    if write(archive_path, read(pointer_path)):
        changed.append(str(archive_path))
    pointer_path.unlink()
    changed.append(str(pointer_path))
    return changed, str(archive_path)


def _render_canonical_bootstrap(template_text: str, toolkit_root: Path) -> str:
    rendered = template_text.replace('__WORK_BUNDLE_ROOT__', str(toolkit_root.resolve()))
    if not rendered.endswith('\n'):
        rendered += '\n'
    return rendered


def migrate_work_bundle_config(
    *,
    toolkit_root: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    config_root = work_bundle_config_root()
    bootstrap_path = config_root / GLOBAL_BOOTSTRAP_FILE_NAME
    existing = compact_yaml_map(read(bootstrap_path)) if bootstrap_path.is_file() else {}
    resolved_toolkit = _resolve_toolkit_root(existing, config_root, toolkit_root)
    template_path = _bootstrap_template_path(resolved_toolkit)
    changed_files: list[str] = []
    archived_files: list[str] = []

    if not template_path.is_file():
        return {
            'status': 'failed',
            'command': 'migrate-work-bundle-config',
            'failures': ['WB_REFERENCE_ASSET_MISSING'],
            'missing_reference': str(template_path),
            'changed_files': [],
        }

    legacy = _is_legacy_bootstrap(existing) if existing else True
    canonical_text = _render_canonical_bootstrap(read(template_path), resolved_toolkit)
    canonical_map = compact_yaml_map(canonical_text)
    needs_bootstrap_write = legacy or force or read(bootstrap_path) != canonical_text

    old_skill = config_root / 'skills' / 'skill-registry.yaml'
    new_skill = config_root / 'registry' / 'skill-registry.yaml'
    needs_skill_copy = old_skill.is_file() and (not new_skill.is_file() or force)

    if not legacy and not needs_bootstrap_write and not needs_skill_copy:
        retired_changed, retired_archive = _retire_legacy_root_pointer(config_root) if not dry_run else ([], None)
        return {
            'status': 'ok',
            'command': 'migrate-work-bundle-config',
            'legacy_bootstrap': False,
            'work_bundle_config_root': str(config_root),
            'work_bundle_root': str(resolved_toolkit),
            'changed_files': retired_changed,
            'archived_files': [retired_archive] if retired_archive else [],
            'retired_root_pointer': retired_archive,
        }

    if dry_run:
        planned = []
        if needs_bootstrap_write:
            planned.append(str(bootstrap_path))
        if needs_skill_copy:
            planned.append(str(new_skill))
        return {
            'status': 'ok',
            'command': 'migrate-work-bundle-config',
            'dry_run': True,
            'legacy_bootstrap': legacy,
            'work_bundle_config_root': str(config_root),
            'work_bundle_root': str(resolved_toolkit),
            'changed_files': planned,
            'archived_files': [str(bootstrap_path)] if legacy and bootstrap_path.is_file() else [],
        }

    if legacy and bootstrap_path.is_file():
        archive_dir = config_root / 'archive'
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f'bootstrap-legacy-{utc_now_rfc3339()[:10]}.yaml'
        archive_path.write_text(bootstrap_path.read_text(encoding='utf-8'), encoding='utf-8')
        archived_files.append(str(archive_path))

    if needs_skill_copy:
        new_skill.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_skill, new_skill)
        changed_files.append(str(new_skill))

    if needs_bootstrap_write:
        if write(bootstrap_path, canonical_text):
            changed_files.append(str(bootstrap_path))

    retired_changed, retired_archive = _retire_legacy_root_pointer(config_root) if not dry_run else ([], None)
    changed_files.extend(retired_changed)
    if retired_archive:
        archived_files.append(retired_archive)

    return {
        'status': 'ok',
        'command': 'migrate-work-bundle-config',
        'legacy_bootstrap': legacy,
        'work_bundle_config_root': str(config_root),
        'work_bundle_root': str(resolved_toolkit),
        'project_registry': canonical_map.get('project_registry'),
        'skill_registry': canonical_map.get('skill_registry'),
        'changed_files': sorted(set(changed_files)),
        'archived_files': archived_files,
        'retired_root_pointer': retired_archive,
    }


def cmd_migrate_work_bundle_config(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py migrate-work-bundle-config')
    parser.add_argument('--toolkit-root', help='Explicit work-bundle toolkit installation root.')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parsed = parser.parse_args(args)
    toolkit_root = Path(parsed.toolkit_root).expanduser().resolve() if parsed.toolkit_root else None
    result = migrate_work_bundle_config(
        toolkit_root=toolkit_root,
        force=parsed.force,
        dry_run=parsed.dry_run,
    )
    out(result)
    return 0 if result.get('status') == 'ok' else 1
