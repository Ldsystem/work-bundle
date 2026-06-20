from __future__ import annotations

import argparse

from core import CLI_HELP_EPILOG, LEGACY_COMMAND_MIGRATIONS
from doctor import cmd_doctor
from integrity import cmd_integrity_report, cmd_merge_skill_hints
from legacy import cmd_legacy_command_removed
from metadata_profile import cmd_domain_profile
from bootstrap_config import cmd_migrate_work_bundle_config
from project import cmd_doctor_project, cmd_init_project, cmd_migrate_project, cmd_project, cmd_register_project_command, cmd_set_prefer_subagent, cmd_show_project, cmd_validate_project
from role_context import cmd_role_context
from rules import cmd_create_rules, cmd_validate_rules
from skill_registry import cmd_registry


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
        'integrity-report': 'integrity-check-report',
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
    if command == 'doctor-project':
        return cmd_doctor_project(parsed.args)
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
    if command == 'select-role-context':
        return cmd_role_context(parsed.args)
    if command == 'validate-role-context':
        return cmd_role_context(parsed.args, validate=True)
    if command == 'merge-skill-hints':
        return cmd_merge_skill_hints(parsed.args)
    if command == 'integrity-check-report':
        return cmd_integrity_report(parsed.args)
    parser.error(f'unknown command: {parsed.command}')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
