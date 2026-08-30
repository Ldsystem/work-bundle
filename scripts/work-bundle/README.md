# Work-Bundle Scripts

Implementation modules in this directory are the manual maintenance surface for work-bundle helpers.

The top-level `../wb.py` entrypoint remains for compatibility with existing agent instructions. Implementation is split by skill area (`rules.py`, `project.py`, `member.py`, `doctor.py`, `metadata_profile.py`, `skill_registry.py`), with `dispatcher.py` only wiring commands.

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
python3 scripts/wb.py migrate-registered-projects --dry-run
python3 scripts/wb.py migrate-registered-projects --accepted-plan-id <plan-id> --apply
python3 scripts/wb.py init-workspace <workspace-root> --mode single-repository --slug <slug> --repository <id>=<source-remote> --apply
python3 scripts/wb.py attach-workspace <workspace-root> --materialize missing --apply
python3 scripts/wb.py doctor-workspace <workspace-root>
python3 scripts/wb.py add-workspace-member <workspace-root> --repository-id <id> --remote <observed-url> --name <binding-name> --path <relative-path> --default-branch <branch> --dry-run
python3 scripts/wb.py add-workspace-member <workspace-root> --repository-id <id> --remote <observed-url> --name <binding-name> --path <relative-path> --default-branch <branch> --accepted-proposal-id <proposal-id> --apply
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
python3 scripts/wb.py defect-ensure-store
python3 scripts/wb.py defect-migrate-store
python3 scripts/wb.py defect-create-evidence --status active --short-description <slug> --deviation <text> --occurrence <text> --evidence <path-or-surface> --severity p5
python3 scripts/wb.py defect-build-index
python3 scripts/wb.py defect-write-index
python3 scripts/wb.py defect-archive-evidence <evidence-id-or-path> --action completed
```

Prefer `--scope` for `create-rules` and `validate-rules`: `toolkit` resolves to `$work_bundle_root/rules/`, `global` resolves to `$work_bundle_config_root/rules/`, and `project` resolves to `<workspace-root>/.work-bundle/rules/`. The project-root form remains a single-repository compatibility alias.

Multi-repository workspace utilities live under singular `<workspace-root>/script/` and are reusable only when declared in `script/index.yaml`; discovery never runs them. Their credential values stay solely in protected, ignored `<workspace-root>/credentials/credentials.yaml`. Single-repository workspaces contain neither runtime folder. Toolkit helpers remain under plural `scripts/`, and credential values are never accepted by these command lines.

`migrate-project` is an in-place metadata upgrader only. Metadata v2 dry-run classifies metadata and registry topology and returns an accepted proposal ID; multiple repositories route to `migrate-to-multi-repository`. When the authority root is not Git-backed, use `--origin` for the concrete primary Git repository. `provision-member --apply` reports success only after the verified checkout, workspace metadata member, and locator registry origin are all published recoverably. Exact older verified checkouts without recovery records resume publication; `cleanup-member` deletes only recorded, unpublished, transaction-owned paths.

`migrate-registered-projects` enumerates the bootstrap-resolved project registry, classifies each entry as current, migratable, unsupported, missing, or blocked, and dry-runs a deterministic version-to-version plan. Apply requires that exact plan ID. Layout steps are registered in `references/wb-registry-layout-migration.yaml` (`2 -> 3` then `3 -> 4`); registry schema version stays distinct from project layout version. Registry `layout_version` is published only after the target layout validates. A failed project restores its pre-migration workspace and registry bytes and never marks the entry current.

`add-workspace-member` is the v4 composite-member transaction. Dry-run and apply fail closed unless the current workspace binding, matching `workspace_root`, root repository local binding, and a valid root Git checkout are present, and the live root origin plus observed branch match the portable root `remote.canonical` and `default_branch`. Dry-run validates required request values and the rendered target metadata before emitting a digest-bound proposal that records current/target mode, unchanged root identity, member id/name/path/remote/branch, exclude patterns, device-binding delta, and the live metadata digest. The first accepted apply converts `single-repository` to `composite` and adds the named nested member; later applies are add-only. A pre-existing member checkout is accepted only when its remote and observed branch already match the request; transaction-owned clone/checkout is re-verified against `--default-branch`. Matching replay is a no-op only when the member checkout exists with matching remote/branch, the registry member binding points at that exact path with `checkout_kind: nested-member`, and the root exclude contains the member pattern; otherwise apply fails closed without mutation and attach/doctor remain the repair path. A different remote or path collides. Portable composite validation rejects duplicate member names and paths. Root Git exclusion uses device-local `.git/info/exclude` with `checkout_kind: nested-member`; attach/doctor reapply those lines and fail closed if the member path is root-index tracked. Rollback restores metadata, registry, and transaction-owned exclude lines and removes only transaction-owned member state. It does not invent remotes, create GitHub repositories, extend v3 `provision-member`, or rewrite the root source repository.

`migrate-control-plane` upgrades metadata v3 to portable v4 only after the exact dry-run proposal is accepted. For single-repository mode it preserves `workspace_root == project_root`, writes a portable `root` workspace binding, keeps machine-local observations in the user registry, and ensures the source repository excludes `.work-bundle/`. An existing compatible ignore rule is left untouched; otherwise WorkBundle records the local realization rule in `.git/info/exclude` rather than rewriting user `.gitignore`. `AGENTS.md` remains a separate concern: tracked content stays tracked and synchronization preserves user-authored content outside the managed section. To reconstruct another device, clone the control-plane repository as `<workspace-root>/.work-bundle`, then attach with source materialization enabled. Root materialization initializes and checks out the configured source remote in place, preserves the cloned control plane and pre-existing user paths, and rolls back only transaction-created source state on failure.

The runtime skill registry resolved from `~/.work-bundle/bootstrap.yaml` field `skill_registry` is external-only. Built-in skills under `$work_bundle_root/skills/`, including `wb-credential-use` and `wb-migrate-to-multi-repository`, are toolkit-owned and must not be registered. For external candidates only, inspect and validate a compact `type: external` proposal first; `register-skill --confirmed` is forbidden until the user explicitly confirms its role, stage, and output mappings.
