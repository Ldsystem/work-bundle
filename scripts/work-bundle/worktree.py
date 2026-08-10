from __future__ import annotations

import json
import shutil
import subprocess
import re
from pathlib import Path

from workspace import WorkspaceTransaction


class ProvisionMemberError(RuntimeError):
    def __init__(self, code: str, result: dict[str, object]) -> None:
        super().__init__(code)
        self.code = code
        self.result = result


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(['git', *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'WB_GIT_FAILED')
    return result.stdout.strip()


def _inside(root: Path, candidate: Path) -> bool:
    root, candidate = root.resolve(), candidate.resolve()
    return candidate == root or root in candidate.parents


def verify_git_control_scope(workspace_root: Path, project_root: Path) -> dict[str, str | bool]:
    common = Path(_git('-C', str(project_root), 'rev-parse', '--path-format=absolute', '--git-common-dir'))
    valid = _inside(workspace_root, project_root) and _inside(workspace_root, common)
    return {'valid': valid, 'project_root': str(project_root.resolve()), 'git_common_dir': str(common.resolve())}


def _remove_created_member(
    control: Path,
    target: Path,
    branch: str,
    *,
    keep_control: bool,
    keep_target: bool,
    delete_branch: bool,
) -> dict[str, object]:
    if control.exists() and target.exists():
        subprocess.run(
            ['git', '--git-dir', str(control), 'worktree', 'remove', '--force', str(target)],
            text=True,
            capture_output=True,
            check=False,
        )
    if target.exists():
        shutil.rmtree(target)
    if keep_target:
        target.mkdir(parents=True, exist_ok=True)
    if control.exists() and keep_control and delete_branch:
        subprocess.run(
            ['git', '--git-dir', str(control), 'branch', '-D', branch],
            text=True,
            capture_output=True,
            check=False,
        )
    if control.exists() and not keep_control:
        shutil.rmtree(control)
    return {
        'state': 'completed',
        'control_preserved': keep_control,
        'target_preserved': keep_target,
    }


def _provision_failure(
    transaction: WorkspaceTransaction,
    workspace_root: Path,
    repository_id: str,
    code: str,
    rollback: dict[str, object],
) -> ProvisionMemberError:
    result = transaction.fail(code)
    result.update({
        'registry_status': 'unchanged',
        'metadata_status': 'unchanged',
        'rollback': rollback,
    })
    recovery = workspace_root / '.work-bundle' / 'transactions' / f'provision-{repository_id}.json'
    transaction.own(recovery)
    recovery.parent.mkdir(parents=True, exist_ok=True)
    recovery.write_text(
        json.dumps(
            {
                'id': transaction.transaction_id,
                'state': 'failed',
                'failure_code': code,
                'registry_status': 'unchanged',
                'metadata_status': 'unchanged',
                'rollback': rollback,
            },
            sort_keys=True,
        ) + '\n',
        encoding='utf-8',
    )
    result['owned_paths'] = [str(path) for path in sorted(transaction.changed_paths)]
    result['recovery_record'] = str(recovery)
    return ProvisionMemberError(code, result)


def provision_member(workspace_root: Path, origin: Path, repository_id: str, branch: str, base_ref: str = 'HEAD') -> dict[str, object]:
    workspace_root = workspace_root.resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', repository_id):
        raise ValueError('WB_REPOSITORY_ID_INVALID')
    control = workspace_root / '.work-bundle' / 'git' / f'{repository_id}.git'
    target = workspace_root / repository_id
    transaction = WorkspaceTransaction(workspace_root, f'provision-{repository_id}')
    transaction.own(control)
    transaction.own(target)
    if target.exists() and any(target.iterdir()):
        raise ValueError('WB_WORKTREE_TARGET_COLLISION')
    control_preexisting = control.exists()
    target_preexisting = target.exists()
    attempted_add = False
    try:
        control.parent.mkdir(parents=True, exist_ok=True)
        if not control_preexisting:
            _git('clone', '--bare', '--no-hardlinks', str(origin.resolve()), str(control))
        branches = _git('--git-dir', str(control), 'worktree', 'list', '--porcelain')
        if f'branch refs/heads/{branch}' in branches:
            raise RuntimeError('WB_WORKTREE_BRANCH_CONFLICT')
        attempted_add = True
        _git('--git-dir', str(control), 'worktree', 'add', '-b', branch, str(target), base_ref)
        verification = verify_git_control_scope(workspace_root, target)
        if not verification['valid']:
            raise RuntimeError('WB_GIT_CONTROL_SCOPE_EXTERNAL')
    except (OSError, RuntimeError) as exc:
        code = str(exc) or 'WB_GIT_FAILED'
        rollback = _remove_created_member(
            control,
            target,
            branch,
            keep_control=control_preexisting,
            keep_target=target_preexisting,
            delete_branch=attempted_add,
        )
        raise _provision_failure(transaction, workspace_root, repository_id, code, rollback) from exc
    transaction.state = 'verified'
    recovery = workspace_root / '.work-bundle' / 'transactions' / f'provision-{repository_id}.json'
    recovery.unlink(missing_ok=True)
    transaction_result = transaction.result()
    transaction_result.update({'registry_status': 'pending', 'metadata_status': 'pending'})
    return {
        'repository_id': repository_id,
        'project_root': str(target),
        'git_control_root': str(control),
        'branch': branch,
        'base_ref': base_ref,
        'verification': verification,
        'transaction': transaction_result,
        'git_actions': [],
    }
