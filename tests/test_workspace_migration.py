from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/work-bundle'))

import migration
from migration import (
    MigrationError,
    MigrationTransaction,
    TRANSACTION_STAGES,
    apply_migration,
    inspect_migration,
    propose_migration,
    retry_transaction,
    rollback_owned_paths,
    source_git_state,
    work_bundle_git_state,
)
from workspace_resources import SCRIPT_INDEX_TEMPLATE


def test_reviewer_fixture_preserves_work_bundle_lazy_import_resolution(isolated_reviewer_receipt_store):
    # The global reviewer fixture is active before this lazy import chain.
    import project
    import bootstrap_config
    import core
    assert Path(core.__file__).resolve().parent == Path(migration.__file__).resolve().parent
    assert bootstrap_config.GLOBAL_BOOTSTRAP_FILE_NAME == core.GLOBAL_BOOTSTRAP_FILE_NAME


def test_reviewer_runtime_loading_preserves_work_bundle_import_namespace(tmp_path):
    script = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import core
import reviewer_workspace
original_path = list(sys.path)
runtime = reviewer_workspace._review_runtime()
artifact = Path(sys.argv[2])
assert runtime.artifact_review_identity(artifact)["artifact_id"] == "spec-test"
assert sys.path == original_path
import project, bootstrap_config
assert bootstrap_config.GLOBAL_BOOTSTRAP_FILE_NAME == core.GLOBAL_BOOTSTRAP_FILE_NAME
assert "execution_context" not in sys.modules
'''
    artifact = tmp_path / "spec.md"
    artifact.write_text("---\nid: spec-test\n---\nTest\n")
    result = subprocess.run([sys.executable, "-c", script, str(Path(migration.__file__).parent), str(artifact)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def seed(root: Path, *, dirty_source: bool = True, dirty_nested: bool = True) -> None:
    root.mkdir()
    subprocess.run(['git', '-C', str(root), 'init', '-q', '-b', 'main'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Test'], check=True)
    (root / '.gitignore').write_text('.work-bundle/\nscript/\ncredentials/\nAGENTS.md\n', encoding='utf-8')
    (root / 'README.md').write_text('seed\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(root), 'add', '.gitignore', 'README.md'], check=True)
    subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'seed'], check=True)

    wb = root / '.work-bundle'
    (wb / 'orchestration').mkdir(parents=True)
    (wb / 'project.yaml').write_text(
        'metadata_version: 2\nauthority: canonical\ncustom_preserved:\n  value: yes\n',
        encoding='utf-8',
    )
    (wb / 'unknown').mkdir()
    unknown = wb / 'unknown' / 'maintain.sh'
    unknown.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
    unknown.chmod(0o750)
    os.utime(unknown, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    subprocess.run(['git', '-C', str(wb), 'init', '-q', '-b', 'knowledge-main'], check=True)
    subprocess.run(['git', '-C', str(wb), 'config', 'user.email', 'test@example.com'], check=True)
    subprocess.run(['git', '-C', str(wb), 'config', 'user.name', 'Test'], check=True)
    subprocess.run(['git', '-C', str(wb), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(wb), 'commit', '-q', '-m', 'authority'], check=True)
    (wb / 'history.txt').write_text('history\n', encoding='utf-8')
    subprocess.run(['git', '-C', str(wb), 'add', 'history.txt'], check=True)
    subprocess.run(['git', '-C', str(wb), 'commit', '-q', '-m', 'history'], check=True)
    (wb / '.cache').mkdir()
    (wb / '.cache' / 'ignored.bin').write_bytes(b'cache')
    if dirty_nested:
        (wb / 'nested-dirty.txt').write_text('accepted dirty state\n', encoding='utf-8')

    (root / 'script').mkdir()
    (root / 'script' / 'index.yaml').write_text(SCRIPT_INDEX_TEMPLATE, encoding='utf-8')
    (root / 'credentials').mkdir()
    synthetic_value = ''.join(('fixture', '-', 'private', '-', 'value'))
    (root / 'credentials' / 'credentials.yaml').write_text(synthetic_value, encoding='utf-8')
    (root / 'AGENTS.md').write_text('user-authored heading\n', encoding='utf-8')
    if dirty_source:
        (root / 'README.md').write_text('seed\naccepted dirty state\n', encoding='utf-8')


def source_snapshot(root: Path) -> dict[str, object]:
    return {
        'repo': source_git_state(root),
        'nested': work_bundle_git_state(root),
        'repo_head': git(root, 'rev-parse', 'HEAD'),
        'nested_head': git(root / '.work-bundle', 'rev-parse', 'HEAD'),
        'unknown': (root / '.work-bundle/unknown/maintain.sh').read_bytes(),
        'unknown_mode': stat.S_IMODE((root / '.work-bundle/unknown/maintain.sh').stat().st_mode),
        'unknown_mtime': (root / '.work-bundle/unknown/maintain.sh').stat().st_mtime_ns,
        'agents': (root / 'AGENTS.md').read_bytes(),
    }


def registry(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        'registry_note: preserve\nprojects:\n  - slug: existing\n    name: "Existing"\n    status: active\n',
        encoding='utf-8',
    )


def proposal(source: Path, target: Path) -> dict[str, object]:
    return propose_migration(
        source,
        target,
        'repo-one',
        'feature/workspace',
        'HEAD',
        workspace_slug='workspace-one',
        repository_name='Repository One',
        additional_repository_origins=[{
            'id': 'repo-two',
            'origin_path': '/non-sensitive/origin-two',
            'remote': '',
            'git_repository': True,
        }],
    )


def apply(source: Path, target: Path, registry_path: Path, *, fail_stage: str | None = None) -> dict[str, object]:
    dry_run = proposal(source, target)
    return apply_migration(
        source,
        target,
        'repo-one',
        'feature/workspace',
        'HEAD',
        workspace_slug='workspace-one',
        repository_name='Repository One',
        additional_repository_origins=[{
            'id': 'repo-two',
            'origin_path': '/non-sensitive/origin-two',
            'remote': '',
            'git_repository': True,
        }],
        accepted_baseline_id=str(dry_run['accepted_baseline_evidence']['id']),
        registry_path=registry_path,
        fail_stage=fail_stage,
    )


def test_proposal_reports_complete_inputs_and_separate_dirty_states(tmp_path: Path) -> None:
    source, target = tmp_path / 'source', tmp_path / 'target'
    seed(source)
    inspection = inspect_migration(source, target)
    dry_run = proposal(source, target)
    assert inspection['source_repository_git']['dirty'] is True
    assert inspection['work_bundle_git']['dirty'] is True
    assert dry_run['workspace_slug'] == 'workspace-one'
    assert dry_run['repository_name'] == 'Repository One'
    assert dry_run['working_branch'] == 'feature/workspace'
    assert dry_run['base_ref'] == 'HEAD'
    assert dry_run['additional_repository_origins'][0]['id'] == 'repo-two'
    assert dry_run['apply_requires_accepted_baseline'] is True
    assert len(dry_run['accepted_baseline_evidence']['id']) == 64
    assert dry_run['changed_files'] == [] and not target.exists()


def test_proposal_rejects_working_branch_checked_out_in_origin_common_dir(tmp_path: Path) -> None:
    source, target, occupied = tmp_path / 'source', tmp_path / 'target', tmp_path / 'occupied'
    seed(source, dirty_source=False, dirty_nested=False)
    subprocess.run(
        ['git', '-C', str(source), 'worktree', 'add', '-q', '-b', 'feature/occupied', str(occupied), 'HEAD'],
        check=True,
    )

    with pytest.raises(MigrationError) as raised:
        propose_migration(source, target, 'repo-one', 'feature/occupied', 'HEAD')

    assert raised.value.code == 'WB_WORKTREE_BRANCH_CONFLICT'
    assert raised.value.result['changed_files'] == []
    assert raised.value.result['working_branch'] == 'feature/occupied'
    assert not target.exists()


def test_proposal_distinguishes_missing_origin_main_from_local_main(tmp_path: Path) -> None:
    source, target = tmp_path / 'source', tmp_path / 'target'
    seed(source, dirty_source=False, dirty_nested=False)

    with pytest.raises(MigrationError) as raised:
        propose_migration(source, target, 'repo-one', 'feature/workspace', 'origin/main')

    assert raised.value.code == 'WB_MIGRATION_LOCAL_ORIGIN_BASE_REF_UNAVAILABLE'
    assert raised.value.result['changed_files'] == []
    assert raised.value.result['base_ref'] == 'origin/main'
    assert raised.value.result['local_branch_available'] is True
    assert not target.exists()

    valid = propose_migration(source, target, 'repo-one', 'feature/workspace', 'main')
    assert valid['changed_files'] == []
    assert not target.exists()


def test_invalid_proposal_prevents_apply_from_reaching_member_provisioning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = tmp_path / 'source', tmp_path / 'target'
    seed(source, dirty_source=False, dirty_nested=False)
    monkeypatch.setattr(
        migration,
        'provision_member',
        lambda *_args, **_kwargs: pytest.fail('provision_member must not run'),
    )

    with pytest.raises(MigrationError, match='LOCAL_ORIGIN_BASE_REF_UNAVAILABLE'):
        apply_migration(source, target, 'repo-one', 'feature/workspace', 'origin/main')

    assert not target.exists()


def test_dirty_apply_requires_exact_accepted_baseline(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    with pytest.raises(MigrationError, match='ACCEPTED_BASELINE_REQUIRED'):
        apply_migration(
            source, target, 'repo-one', 'feature/workspace', registry_path=registry_path,
            workspace_slug='workspace-one', repository_name='Repository One',
        )
    assert not target.exists()
    assert 'workspace-one' not in registry_path.read_text(encoding='utf-8')


def test_apply_preserves_source_and_publishes_v3_and_locator(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    before = source_snapshot(source)
    result = apply(source, target, registry_path)
    assert result['status'] == 'published'
    assert result['metadata_and_registry_status'] == {'metadata': 'published', 'registry': 'published'}
    historical_identity = hashlib.sha256(
        f'{source.resolve()}:{target.resolve()}:workspace-one:repo-one'.encode('utf-8')
    ).hexdigest()[:20]
    assert result['transaction']['id'] == historical_identity
    assert source_snapshot(source) == before
    metadata = (target / '.work-bundle/project.yaml').read_text(encoding='utf-8')
    assert 'metadata_version: 3' in metadata
    assert 'workspace_mode: multi-repository' in metadata
    assert 'checkout_kind: managed-worktree' in metadata
    assert 'git_control_scope: workspace' in metadata
    assert 'custom_preserved:' in metadata
    registry_text = registry_path.read_text(encoding='utf-8')
    assert 'registry_note: preserve' in registry_text
    assert '  - slug: existing' in registry_text
    assert '  - slug: workspace-one' in registry_text
    assert 'repository_origins:' in registry_text and 'repo-two' in registry_text
    member = Path(str(result['member']['project_root']))
    common = Path(git(member, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    assert target.resolve() in common.parents
    assert target.resolve() in member.resolve().parents
    assert (target / '.work-bundle/unknown/maintain.sh').read_bytes() == before['unknown']
    assert stat.S_IMODE((target / '.work-bundle/unknown/maintain.sh').stat().st_mode) == before['unknown_mode']
    assert (target / '.work-bundle/unknown/maintain.sh').stat().st_mtime_ns == before['unknown_mtime']
    assert git(target / '.work-bundle', 'rev-list', '--count', 'HEAD') == '2'
    assert not (target / '.work-bundle/.cache').exists()
    agents_text = (target / 'AGENTS.md').read_text(encoding='utf-8')
    assert agents_text.startswith(before['agents'].decode('utf-8'))
    assert '# Work Bundle RULE START' in agents_text
    credential = target / 'credentials/credentials.yaml'
    assert credential.read_text(encoding='utf-8') == 'version: 1\ncredentials: []\n'
    assert stat.S_IMODE(credential.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(credential.stat().st_mode) == 0o600
    assert result['script_index_validation'] == 'passed'
    assert (target / '.gitignore').is_file()
    assert (target / 'roles/solution-architect.yaml').is_file()
    assert 'credentials/' in (target / '.work-bundle/.gitignore').read_text(encoding='utf-8')
    assert 'git/' in (target / '.work-bundle/.gitignore').read_text(encoding='utf-8')
    record = json.loads(Path(str(result['transaction_record'])).read_text(encoding='utf-8'))
    assert record['state'] == 'published'
    assert record['source_preserved'] is True


def test_non_git_authority_can_provision_from_explicit_external_origin(tmp_path: Path) -> None:
    source, origin, target = tmp_path / 'authority', tmp_path / 'origin', tmp_path / 'target'
    registry_path = tmp_path / 'config/projects.yaml'
    seed(origin, dirty_source=True, dirty_nested=False)
    source.mkdir()
    (source / '.work-bundle').mkdir()
    (source / '.work-bundle/project.yaml').write_text(
        'metadata_version: 2\nauthority: canonical\n', encoding='utf-8'
    )
    (source / 'script').mkdir()
    (source / 'script/index.yaml').write_text(SCRIPT_INDEX_TEMPLATE, encoding='utf-8')
    (source / 'script/legacy.py').write_text('raise SystemExit("must not migrate")\n', encoding='utf-8')
    (source / 'AGENTS.md').write_text('legacy authority\n', encoding='utf-8')
    registry(registry_path)
    dry_run = propose_migration(
        source, target, 'repo-one', 'feature/workspace', 'HEAD', origin=origin,
        workspace_slug='workspace-one', repository_name='Repository One',
    )
    result = apply_migration(
        source, target, 'repo-one', 'feature/workspace', 'HEAD', origin=origin,
        workspace_slug='workspace-one', repository_name='Repository One',
        accepted_baseline_id=str(dry_run['accepted_baseline_evidence']['id']),
        registry_path=registry_path,
    )
    assert result['status'] == 'published'
    assert result['member_origin_git']['dirty'] is True
    assert result['member']['project_root'] == str((target / 'repo-one').resolve())
    assert not (target / 'script/legacy.py').exists()
    assert (source / 'script/legacy.py').is_file()
    assert 'script' in result['skipped_sensitive_and_transient_paths']
    assert 'script' not in result['copied_inventory_and_digests']
    assert git(target / 'repo-one', 'rev-parse', 'HEAD') == git(origin, 'rev-parse', 'HEAD')
    registry_text = registry_path.read_text(encoding='utf-8')
    assert f'origin_path: "{origin.resolve()}"' in registry_text


@pytest.mark.parametrize('stage', TRANSACTION_STAGES)
def test_each_stage_failure_preserves_source_registry_and_recovery(tmp_path: Path, stage: str) -> None:
    source = tmp_path / f'source-{stage}'
    target = tmp_path / f'target-{stage}'
    registry_path = tmp_path / f'config-{stage}/projects.yaml'
    seed(source)
    registry(registry_path)
    source_before = source_snapshot(source)
    registry_before = registry_path.read_bytes()
    with pytest.raises(MigrationError) as raised:
        apply(source, target, registry_path, fail_stage=stage)
    assert source_snapshot(source) == source_before
    assert registry_path.read_bytes() == registry_before
    assert not target.exists()
    record_path = raised.value.transaction_record
    assert record_path is not None and record_path.is_file()
    record = json.loads(record_path.read_text(encoding='utf-8'))
    assert record['state'] == 'failed'
    assert record['registry_status'] == 'unchanged'
    assert record['source_preserved'] is True
    synthetic_value = ''.join(('fixture', '-', 'private', '-', 'value'))
    assert synthetic_value not in json.dumps(record)


def test_failed_transaction_retries_and_published_retry_is_idempotent(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    dry_run = proposal(source, target)
    options = {
        'workspace_slug': 'workspace-one',
        'repository_name': 'Repository One',
        'accepted_baseline_id': dry_run['accepted_baseline_evidence']['id'],
        'registry_path': registry_path,
    }
    with pytest.raises(MigrationError):
        apply_migration(
            source, target, 'repo-one', 'feature/workspace', fail_stage='member-provision', **options
        )
    repaired = retry_transaction(source, target, 'repo-one', 'feature/workspace', **options)
    assert repaired['status'] == 'published'
    registry_after = registry_path.read_bytes()
    metadata_path = target / '.work-bundle/project.yaml'
    metadata_after = metadata_path.read_bytes()
    recovery_path = Path(str(repaired['transaction_record']))
    recovery_after = recovery_path.read_bytes()
    recovery_mtime = recovery_path.stat().st_mtime_ns
    idempotent = retry_transaction(source, target, 'repo-one', 'feature/workspace', **options)
    assert idempotent['status'] == 'published' and idempotent['idempotent'] is True
    required = {
        'copied_inventory_and_digests',
        'skipped_sensitive_and_transient_paths',
        'script_index_validation',
        'agents_merge_status',
        'member',
        'source_preservation_checks',
        'validation_results',
        'retry_or_rollback_instructions',
        'source_repository_git',
        'work_bundle_git',
        'accepted_baseline_id',
    }
    assert required <= idempotent.keys()
    assert idempotent['transaction']['id'] == repaired['transaction']['id']
    assert idempotent['transaction']['context'] == repaired['transaction']['context']
    assert idempotent['member'] == repaired['member']
    assert idempotent['validation_results'] == repaired['validation_results']
    assert registry_path.read_bytes() == registry_after
    assert metadata_path.read_bytes() == metadata_after
    assert recovery_path.read_bytes() == recovery_after
    assert recovery_path.stat().st_mtime_ns == recovery_mtime


def test_rollback_is_owned_path_only_and_idempotent(tmp_path: Path) -> None:
    target = tmp_path / 'target'
    owned = target / 'owned'
    unrelated = target / 'unrelated.txt'
    owned.mkdir(parents=True)
    unrelated.write_text('preserve\n', encoding='utf-8')
    transaction = MigrationTransaction(target, 'owned-only')
    transaction.own(owned)
    first = rollback_owned_paths(transaction)
    second = rollback_owned_paths(transaction)
    assert first['state'] == 'rolled-back' and second['state'] == 'rolled-back'
    assert unrelated.read_text(encoding='utf-8') == 'preserve\n'
    assert transaction.recovery_path.is_file()


def test_unsafe_symlink_and_collision_fail_without_publication(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    (source / '.work-bundle/link').symlink_to(source / 'README.md')
    registry_before = registry_path.read_bytes()
    with pytest.raises(MigrationError, match='UNSAFE_SYMLINK'):
        apply(source, target, registry_path)
    assert not target.exists() and registry_path.read_bytes() == registry_before
    (source / '.work-bundle/link').unlink()
    target.mkdir()
    (target / 'user-file').write_text('preserve\n', encoding='utf-8')
    with pytest.raises(MigrationError, match='TARGET_NOT_EMPTY'):
        apply(source, target, registry_path)
    assert (target / 'user-file').read_text(encoding='utf-8') == 'preserve\n'


def test_failed_apply_preserves_preexisting_empty_target_root(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    target.mkdir()
    registry(registry_path)
    with pytest.raises(MigrationError):
        apply(source, target, registry_path, fail_stage='workspace-resources')
    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_failure_evidence_carries_member_git_verification_and_publication_identities(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    with pytest.raises(MigrationError) as raised:
        apply(source, target, registry_path, fail_stage='metadata-publication')
    record = json.loads(raised.value.transaction_record.read_text(encoding='utf-8'))
    context = record['context']
    assert context['member']['lifecycle_state'] == 'verified'
    assert context['member']['observed_git']['branch'] == 'feature/workspace'
    assert context['member']['observed_git']['head']
    assert context['member']['verification']['passed'] is True
    assert context['member']['verification']['target_validation_passed'] is True
    assert context['metadata_identity']['old']['version'] == '2'
    assert context['metadata_identity']['new'] == {
        'version': 3,
        'workspace_root': str(target.resolve()),
        'workspace_mode': 'multi-repository',
    }
    assert context['registry_identity']['old']['published'] is False
    assert context['registry_identity']['new']['status'] == 'active'
    assert context['publication']['metadata_before']
    assert context['publication']['registry_after']


def test_final_verification_precedes_all_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    registry_before = registry_path.read_bytes()
    writes: list[Path] = []
    original = migration._atomic_write

    def recording_write(path: Path, payload: bytes) -> None:
        writes.append(path.resolve())
        original(path, payload)

    monkeypatch.setattr(migration, '_atomic_write', recording_write)
    with pytest.raises(MigrationError, match='FINAL_VERIFICATION'):
        apply(source, target, registry_path, fail_stage='final-verification')
    assert registry_path.resolve() not in writes
    assert registry_path.read_bytes() == registry_before
    assert not target.exists()


def test_success_result_has_discovery_preflight_recovery_and_baseline_contract(tmp_path: Path) -> None:
    source, target, registry_path = tmp_path / 'source', tmp_path / 'target', tmp_path / 'config/projects.yaml'
    seed(source)
    registry(registry_path)
    result = apply(source, target, registry_path)
    validations = result['validation_results']
    assert validations['passed'] is True
    assert validations['session_start_discovery'] == {
        'passed': True,
        'workspace_root': str(target.resolve()),
        'member_root': str((target / 'repo-one').resolve()),
    }
    assert validations['member_preflight']['passed'] is True
    assert validations['member_preflight']['branch_status'] == 'matched'
    assert validations['source_preservation']['passed'] is True
    assert result['source_repository_git']['dirty'] is True
    assert result['work_bundle_git']['dirty'] is True
    assert result['accepted_baseline_id'] == proposal(source, target)['accepted_baseline_evidence']['id']
    assert 'same accepted_baseline_id' in result['retry_or_rollback_instructions']['retry']
    assert 'transaction-owned target paths only' in result['retry_or_rollback_instructions']['rollback']
