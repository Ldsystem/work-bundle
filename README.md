# work-bundle

[![CI](https://github.com/Ldsystem/work-bundle/actions/workflows/ci.yml/badge.svg)](https://github.com/Ldsystem/work-bundle/actions/workflows/ci.yml)
![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)

Toolkit source for WorkBundle skills, rules, references, and deterministic helper code.

## Ecosystem

WorkBundle owns orchestration contracts, workspace authority, durable knowledge,
and acceptance flow. [Execution Flow](https://github.com/Ldsystem/execution-flow)
is a separate, optional TypeScript repository that supplies provider-neutral
executor selection and ACP delegation without taking over WorkBundle
orchestration.

The recommended local layout for developing both repositories is a
multi-repository workspace:

```text
work-bundle-workspace/
├── .work-bundle/       # portable workspace authority and runtime artifacts
├── work-bundle-main/   # this toolkit repository
└── execution-flow/     # the independent Execution Flow repository
```

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

A multi-repository workspace uses singular `script/` with `script/index.yaml` for reusable utilities. Discovery does not authorize execution. Its local-only `credentials/credentials.yaml` store is Git-ignored and must never be opened, printed, indexed, or transmitted through agent-visible surfaces; credential-backed work goes through `wb-credential-use` with redacted evidence only. Single-repository workspaces contain neither runtime folder; the mechanism templates remain under `references/assets/template/`.

Both single- and multi-repository workspaces are current. Multi-repository members use workspace-local Git control stores and named worktrees; registered origin paths remain locators rather than normal writable checkouts.

Portable control-plane v4 keeps the single-repository layout flat: the source repository owns `<workspace-root>/.git`, while the independently publishable WorkBundle control plane owns `<workspace-root>/.work-bundle/.git`. Its source entry uses `workspace_binding.type: root`; multi-repository entries use `workspace_binding.type: member` plus a member name. A fresh device clones the control plane into `.work-bundle/`, then `attach-workspace --materialize missing --apply` reconstructs the source checkout directly in the existing workspace root. It never requires converting a single repository into a child of a non-Git container.

To add another source to an initialized v4 multi-repository workspace, use the
proposal-bound lifecycle (the direct member name and path must agree):

```bash
python3 scripts/wb.py add-workspace-member <workspace-root> \
  --repository-id <id> --remote <remote> --name <member> --path <member> \
  --default-branch main --dry-run
# Repeat the same request with --accepted-proposal-id <returned-id> --apply.
```

This preserves multi-repository mode and registers a verified existing checkout
or a new clone without creating a root Git repository. The checkout and Git
common directory stay inside the workspace. Replay verifies the local binding;
failed publication preserves adopted checkouts and removes only newly created
ones. Single/composite workspaces retain their root-source and exclusion behavior.

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

Run the deterministic repository gate with isolated dependencies:

```bash
uvx --python 3.13 --from pytest==9.1.1 --with pyyaml==6.0.3 --with sqlite-vec==0.1.9 --with fastembed==0.8.0 pytest -q
bin/work-bundle-skill validate
```

Run the keep-summarizing CLI through its pinned uv-managed environment:

```bash
uv run scripts/ks.py --help
```
