from __future__ import annotations

import argparse
from pathlib import Path

from core import CLI_HELP_EPILOG, LEGACY_COMMAND_MIGRATIONS, out
from doctor import cmd_doctor
from instruction_audit import cmd_instruction_audit
from legacy import cmd_legacy_command_removed
from metadata_profile import cmd_domain_profile
from bootstrap_config import cmd_migrate_work_bundle_config
from project import cmd_cleanup_member, cmd_doctor_project, cmd_init_project, cmd_migrate_project, cmd_migrate_to_multi_repository, cmd_project, cmd_provision_member, cmd_register_project_command, cmd_session_start, cmd_set_prefer_subagent, cmd_show_project, cmd_validate_project
from rules import cmd_create_rules, cmd_validate_rules
from skill_registry import cmd_merge_skill_hints, cmd_registry
from violations import (
    cmd_violation_archive_evidence,
    cmd_violation_build_index,
    cmd_violation_create_evidence,
    cmd_violation_ensure_store,
    cmd_violation_write_index,
)
from credential import CredentialError, list_metadata
from execution_workspace import cmd_execution_workspace
from control_plane import (
    cmd_add_workspace_member,
    cmd_attach_workspace,
    cmd_detach_workspace,
    cmd_doctor_workspace,
    cmd_init_workspace,
    cmd_migrate_control_plane,
    cmd_publish_control_plane,
)
from registry_layout import cmd_migrate_registered_projects


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='wb.py',
        description='Canonical work-bundle helper CLI.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=CLI_HELP_EPILOG,
    )
    parser.add_argument('command', help='Canonical command (retired legacy commands error with migration guidance).')
    parser.add_argument('args', nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    command = parsed.command
    if command in LEGACY_COMMAND_MIGRATIONS:
        return cmd_legacy_command_removed(command, LEGACY_COMMAND_MIGRATIONS[command])
    aliases = {
        'apply-project-initialization': 'init-project',
        'apply-repository-model': 'initialize-project',
        'extract-domain-profile': 'generate-project-metadata-profile',
        'merge-registry-entry': 'register-skill',
        'validate-project-initialization': 'validate-project',
        'validate-runtime-artifacts': 'doctor',
        'validate-repository-health': 'repository-health',
        'validate-workflow-branches': 'workflow-branches',
    }
    command = aliases.get(command, command)
    if command == 'migrate-work-bundle-config':
        return cmd_migrate_work_bundle_config(parsed.args)
    if command in {'init-project', 'initialize-project'}:
        return cmd_init_project(parsed.args)
    if command == 'register-project':
        return cmd_register_project_command(parsed.args)
    if command == 'show-project':
        return cmd_show_project(parsed.args)
    if command == 'migrate-project':
        return cmd_migrate_project(parsed.args)
    if command == 'migrate-control-plane':
        return cmd_migrate_control_plane(parsed.args)
    if command == 'migrate-registered-projects':
        return cmd_migrate_registered_projects(parsed.args)
    if command == 'init-workspace':
        return cmd_init_workspace(parsed.args)
    if command == 'publish-control-plane':
        return cmd_publish_control_plane(parsed.args)
    if command == 'attach-workspace':
        return cmd_attach_workspace(parsed.args)
    if command == 'doctor-workspace':
        return cmd_doctor_workspace(parsed.args)
    if command == 'add-workspace-member':
        return cmd_add_workspace_member(parsed.args)
    if command == 'detach-workspace':
        return cmd_detach_workspace(parsed.args)
    if command == 'migrate-to-multi-repository':
        return cmd_migrate_to_multi_repository(parsed.args)
    if command == 'doctor-project':
        return cmd_doctor_project(parsed.args)
    if command == 'provision-member':
        return cmd_provision_member(parsed.args)
    if command == 'cleanup-member':
        return cmd_cleanup_member(parsed.args)
    if command == 'credential-list':
        credential_parser = argparse.ArgumentParser(prog='wb.py credential-list')
        credential_parser.add_argument('--workspace-root', required=True)
        credential_args = credential_parser.parse_args(parsed.args)
        try:
            out([item.__dict__ for item in list_metadata(Path(credential_args.workspace_root))])
            return 0
        except CredentialError as exc:
            out({'status': 'blocked', 'failure_code': str(exc)})
            return 1
    if command.startswith('execution-workspace-'):
        action = command.removeprefix('execution-workspace-')
        if action in {'prepare', 'status', 'mark-terminal', 'cleanup-owned', 'doctor-stale'}:
            return cmd_execution_workspace(action, parsed.args)
    if command == 'instruction-audit':
        return cmd_instruction_audit(parsed.args)
    if command == 'session-start':
        return cmd_session_start(parsed.args)
    if command == 'inspect-project-initialization':
        return cmd_project(parsed.args, inspect_only=True, repo_model=True)
    if command == 'validate-project':
        return cmd_validate_project(parsed.args)
    if command == 'set-prefer-subagent':
        return cmd_set_prefer_subagent(parsed.args)
    if command == 'create-rules':
        return cmd_create_rules(parsed.args)
    if command == 'validate-rules':
        return cmd_validate_rules(parsed.args)
    if command == 'violation-ensure-store':
        return cmd_violation_ensure_store(parsed.args)
    if command == 'violation-create-evidence':
        return cmd_violation_create_evidence(parsed.args)
    if command == 'violation-build-index':
        return cmd_violation_build_index(parsed.args)
    if command == 'violation-write-index':
        return cmd_violation_write_index(parsed.args)
    if command == 'violation-archive-evidence':
        return cmd_violation_archive_evidence(parsed.args)
    if command in {'doctor', 'repository-health', 'validate-directive-wiring', 'validate-skill-registry', 'validate-work-bundle-rules'}:
        return cmd_doctor(parsed.args)
    if command == 'render-doctor-report':
        return cmd_doctor(parsed.args, report=True)
    if command == 'workflow-branches':
        return cmd_doctor(parsed.args, workflow=True)
    if command == 'generate-project-metadata-profile':
        return cmd_domain_profile(parsed.args)
    if command == 'merge-project-metadata-profile':
        return cmd_domain_profile(parsed.args, merge=True)
    if command == 'validate-project-metadata-profile':
        return cmd_domain_profile(parsed.args, validate=True)
    if command == 'inspect-skill':
        return cmd_registry(parsed.args, inspect=True)
    if command == 'validate-registry-entry':
        return cmd_registry(parsed.args, validate=True)
    if command == 'register-skill':
        return cmd_registry(parsed.args)
    if command == 'merge-skill-hints':
        return cmd_merge_skill_hints(parsed.args)
    parser.error(f'unknown command: {parsed.command}')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
