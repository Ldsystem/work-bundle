# Work-Bundle Scripts

Implementation modules in this directory are the manual maintenance surface for work-bundle helpers.

The top-level `../wb.py` entrypoint remains for compatibility with existing agent instructions. Implementation is split by skill area (`rules.py`, `project.py`, `member.py`, `doctor.py`, `metadata_profile.py`, `skill_registry.py`, `role_context.py`, `integrity.py`), with `dispatcher.py` only wiring commands.

Command examples:

```bash
python3 scripts/wb.py init-project <root> --mode single-repository
python3 scripts/wb.py init-project <root> --mode multi-repository --workspace-root <workspace-root>
python3 scripts/wb.py show-project --workspace-root <workspace-root> --project-root <member-project-root>
python3 scripts/wb.py credential-list --workspace-root <workspace-root>
python3 scripts/wb.py migrate-to-multi-repository <source-project-root> --target-workspace-root <target> --origin <primary-git-origin> --repository-id <id> --repository-name <name> --workspace-slug <slug> --working-branch <branch> --dry-run
python3 scripts/wb.py provision-member --workspace-root <workspace> --workspace-slug <slug> --origin <origin-root> --repository-id <id> --working-branch <branch> --base-ref <ref> --dry-run
python3 scripts/wb.py cleanup-member --workspace-root <workspace> --repository-id <id> --dry-run
python3 scripts/wb.py migrate-control-plane <workspace-root> --dry-run
python3 scripts/wb.py migrate-control-plane <workspace-root> --accepted-proposal-id <proposal-id> --apply
python3 scripts/wb.py init-workspace <workspace-root> --mode single-repository --slug <slug> --repository <id>=<source-remote> --apply
python3 scripts/wb.py attach-workspace <workspace-root> --materialize missing --apply
python3 scripts/wb.py doctor-workspace <workspace-root>
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

Multi-repository workspace utilities live under singular `<workspace-root>/script/` and are reusable only when declared in `script/index.yaml`; discovery never runs them. Their credential values stay solely in protected, ignored `<workspace-root>/credentials/credentials.yaml`. Single-repository workspaces contain neither runtime folder. Toolkit helpers remain under plural `scripts/`, and credential values are never accepted by these command lines.

`migrate-project` is an in-place metadata upgrader only. Metadata v2 dry-run classifies metadata and registry topology and returns an accepted proposal ID; multiple repositories route to `migrate-to-multi-repository`. When the authority root is not Git-backed, use `--origin` for the concrete primary Git repository. `provision-member --apply` reports success only after the verified checkout, workspace metadata member, and locator registry origin are all published recoverably. Exact older verified checkouts without recovery records resume publication; `cleanup-member` deletes only recorded, unpublished, transaction-owned paths.

`migrate-control-plane` upgrades metadata v3 to portable v4 only after the exact dry-run proposal is accepted. For single-repository mode it preserves `workspace_root == project_root`, writes a portable `root` workspace binding, keeps machine-local observations in the user registry, and ensures the source repository excludes `.work-bundle/`. An existing compatible ignore rule is left untouched; otherwise WorkBundle records the local realization rule in `.git/info/exclude` rather than rewriting user `.gitignore`. `AGENTS.md` remains a separate concern: tracked content stays tracked and synchronization preserves user-authored content outside the managed section. To reconstruct another device, clone the control-plane repository as `<workspace-root>/.work-bundle`, then attach with source materialization enabled. Root materialization initializes and checks out the configured source remote in place, preserves the cloned control plane and pre-existing user paths, and rolls back only transaction-created source state on failure.

The runtime skill registry resolved from `~/.work-bundle/bootstrap.yaml` field `skill_registry` is external-only. Built-in skills under `$work_bundle_root/skills/`, including `wb-credential-use` and `wb-migrate-to-multi-repository`, are toolkit-owned and must not be registered. For external candidates only, inspect and validate a compact `type: external` proposal first; `register-skill --confirmed` is forbidden until the user explicitly confirms its role, stage, and output mappings.
