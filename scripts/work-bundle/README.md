# Work-Bundle Scripts

Implementation modules in this directory are the manual maintenance surface for work-bundle helpers.

The top-level `../wb.py` entrypoint remains for compatibility with existing agent instructions. Implementation is split by skill area (`rules.py`, `project.py`, `doctor.py`, `metadata_profile.py`, `skill_registry.py`, `role_context.py`, `integrity.py`), with `dispatcher.py` only wiring commands.

Command examples:

```bash
python3 scripts/wb.py init-project <root> --mode single-repository
python3 scripts/wb.py init-project <root> --mode multi-repository --workspace-root <workspace-root>
python3 scripts/wb.py show-project --workspace-root <workspace-root> --project-root <member-project-root>
python3 scripts/wb.py credential-list --workspace-root <workspace-root>
python3 scripts/wb.py migrate-to-multi-repository <source-project-root> --target-workspace-root <target> --repository-id <id> --working-branch <branch> --dry-run
python3 scripts/wb.py create-rules --scope toolkit
python3 scripts/wb.py create-rules --scope global
python3 scripts/wb.py create-rules --scope project --workspace-root <workspace-root>
python3 scripts/wb.py validate-rules --scope toolkit
python3 scripts/wb.py validate-rules --scope global
python3 scripts/wb.py validate-rules --scope project --workspace-root <workspace-root>
python3 scripts/wb.py inspect-skill skills/wb-credential-use/SKILL.md
python3 scripts/wb.py validate-registry-entry <redacted-proposal.yaml>
python3 scripts/wb.py create-rules rules
python3 scripts/wb.py validate-rules rules
python3 scripts/wb.py violation-ensure-store
python3 scripts/wb.py violation-create-evidence --status active --short-description <slug> --deviation <text> --occurrence <text> --evidence <path-or-surface> --severity p5
python3 scripts/wb.py violation-build-index
python3 scripts/wb.py violation-write-index
python3 scripts/wb.py violation-archive-evidence <evidence-id-or-path> --action completed
python3 scripts/wb.py integrity-check-report new --template references/integrity-check/integrity-check-template.md --output-root /tmp/reports --title check
```

Prefer `--scope` for `create-rules` and `validate-rules`: `toolkit` resolves to `$work_bundle_root/rules/`, `global` resolves to `$work_bundle_config_root/rules/`, and `project` resolves to `<workspace-root>/.work-bundle/rules/`. The project-root form remains a single-repository compatibility alias.

Workspace utilities live under singular `<workspace-root>/script/` and are reusable only when declared in `script/index.yaml`; discovery never runs them. Toolkit helpers remain under plural `scripts/`. Credential values stay solely in protected, ignored `<workspace-root>/credentials/credentials.yaml` and are never accepted by these command lines.

The runtime skill registry resolved from `~/.work-bundle/bootstrap.yaml` field `skill_registry` is external-only. Built-in skills under `$work_bundle_root/skills/`, including `wb-credential-use` and `wb-migrate-to-multi-repository`, are toolkit-owned and must not be registered. For external candidates only, inspect and validate a compact `type: external` proposal first; `register-skill --confirmed` is forbidden until the user explicitly confirms its role, stage, and output mappings.
