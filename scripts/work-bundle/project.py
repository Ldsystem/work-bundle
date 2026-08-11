from __future__ import annotations

import hashlib
import shutil
import subprocess

from core import *

from bootstrap_config import default_toolkit_root
from workspace import WorkspaceContext, WorkspaceTransaction
from workspace_resources import ensure_workspace_resources, validate_script_index
def migrate_project_metadata_v3(source_root: Path, target_root: Path, repository_id: str, branch: str, base_ref: str = 'HEAD', apply: bool = False, **options: object) -> dict[str, object]:
    from migration import apply_migration, propose_migration
    if not apply:
        options.pop('accepted_baseline_id', None)
        return propose_migration(source_root, target_root, repository_id, branch, base_ref, **options)
    return apply_migration(source_root, target_root, repository_id, branch, base_ref, **options)

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
PROJECT_METADATA_V3_REQUIRED_FIELDS = [
    'metadata_version',
    'authority',
    'workspace_root',
    'workspace_mode',
    'workspace_resources',
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
PROJECT_METADATA_VERSION = '3'
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
INIT_FORCE_REL_PATHS = frozenset({
    'AGENTS.md',
    '.work-bundle/project.yaml',
    '.work-bundle/rules/index.yaml',
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


def _yaml_string(value: object) -> str:
    text = str(value or '')
    if not text:
        return '""'
    if re.search(r'[\s:#\[\]{},&*?|\-<>=!%@`"\']', text):
        return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return text


def _source_repository_state_from_locator(locator: dict[str, object], fallback_slug: str) -> dict[str, object]:
    raw_path = locator.get('origin_path') or locator.get('path')
    resolved = Path(str(raw_path)).expanduser().resolve() if raw_path else Path.cwd().resolve()
    state = _source_repository_state(resolved, fallback_slug)
    source_id = str(locator.get('id') or state['id'])
    state['id'] = source_id
    state['work_dir'] = bool(locator.get('work_dir', False))
    state['checkout_role'] = _checkout_role(locator, source_id)
    state['checkout_kind'] = 'single-repository' if state['checkout_role'] == 'truth' else 'local-project'
    state['git_control_scope'] = 'project' if state.get('git_repository') else 'not-applicable'
    locator_remote = str(locator.get('remote') or '')
    if locator_remote:
        state['remote'] = locator_remote
    return state


def _checkout_role(source: dict[str, object], source_id: str = '') -> str:
    explicit = str(source.get('checkout_role') or '')
    if explicit:
        return explicit
    resolved_id = source_id or str(source.get('id') or '')
    if resolved_id.endswith('-main'):
        return 'truth'
    return 'development' if bool(source.get('work_dir')) else 'auxiliary'


def _registry_source_repository_states(project_root: Path, name: str | None, registry_entry_data: dict[str, object] | None) -> list[dict[str, object]]:
    slug = _slug_from_root(project_root, name)
    if not registry_entry_data:
        return [_source_repository_state(project_root, slug)]
    sources = registry_entry_data.get('source_repositories')
    if not isinstance(sources, list) or not sources:
        return [_source_repository_state(project_root, slug)]
    states: list[dict[str, object]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        states.append(_source_repository_state_from_locator(source, f'{slug}-{index + 1}'))
    return states or [_source_repository_state(project_root, slug)]


def _source_repositories_block(repositories: list[dict[str, object]]) -> str:
    lines = ['source_repositories:']
    for repo in repositories:
        codegraph = repo.get('codegraph') if isinstance(repo.get('codegraph'), dict) else {}
        lines.extend([
            f"  - id: {_yaml_string(repo.get('id'))}",
            f"    project_root: {_yaml_string(repo.get('project_root') or repo.get('path'))}",
            f"    origin_id: {_yaml_string(repo.get('origin_id') or repo.get('id'))}",
            f"    checkout_kind: {_yaml_string(repo.get('checkout_kind') or 'single-repository')}",
            f"    git_control_root: {_yaml_string(repo.get('git_control_root'))}",
            f"    git_control_scope: {_yaml_string(repo.get('git_control_scope') or 'project')}",
            f"    worktree_name: {_yaml_string(repo.get('worktree_name') or repo.get('id'))}",
            f"    git_repository: {str(bool(repo.get('git_repository'))).lower()}",
            f"    expected_branch: {_yaml_string(repo.get('expected_branch') or repo.get('working_branch'))}",
            f"    base_ref: {_yaml_string(repo.get('base_ref') or 'HEAD')}",
            f"    observed_head: {_yaml_string(repo.get('observed_head') or repo.get('last_commit_id'))}",
            f"    observation_time: {_yaml_string(repo.get('observation_time') or utc_now_rfc3339())}",
            f"    baseline_status: {repo.get('baseline_status', 'current')}",
            f"    lifecycle_status: {repo.get('lifecycle_status', 'active')}",
            f"    operation_policy: {repo.get('operation_policy', 'inherit')}",
        ])
        lines.extend([
            "    codegraph:",
            f"      supported: {str(bool(codegraph.get('supported'))).lower()}",
            f"      index_present: {str(bool(codegraph.get('index_present'))).lower()}",
            f"      root: {_yaml_string(codegraph.get('root') or repo.get('path'))}",
            f"      status: {codegraph.get('status', 'not-indexed')}",
            f"      synced_commit_id: {_yaml_string(codegraph.get('synced_commit_id'))}",
            f"      last_synced_at: {_yaml_string(codegraph.get('last_synced_at'))}",
            f"      reason: {_yaml_string(codegraph.get('reason'))}",
        ])
    return '\n'.join(lines)


def _source_repository_roles_block() -> str:
    return '\n'.join([
        'source_repository_roles:',
        f"  registry: {_yaml_string(SOURCE_REPOSITORY_ROLES['registry'])}",
        f"  project_metadata: {_yaml_string(SOURCE_REPOSITORY_ROLES['project_metadata'])}",
    ])


def _replace_top_level_block(lines: list[str], block: str, key: str) -> tuple[list[str], bool]:
    replacement = block.splitlines()
    bounds = _yaml_block_bounds(lines, key)
    if not bounds:
        if lines and lines[-1] != '':
            lines.append('')
        return lines + replacement, True
    start, end = bounds
    if lines[start:end] == replacement:
        return lines, False
    return lines[:start] + replacement + lines[end:], True


def _render_project_metadata(
    project_root: Path,
    name: str | None = None,
    registry_entry_data: dict[str, object] | None = None,
    workspace_root: Path | None = None,
    mode: str = 'single-repository',
) -> str:
    template = _require_reference_text(INIT_PROJECT_TEMPLATE)
    slug = _slug_from_root(project_root, name)
    repositories = _registry_source_repository_states(project_root, name, registry_entry_data)
    repo = repositories[0]
    replacements = {
        '<absolute-path-to-workspace-root>': str((workspace_root or project_root).resolve()),
        '<single-repository|multi-repository>': mode,
        '<absolute-path-to-project-root>': str(project_root.resolve()),
        '<industry-or-domain>': name or slug,
        '<runtime-or-framework>': 'unspecified',
        '<stable-repository-id>': repo['id'],
        '<absolute-path-to-source-repository>': repo['path'],
        '<required-working-branch>': repo['working_branch'],
        '<git-head-commit-or-empty-for-non-git>': repo['last_commit_id'],
        '<rfc3339-observation-time>': repo['observation_time'],
        '<commit|stage|pull>': 'commit,stage,pull',
        '<push>': 'push',
        '<reset --hard>': 'reset --hard',
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    rendered_lines, _ = _replace_top_level_block(
        rendered.splitlines(),
        _source_repositories_block(repositories),
        'source_repositories',
    )
    rendered_lines, _ = _replace_top_level_block(
        rendered_lines,
        _source_repository_roles_block(),
        'source_repository_roles',
    )
    rendered = '\n'.join(rendered_lines)
    return rendered.rstrip() + '\n'


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


def _git_command_ok(project_root: Path, *args: str) -> bool:
    return subprocess.run(
        ['git', '-C', str(project_root), *args],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


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
    if 'script/index.yaml' not in resource_section or 'credentials/credentials.yaml' not in resource_section:
        failures.append('workspace_resources_invalid')
    failures.extend(validate_script_index(Path(workspace_root).expanduser().resolve() if workspace_root else project_root))
    return failures


def _top_level_block_text(text: str, key: str) -> str:
    lines = text.splitlines()
    bounds = _yaml_block_bounds(lines, key)
    if not bounds:
        return ''
    start, end = bounds
    return '\n'.join(lines[start:end]).rstrip()


def _replace_or_append_scalar(lines: list[str], key: str, value: str) -> tuple[list[str], bool]:
    rendered: list[str] = []
    replaced = False
    changed = False
    new_line = f'{key}: {value}'
    for line in lines:
        if line.startswith(f'{key}:'):
            rendered.append(new_line)
            replaced = True
            changed = changed or line != new_line
        else:
            rendered.append(line)
    if not replaced:
        rendered.append(new_line)
        changed = True
    return rendered, changed


def _append_missing_top_level_block(lines: list[str], current_text: str, rendered_template: str, key: str) -> tuple[list[str], bool]:
    if _yaml_block_bounds(lines, key):
        return lines, False
    block = _top_level_block_text(rendered_template, key)
    if not block:
        return lines, False
    if lines and lines[-1] != '':
        lines.append('')
    lines.extend(block.splitlines())
    return lines, True


def migrate_project_metadata_v2(
    project_root: Path,
    name: str | None = None,
    registry_entry_data: dict[str, object] | None = None,
) -> bool:
    metadata_path = project_root / '.work-bundle/project.yaml'
    if not metadata_path.is_file():
        return False
    current = read(metadata_path)
    if _yaml_scalar(current, 'metadata_version') == PROJECT_METADATA_VERSION:
        return False
    rendered = _render_project_metadata(project_root, name, registry_entry_data)
    rendered_keys = {
        line.split(':', 1)[0] for line in rendered.splitlines()
        if line and not line.startswith((' ', '#')) and ':' in line
    }
    current_lines = current.splitlines()
    unknown_blocks: list[str] = []
    index = 0
    while index < len(current_lines):
        line = current_lines[index]
        if not line or line.startswith((' ', '#')) or ':' not in line:
            index += 1
            continue
        key = line.split(':', 1)[0]
        end = index + 1
        while end < len(current_lines) and (not current_lines[end] or current_lines[end].startswith((' ', '\t'))):
            end += 1
        if key not in rendered_keys:
            unknown_blocks.append('\n'.join(current_lines[index:end]).rstrip())
        index = end
    next_text = rendered.rstrip()
    if unknown_blocks:
        next_text += '\n\n' + '\n\n'.join(unknown_blocks)
    return write(metadata_path, next_text.rstrip() + '\n')


def _workspace_root_from_registry_entry(entry: dict[str, object], fallback_root: Path) -> Path:
    work_bundle_root = str(entry.get('work_bundle_root') or '')
    if work_bundle_root:
        root = Path(work_bundle_root).expanduser().resolve()
        if root.name == '.work-bundle':
            return root.parent
    return fallback_root.expanduser().resolve()


def _merge_metadata_source_repositories(current: list[dict[str, object]], desired: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    for desired_repo in desired:
        matched = next((repo for repo in current if _same_source_repository(repo, desired_repo)), None)
        if matched is None:
            merged.append(desired_repo)
            continue
        refreshed = dict(matched)
        observation_changed = (
            matched.get('observed_head') != desired_repo.get('observed_head')
            or matched.get('expected_branch') != desired_repo.get('expected_branch')
        )
        for key in (
            'id',
            'path',
            'checkout_role',
            'work_dir',
            'remote',
            'git_repository',
            'working_branch',
            'branch_required',
            'branch_check',
            'last_commit_id',
            'baseline_status',
            'codegraph',
            'project_root', 'origin_id', 'checkout_kind', 'git_control_root',
            'git_control_scope', 'worktree_name', 'expected_branch', 'base_ref',
            'observed_head', 'lifecycle_status', 'operation_policy',
        ):
            refreshed[key] = desired_repo.get(key)
        if observation_changed or not refreshed.get('observation_time'):
            refreshed['observation_time'] = desired_repo.get('observation_time')
        merged.append(refreshed)
    return merged


def sync_project_metadata_from_registry_entry(
    entry: dict[str, object],
    name: str | None = None,
    fallback_root: Path | None = None,
) -> tuple[bool, Path, str]:
    workspace_root = _workspace_root_from_registry_entry(entry, fallback_root or Path.cwd())
    metadata_path = workspace_root / '.work-bundle/project.yaml'
    if not metadata_path.is_file():
        return False, metadata_path, 'missing'
    current_text = read(metadata_path)
    rendered = _render_project_metadata(workspace_root, name or str(entry.get('name') or entry.get('slug') or ''), entry)
    current_repositories = _metadata_source_repositories(current_text)
    desired_repositories = _metadata_source_repositories(rendered)
    merged_repositories = _merge_metadata_source_repositories(current_repositories, desired_repositories)
    lines = current_text.splitlines()
    changed = False
    lines, roles_changed = _replace_top_level_block(lines, _source_repository_roles_block(), 'source_repository_roles')
    changed = changed or roles_changed
    lines, repositories_changed = _replace_top_level_block(lines, _source_repositories_block(merged_repositories), 'source_repositories')
    changed = changed or repositories_changed
    if changed:
        write(metadata_path, '\n'.join(lines).rstrip() + '\n')
        return True, metadata_path, 'updated'
    return False, metadata_path, 'current'


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


def _project_rule_store_root(project_root: Path) -> Path:
    return project_root / '.work-bundle' / 'rules'


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
    rules = _project_rule_store_root(project_root)
    legacy_rules = project_root / 'rules'
    roles = project_root / 'roles'
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
    if data.get('project_metadata_exists') and data.get('project_metadata_v2_failures'):
        failures.append(DIAG_PROJECT_METADATA_INVALID)
        failures.extend(str(item) for item in data.get('project_metadata_v2_failures', []))
    if data.get('mdc_rules'):
        failures.append('mdc_rules_present')
    if data.get('global_registry_copied'):
        failures.append('global_registry_not_copied')
    return failures


def _refresh_registered_project_metadata(current: str, rendered: str) -> str:
    current_repositories = _metadata_source_repositories(current)
    desired_repositories = _metadata_source_repositories(rendered)
    merged_repositories = _merge_metadata_source_repositories(current_repositories, desired_repositories)
    lines = current.splitlines()
    for key, value in (
        ('metadata_version', PROJECT_METADATA_VERSION),
        ('authority', 'canonical'),
        ('project_root', _yaml_scalar(rendered, 'project_root')),
    ):
        lines, _ = _replace_or_append_scalar(lines, key, value)
    lines, _ = _replace_top_level_block(lines, _source_repository_roles_block(), 'source_repository_roles')
    lines, _ = _replace_top_level_block(lines, _source_repositories_block(merged_repositories), 'source_repositories')
    return '\n'.join(lines).rstrip() + '\n'


def ensure_project_layout(project_root: Path) -> list[str]:
    """Create non-authority workspace structure without changing metadata or Git."""
    wb = project_root / '.work-bundle'
    knowledge = wb / 'knowledge'
    changed: list[str] = []
    if _ensure_lines(project_root / '.gitignore', REQUIRED_PROJECT_GITIGNORE):
        changed.append(str(project_root / '.gitignore'))
    for directory in _init_tree_roots():
        if directory == 'rules':
            directory = '.work-bundle/rules'
        path = project_root / directory
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            changed.append(str(path))
    for role in ROLE_NAMES:
        role_path = project_root / 'roles' / f'{role}.yaml'
        role_text = '\n'.join([
            f'id: {role}', 'status: current',
            'domain_profile: .work-bundle/project.yaml', 'duty_profile:',
            '  stance: project-specific role context must be resolved before work',
            '  skilled_at: []', '  quality_focus: []',
            '  must_resolve_from_context:', '    - project-metadata', '',
        ])
        if write(role_path, role_text, overwrite=False):
            changed.append(str(role_path))
    knowledge_project = knowledge / 'project.yaml'
    if write(knowledge_project, 'id: project\nstatus: current\n', overwrite=False):
        changed.append(str(knowledge_project))
    if _ensure_lines(wb / '.gitignore', _init_gitignore_patterns()):
        changed.append(str(wb / '.gitignore'))
    rule_index_path = _project_rule_store_root(project_root) / 'index.yaml'
    if write(
        rule_index_path,
        _require_reference_text(INIT_RULE_INDEX).rstrip() + '\n',
        overwrite=False,
    ):
        changed.append(str(rule_index_path))
    return sorted(set(changed))


def apply_project(
    project_root: Path,
    init_git: bool = True,
    create_override: bool = False,
    name: str | None = None,
    force: bool = False,
    scope: str = 'init',
    registry_entry_data: dict[str, object] | None = None,
    return_details: bool = False,
    workspace_root: Path | None = None,
    mode: str = 'single-repository',
) -> list[str] | tuple[list[str], dict[str, object]]:
    wb = project_root / '.work-bundle'
    knowledge = wb / 'knowledge'
    changed = ensure_project_layout(project_root)
    knowledge_project = knowledge / 'project.yaml'
    if _template_overwrite(project_root, knowledge_project, force, scope) and write(
        knowledge_project, 'id: project\nstatus: current\n', overwrite=True
    ):
        changed.append(str(knowledge_project))
    rule_index_path = _project_rule_store_root(project_root) / 'index.yaml'
    if _template_overwrite(project_root, rule_index_path, force, scope) and write(
        rule_index_path, _require_reference_text(INIT_RULE_INDEX).rstrip() + '\n', overwrite=True
    ):
        changed.append(str(rule_index_path))
    project_metadata_path = project_root / '.work-bundle/project.yaml'
    project_metadata = _render_project_metadata(project_root, name, registry_entry_data, workspace_root, mode)
    if project_metadata_path.is_file():
        current_metadata = read(project_metadata_path)
        current_version = _yaml_scalar(current_metadata, 'metadata_version')
        if current_version in {'1', '2'}:
            project_metadata = current_metadata
        elif registry_entry_data is not None:
            project_metadata = _refresh_registered_project_metadata(current_metadata, project_metadata)
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
    changed = sorted(set(changed))
    if return_details:
        return changed, agents_result
    return changed


def repair_project(project_root: Path, force: bool = False, return_details: bool = False) -> list[str] | tuple[list[str], dict[str, object]]:
    current_metadata = read(project_root / '.work-bundle/project.yaml')
    if (
        _yaml_scalar(current_metadata, 'metadata_version') == '3'
        and _yaml_scalar(current_metadata, 'workspace_mode') == 'multi-repository'
    ):
        changed = ensure_project_layout(project_root)
        changed.extend(ensure_workspace_resources(project_root))
        agents_result = sync_agents_managed_section(project_root, force=force)
        changed.extend(str(path) for path in agents_result.get('changed_files', []))
        changed = sorted(set(changed))
        if return_details:
            return changed, agents_result
        return changed
    registry_entry_data, _ = find_registry_entry(project_root)
    changed, agents_result = apply_project(
        project_root,
        init_git=False,
        force=force,
        scope='init' if force else 'migrate',
        registry_entry_data=registry_entry_data,
        return_details=True,
    )
    changed.extend(ensure_workspace_resources(project_root))
    data = inspect_project(project_root)
    metadata_path = project_root / '.work-bundle/project.yaml'
    if data.get('project_metadata_required_fields_missing') and not read(metadata_path).strip():
        rendered = _render_project_metadata(project_root)
        if write(metadata_path, rendered, overwrite=force):
            changed.append(str(metadata_path))
    if registry_entry_data is not None:
        metadata_changed, refreshed_path, _ = sync_project_metadata_from_registry_entry(
            registry_entry_data,
            fallback_root=project_root,
        )
        if metadata_changed:
            changed.append(str(refreshed_path))
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
    lines = [
        'source_repository_roles:',
        f"  registry: {_yaml_string(SOURCE_REPOSITORY_ROLES['registry'])}",
        f"  project_metadata: {_yaml_string(SOURCE_REPOSITORY_ROLES['project_metadata'])}",
        'projects:',
    ]
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
            source_id = str(source.get("id", "") or _source_repository_id(str(project.get("slug", "project"))))
            lines.append(f"      - id: {source_id}")
            lines.append(f"        path: {source.get('path', '')}")
            lines.append(f"        checkout_role: {_checkout_role(source, source_id)}")
            lines.append(f"        work_dir: {str(bool(source.get('work_dir', index == 0))).lower()}")
            remote = str(source.get("remote", ""))
            lines.append(f'        remote: "{remote}"' if remote else '        remote: ""')
            lines.append(f"        git_repository: {str(bool(source.get('git_repository', False))).lower()}")
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


def _registry_source_from_root(project_root: Path, name: str | None) -> dict[str, object]:
    entry = registry_entry(project_root, name)
    sources = entry.get("source_repositories")
    if isinstance(sources, list) and sources and isinstance(sources[0], dict):
        return sources[0]
    repo = _source_repository_state(project_root, _slug_from_root(project_root, name))
    return {
        "id": repo["id"],
        "path": repo["path"],
        "work_dir": True,
        "remote": repo["remote"],
        "git_repository": repo["git_repository"],
    }


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


def assess_legacy_topology(
    project_root: Path,
    metadata_text: str,
    registry_entry_data: dict[str, object] | None,
    registry_origin_data: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Classify legacy metadata without converting repository locators into members."""
    project_root = project_root.expanduser().resolve()
    metadata_sources = _metadata_source_repositories(metadata_text)
    registry_sources = (
        registry_entry_data.get('source_repositories')
        if isinstance(registry_entry_data, dict)
        else []
    )
    registry_sources = registry_sources if isinstance(registry_sources, list) else []

    def identities(sources: object) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if not isinstance(sources, list):
            return result
        for source in sources:
            if not isinstance(source, dict):
                continue
            raw_path = source.get('project_root') or source.get('origin_path') or source.get('path')
            result.append({
                'id': str(source.get('id') or ''),
                'path': str(Path(str(raw_path)).expanduser().resolve()) if raw_path else '',
            })
        return result

    metadata_identities = identities(metadata_sources)
    registry_identities = identities([*registry_sources, *(registry_origin_data or [])])
    registry_identities = [
        dict(identity)
        for identity in {
            (item['id'], item['path']): item
            for item in registry_identities
        }.values()
    ]
    conflicts: list[str] = []
    by_id: dict[str, set[str]] = {}
    for identity in [*metadata_identities, *registry_identities]:
        if identity['id'] and identity['path']:
            by_id.setdefault(identity['id'], set()).add(identity['path'])
    for source_id, paths in sorted(by_id.items()):
        if len(paths) > 1:
            conflicts.append(f'repository-id-path-conflict:{source_id}')

    paths = {
        identity['path']
        for identity in [*metadata_identities, *registry_identities]
        if identity['path']
    }
    if conflicts:
        classification = 'topology-conflict'
        failure_code = 'WB_MIGRATION_TOPOLOGY_CONFLICT'
    elif len(paths) > 1:
        classification = 'multi-repository-migration-required'
        failure_code = 'WB_MIGRATION_MULTI_REPOSITORY_WORKFLOW_REQUIRED'
    elif paths and paths != {str(project_root)}:
        classification = 'topology-conflict'
        failure_code = 'WB_MIGRATION_TOPOLOGY_CONFLICT'
    else:
        classification = 'single-compatible'
        failure_code = ''
    return {
        'classification': classification,
        'failure_code': failure_code,
        'metadata_sources': metadata_identities,
        'registry_sources': registry_identities,
        'distinct_repository_paths': sorted(paths),
        'conflicts': conflicts,
        'required_command': 'migrate-to-multi-repository' if classification == 'multi-repository-migration-required' else '',
    }


def _metadata_migration_proposal(
    project_root: Path,
    metadata_text: str,
    registry_path: Path,
    registry_entry_data: dict[str, object] | None,
    name: str | None,
    force: bool,
) -> dict[str, object]:
    topology = assess_legacy_topology(
        project_root,
        metadata_text,
        registry_entry_data,
        _registry_origin_locators(registry_path, registry_entry_data),
    )
    facts = {
        'project_root': str(project_root.resolve()),
        'name': name or '',
        'force': force,
        'metadata_sha256': hashlib.sha256(metadata_text.encode('utf-8')).hexdigest(),
        'registry_topology_sha256': hashlib.sha256(
            json.dumps(topology['registry_sources'], sort_keys=True).encode('utf-8')
        ).hexdigest(),
        'topology': topology,
    }
    proposal_id = hashlib.sha256(json.dumps(facts, sort_keys=True).encode('utf-8')).hexdigest()
    return {'id': proposal_id, **facts}


def _registry_origin_locators(
    registry_path: Path,
    registry_entry_data: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not registry_path.is_file() or not isinstance(registry_entry_data, dict):
        return []
    slug = str(registry_entry_data.get('slug') or '')
    if not slug:
        return []
    lines = registry_path.read_text(encoding='utf-8').splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith('  - slug:')]
    project_bounds: tuple[int, int] | None = None
    for position, start in enumerate(starts):
        value = lines[start].split(':', 1)[1].strip().strip('"\'')
        if value == slug:
            project_bounds = (start, starts[position + 1] if position + 1 < len(starts) else len(lines))
            break
    if project_bounds is None:
        return []
    start, end = project_bounds
    origin_start = next(
        (index for index in range(start + 1, end) if lines[index].startswith('    repository_origins:')),
        None,
    )
    if origin_start is None:
        return []
    origins: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in lines[origin_start + 1:end]:
        if line and not line.startswith('      '):
            break
        if line.startswith('      - '):
            if current is not None:
                origins.append(current)
            current = {}
            item = line.strip()[2:]
            if ':' in item:
                key, value = item.split(':', 1)
                current[key.strip()] = value.strip().strip('"\'')
        elif current is not None and line.startswith('        ') and ':' in line:
            key, value = line.strip().split(':', 1)
            current[key.strip()] = value.strip().strip('"\'')
    if current is not None:
        origins.append(current)
    return origins


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
    version = _yaml_scalar(metadata, 'metadata_version')
    required = PROJECT_METADATA_V3_REQUIRED_FIELDS if version == '3' else PROJECT_METADATA_V2_REQUIRED_FIELDS
    missing = [field for field in required if f'{field}:' not in metadata]
    if version not in {'2', '3'}:
        missing.insert(0, 'metadata_version[2|3]')
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
    parser.add_argument("--mode", choices=['single-repository', 'multi-repository'])
    parser.add_argument("--workspace-root")
    parser.add_argument("--name")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-work-bundle-git", action="store_true")
    parser.add_argument("--create-project-skill-override", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    workspace_root = Path(parsed.workspace_root).expanduser().resolve() if parsed.workspace_root else project_root
    existing_metadata = read(workspace_root / '.work-bundle/project.yaml')
    declared_mode = _yaml_scalar(existing_metadata, 'workspace_mode')
    if parsed.mode is None and not declared_mode:
        out({
            'command': 'init-project',
            'status': 'issues-found',
            'mode': None,
            'dry_run': parsed.dry_run,
            'changed_files': [],
            'git_actions': [],
            'failures': ['WB_WORKSPACE_MODE_REQUIRED'],
        })
        return 1
    mode = parsed.mode or declared_mode
    try:
        WorkspaceContext(workspace_root, mode, project_root if mode == 'single-repository' else None).validate()
    except ValueError as exc:
        out({'command': 'init-project', 'status': 'issues-found', 'failures': [str(exc)]})
        return 1
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
        resource_changes = ensure_workspace_resources(workspace_root)
        existing_entry, _ = find_registry_entry(project_root)
        try:
            changed, agents_result = apply_project(
                project_root,
                init_git=not parsed.disable_work_bundle_git,
                create_override=parsed.create_project_skill_override,
                name=parsed.name,
                force=parsed.force,
                scope='init',
                registry_entry_data=existing_entry,
                return_details=True,
                workspace_root=workspace_root,
                mode=mode,
            )
        except ReferenceAssetError as exc:
            out(_reference_failure_payload(exc, 'init-project'))
            return 1
        entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
        if registry_changed and isinstance(changed, list):
            changed.append(str(registry))
        if isinstance(changed, list):
            changed.extend(resource_changes)
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
        "mode": mode,
        "dry_run": parsed.dry_run,
        "git_actions": [],
        "transaction": {
            "id": f"init-{_slug_from_root(workspace_root, parsed.name)}",
            "state": "proposed" if parsed.dry_run else ("published" if not failures else "failed"),
            "owned_paths": sorted(set(changed if isinstance(changed, list) else [])) if not parsed.dry_run else [],
            "registry_status": "unchanged" if parsed.dry_run else ("published" if not failures else "failed"),
            "metadata_status": "unchanged" if parsed.dry_run else ("published" if not failures else "failed"),
        },
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
    entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
    metadata_changed, metadata_path, metadata_status = sync_project_metadata_from_registry_entry(entry, parsed.name, project_root)
    changed_files: list[str] = []
    if registry_changed:
        changed_files.append(str(registry))
    if metadata_changed:
        changed_files.append(str(metadata_path))
    out({
        "command": "register-project",
        "status": "updated" if changed_files else "skipped",
        "registry_path": str(registry),
        "registry_entry": entry,
        "project": entry,
        "project_metadata_path": str(metadata_path),
        "project_metadata_status": metadata_status,
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
    selected_root = parsed.project_root or parsed.workspace_root or "."
    project_root = Path(selected_root).expanduser().resolve()
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


def cmd_provision_member(args: list[str]) -> int:
    from member import MemberLifecycleError, provision_member_lifecycle
    parser = argparse.ArgumentParser(prog='wb.py provision-member')
    parser.add_argument('--workspace-root', required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--repository-id', required=True)
    parser.add_argument('--working-branch', required=True)
    parser.add_argument('--base-ref', default='HEAD')
    parser.add_argument('--workspace-slug')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parsed = parser.parse_args(args)
    workspace_root = Path(parsed.workspace_root).expanduser().resolve()
    origin = Path(parsed.origin).expanduser().resolve()
    try:
        result = provision_member_lifecycle(
            workspace_root,
            origin,
            parsed.repository_id,
            parsed.working_branch,
            parsed.base_ref,
            workspace_slug=parsed.workspace_slug,
            dry_run=parsed.dry_run,
        )
    except MemberLifecycleError as exc:
        out({
            'command': 'provision-member',
            'status': 'issues-found',
            'mode': 'multi-repository',
            'dry_run': parsed.dry_run,
            'failure_code': exc.code,
            'failures': [exc.code],
            'result': exc.result,
            'git_actions': [],
        })
        return 1
    out({'command': 'provision-member', **result})
    return 0


def cmd_cleanup_member(args: list[str]) -> int:
    from member import MemberLifecycleError, cleanup_member_lifecycle
    parser = argparse.ArgumentParser(prog='wb.py cleanup-member')
    parser.add_argument('--workspace-root', required=True)
    parser.add_argument('--repository-id', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parsed = parser.parse_args(args)
    try:
        result = cleanup_member_lifecycle(
            Path(parsed.workspace_root), parsed.repository_id, dry_run=parsed.dry_run
        )
    except MemberLifecycleError as exc:
        out({
            'command': 'cleanup-member', 'status': 'issues-found',
            'failure_code': exc.code, 'failures': [exc.code],
            'result': exc.result, 'git_actions': [],
        })
        return 1
    out({'command': 'cleanup-member', **result})
    return 0


def cmd_migrate_to_multi_repository(args: list[str]) -> int:
    from migration import MigrationError
    parser = argparse.ArgumentParser(prog='wb.py migrate-to-multi-repository')
    parser.add_argument('source_project_root')
    parser.add_argument('--target-workspace-root', required=True)
    parser.add_argument('--repository-id', required=True)
    parser.add_argument('--repository-name', required=True)
    parser.add_argument(
        '--origin',
        help='Git repository used to provision the primary member; defaults to source_project_root',
    )
    parser.add_argument('--workspace-slug', required=True)
    parser.add_argument('--working-branch', required=True)
    parser.add_argument('--base-ref', default='HEAD')
    parser.add_argument('--accepted-baseline-id')
    parser.add_argument('--additional-origin', action='append', default=[], metavar='ID=PATH')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true'); mode.add_argument('--apply', action='store_true')
    parsed = parser.parse_args(args)
    source_root = Path(parsed.source_project_root).expanduser().resolve()
    primary_origin = Path(parsed.origin).expanduser().resolve() if parsed.origin else source_root
    if not parsed.origin and not _is_git_repository(source_root):
        out({
            'command': 'migrate-to-multi-repository', 'status': 'issues-found',
            'failure_code': 'WB_MIGRATION_ORIGIN_REQUIRED',
        })
        return 1
    if not _is_git_repository(primary_origin):
        out({
            'command': 'migrate-to-multi-repository', 'status': 'issues-found',
            'failure_code': 'WB_MIGRATION_ORIGIN_INVALID',
        })
        return 1
    declared_paths = {
        Path(str(item.get('path') or item.get('project_root') or '')).expanduser().resolve()
        for item in _metadata_source_repositories(read(source_root / '.work-bundle/project.yaml'))
        if str(item.get('path') or item.get('project_root') or '')
    }
    source_registry_entry, _ = find_registry_entry(source_root)
    if isinstance(source_registry_entry, dict):
        for item in source_registry_entry.get('source_repositories', []):
            if isinstance(item, dict) and str(item.get('path') or ''):
                declared_paths.add(Path(str(item['path'])).expanduser().resolve())
    if parsed.origin and declared_paths and primary_origin not in declared_paths:
        out({
            'command': 'migrate-to-multi-repository', 'status': 'issues-found',
            'failure_code': 'WB_MIGRATION_ORIGIN_NOT_DECLARED',
        })
        return 1
    additional_origins: list[dict[str, object]] = []
    for value in parsed.additional_origin:
        if '=' not in value:
            parser.error('--additional-origin must use ID=PATH')
        origin_id, origin_path = value.split('=', 1)
        if not origin_id or not origin_path:
            parser.error('--additional-origin must use non-empty ID=PATH')
        additional_origins.append({
            'id': origin_id,
            'origin_path': str(Path(origin_path).expanduser().resolve()),
            'remote': '',
            'git_repository': (Path(origin_path).expanduser() / '.git').exists(),
        })
    try:
        result = migrate_project_metadata_v3(
            source_root, Path(parsed.target_workspace_root),
            parsed.repository_id, parsed.working_branch, parsed.base_ref, parsed.apply,
            origin=primary_origin,
            workspace_slug=parsed.workspace_slug, repository_name=parsed.repository_name,
            accepted_baseline_id=parsed.accepted_baseline_id,
            additional_repository_origins=additional_origins,
        )
    except (MigrationError, ValueError, RuntimeError) as exc:
        out({'command':'migrate-to-multi-repository','status':'issues-found','failure_code':str(exc)})
        return 1
    out({'command':'migrate-to-multi-repository','status':'passed','result':result})
    return 0


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
    parser.add_argument("--accepted-proposal-id")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    parsed = parser.parse_args(args)
    project_root = Path(parsed.project_root).expanduser().resolve()
    before = inspect_project(project_root)
    metadata_path = project_root / '.work-bundle/project.yaml'
    current_text = read(metadata_path)
    current_version = _yaml_scalar(current_text, 'metadata_version')
    registry_entry_data, registry = find_registry_entry(project_root)
    proposal_evidence = _metadata_migration_proposal(
        project_root, current_text, registry, registry_entry_data, parsed.name, parsed.force
    )
    topology = proposal_evidence['topology']
    if not parsed.apply:
        proposal = ''
        if topology['classification'] == 'single-compatible':
            proposal = _render_project_metadata(project_root, parsed.name, registry_entry_data)
        topology_failure = str(topology.get('failure_code') or '')
        failures = (
            [topology_failure]
            if topology_failure
            else ([] if parsed.dry_run else ['WB_MIGRATION_EXPLICIT_ACTION_REQUIRED'])
        )
        data = {
            'command': 'migrate-project',
            'status': 'passed' if parsed.dry_run and not failures else 'issues-found',
            'mode': 'single-repository' if topology['classification'] == 'single-compatible' else topology['classification'],
            'dry_run': True,
            'changed_files': [],
            'git_actions': [],
            'failures': failures,
            'topology_assessment': topology,
            'migration': {
                'from_version': current_version,
                'to_version': PROJECT_METADATA_VERSION,
                'preserves_unknown_fields': True,
                'proposed_sha256': hashlib.sha256(proposal.encode('utf-8')).hexdigest() if proposal else '',
                'proposal_id': proposal_evidence['id'],
                'apply_requires_accepted_proposal': current_version == '2',
            },
            'transaction': {
                'id': f"metadata-{_slug_from_root(project_root, parsed.name)}",
                'state': 'proposed',
                'owned_paths': [str(metadata_path)],
                'registry_status': 'unchanged',
                'metadata_status': 'pending',
            },
        }
        out(data)
        return 0 if parsed.dry_run and not failures else 1
    if topology['classification'] != 'single-compatible':
        failure_code = str(topology.get('failure_code') or 'WB_MIGRATION_TOPOLOGY_CONFLICT')
        out({
            'command': 'migrate-project',
            'status': 'issues-found',
            'mode': topology['classification'],
            'dry_run': False,
            'failures': [failure_code],
            'topology_assessment': topology,
            'changed_files': [],
            'git_actions': [],
        })
        return 1
    if current_version == '2' and not parsed.accepted_proposal_id:
        out({
            'command': 'migrate-project', 'status': 'issues-found', 'dry_run': False,
            'failures': ['WB_MIGRATION_PROPOSAL_REQUIRED'], 'changed_files': [], 'git_actions': [],
            'proposal_id': proposal_evidence['id'],
        })
        return 1
    if current_version == '2' and parsed.accepted_proposal_id != proposal_evidence['id']:
        out({
            'command': 'migrate-project', 'status': 'issues-found', 'dry_run': False,
            'failures': ['WB_MIGRATION_PROPOSAL_STALE'], 'changed_files': [], 'git_actions': [],
            'proposal_id': proposal_evidence['id'],
        })
        return 1
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
    entry, registry_changed, registry = upsert_project_registry(project_root, parsed.name)
    if registry_changed:
        changed.append(str(registry))
    if migrate_project_metadata_v2(project_root, parsed.name, entry):
        changed.append(str(project_root / '.work-bundle/project.yaml'))
    contract_changed, retired_rules_contract, rules_contract_archive = _retire_legacy_rules_contract(project_root)
    changed.extend(contract_changed)
    bootstrap_changed, retired_artifacts, archive_root = _cleanup_retired_bootstrap(project_root)
    changed.extend(bootstrap_changed)
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
        "mode": _yaml_scalar(read(metadata_path), 'workspace_mode') or 'single-repository',
        "dry_run": False,
        "git_actions": [],
        "transaction": {
            "id": f"metadata-{_slug_from_root(project_root, parsed.name)}",
            "state": "published" if not failures else "failed",
            "owned_paths": sorted(set(changed)),
            "registry_status": "published" if registry_changed else "unchanged",
            "metadata_status": "published" if str(metadata_path) in changed else "unchanged",
        },
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
    failures = project_failures(data, strict=parsed.repair, include_roles=True)
    data.update({
        'command': 'doctor-project',
        'status': 'passed' if not failures else 'issues-found',
        'failures': failures,
        'changed_files': sorted(set(changed)),
        'agents_status': agents_result.get('agents_status'),
        'agents_sync': _agents_sync_output(agents_result),
        'mode': _yaml_scalar(read(project_root / '.work-bundle/project.yaml'), 'workspace_mode') or 'single-repository-compatibility',
        'dry_run': not parsed.repair,
        'git_actions': [],
        'finding_classification': {
            'repairable': [item for item in failures if item in {'project_gitignore', 'project_ignores_work_bundle', 'project_ignores_agents', 'agents_md', 'work_bundle', 'work_bundle_gitignore', 'knowledge_root', 'orchestration_root', 'rules_root', 'rule_index'}],
            'advisory': [item for item in failures if item.endswith('baseline_status_stale')],
            'blocking': [item for item in failures if item not in {'project_gitignore', 'project_ignores_work_bundle', 'project_ignores_agents', 'agents_md', 'work_bundle', 'work_bundle_gitignore', 'knowledge_root', 'orchestration_root', 'rules_root', 'rule_index'} and not item.endswith('baseline_status_stale')],
        },
        'transaction': {
            'id': f"doctor-{_slug_from_root(project_root)}",
            'state': 'published' if parsed.repair and not failures else ('failed' if parsed.repair else 'proposed'),
            'owned_paths': sorted(set(changed)),
            'registry_status': 'unchanged',
            'metadata_status': 'published' if str(project_root / '.work-bundle/project.yaml') in changed else 'unchanged',
        },
    })
    out(data)
    return 0 if not failures else 1


def cmd_project(args: list[str], apply: bool = False, inspect_only: bool = False, repo_model: bool = False) -> int:
    if apply:
        return cmd_init_project(args)
    if inspect_only:
        return cmd_show_project(["--project-root", args[0]] if args else [])
    return cmd_validate_project(args)
