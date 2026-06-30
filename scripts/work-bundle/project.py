from __future__ import annotations

import hashlib
import shutil
import subprocess

from core import *

from bootstrap_config import default_toolkit_root

DIAG_REFERENCE_ASSET_MISSING = 'WB_REFERENCE_ASSET_MISSING'
INIT_TREE_MANIFEST = 'references/wb-initialize-project-default-work-bundle-tree.yaml'
INIT_WORK_BUNDLE_GITIGNORE = 'references/wb-initialize-project-default-work-bundle-gitignore'
INIT_RULE_INDEX = 'references/wb-initialize-project-default-rule-index.yaml'
INIT_PROJECT_TEMPLATE = 'references/assets/template/project.yaml'
INIT_AGENTS_TEMPLATE = 'references/assets/template/AGENTS.md'
PROJECT_REGISTRY_TEMPLATE = 'references/assets/template/projects.yaml'
AGENTS_SYNC_MANAGED_SECTION = 'work-bundle-rule'
AGENTS_SYNC_TEMPLATE_PATH = INIT_AGENTS_TEMPLATE
AGENTS_RULE_START_MARKER = '\n'.join([
    '# ========================',
    '# Work Bundle RULE START',
    '# ========================',
])
AGENTS_RULE_END_MARKER = '\n'.join([
    '# ========================',
    '# Work Bundle RULE END',
    '# ========================',
])
REQUIRED_PROJECT_GITIGNORE = ['.work-bundle/', 'AGENTS.md']
PROJECT_METADATA_REQUIRED_FIELDS = [
    'metadata_version',
    'authority',
    'project_root',
    'migration',
]
INIT_FORCE_REL_PATHS = frozenset({
    'AGENTS.md',
    '.work-bundle/project.yaml',
    'rules/index.yaml',
    '.work-bundle/knowledge/project.yaml',
})
MIGRATE_FORCE_REL_PATHS = frozenset({
    '.work-bundle/project.yaml',
})


class ReferenceAssetError(Exception):
    def __init__(self, path: str, code: str = DIAG_REFERENCE_ASSET_MISSING) -> None:
        self.path = path
        self.code = code
        super().__init__(f'{code}: {path}')


def _resolved_work_bundle_root() -> Path:
    resolved = resolve_work_bundle_root()
    if resolved and (resolved / INIT_TREE_MANIFEST).is_file():
        return resolved
    toolkit = default_toolkit_root()
    if (toolkit / INIT_TREE_MANIFEST).is_file():
        return toolkit
    if resolved:
        return resolved
    return Path.cwd().resolve()


def _require_reference_text(relative_path: str) -> str:
    path = _resolved_work_bundle_root() / relative_path
    if not path.is_file():
        raise ReferenceAssetError(str(path))
    return read(path)


def _parse_tree_roots(text: str) -> list[str]:
    roots: list[str] = []
    collecting = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped == 'roots:':
            collecting = True
            continue
        if collecting:
            if line.startswith('  - '):
                roots.append(stripped[2:].strip())
                continue
            if stripped and not line.startswith('  '):
                break
    return roots


def _init_tree_roots() -> list[str]:
    return _parse_tree_roots(_require_reference_text(INIT_TREE_MANIFEST))


def _work_bundle_relative_paths(roots: list[str], prefix: str) -> list[str]:
    marker = f'.work-bundle/{prefix}'
    return [root[len('.work-bundle/'):] for root in roots if root.startswith(marker)]


def _init_orchestration_dirs() -> list[str]:
    return _work_bundle_relative_paths(_init_tree_roots(), 'orchestration/')


def _init_knowledge_dirs() -> list[str]:
    return _work_bundle_relative_paths(_init_tree_roots(), 'knowledge/')


def _init_gitignore_patterns() -> list[str]:
    lines = []
    for raw in _require_reference_text(INIT_WORK_BUNDLE_GITIGNORE).splitlines():
        line = raw.strip()
        if line and not line.startswith('#'):
            lines.append(line)
    return lines


def _render_project_metadata(project_root: Path, name: str | None = None) -> str:
    template = _require_reference_text(INIT_PROJECT_TEMPLATE)
    slug = _slug_from_root(project_root, name)
    replacements = {
        '<absolute-path-to-project-root>': str(project_root.resolve()),
        '<industry-or-domain>': name or slug,
        '<runtime-or-framework>': 'unspecified',
        '<commit|stage|pull>': 'commit,stage,pull',
        '<push>': 'push',
        '<reset --hard>': 'reset --hard',
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered.rstrip() + '\n'


def _normalize_agents_template(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n').rstrip('\n') + '\n'


def _agents_template_text() -> str:
    return _normalize_agents_template(_require_reference_text(INIT_AGENTS_TEMPLATE))


def _agents_template_checksum(template_text: str | None = None) -> str:
    text = template_text if template_text is not None else _agents_template_text()
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _render_agents_managed_block(template_text: str | None = None) -> str:
    body = template_text if template_text is not None else _agents_template_text()
    return f'{AGENTS_RULE_START_MARKER}\n{body}{AGENTS_RULE_END_MARKER}\n'


def _managed_agents_sections(text: str) -> list[tuple[int, int, str]]:
    sections: list[tuple[int, int, str]] = []
    search_from = 0
    while True:
        start = text.find(AGENTS_RULE_START_MARKER, search_from)
        if start < 0:
            break
        body_start = start + len(AGENTS_RULE_START_MARKER)
        if text.startswith('\n', body_start):
            body_start += 1
        end_marker_start = text.find(AGENTS_RULE_END_MARKER, body_start)
        if end_marker_start < 0:
            break
        body = text[body_start:end_marker_start]
        end = end_marker_start + len(AGENTS_RULE_END_MARKER)
        if text.startswith('\n', end):
            end += 1
        sections.append((start, end, body))
        search_from = end
    return sections


def _replace_managed_agents_sections(text: str, block: str) -> str:
    sections = _managed_agents_sections(text)
    if not sections:
        return text
    rendered: list[str] = []
    previous = 0
    for index, (start, end, _) in enumerate(sections):
        rendered.append(text[previous:start])
        if index == 0:
            rendered.append(block)
        previous = end
    rendered.append(text[previous:])
    return ''.join(rendered).rstrip('\n') + '\n'


def _append_managed_agents_section(text: str, block: str) -> str:
    if not text:
        return block
    return text.rstrip('\n') + '\n\n' + block


def _replace_legacy_agents_template(text: str, template_text: str, block: str) -> tuple[str, bool]:
    if _normalize_agents_template(text) == template_text:
        return block, True
    legacy_body = template_text.rstrip('\n')
    start = text.find(legacy_body)
    if start < 0:
        return text, False
    before = text[:start].rstrip('\n')
    after = text[start + len(legacy_body):].lstrip('\n')
    parts = []
    if before:
        parts.append(before)
    parts.append(block.rstrip('\n'))
    if after.strip():
        parts.append(after.rstrip('\n'))
    return '\n\n'.join(parts).rstrip('\n') + '\n', True


def _yaml_block_bounds(lines: list[str], key: str) -> tuple[int, int] | None:
    prefix = f'{key}:'
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith(' ') and not line.startswith('\t'):
            end = index
            break
    return start, end


def _agents_sync_metadata_lines(checksum: str, status: str, synced_at: str) -> list[str]:
    return [
        'agents_sync:',
        f'  managed_section: {AGENTS_SYNC_MANAGED_SECTION}',
        f'  template_path: {AGENTS_SYNC_TEMPLATE_PATH}',
        f'  template_checksum_sha256: "{checksum}"',
        f'  last_synced_at: "{synced_at}"',
        f'  status: {status}',
    ]


def _metadata_agents_checksum(path: Path) -> str:
    lines = read(path).splitlines()
    bounds = _yaml_block_bounds(lines, 'agents_sync')
    if not bounds:
        return ''
    start, end = bounds
    for line in lines[start + 1:end]:
        stripped = line.strip()
        if stripped.startswith('template_checksum_sha256:'):
            return stripped.split(':', 1)[1].strip().strip('"').strip("'")
    return ''


def _update_project_agents_sync(project_root: Path, checksum: str, status: str) -> bool:
    path = project_root / '.work-bundle/project.yaml'
    synced_at = utc_now_rfc3339()
    replacement = _agents_sync_metadata_lines(checksum, status, synced_at)
    lines = read(path).splitlines()
    bounds = _yaml_block_bounds(lines, 'agents_sync')
    if bounds:
        start, end = bounds
        rendered_lines = lines[:start] + replacement + lines[end:]
    else:
        rendered_lines = lines + replacement
    return write(path, '\n'.join(rendered_lines).rstrip() + '\n')


def sync_agents_managed_section(project_root: Path, dry_run: bool = False, force: bool = False) -> dict[str, object]:
    agents_path = project_root / 'AGENTS.md'
    metadata_path = project_root / '.work-bundle/project.yaml'
    template_text = _agents_template_text()
    checksum = _agents_template_checksum(template_text)
    block = _render_agents_managed_block(template_text)
    existing = read(agents_path)
    sections = _managed_agents_sections(existing)
    changed_files: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    if not existing:
        next_text = block
        agents_status = 'created'
    elif not sections:
        next_text, converted_legacy = _replace_legacy_agents_template(existing, template_text, block)
        if converted_legacy:
            warnings.append('legacy-template-wrapped')
        else:
            next_text = _append_managed_agents_section(existing, block)
        agents_status = 'updated'
    else:
        section_current = len(sections) == 1 and _normalize_agents_template(sections[0][2]) == template_text
        metadata_current = _metadata_agents_checksum(metadata_path) == checksum
        if section_current and metadata_current and not force:
            next_text = existing
            agents_status = 'unchanged'
        else:
            next_text = _replace_managed_agents_sections(existing, block)
            agents_status = 'updated'
        if len(sections) > 1:
            warnings.append('multiple-managed-sections-consolidated')

    agents_changed = next_text != existing
    metadata_changed = agents_status != 'unchanged' or _metadata_agents_checksum(metadata_path) != checksum
    if agents_changed:
        changed_files.append(str(agents_path))
    if metadata_changed:
        changed_files.append(str(metadata_path))
    if not dry_run:
        if agents_changed:
            write(agents_path, next_text)
        if metadata_changed:
            _update_project_agents_sync(project_root, checksum, 'current')

    return {
        'agents_status': agents_status,
        'template_checksum_sha256': checksum,
        'changed_files': sorted(set(changed_files)),
        'warnings': warnings,
        'failures': failures,
        'dry_run': dry_run,
    }


def _ensure_lines(path: Path, lines: list[str]) -> bool:
    current = read(path).splitlines()
    changed = False
    for line in lines:
        if line not in current:
            current.append(line)
            changed = True
    if changed or not path.exists():
        write(path, '\n'.join(current).rstrip() + '\n')
    return changed


def _has_ignore(lines: list[str], wanted: str) -> bool:
    variants = {wanted, wanted.rstrip('/'), '/' + wanted.rstrip('/')}
    return any(line.strip() in variants for line in lines)


def _rel_project_path(project_root: Path, path: Path) -> str:
    return str(path.relative_to(project_root)).replace('\\', '/')


def _template_overwrite(project_root: Path, path: Path, force: bool, scope: str) -> bool:
    if not force:
        return False
    rel = _rel_project_path(project_root, path)
    allowed = INIT_FORCE_REL_PATHS if scope == 'init' else MIGRATE_FORCE_REL_PATHS
    return rel in allowed


def _cleanup_retired_bootstrap(project_root: Path) -> tuple[list[str], list[dict[str, str]], str | None]:
    bootstrap_dir = project_root / 'references/bootstrap'
    if not bootstrap_dir.exists():
        return [], [], None
    changed: list[str] = []
    retired_artifacts: list[dict[str, str]] = []
    archive_root = project_root / '.work-bundle/orchestration/docs' / f'legacy-bootstrap-archive-{utc_now_rfc3339()[:10]}'
    for path in sorted(bootstrap_dir.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(bootstrap_dir)
        rel_text = str(rel).replace('\\', '/')
        dest = archive_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if write(dest, read(path)):
            changed.append(str(dest))
        retired_artifacts.append({
            'source': _rel_project_path(project_root, path),
            'relative_path': rel_text,
            'archive_path': _rel_project_path(project_root, dest),
            'action': 'archived-and-removed',
        })
    shutil.rmtree(bootstrap_dir)
    changed.append(_rel_project_path(project_root, bootstrap_dir))
    return changed, retired_artifacts, _rel_project_path(project_root, archive_root)


def _retire_legacy_rules_contract(project_root: Path) -> tuple[list[str], dict[str, str] | None, str | None]:
    contract_path = project_root / 'rules/contract.yaml'
    if not contract_path.is_file():
        return [], None, None
    changed: list[str] = []
    source = _rel_project_path(project_root, contract_path)
    archive_root = project_root / '.work-bundle/orchestration/docs' / f'legacy-rules-contract-archive-{utc_now_rfc3339()[:10]}'
    dest = archive_root / 'contract.yaml'
    dest.parent.mkdir(parents=True, exist_ok=True)
    if write(dest, read(contract_path)):
        changed.append(str(dest))
    contract_path.unlink()
    changed.append(source)
    artifact = {
        'source': source,
        'archive_path': _rel_project_path(project_root, dest),
        'action': 'archived-and-removed',
    }
    return changed, artifact, _rel_project_path(project_root, archive_root)


def _render_bootstrap_retirement_report_section(
    retired_artifacts: list[dict[str, str]],
    archive_root: str | None,
) -> list[str]:
    if not retired_artifacts:
        return []
    lines = [
        '',
        '## Retired Legacy Bootstrap Artifacts',
        '',
        f"- archive_root: {archive_root}",
        f"- retired_count: {len(retired_artifacts)}",
        '',
    ]
    for artifact in retired_artifacts:
        lines.extend([
            f"- source: {artifact.get('source')}",
            f"  archive_path: {artifact.get('archive_path')}",
            f"  action: {artifact.get('action')}",
        ])
    return lines


def _render_rules_contract_retirement_report_section(
    artifact: dict[str, str] | None,
    archive_root: str | None,
) -> list[str]:
    if not artifact:
        return []
    return [
        '',
        '## Retired Legacy Rules Contract',
        '',
        f"- archive_root: {archive_root}",
        f"- source: {artifact.get('source')}",
        f"  archive_path: {artifact.get('archive_path')}",
        f"  action: {artifact.get('action')}",
    ]


def inspect_project(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    rules = project_root / 'rules'
    roles = project_root / 'roles'
    pgi = read(project_root / '.gitignore').splitlines()
    wbi = read(wb / '.gitignore').splitlines()
    pm = read(project_root / '.work-bundle/project.yaml')
    runtime = resolve_bootstrap_runtime()
    project_metadata_path = project_root / '.work-bundle/project.yaml'
    project_metadata_missing = [field for field in PROJECT_METADATA_REQUIRED_FIELDS if f'{field}:' not in pm]
    return {
        'project_root': str(project_root),
        'project_git': (project_root / '.git').exists(),
        'project_gitignore': (project_root / '.gitignore').exists(),
        'project_ignores_work_bundle': _has_ignore(pgi, '.work-bundle/'),
        'project_ignores_agents': _has_ignore(pgi, 'AGENTS.md'),
        'agents_md': (project_root / 'AGENTS.md').exists(),
        'work_bundle': wb.exists(),
        'work_bundle_git': (wb / '.git').exists(),
        'work_bundle_gitignore': (wb / '.gitignore').exists(),
        'work_bundle_gitignore_required_entries': all(x in wbi for x in _init_gitignore_patterns()),
        'knowledge_root': (wb / 'knowledge').exists(),
        'orchestration_root': (wb / 'orchestration').exists(),
        'orchestration_tree': all((wb / d).exists() for d in _init_orchestration_dirs()),
        'project_metadata_path': str(project_metadata_path),
        'project_metadata_exists': project_metadata_path.exists(),
        'project_metadata_required_fields_missing': project_metadata_missing,
        'project_metadata_valid': not project_metadata_missing,
        'project_metadata_authority': '.work-bundle/project.yaml',
        'rules_root': rules.exists(),
        'rule_files': len(list(rules.glob('*.yaml'))) if rules.exists() else 0,
        'rule_index': (rules / 'index.yaml').exists(),
        'roles_root': roles.exists(),
        'role_files': len(list(roles.glob('*.yaml'))) if roles.exists() else 0,
        'role_profiles': all((roles / f'{r}.yaml').exists() for r in ROLE_NAMES),
        'mdc_rules': [str(p) for p in rules.glob('**/*.mdc')] if rules.exists() else [],
        'global_registry_copied': (wb / 'skills/skill-registry.yaml').exists(),
        'project_skill_override': (wb / 'orchestration/skill-registry.override.yaml').exists(),
        'path_model': {
            'project_root': str(project_root),
            'work_bundle_root': runtime.get('resolved_work_bundle_root'),
            'work_bundle_config_root': runtime.get('work_bundle_config_root'),
        },
        'global_bootstrap_path': runtime.get('global_bootstrap_path'),
        'global_bootstrap_exists': runtime.get('global_bootstrap_exists'),
        'resolved_work_bundle_root': runtime.get('resolved_work_bundle_root'),
        'prefer_subagent': resolve_effective_prefer_subagent(project_root),
    }


def project_failures(data: dict, strict: bool = True, include_roles: bool = False) -> list[str]:
    required = ['project_gitignore', 'project_ignores_work_bundle', 'project_ignores_agents', 'agents_md', 'work_bundle', 'work_bundle_gitignore', 'knowledge_root', 'orchestration_root', 'rules_root', 'project_metadata_exists']
    if strict:
        required.extend(['work_bundle_gitignore_required_entries', 'orchestration_tree', 'rule_index', 'roles_root', 'role_profiles'])
    failures = [k for k in required if not data.get(k)]
    if not data.get('project_metadata_exists'):
        failures.append(DIAG_PROJECT_METADATA_MISSING)
    if data.get('project_metadata_exists') and data.get('project_metadata_required_fields_missing'):
        failures.append(DIAG_PROJECT_METADATA_INVALID)
    if data.get('mdc_rules'):
        failures.append('mdc_rules_present')
    if data.get('global_registry_copied'):
        failures.append('global_registry_not_copied')
    return failures


def apply_project(
    project_root: Path,
    init_git: bool = True,
    create_override: bool = False,
    name: str | None = None,
    force: bool = False,
    scope: str = 'init',
    return_details: bool = False,
) -> list[str] | tuple[list[str], dict[str, object]]:
    wb = project_root / '.work-bundle'
    knowledge = wb / 'knowledge'
    changed: list[str] = []
    tree_roots = _init_tree_roots()
    gitignore_patterns = _init_gitignore_patterns()
    if _ensure_lines(project_root / '.gitignore', REQUIRED_PROJECT_GITIGNORE):
        changed.append(str(project_root / '.gitignore'))
    for directory in tree_roots:
        path = project_root / directory
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            changed.append(str(path))
    for role in ROLE_NAMES:
        role_path = project_root / 'roles' / f'{role}.yaml'
        role_text = '\n'.join([
            f'id: {role}',
            'status: current',
            'domain_profile: .work-bundle/project.yaml',
            'duty_profile:',
            '  stance: project-specific role context must be resolved before work',
            '  skilled_at: []',
            '  quality_focus: []',
            '  must_resolve_from_context:',
            '    - project-metadata',
            '',
        ])
        if write(role_path, role_text, overwrite=False):
            changed.append(str(role_path))
    knowledge_project = knowledge / 'project.yaml'
    if write(
        knowledge_project,
        'id: project\nstatus: current\n',
        overwrite=_template_overwrite(project_root, knowledge_project, force, scope),
    ):
        changed.append(str(knowledge_project))
    if _ensure_lines(wb / '.gitignore', gitignore_patterns):
        changed.append(str(wb / '.gitignore'))
    if init_git and not (knowledge / '.git').exists():
        subprocess.run(['git', 'init', str(knowledge)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        changed.append(str(knowledge / '.git'))
    rule_index_path = project_root / 'rules/index.yaml'
    rule_index = _require_reference_text(INIT_RULE_INDEX).rstrip() + '\n'
    if write(
        rule_index_path,
        rule_index,
        overwrite=_template_overwrite(project_root, rule_index_path, force, scope),
    ):
        changed.append(str(rule_index_path))
    project_metadata_path = project_root / '.work-bundle/project.yaml'
    project_metadata = _render_project_metadata(project_root, name)
    if write(
        project_metadata_path,
        project_metadata,
        overwrite=_template_overwrite(project_root, project_metadata_path, force, scope),
    ):
        changed.append(str(project_metadata_path))
    agents_result = sync_agents_managed_section(project_root, force=force)
    changed.extend(str(path) for path in agents_result.get('changed_files', []))
    if create_override:
        path = wb / 'orchestration/skill-registry.override.yaml'
        if write(path, 'id: project-skill-registry-override\nstatus: current\noverrides: {}\n', overwrite=False):
            changed.append(str(path))
    if init_git and (knowledge / '.git').exists():
        subprocess.run(['git', '-C', str(knowledge), 'add', '.'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        has_head = subprocess.run(['git', '-C', str(knowledge), 'rev-parse', '--verify', 'HEAD'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        has_changes = subprocess.run(['git', '-C', str(knowledge), 'diff', '--cached', '--quiet'], check=False).returncode != 0
        if has_changes and not has_head:
            if subprocess.run(['git', '-C', str(knowledge), 'commit', '-m', 'chore: initialize work-bundle knowledge'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                changed.append(str(knowledge / '.git/initial-commit'))
    if (project_root / '.git').exists():
        tracked = [project_root / '.gitignore', project_root / 'AGENTS.md', project_root / '.work-bundle/project.yaml']
        subprocess.run(['git', '-C', str(project_root), 'add', '-f', *[str(path.relative_to(project_root)) for path in tracked if path.exists()]], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        has_staged = subprocess.run(['git', '-C', str(project_root), 'diff', '--cached', '--quiet'], check=False).returncode != 0
        if has_staged:
            if subprocess.run(['git', '-C', str(project_root), 'commit', '-m', 'chore: initialize work-bundle project'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                changed.append(str(project_root / '.git/work-bundle-initialization-commit'))
    changed = sorted(set(changed))
    if return_details:
        return changed, agents_result
    return changed


def repair_project(project_root: Path, force: bool = False, return_details: bool = False) -> list[str] | tuple[list[str], dict[str, object]]:
    changed, agents_result = apply_project(
        project_root,
        init_git=False,
        force=force,
        scope='init' if force else 'migrate',
        return_details=True,
    )
    data = inspect_project(project_root)
    metadata_path = project_root / '.work-bundle/project.yaml'
    if data.get('project_metadata_required_fields_missing') and (force or not read(metadata_path).strip()):
        rendered = _render_project_metadata(project_root)
        if write(metadata_path, rendered, overwrite=force):
            changed.append(str(metadata_path))
    contract_changed, _, _ = _retire_legacy_rules_contract(project_root)
    changed.extend(contract_changed)
    if force:
        bootstrap_changed, _, _ = _cleanup_retired_bootstrap(project_root)
        changed.extend(bootstrap_changed)
    changed = sorted(set(changed))
    if return_details:
        return changed, agents_result
    return changed


def _slug_from_root(project_root: Path, name: str | None = None) -> str:
    raw = name or project_root.name or "project"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip().lower()).strip("-")
    return slug or "project"


def _bootstrap_value(key: str, default: str) -> str:
    config_root = work_bundle_config_root()
    bootstrap = compact_yaml_map(read(config_root / GLOBAL_BOOTSTRAP_FILE_NAME))
    value = bootstrap.get(key, default)
    return value.replace("$work_bundle_config_root", str(config_root))


def project_registry_path() -> Path:
    return Path(_bootstrap_value("project_registry", "$work_bundle_config_root/registry/projects.yaml")).expanduser().resolve()


def _set_yaml_scalar(path: Path, key: str, value: str) -> bool:
    lines = read(path).splitlines()
    rendered: list[str] = []
    new_line = f'{key}: {value}'
    replaced = False
    changed = False
    for line in lines:
        if line.strip().startswith(f'{key}:'):
            replaced = True
            rendered.append(new_line)
            if line != new_line:
                changed = True
            continue
        rendered.append(line)
    if not replaced:
        rendered.append(new_line)
        changed = True
    if changed or not path.exists():
        write(path, '\n'.join(rendered).rstrip() + '\n')
    return changed


def set_prefer_subagent(project_root: Path, scope: str, enabled: bool) -> tuple[Path, bool]:
    value = 'true' if enabled else 'false'
    if scope == 'global':
        path = work_bundle_config_root() / GLOBAL_BOOTSTRAP_FILE_NAME
    elif scope == 'project':
        path = project_metadata_path(project_root)
    else:
        raise ValueError(f'unsupported prefer_subagent scope: {scope}')
    return path, _set_yaml_scalar(path, 'prefer_subagent', value)


def _project_blocks(path: Path) -> list[dict[str, object]]:
    text = read(path)
    projects: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_list: str | None = None
    current_repo: dict[str, object] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "projects:":
            continue
        if line.startswith("  - "):
            if current is not None:
                projects.append(current)
            current = {}
            current_list = None
            current_repo = None
            key, value = stripped[2:].split(":", 1)
            current[key.strip()] = value.strip().strip('"')
            continue
        if current is None:
            continue
        if stripped.startswith("- ") and current_list:
            item = stripped[2:].strip()
            if current_list == "aliases":
                current.setdefault("aliases", []).append(item)
            elif current_list == "source_repositories":
                current_repo = {}
                current.setdefault("source_repositories", []).append(current_repo)
                if ":" in item:
                    key, value = item.split(":", 1)
                    current_repo[key.strip()] = value.strip().strip('"')
            continue
        if line.startswith("    ") and not line.startswith("      "):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_list = None
            current_repo = None
            if value == "":
                if key in {"aliases", "source_repositories"}:
                    current[key] = []
                    current_list = key
                else:
                    current[key] = {}
            elif value == "[]":
                current[key] = []
            else:
                current[key] = value.strip('"')
            continue
        if line.startswith("      ") and current_repo is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"')
            if value in {"true", "false"}:
                current_repo[key.strip()] = value == "true"
            else:
                current_repo[key.strip()] = value
    if current is not None:
        projects.append(current)
    return projects


def _render_projects(projects: list[dict[str, object]]) -> str:
    lines = ["projects:"]
    for project in sorted(projects, key=lambda item: str(item.get("slug", ""))):
        lines.append(f"  - slug: {project.get('slug', '')}")
        lines.append(f"    name: {project.get('name', project.get('slug', ''))}")
        lines.append(f"    work_bundle_root: {project.get('work_bundle_root', '')}")
        lines.append(f"    knowledge_root: {project.get('knowledge_root', '')}")
        aliases = project.get("aliases") if isinstance(project.get("aliases"), list) else []
        if aliases:
            lines.append("    aliases:")
            for alias in aliases:
                lines.append(f"      - {alias}")
        else:
            lines.append("    aliases: []")
        sources = project.get("source_repositories") if isinstance(project.get("source_repositories"), list) else []
        lines.append("    source_repositories:")
        for index, source in enumerate(sources or [{"path": project.get("project_root", ""), "work_dir": True, "remote": ""}]):
            if not isinstance(source, dict):
                continue
            lines.append(f"      - path: {source.get('path', '')}")
            lines.append(f"        work_dir: {str(bool(source.get('work_dir', index == 0))).lower()}")
            remote = str(source.get("remote", ""))
            lines.append(f'        remote: "{remote}"' if remote else '        remote: ""')
        lines.append(f"    status: {project.get('status', 'active')}")
        lines.append(f"    updated_at: {project.get('updated_at', utc_now_rfc3339()[:10])}")
    return "\n".join(lines) + "\n"


def _project_registry_template_text() -> str:
    path = _resolved_work_bundle_root() / PROJECT_REGISTRY_TEMPLATE
    if path.is_file():
        text = read(path)
        return text if text.endswith("\n") else text + "\n"
    return "projects: []\n"


def _normalize_registry_path(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return str(Path(raw).expanduser().resolve())


def _normalize_source_repositories(sources: object) -> list[tuple[str, bool, str]]:
    if not isinstance(sources, list):
        return []
    normalized: list[tuple[str, bool, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        raw_path = source.get("path")
        path = str(Path(str(raw_path)).expanduser().resolve()) if raw_path else ""
        normalized.append((path, bool(source.get("work_dir")), str(source.get("remote", ""))))
    return sorted(normalized)


def _registry_entries_equivalent(left: dict[str, object], right: dict[str, object]) -> bool:
    for key in ("slug", "name", "status"):
        if str(left.get(key, "")) != str(right.get(key, "")):
            return False
    for key in ("work_bundle_root", "knowledge_root"):
        if _normalize_registry_path(left.get(key)) != _normalize_registry_path(right.get(key)):
            return False
    left_aliases = left.get("aliases") if isinstance(left.get("aliases"), list) else []
    right_aliases = right.get("aliases") if isinstance(right.get("aliases"), list) else []
    if left_aliases != right_aliases:
        return False
    return _normalize_source_repositories(left.get("source_repositories")) == _normalize_source_repositories(
        right.get("source_repositories")
    )


def _merge_registry_entry(
    existing: dict[str, object],
    incoming: dict[str, object],
    *,
    aliases: list[str] | None,
    source_repositories: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], bool]:
    merged: dict[str, object] = {
        "slug": incoming.get("slug", existing.get("slug")),
        "name": incoming.get("name", existing.get("name")),
        "work_bundle_root": incoming.get("work_bundle_root", existing.get("work_bundle_root")),
        "knowledge_root": incoming.get("knowledge_root", existing.get("knowledge_root")),
        "status": existing.get("status", incoming.get("status", "active")),
        "updated_at": existing.get("updated_at", incoming.get("updated_at")),
    }
    if aliases is None:
        existing_aliases = existing.get("aliases")
        merged["aliases"] = list(existing_aliases) if isinstance(existing_aliases, list) else incoming.get("aliases", [])
    else:
        merged["aliases"] = aliases
    if source_repositories is None:
        existing_sources = existing.get("source_repositories")
        if isinstance(existing_sources, list) and existing_sources:
            merged["source_repositories"] = existing_sources
        else:
            merged["source_repositories"] = incoming.get("source_repositories", [])
    else:
        merged["source_repositories"] = source_repositories
    changed = not _registry_entries_equivalent(existing, merged)
    if changed:
        merged["updated_at"] = utc_now_rfc3339()[:10]
    return merged, changed


def registry_entry(project_root: Path, name: str | None = None, aliases: list[str] | None = None) -> dict[str, object]:
    resolved = project_root.expanduser().resolve()
    slug = _slug_from_root(resolved, name)
    return {
        "slug": slug,
        "name": name or slug,
        "work_bundle_root": str(resolved / ".work-bundle"),
        "knowledge_root": str(resolved / ".work-bundle" / "knowledge"),
        "aliases": aliases if aliases is not None else [],
        "source_repositories": [{"path": str(resolved), "work_dir": True, "remote": ""}],
        "status": "active",
        "updated_at": utc_now_rfc3339()[:10],
    }


def upsert_project_registry(
    project_root: Path,
    name: str | None = None,
    aliases: list[str] | None = None,
    source_repositories: list[dict[str, object]] | None = None,
) -> tuple[dict[str, object], bool, Path]:
    path = project_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write(path, _project_registry_template_text())
    projects = _project_blocks(path)
    incoming = registry_entry(project_root, name, aliases if aliases is not None else None)
    entry = incoming
    changed = False
    replaced = False
    next_projects: list[dict[str, object]] = []
    resolved_root = str(project_root.resolve())
    for project in projects:
        sources = project.get("source_repositories")
        source_paths = [
            str(Path(str(source.get("path", ""))).expanduser().resolve())
            for source in sources
            if isinstance(sources, list) for source in sources if isinstance(source, dict) and source.get("path")
        ] if isinstance(sources, list) else []
        same_slug = project.get("slug") == incoming["slug"]
        same_root = (
            resolved_root in source_paths
            or _normalize_registry_path(project.get("work_bundle_root")) == _normalize_registry_path(incoming["work_bundle_root"])
        )
        if same_slug or same_root:
            entry, entry_changed = _merge_registry_entry(
                project,
                incoming,
                aliases=aliases,
                source_repositories=source_repositories,
            )
            next_projects.append(entry)
            replaced = True
            changed = changed or entry_changed
        else:
            next_projects.append(project)
    if not replaced:
        next_projects.append(incoming)
        entry = incoming
        changed = True
    rendered = _render_projects(next_projects)
    if read(path) != rendered:
        write(path, rendered)
        changed = True
    return entry, changed, path


def find_registry_entry(project_root: Path) -> tuple[dict[str, object] | None, Path]:
    path = project_registry_path()
    target = str(project_root.resolve())
    for project in _project_blocks(path):
        if project.get("work_bundle_root") == str(project_root / ".work-bundle"):
            return project, path
        sources = project.get("source_repositories")
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict) and source.get("path"):
                    if str(Path(str(source["path"])).expanduser().resolve()) == target:
                        return project, path
    return None, path


def list_project_registry() -> tuple[list[dict[str, object]], Path]:
    path = project_registry_path()
    return _project_blocks(path), path


def remove_project_registry(project: str) -> tuple[bool, Path]:
    path = project_registry_path()
    projects = _project_blocks(path)
    kept: list[dict[str, object]] = []
    removed = False
    for entry in projects:
        aliases = entry.get("aliases")
        alias_match = isinstance(aliases, list) and project in aliases
        if entry.get("slug") == project or alias_match:
            removed = True
            continue
        kept.append(entry)
    if removed:
        write(path, _render_projects(kept))
    return removed, path


def project_registry_issues() -> list[str]:
    projects, path = list_project_registry()
    if not path.exists():
        return [f"missing registry file: {path}"]
    issues: list[str] = []
    seen: set[str] = set()
    for entry in projects:
        slug = str(entry.get("slug", ""))
        if not slug:
            issues.append("project entry missing slug")
            continue
        if slug in seen:
            issues.append(f"duplicate slug {slug}")
        seen.add(slug)
        for key in ["work_bundle_root", "knowledge_root"]:
            if not entry.get(key):
                issues.append(f"missing {key}: {slug}")
    return issues


def _reference_failure_payload(exc: ReferenceAssetError, command: str) -> dict[str, object]:
    return {
        'command': command,
        'status': 'issues-found',
        'failures': [exc.code],
        'missing_reference': exc.path,
    }


def _agents_sync_output(result: dict[str, object]) -> dict[str, object]:
    return {
        'status': result.get('agents_status'),
        'template_checksum_sha256': result.get('template_checksum_sha256'),
        'changed_files': result.get('changed_files', []),
        'warnings': result.get('warnings', []),
        'failures': result.get('failures', []),
        'dry_run': result.get('dry_run', False),
    }


def _session_start_warning(reason: str, project_root: Path) -> str:
    return f'{reason}; run wb-initialize-project migrate for current workspace: {project_root}'


def _session_start_payload(project_root: Path) -> dict[str, object]:
    runtime = resolve_bootstrap_runtime()
    bootstrap_path = Path(str(runtime.get('global_bootstrap_path')))
    work_bundle_root = runtime.get('resolved_work_bundle_root')
    registry_path = project_registry_path() if bootstrap_path.is_file() else work_bundle_config_root() / 'registry/projects.yaml'
    metadata_path = project_root / '.work-bundle/project.yaml'
    agents_path = project_root / 'AGENTS.md'
    return {
        'command': 'session-start',
        'status': 'skipped',
        'project_root': str(project_root),
        'bootstrap_path': str(bootstrap_path),
        'work_bundle_root': work_bundle_root,
        'registry_path': str(registry_path),
        'registry_status': 'missing' if not registry_path.is_file() else 'not-registered',
        'project_metadata_path': str(metadata_path),
        'project_metadata_status': 'present' if metadata_path.is_file() else 'missing',
        'project_agents_checksum': 'missing',
        'agents_path': str(agents_path),
        'agents_status': 'skipped',
        'changed_files': [],
        'warnings': [],
        'failures': [],
        'dry_run': False,
    }


def _session_start_metadata_warnings(project_root: Path) -> list[str]:
    metadata_path = project_root / '.work-bundle/project.yaml'
    metadata = read(metadata_path)
    missing = [field for field in PROJECT_METADATA_REQUIRED_FIELDS if f'{field}:' not in metadata]
    if not missing:
        return []
    return [_session_start_warning(f'project metadata missing required fields: {", ".join(missing)}', project_root)]


def cmd_session_start(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py session-start')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--input-warning', action='append', default=[], help=argparse.SUPPRESS)
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    data = _session_start_payload(project_root)
    data['dry_run'] = parsed.dry_run
    warnings = list(parsed.input_warning)

    bootstrap_path = Path(str(data['bootstrap_path']))
    if not bootstrap_path.is_file():
        warnings.append(_session_start_warning('bootstrap missing', project_root))
        data['warnings'] = warnings
        if parsed.json:
            out(data)
        else:
            print(f"session-start skipped: {'; '.join(warnings)}")
        return 0

    registry_path = Path(str(data['registry_path']))
    if not registry_path.is_file():
        data['registry_status'] = 'missing'
        warnings.append(_session_start_warning('project registry missing', project_root))
        data['warnings'] = warnings
        if parsed.json:
            out(data)
        else:
            print(f"session-start skipped: {'; '.join(warnings)}")
        return 0

    metadata_path = Path(str(data['project_metadata_path']))
    if not metadata_path.is_file():
        warnings.append(_session_start_warning('project metadata missing', project_root))
        data['warnings'] = warnings
        if parsed.json:
            out(data)
        else:
            print(f"session-start skipped: {'; '.join(warnings)}")
        return 0

    metadata_warnings = _session_start_metadata_warnings(project_root)
    if metadata_warnings:
        warnings.extend(metadata_warnings)
        data['warnings'] = warnings
        if parsed.json:
            out(data)
        else:
            print(f"session-start skipped: {'; '.join(warnings)}")
        return 0

    entry, registry = find_registry_entry(project_root)
    data['registry_path'] = str(registry)
    data['registry_status'] = 'registered' if entry else 'not-registered'
    if entry is None:
        warnings.append(_session_start_warning('project registry entry missing', project_root))
        data['warnings'] = warnings
        if parsed.json:
            out(data)
        else:
            print(f"session-start skipped: {'; '.join(warnings)}")
        return 0

    try:
        agents_result = sync_agents_managed_section(project_root, dry_run=parsed.dry_run)
    except ReferenceAssetError as exc:
        data['status'] = 'issues-found'
        data['failures'] = [exc.code]
        data['missing_reference'] = exc.path
        warnings.append(_session_start_warning('reference asset missing', project_root))
        data['warnings'] = warnings
        if parsed.json:
            out(data)
        else:
            print(f"session-start issues-found: {'; '.join(warnings)}")
        return 0

    checksum = str(agents_result.get('template_checksum_sha256') or '')
    data.update({
        'status': 'passed',
        'registry_status': 'registered',
        'registry_entry': entry,
        'project_metadata_status': 'present',
        'project_agents_checksum': f'sha256:{checksum}' if checksum and _metadata_agents_checksum(metadata_path) == checksum else 'stale',
        'agents_status': agents_result.get('agents_status'),
        'changed_files': agents_result.get('changed_files', []),
        'warnings': warnings + list(agents_result.get('warnings', [])),
        'failures': agents_result.get('failures', []),
        'agents_sync': _agents_sync_output(agents_result),
    })
    if data['agents_status'] in {'created', 'updated'}:
        data['status'] = 'issues-found'
    if parsed.dry_run:
        data['project_agents_checksum'] = f'sha256:{checksum}' if checksum and _metadata_agents_checksum(metadata_path) == checksum else 'stale'
    if parsed.json:
        out(data)
    else:
        print(f"session-start {data['status']}: agents {data['agents_status']}")
    return 0


def cmd_init_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py init-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-work-bundle-git", action="store_true")
    parser.add_argument("--create-project-skill-override", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    changed: list[str] | str = "none"
    agents_result: dict[str, object] = {
        'agents_status': 'skipped-dry-run' if parsed.dry_run else 'skipped',
        'template_checksum_sha256': '',
        'changed_files': [],
        'warnings': [],
        'failures': [],
        'dry_run': parsed.dry_run,
    }
    if not parsed.dry_run:
        try:
            changed, agents_result = apply_project(
                project_root,
                init_git=not parsed.disable_work_bundle_git,
                create_override=parsed.create_project_skill_override,
                name=parsed.name,
                force=parsed.force,
                scope='init',
                return_details=True,
            )
        except ReferenceAssetError as exc:
            out(_reference_failure_payload(exc, 'init-project'))
            return 1
        entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
        if registry_changed and isinstance(changed, list):
            changed.append(str(registry))
    else:
        entry = registry_entry(project_root, parsed.name)
        registry = project_registry_path()
    data = inspect_project(project_root)
    failures = project_failures(data, strict=not parsed.dry_run, include_roles=False)
    data.update({
        "command": "init-project",
        "registry_path": str(registry),
        "registry_entry": entry,
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
        "agents_status": agents_result.get('agents_status'),
        "agents_sync": _agents_sync_output(agents_result),
    })
    if parsed.dry_run:
        data["dry_run"] = True
    else:
        data["changed_files"] = sorted(set(changed if isinstance(changed, list) else []))
    out(data)
    return 0 if not failures else 1


def cmd_register_project_command(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py register-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    entry, changed, registry = upsert_project_registry(project_root, parsed.name)
    out({"command": "register-project", "status": "updated" if changed else "skipped", "registry_path": str(registry), "project": entry})
    return 0


def cmd_show_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py show-project")
    parser.add_argument("--project-root", default=".")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    data = inspect_project(project_root)
    entry, registry = find_registry_entry(project_root)
    failures = project_failures(data, strict=False, include_roles=False)
    data.update({
        "command": "show-project",
        "registry_path": str(registry),
        "registry_status": "registered" if entry else "not-registered",
        "registry_entry": entry,
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
    })
    out(data)
    return 0


def cmd_validate_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py validate-project")
    parser.add_argument("project_root")
    parser.add_argument("--dry-run", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    data = inspect_project(project_root)
    entry, registry = find_registry_entry(project_root)
    failures = project_failures(data, strict=True, include_roles=False)
    if entry is None:
        failures.append("project_not_registered")
    data.update({
        "command": "validate-project",
        "registry_path": str(registry),
        "registry_status": "registered" if entry else "not-registered",
        "registry_entry": entry,
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
    })
    out(data)
    return 0 if not failures else 1


def cmd_set_prefer_subagent(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py set-prefer-subagent")
    parser.add_argument("value", choices=["true", "false", "enable", "disable", "enabled", "disabled", "on", "off"])
    parser.add_argument("--scope", choices=["global", "project"], required=True)
    parser.add_argument("--project-root", default=".")
    parsed = parser.parse_args(args)
    enabled = parsed.value in {"true", "enable", "enabled", "on"}
    project_root = Path(parsed.project_root).expanduser().resolve()
    target_path, changed = set_prefer_subagent(project_root, parsed.scope, enabled)
    effective = resolve_effective_prefer_subagent(project_root)
    out({
        "command": "set-prefer-subagent",
        "status": "updated" if changed else "skipped",
        "scope": parsed.scope,
        "prefer_subagent": enabled,
        "target_path": str(target_path),
        "project_root": str(project_root),
        "effective_prefer_subagent": effective,
        "changed_files": [str(target_path)] if changed else [],
    })
    return 0


def cmd_migrate_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py migrate-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parser.add_argument("--force", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    before = inspect_project(project_root)
    try:
        changed, agents_result = apply_project(
            project_root,
            init_git=False,
            name=parsed.name,
            force=parsed.force,
            scope='migrate',
            return_details=True,
        )
    except ReferenceAssetError as exc:
        out(_reference_failure_payload(exc, 'migrate-project'))
        return 1
    contract_changed, retired_rules_contract, rules_contract_archive = _retire_legacy_rules_contract(project_root)
    changed.extend(contract_changed)
    bootstrap_changed, retired_artifacts, archive_root = _cleanup_retired_bootstrap(project_root)
    changed.extend(bootstrap_changed)
    entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
    if registry_changed:
        changed.append(str(registry))
    after = inspect_project(project_root)
    failures = project_failures(after, strict=True, include_roles=False)
    report = project_root / ".work-bundle" / "orchestration" / "docs" / f"migration-report-{utc_now_rfc3339()[:10]}.md"
    report_lines = [
        "# Work-Bundle Project Migration Report",
        "",
        f"- project_root: {project_root}",
        f"- status: {'passed' if not failures else 'issues-found'}",
        f"- before_status: {'passed' if not project_failures(before, strict=False, include_roles=False) else 'issues-found'}",
        f"- changed_files: {len(set(changed))}",
        f"- force: {parsed.force}",
    ]
    report_lines.extend(_render_bootstrap_retirement_report_section(retired_artifacts, archive_root))
    report_lines.extend(_render_rules_contract_retirement_report_section(retired_rules_contract, rules_contract_archive))
    report_lines.append("")
    report_text = "\n".join(report_lines)
    if write(report, report_text, overwrite=False):
        changed.append(str(report))
    out({
        "command": "migrate-project",
        "status": "passed" if not failures else "issues-found",
        "failures": failures,
        "changed_files": sorted(set(changed)),
        "agents_status": agents_result.get('agents_status'),
        "agents_sync": _agents_sync_output(agents_result),
        "migration_report": str(report),
        "retired_bootstrap": {
            "archive_root": archive_root,
            "artifacts": retired_artifacts,
        },
        "retired_rules_contract": {
            "archive_root": rules_contract_archive,
            "artifact": retired_rules_contract,
        },
        "registry_path": str(registry),
        "registry_entry": entry,
        "before_status": "passed" if not project_failures(before, strict=False, include_roles=False) else "issues-found",
    })
    return 0 if not failures else 1


def cmd_doctor_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py doctor-project')
    parser.add_argument('project_root')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--repair', action='store_true')
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    changed: list[str] = []
    agents_result: dict[str, object] = {
        'agents_status': 'not-run',
        'template_checksum_sha256': '',
        'changed_files': [],
        'warnings': [],
        'failures': [],
        'dry_run': False,
    }
    if parsed.repair:
        try:
            changed, agents_result = repair_project(project_root, force=parsed.force, return_details=True)
        except ReferenceAssetError as exc:
            out(_reference_failure_payload(exc, 'doctor-project'))
            return 1
    data = inspect_project(project_root)
    failures = project_failures(data, strict=False, include_roles=True)
    data.update({
        'command': 'doctor-project',
        'status': 'passed' if not failures else 'issues-found',
        'failures': failures,
        'changed_files': sorted(set(changed)),
        'agents_status': agents_result.get('agents_status'),
        'agents_sync': _agents_sync_output(agents_result),
    })
    out(data)
    return 0 if not failures else 1


def cmd_project(args: list[str], apply: bool = False, inspect_only: bool = False, repo_model: bool = False) -> int:
    if apply:
        return cmd_init_project(args)
    if inspect_only:
        return cmd_show_project(["--project-root", args[0]] if args else [])
    return cmd_validate_project(args)
