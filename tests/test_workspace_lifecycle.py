from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
import os
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / 'scripts' / 'work-bundle'
sys.path.insert(0, str(MODULES))
from workspace import WorkspaceContext, WorkspaceTransaction
from workspace_resources import SCRIPT_INDEX_TEMPLATE, ensure_workspace_resources, validate_script_index
import worktree
from worktree import ProvisionMemberError, provision_member, verify_git_control_scope


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def seed(root: Path) -> None:
    root.mkdir()
    subprocess.run(['git', '-C', str(root), 'init', '-q', '-b', 'main'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Test'], check=True)
    (root / 'README.md').write_text('seed\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(root), 'add', 'README.md'], check=True)
    subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'seed'], check=True)


def test_workspace_context_and_resources(tmp_path: Path) -> None:
    WorkspaceContext(tmp_path, 'single-repository', tmp_path).validate()
    changed = ensure_workspace_resources(tmp_path)
    assert len(changed) == 2
    assert ensure_workspace_resources(tmp_path) == []
    assert validate_script_index(tmp_path) == []
    assert (tmp_path / 'credentials').stat().st_mode & 0o777 == 0o700
    assert (tmp_path / 'credentials/credentials.yaml').stat().st_mode & 0o777 == 0o600


def test_two_workspaces_have_independent_git_control(tmp_path: Path) -> None:
    origin = tmp_path / 'origin'
    seed(origin)
    first = provision_member(tmp_path / 'one', origin, 'repo', 'feature-one')
    second = provision_member(tmp_path / 'two', origin, 'repo', 'feature-two')
    assert first['git_control_root'] != second['git_control_root']
    assert verify_git_control_scope(tmp_path / 'one', Path(first['project_root']))['valid']
    assert git(origin, 'branch', '--show-current') == 'main'
    (origin / 'DIRTY').write_text('preserve\n', encoding='utf-8')
    assert '?? DIRTY' in git(origin, 'status', '--short')
    Path(first['project_root']).joinpath('README.md').read_text(encoding='utf-8')
    origin.rename(tmp_path / 'origin-inaccessible')
    assert git(Path(first['project_root']), 'status', '--short') == ''


def test_collision_and_branch_conflict_fail_closed(tmp_path: Path) -> None:
    origin = tmp_path / 'origin'
    seed(origin)
    workspace = tmp_path / 'workspace'
    provision_member(workspace, origin, 'repo', 'feature')
    try:
        provision_member(workspace, origin, 'repo', 'feature')
    except ValueError as exc:
        assert str(exc) in {'WB_WORKTREE_TARGET_COLLISION', 'WB_WORKTREE_BRANCH_CONFLICT'}
    else:
        raise AssertionError('collision was not rejected')


def _index_entry(script_id: str, path: str) -> str:
    contract = SCRIPT_INDEX_TEMPLATE.replace('scripts: []\n', 'scripts:\n')
    return contract + f'''  - id: {script_id}
    path: {path}
    description: fixture
    functionality: validates-only
    use_cases: [test]
    runtime: python3
    invocation: python3 {path}
    dependencies: []
    applicable_repositories: []
    operation: read-only
    credentials: []
    inputs: []
    outputs: []
    safety_notes: []
'''


def test_script_index_validation_is_structural_contained_and_non_executing(tmp_path: Path) -> None:
    ensure_workspace_resources(tmp_path)
    utility = tmp_path / 'script/tool.py'
    marker = tmp_path / 'EXECUTED'
    utility.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")\n', encoding='utf-8')
    index = tmp_path / 'script/index.yaml'
    index.write_text(_index_entry('tool', 'script/tool.py'), encoding='utf-8')
    assert validate_script_index(tmp_path) == []
    assert not marker.exists()

    index.write_text(_index_entry('tool', 'script/tool.py') + _index_entry('tool', 'script/tool.py').split('scripts:\n', 1)[1], encoding='utf-8')
    assert 'WB_SCRIPT_INDEX_DUPLICATE_ID' in validate_script_index(tmp_path)
    index.write_text(_index_entry('escape', 'script/../outside.py'), encoding='utf-8')
    assert 'WB_SCRIPT_INDEX_PATH_ESCAPE' in validate_script_index(tmp_path)
    index.write_text(_index_entry('stale', 'script/missing.py'), encoding='utf-8')
    assert 'WB_SCRIPT_INDEX_STALE_PATH' in validate_script_index(tmp_path)
    index.write_text(SCRIPT_INDEX_TEMPLATE, encoding='utf-8')
    assert 'WB_SCRIPT_INDEX_ORPHAN:tool.py' in validate_script_index(tmp_path)
    assert not marker.exists()


def test_script_index_rejects_symlink_without_executing(tmp_path: Path) -> None:
    ensure_workspace_resources(tmp_path)
    target = tmp_path / 'target.py'
    target.write_text('raise SystemExit("executed")\n', encoding='utf-8')
    link = tmp_path / 'script/link.py'
    os.symlink(target, link)
    (tmp_path / 'script/index.yaml').write_text(_index_entry('link', 'script/link.py'), encoding='utf-8')
    failures = validate_script_index(tmp_path)
    assert 'WB_SCRIPT_INDEX_PATH_ESCAPE' in failures or 'WB_SCRIPT_INDEX_SYMLINK_FORBIDDEN' in failures


def test_script_index_enforces_closed_contract_and_nested_shapes(tmp_path: Path) -> None:
    ensure_workspace_resources(tmp_path)
    utility = tmp_path / 'script/tool.py'
    utility.write_text('pass\n', encoding='utf-8')
    index = tmp_path / 'script/index.yaml'

    index.write_text('version: 1\nentry_contract:\n  required: []\nscripts: []\n', encoding='utf-8')
    assert validate_script_index(tmp_path) == ['WB_SCRIPT_INDEX_CONTRACT_INVALID']

    valid = _index_entry('tool', 'script/tool.py')
    index.write_text(valid.replace('    invocation: python3 script/tool.py', '    invocation:\n      command: python3 script/tool.py'), encoding='utf-8')
    assert any('INVOCATION_INVALID' in failure for failure in validate_script_index(tmp_path))

    index.write_text(valid.replace('    dependencies: []', '    dependencies:\n      name: unsafe-shape'), encoding='utf-8')
    assert any('DEPENDENCIES_INVALID' in failure for failure in validate_script_index(tmp_path))

    index.write_text(valid.replace('    credentials: []', '    credentials: [valid-id, invalid/id]'), encoding='utf-8')
    assert any('CREDENTIALS_INVALID' in failure for failure in validate_script_index(tmp_path))

    index.write_text(valid.replace('    safety_notes: []', '    safety_notes: []\n    unknown: rejected'), encoding='utf-8')
    assert any('FIELDS_UNKNOWN' in failure for failure in validate_script_index(tmp_path))


@pytest.mark.parametrize('stage', ['clone', 'worktree-add', 'verify'])
def test_provision_member_failure_rolls_back_new_state_and_retains_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    origin = tmp_path / 'origin'
    seed(origin)
    workspace = tmp_path / f'workspace-{stage}'
    original_git = worktree._git
    original_verify = worktree.verify_git_control_scope

    def failing_git(*args: str, cwd: Path | None = None) -> str:
        if stage == 'clone' and args and args[0] == 'clone':
            raise RuntimeError('WB_TEST_CLONE_FAILURE')
        if stage == 'worktree-add' and 'add' in args:
            raise RuntimeError('WB_TEST_WORKTREE_ADD_FAILURE')
        return original_git(*args, cwd=cwd)

    monkeypatch.setattr(worktree, '_git', failing_git)
    if stage == 'verify':
        monkeypatch.setattr(worktree, 'verify_git_control_scope', lambda *_: {'valid': False})

    with pytest.raises(ProvisionMemberError) as caught:
        provision_member(workspace, origin, 'repo', 'feature')
    result = caught.value.result
    assert result['state'] == 'failed'
    assert result['registry_status'] == 'unchanged'
    assert result['metadata_status'] == 'unchanged'
    assert result['rollback']['state'] == 'completed'
    assert not (workspace / 'repo').exists()
    assert not (workspace / '.work-bundle/git/repo.git').exists()
    recovery = Path(result['recovery_record'])
    assert recovery.is_file()
    assert 'origin' not in recovery.read_text(encoding='utf-8')

    monkeypatch.setattr(worktree, '_git', original_git)
    monkeypatch.setattr(worktree, 'verify_git_control_scope', original_verify)
    retried = provision_member(workspace, origin, 'repo', 'feature')
    assert retried['transaction']['state'] == 'verified'
    assert not recovery.exists()


def test_provision_member_failure_preserves_preexisting_control_and_empty_target(tmp_path: Path) -> None:
    origin = tmp_path / 'origin'
    seed(origin)
    workspace = tmp_path / 'workspace'
    control = workspace / '.work-bundle/git/repo.git'
    target = workspace / 'repo'
    control.parent.mkdir(parents=True)
    subprocess.run(['git', 'clone', '--bare', '--no-hardlinks', str(origin), str(control)], check=True, capture_output=True)
    target.mkdir(parents=True)

    with pytest.raises(ProvisionMemberError) as caught:
        provision_member(workspace, origin, 'repo', 'feature', 'missing-base-ref')
    assert control.is_dir()
    assert target.is_dir() and not any(target.iterdir())
    assert caught.value.result['rollback']['control_preserved'] is True
    assert caught.value.result['rollback']['target_preserved'] is True

    retried = provision_member(workspace, origin, 'repo', 'feature', 'HEAD')
    assert Path(retried['project_root']).is_dir()


def test_workspace_transaction_is_atomic_recoverable_and_bounded(tmp_path: Path) -> None:
    first = tmp_path / 'one.yaml'
    second = tmp_path / 'two.yaml'
    first.write_text('before\n', encoding='utf-8')
    transaction = WorkspaceTransaction(tmp_path, 'fixture')
    transaction.stage_text(first, 'after\n')
    transaction.stage_text(second, 'created\n')
    result = transaction.publish(lambda: True)
    assert result['state'] == 'published'
    assert first.read_text(encoding='utf-8') == 'after\n'
    assert second.read_text(encoding='utf-8') == 'created\n'
    rollback = transaction.rollback()
    assert rollback['state'] == 'rolled-back'
    assert first.read_text(encoding='utf-8') == 'before\n'
    assert not second.exists()
    try:
        transaction.stage_text(tmp_path.parent / 'escape', 'bad')
    except ValueError as exc:
        assert str(exc) == 'WB_TRANSACTION_PATH_ESCAPE'
    else:
        raise AssertionError('transaction path escape was not rejected')
