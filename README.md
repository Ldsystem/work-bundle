# work-bundle

Toolkit source for WorkBundle skills, rules, references, and deterministic helper code.

WorkBundle distinguishes four roots:

- `work_bundle_root` — this installed toolkit source.
- `work_bundle_config_root` — user runtime state under `~/.work-bundle/`.
- `workspace_root` — authority for `.work-bundle/`, root `AGENTS.md`, reusable `script/`, protected `credentials/`, and managed repository members.
- `project_root` — one concrete repository checkout. It equals `workspace_root` in single-repository mode and is a workspace child in multi-repository mode.

## Structure

- `skills/` - migrated work-bundle skill packages
- `scripts/` - toolkit helper code; this is never the workspace utility directory
- `references/` - shared design and runtime references
- `.work-bundle/` - local agent knowledge and orchestration bundle

A managed workspace uses singular `script/` with `script/index.yaml` for reusable utilities. Discovery does not authorize execution. The local-only `credentials/credentials.yaml` store is Git-ignored and must never be opened, printed, indexed, or transmitted through agent-visible surfaces; credential-backed work goes through `wb-credential-use` with redacted evidence only.

Both single- and multi-repository workspaces are current. Multi-repository members use workspace-local Git control stores and named worktrees; registered origin paths remain locators rather than normal writable checkouts.

## Skill Links

Install bootstrap/registry and symlink all work-bundle skills into the shared agent skill root:

```bash
bin/install.sh
```

Install or refresh skill symlinks only:

```bash
bin/install-work-bundle-skills
```

Useful checks:

```bash
bin/work-bundle-skill list
bin/work-bundle-skill validate
bin/install-work-bundle-skills --dry-run
```
