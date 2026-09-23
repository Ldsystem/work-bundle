from __future__ import annotations

import hashlib
import subprocess

from core import *

from bootstrap_config import default_toolkit_root
from workspace_resources import validate_script_index, _load_yaml
from infrastructure import (
    InfrastructureError,
    atomic_write_text,
    dump_canonical_yaml,
    load_project_registry,
    parse_yaml_mapping,
    resolve_anchor_context,
    validate_infrastructure_document,
)


DIAG_REFERENCE_ASSET_MISSING = 'WB_REFERENCE_ASSET_MISSING'
INIT_TREE_MANIFEST = 'references/wb-initialize-project-default-work-bundle-tree.yaml'
INIT_WORK_BUNDLE_GITIGNORE = 'references/wb-initialize-project-default-work-bundle-gitignore'
INIT_AGENTS_TEMPLATE = 'references/assets/template/AGENTS.md'
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
PROJECT_METADATA_V3_REQUIRED_FIELDS = [
    'metadata_version',
    'authority',
    'workspace_root',
    'workspace_mode',
    'project_root',
    'source_repository_roles',
    'operation_policy',
    'source_repositories',
    'migration',
]
PROJECT_METADATA_V2_REQUIRED_FIELDS = [
    'metadata_version', 'authority', 'project_root', 'source_repository_roles',
    'operation_policy', 'source_repositories', 'migration',
]
SOURCE_REPOSITORY_ROLES = {
    'registry': 'Locator only: workspace slug/root and stable repository origin identity and locators.',
    'project_metadata': 'Working-state authority: member path, branch/HEAD observation, lifecycle transaction, operation policy, and CodeGraph state.',
}
CHECKOUT_ROLES = frozenset({'truth', 'development', 'auxiliary'})
BRANCH_CHECK_REQUIRED_BEFORE = [
    'specification_evidence',
    'implementation_planning',
    'execution',
    'review',
    'project_scope_update',
]
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


def _init_gitignore_patterns() -> list[str]:
    lines = []
    for raw in _require_reference_text(INIT_WORK_BUNDLE_GITIGNORE).splitlines():
        line = raw.strip()
        if line and not line.startswith('#'):
            lines.append(line)
    return lines


def _checkout_role(source: dict[str, object], source_id: str = '') -> str:
    explicit = str(source.get('checkout_role') or '')
    if explicit:
        return explicit
    resolved_id = source_id or str(source.get('id') or '')
    if resolved_id.endswith('-main'):
        return 'truth'
    return 'development' if bool(source.get('work_dir')) else 'auxiliary'


def _git_value(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(project_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ''


def _is_git_repository(project_root: Path) -> bool:
    return _git_value(project_root, 'rev-parse', '--is-inside-work-tree') == 'true'


def _git_branch(project_root: Path) -> str:
    return _git_value(project_root, 'branch', '--show-current')


def _git_head(project_root: Path) -> str:
    return _git_value(project_root, 'rev-parse', 'HEAD')


def _git_remote(project_root: Path) -> str:
    return _git_value(project_root, 'remote', 'get-url', 'origin')


def _metadata_commit_drift_allowed(project_root: Path, expected: str, actual: str) -> bool:
    return not expected or not actual or expected == actual


def _source_repository_id(slug: str) -> str:
    return f'{slug}-main'


def _source_repository_state(project_root: Path, slug: str | None = None) -> dict[str, object]:
    resolved = project_root.expanduser().resolve()
    repo_slug = slug or _slug_from_root(resolved)
    git_repository = _is_git_repository(resolved)
    branch = _git_branch(resolved) if git_repository else ''
    head = _git_head(resolved) if git_repository else ''
    codegraph_present = (resolved / '.codegraph').is_dir()
    return {
        'id': _source_repository_id(repo_slug),
        'path': str(resolved),
        'checkout_role': 'truth',
        'work_dir': True,
        'remote': _git_remote(resolved) if git_repository else '',
        'git_repository': git_repository,
        'working_branch': branch,
        'branch_required': git_repository,
        'last_commit_id': head,
        'project_root': str(resolved),
        'origin_id': _source_repository_id(repo_slug),
        'checkout_kind': 'single-repository',
        'git_control_root': str((resolved / '.git').resolve(strict=False)) if git_repository else '',
        'git_control_scope': 'project' if git_repository else 'not-applicable',
        'worktree_name': _source_repository_id(repo_slug),
        'expected_branch': branch,
        'base_ref': 'HEAD',
        'observed_head': head,
        'observation_time': utc_now_rfc3339(),
        'lifecycle_status': 'active',
        'operation_policy': 'inherit',
        'baseline_status': 'current' if git_repository and branch and head else ('unborn' if git_repository else 'not-git'),
        'codegraph': {
            'supported': codegraph_present,
            'index_present': codegraph_present,
            'root': str(resolved),
            'status': 'unknown' if codegraph_present else 'not-indexed',
            'synced_commit_id': '',
            'last_synced_at': '',
            'reason': '' if codegraph_present else 'no-index',
        },
    }


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
    return ''.join(rendered)


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
    while end > start + 1 and not str(lines[end - 1]).strip():
        end -= 1
    return start, end


def _validated_workspace_metadata(path: Path) -> dict[str, object]:
    document = parse_yaml_mapping(read(path), source=str(path))
    return validate_infrastructure_document(
        document,
        family='workspace-project-metadata',
    )


def _metadata_agents_checksum(path: Path) -> str:
    document = _validated_workspace_metadata(path)
    agents_sync = document.get('agents_sync')
    if not isinstance(agents_sync, dict):
        return ''
    return str(agents_sync.get('template_checksum_sha256') or '')


def _update_project_agents_sync(project_root: Path, checksum: str, status: str) -> bool:
    path = project_root / '.work-bundle/project.yaml'
    document = _validated_workspace_metadata(path)
    document['agents_sync'] = {
        'managed_section': AGENTS_SYNC_MANAGED_SECTION,
        'template_path': AGENTS_SYNC_TEMPLATE_PATH,
        'template_checksum_sha256': checksum,
        'last_synced_at': utc_now_rfc3339(),
        'status': status,
    }
    validated = validate_infrastructure_document(
        document,
        family='workspace-project-metadata',
    )
    rendered = dump_canonical_yaml(validated)
    if read(path) == rendered:
        return False
    atomic_write_text(path, rendered)
    return True


def _yaml_scalar(text: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}:\s*(.*)$', text, re.MULTILINE)
    return match.group(1).strip().strip('"').strip("'") if match else ''


def _yaml_section_lines(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    bounds = _yaml_block_bounds(lines, key)
    if not bounds:
        return []
    start, end = bounds
    return lines[start:end]


def _metadata_source_repositories(text: str) -> list[dict[str, object]]:
    section = _yaml_section_lines(text, 'source_repositories')
    repositories: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_nested: dict[str, object] | None = None
    nested_key: str | None = None
    current_list_key: str | None = None
    for raw in section[1:]:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith('  - '):
            if current is not None:
                repositories.append(current)
            current = {}
            current_nested = None
            nested_key = None
            current_list_key = None
            item = stripped[2:]
            if ':' in item:
                key, value = item.split(':', 1)
                current[key.strip()] = _parse_yaml_value(value.strip())
            continue
        if current is None:
            continue
        if line.startswith('    ') and not line.startswith('      '):
            key, value = stripped.split(':', 1)
            key = key.strip()
            value = value.strip()
            current_nested = None
            nested_key = None
            current_list_key = None
            if value == '':
                if key in {'branch_check', 'codegraph'}:
                    current[key] = {}
                    current_nested = current[key]  # type: ignore[assignment]
                    nested_key = key
                elif key in {'last_commit_id', 'working_branch', 'remote'}:
                    current[key] = ''
                else:
                    current[key] = []
                    current_list_key = key
            else:
                current[key] = _parse_yaml_value(value)
            continue
        if line.startswith('      - ') and current_list_key:
            target = current.get(current_list_key)
            if isinstance(target, list):
                target.append(stripped[2:].strip())
            continue
        if line.startswith('      ') and current_nested is not None and ':' in stripped:
            key, value = stripped.split(':', 1)
            value = value.strip()
            if value == '':
                current_nested[key.strip()] = []
                current_list_key = f'{nested_key}.{key.strip()}'
            else:
                current_nested[key.strip()] = _parse_yaml_value(value)
            continue
        if line.startswith('        - ') and nested_key == 'branch_check':
            branch_check = current.get('branch_check')
            if isinstance(branch_check, dict):
                values = branch_check.setdefault('required_before', [])
                if isinstance(values, list):
                    values.append(stripped[2:].strip())
    if current is not None:
        repositories.append(current)
    for repository in repositories:
        # Normalize v3 member names for compatibility consumers without
        # rewriting the source document or discarding unknown fields.
        if 'project_root' in repository:
            repository.setdefault('path', repository.get('project_root'))
            repository.setdefault('working_branch', repository.get('expected_branch', ''))
            repository.setdefault('last_commit_id', repository.get('observed_head', ''))
            repository.setdefault('checkout_role', 'truth' if repository.get('checkout_kind') == 'single-repository' else 'development')
            repository.setdefault('work_dir', True)
            repository.setdefault('branch_required', bool(repository.get('git_repository')))
    return repositories


def _parse_yaml_value(value: str) -> object:
    value = value.strip().strip('"').strip("'")
    if value == 'true':
        return True
    if value == 'false':
        return False
    return value


def _metadata_operation_policy_valid(text: str) -> bool:
    section = '\n'.join(_yaml_section_lines(text, 'operation_policy'))
    return all(
        token in section
        for token in [
            'project_files:',
            'git:',
            'allow_operations:',
            'permissive_operations:',
            'forbid_operations:',
            'reset --hard',
            'clean -fd',
            'push --force',
        ]
    )


def _metadata_failures(project_root: Path, metadata_text: str, registry_entry_data: dict[str, object] | None) -> list[str]:
    failures: list[str] = []
    version = _yaml_scalar(metadata_text, 'metadata_version')
    if version not in {'2', '3'}:
        failures.append('project_metadata_version_stale')
    if not _metadata_operation_policy_valid(metadata_text):
        failures.append('operation_policy_invalid')
    repositories = _metadata_source_repositories(metadata_text)
    if not repositories:
        failures.append('source_repositories_missing')
        return failures
    registry_ids: set[str] = set()
    if registry_entry_data is not None:
        sources = registry_entry_data.get('source_repositories')
        if isinstance(sources, list):
            for source in sources:
                if isinstance(source, dict) and source.get('id'):
                    registry_ids.add(str(source.get('id')))
    for index, repo in enumerate(repositories):
        prefix = f'source_repositories[{index}]'
        repo_path = Path(str(repo.get('path') or project_root)).expanduser().resolve()
        git_repository = bool(repo.get('git_repository'))
        actual_git = _is_git_repository(repo_path)
        if repo.get('id') in {'', None}:
            failures.append(f'{prefix}.id_missing')
        checkout_role = str(repo.get('checkout_role') or '')
        if checkout_role not in CHECKOUT_ROLES:
            failures.append(f'{prefix}.checkout_role_invalid')
        if registry_ids and str(repo.get('id')) not in registry_ids:
            failures.append(f'{prefix}.registry_project_mismatch')
        if git_repository != actual_git:
            failures.append(f'{prefix}.git_repository_mismatch')
        if version == '3':
            for field in ('project_root', 'origin_id', 'checkout_kind', 'git_control_root', 'git_control_scope', 'worktree_name', 'expected_branch', 'base_ref', 'observed_head', 'observation_time', 'baseline_status', 'lifecycle_status', 'operation_policy', 'codegraph'):
                if field not in repo:
                    failures.append(f'{prefix}.{field}_missing')
            if repo.get('checkout_kind') not in {'single-repository', 'managed-worktree', 'local-project'}:
                failures.append(f'{prefix}.checkout_kind_invalid')
            if repo.get('git_control_scope') not in {'workspace', 'project', 'not-applicable'}:
                failures.append(f'{prefix}.git_control_scope_invalid')
        if git_repository:
            working_branch = str(repo.get('working_branch') or '')
            last_commit_id = str(repo.get('last_commit_id') or '')
            baseline_status = str(repo.get('baseline_status') or '')
            actual_branch = _git_branch(repo_path)
            actual_head = _git_head(repo_path)
            if not working_branch:
                failures.append(f'{prefix}.working_branch_missing')
            if not last_commit_id and actual_head and baseline_status != 'unborn':
                failures.append(f'{prefix}.last_commit_id_missing')
            if last_commit_id and actual_head and not _metadata_commit_drift_allowed(repo_path, last_commit_id, actual_head):
                failures.append(f'{prefix}.baseline_status_stale')
            if working_branch and actual_branch and working_branch != actual_branch:
                failures.append(f'{prefix}.branch_mismatch')
            if version == '2' and repo.get('branch_required') is not True:
                failures.append(f'{prefix}.branch_required_missing')
            branch_check = repo.get('branch_check')
            if version == '2' and not isinstance(branch_check, dict):
                failures.append(f'{prefix}.branch_check_missing')
            elif version == '2':
                required_before = branch_check.get('required_before')
                if not isinstance(required_before, list) or any(item not in required_before for item in BRANCH_CHECK_REQUIRED_BEFORE):
                    failures.append(f'{prefix}.branch_check_required_before_invalid')
                if branch_check.get('on_mismatch') != 'stop':
                    failures.append(f'{prefix}.branch_check_on_mismatch_invalid')
        codegraph = repo.get('codegraph')
        if not isinstance(codegraph, dict):
            failures.append(f'{prefix}.codegraph_missing')
            continue
        marker_present = (repo_path / '.codegraph').is_dir()
        if bool(codegraph.get('index_present')) != marker_present:
            failures.append(f'{prefix}.codegraph_index_present_mismatch')
        for key in ('supported', 'index_present', 'root', 'status', 'synced_commit_id', 'last_synced_at', 'reason'):
            if key not in codegraph:
                failures.append(f'{prefix}.codegraph_{key}_missing')
        if not marker_present and (codegraph.get('status') != 'not-indexed' or codegraph.get('reason') != 'no-index'):
            failures.append(f'{prefix}.codegraph_no_index_invalid')
    return failures


def _workspace_metadata_failures(project_root: Path, metadata_text: str) -> list[str]:
    if _yaml_scalar(metadata_text, 'metadata_version') != '3':
        return []
    failures: list[str] = []
    workspace_root = _yaml_scalar(metadata_text, 'workspace_root')
    mode = _yaml_scalar(metadata_text, 'workspace_mode')
    if mode not in {'single-repository', 'multi-repository'}:
        failures.append('workspace_mode_invalid')
    if mode == 'single-repository' and Path(workspace_root).expanduser().resolve() != project_root.resolve():
        failures.append('workspace_root_contradiction')
    resource_section = '\n'.join(_yaml_section_lines(metadata_text, 'workspace_resources'))
    resolved_workspace = Path(workspace_root).expanduser().resolve() if workspace_root else project_root
    if mode in {'single-repository', 'multi-repository'}:
        if 'script/index.yaml' not in resource_section or 'credentials/credentials.yaml' not in resource_section:
            failures.append('workspace_resources_invalid')
        failures.extend(validate_script_index(resolved_workspace))
    return failures


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
    if existing and not agents_changed:
        agents_status = 'unchanged'
    metadata_changed = _metadata_agents_checksum(metadata_path) != checksum
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


def _has_ignore(lines: list[str], wanted: str) -> bool:
    variants = {wanted, wanted.rstrip('/'), '/' + wanted.rstrip('/')}
    return any(line.strip() in variants for line in lines)


def _project_rule_store_root(project_root: Path) -> Path:
    return project_root / '.work-bundle' / 'rules'


def inspect_project(project_root: Path) -> dict:
    wb = project_root / '.work-bundle'
    rules = _project_rule_store_root(project_root)
    legacy_rules = project_root / 'rules'
    pgi = read(project_root / '.gitignore').splitlines()
    wbi = read(wb / '.gitignore').splitlines()
    pm = read(project_root / '.work-bundle/project.yaml')
    runtime = resolve_bootstrap_runtime()
    project_metadata_path = project_root / '.work-bundle/project.yaml'
    metadata_version = _yaml_scalar(pm, 'metadata_version')
    required_fields = PROJECT_METADATA_V3_REQUIRED_FIELDS if metadata_version == '3' else PROJECT_METADATA_V2_REQUIRED_FIELDS
    project_metadata_missing = [field for field in required_fields if f'{field}:' not in pm]
    registry_entry_data, registry_path = find_registry_entry(project_root)
    metadata_failures = (_metadata_failures(project_root, pm, registry_entry_data) + _workspace_metadata_failures(project_root, pm)) if project_metadata_path.exists() else []
    source_repositories = _metadata_source_repositories(pm)
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
        'project_metadata_version': metadata_version,
        'project_metadata_failures': metadata_failures,
        'project_metadata_v2_failures': metadata_failures,
        'project_metadata_valid': not project_metadata_missing and not metadata_failures,
        'project_metadata_authority': '.work-bundle/project.yaml',
        'project_source_repositories': source_repositories,
        'source_repository_roles': SOURCE_REPOSITORY_ROLES,
        'registry_project_id_status': 'matched' if registry_entry_data else 'not-registered',
        'registry_path': str(registry_path),
        'rules_root': rules.exists(),
        'rules_root_authority': '.work-bundle/rules',
        'rule_files': len(list(rules.glob('*.yaml'))) if rules.exists() else 0,
        'rule_index': (rules / 'index.yaml').exists(),
        'legacy_rules_root': legacy_rules.exists(),
        'legacy_rule_files': len(list(legacy_rules.glob('*.yaml'))) if legacy_rules.exists() else 0,
        'legacy_rule_index': (legacy_rules / 'index.yaml').exists(),
        'legacy_rules_authority': 'legacy-artifact',
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
    }


def project_failures(data: dict, strict: bool = True) -> list[str]:
    required = ['project_gitignore', 'project_ignores_work_bundle', 'project_ignores_agents', 'agents_md', 'work_bundle', 'work_bundle_gitignore', 'knowledge_root', 'orchestration_root', 'rules_root', 'project_metadata_exists']
    if strict:
        required.extend(['work_bundle_gitignore_required_entries', 'orchestration_tree', 'rule_index'])
    failures = [k for k in required if not data.get(k)]
    if not data.get('project_metadata_exists'):
        failures.append(DIAG_PROJECT_METADATA_MISSING)
    if data.get('project_metadata_exists') and data.get('project_metadata_required_fields_missing'):
        failures.append(DIAG_PROJECT_METADATA_INVALID)
    if data.get('project_metadata_exists') and data.get('project_metadata_v2_failures'):
        failures.append(DIAG_PROJECT_METADATA_INVALID)
        failures.extend(str(item) for item in data.get('project_metadata_v2_failures', []))
    if data.get('mdc_rules'):
        failures.append('mdc_rules_present')
    if data.get('global_registry_copied'):
        failures.append('global_registry_not_copied')
    return failures


def _slug_from_root(project_root: Path, name: str | None = None) -> str:
    raw = name or project_root.name or "project"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw.strip().lower()).strip("-")
    return slug or "project"


def project_registry_path() -> Path:
    return resolve_project_registry_path()


def _normalize_loaded_registry_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _normalize_loaded_registry_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_loaded_registry_value(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat) and not isinstance(value, (str, bytes)):
        return isoformat()
    return value


def _project_blocks_from_document(document: object) -> list[dict[str, object]] | None:
    if not isinstance(document, dict):
        return None
    projects = document.get('projects')
    if projects is None:
        return []
    if not isinstance(projects, list):
        return None
    result: list[dict[str, object]] = []
    for item in projects:
        if isinstance(item, dict):
            loaded = _normalize_loaded_registry_value(item)
            if isinstance(loaded, dict):
                result.append(loaded)
    return result


def _project_blocks(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    document = parse_yaml_mapping(read(path), source=str(path))
    validated = validate_infrastructure_document(document, family='project-registry')
    loaded = _project_blocks_from_document(validated)
    if loaded is None:
        raise InfrastructureError(
            'WB_INFRASTRUCTURE_SCHEMA_INVALID',
            f'project-registry failed structural validation: {path}',
            details={'family': 'project-registry', 'path': str(path)},
        )
    return loaded


def _normalize_registry_path(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return str(Path(raw).expanduser().resolve())


def _normalize_source_repositories(sources: object) -> list[tuple[str, str, bool, str, str, str]]:
    if not isinstance(sources, list):
        return []
    normalized: list[tuple[str, str, bool, str, str, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        raw_path = source.get("path")
        path = str(Path(str(raw_path)).expanduser().resolve()) if raw_path else ""
        normalized.append((
            path,
            _checkout_role(source),
            bool(source.get("work_dir")),
            str(source.get("remote", "")),
            str(source.get("id", "")),
            str(bool(source.get("git_repository"))),
        ))
    return sorted(normalized)


def _source_identity(source: dict[str, object]) -> tuple[str, str]:
    source_id = str(source.get("id", "") or "")
    raw_path = source.get("path")
    path = str(Path(str(raw_path)).expanduser().resolve()) if raw_path else ""
    return source_id, path


def _same_source_repository(left: dict[str, object], right: dict[str, object]) -> bool:
    left_id, left_path = _source_identity(left)
    right_id, right_path = _source_identity(right)
    if left_path and right_path:
        return left_path == right_path
    return bool(left_id and right_id and left_id == right_id)


def _unique_source_repository_id(slug: str, source: dict[str, object], used_ids: set[str]) -> str:
    source_id = str(source.get("id") or "")
    if source_id and source_id not in used_ids:
        return source_id
    raw_path = str(source.get("path") or "")
    path_name = Path(raw_path).expanduser().name if raw_path else "repository"
    base = f"{slug}-{_slug_from_root(Path(path_name))}"
    candidate = base
    index = 2
    while candidate in used_ids:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _merge_registry_source_lists(existing_sources: object, incoming_sources: object, slug: str) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    if isinstance(existing_sources, list):
        merged.extend(source for source in existing_sources if isinstance(source, dict))
    incoming = [source for source in incoming_sources if isinstance(source, dict)] if isinstance(incoming_sources, list) else []
    for source in incoming:
        if any(_same_source_repository(existing, source) for existing in merged):
            continue
        next_source = dict(source)
        used_ids = {str(existing.get("id") or "") for existing in merged}
        next_source["id"] = _unique_source_repository_id(slug, next_source, used_ids)
        merged.append(next_source)
    return merged


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
        "work_bundle_root": existing.get("work_bundle_root", incoming.get("work_bundle_root")),
        "knowledge_root": existing.get("knowledge_root", incoming.get("knowledge_root")),
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
        merged["source_repositories"] = _merge_registry_source_lists(
            existing_sources,
            incoming.get("source_repositories", []),
            str(merged.get("slug") or "project"),
        )
    else:
        merged["source_repositories"] = source_repositories
    if existing.get("layout_version") not in {None, ''}:
        merged["layout_version"] = existing.get("layout_version")
    for key, value in existing.items():
        if key not in merged:
            merged[key] = value
    changed = not _registry_entries_equivalent(existing, merged)
    if changed:
        merged["updated_at"] = utc_now_rfc3339()[:10]
    return merged, changed


def registry_entry(project_root: Path, name: str | None = None, aliases: list[str] | None = None) -> dict[str, object]:
    resolved = project_root.expanduser().resolve()
    slug = _slug_from_root(resolved, name)
    repo = _source_repository_state(resolved, slug)
    return {
        "slug": slug,
        "name": name or slug,
        "work_bundle_root": str(resolved / ".work-bundle"),
        "knowledge_root": str(resolved / ".work-bundle" / "knowledge"),
        "aliases": aliases if aliases is not None else [],
        "source_repositories": [{
            "id": repo["id"],
            "path": str(resolved),
            "checkout_role": "truth",
            "work_dir": True,
            "remote": repo["remote"],
            "git_repository": repo["git_repository"],
        }],
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
    document = load_project_registry()
    raw_projects = document.get("projects")
    projects = [dict(item) for item in raw_projects if isinstance(item, dict)] if isinstance(raw_projects, list) else []
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
    document["projects"] = next_projects
    validate_infrastructure_document(document, family="project-registry")
    rendered = dump_canonical_yaml(document)
    if read(path) != rendered:
        atomic_write_text(path, rendered)
        changed = True
    return entry, changed, path


def find_registry_entry(project_root: Path) -> tuple[dict[str, object] | None, Path]:
    path = project_registry_path()
    target = str(project_root.resolve())
    document = load_project_registry()
    projects = document.get("projects")
    for project in projects if isinstance(projects, list) else []:
        if not isinstance(project, dict):
            continue
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
    if not path.is_file():
        return False, path
    document = load_project_registry()
    raw_projects = document.get('projects')
    projects = [dict(item) for item in raw_projects if isinstance(item, dict)] if isinstance(raw_projects, list) else []
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
        document['projects'] = kept
        validated = validate_infrastructure_document(document, family='project-registry')
        atomic_write_text(path, dump_canonical_yaml(validated))
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
    registry_path = Path(str(runtime.get('work_bundle_config_root'))) / 'registry/projects.yaml'
    if bootstrap_path.is_file():
        try:
            registry_path = project_registry_path()
        except InfrastructureError:
            pass
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
    try:
        metadata = parse_yaml_mapping(read(metadata_path), source=str(metadata_path))
    except InfrastructureError as exc:
        return [_session_start_warning(f'project metadata invalid: {exc.code}', project_root)]
    version = metadata.get('metadata_version')
    if version in {2, 3, '2', '3'}:
        return [_session_start_warning(f'historical project metadata v{version} requires migration', project_root)]
    if version != 4:
        return [_session_start_warning(f'project metadata version unsupported: {version!r}', project_root)]
    try:
        resolve_anchor_context(workspace_root=project_root, cwd=project_root)
    except InfrastructureError as exc:
        return [_session_start_warning(f'current project metadata or device binding invalid: {exc.code}', project_root)]
    return []


def cmd_session_start(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py session-start')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--input-warning', action='append', default=[], help=argparse.SUPPRESS)
    parsed = parser.parse_args(args)
    requested_root = Path(parsed.project_root).expanduser().resolve()
    project_root = requested_root
    for candidate in (requested_root, *requested_root.parents):
        if (candidate / '.work-bundle/project.yaml').is_file():
            project_root = candidate
            break
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

    try:
        context = resolve_anchor_context(workspace_root=project_root, cwd=project_root)
        portable = parse_yaml_mapping(read(metadata_path), source=str(metadata_path))
        workspace = portable.get('workspace') if isinstance(portable, dict) else None
        entry = {
            'workspace_id': context.workspace_id,
            'slug': workspace.get('slug') if isinstance(workspace, dict) else project_root.name,
            'workspace_root': str(context.workspace_root),
        }
        data['registry_status'] = 'registered'
    except InfrastructureError as exc:
        warnings.append(_session_start_warning(f'project registry binding invalid: {exc.code}', project_root))
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
    out({
        'command': 'init-project',
        'status': 'issues-found',
        'failure_code': 'WB_CURRENT_INIT_COMMAND_RETIRED',
        'changed_files': [],
        'migration': {
            'current_creation': 'wb.py init-workspace <workspace-root> --slug <slug> --repository <id=remote> (--dry-run|--apply)',
            'historical_metadata': 'wb.py migrate-control-plane <workspace-root> (--dry-run|--apply --accepted-proposal-id <id>)',
        },
    })
    return 1


def cmd_register_project_command(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py register-project")
    parser.add_argument("project_root")
    parser.add_argument("--name")
    parsed = parser.parse_args(args)
    selected_root = Path(parsed.project_root).expanduser().resolve()
    try:
        context = resolve_anchor_context(
            workspace_root=selected_root if (selected_root / '.work-bundle/project.yaml').is_file() else None,
            project_root=selected_root if not (selected_root / '.work-bundle/project.yaml').is_file() else None,
            cwd=selected_root,
        )
    except InfrastructureError as exc:
        out({
            'command': 'register-project',
            'status': 'issues-found',
            'failure_code': exc.code,
            'changed_files': [],
        })
        return 1
    project_root = context.workspace_root
    metadata_path = project_root / '.work-bundle/project.yaml'
    entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
    changed_files: list[str] = []
    if registry_changed:
        changed_files.append(str(registry))
    out({
        "command": "register-project",
        "status": "updated" if changed_files else "skipped",
        "registry_path": str(registry),
        "registry_entry": entry,
        "project": entry,
        "project_metadata_path": str(metadata_path),
        "project_metadata_status": 'portable-v4-unchanged',
        "source_repository_roles": SOURCE_REPOSITORY_ROLES,
        "changed_files": sorted(changed_files),
    })
    return 0


def cmd_show_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py show-project")
    roots = parser.add_mutually_exclusive_group()
    roots.add_argument("--project-root")
    roots.add_argument("--workspace-root")
    parsed = parser.parse_args(args)
    selected_root = Path(parsed.project_root or parsed.workspace_root or ".").expanduser().resolve()
    try:
        context = resolve_anchor_context(
            workspace_root=selected_root if parsed.workspace_root or (selected_root / ".work-bundle/project.yaml").is_file() else None,
            project_root=selected_root if parsed.project_root and not (selected_root / ".work-bundle/project.yaml").is_file() else None,
            cwd=selected_root,
        )
    except InfrastructureError as exc:
        out({'command': 'show-project', 'status': 'issues-found', 'failure_code': exc.code, 'changed_files': []})
        return 1
    workspace_root = context.workspace_root
    version = _yaml_scalar(read(workspace_root / ".work-bundle/project.yaml"), "metadata_version")
    if version == "4":
        from control_plane import cmd_doctor_workspace
        return cmd_doctor_workspace([str(workspace_root)], command_name="show-project")
    out({'command': 'show-project', 'status': 'issues-found', 'failure_code': 'WB_METADATA_MIGRATION_REQUIRED', 'metadata_version': version, 'changed_files': []})
    return 1


def cmd_validate_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb.py validate-project")
    parser.add_argument("project_root")
    parser.add_argument("--dry-run", action="store_true")
    parsed = parser.parse_args(args)
    selected_root = Path(parsed.project_root).expanduser().resolve()
    try:
        context = resolve_anchor_context(
            workspace_root=selected_root if (selected_root / ".work-bundle/project.yaml").is_file() else None,
            project_root=selected_root if not (selected_root / ".work-bundle/project.yaml").is_file() else None,
            cwd=selected_root,
        )
    except InfrastructureError as exc:
        out({'command': 'validate-project', 'status': 'issues-found', 'failure_code': exc.code, 'changed_files': []})
        return 1
    workspace_root = context.workspace_root
    version = _yaml_scalar(read(workspace_root / ".work-bundle/project.yaml"), "metadata_version")
    if version == "4":
        from control_plane import cmd_doctor_workspace
        return cmd_doctor_workspace([str(workspace_root)], command_name="validate-project")
    out({'command': 'validate-project', 'status': 'issues-found', 'failure_code': 'WB_METADATA_MIGRATION_REQUIRED', 'metadata_version': version, 'changed_files': []})
    return 1


def cmd_provision_member(args: list[str]) -> int:
    out({
        'command': 'provision-member', 'status': 'issues-found',
        'failure_code': 'WB_V3_MEMBER_COMMAND_RETIRED', 'changed_files': [],
        'current_command': 'wb.py add-workspace-member <workspace-root> --repository-id <id> --remote <remote> --name <name> --path <path> --default-branch <branch> --dry-run',
    })
    return 1


def cmd_cleanup_member(args: list[str]) -> int:
    out({
        'command': 'cleanup-member', 'status': 'issues-found',
        'failure_code': 'WB_V3_MEMBER_COMMAND_RETIRED', 'changed_files': [],
        'repair': 'Use attach-workspace or doctor-workspace for current v4 binding repair.',
    })
    return 1


def cmd_migrate_to_multi_repository(args: list[str]) -> int:
    out({
        'command': 'migrate-to-multi-repository',
        'status': 'issues-found',
        'failure_code': 'WB_TOPOLOGY_MIGRATION_COMMAND_RETIRED',
        'changed_files': [],
        'migration': {
            'new_workspace': 'wb.py init-workspace <workspace-root> --mode multi-repository --slug <slug> --repository <id=remote> --apply',
            'historical_metadata': 'wb.py migrate-control-plane <workspace-root> --dry-run',
        },
    })
    return 1


def cmd_migrate_project(args: list[str]) -> int:
    out({
        'command': 'migrate-project',
        'status': 'issues-found',
        'failure_code': 'WB_METADATA_MIGRATION_COMMAND_RETIRED',
        'changed_files': [],
        'migration': {
            'single_workspace': 'wb.py migrate-control-plane <workspace-root> (--dry-run|--apply --accepted-proposal-id <id>)',
            'registered_workspaces': 'wb.py migrate-registered-projects (--dry-run|--apply --accepted-plan-id <id>)',
        },
    })
    return 1


def cmd_doctor_project(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog='wb.py doctor-project')
    parser.add_argument('project_root')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--repair', action='store_true')
    parsed = parser.parse_args(args)
    selected_root = Path(parsed.project_root).expanduser().resolve()
    try:
        context = resolve_anchor_context(
            workspace_root=selected_root if (selected_root / ".work-bundle/project.yaml").is_file() else None,
            project_root=selected_root if not (selected_root / ".work-bundle/project.yaml").is_file() else None,
            cwd=selected_root,
        )
    except InfrastructureError as exc:
        out({'command': 'doctor-project', 'status': 'issues-found', 'failure_code': exc.code, 'changed_files': []})
        return 1
    workspace_root = context.workspace_root
    version = _yaml_scalar(read(workspace_root / ".work-bundle/project.yaml"), "metadata_version")
    if version == "4":
        from control_plane import cmd_doctor_workspace
        routed = [str(workspace_root)] + (["--repair"] if parsed.repair else [])
        return cmd_doctor_workspace(routed, command_name="doctor-project")
    out({'command': 'doctor-project', 'status': 'issues-found', 'failure_code': 'WB_METADATA_MIGRATION_REQUIRED', 'metadata_version': version, 'changed_files': []})
    return 1


def cmd_project(args: list[str], apply: bool = False, inspect_only: bool = False, repo_model: bool = False) -> int:
    if apply:
        return cmd_init_project(args)
    if inspect_only:
        return cmd_show_project(["--project-root", args[0]] if args else [])
    return cmd_validate_project(args)
